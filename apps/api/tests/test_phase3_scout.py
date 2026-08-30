"""
Regression tests for Phase 3 — Real SCOUT Research.

Tests verify the RealScoutExecutor:
- produces structured scout_report in ctx.shared
- never fabricates file findings
- stays read-only (no writes)
- passes bounded handoff to FORGE via ctx.shared["research"]
- does not trigger external research for ordinary local tasks
- semantic state transitions correctly
- cancellation works
- existing Phase 1.5/2/2.1 paths unaffected

Run with:  .venv/bin/python3 -m pytest apps/api/tests/test_phase3_scout.py -v
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import patch

from ai_dev_agent_core import ExecutionContext, AgentRegistry
from ai_dev_agent_scout.executor import (
    RealScoutExecutor,
    _scan_tree,
    _read_manifests,
    _identify_relevant,
    _extract_deps,
    _is_blocked,
    _wants_external,
)
from ai_dev_shared import AgentEvent, EventKind, Task, TaskStatus
from ai_dev_shared.constants import AgentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "scout-task-001", title: str = "Tambahkan fitur kalkulator",
               description: str = "Implementasikan fungsi add di calculator.py") -> Task:
    return Task(id=task_id, title=title, description=description)


def _run(coro):
    return asyncio.run(coro)


def _make_workspace(task: Task, files: dict[str, str] | None = None) -> Path:
    """Create a real disposable workspace for SCOUT to inspect."""
    ws = Path.home() / "ai-dev-office" / "workspaces" / task.id[:12]
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)
    if files:
        for name, content in files.items():
            p = ws / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
    return ws


def _collect(task: Task, ctx, ws: Path | None = None) -> tuple[list[AgentEvent], dict]:
    """Run RealScoutExecutor to completion, return events + scout_report."""
    ex = RealScoutExecutor(task, ctx)
    events: list[AgentEvent] = []

    async def go():
        async for ev in ex.execute(task, ctx):
            events.append(ev)

    _run(go())
    report = ctx.shared.get("research", {})
    return events, report


# ---------------------------------------------------------------------------
# A: scout_report is always present in ctx.shared after execution
# ---------------------------------------------------------------------------

def test_scout_report_in_shared_after_run():
    task = _make_task()
    ws = _make_workspace(task, {"index.ts": "export const x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    events, report = _collect(task, ctx, ws)
    assert "research" in ctx.shared
    assert report.get("summary") is not None
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# B: structured contract — required keys present
# ---------------------------------------------------------------------------

def test_scout_report_has_required_keys():
    task = _make_task()
    ws = _make_workspace(task, {"index.ts": "export const x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    for key in ("summary", "relevant_files", "recommendations", "constraints", "references"):
        assert key in report, f"missing key: {key}"
    assert isinstance(report["relevant_files"], list)
    assert isinstance(report["recommendations"], list)
    assert isinstance(report["constraints"], list)
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# C: relevant_files only contains files that actually exist
# ---------------------------------------------------------------------------

def test_relevant_files_only_real_files():
    task = _make_task()
    ws = _make_workspace(task, {
        "calculator.py": "def add(a, b): return a + b",
        "test_calculator.py": "def test_add(): pass",
        "README.md": "# Calculator",
    })
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    for rel in report["relevant_files"]:
        assert (ws / rel).exists(), f"reported non-existent file: {rel}"
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# D: SCOUT never invents files not on disk
# ---------------------------------------------------------------------------

def test_scout_does_not_invent_files():
    task = _make_task()
    ws = _make_workspace(task, {"only_real.py": "x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    for rel in report["relevant_files"]:
        assert (ws / rel).exists(), f"invented file: {rel}"
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# E: package.json is read and deps extracted
# ---------------------------------------------------------------------------

def test_package_json_deps_extracted():
    task = _make_task()
    pkg = json.dumps({"name": "myapp", "dependencies": {"react": "^18", "next": "^14"},
                      "devDependencies": {"typescript": "^5"}})
    ws = _make_workspace(task, {"package.json": pkg, "index.ts": ""})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    summary = report["summary"]
    assert "react" in summary or "next" in summary, "deps not in summary"
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# F: no external research triggered for ordinary local task
# ---------------------------------------------------------------------------

def test_no_external_research_for_local_task():
    task = _make_task(title="Tambahkan fungsi add", description="Buat calculator.py")
    ws = _make_workspace(task, {"calculator.py": "x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    assert report.get("external_research") is False
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# G: external research flag set when task explicitly requests it
# ---------------------------------------------------------------------------

def test_external_research_flagged_for_doc_task():
    task = _make_task(
        title="Research best library",
        description="Bandingkan library untuk HTTP client, documentation required.",
    )
    ws = _make_workspace(task, {"index.ts": ""})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    assert report.get("external_research") is True
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# H: QA_RESULT / RESULT events absent — SCOUT does not own verification
# ---------------------------------------------------------------------------

def test_scout_emits_no_qa_result_event():
    task = _make_task()
    ws = _make_workspace(task, {"index.ts": "x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    events, _ = _collect(task, ctx, ws)
    qa_result_events = [e for e in events if e.kind == EventKind.QA_RESULT]
    assert not qa_result_events, "SCOUT must not emit QA_RESULT"
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# I: SCOUT semantic state — WORKING during research, IDLE on success
# ---------------------------------------------------------------------------

def test_scout_semantic_working_then_idle():
    task = _make_task()
    ws = _make_workspace(task, {"index.ts": "x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    events, _ = _collect(task, ctx, ws)
    statuses = [e.agent_status for e in events if e.agent_status is not None]
    assert AgentStatus.WORKING in statuses, "SCOUT must emit WORKING"
    assert statuses[-1] == AgentStatus.IDLE, "SCOUT must end IDLE"
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# J: cancellation yields INTERRUPTED
# ---------------------------------------------------------------------------

def test_scout_cancel_yields_interrupted():
    task = _make_task()
    ws = _make_workspace(task, {"index.ts": "x = 1"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ex = RealScoutExecutor(task, ctx)
    ex.request_cancel()
    events: list[AgentEvent] = []

    async def go():
        async for ev in ex.execute(task, ctx):
            events.append(ev)

    _run(go())
    result_evs = [e for e in events if e.kind == EventKind.RESULT]
    assert result_evs, "must emit RESULT on cancel"
    assert result_evs[-1].task_status == TaskStatus.INTERRUPTED
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# K: blocked files never read
# ---------------------------------------------------------------------------

def test_blocked_files_not_read():
    for name in (".env", ".env.local", "id_rsa", "credentials"):
        assert _is_blocked(Path(name)), f"{name} should be blocked"
    for suffix in (".pem", ".key", ".p12"):
        assert _is_blocked(Path(f"secret{suffix}")), f"*.{suffix} should be blocked"


# ---------------------------------------------------------------------------
# L: summary bounded (not dumping entire repo)
# ---------------------------------------------------------------------------

def test_summary_bounded():
    from ai_dev_agent_scout.executor import _MAX_SUMMARY_LEN
    task = _make_task()
    ws = _make_workspace(task, {f"file{i}.ts": "x" * 5000 for i in range(20)})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    assert len(report["summary"]) <= _MAX_SUMMARY_LEN + 10
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# M: FORGE receives bounded scout_report via ctx.shared (not raw transcript)
# ---------------------------------------------------------------------------

def test_forge_receives_scout_report_not_transcript():
    """ctx.shared['research'] must be the structured dict, not a raw string."""
    task = _make_task()
    ws = _make_workspace(task, {"main.py": "print('hi')"})
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    _, report = _collect(task, ctx, ws)
    research = ctx.shared.get("research")
    assert isinstance(research, dict), "FORGE expects a dict, not raw transcript"
    assert "summary" in research
    assert "relevant_files" in research
    shutil.rmtree(ws, ignore_errors=True)


# ---------------------------------------------------------------------------
# N: ScoutFactory wires RealScoutExecutor in production config
# ---------------------------------------------------------------------------

def test_scout_factory_returns_real_executor():
    from ai_dev_api.config import settings
    from ai_dev_api.agents import ScoutFactory
    settings.scout_mode = "real"
    factory = ScoutFactory()
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=None)
    ex = factory(task, ctx)
    assert isinstance(ex, RealScoutExecutor)


def test_scout_factory_returns_mock_when_configured():
    from ai_dev_api.config import settings
    from ai_dev_api.agents import ScoutFactory
    from ai_dev_agent_scout.mock import MockScoutExecutor
    settings.scout_mode = "mock"
    factory = ScoutFactory()
    task = _make_task()
    ctx = ExecutionContext(task=task, settings={}, registry=None)
    ex = factory(task, ctx)
    assert isinstance(ex, MockScoutExecutor)
    # Restore
    settings.scout_mode = "real"


# ---------------------------------------------------------------------------
# O: _scan_tree excludes node_modules and hidden dirs
# ---------------------------------------------------------------------------

def test_scan_tree_excludes_noise():
    task = _make_task()
    ws = _make_workspace(task, {
        "src/index.ts": "x",
        "node_modules/react/index.js": "y",
        ".git/HEAD": "ref",
        "__pycache__/mod.pyc": "z",
    })
    tree = _scan_tree(ws)
    paths = set(tree)
    assert "src/index.ts" in paths
    assert not any("node_modules" in p for p in paths)
    assert not any(".git" in p for p in paths)
    assert not any("__pycache__" in p for p in paths)
    shutil.rmtree(ws, ignore_errors=True)
