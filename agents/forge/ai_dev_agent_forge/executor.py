"""
Real HermesExecutor for FORGE - Coding Agent.

NON-BLOCKING VERSION with realtime streaming and cancellation support.

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

Changes from blocking version:
- Streams stdout/stderr in realtime
- Yields intermediate progress events
- Supports cancellation via cancel_event
- Non-blocking event loop
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import time
from pathlib import Path
from typing import AsyncIterator, TypedDict

from ai_dev_agent_core import ExecutionContext
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import AgentStatus, EventKind, TaskStatus

# Default heartbeat interval (seconds) for periods with no real activity.
DEFAULT_HEARTBEAT_INTERVAL = 15

logger = logging.getLogger("ai_dev_agent_forge")

# Lines Hermes emits that are NOT task progress and must not pollute the
# user-facing feed. The tirith warning is an internal security-scanner notice;
# the pattern-matching fallback it describes stays active (we never disable
# the sandbox), we just don't echo the notice as FORGE progress.
_TIRITH_NOISE = "tirith security scanner enabled but not available"

# FORGE must not take ownership of the QA / verification stage. These phrases
# indicate Hermes narrated a QA-style conclusion; since QA is the source of
# truth for PASS/FAIL/NOT_VERIFIED, such lines are excluded from the
# user-facing completion summary (the raw output is still preserved backend-side).
_QA_CLAIM_PATTERNS = (
    "hasil qa",
    "qa pass",
    "qa fail",
    "qa gate",
    "qa verified",
    "qa selesai",
    "semua test",
    "all tests passed",
    "test passed",
    "test lolos",
    "verifikasi dilakukan",
    "verification complete",
    "verification passed",
    # Verification-stage claims Hermes sometimes appends to its summary.
    "verifikasi",
    "verification",
    "unit tests",
    "berhasil dijalankan",
    "lolos syntax",
    "syntax check",
    "passed",
    "lolos",
)


class _ForgeResult(TypedDict):
    success: bool
    summary: str
    changed_files: list[str]
    commands: list[str]
    warnings: list[str]
    error: str
    raw_output: str
    raw_error: str

# Global semaphore to enforce FORGE concurrency = 1
# Prevents multiple Hermes executions running simultaneously
_FORGE_SEMAPHORE = asyncio.Semaphore(1)

# Global execution registry for cancellation
_RUNNING_PROCESSES: dict[str, asyncio.subprocess.Process] = {}

# Shared cancel events so cancel_task_execution() can signal the running
# executor, not just SIGTERM the OS process (so the executor reports
# INTERRUPTED instead of FAILED when cancelled).
_RUNNING_CANCEL_EVENTS: dict[str, asyncio.Event] = {}

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

    NON-BLOCKING VERSION:
    - Streams stdout/stderr in realtime
    - Yields intermediate progress events
    - Supports cancellation via cancel_event
    - Process tracked in global registry for cancellation
    """

    agent_id = "forge"
    DEFAULT_TIMEOUT = 600  # 10 minutes

    def __init__(
        self,
        task: Task,
        ctx: ExecutionContext,
        *,
        model: str = "",
        provider: str = "",
        max_turns: int = 12,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
    ) -> None:
        self.task = task
        self.ctx = ctx
        self.timeout = self.DEFAULT_TIMEOUT
        # Model resolution precedence: explicit AI Dev Office override ->
        # Hermes configured default (used when both are empty) -> fail honestly.
        # FORGE must never hardcode a model/provider here.
        self.model = model
        self.provider = provider
        self.max_turns = max_turns
        self.heartbeat_interval = max(1, int(heartbeat_interval))
        self._workspace: Path | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._cancel_event = asyncio.Event()

    async def execute(
        self, task: Task, ctx: ExecutionContext
    ) -> AsyncIterator[AgentEvent]:
        """Execute task via Hermes CLI and stream AgentEvents in realtime."""
        from ai_dev_agent_core import MockRuntime

        # Create mock runtime for event helpers
        r = MockRuntime(task, ctx)
        r.agent_id = self.agent_id

        # Register cancel event so external cancel_task_execution() can signal us
        _RUNNING_CANCEL_EVENTS[task.id] = self._cancel_event

        # Emit start event
        yield await r.tick(
            r.working("Initializing FORGE workspace", task_status=TaskStatus.RUNNING)
        )

        # Safely report resolved model/provider (no secrets). Empty values
        # mean Hermes will use its configured default from config.yaml.
        resolved_model = self.model or "hermes-config-default"
        resolved_provider = self.provider or "hermes-config-default"
        yield await r.tick(
            r.say(
                f"FORGE model={resolved_model} provider={resolved_provider} "
                f"max_turns={self.max_turns}"
            )
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

                    # Run Hermes with realtime streaming
                    yield await r.tick(r.working("Starting Hermes agent process"))

                    async for event in self._run_hermes_streaming(prompt, r):
                        yield event

            except asyncio.TimeoutError:
                yield await r.tick(r.failure(f"Task timed out after {self.timeout}s"))
                yield await r.tick(
                    r.result(
                        TaskStatus.FAILED,
                        f"FORGE timeout after {self.timeout} seconds",
                        meta={"error": "timeout"},
                    )
                )
            except asyncio.CancelledError:
                yield await r.tick(r.failure("Task cancelled by user"))
                yield await r.tick(
                    r.result(
                        TaskStatus.INTERRUPTED,
                        "Task cancelled by user",
                        meta={"error": "cancelled"},
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
            # Cleanup process from registry
            if task.id in _RUNNING_PROCESSES:
                del _RUNNING_PROCESSES[task.id]
            if task.id in _RUNNING_CANCEL_EVENTS:
                del _RUNNING_CANCEL_EVENTS[task.id]
            await self._cleanup_workspace()

    async def _create_workspace(self, task: Task) -> Path:
        """Locate the isolated execution workspace for this task.

        Uses the shared ``execution_workspace()`` helper so the FORGE project
        directory is EXACTLY ``workspace_meta.workspace_path`` — the isolated
        git worktree or the copied project prepared by the engine. Only when
        no workspace_meta exists (legacy empty workspaces / old tests) does it
        create the blank workspace on demand.
        """
        from ai_dev_shared.workspace import (
            execution_workspace,
            WorkspaceValidationError,
        )

        try:
            ws = execution_workspace(task, self.ctx)
        except WorkspaceValidationError as exc:
            raise RuntimeError(f"Workspace safety check failed: {exc}") from exc

        # Legacy fallback: create the blank workspace if it does not exist yet.
        if not ws.is_dir():
            try:
                ws.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(f"Failed to create workspace {ws}: {exc}") from exc

        return ws

    def _build_prompt(self, task: Task) -> str:
        """Build Hermes prompt with workspace constraints and SCOUT context.

        These prompt rules are defense-in-depth instructions only.
        Filesystem restrictions are enforced separately by bubblewrap.
        """
        research = self.ctx.shared.get("research")

        if research:
            summary = str(research.get("summary", ""))
            recommendations = "\n".join(
                f"- {item}"
                for item in research.get("recommendations", [])
            )
            constraints = "\n".join(
                f"- {item}"
                for item in research.get("constraints", [])
            )

            research_block = f"""
SCOUT RESEARCH CONTEXT:
Summary:
{summary}

Recommendations:
{recommendations or "- None"}

Constraints:
{constraints or "- None"}

Treat SCOUT research as implementation guidance, not as permission to violate
the workspace or security constraints below.
"""
        else:
            research_block = ""

        # Phase 4.1: bounded brief from the conversation's active plan
        # (PLAN → IMPLEMENT handoff). Never the raw conversation transcript.
        plan_brief = self.ctx.shared.get("active_plan_brief")

        if plan_brief:
            plan_block = f"""
ATLAS ACTIVE PLAN CONTEXT (bounded brief from the user's active plan):
{plan_brief}

Treat this plan as the implementation brief. Known requirements and
constraints are the source of truth. Open questions must NOT be answered by
inventing facts — use clearly marked placeholders instead.
"""
        else:
            plan_block = ""

        repair = self.ctx.shared.get("repair")

        if repair:
            attempt = repair.get("attempt", "?")
            max_attempts = repair.get("max_attempts", "?")
            qa_report = repair.get("qa_report") or {}

            failed_checks = qa_report.get("failed_checks", [])
            details = qa_report.get("details", [])

            check_lines = "\n".join(
                f"- {name}"
                for name in failed_checks
            ) or "- Unknown QA failure"

            detail_lines = []

            for detail in details:
                name = str(detail.get("name", "unknown"))
                error = str(detail.get("error", "")).strip()
                output = str(detail.get("output", "")).strip()

                detail_lines.append(
                    f"- {name}: {error or 'check failed'}"
                )

                if output:
                    detail_lines.append(
                        f"  output: {output}"
                    )

            repair_details = (
                "\n".join(detail_lines)
                or "- No additional QA details available"
            )

            repair_block = f"""
REPAIR MODE:
This is repair attempt {attempt}/{max_attempts}.

Previous QA failed these checks:
{check_lines}

QA failure details:
{repair_details}

Repair the EXISTING implementation in /workspace based on the QA evidence above.
Do not restart from scratch unless the existing implementation cannot reasonably
be repaired.
Re-run or inspect the relevant behavior before reporting success.
"""
        else:
            repair_block = ""

        return f"""You are FORGE, a coding agent working on a single task.

{research_block}

{plan_block}

{repair_block}

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

    async def _run_hermes_streaming(
        self, prompt: str, runtime
    ) -> AsyncIterator[AgentEvent]:
        """Run Hermes CLI with realtime stdout/stderr streaming.

        Yields intermediate progress events as output arrives.
        Supports cancellation via cancel_event.
        """
        import os
        import signal

        r = runtime

        if self._workspace is None:
            yield await r.tick(r.failure("No workspace created"))
            yield await r.tick(r.result(TaskStatus.FAILED, "No workspace created"))
            return

        # Check bwrap is available
        if not Path(BWRAP_PATH).exists():
            yield await r.tick(r.failure(f"bwrap not found at {BWRAP_PATH}"))
            yield await r.tick(r.result(TaskStatus.FAILED, f"bwrap not found at {BWRAP_PATH}"))
            return

        # Verify the host Hermes installation and minimal configuration.
        hermes_path = shutil.which("hermes")
        if not hermes_path:
            yield await r.tick(r.failure("Hermes CLI not found in PATH"))
            yield await r.tick(r.result(TaskStatus.FAILED, "Hermes CLI not found in PATH"))
            return

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
            error_msg = f"Required Hermes path missing: {', '.join(missing)}"
            yield await r.tick(r.failure(error_msg))
            yield await r.tick(r.result(TaskStatus.FAILED, error_msg))
            return

        # Keep Hermes runtime state outside the task workspace so FORGE
        # cannot inspect it through /workspace. Use the centralized resolver
        # so the runtime path is always consistent with the workspace path.
        from ai_dev_shared import workspace as ws_mod
        from ai_dev_shared.workspace import workspace_root_from
        ws_info = ws_mod.resolve(
            self.task.id,
            workspace_root=workspace_root_from(self.ctx.settings),
        )
        sandbox_home = ws_info.sandbox_home
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

                # Model/provider resolution precedence:
                #   1. Explicit AI Dev Office override (self.model / self.provider)
                #   2. Hermes configured default (config.yaml) -> omit both flags
                # Hermes CLI uses its config.yaml default when neither is given.
                *(["-m", self.model] if self.model else []),
                *(["--provider", self.provider] if self.provider else []),
                "--max-turns", str(self.max_turns),
            ]

            proc = await asyncio.create_subprocess_exec(
                *bwrap_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )

            # Register process for cancellation
            self._process = proc
            _RUNNING_PROCESSES[self.task.id] = proc

            # Stream stdout in realtime
            output_lines = []
            error_lines = []

            async def read_stdout():
                """Read stdout line by line."""
                if proc.stdout is None:
                    return
                try:
                    async for line in proc.stdout:
                        text = line.decode("utf-8", errors="replace").strip()
                        if text:
                            output_lines.append(text)
                except Exception:
                    pass

            async def read_stderr():
                """Read stderr line by line."""
                if proc.stderr is None:
                    return
                try:
                    async for line in proc.stderr:
                        text = line.decode("utf-8", errors="replace").strip()
                        if text:
                            error_lines.append(text)
                            # Yield stderr as progress (warnings, etc.) but
                            # never surface the internal tirith notice as FORGE
                            # progress — it is logged once at completion instead.
                            if not text.startswith("⚠") and not self._is_noise_line(text):
                                yield await r.tick(r.say(f"[stderr] {text[:100]}"))
                except Exception:
                    pass

            # Run both readers concurrently
            stdout_task = asyncio.create_task(read_stdout())

            # Wait for process with timeout, checking cancel event
            start_time = time.time()

            while proc.returncode is None:
                # Check cancellation
                if self._cancel_event.is_set():
                    yield await r.tick(r.say("Cancellation requested, terminating process..."))
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                        await asyncio.sleep(0.5)
                        if proc.returncode is None:
                            os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await proc.wait()
                    yield await r.tick(r.failure("Task cancelled by user"))
                    yield await r.tick(r.result(TaskStatus.INTERRUPTED, "Task cancelled by user"))
                    return

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > self.timeout:
                    yield await r.tick(r.say(f"Timeout ({self.timeout}s), terminating process..."))
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await proc.wait()
                    raise asyncio.TimeoutError()

                # Yield periodic heartbeat only when there is no real activity,
                # at the configured interval (default 15s) — not 5s spam.
                if int(elapsed) > 0 and int(elapsed) % self.heartbeat_interval == 0:
                    yield await r.tick(
                        r.say(f"Sedang mengerjakan... ({int(elapsed)}s)")
                    )

                # Wait a bit before checking again
                await asyncio.sleep(0.1)

            # Wait for stdout reader to finish
            await stdout_task

            # If cancellation was requested, report INTERRUPTED regardless of
            # how the process exited (SIGTERM looks like a non-zero returncode).
            if self._cancel_event.is_set():
                yield await r.tick(r.failure("Task cancelled by user"))
                yield await r.tick(
                    r.result(TaskStatus.INTERRUPTED, "Task cancelled by user")
                )
                return

            # Collect final output
            output = "\n".join(output_lines)
            error = "\n".join(error_lines)

            success = proc.returncode == 0
            result = self._build_forge_result(output, error, success)

            if success:
                # User-facing feed: concise implementation summary only.
                # QA ownership belongs to the QA stage, not FORGE.
                yield await r.tick(r.say(result["summary"]))
                yield await r.tick(r.idle("Idle"))
                yield await r.tick(
                    r.result(
                        TaskStatus.DONE,
                        result["summary"],
                        meta={
                            "forge_result": {
                                "success": result["success"],
                                "changed_files": result["changed_files"],
                                "commands": result["commands"],
                                "warnings": result["warnings"],
                                "error": result["error"],
                                "workspace_path": str(self._workspace),
                            },
                            # Full raw output preserved backend-side for
                            # ATLAS/QA evidence; never surfaced as feed text.
                            "forge_raw_output": result["raw_output"],
                        },
                    )
                )
            else:
                feed_error = result["error"] or "Hermes execution failed"
                yield await r.tick(r.say(f"Implementasi gagal: {feed_error[:300]}"))
                yield await r.tick(r.failure("Hermes execution failed"))
                yield await r.tick(
                    r.result(
                        TaskStatus.FAILED,
                        f"Implementasi gagal: {feed_error[:500]}",
                        meta={
                            "error": feed_error,
                            "forge_result": {
                                "success": result["success"],
                                "changed_files": result["changed_files"],
                                "commands": result["commands"],
                                "warnings": result["warnings"],
                                "error": result["error"],
                                "workspace_path": str(self._workspace),
                            },
                            "forge_raw_output": result["raw_output"],
                        },
                    )
                )

        except FileNotFoundError:
            yield await r.tick(r.failure("Hermes executable not found"))
            yield await r.tick(r.result(TaskStatus.FAILED, "Hermes executable not found"))
        except Exception as err:
            yield await r.tick(r.failure(f"Unexpected error: {err}"))
            yield await r.tick(r.result(TaskStatus.FAILED, f"FORGE error: {err}"))

    def request_cancel(self):
        """Request cancellation of the running Hermes process."""
        self._cancel_event.set()

    # ------------------------------------------------------------------ normalize
    @staticmethod
    def _is_noise_line(text: str) -> bool:
        """True if the line is internal noise (tirith notice) that should not
        be surfaced as FORGE task progress."""
        return _TIRITH_NOISE in text.lower()

    @staticmethod
    def _is_qa_claim_line(text: str) -> bool:
        """True if the line has FORGE narrating a QA/verification conclusion.
        FORGE must not own the QA stage, so such lines are excluded from the
        user-facing completion summary."""
        low = text.lower()
        return any(pat in low for pat in _QA_CLAIM_PATTERNS)

    def _real_changed_files(self) -> list[str]:
        """List files FORGE actually produced in the workspace (real evidence,
        not parsed from narrative). Excludes runtime state and build caches."""
        if self._workspace is None or not self._workspace.is_dir():
            return []
        files = [
            str(p.relative_to(self._workspace))
            for p in self._workspace.rglob("*")
            if p.is_file()
            and ".ado-runtime" not in p.parts
            and "__pycache__" not in p.parts
            and not p.name.endswith(".pyc")
        ]
        # Sort for stable output; bound to a reasonable number.
        files.sort()
        return files[:50]

    def _build_forge_result(
        self, output: str, error: str, success: bool
    ) -> _ForgeResult:
        """Normalize raw Hermes output into a concise, structured FORGE result.

        FORGE reports ONLY its own implementation work. QA-style conclusions and
        internal warnings are stripped from the user-facing summary. The full
        raw output is preserved backend-side in ``raw_output`` so ATLAS/QA can
        still receive relevant evidence without fabricating or altering facts.
        """
        # Drop internal noise (tirith) and QA-claim lines from the visible text.
        visible_lines: list[str] = []
        warnings: list[str] = []
        tirith_seen = False

        for raw in (output, error):
            for line in raw.splitlines():
                text = line.strip()
                if not text:
                    continue
                low = text.lower()
                if _TIRITH_NOISE in low:
                    if not tirith_seen:
                        tirith_seen = True
                        warnings.append(
                            "tirith scanner tidak tersedia — fallback pattern "
                            "matching tetap aktif (sandbox bwrap)"
                        )
                        logger.warning(
                            "tirith security scanner unavailable for task %s; "
                            "using pattern-matching fallback (sandbox intact)",
                            self.task.id,
                        )
                    continue
                if self._is_qa_claim_line(text):
                    continue
                visible_lines.append(text)

        # Concise implementation summary (bounded).
        summary_body = " ".join(visible_lines).strip()
        if len(summary_body) > 600:
            summary_body = summary_body[:600].rstrip() + "…"

        changed_files = self._real_changed_files()

        # Best-effort command evidence Hermes reported running. We look for
        # shell-prompt style lines ("$ cmd" / "> cmd", anywhere in the line)
        # or explicit tool invocations. Empty if not present — never invented.
        commands = []
        for line in visible_lines:
            m = re.search(r"[\$>]\s+(\S.*)", line)
            if m:
                commands.append(m.group(1).strip())
            elif re.match(
                r"^(npm|node|npx|python|python3|git|cargo|go|make|pytest|pnpm|yarn)\b",
                line,
            ):
                commands.append(line.strip())
        commands = commands[:10]

        heading = "Implementasi selesai." if success else "Implementasi gagal."
        if changed_files:
            file_block = "File berubah: " + ", ".join(changed_files)
        else:
            file_block = "Tidak ada file terdeteksi di workspace."

        summary = f"{heading} {file_block}"
        if summary_body:
            summary += f" {summary_body}"

        return {
            "success": success,
            "summary": summary,
            "changed_files": changed_files,
            "commands": commands,
            "warnings": warnings,
            "error": error.strip() if not success and error.strip() else "",
            "raw_output": output,
            "raw_error": error,
        }

    async def _cleanup_workspace(self) -> None:
        """Remove workspace after task completion if configured to do so.

        cleanup_workspace=True (via ADO_CLEANUP_WORKSPACE=true env) removes
        the task workspace after DONE/FAILED. Default is False so workspaces
        remain available for manual inspection. Cancelled workspaces are
        always kept regardless of the setting.
        """
        from ai_dev_shared import workspace as ws_mod
        from ai_dev_shared.workspace import (
            cleanup_workspace_meta,
            setting_from,
            workspace_root_from,
        )

        # Cancelled workspaces stay for inspection regardless of config.
        if self._cancel_event.is_set():
            return

        cleanup_enabled = setting_from(
            self.ctx.settings, "cleanup_workspace", False
        )
        if not cleanup_enabled:
            return

        try:
            meta = self.ctx.shared.get("workspace_meta")
            if meta is not None:
                cleanup_workspace_meta(
                    meta,
                    workspace_root=workspace_root_from(self.ctx.settings),
                )
                logger.debug(
                    "Workspace cleaned up after task %s", self.task.id[:12]
                )
            elif self._workspace is not None:
                ws_info = ws_mod.resolve(
                    self.task.id,
                    workspace_root=workspace_root_from(self.ctx.settings),
                )
                ws_mod.cleanup(ws_info)
                logger.debug(
                    "Workspace cleaned up after task %s", self.task.id[:12]
                )
        except Exception as exc:  # noqa: BLE001 - cleanup must never crash runtime
            logger.warning(
                "Workspace cleanup failed for task %s: %s",
                self.task.id[:12], exc,
            )


def cancel_task_execution(task_id: str) -> bool:
    """Cancel a running FORGE execution by task ID.

    Signals the executor's cancel event (so it reports INTERRUPTED, not
    FAILED) AND sends SIGTERM to the sandbox process group. Does NOT touch
    the global Hermes gateway — only the bwrap process group for this task.

    Returns True if a running execution was found and signalled, False if
    there was nothing to cancel.
    """
    proc = _RUNNING_PROCESSES.get(task_id)
    if proc is None:
        return False

    # Signal the executor coroutine so it yields INTERRUPTED cleanly.
    event = _RUNNING_CANCEL_EVENTS.get(task_id)
    if event is not None:
        event.set()

    import os
    import signal

    try:
        os.killpg(proc.pid, signal.SIGTERM)
        # Remove the handle so it cannot be double-cancelled and is cleaned
        # up even if the executor's own finally has not run yet.
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return True
    except ProcessLookupError:
        # Process already gone — clean up the stale handle.
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return False
    except Exception:
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return False
