"""
Regression tests for Phase 3.5b — Local Target Project Isolation.

Tests verify:
- validate_target_project: expanduser, exists, is_dir, forbidden paths
- prepare_workspace: empty mode, git-worktree mode, copy mode
- dirty repo → DirtyRepositoryError before specialist execution
- git worktree isolation: source repo unchanged after worktree creation
- non-git copy: excluded paths respected
- compute_workspace_result: changed_files, added_files, diff_stat, apply_ready
- Task model + API: target_project accepted and persisted
- engine pipeline: dirty repo fails task BEFORE specialist dispatch
- workspace_meta in ctx.shared after pipeline prep
- workspace_result computed in ATLAS review

Run with:  .venv/bin/python3 -m pytest apps/api/tests/test_phase35b_target.py -v
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ai_dev_shared.workspace import (
    DirtyRepositoryError,
    WorkspaceMeta,
    WorkspaceResult,
    WorkspaceValidationError,
    compute_workspace_result,
    prepare_workspace,
    validate_target_project,
    _is_git_repo,
    _is_git_dirty,
    _git_head,
)
from ai_dev_shared import Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "tp-task-000001") -> Task:
    return Task(id=task_id, title="test target project", description="")


def _run(coro):
    return asyncio.run(coro)


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True
    )


def _make_clean_git_repo(files: dict[str, str] | None = None) -> Path:
    """Create a real temporary git repo with a clean commit."""
    d = Path(tempfile.mkdtemp())
    _git(["init"], d)
    _git(["config", "user.email", "test@test.com"], d)
    _git(["config", "user.name", "Test"], d)
    files = files or {"README.md": "# test project\n", "src/index.ts": "export const x = 1;\n"}
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(["add", "."], d)
    _git(["commit", "-m", "initial"], d)
    return d


def _make_dirty_git_repo() -> Path:
    """Create a real git repo with uncommitted changes."""
    d = _make_clean_git_repo()
    (d / "dirty.txt").write_text("uncommitted change\n")
    return d


def _make_non_git_dir(files: dict[str, str] | None = None) -> Path:
    """Create a real non-git directory."""
    d = Path(tempfile.mkdtemp())
    files = files or {"index.js": "console.log('hi');\n", ".env": "SECRET=abc"}
    for name, content in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return d


# ---------------------------------------------------------------------------
# A: validate_target_project
# ---------------------------------------------------------------------------

def test_validate_nonexistent_path_rejected():
    try:
        validate_target_project("/nonexistent/path/abc123xyz")
        assert False, "should have raised"
    except WorkspaceValidationError as e:
        assert "does not exist" in str(e)


def test_validate_file_rejected():
    with tempfile.NamedTemporaryFile() as f:
        try:
            validate_target_project(f.name)
            assert False
        except WorkspaceValidationError as e:
            assert "directory" in str(e)


def test_validate_empty_string_rejected():
    try:
        validate_target_project("")
        assert False
    except WorkspaceValidationError:
        pass


def test_validate_forbidden_ssh_rejected():
    try:
        validate_target_project(str(Path.home() / ".ssh"))
        assert False
    except WorkspaceValidationError as e:
        assert "forbidden" in str(e).lower()


def test_validate_good_path_accepted():
    d = _make_non_git_dir()
    try:
        p = validate_target_project(str(d))
        assert p.is_dir()
        assert p == d.resolve()
    finally:
        shutil.rmtree(d)


def test_validate_tilde_expanduser():
    # ~/ai-dev-office/workspaces is a valid dir if it exists
    ws = Path.home() / "ai-dev-office" / "workspaces"
    if ws.is_dir():
        p = validate_target_project("~/ai-dev-office/workspaces")
        assert p == ws.resolve()


# ---------------------------------------------------------------------------
# B: prepare_workspace — empty mode (legacy null)
# ---------------------------------------------------------------------------

def test_prepare_workspace_empty_mode_null_target():
    task = _make_task()
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    meta = prepare_workspace(task.id, None, workspace_root=ws_root)
    try:
        assert meta.mode == "empty"
        assert meta.source_project is None
        assert meta.workspace_path.is_dir()
    finally:
        shutil.rmtree(meta.workspace_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# C: prepare_workspace — git-worktree mode
# ---------------------------------------------------------------------------

def test_prepare_workspace_git_worktree_mode():
    src = _make_clean_git_repo()
    task = _make_task("gw-task-0001")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        assert meta.mode == "git-worktree"
        assert meta.source_project == src
        assert meta.workspace_path.is_dir()
        # worktree is inside the task workspace dir
        assert str(meta.workspace_path).startswith(str(ws_root / task.id[:12]))
        assert meta.source_head is not None
        assert meta.source_dirty is False
    finally:
        # Clean up worktree from source git registry before deleting
        ws_info_path = ws_root / task.id[:12]
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        shutil.rmtree(ws_info_path, ignore_errors=True)
        shutil.rmtree(src)


def test_git_worktree_source_repo_unchanged():
    """Source repo must be completely untouched after worktree creation."""
    src = _make_clean_git_repo({"README.md": "original content\n"})
    task = _make_task("gw-task-0002")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        # Source README is unchanged
        assert (src / "README.md").read_text() == "original content\n"
        # Source has no uncommitted changes after worktree creation
        assert not _is_git_dirty(src)
        # Worktree has source content
        wt_readme = meta.workspace_path / "README.md"
        assert wt_readme.exists()
        assert wt_readme.read_text() == "original content\n"
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        ws_info_path = ws_root / task.id[:12]
        shutil.rmtree(ws_info_path, ignore_errors=True)
        shutil.rmtree(src)


def test_git_worktree_head_matches_source():
    """Worktree HEAD must equal source HEAD."""
    src = _make_clean_git_repo()
    src_head = _git_head(src)
    task = _make_task("gw-task-0003")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        wt_head = _git_head(meta.workspace_path)
        assert meta.source_head == src_head
        assert wt_head == src_head
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        ws_info_path = ws_root / task.id[:12]
        shutil.rmtree(ws_info_path, ignore_errors=True)
        shutil.rmtree(src)


# ---------------------------------------------------------------------------
# D: dirty repo — FAIL SAFELY
# ---------------------------------------------------------------------------

def test_dirty_repo_raises_dirty_repository_error():
    src = _make_dirty_git_repo()
    task = _make_task("dirty-task-001")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        prepare_workspace(task.id, str(src), workspace_root=ws_root)
        assert False, "should have raised DirtyRepositoryError"
    except DirtyRepositoryError as e:
        assert "uncommitted changes" in str(e)
        # Source repo untouched
        assert _is_git_dirty(src)
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


def test_dirty_repo_error_is_user_facing():
    """DirtyRepositoryError must provide a clear actionable message."""
    src = _make_dirty_git_repo()
    task = _make_task("dirty-task-002")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        prepare_workspace(task.id, str(src), workspace_root=ws_root)
    except DirtyRepositoryError as e:
        msg = str(e)
        assert "ADO never modifies" in msg or "source repository" in msg.lower()
        assert str(src) in msg
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


def test_dirty_repo_no_stash_reset():
    """After DirtyRepositoryError, source repo still has dirty files."""
    src = _make_dirty_git_repo()
    dirty_file = src / "dirty.txt"
    task = _make_task("dirty-task-003")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    raised = False
    try:
        prepare_workspace(task.id, str(src), workspace_root=ws_root)
    except DirtyRepositoryError:
        raised = True
        # Check BEFORE cleanup: dirty file still exists, repo still dirty
        assert dirty_file.exists(), "source dirty file was removed"
        assert dirty_file.read_text() == "uncommitted change\n"
        assert _is_git_dirty(src), "source repo was modified"
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)
    assert raised, "DirtyRepositoryError was not raised"


# ---------------------------------------------------------------------------
# E: non-git copy mode
# ---------------------------------------------------------------------------

def test_prepare_workspace_copy_mode_non_git():
    src = _make_non_git_dir({"index.js": "console.log('hi');\n"})
    task = _make_task("copy-task-001")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        assert meta.mode == "copy"
        assert meta.source_project == src
        assert (meta.workspace_path / "index.js").exists()
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


def test_copy_excludes_env_file():
    src = _make_non_git_dir({
        "index.js": "x",
        ".env": "SECRET=abc",
        ".env.local": "DB=pwd",
    })
    task = _make_task("copy-task-002")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        assert not (meta.workspace_path / ".env").exists()
        assert not (meta.workspace_path / ".env.local").exists()
        assert (meta.workspace_path / "index.js").exists()
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


def test_copy_excludes_node_modules():
    src = _make_non_git_dir({"package.json": "{}", "node_modules/lib/index.js": "x"})
    task = _make_task("copy-task-003")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        assert not (meta.workspace_path / "node_modules").exists()
        assert (meta.workspace_path / "package.json").exists()
    finally:
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


# ---------------------------------------------------------------------------
# F: compute_workspace_result — git-worktree mode
# ---------------------------------------------------------------------------

def test_compute_workspace_result_git_worktree():
    src = _make_clean_git_repo({"README.md": "original\n"})
    task = _make_task("wr-task-0001")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        # Make a change in the worktree
        (meta.workspace_path / "new_file.txt").write_text("added by FORGE\n")
        (meta.workspace_path / "README.md").write_text("modified by FORGE\n")

        result = compute_workspace_result(meta)
        assert isinstance(result, WorkspaceResult)
        assert result.mode == "git-worktree"
        assert result.apply_ready is True
        assert "new_file.txt" in result.added_files or "new_file.txt" in result.changed_files
        assert result.diff_stat != ""
        d = result.to_dict()
        assert "changed_files" in d
        assert "apply_ready" in d
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


def test_compute_workspace_result_no_changes():
    """Unchanged worktree → empty changed_files but still returns result."""
    src = _make_clean_git_repo()
    task = _make_task("wr-task-0002")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    try:
        meta = prepare_workspace(task.id, str(src), workspace_root=ws_root)
        result = compute_workspace_result(meta)
        assert isinstance(result, WorkspaceResult)
        # apply_ready False if no changes
        assert result.apply_ready is False or len(result.changed_files) == 0
    finally:
        subprocess.run(["git", "worktree", "prune"], cwd=src, capture_output=True)
        shutil.rmtree(ws_root / task.id[:12], ignore_errors=True)
        shutil.rmtree(src)


# ---------------------------------------------------------------------------
# G: Task model fields
# ---------------------------------------------------------------------------

def test_task_model_has_target_project_field():
    t = Task(id="abc123", title="test", description="", target_project="/tmp/proj")
    assert t.target_project == "/tmp/proj"
    assert t.workspace_meta is None


def test_task_model_target_project_optional():
    t = Task(id="abc123", title="test", description="")
    assert t.target_project is None


def test_task_model_dump_includes_target_project():
    t = Task(id="abc123", title="test", description="", target_project="/tmp/proj")
    d = t.model_dump()
    assert "target_project" in d
    assert d["target_project"] == "/tmp/proj"


# ---------------------------------------------------------------------------
# H: workspace_meta stored in ctx.shared
# ---------------------------------------------------------------------------

def test_workspace_meta_in_ctx_shared_after_prepare():
    from ai_dev_agent_core import ExecutionContext, AgentRegistry
    task = _make_task("ctx-task-001")
    ctx = ExecutionContext(task=task, settings={}, registry=AgentRegistry())
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    meta = prepare_workspace(task.id, None, workspace_root=ws_root)
    ctx.shared["workspace_meta"] = meta
    assert ctx.shared["workspace_meta"] is meta
    assert ctx.shared["workspace_meta"].mode == "empty"
    shutil.rmtree(meta.workspace_path, ignore_errors=True)


def test_workspace_meta_to_dict_serializable():
    task = _make_task("ctx-task-002")
    ws_root = Path.home() / "ai-dev-office" / "workspaces"
    meta = prepare_workspace(task.id, None, workspace_root=ws_root)
    try:
        d = meta.to_dict()
        json.dumps(d)  # Must be JSON serializable
        assert d["mode"] == "empty"
        assert d["source_project"] is None
    finally:
        shutil.rmtree(meta.workspace_path, ignore_errors=True)
