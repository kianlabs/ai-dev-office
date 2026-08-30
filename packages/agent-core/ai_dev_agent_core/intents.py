"""Phase 4.1 — conversational intent contract + deterministic classifier.

The user talks to ATLAS in natural language. Every utterance maps to exactly
one intent of the contract:

    CHAT         → ATLAS only (natural reply, no tools, no specialists)
    PLAN         → ATLAS only (plan artifact, no coding)
    RESEARCH     → SCOUT only (read-only)
    IMPLEMENT    → FORGE → QA (SCOUT optional)
    TEST         → QA only
    MONITOR      → PULSE only
    NEEDS_INPUT  → ATLAS only (asks a short, specific question)

Classification is deterministic and cheap so routing can be tested without
model tokens. An LLM-backed ATLAS may replace the internals later while
returning the same intent strings.

Explicit slash commands (``/chat``, ``/plan``, ...) override the heuristics.
"""

from __future__ import annotations

import re
from typing import Any

# ── Intent contract ──────────────────────────────────────────────────────
INTENT_CHAT = "chat"
INTENT_PLAN = "plan"
INTENT_RESEARCH = "research"
INTENT_IMPLEMENT = "implement"
INTENT_TEST = "test"
INTENT_MONITOR = "monitor"
INTENT_NEEDS_INPUT = "needs_input"

ALL_INTENTS = (
    INTENT_CHAT,
    INTENT_PLAN,
    INTENT_RESEARCH,
    INTENT_IMPLEMENT,
    INTENT_TEST,
    INTENT_MONITOR,
    INTENT_NEEDS_INPUT,
)

# Intents that must NEVER trigger workspace preparation: they dispatch no
# specialist and must not create directories/files (root-cause fix for
# "halo" → FORGE → empty workspace → QA FAIL → repair loop).
NO_WORKSPACE_INTENTS = frozenset({INTENT_CHAT, INTENT_PLAN, INTENT_NEEDS_INPUT})

# Intents that must never enter the FORGE repair loop.
NO_REPAIR_INTENTS = frozenset({INTENT_CHAT, INTENT_PLAN, INTENT_NEEDS_INPUT})

# ── Slash command override ───────────────────────────────────────────────
_SLASH_COMMANDS = {
    "/chat": INTENT_CHAT,
    "/plan": INTENT_PLAN,
    "/research": INTENT_RESEARCH,
    "/implement": INTENT_IMPLEMENT,
    "/test": INTENT_TEST,
    "/monitor": INTENT_MONITOR,
}


def extract_slash_command(text: str) -> str | None:
    """Return the intent forced by a leading slash command, if any."""
    for line in text.splitlines():
        stripped = line.strip().lower()
        if not stripped:
            continue
        first_word = stripped.split()[0]
        return _SLASH_COMMANDS.get(first_word)
    return None


# ── Vocabulary ───────────────────────────────────────────────────────────
_SOCIAL_PATTERNS = (
    r"^\s*(halo|hallo|hai|hi|hei|hey|hello|oi|oy|woy|bro|gan|pagi|siang|"
    r"sore|malam|assalamualaikum)\b",
    r"\b(makasih|makasi|terima ?kasih|thanks|thank you|thx|tq|sama-?sama)\b",
    r"\b(menurutmu|menurut kamu|gimana|bagaimana|apa kabar|kabarmu|kabar kamu)\b",
    r"^\s*(ok|okh|oke|okay|sip|yes|ya|iyah|iye|siap|noted|roger)\s*[!.…]*\s*$",
    r"\b(halo|hai|hallo)\s*[🙂👋😊🤖✨]*\s*[!.…]*\s*$",
)

_STRONG_IMPLEMENT_PATTERNS = (
    r"\b(implementasikan|implementasi|implement|diimplementasikan)\b",
    r"\b(lanjut ?coding|mulai ?coding|mulai ngoding|gas ?coding)\b",
    r"\b(buat sekarang|kerjakan sekarang|kerjakan sekarang|buat sekarang juga)\b",
    r"\b(code it|start coding|go ahead and code)\b",
)

_TEST_PATTERNS = (
    r"\brun (the )?tests?\b",
    r"\btest only\b",
    r"\bcheck tests?\b",
    r"\bverify tests?\b",
    r"\btest suite\b",
    r"\bjalankan (test|tes|pengujian)\b",
    r"\buj(i|ikan) (project|proyek|aplikasi)\b",
    r"\btes (project|proyek|aplikasi)\b",
    r"\b(cek|periksa) (test|tes|pengujian)\b",
)

_MONITOR_PATTERNS = (
    r"\bhealth ?check\b",
    r"\bcheck health\b",
    r"\bruntime health\b",
    r"\bworkspace health\b",
    r"\bmonitor(ing)? (runtime|service|server|health)\b",
    r"\bdeployment (status|health)\b",
    r"\b(cek|periksa|pantau) (health|kesehatan)\b",
    r"\bkesehatan (sistem|runtime|service|server)\b",
    r"\b(cek|check|periksa|verify|monitor|pantau) (port|server|service)\b",
    r"\b(service|server|runtime) (sehat|healthy|status)\b",
    r"\b(service|server) lokal\b",
    r"\blocal (service|server)\b",
    r"\bapakah (service|server)\b",
    r"\bis the (service|server)\b",
    r"\bsehat\b",
    r"\blocalhost\b",
    r"\bport\s*\d+\b",
    r"\b\d{1,3}(\.\d{1,3}){3}\b",
)

_PLAN_PATTERNS = (
    r"\b(plan|planning|plano)\b",
    r"\b(rancang|rancangan|rencana|rencanakan)\b",
    r"\b(desain|design|designing)\b",
    r"\b(struktur)\b",
    r"\b(arsitektur|architecture|architect)\b",
    r"\b(blueprint|wireframe|mockup|mock-up|kerangka)\b",
    r"\bjangan (di)?coding\b",
    r"\btanpa (di)?coding\b",
    r"\bwithout coding\b",
    r"\bno coding\b",
    r"\bdon'?t code\b",
    r"\bjangan di ?code\b",
)

_RESEARCH_PATTERNS = (
    r"\b(research|riset|recherche)\b",
    r"\b(investigate|investigasi|teliti|telaah|kajian)\b",
    r"\b(bandingkan|perbandingan|compare|comparison|vs\.?\s)\b",
    r"\bbest (library|approach|practice|option|tool)\b",
    r"\blibrary terbaik\b",
    r"\b(rekomendasi|recommendation|recommend)\b",
    r"\b(dokumentasi|documentation|docs)\b",
    r"\b(dependensi|dependencies?|dependency)\b",
    r"\b(analisis|analisa|analyse|analyze|analysis)\b",
    r"\b(jelaskan|jelaskan codebase|explain codebase)\b",
    r"\b(pahami|review architecture|periksa struktur)\b",
)

_WEAK_IMPLEMENT_PATTERNS = (
    r"\bimplement\b",
    r"\b(create|add|change|modify|refactor|build|make|write)\b",
    r"\b(buat|buatkan|bikin|bikinkan)\b",
    r"\b(tambah|tambahkan)\b",
    r"\b(perbaiki|perbagus|benahi)\b",
    r"\b(ubah|ganti|update)\b",
    r"\b(fix|repair|patch)\b",
    r"\b(hapus|delete|remove)\b",
)

_REFINEMENT_PATTERN = re.compile(
    r"^\s*(pakai|pake|gunakan|pilih|ganti\s+ke|ganti\s+dengan|ubah\s+ke|"
    r"ubah\s+menjadi|pakai)\b.{1,80}$",
    re.IGNORECASE,
)

# Tokens that carry no task content by themselves ("perbaiki ini", "buat bagus").
_VAGUE_TOKENS = frozenset(
    {
        "perbaiki", "perbagus", "benahi", "fix", "repair", "patch", "improve",
        "buat", "buatkan", "bikin", "bikinkan", "make", "add", "tambah",
        "tambahkan", "ubah", "ganti", "update", "kerjakan", "improve",
        "ini", "itu", "this", "that", "dong", "deh", "ya", "aja", "saja",
        "tolong", "pls", "plis", "please", "bagus", "bagusin", "better",
        "lebih", "dikit", "banget", "sih", "kayak", "seperti", "yang",
        "the", "a", "an", "to", "it", "up", "me", "my", "for", "and", "in",
        "on", "of", "please", "bantu", "help", "coba", "dulu", "dululah",
    }
)

_CODEISH_PATTERN = re.compile(r"[\w./-]+\.(py|js|ts|tsx|jsx|go|rs|java|rb|php|md|json|ya?ml)\b|src/|app/|lib/|tests?/")


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _is_social(text: str) -> bool:
    return _matches_any(text, _SOCIAL_PATTERNS)


def _has_action_keyword(text: str) -> bool:
    return (
        _matches_any(text, _STRONG_IMPLEMENT_PATTERNS)
        or _matches_any(text, _TEST_PATTERNS)
        or _matches_any(text, _MONITOR_PATTERNS)
        or _matches_any(text, _PLAN_PATTERNS)
        or _matches_any(text, _RESEARCH_PATTERNS)
        or _matches_any(text, _WEAK_IMPLEMENT_PATTERNS)
    )


def _is_vague_request(text: str) -> bool:
    """Action words present, but no concrete content to act on.

    "perbaiki ini", "fix", "buat bagus" → NEEDS_INPUT.
    "buat fungsi greet(name) di src/index.js" → not vague.
    """
    if not _matches_any(text, _WEAK_IMPLEMENT_PATTERNS):
        return False

    if _CODEISH_PATTERN.search(text):
        return False

    words = re.findall(r"[a-zA-Z]+", text)
    content_words = [
        w for w in words
        if w.lower() not in _VAGUE_TOKENS and len(w) > 1
    ]
    # Quoted strings or parentheses carry concrete content ("greet(name)").
    if re.search(r"[\"'()]|\w+\(", text):
        return False
    return len(content_words) == 0


def is_plan_refinement(text: str) -> bool:
    """Short steering utterance for the active plan ("pakai PostgreSQL aja")."""
    stripped = text.strip()
    if len(stripped.split()) > 10:
        return False
    return bool(_REFINEMENT_PATTERN.match(stripped)) or bool(
        re.search(r"\b(pakai|pake|gunakan|pilih)\b.{1,40}\b(aja|saja)\b", stripped, re.IGNORECASE)
    )


def _names_all_specialists(text: str) -> bool:
    """True when the user explicitly names SCOUT, FORGE, QA and PULSE."""
    return all(
        re.search(rf"\b{role}\b", text) for role in ("scout", "forge", "qa", "pulse")
    )


def classify_intent(task: Any, has_active_plan: bool = False) -> str:
    """Classify a task into the Phase 4.1 intent contract.

    ``task`` may be a :class:`ai_dev_shared.Task` or anything exposing
    ``title`` and ``description``.

    The classifier reads the COMPLETE user content (``description``). The
    title is only a display summary (often a truncated first line), so it is
    used only when no description exists.
    """
    description = str(getattr(task, "description", "") or "").strip()
    title = str(getattr(task, "title", "") or "").strip()
    text = (description or title).strip().lower()

    # 0. Explicit slash commands override the heuristics.
    forced = extract_slash_command(text)
    if forced is not None:
        return forced

    # 1. Pure social utterances are conversation, never work orders.
    if _is_social(text) and not _has_action_keyword(text):
        return INTENT_CHAT

    # 2. Strong implementation language wins over plan/monitor/test keywords
    #    ("implementasikan plan tadi", "implement X and run tests").
    if _matches_any(text, _STRONG_IMPLEMENT_PATTERNS):
        return INTENT_IMPLEMENT

    # 2b. Explicit full-roster work orders override operational keywords
    #     inside the role list ("... QA jalankan test. 4. PULSE pantau ...").
    if _names_all_specialists(text):
        return INTENT_IMPLEMENT

    # 3. Operational-only requests.
    if _matches_any(text, _TEST_PATTERNS):
        return INTENT_TEST

    if _matches_any(text, _MONITOR_PATTERNS):
        return INTENT_MONITOR

    # 4. Planning / design requests (explicitly not coding).
    if _matches_any(text, _PLAN_PATTERNS):
        return INTENT_PLAN

    # 5. Research / analysis requests.
    if _matches_any(text, _RESEARCH_PATTERNS):
        return INTENT_RESEARCH

    # 6. Active-plan refinements ("pakai PostgreSQL aja").
    if has_active_plan and is_plan_refinement(text):
        return INTENT_PLAN

    # 7. Vague requests need clarification before any specialist runs.
    if _is_vague_request(text):
        return INTENT_NEEDS_INPUT

    # 8. Concrete implementation requests.
    if _matches_any(text, _WEAK_IMPLEMENT_PATTERNS):
        return INTENT_IMPLEMENT

    # 9. Conservative fallback: ask instead of guessing (never FORGE by
    #    accident — the old classifier defaulted to FEATURE here).
    return INTENT_NEEDS_INPUT
