"""Base class for mock runtimes.

MockAgentExecutor implementations subclass :class:`MockRuntime` to get a
readable way of expressing event streams. Real LLM-backed runtimes will not
need this class -- they implement :class:`AgentExecutor` directly.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from ai_dev_shared.constants import AgentStatus, EventKind, TaskStatus
from ai_dev_shared.models import AgentEvent, Subtask, Task

from .context import ExecutionContext

_DEFAULT_DELAY = 0.5


class MockRuntime:
    """Helpers used by the mock executors that ship with the MVP.

    Subclasses must expose ``agent_id`` and are ``async def execute(task, ctx)``
    async generators.
    """

    agent_id: str = ""

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.rng: random.Random = ctx.rng

    # -- event construction -------------------------------------------------
    def _ev(
        self,
        kind: EventKind,
        message: str = "",
        *,
        agent_status: AgentStatus | None = None,
        task_status: TaskStatus | None = None,
        subtasks: list[Subtask] | None = None,
        score: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            agent_id=self.agent_id,
            kind=kind,
            message=message,
            agent_status=agent_status,
            task_status=task_status,
            subtasks=subtasks or [],
            score=score,
            meta=meta or {},
        )

    def say(self, message: str, **kw: Any) -> AgentEvent:
        return self._ev(EventKind.LOG, message, **kw)

    def set_status(
        self,
        status: AgentStatus,
        activity: str = "",
        *,
        task_status: TaskStatus | None = None,
    ) -> AgentEvent:
        return self._ev(
            EventKind.STATUS,
            message=activity,
            agent_status=status,
            task_status=task_status,
        )

    def working(self, activity: str, task_status: TaskStatus | None = None) -> AgentEvent:
        return self.set_status(AgentStatus.WORKING, activity, task_status=task_status)

    def waiting(self, activity: str) -> AgentEvent:
        return self.set_status(AgentStatus.WAITING, activity)

    def idle(self, activity: str = "") -> AgentEvent:
        return self.set_status(AgentStatus.IDLE, activity or "Idle")

    def failure(self, activity: str) -> AgentEvent:
        return self.set_status(AgentStatus.ERROR, activity)

    def emit_subtasks(self, subtasks: list[Subtask], message: str) -> AgentEvent:
        return self._ev(EventKind.SUBTASKS, message, subtasks=subtasks)

    def qa_result(
        self,
        score: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> AgentEvent:
        return self._ev(
            EventKind.QA_RESULT,
            message,
            score=score,
            meta=meta or {},
        )

    def health(self, message: str, meta: dict[str, Any] | None = None) -> AgentEvent:
        return self._ev(EventKind.HEALTH, message, meta=meta or {})

    def review(self, message: str, meta: dict[str, Any] | None = None) -> AgentEvent:
        return self._ev(EventKind.REVIEW, message, meta=meta or {})

    def result(
        self, task_status: TaskStatus, summary: str, meta: dict[str, Any] | None = None
    ) -> AgentEvent:
        return self._ev(
            EventKind.RESULT,
            summary,
            task_status=task_status,
            meta=meta or {},
        )

    # -- pacing -------------------------------------------------------------
    async def tick(self, event: AgentEvent) -> AgentEvent:
        """Sleep a little so the control room feels alive, then return the event."""
        base = _DEFAULT_DELAY * (0.6 + 0.8 * self.rng.random())
        await asyncio.sleep(base / self.ctx.speed)
        return event