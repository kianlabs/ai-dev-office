"""Persistence: one row per task; subtasks stored as JSON."""

from __future__ import annotations

import json

from ai_dev_shared import Subtask, Task, TaskStatus
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