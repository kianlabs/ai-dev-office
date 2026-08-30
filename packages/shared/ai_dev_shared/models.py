"""Pydantic models for the domain: tasks, events, agent records."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from .constants import AgentStatus, EventKind, TaskStatus


class Subtask(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    title: str
    agent_id: str
    status: TaskStatus = TaskStatus.QUEUED


class Task(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    subtasks: list[Subtask] = Field(default_factory=list)
    summary: str | None = None
    error: str | None = None
    # Optional conversation session id (Phase 4.1). Tasks sharing a session
    # id participate in conversation continuation (active plan).
    session_id: str | None = None
    # Structured ATLAS response (Phase 4.1): {intent, message, plan,
    # needs_input}. Set when ATLAS finishes so the UI can show the answer
    # without the user reading raw activity telemetry.
    atlas_response: dict | None = None
    # Optional path to the local project this task targets. When set the
    # workspace preparation creates an isolated git worktree or bounded copy
    # so the source repository is never modified by FORGE/QA/SCOUT.
    target_project: str | None = None
    # Optional explicit monitoring configuration for PULSE:
    #   {"expected_processes": [...], "ports": [...], "health_urls": [...],
    #    "log_files": [...]}
    # When unset, PULSE derives loopback-only targets from the task text.
    pulse_request: dict | None = None
    # Workspace metadata after preparation (mode, source_head, etc.).
    workspace_meta: dict | None = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class AgentEvent(BaseModel):
    """The universal stream primitive.

    Every AgentExecutor yields a stream of these. The orchestration engine
    persists, broadcasts, and reflects them onto agent/task state.
    """

    agent_id: str
    kind: EventKind
    message: str = ""
    agent_status: AgentStatus | None = None
    task_status: TaskStatus | None = None
    subtasks: list[Subtask] = Field(default_factory=list)
    score: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    at: float = Field(default_factory=time.time)


class AgentRecord(BaseModel):
    agent_id: str
    name: str
    role: str
    color: str
    status: AgentStatus = AgentStatus.IDLE
    activity: str = "Idle"
    last_event_at: float = Field(default_factory=time.time)


class ActivityItem(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    at: float = Field(default_factory=time.time)
    agent_id: str
    agent_name: str
    task_id: str | None = None
    message: str
    kind: EventKind = EventKind.LOG


__all__ = [
    "TaskStatus",
    "AgentStatus",
    "EventKind",
    "Subtask",
    "Task",
    "AgentEvent",
    "AgentRecord",
    "ActivityItem",
]