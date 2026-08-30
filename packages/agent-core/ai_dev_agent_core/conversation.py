"""Bounded conversation session context (Phase 4.1).

Keeps a minimal, process-local session state so multi-message conversations
work ("buat plan aplikasi inventory" → "pakai PostgreSQL aja" →
"implementasikan") without ever handing a full conversation transcript to a
specialist. FORGE only ever receives a bounded plan brief derived from the
active plan.

Deliberately bounded: one active plan per session, a capped number of
sessions, and no raw message history.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any

DEFAULT_SESSION_ID = "default"

# Maximum number of sessions kept in memory (least-recently-used eviction).
_MAX_SESSIONS = 64


class ConversationStore:
    """Per-session, bounded conversation context."""

    def __init__(self, max_sessions: int = _MAX_SESSIONS) -> None:
        self._plans: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._updated_at: dict[str, float] = {}
        self._max_sessions = max_sessions

    # ------------------------------------------------------------- sessions
    @staticmethod
    def normalize_session_id(session_id: str | None) -> str:
        return (session_id or DEFAULT_SESSION_ID).strip() or DEFAULT_SESSION_ID

    def _evict_if_needed(self) -> None:
        while len(self._plans) > self._max_sessions:
            oldest, _ = self._plans.popitem(last=False)
            self._updated_at.pop(oldest, None)

    # ---------------------------------------------------------- active plan
    def set_active_plan(self, session_id: str | None, plan: dict[str, Any]) -> dict[str, Any]:
        key = self.normalize_session_id(session_id)
        self._plans[key] = plan
        self._plans.move_to_end(key)
        self._updated_at[key] = time.time()
        self._evict_if_needed()
        return plan

    def get_active_plan(self, session_id: str | None) -> dict[str, Any] | None:
        key = self.normalize_session_id(session_id)
        plan = self._plans.get(key)
        if plan is not None:
            self._plans.move_to_end(key)
        return plan

    def has_active_plan(self, session_id: str | None) -> bool:
        return self.get_active_plan(session_id) is not None

    def clear_active_plan(self, session_id: str | None) -> None:
        key = self.normalize_session_id(session_id)
        self._plans.pop(key, None)
        self._updated_at.pop(key, None)


# Process-global store: the control room is a single-process service.
_store = ConversationStore()


def get_conversation_store() -> ConversationStore:
    return _store


def reset_conversation_store() -> None:
    """Test helper: swap in a fresh store."""
    global _store
    _store = ConversationStore()
