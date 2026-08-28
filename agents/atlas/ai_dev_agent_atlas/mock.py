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


def build_plan(task: Task, intent: str) -> list[Subtask]:
    """Build the controlled Phase 3C.1 implementation pipeline."""

    labels = {
        "auth": "Implement authentication requirements",
        "deploy": "Implement deployment requirements",
        "bug": "Implement minimal regression fix",
        "feature": "Implement requested feature",
    }

    return [
        Subtask(
            title="Research implementation constraints and recommended approach",
            agent_id="scout",
        ),
        Subtask(title=labels[intent], agent_id="forge"),
        Subtask(
            title="Verify implementation and run deterministic QA gate",
            agent_id="qa",
        ),
    ]


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

        # SCOUT performs read-only research first and stores its structured
        # brief in the shared per-task execution context.
        async for ev in ctx.dispatch_stream("scout"):
            yield await r.tick(ev)

        research = ctx.shared.get("research")
        if research:
            yield await r.tick(
                r.say(
                    "SCOUT research accepted and attached to FORGE context",
                    meta={"research": research},
                )
            )

        # Dispatch to FORGE. Its child context receives the same shared state.
        async for ev in ctx.dispatch_stream("forge"):
            yield await r.tick(ev)

        # Dispatch to QA via registry using its child context.
        qa_score: str | None = None
        async for ev in ctx.dispatch_stream("qa"):
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

        yield await r.tick(
            r.working(
                "Reviewing FORGE implementation and QA result",
                task_status=TaskStatus.REVIEW,
            )
        )
        yield await r.tick(
            r.review("FORGE implementation complete · QA gate passed")
        )
        yield await r.tick(
            r.review("Final sign-off: implementation accepted.")
        )
        yield await r.tick(r.idle("Idle"))
        yield await r.tick(r.result(TaskStatus.DONE, f"Completed: {task.title}"))