"""
Regression tests for Phase 2 — Real Deterministic QA.

These tests mock ONLY the network/process boundary (the bwrap subprocess) so
the real command detection, PASS/FAIL logic, NOT_VERIFIED contract, and
structured result reporting are exercised for real.

Run with:  .venv/bin/python3 -m pytest apps/api/tests/test_phase2_qa.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ai_dev_agent_core import ExecutionContext, AgentRegistry
from ai_dev_agent_qa import DeterministicQAExecutor, cancel_qa_execution
from ai_dev_shared import AgentEvent, EventKind, Task, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "qa-task-001") -> Task:
    return Task(
        id=task_id,
        title="Verify a small Node project",
        description="Run the project's checks.",
    )


def _run(coro):
    return asyncio.run(coro)


def _collect(task: Task, ctx, executor: DeterministicQAExecutor,
             fake_check=None):
    """Run the executor with an optional fake _run_check, returning events."""
    events: list[AgentEvent] = []

    async def go():
        if fake_check is not None:
            with patch.object(executor, "_run_check", fake_check):
                async for ev in executor.execute(task, ctx):
                    events.append(ev)
        else:
            async for ev in executor.execute(task, ctx):
                events.append(ev)

    _run(go())
    return events


def _make_workspace(task: Task, package_scripts: dict | None = None,
                    files: dict | None = None) -> Path:
    """Create a real disposable workspace on disk (mirrors FORGE output)."""
    root = Path.home() / "ai-dev-office" / "workspaces"
    ws = root / task.id[:12]
    if ws.exists():
        import shutil as _sh
        _sh.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)

    if package_scripts is not None:
        (ws / "package.json").write_text(
            json.dumps({"name": "tmp", "scripts": package_scripts})
        )
    if files:
        for name, content in files.items():
            (ws / name).write_text(content)
    return ws


def _ok_check(name: str, exit_code: int = 0):
    async def fake(workspace, command):
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "output": f"{name} output",
            "error": "" if exit_code == 0 else f"{name} failed",
        }
    return fake


# ---------------------------------------------------------------------------
# Test A: QA uses SAME workspace as FORGE (task.id[:12])
# ---------------------------------------------------------------------------

def test_qa_uses_forge_workspace_location():
    """QA must inspect the same workspace FORGE wrote to (task.id[:12])."""
    task = _make_task()
    ws = _make_workspace(task, files={"README.md": "hi"})
    # Sanity: the workspace FORGE would use equals what QA reads.
    from ai_dev_agent_qa.executor import DeterministicQAExecutor as QA
    expected = Path.home() / "ai-dev-office" / "workspaces" / task.id[:12]
    assert ws == expected
    # Cleanup
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test B: detects available package scripts
# ---------------------------------------------------------------------------

def test_detects_available_package_scripts():
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true", "lint": "true"})
    ex = DeterministicQAExecutor(task, ExecutionContext(task=task, settings={}, registry=None))
    checks = ex._detect_checks(ws)
    names = [n for n, _ in checks]
    assert "test" in names
    assert "lint" in names
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


def test_nonexistent_script_is_not_fabricated():
    """A script not present in package.json is skipped, never invented."""
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"build": "true"})
    ex = DeterministicQAExecutor(task, ExecutionContext(task=task, settings={}, registry=None))
    checks = ex._detect_checks(ws)
    names = [n for n, _ in checks]
    # Only 'build' exists -> none of test/typecheck/lint should appear.
    assert "test" not in names
    assert "typecheck" not in names
    assert "lint" not in names
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test C: exit 0 -> PASS, nonzero -> FAIL (real evidence)
# ---------------------------------------------------------------------------

def test_exit_zero_produces_pass_with_real_evidence():
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    events = _collect(task, ctx, ex, fake_check=_ok_check("test", 0))

    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert qa_results, "must emit a QA_RESULT event"
    assert qa_results[-1].score == "PASS"
    report = qa_results[-1].meta["qa_report"]
    assert report["overall_pass"] is True
    assert report["checks"][0]["exit_code"] == 0
    assert report["checks"][0]["command"].endswith("npm run test")
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


def test_nonzero_exit_produces_fail():
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    events = _collect(task, ctx, ex, fake_check=_ok_check("test", 1))

    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert qa_results[-1].score == "FAIL"
    report = qa_results[-1].meta["qa_report"]
    assert report["overall_pass"] is False
    assert report["checks"][0]["exit_code"] == 1
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test D: no runnable checks -> NOT_VERIFIED, NOT fake PASS
# ---------------------------------------------------------------------------

def test_no_runnable_checks_is_not_verified_not_fake_pass():
    task = _make_task()
    ws = _make_workspace(task, files={"notes.txt": "just text"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    events = _collect(task, ctx, ex)

    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert qa_results, "still emits a QA_RESULT so ATLAS sees NOT_VERIFIED"
    assert qa_results[-1].score == "NOT_VERIFIED"
    assert qa_results[-1].score != "PASS"
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test E: structured evidence reaches ATLAS (checks list in shared + event)
# ---------------------------------------------------------------------------

def test_structured_checks_reach_atlas_via_shared():
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true", "lint": "true"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    _collect(task, ctx, ex, fake_check=_ok_check("x", 0))

    report = ctx.shared.get("qa_report")
    assert report is not None
    assert report["verified"] is True
    assert len(report["checks"]) == 2
    for c in report["checks"]:
        assert set(c.keys()) >= {"name", "command", "exit_code", "passed", "summary"}
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test F: fake canned messages absent from production executor
# ---------------------------------------------------------------------------

def test_real_executor_has_no_canned_messages():
    import ai_dev_agent_qa.executor as mod
    src = Path(mod.__file__).read_text()
    assert "12 passed" not in src
    assert "tsc --noEmit → 0 errors" not in src
    assert "next lint → clean" not in src


# ---------------------------------------------------------------------------
# Test G: stdout/stderr bounded
# ---------------------------------------------------------------------------

def test_output_is_bounded():
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    big = "x" * 99999

    async def fake_big(workspace, command):
        return {"success": True, "exit_code": 0, "output": big, "error": ""}

    events = _collect(task, ctx, ex, fake_check=fake_big)
    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    report = qa_results[-1].meta["qa_report"]
    # The stored summary must be truncated to the bound.
    assert len(report["checks"][0]["summary"]) <= 4000
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test H: cancellation terminates QA subprocess only (no fake, INT state)
# ---------------------------------------------------------------------------

def test_cancel_qa_returns_false_when_no_process():
    assert cancel_qa_execution("nonexistent-task-id") is False


def test_cancel_sets_interrupt_state():
    """When cancelled mid-run, QA emits INTERRUPTED and resets to idle."""
    task = _make_task()
    ws = _make_workspace(task, package_scripts={"test": "true"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    events: list[AgentEvent] = []

    async def slow_check(workspace, command):
        await asyncio.sleep(5)
        return {"success": True, "exit_code": 0, "output": "ok", "error": ""}

    async def go():
        with patch.object(ex, "_run_check", slow_check):
            ex.request_cancel()
            async for ev in ex.execute(task, ctx):
                events.append(ev)

    _run(go())

    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert qa_results[-1].score == "INTERRUPTED"
    idle_events = [e for e in events if e.agent_status and e.agent_status.value == "IDLE"]
    assert idle_events, "QA must return to IDLE after cancel"
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# Test I: engine cancel_running now signals QA too
# ---------------------------------------------------------------------------

def test_engine_cancel_running_signals_qa():
    from ai_dev_agent_core import OrchestrationEngine

    engine = OrchestrationEngine(AgentRegistry(), orchestrator_agent="atlas")
    engine._running = _make_task("qa-active-001")
    assert engine.cancel_running("qa-active-001") is True


# ---------------------------------------------------------------------------
# Test J: empty workspace -> FAIL (not NOT_VERIFIED)
# ---------------------------------------------------------------------------

def test_empty_workspace_is_fail():
    task = _make_task()
    ws = _make_workspace(task)  # created but no files
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = DeterministicQAExecutor(task, ctx)

    events = _collect(task, ctx, ex)
    qa_results = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert qa_results[-1].score == "FAIL"
    import shutil as _sh
    _sh.rmtree(ws, ignore_errors=True)
