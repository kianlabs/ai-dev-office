"""ai-dev-agent-atlas: ATLAS - Engineering Manager / orchestrator."""

from ai_dev_agent_atlas.mock import MockAtlasExecutor
from ai_dev_agent_atlas.planner import AtlasPlan, build_role_aware_plan
from ai_dev_agent_atlas.planning import (
    apply_plan_update,
    build_plan_artifact,
    chat_reply,
    needs_input_reply,
    render_plan_brief,
)

__all__ = [
    "AtlasPlan",
    "MockAtlasExecutor",
    "build_role_aware_plan",
    "build_plan_artifact",
    "apply_plan_update",
    "render_plan_brief",
    "chat_reply",
    "needs_input_reply",
]
