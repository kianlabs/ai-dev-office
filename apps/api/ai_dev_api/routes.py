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
    task = Task(title=payload.title, description=payload.description)
    session.add(TaskRow.from_task(task))
    await session.commit()
    await state.engine.enqueue(task)
    return task.model_dump()


@router.get("/agents")
async def list_agents(state: State) -> list[dict[str, Any]]:
    return state.registry.snapshot()


@router.get("/activity")
async def activity(state: State) -> list[dict[str, Any]]:
    return [a.model_dump() for a in reversed(list(state.engine.feed))]


@router.delete("/tasks/{task_id}", status_code=204)
async def cancel_task(task_id: str, state: State, session: Session) -> None:
    task = await session.get(TaskRow, task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    if task.status == TaskStatus.QUEUED.value:
        if state.engine.cancel_pending(task_id):
            await session.delete(task)
            await session.commit()
        return
    raise HTTPException(409, "Only queued tasks can be cancelled")


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
        async with state.session_factory() as session:
            rows = (
                await session.execute(select(TaskRow).order_by(TaskRow.created_at))
            ).scalars()
            tasks = [r.to_task() for r in rows]
        await ws.send_json({"type": "snapshot", "data": _snapshot(state, tasks)})
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await bus.disconnect(ws)