"""The executor contract.

An AgentExecutor is the **only** interface the orchestration engine talks to.
Real runtimes (Hermes, OpenAI, Claude, a local LLM, ...) mount by implementing
this same protocol -- the dashboard, task flow and event system stay unchanged.

The MVP ships with MockAgentExecutor implementations that stream fabricated
events so the whole control-room flow is testable without any LLM.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from ai_dev_shared.models import AgentEvent, Task


@runtime_checkable
class AgentExecutor(Protocol):
    """Executes a single task and streams progress events."""

    agent_id: str

    def execute(
        self, task: Task, ctx: "ExecutionContext"
    ) -> AsyncIterator[AgentEvent]:
        """Yield AgentEvents describing the agent's progress.

        Order of the stream decides the final outcome: a `RESULT` event with a
        FAILED task_status marks the task failed, otherwise the outcome is the
        last RESULT emitted.
        """
        ...


@runtime_checkable
class ExecutorFactory(Protocol):
    """Creates a fresh executor when a task is dispatched to an agent."""

    agent_id: str

    def __call__(self, task: Task, ctx: "ExecutionContext") -> "AgentExecutor":
        ...