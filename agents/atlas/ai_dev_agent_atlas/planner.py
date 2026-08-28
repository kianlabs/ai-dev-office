"""Deterministic role-aware planner for ATLAS.

This planner decides WHICH specialist roles are needed for a task.
It does not execute agents and does not perform delegation itself.

The deterministic implementation is intentionally replaceable by a future
LLM-backed ATLAS planner while preserving the same plan contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_dev_shared import Subtask, Task


@dataclass(frozen=True)
class AtlasPlan:
    """Structured execution plan produced by ATLAS."""

    intent: str
    agents: tuple[str, ...]
    subtasks: tuple[Subtask, ...]
    reasons: dict[str, str]


def _task_text(task: Task) -> str:
    return f"{task.title}\n{task.description}".lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def build_role_aware_plan(task: Task, intent: str) -> AtlasPlan:
    """Select specialist agents based on the requested work.

    Rules are deterministic for Phase 3C.5 so routing can be tested without
    spending model tokens. A future real ATLAS planner may replace these rules
    while returning the same AtlasPlan contract.
    """

    text = _task_text(task)

    analysis_only = _contains_any(
        text,
        (
            "analyze",
            "analyse",
            "analysis",
            "research",
            "investigate",
            "explain codebase",
            "review architecture",
            "analisis",
            "teliti",
            "riset",
            "jelaskan codebase",
            "jelaskan arsitektur",
        ),
    )

    test_only = _contains_any(
        text,
        (
            "run tests",
            "run test",
            "test only",
            "check tests",
            "verify tests",
            "jalankan test",
            "jalankan tes",
            "cek test",
            "cek tes",
        ),
    )

    health_only = _contains_any(
        text,
        (
            "health check",
            "check health",
            "runtime health",
            "workspace health",
            "monitor runtime",
            "deployment status",
            "deployment health",
            "cek health",
            "cek kesehatan",
            "cek runtime",
            "monitor runtime",
        ),
    )

    no_modification = _contains_any(
        text,
        (
            "without changing",
            "without modifying",
            "do not change",
            "do not modify",
            "don't change",
            "don't modify",
            "read only",
            "read-only",
            "tanpa mengubah",
            "tanpa merubah",
            "tanpa memodifikasi",
            "jangan ubah",
            "jangan merubah",
            "jangan modifikasi",
            "hanya analisis",
            "hanya analisa",
        ),
    )

    implementation_requested = _contains_any(
        text,
        (
            "implement",
            "create",
            "add ",
            "fix",
            "change",
            "modify",
            "refactor",
            "build",
            "buat",
            "tambahkan",
            "perbaiki",
            "ubah",
            "implementasikan",
        ),
    )

    # Explicit read-only/no-modification language overrides generic intent.
    # classify_intent() may label a task as "feature" from broad task wording,
    # but ATLAS must not dispatch FORGE when the user explicitly forbids edits.
    # Explicit read-only and operational-only requests override the broad
    # intent classifier. A task such as "check runtime health" must not become
    # an implementation task merely because classify_intent() returned
    # "feature".
    explicit_non_implementation = (
        no_modification
        or test_only
        or health_only
    )

    implementation = (
        not explicit_non_implementation
        and (
            implementation_requested
            or intent in {"feature", "bug", "auth", "deploy"}
        )
    )

    research_needed = _contains_any(
        text,
        (
            "research",
            "investigate",
            "compare",
            "best library",
            "best approach",
            "documentation",
            "docs",
            "dependency",
            "dependencies",
            "riset",
            "teliti",
            "bandingkan",
            "library terbaik",
            "dokumentasi",
            "dependensi",
        ),
    )

    deployment_related = intent == "deploy" or _contains_any(
        text,
        (
            "deploy",
            "deployment",
            "production",
            "preview",
            "release",
            "hosting",
        ),
    )

    # Explicit single-role operational requests take precedence.
    if health_only and not implementation:
        agents = ("pulse",)
        reasons = {
            "pulse": "runtime/workspace health inspection requested",
        }

    elif test_only and not implementation:
        agents = ("qa",)
        reasons = {
            "qa": "verification/testing requested without implementation",
        }

    elif analysis_only and not implementation:
        agents = ("scout",)
        reasons = {
            "scout": "research or codebase analysis requested",
        }

    elif implementation:
        selected: list[str] = []
        reasons = {}

        if research_needed:
            selected.append("scout")
            reasons["scout"] = (
                "implementation requires research or dependency context"
            )

        selected.append("forge")
        reasons["forge"] = "source implementation is required"

        selected.append("qa")
        reasons["qa"] = "implementation must be verified"

        if deployment_related:
            selected.append("pulse")
            reasons["pulse"] = (
                "deployment-related work requires readiness monitoring"
            )

        agents = tuple(selected)

    else:
        # Conservative default: understand the request without modifying code.
        agents = ("scout",)
        reasons = {
            "scout": "request is ambiguous; gather context before modification",
        }

    titles = {
        "scout": "Research requirements, constraints, and relevant context",
        "forge": "Implement the requested source changes",
        "qa": "Verify artifacts and run deterministic QA checks",
        "pulse": "Inspect workspace and runtime health",
    }

    subtasks = tuple(
        Subtask(
            title=titles[agent_id],
            agent_id=agent_id,
        )
        for agent_id in agents
    )

    return AtlasPlan(
        intent=intent,
        agents=agents,
        subtasks=subtasks,
        reasons=reasons,
    )
