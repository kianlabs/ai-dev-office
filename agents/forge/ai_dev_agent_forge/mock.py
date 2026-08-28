"""MockAgentExecutor for FORGE - the Coding Agent."""

from __future__ import annotations

from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext, MockRuntime, classify_intent
from ai_dev_shared import AgentEvent, Task
from ai_dev_tools import ToolChest, default_tools

_TARGETS = {
    "auth": "lib/auth.ts",
    "deploy": "vercel.json",
    "bug": "lib/queryCache.ts",
    "feature": "app/dashboard/page.tsx",
}


class MockForgeExecutor:
    agent_id = "forge"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id
        self.chest = ToolChest(default_tools())

    async def execute(self, task: Task, ctx: ExecutionContext) -> AsyncIterator[AgentEvent]:
        r = self.r
        target = _TARGETS.get(classify_intent(task), "lib/feature.ts")

        yield await r.tick(r.working("Restoring workspace context"))
        yield await r.tick(r.say("Branch: feat/ado-task — based on main"))
        yield await r.tick(r.say("Install deps → npm install --frozen-lockfile (cached)"))

        res = await self.chest.call_tool("write_code", file=target, change="wire provider + type-safe helpers")
        if res.ok:
            yield await r.tick(r.say(f"Editing {target}"))
            yield await r.tick(r.say("Updated 3 modules · touched route group + config"))

        yield await r.tick(r.working("Compiling changes"))
        check = await self.chest.call_tool("run_check", command="build")
        if check.ok:
            yield await r.tick(r.say("npm run build → ✓ compiled (0 errors)"))
        else:
            yield await r.tick(r.say("npm run build → warnings only (production-safe)"))

        yield await r.tick(r.say("Diff summary: +312 −18 across 5 files"))
        yield await r.tick(r.idle("Idle"))