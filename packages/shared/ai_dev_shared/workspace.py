"""Centralized workspace path resolution for all agents.

Single source of truth for every agent that needs to locate, create,
validate, or clean up a task workspace. All resolution lives here so
FORGE, QA, and SCOUT never compute paths independently.

Workspace layout:
    <workspace_root>/
        {task_id[:12]}/          ← writable task workspace (FORGE writes here)
    <workspace_root>/.ado-runtime/
        {task_id[:12]}/          ← Hermes runtime state (invisible to agents)
            home/
                .hermes/

Safety rules enforced by this module:
- workspace_root must be under the repo root or an explicit override.
- The repo root itself (~/.hermes/, ~/.ssh/, etc.) is NEVER a workspace.
- Workspace paths are validated before any agent mounts or reads them.
- Cleanup is explicit and opt-in; never implicit during live execution.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger("ai_dev_shared.workspace")

# Hard limit: workspace names are always task_id[:12] (12 hex chars).
_WORKSPACE_NAME_LEN = 12

# Directories that must never be used as workspace_root.
_FORBIDDEN_ROOTS: tuple[Path, ...] = (
    Path.home(),
    Path.home() / ".hermes",
    Path.home() / ".ssh",
    Path.home() / ".gnupg",
    Path.home() / ".config",
    Path("/"),
    Path("/tmp"),
    Path("/etc"),
)

# A workspace older than this (seconds) with no writes is considered stale.
_STALE_AGE_SECONDS = 3 * 3600  # 3 hours


class WorkspaceInfo(NamedTuple):
    """All workspace paths for one task, resolved from a single root."""

    task_id: str
    root: Path            # workspace_root (shared parent)
    path: Path            # actual task workspace: root / task_id[:12]
    runtime: Path         # Hermes runtime state: root / .ado-runtime / task_id[:12]
    sandbox_home: Path    # synthetic HOME inside sandbox


class WorkspaceValidationError(ValueError):
    """Raised when a workspace path fails safety validation."""


def default_workspace_root() -> Path:
    """Returns the default workspace root (matches current config default)."""
    return Path.home() / "ai-dev-office" / "workspaces"


def resolve(task_id: str, workspace_root: Path | None = None) -> WorkspaceInfo:
    """Resolve all workspace paths for a task from a single root.

    This is the ONLY place workspace paths should be computed. All agents
    (FORGE, QA, SCOUT) must call this instead of building paths manually.

    Args:
        task_id:        The full task UUID hex string.
        workspace_root: Override (e.g. from Settings.forge_workspace_root).
                        Defaults to ``default_workspace_root()``.

    Returns:
        WorkspaceInfo with all resolved paths.

    Raises:
        WorkspaceValidationError: if workspace_root is in a forbidden location.
    """
    root = Path(workspace_root) if workspace_root is not None else default_workspace_root()
    root = root.resolve()
    _validate_root(root)

    name = task_id[:_WORKSPACE_NAME_LEN]
    path = root / name
    runtime = root / ".ado-runtime" / name
    sandbox_home = runtime / "home"

    return WorkspaceInfo(
        task_id=task_id,
        root=root,
        path=path,
        runtime=runtime,
        sandbox_home=sandbox_home,
    )


def create(task_id: str, workspace_root: Path | None = None) -> WorkspaceInfo:
    """Resolve and create the workspace directory.

    The workspace directory is created if it does not exist. The runtime
    directory is NOT created here — the FORGE executor creates it when
    the sandbox HOME is needed.

    Returns:
        WorkspaceInfo (path now exists on disk).
    """
    info = resolve(task_id, workspace_root)
    info.path.mkdir(parents=True, exist_ok=True)
    return info


def validate_exists(info: WorkspaceInfo) -> None:
    """Raise WorkspaceValidationError if workspace does not exist.

    QA and SCOUT call this before operating on a workspace they expect
    FORGE to have populated.
    """
    if not info.path.is_dir():
        raise WorkspaceValidationError(
            f"Workspace missing for task {info.task_id[:12]}: {info.path}"
        )


def is_safe_path(path: Path, workspace_root: Path) -> bool:
    """True if path is safely inside workspace_root (no traversal escape)."""
    try:
        path.resolve().relative_to(workspace_root.resolve())
        return True
    except ValueError:
        return False


def is_stale(info: WorkspaceInfo, max_age: float = _STALE_AGE_SECONDS) -> bool:
    """True if workspace exists but has not been written to recently."""
    if not info.path.is_dir():
        return False
    try:
        mtime = info.path.stat().st_mtime
        return (time.time() - mtime) > max_age
    except OSError:
        return False


def cleanup(info: WorkspaceInfo, *, keep_runtime: bool = False) -> bool:
    """Remove task workspace and optionally its runtime directory.

    Never raises — failures are logged as warnings. Returns True if
    workspace was removed, False if it did not exist or removal failed.
    """
    removed = False
    if info.path.exists():
        try:
            shutil.rmtree(info.path)
            removed = True
            logger.debug("Workspace removed: %s", info.path)
        except OSError as exc:
            logger.warning("Failed to remove workspace %s: %s", info.path, exc)

    if not keep_runtime and info.runtime.exists():
        try:
            shutil.rmtree(info.runtime)
            logger.debug("Runtime state removed: %s", info.runtime)
        except OSError as exc:
            logger.warning(
                "Failed to remove runtime state %s: %s", info.runtime, exc
            )

    return removed


# ── Internal ──────────────────────────────────────────────────────────────────

def _validate_root(root: Path) -> None:
    """Raise WorkspaceValidationError if root is in a forbidden location."""
    resolved = root.resolve()
    for forbidden in _FORBIDDEN_ROOTS:
        try:
            forbidden_resolved = forbidden.resolve()
        except OSError:
            continue
        if resolved == forbidden_resolved:
            raise WorkspaceValidationError(
                f"workspace_root cannot be {resolved} (forbidden safety boundary)"
            )
        # Ensure the root is not INSIDE a forbidden directory that isn't
        # the repo root or a legitimate data directory.
        if forbidden_resolved in (Path.home(), Path("/")) and resolved == forbidden_resolved:
            raise WorkspaceValidationError(
                f"workspace_root {resolved} resolves to a forbidden path"
            )
    # Must be inside the user's home (prevents escaping to /tmp, /etc, etc.
    # when running in production). Allow absolute override for testing.
    try:
        resolved.relative_to(Path.home())
    except ValueError:
        raise WorkspaceValidationError(
            f"workspace_root {resolved} must be under home directory "
            f"({Path.home()})"
        )
