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
from ai_dev_agent_atlas.planner import build_role_aware_plan
from ai_dev_shared import AgentEvent, Subtask, Task, TaskStatus
from ai_dev_shared.constants import EventKind
from ai_dev_tools import ToolChest, default_tools


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

        plan = build_role_aware_plan(task, intent)
        subtasks = list(plan.subtasks)

        ctx.shared["atlas_plan"] = {
            "intent": plan.intent,
            "agents": list(plan.agents),
            "reasons": plan.reasons,
        }

        yield await r.tick(
            r.say(
                f"Role-aware plan selected: {', '.join(agent.upper() for agent in plan.agents)}",
                meta={"plan": ctx.shared["atlas_plan"]},
            )
        )

        yield await r.tick(
            r.emit_subtasks(
                subtasks,
                f"Created {len(subtasks)} subtasks for {len(plan.agents)} agents",
            )
        )

        yield await r.tick(
            r.working(
                "Dispatching selected specialists",
                task_status=TaskStatus.RUNNING,
            )
        )

        qa_score: str | None = None
        health_status: str | None = None

        for agent_id in plan.agents:
            reason = plan.reasons.get(agent_id, "selected by ATLAS")

            yield await r.tick(
                r.waiting(
                    f"Dispatching {agent_id.upper()} — {reason}"
                )
            )

            async for ev in ctx.dispatch_stream(agent_id):
                if ev.kind == EventKind.QA_RESULT:
                    qa_score = ev.score

                if ev.kind == EventKind.HEALTH:
                    health = ev.meta.get("health") or {}
                    health_status = health.get("status")

                yield await r.tick(ev)

            if agent_id == "scout":
                research = ctx.shared.get("research")
                if research:
                    yield await r.tick(
                        r.say(
                            "SCOUT research accepted into shared task context",
                            meta={"research": research},
                        )
                    )

        if qa_score == "FAIL":
            yield await r.tick(
                r.working(
                    "Reviewing failed QA gate",
                    task_status=TaskStatus.REVIEW,
                )
            )
            yield await r.tick(r.review("QA gate failed."))
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.FAILED,
                    "Task failed at QA gate — see QA report for details.",
                    meta={"error": "QA gate failed"},
                )
            )
            return

        if health_status == "UNHEALTHY":
            yield await r.tick(
                r.working(
                    "Reviewing unhealthy runtime/workspace state",
                    task_status=TaskStatus.REVIEW,
                )
            )
            yield await r.tick(
                r.review("PULSE reported an unhealthy state.")
            )
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.FAILED,
                    "Task failed health verification.",
                    meta={"error": "PULSE health check failed"},
                )
            )
            return

        yield await r.tick(
            r.working(
                "Reviewing specialist results",
                task_status=TaskStatus.REVIEW,
            )
        )
        yield await r.tick(
            r.review(
                "Selected specialist workflow completed successfully."
            )
        )
        yield await r.tick(r.idle("Idle"))
        yield await r.tick(
            r.result(
                TaskStatus.DONE,
                f"Completed: {task.title}",
                meta={
                    "agents": list(plan.agents),
                    "qa": qa_score,
                    "health": health_status,
                },
            )
        )