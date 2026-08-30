"""Deterministic role-aware planner for ATLAS (Phase 4.1 routing table).

Maps the conversational intent contract onto the specialist roster:

    CHAT         → (no specialists)
    PLAN         → (no specialists — ATLAS only, never FORGE/QA)
    RESEARCH     → SCOUT only
    IMPLEMENT    → (SCOUT optional) FORGE → QA (PULSE when deploy/monitor)
    TEST         → QA only
    MONITOR      → PULSE only
    NEEDS_INPUT  → (no specialists)

The implementation is intentionally deterministic/replaceable by a future
LLM-backed ATLAS planner while preserving the same plan contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai_dev_agent_core.intents import (
    INTENT_CHAT,
    INTENT_IMPLEMENT,
    INTENT_MONITOR,
    INTENT_NEEDS_INPUT,
    INTENT_PLAN,
    INTENT_RESEARCH,
    INTENT_TEST,
)
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


def build_role_aware_plan(task: Task, intent: str) -> AtlasPlan:
    """Select specialist agents based on the Phase 4.1 intent contract.

    Rules are deterministic so routing can be tested without spending model
    tokens. A future real ATLAS planner may replace these rules while
    returning the same AtlasPlan contract.
    """

    text = _task_text(task)

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

    deployment_related = _contains_any(
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

    monitoring_related = deployment_related or _contains_any(
        text,
        (
            "health check",
            "monitor runtime",
            "monitor service",
            "monitor server",
            "pantau runtime",
            "pantau service",
            "pantau server",
            "cek health",
            "cek kesehatan",
            "cek port",
            "check port",
            "cek server",
            "check server",
            "cek service",
            "check service",
        ),
    )

    if intent == INTENT_IMPLEMENT:
        selected: list[str] = []
        reasons: dict[str, str] = {}

        if research_needed:
            selected.append("scout")
            reasons["scout"] = (
                "implementation requires research or dependency context"
            )

        selected.append("forge")
        reasons["forge"] = "source implementation is required"

        selected.append("qa")
        reasons["qa"] = "implementation must be verified"

        if monitoring_related:
            selected.append("pulse")
            reasons["pulse"] = (
                "runtime/deployment verification is required"
            )

        agents = tuple(selected)

    elif intent == INTENT_RESEARCH:
        agents = ("scout",)
        reasons = {
            "scout": "research or codebase analysis requested",
        }

    elif intent == INTENT_TEST:
        agents = ("qa",)
        reasons = {
            "qa": "verification/testing requested without implementation",
        }

    elif intent == INTENT_MONITOR:
        agents = ("pulse",)
        reasons = {
            "pulse": "runtime/workspace health inspection requested",
        }

    else:
        # CHAT / PLAN / NEEDS_INPUT (and any unknown intent): ATLAS handles
        # the request itself. No specialist, no workspace, no repair loop.
        agents = ()
        reasons = {}

    # ---- Explicit role requirements take precedence ----------------------
    # If the user explicitly names specialist roles (a role chain such as
    # "SCOUT → FORGE → QA → PULSE", a numbered list naming roles, or a phrase
    # like "libatkan semua specialist"), the plan MUST include every requested
    # role. The intent-based selection above is still the base for ordinary
    # tasks with no explicit roles, so minimal role-aware routing is preserved.
    #
    # Explicit roles are a superset: we honour them AND keep any roles the
    # intent already picked, so we never drop a requested specialist while
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
