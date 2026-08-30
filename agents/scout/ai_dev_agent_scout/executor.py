"""Real deterministic SCOUT executor.

SCOUT is a READ-ONLY research specialist. It inspects the repository structure
and produces a bounded structured brief that FORGE consumes.

Design principles:
- Local-first: inspect actual project files before considering external sources.
- Read-only: never writes, edits, runs shell commands, or mutates state.
- Bounded: reads only relevant files; never dumps entire repo into context.
- Honest: only reports what was actually found on disk.
- Token-efficient: produces a concise structured brief, not a raw transcript.

Security:
- No subprocess execution.
- No ~/.ssh, .env, or credential files are read.
- File reads are bounded (max _FILE_READ_LIMIT bytes per file).
- Directory traversal is bounded (max _MAX_FILES_SCANNED entries).
- External web research only when task explicitly requests it (never by default).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import AsyncIterator

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import AgentStatus, TaskStatus

logger = logging.getLogger("ai_dev_agent_scout")

# Bounds on file system inspection (prevents accidental huge context injection).
_FILE_READ_LIMIT = 4_000       # bytes per individual file read
_MAX_FILES_SCANNED = 200       # max directory entries examined
_MAX_RELEVANT_FILES = 10       # max files reported in brief
_MAX_SUMMARY_LEN = 1_200       # chars for the brief summary field

# Config/manifest files that carry high-value structural information.
_MANIFEST_FILES = (
    "package.json",
    "pyproject.toml",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
    "tsconfig.json",
    "vite.config.ts",
    "vite.config.js",
    "next.config.ts",
    "next.config.js",
    "README.md",
)

# File patterns that must never be read regardless of task content.
_BLOCKED_NAMES = frozenset({
    ".env", ".env.local", ".env.production", ".env.development",
    ".envrc", "credentials", "secrets.json", "secrets.yaml",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
_BLOCKED_SUFFIXES = frozenset({
    ".pem", ".key", ".p12", ".pfx", ".crt", ".cer",
})

# Task-text phrases that signal the user explicitly wants external docs/web
# research. Without these, SCOUT stays local.
_EXTERNAL_RESEARCH_TRIGGERS = (
    "documentation", "docs", "research",
    "best library", "best approach", "compare library",
    "latest api", "latest version", "dependensi terbaru",
    "dokumentasi", "riset", "bandingkan library",
    "library terbaik", "pendekatan terbaik",
)


def _is_blocked(path: Path) -> bool:
    """True if a file should never be read (credentials, secrets, keys)."""
    return (
        path.name in _BLOCKED_NAMES
        or path.suffix.lower() in _BLOCKED_SUFFIXES
        or path.name.startswith(".env")
    )


def _task_text(task: Task) -> str:
    return f"{task.title}\n{task.description}".lower()


def _wants_external(task: Task) -> bool:
    text = _task_text(task)
    return any(trigger in text for trigger in _EXTERNAL_RESEARCH_TRIGGERS)


def _repo_root() -> Path:
    """Best-effort resolution of the ai-dev-office repo root."""
    return Path.home() / "ai-dev-office"


def _bounded_read(path: Path) -> str:
    """Read up to _FILE_READ_LIMIT bytes from a file. Returns empty on error."""
    if _is_blocked(path):
        return ""
    try:
        raw = path.read_bytes()[:_FILE_READ_LIMIT]
        return raw.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _workspace_for(task: Task) -> Path:
    """Same workspace path FORGE will write to."""
    return Path.home() / "ai-dev-office" / "workspaces" / task.id[:12]


class RealScoutExecutor:
    """Real read-only SCOUT: inspects the project, produces a structured brief.

    Dispatched by ATLAS before FORGE. Writes only to ``ctx.shared["research"]``.
    Never touches the filesystem destructively.
    """

    agent_id = "scout"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    async def execute(
        self, task: Task, ctx: ExecutionContext
    ) -> AsyncIterator[AgentEvent]:
        r = MockRuntime(task, ctx)
        r.agent_id = self.agent_id

        yield await r.tick(
            r.working("Memeriksa struktur repository", task_status=TaskStatus.RUNNING)
        )

        # ── 1. Locate workspace or fall back to repo root ──────────────────
        workspace = _workspace_for(task)
        if workspace.is_dir():
            scan_root = workspace
            scope = "workspace"
        else:
            scan_root = _repo_root()
            scope = "repository"

        yield await r.tick(r.say(f"Scan root: {scan_root} (scope={scope})"))

        if self._cancel_requested:
            yield await r.tick(r.failure("SCOUT dibatalkan"))
            yield await r.tick(r.result(TaskStatus.INTERRUPTED, "SCOUT dibatalkan"))
            return

        # ── 2. Collect file tree (bounded) ─────────────────────────────────
        file_tree = _scan_tree(scan_root)
        yield await r.tick(
            r.say(f"Ditemukan {len(file_tree)} berkas (batas {_MAX_FILES_SCANNED})")
        )

        # ── 3. Read manifest / config files ────────────────────────────────
        yield await r.tick(r.working("Membaca konfigurasi project"))
        manifests = _read_manifests(scan_root)
        for name in manifests:
            yield await r.tick(r.say(f"Membaca {name}"))

        # ── 4. Identify relevant files based on task intent ────────────────
        yield await r.tick(r.working("Mengidentifikasi berkas relevan"))
        relevant = _identify_relevant(task, file_tree, scan_root)
        for rel_path in relevant[:_MAX_RELEVANT_FILES]:
            yield await r.tick(r.say(f"Berkas relevan: {rel_path}"))

        if self._cancel_requested:
            yield await r.tick(r.failure("SCOUT dibatalkan"))
            yield await r.tick(r.result(TaskStatus.INTERRUPTED, "SCOUT dibatalkan"))
            return

        # ── 5. Read relevant file snippets (bounded) ───────────────────────
        yield await r.tick(r.working("Membaca cuplikan berkas relevan"))
        file_snippets = _read_snippets(scan_root, relevant)

        # ── 6. Inspect dependencies ────────────────────────────────────────
        deps_summary = _extract_deps(manifests)
        if deps_summary:
            yield await r.tick(r.say(f"Dependensi terdeteksi: {deps_summary[:200]}"))

        # ── 7. Optional: external research trigger check ───────────────────
        external_note = ""
        if _wants_external(task):
            yield await r.tick(r.working("Tugas meminta riset eksternal (ops only)"))
            # Phase 3: local-first only. External web research deferred to
            # Phase 4 (Hermes-backed SCOUT for ambiguous tasks). For now we
            # note the intent and return local findings.
            external_note = (
                "Riset eksternal diminta tetapi belum diaktifkan (Phase 3). "
                "Hasil dari inspeksi lokal saja."
            )
            yield await r.tick(r.say(external_note))

        # ── 8. Build structured scout_report ──────────────────────────────
        yield await r.tick(r.waiting("Menyusun laporan riset untuk ATLAS"))

        summary = _build_summary(task, relevant, manifests, deps_summary, file_snippets)
        if external_note:
            summary += f" [{external_note}]"

        scout_report = {
            # Human-readable summary for FORGE's prompt context.
            "summary": summary,
            # Relative paths of files worth reading — FORGE may use these.
            "relevant_files": relevant[:_MAX_RELEVANT_FILES],
            # Implementation guidance (based on local evidence only).
            "recommendations": _build_recommendations(task, relevant, manifests),
            # Hard constraints FORGE must observe.
            "constraints": [
                "Work only inside /workspace",
                "Do not modify files outside /workspace",
                "No git push, no deploy, no sudo",
                "Preserve existing project structure unless task requires change",
            ],
            # Evidence trail: what was actually inspected.
            "references": [
                f"file:{f}" for f in relevant[:5]
            ] + [
                f"manifest:{m}" for m in list(manifests)[:3]
            ],
            # Metadata
            "scope": scope,
            "files_scanned": len(file_tree),
            "external_research": bool(external_note),
        }

        # Write to shared context — the ATLAS→FORGE channel.
        ctx.shared["research"] = scout_report

        yield await r.tick(
            r.say(
                f"Riset selesai. Berkas relevan: "
                + ", ".join(relevant[:5] or ["(tidak ada)"]),
                meta={"scout_report": scout_report, "structured": True},
            )
        )

        yield await r.tick(r.idle("Idle"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scan_tree(root: Path) -> list[str]:
    """Return relative paths of files under root, bounded."""
    results: list[str] = []
    try:
        for p in root.rglob("*"):
            if len(results) >= _MAX_FILES_SCANNED:
                break
            if not p.is_file():
                continue
            # Skip hidden dirs, build caches, node_modules.
            parts = p.relative_to(root).parts
            if any(
                part.startswith(".") or part in ("node_modules", "__pycache__", ".git",
                                                  "dist", "build", ".next", "out")
                for part in parts
            ):
                continue
            results.append(str(p.relative_to(root)))
    except OSError:
        pass
    return results


def _read_manifests(root: Path) -> dict[str, str]:
    """Read high-value manifest/config files, bounded."""
    out: dict[str, str] = {}
    for name in _MANIFEST_FILES:
        p = root / name
        if p.is_file():
            content = _bounded_read(p)
            if content:
                out[name] = content
    return out


def _identify_relevant(task: Task, file_tree: list[str], root: Path) -> list[str]:
    """Score files by relevance to the task; return top matches."""
    text = _task_text(task)

    # Extract keywords from task (strip common stop-words).
    words = set(re.findall(r"[a-z][a-z0-9_-]{2,}", text))
    stop = {"dan", "yang", "untuk", "dengan", "dari", "tidak", "ini", "itu",
            "atau", "the", "and", "for", "with", "from", "that", "this",
            "have", "akan", "jangan", "setelah", "pada", "dalam", "lakukan",
            "harus", "bisa", "juga", "lain", "file", "buat", "tugas",
            "gunakan", "ubah", "berdasarkan", "hasil", "lebih", "semua"}
    keywords = words - stop

    scored: list[tuple[int, str]] = []
    for rel in file_tree:
        low = rel.lower()
        score = sum(1 for kw in keywords if kw in low)
        # Boost important file types.
        if low.endswith((".ts", ".tsx", ".py", ".js", ".jsx")):
            score += 1
        if "test" in low or "spec" in low:
            score += 1
        if "config" in low or "index" in low or "main" in low:
            score += 1
        scored.append((score, rel))

    scored.sort(key=lambda x: -x[0])
    return [rel for _, rel in scored if _ > 0][:_MAX_RELEVANT_FILES]


def _read_snippets(root: Path, relevant: list[str]) -> dict[str, str]:
    """Read first _FILE_READ_LIMIT bytes of each relevant file."""
    out: dict[str, str] = {}
    for rel in relevant[:_MAX_RELEVANT_FILES]:
        p = root / rel
        content = _bounded_read(p)
        if content:
            out[rel] = content
    return out


def _extract_deps(manifests: dict[str, str]) -> str:
    """Extract a short dependency summary from manifests."""
    parts: list[str] = []
    pkg = manifests.get("package.json", "")
    if pkg:
        try:
            data = json.loads(pkg)
            deps = list(data.get("dependencies", {}).keys())[:10]
            dev_deps = list(data.get("devDependencies", {}).keys())[:5]
            if deps:
                parts.append("deps: " + ", ".join(deps))
            if dev_deps:
                parts.append("devDeps: " + ", ".join(dev_deps))
        except (json.JSONDecodeError, AttributeError):
            pass
    pyproject = manifests.get("pyproject.toml", "")
    if pyproject:
        found = re.findall(r'"([a-zA-Z0-9_-]+)"\s*=', pyproject)[:8]
        if found:
            parts.append("py-deps: " + ", ".join(found))
    req = manifests.get("requirements.txt", "")
    if req:
        lines = [l.strip().split("==")[0].split(">=")[0] for l in req.splitlines()
                 if l.strip() and not l.startswith("#")][:8]
        if lines:
            parts.append("py-requirements: " + ", ".join(lines))
    return "; ".join(parts)


def _build_summary(
    task: Task,
    relevant: list[str],
    manifests: dict[str, str],
    deps_summary: str,
    snippets: dict[str, str],
) -> str:
    """Concise implementation-focused summary (bounded)."""
    parts: list[str] = []
    if manifests:
        parts.append(f"Manifests ditemukan: {', '.join(list(manifests)[:4])}")
    if deps_summary:
        parts.append(deps_summary[:300])
    if relevant:
        parts.append(f"Berkas relevan: {', '.join(relevant[:5])}")
    else:
        parts.append("Tidak ada berkas relevan terdeteksi di workspace")
    summary = ". ".join(parts)
    if len(summary) > _MAX_SUMMARY_LEN:
        summary = summary[:_MAX_SUMMARY_LEN].rstrip() + "…"
    return summary


def _build_recommendations(
    task: Task,
    relevant: list[str],
    manifests: dict[str, str],
) -> list[str]:
    """Evidence-based implementation recommendations."""
    recs: list[str] = []
    text = _task_text(task)

    has_pkg = "package.json" in manifests
    has_ts = any(f.endswith((".ts", ".tsx")) for f in relevant)
    has_py = any(f.endswith(".py") for f in relevant)
    has_tests = any("test" in f.lower() or "spec" in f.lower() for f in relevant)

    if has_pkg and has_ts:
        recs.append("Project adalah TypeScript/Node — gunakan sintaks TypeScript")
    elif has_py:
        recs.append("Project adalah Python — ikuti konvensi Python yang ada")
    if has_tests:
        recs.append("Test sudah ada — pastikan perubahan tidak merusak test yang ada")
    if relevant:
        recs.append(f"Prioritaskan perubahan di: {', '.join(relevant[:3])}")
    else:
        recs.append("Buat file baru sesuai permintaan task di dalam /workspace")

    # Bound to 5 recommendations.
    return recs[:5]
