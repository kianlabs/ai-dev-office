"""MockAgentExecutor for QA - the Testing Agent.

Emits PASS/FAIL. Deterministic rule keeps the demo controllable:
the task fails its gate when its title or description mentions fail/error.
"""

from __future__ import annotations

import re
from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task
from ai_dev_tools import ToolChest, default_tools


class MockQAExecutor:
    agent_id = "qa"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id
        self.chest = ToolChest(default_tools())

    async def execute(self, task: Task, ctx: ExecutionContext) -> AsyncIterator[AgentEvent]:
        r = self.r
        text = f"{task.title} {task.description}".lower()
        should_fail = bool(re.search(r"\bfail\b|reach an error|inject err|force fail", text))

        yield await r.tick(r.waiting("Waiting for FORGE to hand off code"))
        yield await r.tick(r.working("Running test suite"))
        tests = await self.chest.call_tool("run_check", command="test")
        if tests.ok:
            yield await r.tick(r.say("npm test → 12 passed, 0 failed (3 suites)"))
        else:
            yield await r.tick(r.say("npm test → 1 suite failing (expected edge)"))

        yield await r.tick(r.working("Running typecheck"))
        tc = await self.chest.call_tool("run_check", command="typecheck")
        yield await r.tick(r.say("tsc --noEmit → 0 errors"))

        yield await r.tick(r.working("Running lint + regression diff"))
        await self.chest.call_tool("run_check", command="lint")
        yield await r.tick(r.say("next lint → clean · no new regressions on affected routes"))

        score = "FAIL" if should_fail else "PASS"
        if score == "PASS":
            yield await r.tick(r.qa_result("PASS", "QA gate: PASS — all checks green (test/type/lint)"))
            yield await r.tick(r.idle("Idle"))
        else:
            yield await r.tick(r.qa_result("FAIL", "QA gate: FAIL — edge-case regression detected"))
            yield await r.tick(r.idle("Idle"))