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

Phase 3.5b — Local Target Project Isolation:
When a task includes a target_project path, this module prepares the workspace
by either:
  - git-worktree: creating an isolated detached git worktree inside the task
    workspace (source repo is NEVER touched — no stash/reset/checkout).
  - copy: doing a bounded safe copy of the source tree into the task workspace
    (excludes .git, node_modules, .next, build artifacts, secrets).
  - empty: legacy mode — no source project, blank workspace.

All agents read workspace metadata from ctx.shared["workspace_meta"] which
is the single source of truth for the current task's project context.

Safety rules enforced by this module:
- workspace_root must be under the repo root or an explicit override.
- The repo root itself (~/.hermes/, ~/.ssh/, etc.) is NEVER a workspace.
- Workspace paths are validated before any agent mounts or reads them.
- Dirty git repos are REJECTED before any specialist runs (no stash/reset).
- Cleanup is explicit and opt-in; never implicit during live execution.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Literal, NamedTuple

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

# Paths to exclude when doing a safe copy from a non-git project.
_COPY_EXCLUDE_DIRS = frozenset({
    ".git", "node_modules", ".next", "dist", "build", "out",
    "coverage", "__pycache__", ".venv", "venv", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".tox", "target",
})
_COPY_EXCLUDE_NAMES = frozenset({
    ".env", ".env.local", ".env.production", ".env.development",
    ".envrc", "credentials", "secrets.json", "secrets.yaml",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
_COPY_EXCLUDE_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".crt"})

# Paths that must never be accepted as target_project.
_FORBIDDEN_TARGET_PREFIXES: tuple[str, ...] = (
    str(Path.home() / ".ssh"),
    str(Path.home() / ".gnupg"),
    str(Path.home() / ".hermes"),
    "/etc",
    "/boot",
    "/root",
    "/proc",
    "/sys",
)

WorkspaceMode = Literal["git-worktree", "copy", "empty"]


class WorkspaceInfo(NamedTuple):
    """All workspace paths for one task, resolved from a single root."""

    task_id: str
    root: Path            # workspace_root (shared parent)
    path: Path            # actual task workspace: root / task_id[:12]
    runtime: Path         # Hermes runtime state: root / .ado-runtime / task_id[:12]
    sandbox_home: Path    # synthetic HOME inside sandbox


class WorkspaceMeta:
    """Rich metadata about a prepared workspace — stored in ctx.shared.

    All agents read this instead of computing paths independently.
    This is the single source of truth for the current task's project context.
    """

    __slots__ = (
        "task_id", "workspace_path", "source_project", "mode",
        "source_head", "source_dirty", "excluded_paths",
    )

    def __init__(
        self,
        *,
        task_id: str,
        workspace_path: Path,
        source_project: Path | None,
        mode: WorkspaceMode,
        source_head: str | None = None,
        source_dirty: bool = False,
        excluded_paths: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.workspace_path = workspace_path
        self.source_project = source_project
        self.mode = mode
        self.source_head = source_head
        self.source_dirty = source_dirty
        self.excluded_paths = excluded_paths or []

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "workspace_path": str(self.workspace_path),
            "source_project": str(self.source_project) if self.source_project else None,
            "mode": self.mode,
            "source_head": self.source_head,
            "source_dirty": self.source_dirty,
            "excluded_paths": self.excluded_paths,
        }


class WorkspaceResult:
    """Diff / review metadata produced after FORGE+QA execution.

    Populated by compute_workspace_result() and stored in
    ctx.shared["workspace_result"].
    """

    __slots__ = (
        "workspace_path", "source_project", "mode",
        "changed_files", "added_files", "modified_files", "deleted_files",
        "diff_stat", "apply_ready",
    )

    def __init__(
        self,
        *,
        workspace_path: Path,
        source_project: Path | None,
        mode: WorkspaceMode,
        changed_files: list[str],
        added_files: list[str],
        modified_files: list[str],
        deleted_files: list[str],
        diff_stat: str,
        apply_ready: bool,
    ) -> None:
        self.workspace_path = workspace_path
        self.source_project = source_project
        self.mode = mode
        self.changed_files = changed_files
        self.added_files = added_files
        self.modified_files = modified_files
        self.deleted_files = deleted_files
        self.diff_stat = diff_stat
        self.apply_ready = apply_ready

    def to_dict(self) -> dict:
        return {
            "workspace_path": str(self.workspace_path),
            "source_project": str(self.source_project) if self.source_project else None,
            "mode": self.mode,
            "changed_files": self.changed_files,
            "added_files": self.added_files,
            "modified_files": self.modified_files,
            "deleted_files": self.deleted_files,
            "diff_stat": self.diff_stat,
            "apply_ready": self.apply_ready,
        }


class WorkspaceValidationError(ValueError):
    """Raised when a workspace path fails safety validation."""


class DirtyRepositoryError(WorkspaceValidationError):
    """Raised when target_project has uncommitted changes.

    The source repo is left completely untouched — no stash, no reset.
    The user must commit or discard their changes before re-submitting.
    """


def default_workspace_root() -> Path:
    """Returns the default workspace root (matches current config default)."""
    return Path.home() / "ai-dev-office" / "workspaces"


# ─────────────────────────────────────────────────────────────────────────────
# Core path resolution (unchanged from Phase 3.5a)
# ─────────────────────────────────────────────────────────────────────────────

def resolve(task_id: str, workspace_root: Path | None = None) -> WorkspaceInfo:
    """Resolve all workspace paths for a task from a single root."""
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
    """Resolve and create the workspace directory."""
    info = resolve(task_id, workspace_root)
    info.path.mkdir(parents=True, exist_ok=True)
    return info


def validate_exists(info: WorkspaceInfo) -> None:
    """Raise WorkspaceValidationError if workspace does not exist."""
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
    """Remove task workspace and optionally its runtime directory."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.5b — Target project validation + workspace preparation
# ─────────────────────────────────────────────────────────────────────────────

def validate_target_project(raw_path: str) -> Path:
    """Validate and resolve a target_project path from user input.

    Applies expanduser, resolves to absolute path, checks existence,
    confirms it is a directory, and rejects forbidden system paths.

    Returns the resolved absolute Path.

    Raises:
        WorkspaceValidationError: with a clear user-facing message on failure.
    """
    if not raw_path or not raw_path.strip():
        raise WorkspaceValidationError("target_project cannot be empty")

    try:
        p = Path(raw_path).expanduser().resolve()
    except (TypeError, ValueError) as exc:
        raise WorkspaceValidationError(
            f"target_project is not a valid path: {raw_path!r}"
        ) from exc

    if not p.exists():
        raise WorkspaceValidationError(
            f"target_project does not exist: {p}"
        )

    if not p.is_dir():
        raise WorkspaceValidationError(
            f"target_project must be a directory, got file: {p}"
        )

    # Reject forbidden system paths.
    p_str = str(p)
    for forbidden in _FORBIDDEN_TARGET_PREFIXES:
        if p_str == forbidden or p_str.startswith(forbidden + "/"):
            raise WorkspaceValidationError(
                f"target_project {p} is in a forbidden system location"
            )

    return p


def prepare_workspace(
    task_id: str,
    target_project: str | None,
    workspace_root: Path | None = None,
) -> WorkspaceMeta:
    """Prepare an isolated task workspace from an optional target project.

    This is the single entry point for all workspace setup. Called once
    before any specialist agent runs. Result stored in ctx.shared["workspace_meta"].

    Modes:
        empty       — no target_project (legacy; blank workspace created).
        git-worktree — target is a clean git repo; isolated worktree created.
        copy        — target is non-git or an override; safe bounded copy.

    Args:
        task_id:         Task UUID hex string.
        target_project:  User-supplied path string (may be None).
        workspace_root:  Override workspace root (from settings).

    Returns:
        WorkspaceMeta describing the prepared workspace.

    Raises:
        WorkspaceValidationError: bad path, non-directory, forbidden location.
        DirtyRepositoryError: clean source repo required; user must commit first.
    """
    info = create(task_id, workspace_root)

    if not target_project:
        # Legacy: empty disposable workspace.
        return WorkspaceMeta(
            task_id=task_id,
            workspace_path=info.path,
            source_project=None,
            mode="empty",
        )

    src = validate_target_project(target_project)

    if _is_git_repo(src):
        # Reject dirty repos before any specialist work begins.
        if _is_git_dirty(src):
            raise DirtyRepositoryError(
                f"Target project has uncommitted changes: {src}\n"
                f"Commit or stash your changes, then re-submit the task.\n"
                f"ADO never modifies the source repository."
            )

        head = _git_head(src)
        worktree_path = _create_git_worktree(src, info.path, task_id)

        logger.info(
            "git worktree created for task %s: %s → %s (HEAD=%s)",
            task_id[:12], src, worktree_path, head[:8] if head else "?",
        )

        return WorkspaceMeta(
            task_id=task_id,
            workspace_path=worktree_path,
            source_project=src,
            mode="git-worktree",
            source_head=head,
            source_dirty=False,
        )

    else:
        # Non-git: safe bounded copy.
        excluded = _copy_project(src, info.path)

        logger.info(
            "Project copied for task %s: %s → %s (excluded: %s)",
            task_id[:12], src, info.path, excluded,
        )

        return WorkspaceMeta(
            task_id=task_id,
            workspace_path=info.path,
            source_project=src,
            mode="copy",
            excluded_paths=excluded,
        )


def setting_from(settings, name: str, default=None):
    """Read a setting from a dict or a settings object.

    ExecutionContext.settings is sometimes a plain dict (engine pipeline) and
    sometimes a settings object (tests, factories). This helper reads either.
    """
    if settings is None:
        return default
    if isinstance(settings, dict):
        return settings.get(name, default)
    return getattr(settings, name, default)


def workspace_root_from(settings) -> Path | None:
    """Extract the workspace root from ExecutionContext.settings.

    Returns None when not configured, which resolves to the shared default
    (``~/ai-dev-office/workspaces``).
    """
    root = setting_from(settings, "forge_workspace_root")
    return Path(root) if root is not None else None


def execution_workspace(
    task,
    ctx,
    workspace_root: Path | None = None,
) -> Path:
    """Return the authoritative execution directory for a task.

    ``workspace_meta.workspace_path`` — prepared once by the engine before any
    specialist runs — is the single source of truth. SCOUT, FORGE, and QA must
    all operate on this exact directory (the isolated git worktree or the
    copied project), so every agent observes the same project state.

    The legacy centralized resolution is used ONLY as a fallback when no
    workspace_meta exists: ``target_project=None`` legacy empty workspaces,
    old tests, and backwards compatibility.
    """
    shared = getattr(ctx, "shared", None) or {}
    meta = shared.get("workspace_meta")
    if meta is not None:
        return Path(meta.workspace_path).resolve()

    if workspace_root is None:
        workspace_root = workspace_root_from(getattr(ctx, "settings", None))
    return resolve(task.id, workspace_root=workspace_root).path


def cleanup_workspace_meta(
    meta: WorkspaceMeta,
    *,
    workspace_root: Path | None = None,
    keep_runtime: bool = False,
) -> bool:
    """Explicitly remove a prepared task workspace.

    ``git-worktree`` mode: uses ``git worktree remove --force`` on the source
    repo so no stale ``worktree`` registration remains under the source repo's
    ``.git/worktrees/`` — plain ``shutil.rmtree`` alone leaves that registry
    entry behind. ``copy``/``empty`` modes: plain ``rmtree``.

    Only ever invoked when cleanup is explicitly requested (``cleanup_workspace``
    setting). Never touches the source repo working tree contents, never
    resets/stashes, never deletes the source project, and never removes the
    Hermes runtime unless ``keep_runtime=False``.

    Failures are logged as warnings and do not raise.
    """
    removed = False

    if meta.mode == "git-worktree" and meta.source_project is not None:
        ws_path = Path(meta.workspace_path)
        src = Path(meta.source_project)
        rc, out, err = _run_git(
            ["worktree", "remove", "--force", str(ws_path)],
            src,
            timeout=30,
        )
        if rc != 0:
            logger.warning(
                "git worktree remove failed for task %s: %s",
                meta.task_id[:12],
                err or out,
            )
        else:
            removed = True
            logger.debug("git worktree removed for task %s", meta.task_id[:12])
        # Best-effort: drop any orphaned registration.
        _run_git(["worktree", "prune"], src)

    if workspace_root is None:
        workspace_root = workspace_root_from(None)
    info = resolve(meta.task_id, workspace_root=workspace_root)

    if info.path.exists():
        try:
            shutil.rmtree(info.path)
            removed = True
        except OSError as exc:
            logger.warning("Failed to remove workspace %s: %s", info.path, exc)

    if not keep_runtime and info.runtime.exists():
        try:
            shutil.rmtree(info.runtime)
            logger.debug("Runtime state removed: %s", info.runtime)
        except OSError as exc:
            logger.warning("Failed to remove runtime state %s: %s", info.runtime, exc)

    return removed


def compute_workspace_result(meta: WorkspaceMeta) -> WorkspaceResult:
    """Compute diff/review metadata after FORGE+QA execution.

    For git-worktree mode: runs git diff/status inside the isolated worktree
    to produce a real change summary (source repo is read-only, untouched).
    For copy/empty: lists modified files by comparing mtime vs workspace
    creation time (best-effort).

    Returns WorkspaceResult with structured change metadata.
    """
    ws = meta.workspace_path
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    diff_stat = ""
    apply_ready = False

    if meta.mode == "git-worktree" and ws.is_dir():
        added, modified, deleted = _git_status_changes(ws)
        diff_stat = _git_diff_stat(ws)
        apply_ready = bool(added or modified or deleted)

    elif meta.mode in ("copy", "empty") and ws.is_dir():
        # Best-effort: list all files in workspace as "added".
        files = [
            str(p.relative_to(ws))
            for p in ws.rglob("*")
            if p.is_file()
            and ".ado-runtime" not in p.parts
            and "__pycache__" not in p.parts
            and not p.name.endswith(".pyc")
        ]
        added = files
        diff_stat = f"{len(files)} file(s) in workspace"
        apply_ready = False  # No source repo to apply to.

    changed = sorted(set(added + modified + deleted))

    return WorkspaceResult(
        workspace_path=ws,
        source_project=meta.source_project,
        mode=meta.mode,
        changed_files=changed,
        added_files=added,
        modified_files=modified,
        deleted_files=deleted,
        diff_stat=diff_stat,
        apply_ready=apply_ready,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Git helpers — all read-only on source; worktree ops on workspace copy
# ─────────────────────────────────────────────────────────────────────────────

def _run_git(args: list[str], cwd: Path, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr).

    Only line endings are stripped — leading whitespace is significant for
    ``git status --porcelain`` (the first column carries the status flags).
    """
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.rstrip("\r\n"), r.stderr.rstrip("\r\n")
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return -1, "", str(exc)


def _is_git_repo(path: Path) -> bool:
    """True if path is inside a git repository."""
    rc, _, _ = _run_git(["rev-parse", "--git-dir"], path)
    return rc == 0


def _is_git_dirty(path: Path) -> bool:
    """True if the git repo has uncommitted changes (staged or unstaged).

    Read-only check — never modifies the repository.
    """
    rc, out, _ = _run_git(["status", "--porcelain"], path)
    if rc != 0:
        # If git status fails, treat as dirty to be safe.
        return True
    return bool(out.strip())


def _git_head(path: Path) -> str | None:
    """Return the current HEAD commit SHA (short). None on failure."""
    rc, out, _ = _run_git(["rev-parse", "HEAD"], path)
    return out[:40] if rc == 0 and out else None


def _create_git_worktree(src: Path, workspace_path: Path, task_id: str) -> Path:
    """Create a detached git worktree inside the task workspace.

    The worktree is placed at workspace_path/worktree/ so the workspace
    root can hold runtime metadata alongside it.

    Raises:
        WorkspaceValidationError: if worktree creation fails.
    """
    worktree_dir = workspace_path / "worktree"
    # Remove stale worktree dir if leftover from a previous attempt.
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir)

    # Remove from git's worktree registry if it got orphaned.
    _run_git(["worktree", "prune"], src)

    rc, out, err = _run_git(
        ["worktree", "add", "--detach", str(worktree_dir), "HEAD"],
        src,
        timeout=60,
    )

    if rc != 0:
        raise WorkspaceValidationError(
            f"Failed to create git worktree from {src}: {err or out}"
        )

    return worktree_dir


def _git_status_changes(ws: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (added, modified, deleted) file lists from git status."""
    rc, out, _ = _run_git(["status", "--porcelain"], ws)
    if rc != 0 or not out:
        return [], [], []

    added, modified, deleted = [], [], []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        xy = line[:2]
        # porcelain format: XY<space>filename (3 chars before filename)
        fname = line[3:].strip()
        # Handle rename: "R  old -> new" or "R  new\told"
        if " -> " in fname:
            fname = fname.split(" -> ")[-1].strip()
        elif "\t" in fname:
            fname = fname.split("\t")[-1].strip()
        if "?" in xy:
            added.append(fname)
        elif "D" in xy:
            deleted.append(fname)
        elif any(c in xy for c in ("M", "A", "R", "C", "U")):
            modified.append(fname)

    return added, modified, deleted


def _git_diff_stat(ws: Path) -> str:
    """Return a bounded git diff --stat summary."""
    rc, out, _ = _run_git(["diff", "--stat", "HEAD"], ws, timeout=15)
    if rc != 0 or not out:
        # Try untracked new files summary.
        rc2, out2, _ = _run_git(
            ["status", "--short"], ws, timeout=15
        )
        return out2[:500] if rc2 == 0 else ""
    return out[:500]


def _copy_project(src: Path, dest: Path) -> list[str]:
    """Copy src tree into dest, skipping noise and sensitive files.

    Returns list of excluded directory names.
    """
    excluded: list[str] = []

    def _should_skip(p: Path) -> bool:
        name = p.name
        if name in _COPY_EXCLUDE_DIRS:
            excluded.append(name)
            return True
        if name in _COPY_EXCLUDE_NAMES:
            excluded.append(name)
            return True
        if p.suffix.lower() in _COPY_EXCLUDE_SUFFIXES:
            excluded.append(name)
            return True
        if name.startswith(".env"):
            excluded.append(name)
            return True
        if name.startswith("credentials"):
            excluded.append(name)
            return True
        return False

    def _copy_tree(src_dir: Path, dst_dir: Path) -> None:
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in src_dir.iterdir():
            if _should_skip(item):
                continue
            dst = dst_dir / item.name
            if item.is_dir():
                _copy_tree(item, dst)
            elif item.is_file():
                try:
                    shutil.copy2(item, dst)
                except OSError as exc:
                    logger.warning("Skipping unreadable file %s: %s", item, exc)

    _copy_tree(src, dest)
    return list(set(excluded))


# ─────────────────────────────────────────────────────────────────────────────
# Internal validation
# ─────────────────────────────────────────────────────────────────────────────

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
        if forbidden_resolved in (Path.home(), Path("/")) and resolved == forbidden_resolved:
            raise WorkspaceValidationError(
                f"workspace_root {resolved} resolves to a forbidden path"
            )
    try:
        resolved.relative_to(Path.home())
    except ValueError:
        raise WorkspaceValidationError(
            f"workspace_root {resolved} must be under home directory "
            f"({Path.home()})"
        )
