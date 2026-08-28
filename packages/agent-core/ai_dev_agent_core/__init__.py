"""ai-dev-agent-core: executor contract, registry and orchestration engine."""

from ai_dev_agent_core.base import MockRuntime
from ai_dev_agent_core.context import (
    DispatchForbiddenError,
    ExecutionContext,
    MAX_DISPATCH_HOPS,
    ORCHESTRATOR_AGENT,
    WORKER_AGENTS,
)
from ai_dev_agent_core.engine import OrchestrationEngine
from ai_dev_agent_core.executor import AgentExecutor, ExecutorFactory
from ai_dev_agent_core.mock_content import (
    classify_intent,
    doc_subject_for,
    repo_name_for,
)
from ai_dev_agent_core.registry import AgentRegistry

__all__ = [
    "MockRuntime",
    "ExecutionContext",
    "OrchestrationEngine",
    "AgentExecutor",
    "ExecutorFactory",
    "AgentRegistry",
    "classify_intent",
    "doc_subject_for",
    "repo_name_for",
    "DispatchForbiddenError",
    "ORCHESTRATOR_AGENT",
    "WORKER_AGENTS",
    "MAX_DISPATCH_HOPS",
]