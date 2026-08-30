"""Domain enums and agent catalog shared by every component of AI Dev Office."""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    DONE = "DONE"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"  # Task cancelled by user or system


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    WORKING = "WORKING"
    WAITING = "WAITING"
    ERROR = "ERROR"


class EventKind(str, Enum):
    """Kinds of events emitted by AgentExecutor implementations."""

    STATUS = "STATUS"            # status change (agent/task)
    LOG = "LOG"                  # human readable progress line
    SUBTASKS = "SUBTASKS"        # ATLAS emitted a task breakdown
    QA_RESULT = "QA_RESULT"      # QA reported PASS/FAIL
    HEALTH = "HEALTH"            # PULSE health report
    REVIEW = "REVIEW"            # ATLAS review comments
    RESULT = "RESULT"            # final outcome for a task


# ---------------------------------------------------------------------------
# Agent catalog. The web dashboard renders these; every runtime keeps the same
# registry so a future LLM-backed executor swaps in without UI changes.
# ---------------------------------------------------------------------------

AGENT_ROLES = {
    "atlas": "Engineering Manager",
    "scout": "Research Agent",
    "forge": "Developer Agent",
    "qa": "Testing Agent",
    "pulse": "Monitoring Agent",
}

AGENT_COLORS = {
    "atlas": "#60a5fa",
    "scout": "#a78bfa",
    "forge": "#f59e0b",
    "qa": "#34d399",
    "pulse": "#22d3ee",
}

AGENT_ORDER = ["atlas", "scout", "forge", "qa", "pulse"]

# Activity feed is a ring buffer of this size in the API process.
ACTIVITY_BUFFER_SIZE = 300