"""Application-wide state holder.

Routes (HTTP and WebSocket) resolve these via a dependency that does not need
the ``Request`` object -- FastAPI does not inject ``Request`` into dependencies
resolved for WebSocket routes, so we keep the live store module-global instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_dev_agent_core import OrchestrationEngine

from .realtime import RealtimeBus


@dataclass
class AppState:
    registry: Any
    engine: OrchestrationEngine
    bus: RealtimeBus = field(default_factory=RealtimeBus)
    session_factory: Any = None


_state: AppState | None = None


def set_state(state: AppState | None) -> None:
    global _state
    _state = state


def get_state() -> AppState:
    if _state is None:
        raise RuntimeError("AppState not initialized (lifespan did not run?)")
    return _state