"""Execution context passed into every AgentExecutor invocation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ai_dev_shared.models import AgentEvent, Task

if TYPE_CHECKING:
    from .registry import AgentRegistry


# Dispatch guard constants
ORCHESTRATOR_AGENT = "atlas"
WORKER_AGENTS = {"scout", "forge", "qa", "pulse"}
MAX_DISPATCH_HOPS = 8


class DispatchForbiddenError(RuntimeError):
    """Raised when dispatch violates orchestration rules."""
    pass


@dataclass
class ExecutionContext:
    """Everything a runtime needs to work on one task."""

    task: Task
    settings: dict[str, Any] = field(default_factory=dict)
    registry: AgentRegistry | None = None
    seed: int = 0
    _dispatch_path: list[str] = field(default_factory=list, repr=False)
    _caller_agent: str | None = field(default=None, repr=False)

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

    def dispatch(self, agent_id: str) -> Any:
        """Create an executor for a subtask via registry.

        This is the ONLY way ATLAS should delegate to other agents.
        The registry selects the appropriate executor (mock or real).

        Raises:
            DispatchForbiddenError: If dispatch violates orchestration rules.
        """
        if self.registry is None:
            raise RuntimeError("Cannot dispatch: no registry in context")

        # Rule 1: Only ATLAS (orchestrator) can dispatch
        if self._caller_agent and self._caller_agent != ORCHESTRATOR_AGENT:
            raise DispatchForbiddenError(
                f"worker_dispatch_forbidden: {self._caller_agent} cannot dispatch {agent_id} "
                f"(only {ORCHESTRATOR_AGENT} can dispatch)"
            )

        # Rule 2: Block recursive dispatch (agent dispatching itself)
        if agent_id in self._dispatch_path:
            path_str = " → ".join(self._dispatch_path + [agent_id])
            raise DispatchForbiddenError(
                f"recursive_dispatch: {agent_id} already in dispatch path [{path_str}]"
            )

        # Rule 3: Max dispatch hops
        if len(self._dispatch_path) >= MAX_DISPATCH_HOPS:
            path_str = " → ".join(self._dispatch_path)
            raise DispatchForbiddenError(
                f"max_dispatch_hops: exceeded {MAX_DISPATCH_HOPS} hops in path [{path_str}]"
            )

        # Create child context with updated dispatch path
        child_ctx = ExecutionContext(
            task=self.task,
            settings=self.settings,
            registry=self.registry,
            seed=self.seed,
            _dispatch_path=self._dispatch_path + [agent_id],
            _caller_agent=agent_id,
        )

        executor = self.registry.executor_for(agent_id, self.task, child_ctx)

        # Keep the child context attached to the executor returned for
        # backwards compatibility with existing dispatch() callers.
        setattr(executor, "_dispatch_ctx", child_ctx)
        return executor

    async def dispatch_stream(self, agent_id: str):
        """Dispatch a worker and stream events with its child context."""
        executor = self.dispatch(agent_id)
        child_ctx = getattr(executor, "_dispatch_ctx")

        async for event in executor.execute(self.task, child_ctx):
            yield event
