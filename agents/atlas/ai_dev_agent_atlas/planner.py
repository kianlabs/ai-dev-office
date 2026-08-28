"""Deterministic role-aware planner for ATLAS.

This planner decides WHICH specialist roles are needed for a task.
It does not execute agents and does not perform delegation itself.

The deterministic implementation is intentionally replaceable by a future
LLM-backed ATLAS planner while preserving the same plan contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

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


def _contains_fuzzy_word(
    text: str,
    terms: tuple[str, ...],
    threshold: float = 0.90,
) -> bool:
    """Match minor typos only for long, explicit intent words."""

    words = re.findall(r"[a-zA-Z]+", text.lower())

    for word in words:
        for term in terms:
            if abs(len(word) - len(term)) > 2:
                continue

            if SequenceMatcher(None, word, term).ratio() >= threshold:
                return True

    return False


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
            "analisa",
            "telaah",
            "teliti",
            "riset",
            "jelaskan",
            "jelaskan codebase",
            "jelaskan arsitektur",
            "pahami codebase",
            "pahami arsitektur",
            "periksa struktur",
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
            "jalankan pengujian",
            "uji project",
            "uji proyek",
            "tes project",
            "tes proyek",
            "cek test",
            "cek tes",
            "periksa pengujian",
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
            "periksa kesehatan",
            "kesehatan sistem",
            "kesehatan runtime",
            "cek runtime",
            "periksa runtime",
            "monitor runtime",
            "pantau runtime",
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
            "jangan mengubah",
            "jangan merubah",
            "jangan modifikasi",
            "jangan memodifikasi",
            "tidak boleh mengubah",
            "tidak boleh merubah",
            "tidak boleh memodifikasi",
            "jangan edit",
            "tanpa edit",
            "read only",
            "read-only",
            "hanya analisis",
            "hanya analisa",
        ),
    )

    implementation_requested = (
        _contains_any(
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
        or _contains_fuzzy_word(
            text,
            (
                "implement",
                "implementasi",
                "implementasikan",
            ),
        )
    )

    # Explicit read-only language is a hard safety constraint.
    # Testing/health keywords alone are not enough to suppress implementation:
    # "implement X and run tests" still requires FORGE + QA.
    #
    # Broad classifier intent is only trusted when the task does not explicitly
    # describe itself as an operational-only request.
    operational_only = (
        (test_only or health_only)
        and not implementation_requested
    )

    implementation = (
        not no_modification
        and not operational_only
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

    monitoring_needed = deployment_related or health_only

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

        if monitoring_needed:
            selected.append("pulse")
            reasons["pulse"] = (
                "runtime/deployment verification is required"
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
