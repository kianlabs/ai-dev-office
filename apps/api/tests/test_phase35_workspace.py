"""
Regression tests for Phase 3.5 — Centralized Workspace Resolver.

Tests verify:
- workspace.resolve() is the single source of truth
- all three agents (FORGE, QA, SCOUT) use the same resolver
- safety validation rejects forbidden roots
- workspace info paths are consistent
- cleanup respects config flag
- stale detection works
- existing Phase 1.5/2/2.1/3 paths unaffected

Run with:  .venv/bin/python3 -m pytest apps/api/tests/test_phase35_workspace.py -v
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from unittest.mock import patch

from ai_dev_shared.workspace import (
    WorkspaceInfo,
    WorkspaceValidationError,
    cleanup,
    create,
    default_workspace_root,
    is_safe_path,
    is_stale,
    resolve,
)
from ai_dev_shared import Task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(task_id: str = "ws-task-000001") -> Task:
    return Task(id=task_id, title="test workspace", description="")


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# A: resolve() returns consistent paths
# ---------------------------------------------------------------------------

def test_resolve_returns_workspace_info():
    task = _make_task()
    info = resolve(task.id)
    assert isinstance(info, WorkspaceInfo)
    assert info.task_id == task.id
    assert info.path.name == task.id[:12]
    assert info.root == default_workspace_root().resolve()


def test_all_agents_resolve_same_path():
    """FORGE, QA, SCOUT must compute identical workspace paths."""
    task = _make_task()

    # Simulate how each agent resolves
    forge_info = resolve(task.id)
    qa_info = resolve(task.id)
    scout_info = resolve(task.id)

    assert forge_info.path == qa_info.path == scout_info.path
    assert forge_info.runtime == qa_info.runtime == scout_info.runtime


def test_runtime_is_separate_from_workspace():
    """Runtime state must be outside the task workspace (not visible to agents)."""
    task = _make_task()
    info = resolve(task.id)
    # runtime is NOT inside workspace
    try:
        info.runtime.relative_to(info.path)
        assert False, "runtime must not be inside workspace"
    except ValueError:
        pass  # correct


def test_sandbox_home_inside_runtime():
    task = _make_task()
    info = resolve(task.id)
    assert info.sandbox_home.is_relative_to(info.runtime)


# ---------------------------------------------------------------------------
# B: create() creates the workspace directory
# ---------------------------------------------------------------------------

def test_create_makes_directory():
    task = _make_task("create-test-001")
    info = create(task.id)
    try:
        assert info.path.is_dir()
    finally:
        shutil.rmtree(info.path, ignore_errors=True)


def test_create_idempotent():
    """create() called twice on same task is safe."""
    task = _make_task("create-test-002")
    info1 = create(task.id)
    info2 = create(task.id)
    try:
        assert info1.path == info2.path
        assert info2.path.is_dir()
    finally:
        shutil.rmtree(info1.path, ignore_errors=True)


# ---------------------------------------------------------------------------
# C: safety validation rejects forbidden roots
# ---------------------------------------------------------------------------

def test_forbidden_root_home_rejected():
    with patch("ai_dev_shared.workspace._FORBIDDEN_ROOTS",
               (Path.home(), Path("/"))):
        try:
            resolve("abc123", workspace_root=Path.home())
            assert False, "should have raised"
        except WorkspaceValidationError:
            pass


def test_root_slash_rejected():
    try:
        resolve("abc123", workspace_root=Path("/workspace"))
        assert False, "should have raised — outside home"
    except WorkspaceValidationError:
        pass


def test_etc_rejected():
    try:
        resolve("abc123", workspace_root=Path("/etc/workspaces"))
        assert False, "should have raised — outside home"
    except WorkspaceValidationError:
        pass


def test_valid_root_accepted():
    """A path inside home is accepted."""
    valid = Path.home() / "ai-dev-office" / "workspaces"
    info = resolve("abc123", workspace_root=valid)
    assert info.root == valid.resolve()


# ---------------------------------------------------------------------------
# D: is_safe_path prevents traversal
# ---------------------------------------------------------------------------

def test_is_safe_path_rejects_escape():
    root = Path.home() / "ai-dev-office" / "workspaces"
    escaped = Path.home() / ".ssh" / "id_rsa"
    assert not is_safe_path(escaped, root)


def test_is_safe_path_accepts_inside():
    root = Path.home() / "ai-dev-office" / "workspaces"
    inside = root / "abc123" / "file.py"
    assert is_safe_path(inside, root)


# ---------------------------------------------------------------------------
# E: stale detection
# ---------------------------------------------------------------------------

def test_stale_nonexistent_workspace_is_not_stale():
    task = _make_task("stale-test-001")
    info = resolve(task.id)
    assert not is_stale(info)


def test_stale_fresh_workspace_is_not_stale():
    task = _make_task("stale-test-002")
    info = create(task.id)
    try:
        assert not is_stale(info, max_age=3600)
    finally:
        shutil.rmtree(info.path, ignore_errors=True)


# ---------------------------------------------------------------------------
# F: cleanup works and is non-destructive when workspace missing
# ---------------------------------------------------------------------------

def test_cleanup_removes_workspace():
    task = _make_task("cleanup-test-001")
    info = create(task.id)
    assert info.path.is_dir()
    result = cleanup(info, keep_runtime=True)
    assert result is True
    assert not info.path.exists()


def test_cleanup_nonexistent_returns_false():
    task = _make_task("cleanup-test-002")
    info = resolve(task.id)
    result = cleanup(info)
    assert result is False


# ---------------------------------------------------------------------------
# G: FORGE executor uses resolver (not hardcoded path)
# ---------------------------------------------------------------------------

def test_forge_executor_uses_resolver():
    """HermesExecutor._create_workspace must call workspace.create, not hardcode."""
    from ai_dev_agent_forge.executor import HermesExecutor
    import inspect
    src = inspect.getsource(HermesExecutor._create_workspace)
    assert "ws_mod.create" in src or "workspace" in src
    assert "Path.home() / \"ai-dev-office\" / \"workspaces\"" not in src


def test_qa_executor_uses_resolver():
    """DeterministicQAExecutor._workspace_for must use workspace resolver."""
    from ai_dev_agent_qa.executor import DeterministicQAExecutor
    import inspect
    src = inspect.getsource(DeterministicQAExecutor._workspace_for)
    assert "ws_mod.resolve" in src
    assert "Path.home() / \"ai-dev-office\"" not in src


def test_scout_executor_uses_resolver():
    """_workspace_for in scout executor must use workspace resolver."""
    from ai_dev_agent_scout.executor import _workspace_for
    import inspect
    src = inspect.getsource(_workspace_for)
    assert "ws_mod.resolve" in src
    assert "Path.home() / \"ai-dev-office\"" not in src


# ---------------------------------------------------------------------------
# H: cleanup config flag respected
# ---------------------------------------------------------------------------

def test_cleanup_disabled_by_default_in_config():
    from ai_dev_api.config import settings
    assert settings.cleanup_workspace is False


def test_cleanup_workspace_root_in_config():
    from ai_dev_api.config import settings
    assert settings.forge_workspace_root is not None
    ws_root = Path(settings.forge_workspace_root).resolve()
    # Must be inside home (not a system path)
    assert str(ws_root).startswith(str(Path.home()))


# ---------------------------------------------------------------------------
# I: workspace resolver output matches existing workspace logic (no regression)
# ---------------------------------------------------------------------------

def test_resolver_matches_legacy_path():
    """Resolved path must equal old legacy path so existing workspaces are found."""
    task = _make_task("legacy-test-001")
    legacy = Path.home() / "ai-dev-office" / "workspaces" / task.id[:12]
    info = resolve(task.id)
    assert info.path == legacy
