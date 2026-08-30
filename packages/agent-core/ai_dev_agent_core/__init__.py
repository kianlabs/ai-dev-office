"""ai-dev-agent-core: executor contract, registry and orchestration engine."""

from ai_dev_agent_core.base import MockRuntime
from ai_dev_agent_core.conversation import (
    ConversationStore,
    get_conversation_store,
    reset_conversation_store,
)
from ai_dev_agent_core.context import (
    DispatchForbiddenError,
    ExecutionContext,
    MAX_DISPATCH_HOPS,
    ORCHESTRATOR_AGENT,
    WORKER_AGENTS,
)
from ai_dev_agent_core.engine import OrchestrationEngine
from ai_dev_agent_core.executor import AgentExecutor, ExecutorFactory
from ai_dev_agent_core.intents import (
    ALL_INTENTS,
    INTENT_CHAT,
    INTENT_IMPLEMENT,
    INTENT_MONITOR,
    INTENT_NEEDS_INPUT,
    INTENT_PLAN,
    INTENT_RESEARCH,
    INTENT_TEST,
    NO_REPAIR_INTENTS,
    NO_WORKSPACE_INTENTS,
    classify_intent,
    is_plan_refinement,
)
from ai_dev_agent_core.mock_content import (
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
    # Phase 4.1: intent contract + conversation context.
    "ALL_INTENTS",
    "INTENT_CHAT",
    "INTENT_PLAN",
    "INTENT_RESEARCH",
    "INTENT_IMPLEMENT",
    "INTENT_TEST",
    "INTENT_MONITOR",
    "INTENT_NEEDS_INPUT",
    "NO_WORKSPACE_INTENTS",
    "NO_REPAIR_INTENTS",
    "is_plan_refinement",
    "ConversationStore",
    "get_conversation_store",
    "reset_conversation_store",
]