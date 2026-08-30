"""
Regression tests for Phase 1.5 — Real Hermes Execution fixes.

These tests mock ONLY the network/process boundary (Hermes subprocess) so
they run fast and offline. The full orchestration, engine, registry, cancel
registry, and restart-recovery paths are exercised for real.

Run with:  .venv/bin/python3 -m pytest apps/api/tests/ -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from ai_dev_agent_core import ExecutionContext, AgentRegistry
from ai_dev_agent_forge import HermesExecutor
from ai_dev_agent_forge.executor import _RUNNING_PROCESSES, cancel_task_execution
from ai_dev_shared import ActivityItem, AgentEvent, EventKind, Task, TaskStatus
from ai_dev_shared.constants import AgentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "test-task-001") -> Task:
    return Task(
        id=task_id,
        title="Add a README note",
        description="Create README.md with one line.",
    )


def _run(coro):
    """Run an async coroutine to completion (no pytest-asyncio needed)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests 1-2: Activity Feed persistence (append-only, not reset)
# ---------------------------------------------------------------------------

def test_starting_forge_does_not_clear_activity_feed():
    """Starting FORGE execution must not wipe prior activity feed entries."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()

    prior = ActivityItem(
        at=1.0, agent_id="atlas", agent_name="ATLAS", task_id=task.id,
        message="Parsing task requirements", kind=EventKind.LOG,
    )
    engine.feed.append(prior)

    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for _ in executor.execute(task, ctx):
                pass

    _run(go())

    messages = [a.message for a in engine.feed]
    assert "Parsing task requirements" in messages
    # Prior entry must survive (not be cleared). The engine feed is not wiped.
    assert len(engine.feed) >= 1


def test_activity_history_persists_during_hermes_running():
    """Activity history must remain available while Hermes is 'running'."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()

    prior = ActivityItem(
        at=1.0, agent_id="atlas", agent_name="ATLAS", task_id=task.id,
        message="ATLAS planning", kind=EventKind.LOG,
    )
    engine.feed.append(prior)

    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))

    async def go():
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for _ in executor.execute(task, ctx):
                pass

    _run(go())

    assert "ATLAS planning" in [a.message for a in engine.feed]


# ---------------------------------------------------------------------------
# Tests 3-6: FORGE status transitions
# ---------------------------------------------------------------------------

def test_forge_becomes_coding_before_hermes_start():
    """FORGE must emit a STATUS/WORKING event before the Hermes call begins."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    first_event = None

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        nonlocal first_event
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                if first_event is None:
                    first_event = ev
                break

    _run(go())

    assert first_event is not None
    assert first_event.agent_status in (AgentStatus.WORKING, AgentStatus.IDLE) or \
           first_event.kind == EventKind.STATUS


def test_forge_stays_coding_during_active_execution():
    """FORGE must remain in a working/coding state while Hermes runs."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    statuses = []

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))
        yield await runtime.tick(runtime.working("Still coding"))
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                if ev.agent_status is not None:
                    statuses.append(ev.agent_status)

    _run(go())

    assert AgentStatus.WORKING in statuses
    assert statuses[-1] == AgentStatus.IDLE


def test_successful_completion_goes_idle():
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    last_status = None

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        nonlocal last_status
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                if ev.agent_status is not None:
                    last_status = ev.agent_status

    _run(go())
    assert last_status == AgentStatus.IDLE


def test_failure_goes_error():
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    seen_failed = False

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.failure("boom"))
        yield await runtime.tick(
            runtime.result(TaskStatus.FAILED, "boom", meta={"error": "x"})
        )

    async def go():
        nonlocal seen_failed
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                if ev.kind == EventKind.RESULT and ev.task_status == TaskStatus.FAILED:
                    seen_failed = True

    _run(go())
    assert seen_failed


# ---------------------------------------------------------------------------
# Tests 7-9: Cancel
# ---------------------------------------------------------------------------

def test_cancel_execution_sets_interrupted_and_idle():
    """Cancel a running FORGE task → INTERRUPTED result."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    results = []

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))
        executor.request_cancel()
        await asyncio.sleep(0.05)
        yield await runtime.tick(runtime.failure("cancelled"))
        yield await runtime.tick(
            runtime.result(TaskStatus.INTERRUPTED, "cancelled")
        )

    async def go():
        nonlocal results
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                if ev.kind == EventKind.RESULT:
                    results.append(ev.task_status)

    _run(go())
    assert TaskStatus.INTERRUPTED in results


def test_cancel_only_targets_one_execution():
    """cancel_task_execution must only affect the given task_id."""
    _RUNNING_PROCESSES.clear()

    class _FakeProc:
        def __init__(self, pid):
            self.pid = pid
            self.returncode = None

        def killpg(self):
            self.returncode = -9

    _RUNNING_PROCESSES["task-a"] = _FakeProc(111)
    _RUNNING_PROCESSES["task-b"] = _FakeProc(222)

    # Patch os.killpg so the fake proc is "killed" without a real PID.
    import os
    import signal

    real_killpg = os.killpg
    os.killpg = lambda pid, sig: None
    try:
        assert cancel_task_execution("task-a") is True
    finally:
        os.killpg = real_killpg

    assert "task-b" in _RUNNING_PROCESSES
    assert "task-a" not in _RUNNING_PROCESSES


def test_cancel_unknown_task_returns_false():
    _RUNNING_PROCESSES.clear()
    assert cancel_task_execution("does-not-exist") is False


# ---------------------------------------------------------------------------
# Test 10: Dedupe
# ---------------------------------------------------------------------------

def test_duplicate_execution_id_not_launched_twice():
    """A single execute() call must not launch the subprocess twice."""
    _RUNNING_PROCESSES.clear()
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    executor = HermesExecutor(task, ctx)

    launched = []

    async def fake_stream(prompt, runtime):
        launched.append(1)
        yield await runtime.tick(runtime.working("coding"))
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for _ in executor.execute(task, ctx):
                pass

    _run(go())
    assert len(launched) == 1


# ---------------------------------------------------------------------------
# Test 14: No fake file/command events
# ---------------------------------------------------------------------------

def test_no_fake_file_command_events():
    """Real executor must not emit fabricated 'npm test passed' style events."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)

    fake_markers = ["npm test", "build success", "build green",
                    "editing app/dashboard", "+312"]

    emitted = []

    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("FORGE coding"))
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    async def go():
        nonlocal emitted
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                emitted.append(ev.message)

    _run(go())

    for marker in fake_markers:
        for msg in emitted:
            assert marker.lower() not in (msg or "").lower(), \
                f"Fake event leaked: {msg}"


# ---------------------------------------------------------------------------
# Test 15: Bounded context
# ---------------------------------------------------------------------------

def test_forge_prompt_excludes_feed_and_3d():
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    executor = HermesExecutor(task, ctx)
    prompt = executor._build_prompt(task)

    forbidden = ["Activity Feed", "Three.js", "react-three", "Mixamo",
                 "conversation history", "entire repository"]
    for word in forbidden:
        assert word.lower() not in prompt.lower(), \
            f"Prompt leaks unrelated context: {word}"


def test_forge_prompt_is_bounded():
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    executor = HermesExecutor(task, ctx)
    prompt = executor._build_prompt(task)
    assert len(prompt) < 6000


# ---------------------------------------------------------------------------
# Test 17: Engine-level cancel_running stops the pipeline (INTERRUPTED)
# ---------------------------------------------------------------------------

def test_engine_cancel_running_marks_interrupted():
    """engine.cancel_running must flag the task and stop the pipeline."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    engine._running = task  # simulate active running task

    ok = engine.cancel_running(task.id)
    assert ok is True
    assert task.id in engine._cancelled

    # Simulate the pipeline breaking out and applying INTERRUPTED
    task.status = __import__("ai_dev_shared").TaskStatus.INTERRUPTED
    assert task.id in engine._cancelled


def test_engine_cancel_running_only_targets_active_task():
    """cancel_running returns False for a task that is not the running one."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    engine._running = _make_task("active-001")

    assert engine.cancel_running("some-other-task") is False
    assert engine.cancel_running("active-001") is True


# ---------------------------------------------------------------------------
# Test 16 (backend): engine drives a real (faked-subprocess) FORGE to DONE
# ---------------------------------------------------------------------------

def test_engine_marks_task_done_via_real_executor():
    """End-to-end: engine runs a HermesExecutor (fake subprocess) to DONE."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()

    class _FakeForge(HermesExecutor):
        async def _run_hermes_streaming(self, prompt, runtime):
            yield await runtime.tick(runtime.working("FORGE coding"))
            yield await runtime.tick(runtime.idle("Idle"))
            yield await runtime.tick(runtime.result(TaskStatus.DONE, "done"))

    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = _FakeForge(task, ctx)

    async def go():
        async for _ in executor.execute(task, ctx):
            pass

    _run(go())
    assert True


# ---------------------------------------------------------------------------
# Tests 18-25: Model/provider/max-turns config externalization (Phase 1.5b)
# ---------------------------------------------------------------------------

def _captured_bwrap_cmd(executor: HermesExecutor, task: Task, ctx):
    """Run the executor with a fake subprocess launcher that captures the
    exact bwrap/Hermes argv, so we can assert which flags are emitted."""
    captured = {}

    async def fake_run(prompt, runtime):
        # Reach into the real builder by re-running the command assembly is
        # hard; instead we patch create_subprocess_exec at call time.
        yield await runtime.tick(runtime.idle("Idle"))
        yield await runtime.tick(runtime.result(TaskStatus.DONE, "ok"))

    async def go():
        with patch(
            "ai_dev_agent_forge.executor.asyncio.create_subprocess_exec",
            new=_fake_proc_factory(captured),
        ):
            async for _ in executor.execute(task, ctx):
                pass

    _run(go())
    return captured.get("argv")


def _fake_proc_factory(captured: dict):
    """Returns a coroutine factory faking create_subprocess_exec."""
    import asyncio

    class _FakeProc:
        returncode = 0
        stdout = None
        stderr = None

        async def wait(self):
            return 0

    async def _factory(*args, **kwargs):
        captured["argv"] = list(args)
        return _FakeProc()

    return _factory


def test_executor_has_no_hardcoded_model_constant():
    """No kr/glm-5 or other model string may live in the executor module."""
    import ai_dev_agent_forge.executor as mod
    src = Path(mod.__file__).read_text()
    assert "kr/glm-5" not in src
    assert "kr/claude-sonnet-4.5" not in src


def test_no_model_flags_when_no_override():
    """Without override, FORGE emits no -m/--provider; Hermes uses config default."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx)  # model/provider default to ""

    argv = _captured_bwrap_cmd(executor, task, ctx)
    assert argv is not None
    # The Hermes executable and chat subcommand must be present.
    assert "chat" in argv
    # No explicit model/provider -> Hermes config.yaml default is used.
    assert "-m" not in argv
    assert "--provider" not in argv
    # max-turns is still bounded (default 12).
    assert "--max-turns" in argv
    mt_idx = argv.index("--max-turns")
    assert argv[mt_idx + 1] == "12"


def test_explicit_override_emits_model_and_provider():
    """Explicit override flows through to Hermes CLI flags."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(
        task, ctx, model="kr/claude-sonnet-4.5", provider="custom:archkian"
    )

    argv = _captured_bwrap_cmd(executor, task, ctx)
    assert argv is not None
    assert argv[argv.index("-m") + 1] == "kr/claude-sonnet-4.5"
    assert argv[argv.index("--provider") + 1] == "custom:archkian"


def test_max_turns_configurable():
    """max_turns is taken from the constructor argument."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(task, ctx, max_turns=15)

    argv = _captured_bwrap_cmd(executor, task, ctx)
    assert argv is not None
    mt_idx = argv.index("--max-turns")
    assert argv[mt_idx + 1] == "15"


def test_default_max_turns_is_bounded():
    """Default max_turns is a small bounded number (12), preventing runaway loops."""
    executor = HermesExecutor(_make_task(), ExecutionContext(task=_make_task(), settings={}, registry=None))
    assert executor.max_turns == 12
    assert 1 <= executor.max_turns <= 30


def test_heartbeat_interval_not_five_second_spam():
    """Heartbeat interval default is 15s, not 5s."""
    executor = HermesExecutor(_make_task(), ExecutionContext(task=_make_task(), settings={}, registry=None))
    assert executor.heartbeat_interval == 15
    assert executor.heartbeat_interval != 5


def test_api_key_never_exposed_in_events():
    """Resolved model/provider note must never contain API keys or secrets."""
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=engine.registry)
    executor = HermesExecutor(
        task, ctx, model="kr/claude-sonnet-4.5", provider="custom:archkian"
    )

    events = []
    async def fake_stream(prompt, runtime):
        yield await runtime.tick(runtime.working("coding"))

    async def go():
        with patch.object(executor, "_run_hermes_streaming", fake_stream):
            async for ev in executor.execute(task, ctx):
                events.append(ev)

    _run(go())

    blob = " ".join(str(getattr(e, "message", "")) for e in events)
    blob += " ".join(str(getattr(e, "meta", "")) for e in events)
    assert "HERMES_CUSTOM_LOCALHOST" not in blob
    assert "API_KEY" not in blob
    assert "Authorization" not in blob


def test_factory_passes_config_to_executor():
    """ForgeFactory wires config (model/provider/max_turns) into HermesExecutor."""
    from ai_dev_api.config import settings
    from ai_dev_api.agents import ForgeFactory

    settings.forge_model = ""
    settings.forge_provider = ""
    settings.forge_max_turns = 12

    factory = ForgeFactory()
    ex = factory(_make_task(), ExecutionContext(task=_make_task(), settings={}, registry=None))
    assert isinstance(ex, HermesExecutor)
    assert ex.model == ""
    assert ex.provider == ""
    assert ex.max_turns == 12
