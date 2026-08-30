"""Wires five mock agents into agent registry with its own factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_dev_agent_atlas import MockAtlasExecutor
from ai_dev_agent_core import AgentRegistry, ExecutionContext
from ai_dev_agent_forge import HermesExecutor, MockForgeExecutor
from ai_dev_agent_pulse import DeterministicPulseExecutor, MockPulseExecutor
from ai_dev_agent_qa import DeterministicQAExecutor, MockQAExecutor
from ai_dev_agent_scout import MockScoutExecutor, RealScoutExecutor
from ai_dev_shared import AGENT_COLORS, AGENT_ROLES, Task

_MOCK_CLASSES = {
    "atlas": MockAtlasExecutor,
    "scout": MockScoutExecutor,
    "forge": MockForgeExecutor,
    "qa": MockQAExecutor,
    "pulse": MockPulseExecutor,
}


@dataclass(frozen=True)
class MockFactory:
    """Creates fresh mock executor per task invocation."""

    agent_id: str
    executor_cls: type

    def __call__(self, task: Task, ctx: ExecutionContext):
        return self.executor_cls(task, ctx)


@dataclass(frozen=True)
class ScoutFactory:
    """Select mock or real SCOUT executor based on config."""

    agent_id: str = "scout"

    def __call__(self, task: Task, ctx: ExecutionContext) -> Any:
        from .config import settings

        if settings.scout_mode.lower() == "real":
            return RealScoutExecutor(task, ctx)
        return MockScoutExecutor(task, ctx)


@dataclass(frozen=True)
class QAFactory:
    """Select mock or deterministic QA executor."""

    agent_id: str = "qa"

    def __call__(self, task: Task, ctx: ExecutionContext) -> Any:
        from .config import settings

        if settings.qa_mode.lower() == "deterministic":
            executor = DeterministicQAExecutor(task, ctx)
            executor.timeout = settings.qa_timeout
            return executor

        return MockQAExecutor(task, ctx)


@dataclass(frozen=True)
class PulseFactory:
    """Select mock or deterministic (real) PULSE executor.

    Phase 4: deterministic local runtime/health monitoring is the default;
    mock is an explicit fallback (ADO_PULSE_MODE=mock)."""

    agent_id: str = "pulse"

    def __call__(self, task: Task, ctx: ExecutionContext) -> Any:
        from .config import settings

        if settings.pulse_mode.lower() == "mock":
            return MockPulseExecutor(task, ctx)

        return DeterministicPulseExecutor(task, ctx)


@dataclass(frozen=True)
class ForgeFactory:
    """Factory that selects MockForgeExecutor or HermesExecutor based on config."""

    agent_id: str = "forge"

    def __call__(self, task: Task, ctx: ExecutionContext) -> Any:
        """Create executor based on FORGE_MODE setting."""
        from .config import settings

        mode = settings.forge_mode.lower()

        if mode == "hermes":
            executor = HermesExecutor(
                task,
                ctx,
                model=settings.forge_model,
                provider=settings.forge_provider,
                max_turns=settings.forge_max_turns,
            )
            executor.timeout = settings.forge_timeout
            return executor
        else:
            # Default to mock
            return MockForgeExecutor(task, ctx)


def _name(agent_id: str) -> str:
    return {
        "atlas": "ATLAS",
        "scout": "SCOUT",
        "forge": "FORGE",
        "qa": "QA",
        "pulse": "PULSE",
    }.get(agent_id, agent_id.upper())


def build_registry() -> AgentRegistry:
    """A real LLM runtime mounts here: swap MockFactory agent_id -> cls
    table registrations built on another AgentExecutor implementation."""
    registry = AgentRegistry()

    # Register ATLAS, SCOUT and PULSE with mock factories.
    # FORGE, QA, and SCOUT have selectable execution modes.
    for agent_id, cls in _MOCK_CLASSES.items():
        if agent_id in {"forge", "qa", "pulse", "scout"}:
            continue

        registry.register(
            MockFactory(agent_id, cls),
            name=_name(agent_id),
            role=AGENT_ROLES[agent_id],
            color=AGENT_COLORS[agent_id],
        )

    registry.register(
        ScoutFactory(),
        name=_name("scout"),
        role=AGENT_ROLES["scout"],
        color=AGENT_COLORS["scout"],
    )

    registry.register(
        QAFactory(),
        name=_name("qa"),
        role=AGENT_ROLES["qa"],
        color=AGENT_COLORS["qa"],
    )

    registry.register(
        PulseFactory(),
        name=_name("pulse"),
        role=AGENT_ROLES["pulse"],
        color=AGENT_COLORS["pulse"],
    )

    # Register FORGE with smart factory (mock or hermes based on FORGE_MODE)
    registry.register(
        ForgeFactory(),
        name=_name("forge"),
        role=AGENT_ROLES["forge"],
        color=AGENT_COLORS["forge"],
    )

    return registry
