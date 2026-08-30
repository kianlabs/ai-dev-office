"""Real deterministic read-only executor for PULSE - Monitor / DevOps Agent.

PULSE inspects LOCAL runtime / process / project health and returns
deterministic evidence. It is intentionally pure-Python (stdlib only): no
psutil/requests dependency, no sandbox, and no subprocesses — port probes use
``socket``, HTTP probes use ``http.client``, processes use ``/proc``, and log
files are tailed with bounded reads.

PULSE never deploys, restarts, kills, edits code, or modifies the source
project. Monitoring observes; it does not manage lifecycle.

Health semantics:
  * HEALTHY       - every REQUIRED real check passed and no warnings
  * DEGRADED      - required checks passed but non-critical warnings exist
  * UNHEALTHY     - a required process/port/HTTP/workspace check failed
  * NOT_VERIFIED  - no explicit monitoring target was configured
  * INTERRUPTED   - task cancelled while checks were pending

Targets come from ``task.pulse_request`` (explicit structured config) merged
with deterministic parsing of the task text (http(s) URLs, ``port <n>`` and
``host:port`` mentions). Only loopback/local targets are ever probed.
"""

from __future__ import annotations

import asyncio
import http.client
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit as _urlsplit

from ai_dev_agent_core import ExecutionContext, MockRuntime
from ai_dev_shared import AgentEvent, Task
from ai_dev_shared.constants import EventKind, TaskStatus

# Bound/Duration constants keep every probe short-lived and evidence bounded.
_PORT_TIMEOUT = 2.0
_HTTP_TIMEOUT = 3.0
_BODY_LIMIT = 2000          # max HTTP response bytes read
_BODY_PREFIX = 200          # max response bytes surfaced as evidence
_CMD_LIMIT = 120            # max process command chars surfaced
_LOG_TAIL_BYTES = 8192      # max bytes read from the tail of a log file
_LOG_TAIL_LINES = 200       # max tail lines kept for pattern detection
_LOG_SAMPLE = 160           # max chars of a matched log line surfaced
_PROC_SCAN_LIMIT = 4096     # bound the /proc directory scan

_PROCFS = "/proc"

# Loopback-only: PULSE never probes remote hosts.
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Port regex patterns for text-derived targets.
_PORT_PATTERNS = (
    r"\bport\s+(\d{2,5})\b",
    r"\bporta\s+(\d{2,5})\b",
    r"(?:127\.0\.0\.1|localhost):(\d{2,5})\b",
)

_URL_RE = re.compile(
    r"https?://[A-Za-z0-9\-.:\[\]]+(?:/[A-Za-z0-9\-._~?&=/%]*)?",
    re.IGNORECASE,
)

# Obvious runtime error patterns surfaced from log tails. PULSE reports the
# evidence only — it never claims a root cause beyond what the pattern shows.
_LOG_ERROR_PATTERNS = ("ERROR", "FATAL", "Traceback", "Unhandled")

# Secret/credential path hints that must never be read, even when requested.
_SECRET_NAME_HINTS = (
    ".env", ".env.local", ".envrc", "credentials",
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    ".htpasswd", ".netrc", ".npmrc",
    ".pem", ".key", ".p12", ".pfx", ".crt",
)

_REQUIRED_TYPES = {"process", "port", "http", "workspace"}

# Cancellation registry: task_id -> asyncio.Event (PULSE runs no subprocesses,
# so the event is all that is needed to stop the short-lived check loop).
_RUNNING_CANCEL_EVENTS: dict[str, asyncio.Event] = {}


def cancel_pulse_execution(task_id: str) -> bool:
    """Request cancellation of a task's PULSE check loop.

    PULSE spawns no subprocesses, so signalling is merely setting the task's
    cancel event. Returns True if a running PULSE loop was found.
    """
    event = _RUNNING_CANCEL_EVENTS.get(task_id)
    if event is None:
        return False
    event.set()
    _RUNNING_CANCEL_EVENTS.pop(task_id, None)
    return True


def derive_pulse_request(task: Task) -> dict[str, Any]:
    """Merge explicit ``task.pulse_request`` with text-derived targets.

    Text-derived targets: http(s) URLs, ``port <n>`` / ``porta <n>`` mentions,
    and ``127.0.0.1:<port>`` / ``localhost:<port>`` patterns. Processes and log
    files are explicit-configuration only (never guessed from prose).
    """
    text = f"{task.title}\n{task.description}"
    explicit = task.pulse_request or {}

    ports: list[int] = []
    seen_ports: set[int] = set()
    for pattern in _PORT_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            try:
                port = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in seen_ports:
                seen_ports.add(port)
                ports.append(port)

    urls: list[str] = []
    seen_urls: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!?")
        if url not in seen_urls:
            seen_urls.add(url)
            urls.append(url)

    for entry in (explicit.get("ports") or []):
        try:
            port = int(entry)
        except (TypeError, ValueError):
            continue
        if 1 <= port <= 65535 and port not in seen_ports:
            seen_ports.add(port)
            ports.append(port)

    for entry in (explicit.get("health_urls") or []):
        url = str(entry).strip()
        if url not in seen_urls:
            seen_urls.add(url)
            urls.append(url)

    return {
        "expected_processes": list(explicit.get("expected_processes") or []),
        "ports": ports,
        "health_urls": urls,
        "log_files": list(explicit.get("log_files") or []),
    }


class DeterministicPulseExecutor:
    """Read-only local health monitor producing structured pulse_report.

    PULSE is intentionally read-only. It does not deploy, restart services,
    kill processes, modify source code, or dispatch other agents.
    """

    agent_id = "pulse"

    def __init__(self, task: Task, ctx: ExecutionContext) -> None:
        self.task = task
        self.ctx = ctx
        self._cancel_event = asyncio.Event()
        self.r = MockRuntime(task, ctx)
        self.r.agent_id = self.agent_id

    # ------------------------------------------------------------------ paths
    def _workspace_for(self, task: Task) -> Path:
        """Resolve the authoritative workspace (same as SCOUT/FORGE/QA)."""
        from ai_dev_shared.workspace import execution_workspace
        return execution_workspace(task, self.ctx)

    # ------------------------------------------------------------ normalize
    def _normalize_process_entries(
        self,
        entries: list[Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        specs: list[dict[str, Any]] = []
        warnings: list[str] = []
        for entry in entries:
            if isinstance(entry, str):
                specs.append({"name": entry, "cmdline": entry, "pid": None})
                continue
            if isinstance(entry, dict):
                pid = entry.get("pid")
                if pid is not None:
                    try:
                        pid = int(pid)
                    except (TypeError, ValueError):
                        pid = -1
                    if pid < 1:
                        warnings.append(
                            f"proses {entry.get('name', pid)}: pid tidak valid"
                        )
                        continue
                cmd = str(entry.get("cmdline") or "")
                name = str(
                    entry.get("name") or (str(pid) if pid else cmd or "process")
                )
                specs.append({"name": name, "cmdline": cmd, "pid": pid})
                continue
            warnings.append(f"entri expected_processes tidak dikenal: {entry!r}")
        return specs, warnings

    def _normalize_urls(self, urls: list[str]) -> tuple[list[str], list[str]]:
        kept: list[str] = []
        warnings: list[str] = []
        for url in urls:
            try:
                parts = _urlsplit(url)
            except ValueError:
                warnings.append(f"health URL tidak valid: {url}")
                continue
            scheme = (parts.scheme or "").lower()
            hostname = (parts.hostname or "").lower()
            if scheme not in ("http", "https"):
                warnings.append(f"skema tidak didukung (loopback-only): {url}")
                continue
            if hostname not in _LOOPBACK_HOSTS:
                warnings.append(f"host non-loopback ditolak: {url}")
                continue
            if parts.username or parts.password:
                warnings.append(f"URL berisi kredensial, ditolak: {url}")
                continue
            kept.append(url)
        return kept, warnings

    def _normalize_log_paths(
        self,
        entries: list[Any],
        workspace: Path | None,
    ) -> tuple[list[Path], list[str]]:
        paths: list[Path] = []
        warnings: list[str] = []
        for entry in entries:
            raw = str(entry).strip()
            candidate = Path(raw)
            if not candidate.is_absolute() and workspace is not None:
                candidate = workspace / candidate
            try:
                resolved = candidate.resolve()
            except OSError:
                warnings.append(f"log path tidak dapat di-resolve: {raw}")
                continue
            name = resolved.name.lower()
            if any(hint in name for hint in _SECRET_NAME_HINTS) or any(
                hint in part.lower()
                for hint in _SECRET_NAME_HINTS
                for part in resolved.parts
            ):
                warnings.append(f"log path ditolak (berpotensi sensitif): {resolved}")
                continue
            paths.append(resolved)
        return paths, warnings

    # --------------------------------------------------------------- probes
    def _proc_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _proc_cmdline(self, pid: int) -> str:
        try:
            raw = Path(_PROCFS, str(pid), "cmdline").read_bytes()
            return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        except OSError:
            return ""

    def _proc_elapsed(self, pid: int) -> float | None:
        """Second the process has been running (from /proc start time)."""
        try:
            raw = Path(_PROCFS, str(pid), "stat").read_text(errors="replace")
            head = raw.index(")")
            tail = raw[head + 1:].split()
            clk = os.sysconf("SC_CLK_TCK")
            start = int(tail[19])  # field 22 "starttime" (0-based after comm)
            uptime = float(Path("/proc/uptime").read_text().split()[0])
            return round(uptime - start / clk, 1)
        except (OSError, ValueError, IndexError):
            return None

    def _find_process_by_cmdline(self, expected: str) -> tuple[int | None, str, float | None]:
        if not expected:
            return None, "", None
        scanned = 0
        try:
            it = Path(_PROCFS).iterdir()
        except OSError:
            return None, "", None
        for entry in it:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid in (0, 1) or pid == os.getpid():
                continue
            scanned += 1
            if scanned > _PROC_SCAN_LIMIT:
                break
            cmd = self._proc_cmdline(pid)
            if expected in cmd:
                return pid, cmd, self._proc_elapsed(pid)
        return None, "", None

    def _check_process(self, spec: dict[str, Any]) -> dict[str, Any]:
        pid = spec.get("pid")
        name = spec.get("name") or "process"
        expected = spec.get("cmdline")

        if pid is not None:
            running = self._proc_alive(pid)
            cmd = self._proc_cmdline(pid)
            elapsed = self._proc_elapsed(pid) if running else None
            matched = bool(not expected or (expected and expected in cmd))
            ok = running and matched
            evidence: dict[str, Any] = {
                "pid": pid,
                "running": running,
                "command": cmd[:_CMD_LIMIT],
                "elapsed_seconds": elapsed,
            }
            if ok:
                return {
                    "ok": True,
                    "summary": f"Proses {name} berjalan (pid {pid})",
                    "evidence": evidence,
                }
            reason = "tidak berjalan" if not running else "perintah tidak cocok"
            return {
                "ok": False,
                "summary": f"Proses {name} {reason}",
                "evidence": evidence,
            }

        found_pid, cmd, elapsed = self._find_process_by_cmdline(name)
        if found_pid is None or (expected and expected not in cmd):
            return {
                "ok": False,
                "summary": f"Proses {name} tidak terdeteksi",
                "evidence": {
                    "pid": None,
                    "running": False,
                    "command": "",
                    "elapsed_seconds": None,
                },
            }
        return {
            "ok": True,
            "summary": f"Proses {name} berjalan (pid {found_pid})",
            "evidence": {
                "pid": found_pid,
                "running": True,
                "command": cmd[:_CMD_LIMIT],
                "elapsed_seconds": elapsed,
            },
        }

    def _check_port(self, host: str, port: int) -> dict[str, Any]:
        started = time.perf_counter()
        ok = False
        error: str | None = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_PORT_TIMEOUT)
        try:
            sock.connect((host, port))
            ok = True
        except OSError as exc:
            error = exc.strerror or type(exc).__name__
        finally:
            sock.close()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        evidence = {
            "host": host,
            "port": port,
            "reachable": ok,
            "latency_ms": latency_ms,
        }
        if ok:
            return {
                "ok": True,
                "summary": f"Port {port} aktif",
                "evidence": evidence,
            }
        return {
            "ok": False,
            "summary": f"Port {port} tidak merespons ({error})",
            "evidence": evidence,
        }

    def _check_http(self, url: str) -> dict[str, Any]:
        parts = _urlsplit(url)
        scheme = (parts.scheme or "http").lower()
        host = parts.hostname or "127.0.0.1"
        port = parts.port
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        if scheme not in ("http", "https"):
            return {
                "ok": False,
                "summary": f"Deny pemantauan URL non-http(s): {url}",
                "evidence": {"url": url, "status_code": None},
            }

        started = time.perf_counter()
        status_code: int | None = None
        body = b""
        error: str | None = None
        try:
            if scheme == "https":
                conn = http.client.HTTPSConnection(host, port, timeout=_HTTP_TIMEOUT)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=_HTTP_TIMEOUT)
            conn.request("GET", path)
            resp = conn.getresponse()
            status_code = resp.status
            # Bounded read: never hold more than _BODY_LIMIT bytes.
            body = resp.read(_BODY_LIMIT)
            resp.close()
            conn.close()
        except (OSError, http.client.HTTPException) as exc:
            error = exc.strerror or type(exc).__name__
        latency_ms = round((time.perf_counter() - started) * 1000, 2)

        body_text = body.decode("utf-8", "replace")
        body_prefix = re.sub(r"\s+", " ", body_text)[:_BODY_PREFIX]
        evidence = {
            "url": url,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "body_prefix": body_prefix,
            "status": "ok" if status_code is not None and 200 <= status_code < 400 else (
                "unreachable" if status_code is None else str(status_code)
            ),
        }

        if status_code is not None and 200 <= status_code < 400:
            return {
                "ok": True,
                "summary": (
                    f"{path} merespons {status_code}"
                    if status_code == 200
                    else f"{path} merespons {status_code}"
                ),
                "evidence": evidence,
            }
        summary = (
            f"{path} tidak merespons ({error})"
            if status_code is None
            else f"{path} merespons {status_code}"
        )
        return {"ok": False, "summary": summary, "evidence": evidence}

    def _tail_log(self, path: Path) -> tuple[list[str], int]:
        """Read a bounded tail of a log file."""
        size = path.stat().st_size
        start = max(0, size - _LOG_TAIL_BYTES)
        with path.open("rb") as fh:
            fh.seek(start)
            data = fh.read()
        text = data.decode("utf-8", "replace")
        lines = text.splitlines()[-_LOG_TAIL_LINES:]
        return lines, len(text)

    def _check_log(self, path: Path, workspace: Path | None) -> dict[str, Any]:
        base = workspace.resolve() if workspace is not None else None
        runtime = None
        if base is not None:
            runtime = base.parent / ".ado-runtime" / base.name
            if not runtime.is_dir():
                runtime = base.parent / ".ado-runtime"

        if base is None or (path != base and base not in path.parents and
                            runtime is not None and runtime not in path.parents):
            return {
                "ok": False,
                "summary": f"Log di luar area task ditolak: {path}",
                "evidence": {"tail_lines": 0, "matched_patterns": []},
            }

        if not path.is_file():
            return {
                "ok": False,
                "summary": f"File log tidak ditemukan: {path.name}",
                "evidence": {"tail_lines": 0, "matched_patterns": []},
            }

        try:
            lines, bytes_read = self._tail_log(path)
        except OSError as exc:
            return {
                "ok": False,
                "summary": f"Log tidak dapat dibaca: {exc.strerror or type(exc).__name__}",
                "evidence": {"tail_lines": 0, "matched_patterns": []},
            }

        matched = [
            pattern
            for pattern in _LOG_ERROR_PATTERNS
            if any(pattern in line for line in lines)
        ]
        sample = ""
        if matched:
            for line in lines:
                if any(pattern in line for pattern in matched):
                    sample = line[:_LOG_SAMPLE]
                    break

        evidence = {
            "tail_lines": len(lines),
            "bytes_read": bytes_read,
            "matched_patterns": matched,
            "sample": sample,
        }
        if matched:
            return {
                "ok": False,
                "summary": f"Log {path.name} mengandung {', '.join(matched)}",
                "evidence": evidence,
            }
        return {
            "ok": True,
            "summary": f"Log {path.name} bersih ({len(lines)} baris terakhir)",
            "evidence": evidence,
        }

    def _check_workspace(self, workspace: Path | None) -> dict[str, Any] | None:
        """Workspace consistency check (only when there is something to verify).

        Returns ``None`` (skip) for pure-monitoring tasks whose disposable
        (empty mode) workspace is empty or absent — nothing project-specific was
        prepared, so there is nothing to verify. An isolated git-worktree /
        copy that is missing or empty is a real anomaly and fails the check."""
        shared = getattr(self.ctx, "shared", None) or {}
        meta = shared.get("workspace_meta")
        has_project = (
            meta is not None
            and getattr(meta, "mode", "empty") in ("git-worktree", "copy")
        )
        if workspace is None:
            return None
        if not workspace.is_dir():
            if not has_project:
                return None
            return {
                "ok": False,
                "summary": "Workspace task tidak ditemukan",
                "evidence": {"entries": 0},
            }
        entries = [
            p for p in workspace.iterdir()
            if p.name != ".git" and ".ado-runtime" not in p.parts
        ]
        if entries:
            return {
                "ok": True,
                "summary": f"Workspace konsisten ({len(entries)} entri)",
                "evidence": {"entries": len(entries)},
            }
        if has_project:
            return {
                "ok": False,
                "summary": "Workspace task kosong",
                "evidence": {"entries": 0},
            }
        return None

    # ------------------------------------------------------------- assemble
    def _build_specs(
        self,
        request: dict[str, Any],
        workspace: Path,
    ) -> tuple[list[tuple[Any, ...]], list[str]]:
        specs: list[tuple[Any, ...]] = []
        warnings: list[str] = []

        procs, proc_warnings = self._normalize_process_entries(
            request.get("expected_processes") or []
        )
        warnings.extend(proc_warnings)
        for spec in procs:
            specs.append(("process", spec, spec.get("name") or "process",
                          str(spec.get("name") or spec.get("cmdline") or "")))

        for port in request.get("ports") or []:
            if not (1 <= int(port) <= 65535):
                warnings.append(f"port di luar rentang ditolak: {port}")
                continue
            specs.append(("port", ("127.0.0.1", int(port)), f"port {port}",
                          f"127.0.0.1:{port}"))

        urls, url_warnings = self._normalize_urls(request.get("health_urls") or [])
        warnings.extend(url_warnings)
        for url in urls:
            specs.append(("http", url, url, url))

        logs, log_warnings = self._normalize_log_paths(
            request.get("log_files") or [], workspace,
        )
        warnings.extend(log_warnings)
        for log_path in logs:
            specs.append(("log", log_path, f"log {log_path.name}", str(log_path)))

        ws_check = self._check_workspace(workspace)
        if ws_check is not None:
            specs.append(("workspace", workspace, "workspace", str(workspace)))

        return specs, warnings

    async def _run_specs(
        self,
        specs: list[tuple[Any, ...]],
        workspace: Path,
    ) -> tuple[list[dict[str, Any]], bool]:
        checks: list[dict[str, Any]] = []
        cancelled = False
        for spec in specs:
            if self._cancel_event.is_set():
                cancelled = True
                break
            typ, payload, name, target = spec
            if typ == "process":
                result = await asyncio.to_thread(self._check_process, payload)
            elif typ == "port":
                host, port = payload
                result = await asyncio.to_thread(self._check_port, host, port)
            elif typ == "http":
                result = await asyncio.to_thread(self._check_http, payload)
            elif typ == "log":
                result = await asyncio.to_thread(self._check_log, payload, workspace)
            elif typ == "workspace":
                result = self._check_workspace(payload)
            else:
                continue
            if result is None:
                continue
            result.update({"name": name, "type": typ, "target": target})
            checks.append(result)
        return checks, cancelled

    def _finalize(
        self,
        checks: list[dict[str, Any]],
        warnings: list[str],
        workspace: Path,
        cancelled: bool,
    ) -> dict[str, Any]:
        if cancelled:
            return {
                "status": "INTERRUPTED",
                "verified": bool(checks),
                "workspace_path": str(workspace),
                "checks": checks,
                "warnings": warnings,
                "summary": "PULSE dibatalkan oleh user",
            }

        if not checks:
            return {
                "status": "NOT_VERIFIED",
                "verified": False,
                "workspace_path": str(workspace),
                "checks": [],
                "warnings": warnings,
                "summary": "Tidak ada target health yang dikonfigurasi",
            }

        failed_required = [
            c for c in checks
            if c.get("type") in _REQUIRED_TYPES and not c["ok"]
        ]
        failed_optional = [
            c for c in checks
            if c.get("type") not in _REQUIRED_TYPES and not c["ok"]
        ]

        for check in failed_optional:
            if check["summary"] not in warnings:
                warnings.append(check["summary"])

        if failed_required:
            return {
                "status": "UNHEALTHY",
                "verified": True,
                "workspace_path": str(workspace),
                "checks": checks,
                "warnings": warnings,
                "summary": (
                    "Health check gagal: "
                    + ", ".join(c["summary"] for c in failed_required)
                ),
            }

        if warnings:
            return {
                "status": "DEGRADED",
                "verified": True,
                "workspace_path": str(workspace),
                "checks": checks,
                "warnings": warnings,
                "summary": "Health check lolos dengan peringatan",
            }

        return {
            "status": "HEALTHY",
            "verified": True,
            "workspace_path": str(workspace),
            "checks": checks,
            "warnings": [],
            "summary": "Semua health check real lolos",
        }

    # ---------------------------------------------------------------- main
    async def execute(
        self,
        task: Task,
        ctx: ExecutionContext,
    ) -> AsyncIterator[AgentEvent]:
        from ai_dev_agent_pulse.executor import _RUNNING_CANCEL_EVENTS

        r = self.r
        workspace = self._workspace_for(task)

        _RUNNING_CANCEL_EVENTS[task.id] = self._cancel_event
        try:
            yield await r.tick(
                r.working(
                    "Memeriksa runtime lokal",
                    task_status=TaskStatus.RUNNING,
                )
            )

            request = derive_pulse_request(task)
            specs, warnings = self._build_specs(request, workspace)
            checks, cancelled = await self._run_specs(specs, workspace)

            if not cancelled:
                for check in checks:
                    ok = check["ok"]
                    if ok:
                        yield await r.tick(r.say(check["summary"]))
                    else:
                        yield await r.tick(
                            r.say(f"{check['summary']} (tidak sehat)")
                        )
                for warning in warnings:
                    if warning not in {c["summary"] for c in checks}:
                        yield await r.tick(r.say(f"Catatan: {warning}"))

            report = self._finalize(checks, warnings, workspace, cancelled)
            ctx.shared["health"] = report
            ctx.shared["pulse_report"] = report

            status_line = {
                "HEALTHY": "Runtime sehat",
                "DEGRADED": "Runtime sehat dengan peringatan",
                "UNHEALTHY": "Pelayanan tidak sehat",
                "NOT_VERIFIED": "Tidak ada target health",
                "INTERRUPTED": "PULSE dibatalkan oleh user",
            }.get(report["status"], report["status"])

            yield await r.tick(
                r.health(
                    f"Health: {report['status']} — {report['summary']}",
                    meta={
                        "pulse_report": report,
                        "health": report,
                    },
                )
            )

            yield await r.tick(r.idle("Idle"))
        finally:
            _RUNNING_CANCEL_EVENTS.pop(task.id, None)