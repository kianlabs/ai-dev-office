"""Execution context passed into every AgentExecutor invocation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ai_dev_shared.models import Task

if TYPE_CHECKING:
    from .registry import AgentRegistry


@dataclass
class ExecutionContext:
    """Everything a runtime needs to work on one task."""

    task: Task
    settings: dict[str, Any] = field(default_factory=dict)
    registry: "AgentRegistry | None" = None
    seed: int = 0

    @property
    def rng(self) -> random.Random:
        key = f"rng-{id(self)}"
        stored = getattr(self, key, None)
        if stored is None:
            stored = random.Random(self.seed)
            setattr(self, key, stored)
        return stored

    @property
    def speed(self) -> float:
        """Speed multiplier: higher = faster. e.g. 1.0 realtime, 8.0 demo."""
        return max(0.25, float(self.settings.get("speed", 1.0)))