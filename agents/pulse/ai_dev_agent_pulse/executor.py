"""Deterministic read-only executor for PULSE - Monitor / DevOps Agent."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Any

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task


class DeterministicPulseExecutor:
    """Inspect task health without modifying the workspace.

    PULSE is intentionally read-only. It does not deploy, restart services,
    modify source code, or dispatch other agents.
    """

    agent_id = "pulse"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id

    def _workspace_for(self, task: Task) -> Path:
        return (
            Path.home()
            / "ai-dev-office"
            / "workspaces"
            / task.id[:12]
        )

    def _inspect_workspace(self, workspace: Path) -> dict[str, Any]:
        if not workspace.exists():
            return {
                "name": "workspace",
                "status": "FAIL",
                "detail": "task workspace does not exist",
            }

        files = [
            p
            for p in workspace.rglob("*")
            if p.is_file()
            and ".ado-runtime" not in p.parts
        ]

        if not files:
            return {
                "name": "workspace",
                "status": "FAIL",
                "detail": "task workspace contains no artifacts",
            }

        total_bytes = 0

        for path in files:
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass

        return {
            "name": "workspace",
            "status": "PASS",
            "detail": (
                f"{len(files)} artifact(s), "
                f"{total_bytes} byte(s)"
            ),
            "artifact_count": len(files),
            "total_bytes": total_bytes,
        }

    def _inspect_research(self, ctx: ExecutionContext) -> dict[str, Any]:
        research = ctx.shared.get("research")

        if research:
            return {
                "name": "research_context",
                "status": "PASS",
                "detail": "SCOUT structured context available",
            }

        return {
            "name": "research_context",
            "status": "INFO",
            "detail": "no SCOUT research required/provided",
        }

    def _build_health(
        self,
        workspace: Path,
        ctx: ExecutionContext,
    ) -> dict[str, Any]:
        checks = [
            self._inspect_workspace(workspace),
            self._inspect_research(ctx),
        ]

        failures = [
            check
            for check in checks
            if check["status"] == "FAIL"
        ]

        if failures:
            status = "UNHEALTHY"
            summary = (
                "Workspace health check failed: "
                + ", ".join(check["name"] for check in failures)
            )
        else:
            status = "HEALTHY"
            summary = "Task workspace health checks passed"

        return {
            "status": status,
            "checks": checks,
            "summary": summary,
            "workspace": str(workspace),
        }

    async def execute(
        self,
        task: Task,
        ctx: ExecutionContext,
    ) -> AsyncIterator[AgentEvent]:
        r = self.r
        workspace = self._workspace_for(task)

        yield await r.tick(
            r.working("Inspecting task workspace health")
        )

        health = self._build_health(workspace, ctx)

        for check in health["checks"]:
            yield await r.tick(
                r.say(
                    f"{check['name']} → "
                    f"{check['status']} :: "
                    f"{check['detail']}"
                )
            )

        ctx.shared["health"] = health

        yield await r.tick(
            r.health(
                f"Health: {health['status']} — {health['summary']}",
                meta={"health": health},
            )
        )

        yield await r.tick(r.idle("Idle"))
