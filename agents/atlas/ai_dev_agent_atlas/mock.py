"""MockAgentExecutor for ATLAS - the orchestrator / Engineering Manager.

ATLAS receives the raw user task, plans subtasks, dispatches them to the other
agents (forwarding their event streams unchanged) and performs the final
review. The final RESULT event decides DONE vs FAILED.
"""

from __future__ import annotations

from typing import AsyncIterator

from ai_dev_agent_core import (
    ExecutionContext,
    MockRuntime,
    classify_intent,
    repo_name_for,
)
from ai_dev_shared import AgentEvent, Subtask, Task, TaskStatus
from ai_dev_shared.constants import EventKind
from ai_dev_tools import ToolChest, default_tools
from ai_dev_agent_forge import MockForgeExecutor
from ai_dev_agent_pulse import MockPulseExecutor
from ai_dev_agent_qa import MockQAExecutor
from ai_dev_agent_scout import MockScoutExecutor


def build_plan(task: Task, intent: str) -> list[Subtask]:
    plans = {
        "auth": [
            ("Define auth flow & session strategy", "scout"),
            ("Implement credentials provider + route guard", "forge"),
            ("Add integration tests & monitor auth health", "qa"),
        ],
        "deploy": [
            ("Map CI/CD pipeline to target platform", "scout"),
            ("Configure deployment settings & secrets", "forge"),
            ("Verify deploy + monitor release health", "pulse"),
        ],
        "bug": [
            ("Reproduce & isolate regression source", "scout"),
            ("Implement fix with minimal diff", "forge"),
            ("Run regression suite + watch logs", "qa"),
        ],
        "feature": [
            ("Research API surface & data model", "scout"),
            ("Implement feature modules", "forge"),
            ("Test, typecheck & harden", "qa"),
        ],
    }
    return [Subtask(title=t, agent_id=a) for t, a in plans[intent]]


class MockAtlasExecutor:
    agent_id = "atlas"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id
        self.chest = ToolChest(default_tools())

    async def execute(self, task: Task, ctx: ExecutionContext) -> AsyncIterator[AgentEvent]:
        r = self.r
        yield await r.tick(r.working("Parsing task requirements", task_status=TaskStatus.PLANNING))
        yield await r.tick(r.say(f"Task accepted: \"{task.title}\""))

        intent = classify_intent(task)
        yield await r.tick(r.say(f"Requirement understood → objective type: {intent.upper()}"))

        res = await self.chest.call_tool("read_project_tree", repo=repo_name_for(task))
        if res.ok:
            yield await r.tick(r.say("Mapped repository structure :: 14 files · 3 entrypoints · 1 lockfile"))

        subtasks = build_plan(task, intent)
        yield await r.tick(
            r.emit_subtasks(subtasks, f"Created {len(subtasks)} subtasks for {len(subtasks)} agents")
        )
        yield await r.tick(r.working("Dispatching subtasks", task_status=TaskStatus.RUNNING))
        yield await r.tick(r.waiting("Agents executing subtasks"))

        scout = MockScoutExecutor(task, ctx)
        async for ev in scout.execute(task, ctx):
            yield await r.tick(ev)

        forge = MockForgeExecutor(task, ctx)
        async for ev in forge.execute(task, ctx):
            yield await r.tick(ev)

        qa = MockQAExecutor(task, ctx)
        qa_score: str | None = None
        async for ev in qa.execute(task, ctx):
            if ev.kind == EventKind.QA_RESULT:
                qa_score = ev.score
            yield await r.tick(ev)

        if qa_score == "FAIL":
            yield await r.tick(r.working("Reviewing failed gate", task_status=TaskStatus.REVIEW))
            yield await r.tick(r.review("QA gate failed: regression detected in edge cases."))
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.FAILED,
                    "Task failed at QA gate — see QA report for details.",
                    meta={"error": "QA gate failed"},
                )
            )
            return

        pulse = MockPulseExecutor(task, ctx)
        async for ev in pulse.execute(task, ctx):
            yield await r.tick(ev)

        yield await r.tick(r.working("Consolidating implementation report", task_status=TaskStatus.REVIEW))
        yield await r.tick(r.review("All subtasks complete · code compiles · tests green · deploy healthy"))
        yield await r.tick(r.review("Final sign-off: implementation meets acceptance criteria."))
        yield await r.tick(r.idle("Idle"))
        yield await r.tick(r.result(TaskStatus.DONE, f"Completed: {task.title}"))