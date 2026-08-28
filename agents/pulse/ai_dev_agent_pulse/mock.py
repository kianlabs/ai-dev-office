"""MockAgentExecutor for PULSE - the Monitoring Agent."""

from __future__ import annotations

from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task
from ai_dev_tools import ToolChest, default_tools


class MockPulseExecutor:
    agent_id = "pulse"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id
        self.chest = ToolChest(default_tools())

    async def execute(self, task: Task, ctx: ExecutionContext) -> AsyncIterator[AgentEvent]:
        r = self.r

        yield await r.tick(r.working("Watching build pipeline"))
        poll = await self.chest.call_tool("poll_deployment", target="preview")
        if poll.ok:
            yield await r.tick(r.say("Deploy status: Ready · preview URL live"))
        else:
            yield await r.tick(r.say("Deploy: Uploading → regenerating asset cache…"))

        yield await r.tick(r.working("Scanning runtime error logs"))
        yield await r.tick(r.say("Tail 100 lines · 0 unhandled exceptions · p50 latency OK"))

        yield await r.tick(r.health("Health: BUILD GREEN · DEPLOY HEALTHY", meta={"build": "green", "deploy": "healthy"}))
        yield await r.tick(r.waiting("Holding watch window for ATLAS sign-off"))
        yield await r.tick(r.idle("Idle"))