"""Real HermesExecutor for FORGE - Coding Agent.

This is a MINIMAL smoke integration that runs Hermes as a subprocess with bubblewrap isolation.
Filesystem isolation via bwrap, NOT network isolation.

Security status:
- Filesystem isolation: ACTIVE (bwrap)
- Network isolation: NONE (--share-net for API)
- Prompt restrictions: NOT security boundaries

Isolation properties:
- Workspace: writable (/workspace)
- ~/.ssh: NOT accessible
- ~/.gnupg: NOT accessible
- ~/.config: NOT accessible
- ~/ai-dev-office: NOT accessible
- Other home files: NOT accessible
- System paths: read-only
- Hermes config: required config exposed read-only
- Provider credential: only the required provider key is passed via environment
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import AgentStatus, EventKind, TaskStatus

# Global semaphore to enforce FORGE concurrency = 1
# Prevents multiple Hermes executions running simultaneously
_FORGE_SEMAPHORE = asyncio.Semaphore(1)

# Isolation configuration
BWRAP_PATH = "/usr/bin/bwrap"

HOST_HERMES_ROOT = Path.home() / ".hermes"
HOST_HERMES_AGENT = HOST_HERMES_ROOT / "hermes-agent"
HOST_HERMES_CONFIG = HOST_HERMES_ROOT / "config.yaml"

SANDBOX_HOME = "/home/forge"
SANDBOX_HERMES_HOME = f"{SANDBOX_HOME}/.hermes"

# Keep Hermes runtime at its original absolute location because the venv
# entrypoint/interpreter uses absolute paths and is not relocatable.
SANDBOX_HERMES_AGENT = "/home/k14n/.hermes/hermes-agent"
SANDBOX_HERMES_EXE = f"{SANDBOX_HERMES_AGENT}/venv/bin/hermes"


def _load_archkian_api_key() -> str:
    """Load only the credential required by the configured custom provider."""
    env_file = HOST_HERMES_ROOT / ".env"
    key_name = "HERMES_CUSTOM_LOCALHOST_20128_API_KEY"

    if not env_file.is_file():
        raise RuntimeError(f"Required Hermes env file not found: {env_file}")

    for raw_line in env_file.read_text().splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        name, value = line.split("=", 1)

        if name.strip() == key_name:
            value = value.strip().strip("\"'")
            if not value:
                break
            return value

    raise RuntimeError(f"{key_name} is not configured")


class HermesExecutor:
    """Bridges AgentExecutor contract to Hermes CLI subprocess.

    Each task runs in an isolated workspace directory.
    Hermes is invoked with -q (non-interactive) and --quiet flags.
    """

    agent_id = "forge"
    DEFAULT_TIMEOUT = 600  # 10 minutes

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.timeout = self.DEFAULT_TIMEOUT
        self._workspace: Path | None = None

    async def execute(
        self, task: Task, ctx: ExecutionContext
    ) -> AsyncIterator[AgentEvent]:
        """Execute task via Hermes CLI and stream AgentEvents."""
        from ai_dev_agent_core import MockRuntime

        # Create mock runtime for event helpers
        r = MockRuntime(task, ctx)
        r.agent_id = self.agent_id

        # Emit start event
        yield await r.tick(
            r.working("Initializing FORGE workspace", task_status=TaskStatus.RUNNING)
        )

        # Acquire semaphore to enforce FORGE concurrency = 1
        acquired = False
        try:
            # Try to acquire with timeout to report if blocked
            try:
                acquired = _FORGE_SEMAPHORE.locked()
                if acquired:
                    yield await r.tick(r.waiting("Waiting for FORGE slot (concurrency=1)"))

                async with _FORGE_SEMAPHORE:
                    # Create isolated workspace
                    self._workspace = await self._create_workspace(task)
                    yield await r.tick(
                        r.say(f"Workspace created: {self._workspace}")
                    )

                    # Build prompt with safety rules
                    prompt = self._build_prompt(task)
                    yield await r.tick(r.say("Task prompt prepared with workspace constraints"))

                    # Run Hermes
                    yield await r.tick(r.working("Starting Hermes agent process"))

                    result = await self._run_hermes(prompt, r)

                    if result["success"]:
                        yield await r.tick(r.say(f"Hermes completed: {result['output'][:200]}"))
                        yield await r.tick(r.idle("Idle"))
                        yield await r.tick(
                            r.result(TaskStatus.DONE, f"Task completed via Hermes: {result['output'][:500]}")
                        )
                    else:
                        yield await r.tick(r.say(f"Hermes failed: {result['error']}"))
                        yield await r.tick(r.failure("Hermes execution failed"))
                        yield await r.tick(
                            r.result(
                                TaskStatus.FAILED,
                                f"Hermes execution failed: {result['error']}",
                                meta={"error": result["error"]},
                            )
                        )

            except asyncio.TimeoutError:
                yield await r.tick(r.failure(f"Task timed out after {self.timeout}s"))
                yield await r.tick(
                    r.result(
                        TaskStatus.FAILED,
                        f"FORGE timeout after {self.timeout} seconds",
                        meta={"error": "timeout"},
                    )
                )
            except Exception as err:
                yield await r.tick(r.failure(f"Unexpected error: {err}"))
                yield await r.tick(
                    r.result(
                        TaskStatus.FAILED,
                        f"FORGE error: {err}",
                        meta={"error": str(err)},
                    )
                )
        finally:
            await self._cleanup_workspace()

    async def _create_workspace(self, task: Task) -> Path:
        """Create isolated workspace directory for this task."""
        workspace_root = Path.home() / "ai-dev-office" / "workspaces"
        workspace_root.mkdir(parents=True, exist_ok=True)

        # Use task ID for unique workspace
        workspace = workspace_root / task.id[:12]
        workspace.mkdir(exist_ok=True)

        return workspace

    def _build_prompt(self, task: Task) -> str:
        """Build Hermes prompt with workspace constraints.

        These prompt rules are defense-in-depth instructions only.
        Filesystem restrictions are enforced separately by bubblewrap.
        """
        return f"""You are FORGE, a coding agent working on a single task.

CRITICAL WORKSPACE CONSTRAINTS:
- Your sandbox working directory is exactly: /workspace
- Work ONLY inside /workspace
- Create and modify task files inside /workspace
- Prefer relative paths such as ./file.py
- Do NOT use the host path shown outside the sandbox
- Do NOT use sudo, systemctl, pacman, or other system commands
- Do NOT push to git, deploy, or modify remote systems
- Do NOT access ~/.ssh, .env files, or credentials
- Do NOT modify files outside /workspace
- Before reporting success, verify that requested files actually exist in /workspace
- Do not claim a file was created unless it exists on disk
- Return a SHORT final result summary (max 200 words)

TASK:
{task.title}

{task.description}

Complete this task inside your workspace, then provide a brief summary of what was done.
"""

    async def _run_hermes(
        self, prompt: str, runtime
    ) -> dict:
        """Run Hermes CLI as subprocess with bwrap filesystem isolation.

        Returns:
            {"success": bool, "output": str, "error": str}
        """
        if self._workspace is None:
            return {"success": False, "error": "No workspace created"}

        # Check bwrap is available
        if not Path(BWRAP_PATH).exists():
            return {"success": False, "error": f"bwrap not found at {BWRAP_PATH}"}

        # Verify the host Hermes installation and minimal configuration.
        hermes_path = shutil.which("hermes")
        if not hermes_path:
            return {"success": False, "error": "Hermes CLI not found in PATH"}

        # Hermes venv uses an absolute interpreter path. Resolve its real
        # Python runtime so the same path can be exposed read-only in bwrap.
        host_hermes_python = (
            HOST_HERMES_AGENT / "venv" / "bin" / "python3"
        ).resolve()

        # UV keeps version aliases (for example cpython-3.11-...) beside the
        # resolved version directory. Mount the Python store so absolute
        # symlinks inside the Hermes venv continue to resolve in the sandbox.
        host_uv_python_store = Path.home() / ".local" / "share" / "uv" / "python"

        required_paths = (
            HOST_HERMES_AGENT,
            HOST_HERMES_CONFIG,
            host_hermes_python,
            host_uv_python_store,
        )
        missing = [str(path) for path in required_paths if not path.exists()]
        if missing:
            return {
                "success": False,
                "error": f"Required Hermes path missing: {', '.join(missing)}",
            }

        # Keep Hermes runtime state outside the task workspace so FORGE
        # cannot inspect it through /workspace.
        runtime_root = self._workspace.parent / ".ado-runtime" / self._workspace.name
        sandbox_home = runtime_root / "home"
        sandbox_hermes_home = sandbox_home / ".hermes"
        sandbox_hermes_home.mkdir(parents=True, exist_ok=True)

        try:
            archkian_api_key = _load_archkian_api_key()

            # Build bwrap command for filesystem isolation
            # Key principle: workspace writable, system/hermes read-only, home blocked
            bwrap_cmd = [
                BWRAP_PATH,
                "--unshare-all",
                "--share-net",  # Provider API requires network access.

                # Do not leak the parent/backend environment into FORGE.
                # Required variables are explicitly allowlisted below.
                "--clearenv",

                # Task workspace is the only project data exposed read/write.
                "--bind", str(self._workspace), "/workspace",

                # Minimal synthetic writable HOME for Hermes runtime state.
                "--dir", "/home",
                "--bind", str(sandbox_home), SANDBOX_HOME,

                # Empty parent directories for the original absolute
                # Hermes/venv paths. No other host HOME content is mounted.
                "--dir", "/home/k14n",
                "--dir", "/home/k14n/.hermes",

                # Hermes application/runtime is visible but immutable at its
                # original absolute path because its venv is not relocatable.
                "--ro-bind",
                str(HOST_HERMES_AGENT),
                SANDBOX_HERMES_AGENT,

                # The venv's Python may resolve into ~/.local/share/uv.
                # Expose only that resolved Python runtime, read-only.
                "--dir", "/home/k14n/.local",
                "--dir", "/home/k14n/.local/share",
                "--dir", "/home/k14n/.local/share/uv",
                "--ro-bind",
                str(host_uv_python_store),
                "/home/k14n/.local/share/uv/python",

                # Expose only provider configuration required by this setup.
                "--ro-bind",
                str(HOST_HERMES_CONFIG),
                f"{SANDBOX_HERMES_HOME}/config.yaml",

                # System runtime.
                "--ro-bind", "/usr", "/usr",
                "--ro-bind", "/lib", "/lib",
                "--ro-bind", "/lib64", "/lib64",
                "--ro-bind", "/bin", "/bin",
                "--ro-bind", "/etc", "/etc",
                "--proc", "/proc",
                "--dev", "/dev",
                "--tmpfs", "/tmp",

                # Prevent Hermes from resolving the real user's HOME.
                "--setenv", "HOME", SANDBOX_HOME,
                "--setenv", "USER", "forge",
                "--setenv", "LOGNAME", "forge",
                "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
                "--setenv", "LANG", "C.UTF-8",
                "--setenv",
                "HERMES_CUSTOM_LOCALHOST_20128_API_KEY",
                archkian_api_key,

                "--chdir", "/workspace",

                SANDBOX_HERMES_EXE,
                "chat",
                "-q",
                prompt,
                "--quiet",
                "-m", "kr/glm-5",
                "--provider", "custom:archkian",
            ]

            proc = await asyncio.create_subprocess_exec(
                *bwrap_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                # Kill the whole sandbox process group so Hermes/tool children
                # cannot survive after the bwrap parent is terminated.
                import os
                import signal

                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

                await proc.wait()
                raise

            output = stdout.decode("utf-8", errors="replace").strip()
            error = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode == 0:
                return {"success": True, "output": output, "error": ""}
            else:
                return {
                    "success": False,
                    "output": output,
                    "error": error or f"Exit code {proc.returncode}",
                }

        except FileNotFoundError:
            return {"success": False, "error": "Hermes executable not found"}
        except Exception as err:
            return {"success": False, "error": str(err)}

    async def _cleanup_workspace(self) -> None:
        """Remove workspace after task completion.

        Note: We keep workspace for debugging in smoke test.
        In production, this should clean up.
        """
        # For smoke test, keep workspace for inspection
        # In production: shutil.rmtree(self._workspace, ignore_errors=True)
        pass
