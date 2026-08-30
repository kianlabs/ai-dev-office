"""Real deterministic QA executor.

QA verifies the workspace produced by FORGE using deterministic, project-derived
commands (never an LLM for PASS/FAIL). It runs in a read-only bubblewrap sandbox
so FORGE output cannot be mutated by QA.

PASS/FAIL is decided solely by real command exit codes. When no runnable check
can be detected, QA reports NOT_VERIFIED (never a fabricated PASS).

Security properties:
- workspace mounted read-only
- network namespace isolated (no --share-net; checks are local)
- parent environment cleared
- only predefined project scripts are executed (no arbitrary user-text commands)
- per-command timeout kills the sandbox process group
- a global cancel registry terminates only THIS task's QA subprocess
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import shutil
from pathlib import Path
from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import AgentStatus, EventKind, TaskStatus

BWRAP_PATH = "/usr/bin/bwrap"

# Enforce single QA execution at a time (matches FORGE concurrency model).
_QA_SEMAPHORE = asyncio.Semaphore(1)

# Cancellation registry: task_id -> running bwrap Process (QA-only).
_RUNNING_PROCESSES: dict[str, asyncio.subprocess.Process] = {}

# Bound on stdout/stderr bytes we keep/emit per check (avoid feed flooding).
_OUTPUT_LIMIT = 4000

# Per-command timeout (seconds). QA checks are local; keep them bounded.
_PER_COMMAND_TIMEOUT = 120


class DeterministicQAExecutor:
    agent_id = "qa"
    DEFAULT_TIMEOUT = 180

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.timeout = self.DEFAULT_TIMEOUT
        self._cancel_event = asyncio.Event()

    def _workspace_for(self, task: Task) -> Path:
        """Resolve the authoritative execution workspace.

        ``workspace_meta.workspace_path`` is the single source of truth so QA
        tests the EXACT isolated project FORGE wrote to (git worktree / copied
        project). The legacy resolver is only the fallback for
        ``target_project=None`` empty workspaces.
        """
        from ai_dev_shared.workspace import execution_workspace
        return execution_workspace(task, self.ctx)

    async def execute(
        self,
        task: Task,
        ctx: ExecutionContext,
    ) -> AsyncIterator[AgentEvent]:
        r = MockRuntime(task, ctx)
        r.agent_id = self.agent_id

        # Register cancel event so external cancel can signal us.
        from ai_dev_agent_qa.executor import _RUNNING_CANCEL_EVENTS
        _RUNNING_CANCEL_EVENTS[task.id] = self._cancel_event

        workspace = self._workspace_for(task)

        yield await r.tick(
            r.working(
                "Menguji...",
                task_status=TaskStatus.RUNNING,
            )
        )

        if not workspace.is_dir():
            qa_report = {
                "score": "FAIL",
                "verified": False,
                "failed_checks": ["workspace"],
                "details": [
                    {
                        "name": "workspace",
                        "error": f"workspace missing: {workspace}",
                        "output": "",
                    }
                ],
                "workspace_path": str(workspace),
            }
            ctx.shared["qa_report"] = qa_report
            yield await r.tick(
                r.qa_result(
                    "FAIL",
                    f"QA gate: FAIL — workspace missing: {workspace}",
                    meta={"qa_report": qa_report},
                )
            )
            yield await r.tick(r.idle("Idle"))
            return

        async with _QA_SEMAPHORE:
            checks = self._detect_checks(workspace)

            if not checks:
                # No runnable project checks detected. Per the QA contract we
                # must NOT fabricate a PASS. Verify the workspace is non-empty
                # and report NOT_VERIFIED.
                entries = [
                    p
                    for p in workspace.rglob("*")
                    if p.is_file() and ".ado-runtime" not in p.parts
                ]

                if entries:
                    yield await r.tick(
                        r.say(
                            f"Tidak ada skrip test/typecheck/lint yang terdeteksi; "
                            f"memverifikasi {len(entries)} berkas workspace"
                        )
                    )
                    qa_report = {
                        "score": "NOT_VERIFIED",
                        "verified": False,
                        "failed_checks": [],
                        "details": [],
                        "note": (
                            "No runnable deterministic checks detected in workspace"
                        ),
                        "workspace_path": str(workspace),
                    }
                    ctx.shared["qa_report"] = qa_report
                    yield await r.tick(
                        r.qa_result(
                            "NOT_VERIFIED",
                            "QA gate: NOT_VERIFIED — tidak ada check yang bisa "
                            "dijalankan (bukan PASS palsu)",
                            meta={"qa_report": qa_report},
                        )
                    )
                else:
                    qa_report = {
                        "score": "FAIL",
                        "verified": False,
                        "failed_checks": ["workspace-artifacts"],
                        "details": [
                            {
                                "name": "workspace-artifacts",
                                "error": "FORGE workspace is empty",
                                "output": "",
                            }
                        ],
                        "workspace_path": str(workspace),
                    }
                    ctx.shared["qa_report"] = qa_report
                    yield await r.tick(
                        r.qa_result(
                            "FAIL",
                            "QA gate: FAIL — FORGE workspace is empty",
                            meta={"qa_report": qa_report},
                        )
                    )

                yield await r.tick(r.idle("Idle"))
                return

            check_results: list[dict[str, object]] = []
            failures: list[dict[str, str]] = []

            for name, command in checks:
                if self._cancel_event.is_set():
                    break

                yield await r.tick(r.working(f"Menjalankan: {name}"))

                result = await self._run_check(workspace, command)

                passed = bool(result["success"])
                raw_code = result.get("exit_code", -1)
                exit_code = int(raw_code) if isinstance(raw_code, int) else -1
                summary = self._summarize(result)

                check_results.append(
                    {
                        "name": name,
                        "command": " ".join(command),
                        "exit_code": exit_code,
                        "passed": passed,
                        "summary": summary,
                    }
                )

                if passed:
                    yield await r.tick(
                        r.say(f"{name} selesai (exit {exit_code})")
                    )
                else:
                    failures.append(
                        {
                            "name": name,
                            "error": summary,
                            "output": result.get("output", "") or "",
                        }
                    )
                    yield await r.tick(
                        r.say(f"{name} gagal (exit {exit_code})")
                    )

            if self._cancel_event.is_set():
                qa_report = {
                    "score": "INTERRUPTED",
                    "verified": False,
                    "failed_checks": [f["name"] for f in failures],
                    "details": failures,
                    "checks": check_results,
                    "workspace_path": str(workspace),
                }
                ctx.shared["qa_report"] = qa_report
                yield await r.tick(r.failure("QA dibatalkan oleh user"))
                yield await r.tick(
                    r.qa_result(
                        "INTERRUPTED",
                        "QA gate: INTERRUPTED — dibatalkan oleh user",
                        meta={"qa_report": qa_report},
                    )
                )
                yield await r.tick(r.idle("Idle"))
                return

            overall_pass = not failures and bool(check_results)

            if failures:
                qa_report = {
                    "score": "FAIL",
                    "verified": True,
                    "overall_pass": False,
                    "failed_checks": [f["name"] for f in failures],
                    "details": failures,
                    "checks": check_results,
                    "workspace_path": str(workspace),
                }
                ctx.shared["qa_report"] = qa_report
                yield await r.tick(
                    r.qa_result(
                        "FAIL",
                        "QA gate: FAIL — failed checks: "
                        + ", ".join(qa_report["failed_checks"]),
                        meta={"qa_report": qa_report},
                    )
                )
            else:
                qa_report = {
                    "score": "PASS",
                    "verified": True,
                    "overall_pass": True,
                    "failed_checks": [],
                    "details": [],
                    "checks": check_results,
                    "workspace_path": str(workspace),
                }
                ctx.shared["qa_report"] = qa_report
                yield await r.tick(
                    r.qa_result(
                        "PASS",
                        "QA gate: PASS — semua check terdeteksi hijau",
                        meta={"qa_report": qa_report},
                    )
                )

            yield await r.tick(r.idle("Idle"))

    # ------------------------------------------------------------------ detect
    def _detect_checks(
        self,
        workspace: Path,
    ) -> list[tuple[str, list[str]]]:
        """Select only deterministic allowlisted checks derived from the
        project itself. No arbitrary user-text commands are ever run."""

        checks: list[tuple[str, list[str]]] = []

        package_json = workspace / "package.json"

        if package_json.is_file():
            try:
                data = json.loads(package_json.read_text())
            except (OSError, json.JSONDecodeError):
                # package.json present but unparseable -> a real syntax check.
                return [
                    (
                        "package-json",
                        [
                            "/usr/bin/node",
                            "-e",
                            (
                                "JSON.parse(require('fs')"
                                ".readFileSync('/workspace/package.json','utf8'))"
                            ),
                        ],
                    )
                ]

            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                npm = shutil.which("npm") or "/usr/bin/npm"

                # Prefer real, safe, project-defined checks. A missing script
                # is simply skipped — never fabricated.
                for script in ("test", "typecheck", "lint"):
                    if script in scripts:
                        checks.append(
                            (
                                script,
                                [npm, "run", script],
                            )
                        )

        # Basic syntax verification for plain Python workspaces.
        python_files = [
            p
            for p in workspace.rglob("*.py")
            if ".venv" not in p.parts
            and "node_modules" not in p.parts
        ]

        if python_files:
            checks.append(
                (
                    "python-syntax",
                    [
                        "/usr/bin/python",
                        "-c",
                        (
                            "import ast,pathlib;"
                            "files=list(pathlib.Path('/workspace').rglob('*.py'));"
                            "[ast.parse(p.read_text(),filename=str(p)) for p in files]"
                        ),
                    ],
                )
            )

        return checks

    # -------------------------------------------------------------------- run
    def _summarize(self, result: dict[str, object]) -> str:
        """Build a bounded, real summary from actual output/error."""
        out = str(result.get("output", "") or "")
        err = str(result.get("error", "") or "")
        text = (err or out).strip()
        if not text:
            return "no output"
        if len(text) > _OUTPUT_LIMIT:
            return text[-_OUTPUT_LIMIT:]
        return text

    async def _run_check(
        self,
        workspace: Path,
        command: list[str],
    ) -> dict[str, object]:
        if not Path(BWRAP_PATH).exists():
            return {
                "success": False,
                "exit_code": -1,
                "output": "",
                "error": "bubblewrap unavailable",
            }

        bwrap_cmd = [
            BWRAP_PATH,
            "--unshare-all",
            # QA must not reach the network; checks are local deterministic.
            "--clearenv",

            # FORGE output is immutable to QA (read-only).
            "--ro-bind",
            str(workspace),
            "/workspace",

            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/etc", "/etc",

            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",

            "--dir", "/home",
            "--dir", "/home/qa",

            "--setenv", "HOME", "/home/qa",
            "--setenv", "USER", "qa",
            "--setenv", "LOGNAME", "qa",
            "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
            "--setenv", "LANG", "C.UTF-8",

            "--chdir", "/workspace",

            *command,
        ]

        proc = await asyncio.create_subprocess_exec(
            *bwrap_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )

        # Register for cancellation (QA-only subprocess).
        _RUNNING_PROCESSES[self.task.id] = proc

        # Periodically check cancel; enforce per-command timeout.
        waiter = asyncio.ensure_future(proc.communicate())
        elapsed = 0.0
        tick = 0.2
        try:
            while not waiter.done():
                if self._cancel_event.is_set():
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                        await asyncio.sleep(0.3)
                        if not waiter.done():
                            os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await waiter
                    return {
                        "success": False,
                        "exit_code": -1,
                        "output": "",
                        "error": "QA check cancelled by user",
                    }

                await asyncio.sleep(tick)
                elapsed += tick
                if elapsed > _PER_COMMAND_TIMEOUT:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    await waiter
                    return {
                        "success": False,
                        "exit_code": -1,
                        "output": "",
                        "error": f"QA check timeout after {_PER_COMMAND_TIMEOUT}s",
                    }
        finally:
            _RUNNING_PROCESSES.pop(self.task.id, None)

        stdout, stderr = await waiter

        output = stdout.decode("utf-8", errors="replace").strip()
        error = stderr.decode("utf-8", errors="replace").strip()

        if len(output) > _OUTPUT_LIMIT:
            output = output[-_OUTPUT_LIMIT:]
        if len(error) > _OUTPUT_LIMIT:
            error = error[-_OUTPUT_LIMIT:]

        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode or 0,
            "output": output,
            "error": error or (
                "" if proc.returncode == 0 else f"exit code {proc.returncode}"
            ),
        }

    def request_cancel(self) -> None:
        self._cancel_event.set()


# Shared cancel registry (task_id -> asyncio.Event) for QA.
_RUNNING_CANCEL_EVENTS: dict[str, asyncio.Event] = {}


def cancel_qa_execution(task_id: str) -> bool:
    """Cancel a running QA bwrap subprocess for a task.

    Terminates ONLY this task's QA sandbox process group — never the global
    Hermes gateway or any FORGE process. Returns True if a QA process was
    found and signalled.
    """
    proc = _RUNNING_PROCESSES.get(task_id)
    if proc is None:
        return False

    event = _RUNNING_CANCEL_EVENTS.get(task_id)
    if event is not None:
        event.set()

    try:
        os.killpg(proc.pid, signal.SIGTERM)
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return True
    except ProcessLookupError:
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return False
    except Exception:
        _RUNNING_PROCESSES.pop(task_id, None)
        _RUNNING_CANCEL_EVENTS.pop(task_id, None)
        return False
