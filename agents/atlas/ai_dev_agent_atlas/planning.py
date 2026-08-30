"""Phase 4.1 — ATLAS plan artifacts, anti-hallucination, and dialogue replies.

Three responsibilities:

1. ``build_plan_artifact``  — turn a PLAN request into the structured plan
   contract (goal, known_requirements, assumptions, missing_information, ...).
   ANTI-HALLUCINATION RULE: facts the user never stated (business names,
   addresses, WhatsApp numbers, testimonials, customer data) are NEVER
   invented — they land in ``missing_information`` and the plan instructs the
   use of clearly-marked placeholders until the user supplies them.
2. ``apply_plan_update``    — fold a short refinement ("pakai PostgreSQL aja")
   into the active plan (conversation continuation).
3. ``render_plan_brief``    — render a bounded brief of the active plan; this
   (never the raw transcript) is what IMPLEMENT hands to FORGE.
"""

from __future__ import annotations

import re
from typing import Any

_PLAN_FIELDS = (
    "goal",
    "known_requirements",
    "assumptions",
    "missing_information",
    "blockers",
    "architecture",
    "features",
    "data_model",
    "api_plan",
    "ui_plan",
    "implementation_steps",
    "constraints",
    "open_questions",
)

_NO_CODING_PATTERNS = (
    r"jangan (di)?coding",
    r"tanpa (di)?coding",
    r"jangan di ?code",
    r"without coding",
    r"no coding",
    r"don'?t code",
    r"jangan coding",
)

_PLACEHOLDER_RULE = (
    "Jangan mengarang fakta bisnis (nama, alamat, kontak, testimoni, data "
    "pelanggan) — gunakan placeholder jelas seperti [NAMA PERUSAHAAN] sampai "
    "user memberikan datanya"
)

_TECH_DECISIONS = (
    (r"\bpostgres(ql)?\b", "PostgreSQL", "Database"),
    (r"\bmysql\b", "MySQL", "Database"),
    (r"\bmongodb?\b", "MongoDB", "Database"),
    (r"\bsqlite\b", "SQLite", "Database"),
    (r"\bsupabase\b", "Supabase", "Database/Backend"),
    (r"\bnext\.?js\b", "Next.js", "Framework"),
    (r"\breact\b", "React", "Framework"),
    (r"\bvue\b", "Vue", "Framework"),
    (r"\bsvelte\b", "Svelte", "Framework"),
    (r"\bangular\b", "Angular", "Framework"),
    (r"\btailwind\b", "Tailwind CSS", "Styling"),
    (r"\bbootstrap\b", "Bootstrap", "Styling"),
    (r"\bfastapi\b", "FastAPI", "Backend"),
    (r"\bexpress\b", "Express", "Backend"),
    (r"\bdjango\b", "Django", "Backend"),
    (r"\blaravel\b", "Laravel", "Backend"),
    (r"\b(flutter|react native)\b", "Flutter/React Native", "Mobile"),
    (r"\bnode\.?js\b", "Node.js", "Runtime"),
)


def _empty_plan() -> dict[str, Any]:
    return {field: ([] if field != "goal" else "") for field in _PLAN_FIELDS}


def _strip_request_phrasing(text: str) -> str:
    """Light cleanup of the raw request for display as the plan goal."""
    cleaned = text.strip()
    # Drop the explicit "no coding" instruction from the subject (DOTALL:
    # title+description duplication means the phrase may span lines).
    cleaned = re.sub(
        r"(,?\s*)(jangan (di)?coding|tanpa (di)?coding|jangan di ?code|"
        r"without coding|no coding|don'?t code)\b.*$",
        "",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Drop leading request phrasing ("tolong", "buat plan", "buat desain", ...).
    cleaned = re.sub(r"^(tolong|coba)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^buat(kan)?\s+(plan|planning|desain|design|struktur|rancangan)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"^(plan|planning|desain|design|struktur|rancangan)\s+(untuk|dari)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" ,.") or "yang dijelaskan user"


def _has_no_coding_constraint(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(p, lowered) for p in _NO_CODING_PATTERNS)


def _booking_plan(subject: str) -> dict[str, Any]:
    plan = _empty_plan()
    plan["goal"] = f"Merencanakan {subject}"
    plan["known_requirements"] = [subject]
    plan["features"] = [
        "Pencarian & daftar lapangan",
        "Jadwal ketersediaan (slot waktu)",
        "Pemesanan (booking) slot",
        "Konfirmasi & pembatalan booking",
    ]
    plan["data_model"] = ["Lapangan/Venue", "Slot jadwal", "Booking", "Pengguna"]
    plan["assumptions"] = [
        "Fitur mengikuti alur booking standar (belum dikonfirmasi user)",
        "Tech stack belum ditentukan",
    ]
    plan["missing_information"] = [
        "Nama/brand aplikasi",
        "Jenis lapangan & lokasi",
        "Harga & metode pembayaran",
        "Apakah perlu akun/login pengguna",
    ]
    return plan


def _landing_page_plan(subject: str, text: str) -> dict[str, Any]:
    plan = _empty_plan()
    plan["goal"] = f"Merencanakan {subject}"
    known = ["Landing page"]
    if re.search(r"pintu kayu", text, re.IGNORECASE):
        known.append("Bisnis pintu kayu")
    plan["known_requirements"] = known
    plan["ui_plan"] = [
        "Hero (headline + CTA)",
        "Layanan/produk",
        "Galeri portofolio",
        "Kontak & CTA",
    ]
    plan["assumptions"] = [
        "Semua konten faktual memakai placeholder sampai user memberikan data",
    ]
    plan["missing_information"] = [
        "Nama perusahaan",
        "Logo & warna brand",
        "Foto produk asli",
        "Nomor WhatsApp / kontak",
        "Alamat lokasi",
        "Testimoni pelanggan asli",
    ]
    return plan


def _inventory_plan(subject: str) -> dict[str, Any]:
    plan = _empty_plan()
    plan["goal"] = f"Merencanakan {subject}"
    plan["known_requirements"] = [subject]
    plan["features"] = [
        "Input & update barang",
        "Daftar stok",
        "Mutasi stok (masuk/keluar)",
        "Laporan stok",
    ]
    plan["data_model"] = ["Item/Barang", "Kategori", "Mutasi stok", "Pengguna"]
    plan["assumptions"] = [
        "Platform & stack belum ditentukan",
    ]
    plan["missing_information"] = [
        "Jenis barang yang dikelola",
        "Jumlah pengguna & role",
        "Platform (web/desktop/mobile)",
    ]
    return plan


def _generic_plan(subject: str) -> dict[str, Any]:
    plan = _empty_plan()
    plan["goal"] = f"Merencanakan {subject}"
    plan["known_requirements"] = [subject]
    plan["assumptions"] = [
        "Detail kebutuhan mengikuti konfirmasi user pada open_questions",
    ]
    plan["missing_information"] = [
        "Fitur utama yang diinginkan",
        "Target pengguna",
        "Platform / stack yang diinginkan",
    ]
    return plan


def _request_content(task: Any) -> str:
    """The complete user request. Prefer the full description; the display
    title is only a (possibly truncated) first-line summary."""
    return (task.description or "").strip() or str(task.title).strip()


def build_plan_artifact(task: Any) -> dict[str, Any]:
    """Build the structured plan contract from a PLAN request."""
    text = _request_content(task)
    lowered = text.lower()

    if re.search(r"booking|lapangan|reservasi", lowered):
        subject = _strip_request_phrasing(text) or "aplikasi booking"
        plan = _booking_plan(subject)
    elif re.search(r"landing ?page|company ?profile|website perusahaan", lowered):
        subject = _strip_request_phrasing(text) or "landing page"
        plan = _landing_page_plan(subject, text)
    elif re.search(r"inventory|inventaris|stok|gudang", lowered):
        subject = _strip_request_phrasing(text) or "aplikasi inventory"
        plan = _inventory_plan(subject)
    else:
        subject = _strip_request_phrasing(text) or "kebutuhan yang dijelaskan user"
        plan = _generic_plan(subject)

    plan["constraints"] = []
    if _has_no_coding_constraint(lowered):
        plan["constraints"].append(
            "PLAN ONLY — jangan menulis kode, file, atau workspace"
        )
    plan["constraints"].append(_PLACEHOLDER_RULE)

    # Non-blocking unknowns surface as open questions; nothing blocks planning.
    plan["open_questions"] = list(plan["missing_information"])
    plan["blockers"] = []
    return plan


def apply_plan_update(plan: dict[str, Any], text: str) -> dict[str, Any]:
    """Fold a short refinement ("pakai PostgreSQL aja") into the active plan.

    Returns a NEW plan dict; the input is not mutated.
    """
    updated = {k: (list(v) if isinstance(v, list) else v) for k, v in plan.items()}
    lowered = text.lower()
    decided = False

    for pattern, choice, topic in _TECH_DECISIONS:
        if re.search(pattern, lowered):
            entry = f"{topic}: {choice}"
            constraints = updated.setdefault("constraints", [])
            if entry not in constraints:
                constraints.append(entry)
            # The decision answers related open questions.
            updated["open_questions"] = [
                q for q in updated.get("open_questions", [])
                if topic.split("/")[0].lower() not in q.lower()
                and "stack" not in q.lower()
            ]
            updated["missing_information"] = [
                q for q in updated.get("missing_information", [])
                if topic.split("/")[0].lower() not in q.lower()
                and "stack" not in q.lower()
            ]
            decided = True
            break

    if decided:
        updated["assumptions"] = [
            a for a in updated.get("assumptions", [])
            if "belum ditentukan" not in a.lower()
        ]

    if not decided:
        # Unknown refinement: record verbatim as a bounded constraint note.
        constraints = updated.setdefault("constraints", [])
        note = f"Keputusan user: {text.strip()[:120]}"
        if note not in constraints:
            constraints.append(note)

    return updated


_BRIEF_SECTIONS = (
    ("goal", "GOAL"),
    ("known_requirements", "KNOWN REQUIREMENTS"),
    ("constraints", "CONSTRAINTS/DECISIONS"),
    ("assumptions", "ASSUMPTIONS"),
    ("implementation_steps", "IMPLEMENTATION STEPS"),
    ("open_questions", "OPEN QUESTIONS (unresolved — do NOT invent answers)"),
)

_BRIEF_MAX_CHARS = 1600


def render_plan_brief(plan: dict[str, Any]) -> str:
    """Render the active plan as a bounded brief for the IMPLEMENT handoff."""
    lines: list[str] = []
    for field, header in _BRIEF_SECTIONS:
        value = plan.get(field)
        if not value:
            continue
        if isinstance(value, str):
            lines.append(f"{header}: {value}")
        else:
            lines.append(f"{header}:")
            lines.extend(f"- {item}" for item in value)

    brief = "\n".join(lines)
    if len(brief) > _BRIEF_MAX_CHARS:
        brief = brief[:_BRIEF_MAX_CHARS - 3].rstrip() + "..."
    return brief


# ── Conversational replies (CHAT / NEEDS_INPUT) ──────────────────────────

_GREETING_RE = re.compile(
    r"\b(halo|hallo|hai|hi|hei|hey|hello|pagi|siang|sore|malam)\b", re.IGNORECASE
)
_THANKS_RE = re.compile(
    r"\b(makasih|makasi|terima ?kasih|thanks|thank you|thx|tq)\b", re.IGNORECASE
)
_OPINION_RE = re.compile(
    r"\b(menurutmu|menurut kamu|gimana|bagaimana|apa kabar|bisa apa|kamu siapa)\b",
    re.IGNORECASE,
)
_FIX_REQUEST_RE = re.compile(r"\b(perbaiki|fix|repair|benahi|patch)\b", re.IGNORECASE)
_BUILD_REQUEST_RE = re.compile(r"\b(buat|bikin|buatkan|add|create|tambah)\b", re.IGNORECASE)


def chat_reply(text: str) -> str:
    """A natural, deterministic conversational reply. No tools, no specialists."""
    if _THANKS_RE.search(text):
        return (
            "Sama-sama! 👋 Kalau ada yang mau direncanakan, diteliti, "
            "atau dikerjakan, tinggal bilang saja."
        )
    if _OPINION_RE.search(text):
        return (
            "Aku siap membantu — mulai dari planning, research, coding, "
            "testing, sampai monitoring. Mau mulai dari mana?"
        )
    if _GREETING_RE.search(text):
        return "Halo 👋 Ada yang mau kamu rencanakan atau kerjakan?"
    return (
        "Halo! Aku ATLAS. Ceritakan apa yang mau kamu rencanakan atau "
        "kerjakan, dan aku yang atur specialist-nya."
    )


def needs_input_reply(text: str) -> str:
    """A short, specific clarifying question. No specialists dispatched."""
    if _FIX_REQUEST_RE.search(text):
        return (
            "Mau memperbaiki apa? Sebutkan file, error, atau fitur yang "
            "bermasalah — contoh: \"perbaiki bug login di src/auth.ts\"."
        )
    if _BUILD_REQUEST_RE.search(text):
        return (
            "Mau dibuat apa? Ceritakan hasil yang diinginkan — contoh: "
            "\"buat fungsi greet(name) di src/index.js\" atau "
            "\"buat plan aplikasi booking lapangan\"."
        )
    return (
        "Bisa dijelaskan lebih spesifik apa yang kamu inginkan? "
        "Contoh: \"buat plan aplikasi booking lapangan\" atau "
        "\"jalankan test project ini\"."
    )
