"""Wires the five mock agents into the agent registry with its own factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_dev_agent_atlas import MockAtlasExecutor
from ai_dev_agent_core import AgentRegistry, ExecutionContext
from ai_dev_agent_forge import MockForgeExecutor
from ai_dev_agent_pulse import MockPulseExecutor
from ai_dev_agent_qa import MockQAExecutor
from ai_dev_agent_scout import MockScoutExecutor
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
    """Creates a fresh mock executor per task invocation."""

    agent_id: str
    executor_cls: type

    def __call__(self, task: Task, ctx: ExecutionContext):
        return self.executor_cls(task, ctx)


def build_registry() -> AgentRegistry:
    """A real LLM runtime mounts here: swap the MockFactory agent_id -> cls
    table for registrations built on another AgentExecutor implementation.
    """
    registry = AgentRegistry()
    for agent_id, cls in _MOCK_CLASSES.items():
        registry.register(
            MockFactory(agent_id, cls),
            name=_name(agent_id),
            role=AGENT_ROLES[agent_id],
            color=AGENT_COLORS[agent_id],
        )
    return registry


def _name(agent_id: str) -> str:
    return {
        "atlas": "ATLAS",
        "scout": "SCOUT",
        "forge": "FORGE",
        "qa": "QA",
        "pulse": "PULSE",
    }[agent_id]


def infer_intent(task: Task) -> str:
    from ai_dev_agent_core import classify_intent

    return classify_intent(task)