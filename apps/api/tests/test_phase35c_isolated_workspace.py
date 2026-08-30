"""
Regression tests for Phase 3.5c — Real agents use the SAME isolated workspace.

Proves that SCOUT, FORGE, and QA all operate on EXACTLY
``workspace_meta.workspace_path`` (the isolated git worktree / copied project)
instead of diverging to ``workspaces/<task-id>``.

Run with:  .venv/bin/python3 -m pytest apps/api/tests/test_phase35c_isolated_workspace.py -v

The real Hermes end-to-end test (test_real_hermes_e2e_target_project) requires
the local Hermes agent + bwrap; it is skipped when they are unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_dev_agent_core import AgentRegistry, ExecutionContext, OrchestrationEngine
from ai_dev_shared import AgentEvent, EventKind, Task, TaskStatus
from ai_dev_shared.workspace import (
    WorkspaceMeta,
    cleanup_workspace_meta,
    compute_workspace_result,
    execution_workspace,
    prepare_workspace,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOME_WS = Path.home() / "ai-dev-office" / "workspaces"


def _run(coro):
    return asyncio.run(coro)


async def _async_broadcast(_message):
    """No-op async broadcast so the engine pipeline can run in tests."""
    return None


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _new_task(target: str | None = None) -> Task:
    return Task(
        id=uuid.uuid4().hex,
        title="isolated workspace task",
        description="modify files",
        target_project=str(target) if target else None,
    )


def _empty_ctx(task: Task, meta: WorkspaceMeta | None = None,
               settings=None) -> ExecutionContext:
    ctx = ExecutionContext(
        task=task,
        settings=settings or {},
        registry=AgentRegistry(),
    )
    if meta is not None:
        ctx.shared["workspace_meta"] = meta
    return ctx


def _make_clean_git_repo(files: dict[str, str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp())
    _git(["init"], d)
    _git(["config", "user.email", "test@test.com"], d)
    _git(["config", "user.name", "Test"], d)
    files = files or {"README.md": "# test project\n"}
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(["add", "."], d)
    _git(["commit", "-m", "initial"], d)
    return d


def _make_dirty_git_repo() -> Path:
    d = _make_clean_git_repo()
    (d / "dirty.txt").write_text("uncommitted change\n")
    return d


def _make_non_git_dir(files: dict[str, str] | None = None) -> Path:
    d = Path(tempfile.mkdtemp())
    files = files or {"index.js": "console.log('hi');\n"}
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return d


def _cleanup_ws(task_id: str, src: Path | None = None) -> None:
    ws_dir = _HOME_WS / task_id[:12]
    shutil.rmtree(ws_dir, ignore_errors=True)
    if src is not None:
        shutil.rmtree(src, ignore_errors=True)


# ---------------------------------------------------------------------------
# A: shared execution_workspace helper
# ---------------------------------------------------------------------------

def test_execution_workspace_prefers_workspace_meta():
    task = _new_task()
    meta = WorkspaceMeta(
        task_id=task.id,
        workspace_path=Path("/home/ado-anywhere/worktree"),
        source_project=None,
        mode="git-worktree",
    )
    ctx = _empty_ctx(task, meta)
    assert execution_workspace(task, ctx) == Path("/home/ado-anywhere/worktree").resolve()


def test_execution_workspace_legacy_fallback():
    task = _new_task()
    ctx = _empty_ctx(task)  # no workspace_meta
    from ai_dev_shared.workspace import resolve
    expected = resolve(task.id).path
    assert execution_workspace(task, ctx) == expected


def test_execution_workspace_empty_mode_with_meta():
    task = _new_task()
    meta = prepare_workspace(task.id, None, workspace_root=_HOME_WS)
    ctx = _empty_ctx(task, meta)
    try:
        ws = execution_workspace(task, ctx)
        assert meta.mode == "empty"
        assert ws == Path(meta.workspace_path).resolve()
    finally:
        shutil.rmtree(_HOME_WS / task.id[:12], ignore_errors=True)


# ---------------------------------------------------------------------------
# B: SCOUT uses the worktree path
# ---------------------------------------------------------------------------

def _scout_report(ctx: ExecutionContext, task: Task) -> dict:
    from ai_dev_agent_scout.executor import RealScoutExecutor
    ex = RealScoutExecutor(task, ctx)

    async def go():
        async for _ in ex.execute(task, ctx):
            pass

    _run(go())
    return ctx.shared["research"]


def test_scout_workspace_path_equals_meta_worktree():
    src = _make_clean_git_repo({"src/index.js": "export const a = 1;\n"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        report = _scout_report(ctx, task)
        assert meta.mode == "git-worktree"
        assert report["workspace_path"] == str(Path(meta.workspace_path).resolve())
        assert "index.js" in report["summary"] or "index.js" in report["relevant_files"]
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def test_scout_does_not_fall_back_to_repo_when_meta_exists():
    src = _make_clean_git_repo({"src/index.js": "x"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        # Remove the worktree dir on disk — meta still exists.
        shutil.rmtree(meta.workspace_path)
        report = _scout_report(ctx, task)
        # Scope must stay 'workspace', not fall back to the ai-dev-office repo.
        assert report["scope"] == "workspace"
        assert report["workspace_path"] == str(Path(meta.workspace_path).resolve())
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


# ---------------------------------------------------------------------------
# C: FORGE uses the worktree path + bwrap bind
# ---------------------------------------------------------------------------

def test_forge_execution_path_equals_meta_worktree():
    from ai_dev_agent_forge.executor import HermesExecutor
    src = _make_clean_git_repo({"src/index.js": "x"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        ex = HermesExecutor(task, ctx)

        async def go():
            return await ex._create_workspace(task)

        ws = _run(go())
        assert ws == Path(meta.workspace_path).resolve()
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def _fake_proc_factory(captured: dict):
    class _FakeProc:
        returncode = 0
        stdout = None
        stderr = None

        async def wait(self):
            return 0

        async def communicate(self):
            return b"", b""

    async def _factory(*args, **kwargs):
        captured["argv"] = list(args)
        return _FakeProc()

    return _factory


def test_forge_bwrap_bind_uses_worktree_path():
    from ai_dev_agent_forge.executor import HermesExecutor
    src = _make_clean_git_repo({"src/index.js": "x"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        ex = HermesExecutor(task, ctx)
        captured = {}

        async def go():
            with patch(
                "ai_dev_agent_forge.executor.asyncio.create_subprocess_exec",
                new=_fake_proc_factory(captured),
            ):
                async for _ in ex.execute(task, ctx):
                    pass

        _run(go())
        argv = captured["argv"]
        assert argv is not None
        bind_idx = argv.index("--bind")
        # The writable /workspace bind MUST be the isolated worktree.
        assert argv[bind_idx + 1] == str(Path(meta.workspace_path).resolve())
        assert argv[bind_idx + 2] == "/workspace"
        # cwd is inside /workspace, not a host path.
        assert argv[argv.index("--chdir") + 1] == "/workspace"
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def test_forge_result_reports_workspace_path():
    from ai_dev_agent_forge.executor import HermesExecutor
    src = _make_clean_git_repo({"src/index.js": "x"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        ex = HermesExecutor(task, ctx)
        events: list[AgentEvent] = []

        async def go():
            with patch(
                "ai_dev_agent_forge.executor.asyncio.create_subprocess_exec",
                new=_fake_proc_factory({}),
            ):
                async for ev in ex.execute(task, ctx):
                    events.append(ev)

        _run(go())
        fr = next(
            (
                e.meta["forge_result"]
                for e in events
                if e.kind == EventKind.RESULT and e.meta.get("forge_result")
            ),
            None,
        )
        assert fr is not None, "FORGE emitted a structured result"
        assert fr["workspace_path"] == str(Path(meta.workspace_path).resolve())
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


# ---------------------------------------------------------------------------
# D: QA uses the worktree path + ro-bind
# ---------------------------------------------------------------------------

def test_qa_workspace_for_equals_meta_worktree():
    from ai_dev_agent_qa.executor import DeterministicQAExecutor
    src = _make_clean_git_repo({"src/index.js": "x"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        ex = DeterministicQAExecutor(task, ctx)
        assert ex._workspace_for(task) == Path(meta.workspace_path).resolve()
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def test_qa_bwrap_ro_bind_uses_worktree_path():
    from ai_dev_agent_qa.executor import DeterministicQAExecutor
    src = _make_clean_git_repo({"package.json": json.dumps({"scripts": {"test": "true"}})})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        ex = DeterministicQAExecutor(task, ctx)
        captured = {}

        async def go():
            with patch(
                "ai_dev_agent_qa.executor.asyncio.create_subprocess_exec",
                new=_fake_proc_factory(captured),
            ):
                await ex._run_check(Path(meta.workspace_path), ["true"])

        _run(go())
        argv = captured["argv"]
        ro_idx = argv.index("--ro-bind")
        assert argv[ro_idx + 1] == str(Path(meta.workspace_path).resolve())
        assert argv[ro_idx + 2] == "/workspace"
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def _run_qa_pass(task: Task, meta: WorkspaceMeta):
    from ai_dev_agent_qa.executor import DeterministicQAExecutor
    ctx = _empty_ctx(task, meta)
    ex = DeterministicQAExecutor(task, ctx)
    events: list[AgentEvent] = []

    async def fake_check(workspace, command):
        return {"success": True, "exit_code": 0, "output": "ok", "error": ""}

    async def go():
        with patch.object(ex, "_run_check", fake_check):
            async for ev in ex.execute(task, ctx):
                events.append(ev)

    _run(go())
    return events, ctx.shared["qa_report"]


def test_qa_report_reports_workspace_path():
    src = _make_clean_git_repo({
        "package.json": json.dumps({"scripts": {"test": "true"}}),
    })
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        events, report = _run_qa_pass(task, meta)
        assert report["score"] == "PASS"
        assert report["workspace_path"] == str(Path(meta.workspace_path).resolve())
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


# ---------------------------------------------------------------------------
# E: workspace_result uses the same path (copy + git modes)
# ---------------------------------------------------------------------------

def test_workspace_result_path_equals_execution_workspace_git():
    src = _make_clean_git_repo({"README.md": "original\n"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        (meta.workspace_path / "new.txt").write_text("added\n")
        ctx = _empty_ctx(task, meta)
        result = compute_workspace_result(meta)
        assert result.workspace_path == execution_workspace(task, ctx)
        assert result.apply_ready is True
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def test_workspace_result_path_equals_execution_workspace_copy():
    src = _make_non_git_dir({"index.js": "console.log('hi');\n"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        ctx = _empty_ctx(task, meta)
        assert meta.mode == "copy"
        assert execution_workspace(task, ctx) == Path(meta.workspace_path).resolve()
        assert compute_workspace_result(meta).workspace_path == Path(meta.workspace_path).resolve()
    finally:
        _cleanup_ws(task.id, src)


def test_target_project_none_behavior_unchanged():
    task = _new_task(None)
    meta = prepare_workspace(task.id, None, workspace_root=_HOME_WS)
    try:
        ctx = _empty_ctx(task, meta)
        ws = execution_workspace(task, ctx)
        assert meta.mode == "empty"
        assert ws == Path(meta.workspace_path).resolve()
    finally:
        _cleanup_ws(task.id)


# ---------------------------------------------------------------------------
# F: git worktree cleanup (explicit removal from source registry)
# ---------------------------------------------------------------------------

def test_git_worktree_cleanup_removes_registration():
    src = _make_clean_git_repo({"README.md": "ok\n"})
    task = _new_task(str(src))
    worktree_dir: Path | None = None
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        worktree_dir = meta.workspace_path
        assert (src / ".git" / "worktrees").exists() or "worktree" in _git(
            ["worktree", "list"], src
        ).stdout
        worktree_cmd = _git(["worktree", "list"], src)
        out = worktree_cmd.stdout
        assert worktree_cmd.returncode == 0
        assert str(worktree_dir.resolve()) in out

        removed = cleanup_workspace_meta(meta, workspace_root=_HOME_WS)
        assert removed is True
        # Registration gone from the SOURCE repo's worktree registry.
        out2 = _git(["worktree", "list"], src).stdout
        assert str(worktree_dir.resolve()) not in out2
        # Worktree directory gone.
        assert not worktree_dir.exists()
        # Source repo untouched.
        assert not _git(["status", "--porcelain"], src).stdout.strip()
    finally:
        if worktree_dir is not None and worktree_dir.exists():
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=src, capture_output=True)
        _cleanup_ws(task.id, src)


def test_git_worktree_cleanup_failure_does_not_crash():
    """Cleanup failure is logged, not raised — runtime keeps running."""
    src = _make_clean_git_repo({"README.md": "ok\n"})
    task = _new_task(str(src))
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=_HOME_WS)
        # Force the git worktree remove to fail by removing the source repo.
        shutil.rmtree(src)
        # Must not raise.
        cleanup_workspace_meta(meta, workspace_root=_HOME_WS)
        assert True
    finally:
        _cleanup_ws(task.id)


# ---------------------------------------------------------------------------
# G: dirty repo regression — task aborts before any specialist
# ---------------------------------------------------------------------------

def test_dirty_repo_engine_aborts_before_dispatch():
    src = _make_dirty_git_repo()
    dirty_file = src / "dirty.txt"
    task = _new_task(str(src))
    engine = OrchestrationEngine(
        AgentRegistry(),
        orchestrator_agent="atlas",
        broadcast=_async_broadcast,
    )

    async def go():
        await engine.enqueue(task)
        deadline = time.time() + 30
        while time.time() < deadline:
            await asyncio.sleep(0.05)
            if task.status in (TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED):
                break

    _run(go())
    assert task.status == TaskStatus.FAILED
    assert "uncommitted changes" in (task.error or "")
    # No worktree was created.
    assert not (_HOME_WS / task.id[:12] / "worktree").exists()
    # Source dirty file untouched, still dirty, no stash/reset.
    assert dirty_file.exists()
    assert dirty_file.read_text() == "uncommitted change\n"
    assert "dirty.txt" in _git(["status", "--porcelain"], src).stdout
    _cleanup_ws(task.id, src)


# ---------------------------------------------------------------------------
# H: real Hermes end-to-end — SCOUT → FORGE → QA on one isolated project
# ---------------------------------------------------------------------------

class _RecordingEngine(OrchestrationEngine):
    """Engine that records every streamed AgentEvent for evidence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: list[tuple] = []

    async def _apply(self, event, task):
        meta = dict(event.meta or {})
        for key in ("forge_raw_output", "forge_raw_error", "raw_output", "raw_error"):
            meta.pop(key, None)
        self.events.append(
            (event.agent_id, event.kind, event.message, event.score, meta)
        )
        await super()._apply(event, task)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


_HERMES_EXE = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "hermes"

_need_hermes = pytest.mark.skipif(
    not (Path("/usr/bin/bwrap").exists() and _HERMES_EXE.exists()),
    reason="local Hermes agent + bwrap required for real E2E",
)


@_need_hermes
def test_real_hermes_e2e_target_project():
    from ai_dev_api.agents import build_registry

    target_dir = Path("/tmp/ado-target-real-e2e")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True)

    (target_dir / "package.json").write_text(
        json.dumps(
            {
                "name": "ado-target-real-e2e",
                "version": "1.0.0",
                "scripts": {"test": "node test.js"},
            },
            indent=2,
        )
    )
    src_dir = target_dir / "src"
    src_dir.mkdir()
    (src_dir / "index.js").write_text(
        "function add(a, b) {\n  return a + b;\n}\n\nmodule.exports = { add };\n"
    )
    (target_dir / "test.js").write_text(
        "const assert = require('assert');\n"
        "const { add } = require('./src/index');\n"
        "assert.strictEqual(add(2, 3), 5);\n"
        "console.log('baseline ok');\n"
    )

    _git(["init"], target_dir)
    _git(["config", "user.email", "e2e@test.com"], target_dir)
    _git(["config", "user.name", "E2E"], target_dir)
    _git(["add", "."], target_dir)
    _git(["commit", "-m", "baseline"], target_dir)

    head_before = _git(["rev-parse", "HEAD"], target_dir).stdout.strip()
    status_before = _git(["status", "--porcelain"], target_dir).stdout
    hash_before = _sha256(src_dir / "index.js")

    registry = build_registry()
    engine = _RecordingEngine(
        registry,
        orchestrator_agent="atlas",
        broadcast=_async_broadcast,
        settings={
            "speed": 99.0,
            "forge_workspace_root": _HOME_WS,
            "cleanup_workspace": False,
        },
    )

    task = Task(
        title="Implementasikan fungsi greet pada project Node",
        description=(
            "Gunakan SCOUT, FORGE, dan QA.\n"
            "SCOUT:\n"
            "Periksa project dan tentukan file yang relevan.\n"
            "FORGE:\n"
            "Tambahkan fungsi greet(name) di src/index.js yang mengembalikan:\n"
            "Hello, <name>!\n"
            "Sesuaikan test.js agar fungsi greet diverifikasi.\n"
            "QA:\n"
            "Jalankan verifikasi nyata menggunakan test project."
        ),
        target_project=str(target_dir),
    )

    try:
        async def go():
            await engine.enqueue(task)
            deadline = time.time() + 900
            while time.time() < deadline:
                await asyncio.sleep(0.5)
                if task.status in (
                    TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED,
                ):
                    await asyncio.sleep(0.2)
                    return task
            raise TimeoutError("E2E pipeline did not finish within 900s")

        _run(go())
    finally:
        pass

    meta_ws: Path | None = None
    try:
        # ── Proof 1: git-worktree mode ─────────────────────────────────────
        assert task.workspace_meta is not None
        assert task.workspace_meta["mode"] == "git-worktree"
        meta_ws = Path(task.workspace_meta["workspace_path"]).resolve()
        assert meta_ws.is_dir()
        assert str(meta_ws).startswith(str(_HOME_WS))

        # ── Proof 2/5: SCOUT + QA report the same workspace_path ───────────
        scout_report = None
        forge_result = None
        qa_report = None
        atlas_result = None
        for agent_id, kind, message, score, meta in engine.events:
            if agent_id == "scout" and "scout_report" in meta:
                scout_report = meta["scout_report"]
            if agent_id == "forge" and kind == EventKind.RESULT and meta.get("forge_result"):
                forge_result = meta["forge_result"]
            if kind == EventKind.QA_RESULT and meta.get("qa_report"):
                qa_report = meta["qa_report"]
            if agent_id == "atlas" and kind == EventKind.RESULT and meta.get("workspace_result"):
                atlas_result = meta["workspace_result"]

        assert scout_report is not None, "scout ran and reported"
        assert forge_result is not None, "forge ran and reported"
        assert qa_report is not None, "qa ran and reported"
        assert atlas_result is not None, "atlas computed workspace_result"

        assert scout_report["workspace_path"] == str(meta_ws)
        assert forge_result["workspace_path"] == str(meta_ws)
        assert qa_report["workspace_path"] == str(meta_ws)
        assert atlas_result["workspace_path"] == str(meta_ws)

        # ── Proof 3/4: Hermes really edited the worktree ───────────────────
        status_worktree = _git(["status", "--porcelain"], meta_ws).stdout
        assert "src/index.js" in status_worktree or "index.js" in status_worktree
        new_index = (meta_ws / "src" / "index.js").read_text()
        assert "greet" in new_index
        new_test = (meta_ws / "test.js").read_text()
        assert "greet" in new_test

        # ── Proof 6/7: QA ran npm test with exit code 0 ────────────────────
        assert qa_report["score"] == "PASS"
        test_check = next(
            (c for c in qa_report.get("checks", []) if c.get("name") == "test"), None
        )
        assert test_check is not None, "QA ran the 'test' script"
        assert "npm run test" in test_check["command"]
        assert test_check["exit_code"] == 0

        # ── Proof 11/12/13: worktree status + workspace_result + apply_ready ──
        assert atlas_result["apply_ready"] is True
        changed = set(atlas_result.get("changed_files", []))
        assert "src/index.js" in changed
        assert "test.js" in changed

        # ── Proof 8/9/10: source repo untouched ────────────────────────────
        status_after = _git(["status", "--porcelain"], target_dir).stdout
        head_after = _git(["rev-parse", "HEAD"], target_dir).stdout.strip()
        hash_after = _sha256(src_dir / "index.js")
        assert status_after == "" and status_before == ""
        assert head_after == head_before
        assert hash_after == hash_before

        # ── Cleanup: explicit git worktree removal ─────────────────────────
        meta_obj = WorkspaceMeta(
            task_id=task.id,
            workspace_path=meta_ws,
            source_project=target_dir,
            mode="git-worktree",
        )
        cleanup_workspace_meta(meta_obj, workspace_root=_HOME_WS)
        wt_list = _git(["worktree", "list"], target_dir).stdout
        assert str(meta_ws) not in wt_list
    finally:
        # Best-effort cleanup even when an assertion failed mid-run.
        if meta_ws is not None and target_dir.exists():
            try:
                cleanup_workspace_meta(
                    WorkspaceMeta(
                        task_id=task.id,
                        workspace_path=meta_ws,
                        source_project=target_dir,
                        mode="git-worktree",
                    ),
                    workspace_root=_HOME_WS,
                )
            except Exception:
                pass
        shutil.rmtree(target_dir, ignore_errors=True)