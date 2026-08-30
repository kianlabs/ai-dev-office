"""FastAPI entrypoint for AI Dev Office."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from ai_dev_agent_core import OrchestrationEngine
from ai_dev_shared import TaskStatus
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .agents import build_registry
from .app_state import AppState, set_state
from .config import settings
from .db import init_db, session_factory
from .realtime import RealtimeBus
from .routes import router, ws_router

STATE: AppState | None = None


async def _persist_task(task) -> None:
    from .models import TaskRow

    async with session_factory() as session:
        row = await session.get(TaskRow, task.id)
        fresh = TaskRow.from_task(task)
        if row is None:
            session.add(fresh)
        else:
            row.title = fresh.title
            row.description = fresh.description
            row.status = fresh.status
            row.subtasks = fresh.subtasks
            row.summary = fresh.summary
            row.error = fresh.error
            row.created_at = fresh.created_at
            row.updated_at = fresh.updated_at
        await session.commit()


async def _persist_activity(item) -> None:
    """Persist each activity item so the feed survives restarts/reconnects."""
    from .models import ActivityRow

    async with session_factory() as session:
        # Idempotent: skip if this event id is already stored.
        existing = await session.get(ActivityRow, item.id)
        if existing is not None:
            return
        session.add(ActivityRow.from_item(item))
        await session.commit()


async def _recover_orphans() -> None:
    """Mark RUNNING/REVIEW tasks from a dead backend as INTERRUPTED.

    On startup the in-memory execution state is gone, so any task left in a
    non-terminal state was interrupted by the previous process exiting.
    """
    from .models import TaskRow

    terminal = {TaskStatus.DONE.value, TaskStatus.FAILED.value, TaskStatus.INTERRUPTED.value}
    async with session_factory() as session:
        rows = (await session.execute(select(TaskRow))).scalars().all()
        for row in rows:
            if row.status not in terminal:
                row.status = TaskStatus.INTERRUPTED.value
                row.error = "Eksekusi terputus karena backend berhenti."
                row.updated_at = time.time()
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    await _recover_orphans()
    registry = build_registry()
    bus = RealtimeBus()

    engine = OrchestrationEngine(
        registry,
        orchestrator_agent="atlas",
        broadcast=bus.broadcast,
        persist_task=_persist_task,
        persist_activity=_persist_activity,
        settings={"speed": settings.speed},
    )
    state = AppState(registry=registry, engine=engine, bus=bus, session_factory=session_factory)
    set_state(state)
    app.state.state = state
    yield


app = FastAPI(title="AI Dev Office", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "AI Dev Office API",
        "status": "running",
        "routes": ["/api/snapshot", "/api/tasks", "/api/agents", "/api/activity", "/ws"],
        "time": time.time(),
    }