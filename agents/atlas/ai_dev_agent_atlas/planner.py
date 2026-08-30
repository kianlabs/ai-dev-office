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
    # NOTE: the planner reads the COMPLETE task (display title + full content).
    # `task.description` carries the exact multi-line user instructions and is
    # never truncated to the first line. `task.title` is only a short display
    # summary. Never let a display-first-line replace `task.description`. The
    # title is repeated here for the convenience of single-line submissions
    # where the user only typed a title with no description.
    return f"{task.title}\n{task.description}".lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


# Canonical dispatch order for the specialist roster.
ROLE_ORDER = ("scout", "forge", "qa", "pulse")

# Phrases that request the FULL specialist roster regardless of keywords.
_ALL_SPECIALISTS_PHRASES = (
    "libatkan semua specialist",
    "libatkan seluruh specialist",
    "libatkan semua agen",
    "libatkan seluruh agen",
    "semua specialist",
    "seluruh specialist",
    "semua agen",
    "seluruh agen",
    "all specialists",
    "all agents",
    "all roles",
    "involve all specialists",
    "involve all agents",
)


def _explicit_role_mentions(text: str) -> tuple[str, ...]:
    """Specialist roles the task explicitly names, in order of first mention.

    Matches whole words (SCOUT/FORGE/QA/PULSE) so numbered lists, role chains
    ("SCOUT → FORGE → QA → PULSE") and plain prose ("libatkan FORGE dan QA")
    all surface the roles the user explicitly asked for.
    """
    found: list[tuple[int, str]] = []
    for token in ROLE_ORDER:
        match = re.search(rf"\b{token}\b", text)
        if match:
            found.append((match.start(), token))
    found.sort()
    return tuple(token for _, token in found)


def _all_specialists_requested(text: str) -> bool:
    return _contains_any(text, _ALL_SPECIALISTS_PHRASES)


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
            # Phase 4: local service monitoring vocabulary.
            "cek port",
            "check port",
            "periksa port",
            "cek server",
            "check server",
            "periksa server",
            "cek service",
            "check service",
            "periksa service",
            "verify service",
            "verify server",
            "monitor service",
            "monitor server",
            "pantau service",
            "pantau server",
            "service sehat",
            "server sehat",
            "service lokal",
            "server lokal",
            "local service",
            "local server",
            "service status",
            "server status",
            "apakah service",
            "apakah server",
            "is the service",
            "is the server",
            "health",
            "sehat",
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

    # ---- Explicit role requirements take precedence ----------------------
    # If the user explicitly names specialist roles (a role chain such as
    # "SCOUT → FORGE → QA → PULSE", a numbered list naming roles, or a phrase
    # like "libatkan semua specialist"), the plan MUST include every requested
    # role. The heuristic selection above is still the base for ordinary
    # tasks with no explicit roles, so minimal role-aware routing is preserved.
    #
    # Explicit roles are a superset: we honour them AND keep any roles the
    # heuristic already picked, so we never drop a requested specialist while
    # also never forcing a plain task to use every agent.
    explicit_roles = _explicit_role_mentions(text)
    if _all_specialists_requested(text) or set(explicit_roles) == set(ROLE_ORDER):
        explicit_roles = ROLE_ORDER

    if explicit_roles:
        ordered: list[str] = []
        for rid in explicit_roles:
            if rid not in ordered:
                ordered.append(rid)
        for rid in agents:
            if rid not in ordered:
                ordered.append(rid)
        agents = tuple(ordered)
        for rid in explicit_roles:
            reasons.setdefault(rid, "explicitly required by the user task")

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
