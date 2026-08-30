"""REST + WebSocket routes for the control room."""

from __future__ import annotations

import time
from typing import Any, Annotated

from ai_dev_shared import Task, TaskStatus
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .app_state import AppState, get_state
from .db import get_session
from .models import TaskRow
from .realtime import RealtimeBus

router = APIRouter(prefix="/api")
ws_router = APIRouter()
Session = Annotated[AsyncSession, Depends(get_session)]
State = Annotated[AppState, Depends(get_state)]


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=2000)
    # Optional path to the local project FORGE/QA/SCOUT should work on.
    # When supplied, the workspace is prepared as an isolated git worktree
    # (clean repo) or bounded copy (non-git). The source project is never
    # modified. Rejected if the repo has uncommitted changes.
    target_project: str | None = Field(default=None, max_length=4096)
    # Optional explicit monitoring config forwarded to PULSE. When omitted,
    # PULSE derives local targets from the task text.
    pulse_request: dict | None = None
    # Optional conversation session id (Phase 4.1). Tasks sharing a session
    # id participate in conversation continuation (active plan). When omitted
    # the default session is used.
    session_id: str | None = Field(default=None, max_length=64)


def _stats(tasks: list[Task]) -> dict[str, Any]:
    return {
        "total": len(tasks),
        "running": sum(
            t.status in (TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.REVIEW)
            for t in tasks
        ),
        "queued": sum(t.status == TaskStatus.QUEUED for t in tasks),
        "done": sum(t.status == TaskStatus.DONE for t in tasks),
        "failed": sum(t.status == TaskStatus.FAILED for t in tasks),
    }


def _snapshot(
    state: AppState, tasks: list[Task]
) -> dict[str, Any]:
    # Activity feed is in-memory (engine.feed) plus what is persisted. The
    # WS snapshot is sent from an async handler; we use the in-memory feed
    # here (persistence is for restart/reconnect reconciliation, loaded by the
    # dedicated /api/activity endpoint which is async-safe).
    return {
        "tasks": [t.model_dump() for t in tasks],
        "agents": state.registry.snapshot(),
        "activity": [a.model_dump() for a in reversed(list(state.engine.feed))],
        "stats": _stats(tasks),
        "running_task_id": state.engine.running_task_id,
    }


# ---------------------------------------------------------------- REST
@router.get("/health")
async def health(state: State) -> dict[str, Any]:
    return {"status": "ok", "service": "ai-dev-office", "time": time.time()}


@router.get("/snapshot")
async def snapshot(state: State, session: Session) -> dict[str, Any]:
    rows = (await session.execute(select(TaskRow).order_by(TaskRow.created_at))).scalars()
    tasks = [r.to_task() for r in rows]
    return _snapshot(state, tasks)


@router.get("/tasks")
async def list_tasks(state: State, session: Session) -> list[dict[str, Any]]:
    rows = (await session.execute(select(TaskRow).order_by(TaskRow.created_at))).scalars()
    return [r.to_task().model_dump() for r in rows]


@router.post("/tasks", status_code=201)
async def create_task(payload: TaskCreate, state: State, session: Session) -> dict[str, Any]:
    from ai_dev_shared.workspace import (
        validate_target_project,
        WorkspaceValidationError,
        DirtyRepositoryError,
    )

    # Validate target_project before creating the task record.
    if payload.target_project:
        try:
            validate_target_project(payload.target_project)
        except DirtyRepositoryError as exc:
            raise HTTPException(
                409,
                f"Target project has uncommitted changes. "
                f"Commit or discard them first. ({exc})",
            )
        except WorkspaceValidationError as exc:
            raise HTTPException(422, f"Invalid target_project: {exc}")

    task = Task(
        title=payload.title,
        description=payload.description,
        target_project=payload.target_project,
        pulse_request=payload.pulse_request,
        session_id=payload.session_id,
    )
    session.add(TaskRow.from_task(task))
    await session.commit()
    await state.engine.enqueue(task)
    return task.model_dump()


@router.get("/agents")
async def list_agents(state: State) -> list[dict[str, Any]]:
    return state.registry.snapshot()


@router.get("/activity")
async def activity(state: State, session: Session) -> list[dict[str, Any]]:
    # In-memory feed (most recent events this process) plus persisted history
    # from the database (survives restart/reconnect). Merge + dedupe by id.
    from .models import ActivityRow
    from sqlalchemy import select

    persisted = (
        await session.execute(select(ActivityRow).order_by(ActivityRow.at))
    ).scalars().all()
    persisted_items = [r.to_item() for r in persisted]

    seen = {a.id for a in persisted_items}
    for item in reversed(list(state.engine.feed)):
        if item.id not in seen:
            persisted_items.append(item)
            seen.add(item.id)

    persisted_items.sort(key=lambda a: a.at)
    return [a.model_dump() for a in reversed(persisted_items)]


@router.delete("/tasks/{task_id}", status_code=204)
async def cancel_task(task_id: str, state: State, session: Session) -> None:
    """Cancel a task - works for both QUEUED and RUNNING tasks."""
    from ai_dev_agent_forge.executor import cancel_task_execution as cancel_forge

    task = await session.get(TaskRow, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")

    task_status = TaskStatus(task.status)

    # Cancel QUEUED task (not yet started)
    if task_status == TaskStatus.QUEUED:
        if state.engine.cancel_pending(task_id):
            await session.delete(task)
            await session.commit()
        return

    # Cancel RUNNING task
    if task_status in (TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.REVIEW):
        # Ask the engine to stop the pipeline for this task. The engine checks
        # the cancel flag after each streamed event, marks the task
        # INTERRUPTED, and signals any live FORGE Hermes subprocess (without
        # touching the global Hermes gateway). Returns True if this is the
        # actively-running task.
        engine_cancelled = state.engine.cancel_running(task_id)

        # Mark the task INTERRUPTED in the DB and broadcast regardless, so the
        # UI reflects the cancel immediately even if the engine is between
        # events. The engine will also persist/emit the final INTERRUPTED state.
        task.status = TaskStatus.INTERRUPTED.value
        task.error = "Task cancelled by user"
        task.updated_at = time.time()
        await session.commit()

        await state.bus.broadcast({
            "type": "task_status",
            "data": {
                "id": task_id,
                "status": TaskStatus.INTERRUPTED.value,
                "error": "Task cancelled by user",
            }
        })
        return

    raise HTTPException(409, f"Cannot cancel task with status {task_status.value}")


# ---------------------------------------------------------------- WS
# NOTE: defined with a full path so the APIRouter(prefix="/api") does not
# rewrite it to /api/ws.
ws_router = APIRouter()


@ws_router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    state = get_state()
    bus: RealtimeBus = state.bus
    await bus.connect(ws)
    try:
        from .models import ActivityRow
        from sqlalchemy import select

        async with state.session_factory() as session:
            rows = (
                await session.execute(select(TaskRow).order_by(TaskRow.created_at))
            ).scalars()
            tasks = [r.to_task() for r in rows]

            # Reconcile activity: persisted history + in-memory (this process)
            persisted = (
                await session.execute(select(ActivityRow).order_by(ActivityRow.at))
            ).scalars().all()
            persisted_items = [r.to_item() for r in persisted]
            seen = {a.id for a in persisted_items}
            for item in reversed(list(state.engine.feed)):
                if item.id not in seen:
                    persisted_items.append(item)
                    seen.add(item.id)
            persisted_items.sort(key=lambda a: a.at)

            snap = _snapshot(state, tasks)
            snap["activity"] = [a.model_dump() for a in reversed(persisted_items)]

        await ws.send_json({"type": "snapshot", "data": snap})
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await bus.disconnect(ws)