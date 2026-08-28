"""Agent registry: where every agent's identity and executor factory live."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ai_dev_shared import AgentRecord

from .executor import ExecutorFactory

if TYPE_CHECKING:
    from ai_dev_shared.constants import AgentStatus
    from .context import ExecutionContext
    from .executor import AgentExecutor


class AgentRegistry:
    """Maps agent ids to metadata + a factory producing per-task executors."""

    def __init__(self) -> None:
        self._records: dict[str, AgentRecord] = {}
        self._factories: dict[str, ExecutorFactory] = {}

    def register(
        self,
        factory: ExecutorFactory,
        *,
        name: str,
        role: str,
        color: str,
    ) -> None:
        agent_id = factory.agent_id
        self._records[agent_id] = AgentRecord(
            agent_id=agent_id, name=name, role=role, color=color
        )
        self._factories[agent_id] = factory

    def executor_for(self, agent_id: str, task: Any, ctx: Any) -> "AgentExecutor":
        return self._factories[agent_id](task, ctx)

    def record(self, agent_id: str) -> AgentRecord:
        return self._records[agent_id]

    def apply(
        self,
        agent_id: str,
        *,
        status: "AgentStatus | None" = None,
        activity: str | None = None,
    ) -> None:
        rec = self._records[agent_id]
        if status is not None:
            rec.status = status
        if activity is not None:
            rec.activity = activity

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            self._records[a].model_dump()
            for a in ("atlas", "scout", "forge", "qa", "pulse")
            if a in self._records
        ]

    def ids(self) -> list[str]:
        return list(self._factories)