"""MockAgentExecutor for ATLAS - the orchestrator / Engineering Manager.

Phase 4.1: ATLAS is now conversational. Every task is classified into the
intent contract (CHAT/PLAN/RESEARCH/IMPLEMENT/TEST/MONITOR/NEEDS_INPUT) and
routed accordingly:

* CHAT / NEEDS_INPUT → ATLAS answers directly. No tools, no specialists, no
  workspace, no repair loop.
* PLAN → ATLAS builds/updates a structured plan artifact and stores it as the
  session's active plan. No coding, no FORGE, no QA.
* RESEARCH/TEST/MONITOR/IMPLEMENT → the specialist roster selected by the
  role-aware planner, streamed through ATLAS as before.

The final RESULT event decides DONE vs FAILED and carries the structured
ATLAS response ({intent, message, plan, needs_input}).
"""

from __future__ import annotations

from typing import AsyncIterator

from ai_dev_agent_core import (
    ExecutionContext,
    MockRuntime,
    classify_intent,
    get_conversation_store,
    is_plan_refinement,
    repo_name_for,
    INTENT_CHAT,
    INTENT_IMPLEMENT,
    INTENT_NEEDS_INPUT,
    INTENT_PLAN,
    NO_REPAIR_INTENTS,
)
from ai_dev_agent_atlas.planner import build_role_aware_plan
from ai_dev_agent_atlas.planning import (
    apply_plan_update,
    build_plan_artifact,
    chat_reply,
    needs_input_reply,
    render_plan_brief,
)
from ai_dev_shared import AgentEvent, Subtask, Task, TaskStatus
from ai_dev_shared.constants import EventKind
from ai_dev_tools import ToolChest, default_tools


def _atlas_response(
    intent: str,
    message: str,
    plan: dict | None = None,
    needs_input: bool | None = None,
) -> dict:
    return {
        "intent": intent,
        "message": message,
        "plan": plan,
        "needs_input": needs_input,
    }


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
        yield await r.tick(r.working("Reading the request", task_status=TaskStatus.PLANNING))

        store = get_conversation_store()
        session_id = task.session_id
        active_plan = store.get_active_plan(session_id)

        # Re-classify with conversation awareness: the engine classified
        # without knowing whether this session has an active plan, so a
        # refinement like "pakai PostgreSQL aja" arrives as NEEDS_INPUT and
        # becomes PLAN here (both are no-workspace intents).
        intent = classify_intent(task, has_active_plan=active_plan is not None)
        if intent != ctx.shared.get("intent"):
            ctx.shared["intent"] = intent
        # The complete user content; the title is only a display summary.
        user_text = (task.description or "").strip() or task.title

        # ── Conversational intents: ATLAS answers directly ────────────────
        if intent == INTENT_CHAT:
            reply = chat_reply(user_text)
            yield await r.tick(r.say(reply))
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.DONE,
                    reply,
                    meta={"atlas_response": _atlas_response(INTENT_CHAT, reply)},
                )
            )
            return

        if intent == INTENT_NEEDS_INPUT:
            reply = needs_input_reply(user_text)
            yield await r.tick(r.say(reply))
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.DONE,
                    reply,
                    meta={
                        "atlas_response": _atlas_response(
                            INTENT_NEEDS_INPUT, reply, needs_input=True
                        )
                    },
                )
            )
            return

        if intent == INTENT_PLAN:
            if active_plan and is_plan_refinement(user_text):
                plan = apply_plan_update(active_plan, user_text)
                store.set_active_plan(session_id, plan)
                message = f"Plan diperbarui: {plan.get('goal', '')}".strip()
            else:
                plan = build_plan_artifact(task)
                store.set_active_plan(session_id, plan)
                message = f"Plan dibuat: {plan.get('goal', '')}".strip()

            yield await r.tick(r.say(message))
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.DONE,
                    message,
                    meta={
                        "atlas_response": _atlas_response(
                            INTENT_PLAN, message, plan=plan
                        )
                    },
                )
            )
            return

        # ── Specialist intents ────────────────────────────────────────────
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
                f"Role-aware plan selected: {', '.join(agent.upper() for agent in plan.agents) if plan.agents else 'ATLAS only'}",
                meta={"plan": ctx.shared["atlas_plan"]},
            )
        )

        yield await r.tick(
            r.emit_subtasks(
                subtasks,
                f"Created {len(subtasks)} subtasks for {len(plan.agents)} agents",
            )
        )

        # ── PLAN → IMPLEMENT handoff (conversation continuation) ──────────
        # FORGE only receives a bounded brief derived from the active plan —
        # never the raw conversation transcript.
        if intent == INTENT_IMPLEMENT and active_plan is not None:
            ctx.shared["active_plan_brief"] = render_plan_brief(active_plan)
            yield await r.tick(
                r.say(
                    "Active plan from this conversation attached as the "
                    "implementation brief"
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
        forge_failed = False
        forge_attempted = False

        max_repair_attempts = 2
        repair_attempts = 0

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

                if (
                    agent_id == "forge"
                    and ev.kind == EventKind.RESULT
                    and ev.task_status == TaskStatus.FAILED
                ):
                    forge_failed = True

                yield await r.tick(ev)

            if agent_id == "forge":
                # FORGE genuinely made an implementation attempt — the only
                # state in which a repair loop is ever allowed.
                forge_attempted = True

            if forge_failed:
                break

            if agent_id == "scout":
                research = ctx.shared.get("research")
                if research:
                    yield await r.tick(
                        r.say(
                            "SCOUT research accepted into shared task context",
                            meta={"research": research},
                        )
                    )

        # ── Repair loop guard (Phase 4.1) ─────────────────────────────────
        # Repair FORGE only when the intent is IMPLEMENT *and* FORGE actually
        # attempted the implementation. CHAT/PLAN/NEEDS_INPUT never enter the
        # repair loop, even with an empty workspace.
        repair_allowed = (
            intent not in NO_REPAIR_INTENTS
            and intent == INTENT_IMPLEMENT
            and forge_attempted
            and "qa" in plan.agents
        )

        while (
            repair_allowed
            and qa_score == "FAIL"
            and not forge_failed
            and repair_attempts < max_repair_attempts
        ):
            repair_attempts += 1

            qa_report = ctx.shared.get("qa_report") or {
                "score": "FAIL",
                "failed_checks": [],
                "details": [],
            }

            repair_state = {
                "attempt": repair_attempts,
                "max_attempts": max_repair_attempts,
                "qa_report": qa_report,
            }

            ctx.shared["repair"] = repair_state

            yield await r.tick(
                r.working(
                    f"Preparing repair attempt "
                    f"{repair_attempts}/{max_repair_attempts}",
                    task_status=TaskStatus.RUNNING,
                )
            )

            yield await r.tick(
                r.say(
                    "QA failure routed back to FORGE by ATLAS",
                    meta={"repair": repair_state},
                )
            )

            forge_failed = False

            async for ev in ctx.dispatch_stream("forge"):
                if (
                    ev.kind == EventKind.RESULT
                    and ev.task_status == TaskStatus.FAILED
                ):
                    forge_failed = True

                yield await r.tick(ev)

            if forge_failed:
                break

            qa_score = None

            async for ev in ctx.dispatch_stream("qa"):
                if ev.kind == EventKind.QA_RESULT:
                    qa_score = ev.score

                yield await r.tick(ev)

            if qa_score == "PASS":
                ctx.shared["repair"]["resolved"] = True
                break

        if forge_failed:
            message = f"Implementasi gagal saat FORGE: {task.title}"
            yield await r.tick(
                r.working(
                    "Reviewing failed FORGE execution",
                    task_status=TaskStatus.REVIEW,
                )
            )
            yield await r.tick(
                r.review("FORGE execution failed.")
            )
            yield await r.tick(r.idle("Idle"))
            yield await r.tick(
                r.result(
                    TaskStatus.FAILED,
                    message,
                    meta={
                        "error": "FORGE execution failed",
                        "repair_attempts": repair_attempts,
                        "atlas_response": _atlas_response(
                            intent, message
                        ),
                    },
                )
            )
            return

        if qa_score == "FAIL":
            message = f"Implementasi selesai tetapi QA gagal: {task.title}"
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
                    message,
                    meta={
                        "error": "QA gate failed",
                        "atlas_response": _atlas_response(intent, message),
                    },
                )
            )
            return

        if health_status == "UNHEALTHY":
            message = f"Verifikasi kesehatan runtime gagal: {task.title}"
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
                    message,
                    meta={
                        "error": "PULSE health check failed",
                        "atlas_response": _atlas_response(intent, message),
                    },
                )
            )
            return

        yield await r.tick(
            r.working(
                "Reviewing specialist results",
                task_status=TaskStatus.REVIEW,
            )
        )

        # ── Workspace diff/review metadata (Phase 3.5b) ──────────────────
        # Compute real change summary from the isolated workspace so ATLAS
        # can report what actually changed vs the source project.
        ws_result_dict: dict = {}
        ws_meta = ctx.shared.get("workspace_meta")
        if ws_meta is not None:
            try:
                from ai_dev_shared.workspace import compute_workspace_result
                ws_result = compute_workspace_result(ws_meta)
                ws_result_dict = ws_result.to_dict()
                ctx.shared["workspace_result"] = ws_result
            except Exception:
                pass  # Non-fatal: diff metadata is best-effort

        yield await r.tick(
            r.review(
                "Selected specialist workflow completed successfully."
            )
        )
        yield await r.tick(r.idle("Idle"))

        message = f"Completed: {task.title}"
        yield await r.tick(
            r.result(
                TaskStatus.DONE,
                message,
                meta={
                    "agents": list(plan.agents),
                    "qa": qa_score,
                    "health": health_status,
                    "repair_attempts": repair_attempts,
                    "workspace_result": ws_result_dict,
                    "atlas_response": _atlas_response(intent, message),
                },
            )
        )
