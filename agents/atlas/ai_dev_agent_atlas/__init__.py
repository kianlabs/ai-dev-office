"""ai-dev-agent-atlas: ATLAS - Engineering Manager / orchestrator."""

from ai_dev_agent_atlas.mock import MockAtlasExecutor
from ai_dev_agent_atlas.planner import AtlasPlan, build_role_aware_plan

__all__ = [
    "AtlasPlan",
    "MockAtlasExecutor",
    "build_role_aware_plan",
]
