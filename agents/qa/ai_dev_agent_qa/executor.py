"""Deterministic real QA executor.

QA verifies the workspace produced by FORGE.

Security properties:
- workspace mounted read-only
- network namespace isolated
- parent environment cleared
- no autonomous command selection
- only predefined project checks are executed
- timeout kills the whole sandbox process group
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
from ai_dev_shared.constants import TaskStatus

BWRAP_PATH = "/usr/bin/bwrap"

_QA_SEMAPHORE = asyncio.Semaphore(1)


class DeterministicQAExecutor:
    agent_id = "qa"
    DEFAULT_TIMEOUT = 180

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.timeout = self.DEFAULT_TIMEOUT

    def _workspace_for(self, task: Task) -> Path:
        root = Path.home() / "ai-dev-office" / "workspaces"
        return root / task.id[:12]

    async def execute(
        self,
        task: Task,
        ctx: ExecutionContext,
    ) -> AsyncIterator[AgentEvent]:
        r = MockRuntime(task, ctx)
        r.agent_id = self.agent_id

        workspace = self._workspace_for(task)

        yield await r.tick(r.waiting("Waiting for FORGE workspace"))
        yield await r.tick(
            r.working(
                "Inspecting FORGE output",
                task_status=TaskStatus.RUNNING,
            )
        )

        if not workspace.is_dir():
            yield await r.tick(
                r.qa_result(
                    "FAIL",
                    f"QA gate: FAIL — workspace missing: {workspace}",
                )
            )
            yield await r.tick(r.idle("Idle"))
            return

        async with _QA_SEMAPHORE:
            checks = self._detect_checks(workspace)

            if not checks:
                # A workspace can legitimately contain non-code artifacts.
                # Still verify it exists and is non-empty.
                entries = [
                    p
                    for p in workspace.rglob("*")
                    if p.is_file()
                    and ".ado-runtime" not in p.parts
                ]

                if entries:
                    yield await r.tick(
                        r.say(
                            f"No runnable project checks detected; "
                            f"verified {len(entries)} workspace file(s)"
                        )
                    )
                    yield await r.tick(
                        r.qa_result(
                            "PASS",
                            "QA gate: PASS — workspace artifacts present; "
                            "no applicable test/typecheck/lint scripts detected",
                        )
                    )
                else:
                    yield await r.tick(
                        r.qa_result(
                            "FAIL",
                            "QA gate: FAIL — FORGE workspace is empty",
                        )
                    )

                yield await r.tick(r.idle("Idle"))
                return

            failures: list[str] = []

            for name, command in checks:
                yield await r.tick(r.working(f"Running QA check: {name}"))

                result = await self._run_check(
                    workspace,
                    command,
                )

                if result["success"]:
                    output = result["output"].strip()
                    summary = output[-500:] if output else "completed successfully"
                    yield await r.tick(
                        r.say(f"{name} → PASS :: {summary}")
                    )
                else:
                    failures.append(name)
                    error = result["error"].strip()
                    summary = error[-500:] if error else "check failed"
                    yield await r.tick(
                        r.say(f"{name} → FAIL :: {summary}")
                    )

            if failures:
                yield await r.tick(
                    r.qa_result(
                        "FAIL",
                        "QA gate: FAIL — failed checks: "
                        + ", ".join(failures),
                    )
                )
            else:
                yield await r.tick(
                    r.qa_result(
                        "PASS",
                        "QA gate: PASS — all applicable deterministic checks green",
                    )
                )

            yield await r.tick(r.idle("Idle"))

    def _detect_checks(
        self,
        workspace: Path,
    ) -> list[tuple[str, list[str]]]:
        """Select only deterministic allowlisted checks."""

        checks: list[tuple[str, list[str]]] = []

        package_json = workspace / "package.json"

        if package_json.is_file():
            try:
                data = json.loads(package_json.read_text())
            except (OSError, json.JSONDecodeError):
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

    async def _run_check(
        self,
        workspace: Path,
        command: list[str],
    ) -> dict[str, object]:
        if not Path(BWRAP_PATH).exists():
            return {
                "success": False,
                "output": "",
                "error": "bubblewrap unavailable",
            }

        bwrap_cmd = [
            BWRAP_PATH,
            "--unshare-all",
            "--clearenv",

            # FORGE output is immutable to QA.
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

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

            await proc.wait()

            return {
                "success": False,
                "output": "",
                "error": f"QA check timeout after {self.timeout}s",
            }

        output = stdout.decode(
            "utf-8",
            errors="replace",
        ).strip()

        error = stderr.decode(
            "utf-8",
            errors="replace",
        ).strip()

        return {
            "success": proc.returncode == 0,
            "output": output,
            "error": error or (
                ""
                if proc.returncode == 0
                else f"exit code {proc.returncode}"
            ),
        }
