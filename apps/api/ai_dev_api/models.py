"""Persistence: one row per task; subtasks stored as JSON.

ActivityItem rows are appended so the feed survives backend restarts and
WebSocket reconnects (root cause of Issue 1).
"""

from __future__ import annotations

import json

from ai_dev_shared import ActivityItem, Subtask, Task, TaskStatus
from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.QUEUED.value)
    subtasks: Mapped[str] = mapped_column(Text, default="[]")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

    def to_task(self) -> Task:
        raw_subtasks: list[dict] = json.loads(self.subtasks or "[]")
        return Task(
            id=self.id,
            title=self.title,
            description=self.description,
            status=TaskStatus(self.status),
            subtasks=[Subtask(**s) for s in raw_subtasks],
            summary=self.summary,
            error=self.error,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_task(cls, task: Task) -> "TaskRow":
        return cls(
            id=task.id,
            title=task.title,
            description=task.description,
            status=task.status.value,
            subtasks=json.dumps([s.model_dump() for s in task.subtasks]),
            summary=task.summary,
            error=task.error,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


class ActivityRow(Base):
    """Append-only activity feed entry persisted to the database."""

    __tablename__ = "activity"

    # Composite key: a stable per-event id so re-broadcasts are idempotent.
    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    at: Mapped[float] = mapped_column(Float, index=True)
    agent_id: Mapped[str] = mapped_column(String(20))
    agent_name: Mapped[str] = mapped_column(String(40))
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))

    def to_item(self) -> ActivityItem:
        return ActivityItem(
            id=self.id,
            at=self.at,
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            task_id=self.task_id,
            message=self.message,
            kind=self.kind,  # type: ignore[arg-type]
        )

    @classmethod
    def from_item(cls, item: ActivityItem) -> "ActivityRow":
        return cls(
            id=item.id,
            at=item.at,
            agent_id=item.agent_id,
            agent_name=item.agent_name,
            task_id=item.task_id,
            message=item.message,
            kind=item.kind.value,
        )