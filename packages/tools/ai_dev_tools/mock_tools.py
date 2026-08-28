"""Deterministic stub tools used by the mock executors.

These never touch the real filesystem or shell -- they return canned output so
the research/code/test phases produce believable progress without any risky
autonomous execution.
"""

from __future__ import annotations

import random
from typing import Any

from .base import BaseTool, ToolResult


class ReadDocumentationTool(BaseTool):
    name = "read_docs"
    description = "Simulates reading technical documentation for a topic."

    TOPICS = {
        "auth": "NextAuth.js: Credentials & JWT session strategy, middleware for route guards, hashing with bcrypt.",
        "deploy": "Vercel: build pipeline, preview deployments, DATABASE_URL env injection; Railway: health checks, volume mounts.",
        "bug": "Node.js stack traces: unhandled promise rejections, missing await, hydration mismatch causes in Next.js.",
        "feature": "Feature branch structure, testing pyramid, incremental rendering options (SSR/ISR/CSG).",
    }

    async def run(self, topic: str = "auth", **_: Any) -> ToolResult:
        text = self.TOPICS.get(topic, self.TOPICS["feature"])
        return ToolResult(ok=True, output=text, meta={"topic": topic})


class ReadProjectTreeTool(BaseTool):
    name = "read_project_tree"
    description = "Simulates scanning the target repository structure."

    async def run(self, repo: str = "nextjs-app", **_: Any) -> ToolResult:
        tree = (
            f"{repo}/\n"
            "├─ app/\n"
            "│  ├─ layout.tsx\n"
            "│  ├─ dashboard/\n"
            "│  ├─ login/page.tsx\n"
            "│  └─ api/auth/\n"
            "├─ lib/\n"
            "│  ├─ db.ts\n"
            "│  └─ auth.ts\n"
            "├─ components/\n"
            "│  └─ navbar.tsx\n"
            "└─ package.json"
        )
        return ToolResult(ok=True, output=tree, meta={"repo": repo})


class WriteCodeTool(BaseTool):
    name = "write_code"
    description = "Simulates editing a source file. Returns a diff-like snippet."

    async def run(self, file: str = "lib/auth.ts", change: str = "", **_: Any) -> ToolResult:
        snippet = f"@@ {file} @@\n+ // {change or 'auth provider wired up'}"
        return ToolResult(ok=True, output=snippet, meta={"file": file})


class RunCheckTool(BaseTool):
    """Simulated npm/test/lint/typecheck command. Real shell-free by design."""

    name = "run_check"
    description = "Simulates running a development command and captures its output."

    OUTPUTS = {
        "test": "PASS  examples/auth\ntests: 12 passed, 0 failed ─ 0.34s\nTest Suites: 3 passed, 3 total",
        "typecheck": "tsc --noEmit : completed with 0 errors",
        "lint": "next lint: no issues found",
        "build": "Route (app)/dashboard ... ✓ compiled\nGenerating static pages (5/5) ✓",
    }

    async def run(self, command: str = "test", **_: Any) -> ToolResult:
        rng = random.Random(f"{command}:{len(command)}")
        ok = rng.random() > 0.06
        output = self.OUTPUTS.get(command, f"$ {command} -> ok")
        if not ok:
            output = f"{output}\n1 file has a type error (simulated)."
        return ToolResult(ok=ok, output=output, meta={"command": command})


class PollDeploymentTool(BaseTool):
    name = "poll_deployment"
    description = "Simulates querying deployment / build health."

    async def run(self, target: str = "preview", **_: Any) -> ToolResult:
        states = ["Uploading", "Building", "Ready", "Ready"]
        state = states[min(len(states) - 1, random.randint(0, 3))]
        return ToolResult(ok=state == "Ready", output=state, meta={"target": target})


def default_tools() -> list[BaseTool]:
    return [
        ReadDocumentationTool(),
        ReadProjectTreeTool(),
        WriteCodeTool(),
        RunCheckTool(),
        PollDeploymentTool(),
    ]