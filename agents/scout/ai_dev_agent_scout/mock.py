"""MockAgentExecutor for SCOUT - the Research Agent."""

from __future__ import annotations

from typing import AsyncIterator

from ai_dev_agent_core import (
    ExecutionContext,
    MockRuntime,
    doc_subject_for,
    repo_name_for,
)
from ai_dev_shared import AgentEvent, Task
from ai_dev_tools import ToolChest, default_tools


class MockScoutExecutor:
    agent_id = "scout"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id
        self.chest = ToolChest(default_tools())

    async def execute(self, task: Task, ctx: ExecutionContext) -> AsyncIterator[AgentEvent]:
        r = self.r
        topic = doc_subject_for(task)

        yield await r.tick(r.working("Scanning repository structure"))
        res = await self.chest.call_tool("read_project_tree", repo=repo_name_for(task))
        if res.ok:
            yield await r.tick(r.say("Located app/, lib/, components/ — repo follows Next.js App Router"))
            yield await r.tick(r.say("Found auth config surface · 2 route groups affected"))

        yield await r.tick(r.working(f"Reading documentation: {topic}"))
        docs = await self.chest.call_tool("read_docs", topic=topic)
        if docs.ok:
            yield await r.tick(r.say(f"Docs digest :: {docs.output[:90]}…"))

        yield await r.tick(r.working("Evaluating solutions vs. stack constraints"))
        yield await r.tick(r.say("Option A: library-native · Option B: minimal custom layer"))
        yield await r.tick(r.say("Recommendation: Option A — lower maintenance surface"))

        yield await r.tick(
            r.waiting("Preparing structured research brief for ATLAS")
        )

        research = {
            "summary": (
                docs.output
                if docs.ok
                else f"Research completed for topic: {topic}"
            ),
            "recommendations": [
                "Prefer the library-native implementation path",
                "Keep the implementation minimal and maintainable",
            ],
            "constraints": [
                "Preserve the existing project structure",
                "Avoid unnecessary dependencies",
                "Keep changes scoped to the requested task",
            ],
            "references": [
                f"mock-docs:{topic}",
                f"project:{repo_name_for(task)}",
            ],
        }

        # Structured SCOUT -> ATLAS/FORGE communication channel.
        ctx.shared["research"] = research

        yield await r.tick(
            r.say(
                "Research brief delivered to ATLAS",
                meta={
                    "research": research,
                    "structured": True,
                },
            )
        )

        yield await r.tick(r.idle("Idle"))
