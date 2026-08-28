"""Real HermesExecutor for FORGE - Coding Agent.

This is a MINIMAL smoke integration that runs Hermes as a subprocess.
NOT production-ready - no sandbox, limited output parsing.

Security limitations:
- Prompt rules are NOT a real sandbox
- Hermes has full filesystem access
- No credential isolation
- No network filtering
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from pathlib import Path
from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import AgentStatus, EventKind, TaskStatus

# Global semaphore to enforce FORGE concurrency = 1
# Prevents multiple Hermes executions running simultaneously
_FORGE_SEMAPHORE = asyncio.Semaphore(1)


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

        WARNING: These rules are NOT enforced - they're just instructions.
        Hermes has full filesystem access.
        """
        return f"""You are FORGE, a coding agent working on a single task.

CRITICAL WORKSPACE CONSTRAINTS:
- Work ONLY inside: {self._workspace}
- Do NOT use sudo, systemctl, pacman, or other system commands
- Do NOT push to git, deploy, or modify remote systems
- Do NOT access ~/.ssh, .env files, or credentials
- Do NOT modify files outside your workspace
- Return a SHORT final result summary (max 200 words)

TASK:
{task.title}

{task.description}

Complete this task inside your workspace, then provide a brief summary of what was done.
"""

    async def _run_hermes(
        self, prompt: str, runtime
    ) -> dict:
        """Run Hermes CLI as subprocess.

        Returns:
            {"success": bool, "output": str, "error": str}
        """
        if self._workspace is None:
            return {"success": False, "error": "No workspace created"}

        # Check Hermes is available
        hermes_path = shutil.which("hermes")
        if not hermes_path:
            return {"success": False, "error": "Hermes CLI not found in PATH"}

        try:
            # Run Hermes with -q (non-interactive), --quiet (minimal output)
            # Specify model and provider for smoke test
            proc = await asyncio.create_subprocess_exec(
                hermes_path,
                "chat",
                "-q",
                prompt,
                "--quiet",
                "--in",
                str(self._workspace),
                "-m",
                "kr/glm-5",
                "--provider",
                "custom:archkian",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
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
