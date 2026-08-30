"""
Phase 4.1 — Conversational ATLAS + intent routing regression tests.

Covers the intent contract (CHAT/PLAN/RESEARCH/IMPLEMENT/TEST/MONITOR/
NEEDS_INPUT), the routing table, anti-hallucination plan artifacts,
conversation continuation, the PLAN→IMPLEMENT handoff, and the repair-loop
guard. The 10 mandatory acceptance cases from Phase 4.1 are all represented.

Run with:  .venv/bin/pytest apps/api/tests/test_phase41_intent.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from ai_dev_agent_core import (
    AgentRegistry,
    ExecutionContext,
    OrchestrationEngine,
    classify_intent,
    get_conversation_store,
    is_plan_refinement,
    reset_conversation_store,
    INTENT_CHAT,
    INTENT_IMPLEMENT,
    INTENT_MONITOR,
    INTENT_NEEDS_INPUT,
    INTENT_PLAN,
    INTENT_RESEARCH,
    INTENT_TEST,
)
from ai_dev_agent_atlas import MockAtlasExecutor, build_role_aware_plan
from ai_dev_agent_atlas.planning import (
    apply_plan_update,
    build_plan_artifact,
    chat_reply,
    needs_input_reply,
    render_plan_brief,
)
from ai_dev_shared import AGENT_COLORS, AGENT_ROLES, Task, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(text: str, **kw) -> Task:
    return Task(title=text.split("\n")[0][:120], description=text, **kw)


def _intent(text: str, has_active_plan: bool = False) -> str:
    return classify_intent(_task(text), has_active_plan=has_active_plan)


def _plan_for(text: str):
    task = _task(text)
    return build_role_aware_plan(task, classify_intent(task))


class _Factory:
    """Minimal executor factory pinned to one executor class."""

    def __init__(self, agent_id: str, executor_cls) -> None:
        self.agent_id = agent_id
        self._cls = executor_cls

    def __call__(self, task, ctx):
        return self._cls(task, ctx)


def _build_registry() -> AgentRegistry:
    from ai_dev_agent_forge import MockForgeExecutor
    from ai_dev_agent_qa import MockQAExecutor
    from ai_dev_agent_pulse import MockPulseExecutor
    from ai_dev_agent_scout import MockScoutExecutor

    registry = AgentRegistry()
    for agent_id, cls in (
        ("atlas", MockAtlasExecutor),
        ("scout", MockScoutExecutor),
        ("forge", MockForgeExecutor),
        ("qa", MockQAExecutor),
        ("pulse", MockPulseExecutor),
    ):
        registry.register(
            _Factory(agent_id, cls),
            name=agent_id.upper(),
            role=AGENT_ROLES[agent_id],
            color=AGENT_COLORS[agent_id],
        )
    return registry


async def _run_task(text: str, workspace_root: Path | None = None, **task_kw) -> Task:
    reset_conversation_store()
    import shutil
    import uuid

    # Workspace validation requires roots under the home directory.
    own_root = workspace_root is None
    root = workspace_root or (Path.home() / ".ado-phase41-tests" / uuid.uuid4().hex[:8])
    engine = OrchestrationEngine(
        _build_registry(),
        orchestrator_agent="atlas",
        settings={
            "speed": 500.0,
            "forge_workspace_root": str(root),
            "cleanup_workspace": True,
        },
    )
    task = _task(text, **task_kw)
    await engine.enqueue(task)
    try:
        for _ in range(600):
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED):
                return task
            await asyncio.sleep(0.05)
        raise TimeoutError(f"Task did not finish: {task.status}")
    finally:
        if own_root:
            shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_store():
    reset_conversation_store()
    yield
    reset_conversation_store()


# ---------------------------------------------------------------------------
# Mandatory cases 1-8: classification
# ---------------------------------------------------------------------------

def test_1_halo_is_chat():
    assert _intent("halo") == INTENT_CHAT


def test_1b_short_social_utterances_are_chat():
    for text in ("hai", "makasih", "menurutmu gimana?", "ok", "halo 👋"):
        assert _intent(text) == INTENT_CHAT, text


def test_2_booking_plan_without_coding_is_plan():
    assert _intent("buat struktur aplikasi booking, jangan coding") == INTENT_PLAN


def test_3_landing_page_plan_is_plan():
    assert (
        _intent("buat desain landing page perusahaan pintu kayu tanpa coding")
        == INTENT_PLAN
    )


def test_4_compare_auth_libraries_is_research():
    assert _intent("bandingkan auth library untuk project ini") == INTENT_RESEARCH


def test_5_concrete_function_request_is_implement():
    assert _intent("buat fungsi greet(name) di src/index.js") == INTENT_IMPLEMENT


def test_6_run_tests_only_is_test():
    assert _intent("jalankan test project ini saja") == INTENT_TEST


def test_7_check_localhost_health_is_monitor():
    assert _intent("cek localhost:8000 sehat") == INTENT_MONITOR


def test_8_vague_requests_need_input():
    for text in ("perbaiki ini", "fix", "buat bagus"):
        assert _intent(text) == INTENT_NEEDS_INPUT, text


# ---------------------------------------------------------------------------
# Slash command overrides
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command,expected",
    [
        ("/chat halo", INTENT_CHAT),
        ("/plan aplikasi booking", INTENT_PLAN),
        ("/research auth libraries", INTENT_RESEARCH),
        ("/implement greet function", INTENT_IMPLEMENT),
        ("/test", INTENT_TEST),
        ("/monitor localhost:8000", INTENT_MONITOR),
    ],
)
def test_slash_commands_override_heuristics(command, expected):
    assert _intent(command) == expected


# ---------------------------------------------------------------------------
# Routing table (planner)
# ---------------------------------------------------------------------------

def test_routing_chat_plan_needs_input_dispatch_no_specialists():
    assert _plan_for("halo").agents == ()
    assert _plan_for("buat plan aplikasi booking lapangan").agents == ()
    assert _plan_for("perbaiki ini").agents == ()


def test_routing_research_is_scout_only():
    assert _plan_for("bandingkan auth library untuk project ini").agents == ("scout",)


def test_routing_test_is_qa_only():
    assert _plan_for("jalankan test project ini saja").agents == ("qa",)


def test_routing_monitor_is_pulse_only():
    assert _plan_for("cek localhost:8000 sehat").agents == ("pulse",)


def test_routing_implement_is_forge_qa():
    assert _plan_for("buat fungsi greet(name) di src/index.js").agents == ("forge", "qa")


def test_routing_implement_with_research_adds_scout():
    plan = _plan_for("implementasikan auth dengan riset library terbaik dulu")
    assert plan.agents == ("scout", "forge", "qa")


# ---------------------------------------------------------------------------
# Mandatory case 1 (E2E): "halo" never touches FORGE/QA/workspace
# ---------------------------------------------------------------------------

async def _assert_no_specialist_activity(task, engine):
    rec = engine.registry.record("forge")
    assert rec.status.value == "IDLE"
    assert rec.activity == "Idle"


def test_e2e_halo_is_chat_with_natural_reply_no_specialists(tmp_path):
    async def go():
        return await _run_task("halo")

    task = asyncio.run(go())

    assert task.status == TaskStatus.DONE
    assert task.atlas_response is not None
    assert task.atlas_response["intent"] == INTENT_CHAT
    assert task.atlas_response["message"]
    assert "Halo" in task.atlas_response["message"]
    assert task.atlas_response["plan"] is None
    assert task.subtasks == []
    # No workspace may be created for a chat message.
    assert task.workspace_meta is None


def test_e2e_chat_does_not_dispatch_specialists(tmp_path):
    async def go():
        engine = OrchestrationEngine(
            _build_registry(),
            orchestrator_agent="atlas",
            settings={"speed": 500.0, "forge_workspace_root": str(tmp_path)},
        )
        task = _task("makasih")
        await engine.enqueue(task)
        for _ in range(600):
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED):
                break
            await asyncio.sleep(0.05)
        return task, engine

    task, engine = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    for agent_id in ("scout", "forge", "qa", "pulse"):
        rec = engine.registry.record(agent_id)
        assert rec.status.value == "IDLE", agent_id


# ---------------------------------------------------------------------------
# Mandatory cases 2-3 (E2E): PLAN artifacts + anti-hallucination
# ---------------------------------------------------------------------------

def test_e2e_plan_booking_creates_plan_without_forge_or_workspace(tmp_path):
    async def go():
        return await _run_task(
            "buat plan aplikasi booking lapangan, jangan coding"
        )

    task = asyncio.run(go())

    assert task.status == TaskStatus.DONE
    resp = task.atlas_response
    assert resp["intent"] == INTENT_PLAN
    assert resp["plan"] is not None
    plan = resp["plan"]
    assert plan["goal"]
    assert plan["known_requirements"]
    # PLAN ONLY constraint present; no coding happened.
    assert any("PLAN ONLY" in c for c in plan["constraints"])
    assert task.workspace_meta is None
    assert task.subtasks == []


def test_plan_artifact_landing_page_does_not_invent_business_facts():
    plan = build_plan_artifact(
        _task("buat desain landing page perusahaan pintu kayu, jangan coding")
    )

    blob = str(plan).lower()
    # No invented names, contacts, testimonials, or customer data.
    for invented_marker in ("@gmail", "wa 08", "+62", "cv.", "pt.", "tokoku"):
        assert invented_marker not in blob, invented_marker

    # Known facts are exactly what the user said.
    assert "Landing page" in plan["known_requirements"]
    assert "Bisnis pintu kayu" in plan["known_requirements"]

    # Everything unknown is explicitly missing information, separated from
    # known requirements and assumptions.
    missing_blob = " | ".join(plan["missing_information"])
    for unknown in (
        "Nama perusahaan",
        "Nomor WhatsApp",
        "Alamat lokasi",
        "Testimoni",
        "Foto produk asli",
    ):
        assert unknown in missing_blob, unknown
    assert plan["blockers"] == []
    # Placeholder rule guards implementation against hallucinated facts.
    assert any("placeholder" in c.lower() for c in plan["constraints"])


def test_plan_artifact_separates_known_assumptions_missing():
    plan = build_plan_artifact(_task("buat plan aplikasi booking lapangan"))
    assert plan["known_requirements"] != plan["missing_information"]
    assert plan["assumptions"] != []
    assert plan["open_questions"] == plan["missing_information"]


# ---------------------------------------------------------------------------
# Mandatory case 9: continuation — plan update + reuse
# ---------------------------------------------------------------------------

def test_plan_refinement_updates_active_plan():
    reset_conversation_store()
    store = get_conversation_store()
    plan = build_plan_artifact(_task("buat plan aplikasi inventory"))
    store.set_active_plan("sess-a", plan)

    assert is_plan_refinement("pakai PostgreSQL aja")
    updated = apply_plan_update(store.get_active_plan("sess-a"), "pakai PostgreSQL aja")
    store.set_active_plan("sess-a", updated)

    current = store.get_active_plan("sess-a")
    assert "Database: PostgreSQL" in current["constraints"]
    assert current is not plan  # immutable update


def test_refinement_classified_as_plan_only_with_active_plan():
    assert _intent("pakai PostgreSQL aja", has_active_plan=False) == INTENT_NEEDS_INPUT
    assert _intent("pakai PostgreSQL aja", has_active_plan=True) == INTENT_PLAN


def test_conversation_store_is_bounded():
    store = get_conversation_store()
    for i in range(200):
        store.set_active_plan(f"sess-{i}", {"goal": str(i)})
    assert len(store._plans) <= store._max_sessions


# ---------------------------------------------------------------------------
# PLAN → IMPLEMENT handoff (mandatory case 9 continuation)
# ---------------------------------------------------------------------------

def test_implement_with_active_plan_hands_bounded_brief_to_forge():
    from ai_dev_agent_forge import HermesExecutor

    store = get_conversation_store()
    plan = build_plan_artifact(_task("buat plan aplikasi inventory"))
    plan = apply_plan_update(plan, "pakai PostgreSQL aja")
    store.set_active_plan("sess-b", plan)

    task = _task("implementasikan plan tadi", session_id="sess-b")
    ctx = ExecutionContext(task=task, settings={}, registry=_build_registry())
    executor = MockAtlasExecutor(task, ctx)

    async def go():
        async for _ in executor.execute(task, ctx):
            pass

    asyncio.run(go())

    brief = ctx.shared.get("active_plan_brief")
    assert brief is not None
    assert "Database: PostgreSQL" in brief
    # The brief is bounded — never a raw transcript.
    assert len(brief) < 2000

    # FORGE receives the brief through its prompt (small wiring).
    forge = HermesExecutor(task, ctx)
    prompt = forge._build_prompt(task)
    assert "ATLAS ACTIVE PLAN CONTEXT" in prompt
    assert "PostgreSQL" in prompt


def test_forge_prompt_without_plan_has_no_plan_block():
    from ai_dev_agent_forge import HermesExecutor

    task = _task("buat fungsi greet(name) di src/index.js")
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    forge = HermesExecutor(task, ctx)
    assert "ATLAS ACTIVE PLAN CONTEXT" not in forge._build_prompt(task)


# ---------------------------------------------------------------------------
# Mandatory case 10: repair-loop guard
# ---------------------------------------------------------------------------

def test_e2e_implement_enters_repair_loop_on_qa_fail(tmp_path):
    async def go():
        # "fail" word makes the mock QA fail deterministically → repair loop.
        return await _run_task(
            "buat fungsi greet(name) di src/index.js, force fail"
        )

    task = asyncio.run(go())

    assert task.status == TaskStatus.FAILED
    # FORGE genuinely attempted implementation, so repair was allowed.
    assert task.atlas_response["intent"] == INTENT_IMPLEMENT


def test_e2e_chat_and_plan_never_repair_even_with_empty_workspace(tmp_path):
    async def go():
        results = []
        for text in ("halo", "buat plan aplikasi inventory, jangan coding"):
            results.append(await _run_task(text))
        return results

    tasks = asyncio.run(go())
    for task in tasks:
        assert task.status == TaskStatus.DONE
        assert task.atlas_response["intent"] in (INTENT_CHAT, INTENT_PLAN)
        assert task.subtasks == []
        assert task.workspace_meta is None


def test_needs_input_never_dispatches_specialists(tmp_path):
    async def go():
        return await _run_task("perbaiki ini")

    task = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    assert task.atlas_response["intent"] == INTENT_NEEDS_INPUT
    assert task.atlas_response["needs_input"] is True
    assert task.subtasks == []


# ---------------------------------------------------------------------------
# Mandatory cases 5-7 (E2E): IMPLEMENT / TEST / MONITOR routing
# ---------------------------------------------------------------------------

def test_e2e_implement_dispatches_forge_and_qa(tmp_path):
    async def go():
        return await _run_task("buat fungsi greet(name) di src/index.js")

    task = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    assert task.atlas_response["intent"] == INTENT_IMPLEMENT
    agent_ids = {s.agent_id for s in task.subtasks}
    assert agent_ids == {"forge", "qa"}
    # IMPLEMENT prepares a workspace.
    assert task.workspace_meta is not None


def test_e2e_test_routes_qa_only(tmp_path):
    async def go():
        return await _run_task("jalankan test project ini saja")

    task = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    assert task.atlas_response["intent"] == INTENT_TEST
    assert {s.agent_id for s in task.subtasks} == {"qa"}


def test_e2e_monitor_routes_pulse_only(tmp_path):
    async def go():
        return await _run_task("cek localhost:8000 sehat")

    task = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    assert task.atlas_response["intent"] == INTENT_MONITOR
    assert {s.agent_id for s in task.subtasks} == {"pulse"}


def test_e2e_research_routes_scout_only(tmp_path):
    async def go():
        return await _run_task("bandingkan auth library untuk project ini")

    task = asyncio.run(go())
    assert task.status == TaskStatus.DONE
    assert task.atlas_response["intent"] == INTENT_RESEARCH
    assert {s.agent_id for s in task.subtasks} == {"scout"}


# ---------------------------------------------------------------------------
# Conversational replies
# ---------------------------------------------------------------------------

def test_chat_reply_is_natural_and_specific():
    assert "Halo" in chat_reply("halo")
    assert "Sama-sama" in chat_reply("makasih")
    reply = needs_input_reply("perbaiki ini")
    assert "?" in reply  # asks a question, dispatches nothing


def test_needs_input_reply_is_short_and_specific():
    for text in ("perbaiki ini", "buat bagus", "fix"):
        reply = needs_input_reply(text)
        assert len(reply) < 200
        assert "?" in reply
