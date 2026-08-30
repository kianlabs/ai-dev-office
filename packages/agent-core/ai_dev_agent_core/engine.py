"""Orchestration engine.

Responsible for the lifecycle of a task end to end:

    QUEUED -> executor stream (PLANNING/RUNNING/REVIEW as decided inside the
    orchestrator agent) -> DONE | FAILED

The engine does not know about LLMs. It consumes an :class:`AgentEvent`
stream from an :class:`AgentExecutor` and:

  * reflects agent status onto the registry,
  * mirrors task state (subtasks, summary, error, status),
  * appends entries to the activity feed,
  * broadcasts over the realtime bus.

Tasks are executed one at a time (the orchestrator agent is a single slot) --
extra tasks stay QUEUED until the current pipeline finishes.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable

from ai_dev_shared import (
    ACTIVITY_BUFFER_SIZE,
    ActivityItem,
    Task,
    TaskStatus,
)
from ai_dev_shared.models import AgentStatus, EventKind

from .context import ExecutionContext
from .registry import AgentRegistry

Broadcast = Callable[[dict[str, Any]], Awaitable[None]]
PersistTask = Callable[[Task], Awaitable[None] | None]
PersistActivity = Callable[[ActivityItem], Awaitable[None] | None]


class OrchestrationEngine:
    def __init__(
        self,
        registry: AgentRegistry,
        *,
        orchestrator_agent: str = "atlas",
        broadcast: Broadcast | None = None,
        persist_task: PersistTask | None = None,
        persist_activity: PersistActivity | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.registry = registry
        self.orchestrator_agent = orchestrator_agent
        self._broadcast = broadcast or (lambda _m: None)
        self._persist_task = persist_task or (lambda _t: None)
        self._persist_activity = persist_activity or _noop_async
        self.settings = settings or {}
        self.feed: deque[ActivityItem] = deque(maxlen=ACTIVITY_BUFFER_SIZE)
        self._lock = asyncio.Lock()
        self._pending: deque[Task] = deque()
        self._running: Task | None = None
        self._worker: asyncio.Task | None = None
        # Task IDs the user has requested to cancel while running.
        self._cancelled: set[str] = set()

    # ------------------------------------------------------------------ API
    async def enqueue(self, task: Task) -> Task:
        """Queue a task. Execution begins when the orchestrator slot frees up.

        Deliberately not holding the pump lock: this can be called from a REST
        handler and returns immediately, execution happens in the background.
        """
        task.status = TaskStatus.QUEUED
        task.updated_at = time.time()
        self._pending.append(task)
        await self._emit_task(task, "task_status")
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._pump())
        return task

    @property
    def running_task_id(self) -> str | None:
        return self._running.id if self._running else None

    def cancel_pending(self, task_id: str) -> bool:
        """Remove a not-yet-started task from the queue. True if removed."""
        before = len(self._pending)
        self._pending = deque(t for t in self._pending if t.id != task_id)
        return len(self._pending) < before

    def cancel_running(self, task_id: str) -> bool:
        """Request cancellation of a currently-running task.

        Returns True if the task is the active running task (or already
        tracked for cancellation). The pipeline checks this flag after each
        streamed event and stops cleanly, marking the task INTERRUPTED.

        Also signals any live FORGE Hermes subprocess for this task so it
        terminates promptly (does NOT touch the global Hermes gateway).
        """
        if self._running is not None and self._running.id == task_id:
            self._cancelled.add(task_id)
            # Best-effort: kill the FORGE subprocess if one is registered.
            try:
                from ai_dev_agent_forge.executor import cancel_task_execution
                cancel_task_execution(task_id)
            except Exception:
                pass
            return True
        # If not the running task but was queued, let cancel_pending handle it.
        return False

    # --------------------------------------------------------------- pump
    async def _pump(self) -> None:
        async with self._lock:
            while self._pending:
                task = self._pending.popleft()
                self._running = task
                await self._run_pipeline(task)
        self._running = None
        self._worker = None

    async def _run_pipeline(self, task: Task) -> None:
        await self._emit_task(task, "task_status")

        ctx = ExecutionContext(
            task=task,
            settings=self.settings,
            registry=self.registry,
            seed=int(task.id[:8], 16),
        )
        executor = self.registry.executor_for(self.orchestrator_agent, task, ctx)

        finished = False
        try:
            async for event in executor.execute(task, ctx):
                await self._apply(event, task)
                # Stop the pipeline if the user cancelled this task.
                if task.id in self._cancelled:
                    break
            finished = True
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - failing agent fails the task
            rec = self.registry.record(executor.agent_id)
            rec.status = AgentStatus.ERROR
            rec.activity = str(err)[:120]
            task.status = TaskStatus.FAILED
            task.error = str(err)[:500]
            await self._broadcast(
                {"type": "agent_status", "data": rec.model_dump()}
            )

        if task.id in self._cancelled:
            # User cancelled: report INTERRUPTED, not FAILED/DONE.
            task.status = TaskStatus.INTERRUPTED
            task.error = task.error or "Task cancelled by user"
            # Reset busy agents to idle.
            for agent_id in ("atlas", "scout", "forge", "qa", "pulse"):
                rec = self.registry.record(agent_id)
                if rec.status != AgentStatus.IDLE:
                    rec.status = AgentStatus.IDLE
                    rec.activity = "Idle"
                    await self._broadcast(
                        {"type": "agent_status", "data": rec.model_dump()}
                    )
        elif not finished and task.status not in (TaskStatus.DONE, TaskStatus.FAILED):
            # Executor ended without a RESULT event: defensive default.
            task.status = TaskStatus.FAILED
            task.error = task.error or "Executor finished without a RESULT event."

        task.updated_at = time.time()
        if self._persist_task is not None:
            await _maybe_await(self._persist_task(task))
        await self._emit_task(task, "task_status")
        await self._broadcast({"type": "task_finished", "data": task.model_dump()})

    # ------------------------------------------------------------- events
    async def _apply(self, event: Any, task: Task) -> None:
        old_task_status = task.status
        rec = self.registry.record(event.agent_id)

        if event.agent_status is not None:
            rec.status = event.agent_status
        rec.last_event_at = event.at

        if event.task_status is not None:
            task.status = event.task_status
        if event.message:
            rec.activity = event.message
        if event.subtasks:
            task.subtasks = event.subtasks
        if event.kind == EventKind.RESULT:
            task.summary = event.message
            if task.status == TaskStatus.FAILED:
                task.error = event.meta.get("error")

        task.updated_at = time.time()
        if self._persist_task is not None:
            await _maybe_await(self._persist_task(task))

        if event.message and event.kind in (
            EventKind.LOG,
            EventKind.SUBTASKS,
            EventKind.QA_RESULT,
            EventKind.HEALTH,
            EventKind.REVIEW,
            EventKind.RESULT,
            EventKind.STATUS,
        ):
            item = ActivityItem(
                at=event.at,
                agent_id=event.agent_id,
                agent_name=rec.name,
                task_id=task.id,
                message=event.message,
                kind=event.kind,
            )
            self.feed.append(item)
            await self._persist_activity(item)
            await self._broadcast({"type": "feed", "data": item.model_dump()})

        if event.agent_status is not None:
            await self._broadcast(
                {"type": "agent_status", "data": rec.model_dump()}
            )
        if task.status != old_task_status:
            await self._emit_task(task, "task_status")

    async def _emit_task(self, task: Task, kind: str) -> None:
        await self._broadcast({"type": kind, "data": task.model_dump()})


async def _maybe_await(result: Awaitable[None] | None) -> None:
    if result is not None:
        await result


async def _noop_async(_: Any) -> None:
    """Default no-op activity persister when no DB callback is wired."""