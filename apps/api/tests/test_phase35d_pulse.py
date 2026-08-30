"""
Regression tests for Phase 4 — REAL PULSE local monitoring.

PULSE must inspect real local runtime/process/project health with
deterministic evidence (pure stdlib: socket / http.client / /proc), be
read-only, use the same ``workspace_meta.workspace_path`` as SCOUT/FORGE/QA,
route only on explicit health requests, cancel cleanly, and return
HEALTHY / DEGRADED / UNHEALTHY / NOT_VERIFIED / INTERRUPTED.

Run:  .venv/bin/python3 -m pytest apps/api/tests/test_phase35d_pulse.py -v
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_dev_agent_atlas.planner import build_role_aware_plan
from ai_dev_agent_core import AgentRegistry, ExecutionContext, OrchestrationEngine
from ai_dev_agent_core.mock_content import classify_intent
from ai_dev_agent_pulse.mock import MockPulseExecutor
from ai_dev_agent_pulse.executor import (
    DeterministicPulseExecutor,
    cancel_pulse_execution,
    derive_pulse_request,
)
from ai_dev_shared import AgentEvent, EventKind, Task, TaskStatus
from ai_dev_shared.workspace import WorkspaceMeta, execution_workspace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _home_tmp(prefix: str = ".ado-pulse-") -> Path:
    return Path(__import__("tempfile").mkdtemp(prefix=prefix, dir=Path.home()))


def _run(coro):
    return asyncio.run(coro)


async def _async_broadcast(_message):
    return None


def _collect(executor, task: Task, ctx: ExecutionContext):
    """Run an executor to completion; return (events, health report)."""
    events: list[AgentEvent] = []

    async def go():
        async for ev in executor.execute(task, ctx):
            events.append(ev)

    _run(go())
    return events, ctx.shared.get("health")


def _base_ctx(task: Task, workspace_root: Path | None = None,
              meta: WorkspaceMeta | None = None) -> ExecutionContext:
    ctx = ExecutionContext(
        task=task,
        settings={"forge_workspace_root": str(workspace_root)} if workspace_root else {},
        registry=AgentRegistry(),
    )
    if meta is not None:
        ctx.shared["workspace_meta"] = meta
    return ctx


# ---------------------------------------------------------------------------
# Test HTTP / port fixtures
# ---------------------------------------------------------------------------

class _HealthHandler(BaseHTTPRequestHandler):
    """/health -> 200 JSON; /big -> bounded large body; else 404."""

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/big":
            body = b"x" * 40_000
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture()
def http_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _listening_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    sock.close()
    return port


# ---------------------------------------------------------------------------
# 1. Factory wiring: real by default, mock fallback
# ---------------------------------------------------------------------------

def test_pulse_real_executor_wired_by_default():
    from ai_dev_api.agents import build_registry

    registry = build_registry()
    task = Task(title="cek port", description="cek port 8080")
    ctx = ExecutionContext(task=task, settings={}, registry=registry)
    executor = registry.executor_for("pulse", task, ctx)
    assert isinstance(executor, DeterministicPulseExecutor)


def test_pulse_mock_fallback_still_works(monkeypatch):
    from ai_dev_api.agents import build_registry
    from ai_dev_api.config import settings

    monkeypatch.setattr(settings, "pulse_mode", "mock")
    registry = build_registry()
    task = Task(title="tags", description="monitor dev")
    ctx = ExecutionContext(task=task, settings={}, registry=registry)
    executor = registry.executor_for("pulse", task, ctx)
    assert isinstance(executor, MockPulseExecutor)

    produced = []

    async def go():
        async for _ in executor.execute(task, ctx):
            pass

    _run(go())


# ---------------------------------------------------------------------------
# 3. No target -> NOT_VERIFIED
# ---------------------------------------------------------------------------

def test_no_target_returns_not_verified():
    root = _home_tmp()
    try:
        task = Task(title="Riset depan pintu", description="jelaskan struktur kode")
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        events, report = _collect(executor, task, ctx)

        assert report["status"] == "NOT_VERIFIED"
        assert report["verified"] is False
        assert report["checks"] == []
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 4/7. Port checks
# ---------------------------------------------------------------------------

def test_local_port_reachable_healthy():
    root = _home_tmp()
    port = _listening_port()
    try:
        with socket.socket() as keep:
            keep.bind(("127.0.0.1", port))
            keep.listen(1)
            task = Task(title="cek port", pulse_request={"ports": [port]})
            ctx = _base_ctx(task, root)
            executor = DeterministicPulseExecutor(task, ctx)
            _, report = _collect(executor, task, ctx)

            assert report["status"] == "HEALTHY"
            assert report["verified"] is True
            check = report["checks"][0]
            assert check["type"] == "port"
            assert check["target"] == f"127.0.0.1:{port}"
            assert check["ok"] is True
            assert check["evidence"]["reachable"] is True
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # Unreachable port is UNHEALTHY.
    root = _home_tmp()
    try:
        closed = _listening_port()
        task = Task(title="cek port", pulse_request={"ports": [closed]})
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        assert report["status"] == "UNHEALTHY"
        assert report["verified"] is True
        assert report["checks"][0]["ok"] is False
        assert report["checks"][0]["evidence"]["reachable"] is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_closed_port_unhealthy():
    root = _home_tmp()
    try:
        closed = _listening_port()
        task = Task(title="cek port", pulse_request={"ports": [closed]})
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)
        assert report["status"] == "UNHEALTHY"
        assert report["verified"] is True
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 6/7/8. HTTP checks + bounded body
# ---------------------------------------------------------------------------

def test_local_http_200_healthy(http_server):
    root = _home_tmp()
    try:
        port = http_server.server_address[1]
        task = Task(
            title="cek health",
            pulse_request={"health_urls": [f"http://127.0.0.1:{port}/health"]},
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        assert report["status"] == "HEALTHY"
        assert report["verified"] is True
        http_check = next(c for c in report["checks"] if c["type"] == "http")
        assert http_check["ok"] is True
        assert http_check["evidence"]["status_code"] == 200
        assert http_check["evidence"]["latency_ms"] >= 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_local_http_failure_unhealthy():
    root = _home_tmp()
    try:
        dead = _listening_port()
        task = Task(
            title="cek health",
            pulse_request={"health_urls": [f"http://127.0.0.1:{dead}/health"]},
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        assert report["status"] == "UNHEALTHY"
        assert report["verified"] is True
        http_check = next(c for c in report["checks"] if c["type"] == "http")
        assert http_check["ok"] is False
        assert http_check["evidence"]["status_code"] is None
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_http_body_is_bounded(http_server):
    root = _home_tmp()
    try:
        port = http_server.server_address[1]
        task = Task(
            title="cek health",
            pulse_request={"health_urls": [f"http://127.0.0.1:{port}/big"]},
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        check = next(c for c in report["checks"] if c["type"] == "http")
        body_prefix = check["evidence"].get("body_prefix", "")
        assert isinstance(body_prefix, str)
        # Full body is 40KB; evidence prefix must be far smaller and bounded.
        assert len(body_prefix) <= 200
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 9/10. Process checks (PID + missing)
# ---------------------------------------------------------------------------

def test_explicit_process_pid_detected():
    root = _home_tmp()
    marker_pid: int | None = None
    try:
        code = f"import time; time.sleep(600)  # {uuid.uuid4().hex}"
        proc = subprocess.Popen([sys.executable, "-c", code])
        marker_pid = proc.pid
        task = Task(
            title="cek proses",
            pulse_request={
                "expected_processes": [{"name": "worker", "pid": proc.pid}]
            },
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        check = next(c for c in report["checks"] if c["type"] == "process")
        assert check["ok"] is True
        assert check["evidence"]["pid"] == proc.pid
        assert check["evidence"]["running"] is True
        assert "worker" in check["summary"]
        assert check["evidence"]["command"] != ""
    finally:
        if marker_pid is not None:
            try:
                os.kill(marker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        shutil.rmtree(root, ignore_errors=True)


def test_missing_process_detected():
    root = _home_tmp()
    try:
        exited = subprocess.run([sys.executable, "-c", "pass"]).returncode
        assert exited == 0
        # Use a pid that is no longer running: spawn + let it die, then probe.
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait(timeout=5)
        task = Task(
            title="cek proses",
            pulse_request={
                "expected_processes": [{"name": "ghost", "pid": dead_pid}]
            },
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        check = next(c for c in report["checks"] if c["type"] == "process")
        assert check["ok"] is False
        assert check["evidence"]["running"] is False
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 11/12. Log checks
# ---------------------------------------------------------------------------

def _log_task(root: Path, text: str, task_id: str = "112233445566778899aabb"):
    task = Task(
        id=task_id,
        title="cek log",
        pulse_request={"log_files": ["<placeholder>"]},
    )
    ctx = _base_ctx(task, root)
    ws = Path(execution_workspace(task, ctx))
    ws.mkdir(parents=True, exist_ok=True)
    log = ws / "runtime.log"
    log.write_text(text)
    return task, ctx, log, ws


def test_log_tail_detects_error_pattern():
    root = _home_tmp()
    try:
        task, ctx, log, ws = _log_task(
            root,
            "info: starting\n"
            "ERROR: connection reset by peer\n"
            "warn: retrying\n",
        )
        task.pulse_request = {"log_files": [str(log)]}
        executor = DeterministicPulseExecutor(task, ctx)
        events, report = _collect(executor, task, ctx)

        check = next(c for c in report["checks"] if c["type"] == "log")
        assert check["ok"] is False
        assert "ERROR" in check["evidence"]["matched_patterns"]
        assert check["evidence"]["bytes_read"] <= 8192
        assert "ERROR" in check["evidence"]["sample"]
        # Required checks passed; the log warning downgrades -> DEGRADED.
        assert report["status"] == "DEGRADED"
        assert report["verified"] is True
        assert any("ERROR" in w for w in report["warnings"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_clean_log_tail_is_healthy():
    root = _home_tmp()
    try:
        task, ctx, log, ws = _log_task(
            root, "info: all good\ninfo: still fine\n"
        )
        task.pulse_request = {"log_files": [str(log)]}
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        check = next(c for c in report["checks"] if c["type"] == "log")
        assert check["ok"] is True
        assert check["evidence"]["matched_patterns"] == []
        assert report["status"] in ("HEALTHY", "DEGRADED")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_secret_log_paths_rejected():
    root = _home_tmp()
    try:
        secret = Path.home() / ".env"
        task = Task(
            title="cek log",
            pulse_request={"log_files": [str(secret)]},
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        # The secret path is never probed: no log check targets it.
        assert all(c["type"] != "log" for c in report["checks"])
        assert any(str(secret) in w for w in report["warnings"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 13/11. Workspace integration
# ---------------------------------------------------------------------------

def test_workspace_path_uses_workspace_meta():
    root = _home_tmp()
    try:
        ws = root / uuid.uuid4().hex[:12]
        ws.mkdir(parents=True)
        (ws / "app.js").write_text("const x = 1\n")
        meta = WorkspaceMeta(
            task_id="aa" * 16,
            workspace_path=ws,
            source_project=None,
            mode="git-worktree",
        )
        port = _listening_port()
        task = Task(
            title="cek health",
            pulse_request={"health_urls": [f"http://127.0.0.1:{port}/health"]},
        )
        ctx = _base_ctx(task, root, meta=meta)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)

        assert report["workspace_path"] == str(ws)
        assert report["workspace_path"] == str(execution_workspace(task, ctx))
        ws_check = next(c for c in report["checks"] if c["type"] == "workspace")
        assert ws_check["ok"] is True
        assert ws_check["target"] == str(ws)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 14. No arbitrary port scanning
# ---------------------------------------------------------------------------

def test_no_arbitrary_port_scanning():
    root = _home_tmp()
    try:
        port = _listening_port()
        task = Task(
            title="cek service",
            description=f"periksa http://127.0.0.1:{port}/health",
        )
        request = derive_pulse_request(task)
        assert request["ports"] == [port]
        assert request["health_urls"] == [f"http://127.0.0.1:{port}/health"]

        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        _, report = _collect(executor, task, ctx)
        targets = [c["target"] for c in report["checks"] if c["type"] == "port"]
        assert targets == [f"127.0.0.1:{port}"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 15. Read-only: no subprocesses, no kill/restart
# ---------------------------------------------------------------------------

def test_read_only_no_subprocess_no_kill(http_server):
    root = _home_tmp()
    port = http_server.server_address[1]
    kills: list[int] = []
    marker_pid: int | None = None

    real_kill = os.kill

    def recording_kill(pid, sig, *a, **kw):
        kills.append(int(sig))
        return real_kill(pid, sig)

    try:
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
        marker_pid = sleeper.pid
        task = Task(
            title="cek health & proses",
            pulse_request={
                "ports": [port],
                "health_urls": [f"http://127.0.0.1:{port}/health"],
                "expected_processes": [{"name": "worker", "pid": sleeper.pid}],
            },
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=AssertionError("PULSE must not spawn subprocesses"),
        ), patch("os.kill", side_effect=recording_kill):
            _, report = _collect(executor, task, ctx)

        assert report["status"] == "HEALTHY"
        # Existence probes only (signal 0) — never a kill/restart signal.
        assert len(kills) == 1 and kills == [0]
    finally:
        if marker_pid is not None:
            try:
                os.kill(marker_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------------------
# 16/17. Planner routing
# ---------------------------------------------------------------------------

def _plan(text: str):
    title = text.split("\n")[0].strip()
    task = Task(title=title, description=text)
    return build_role_aware_plan(task, classify_intent(task))


@pytest.mark.parametrize(
    "text",
    [
        "Gunakan PULSE.\nPeriksa apakah service lokal di "
        "http://127.0.0.1:8123/health sehat.",
        "cek port 8080",
        "check health",
        "verify service localhost",
    ],
)
def test_planner_routes_explicit_health_to_pulse(text):
    plan = _plan(text)
    assert plan.agents == ("pulse",)


def test_planner_does_not_add_pulse_for_ordinary_task():
    plan = _plan("fix the frontend login bug so it stops crashing")
    assert plan.agents == ("forge", "qa")


# ---------------------------------------------------------------------------
# 18. Cancellation
# ---------------------------------------------------------------------------

def test_cancel_registry_unknown_task_returns_false():
    assert cancel_pulse_execution("does-not-exist-000") is False


def test_cancellation_stops_pending_checks(http_server):
    from ai_dev_agent_pulse.executor import _RUNNING_CANCEL_EVENTS

    root = _home_tmp()
    try:
        port = http_server.server_address[1]
        task = Task(
            title="cek service",
            pulse_request={
                "ports": [port],
                "health_urls": [f"http://127.0.0.1:{port}/health"],
            },
        )
        ctx = _base_ctx(task, root)
        executor = DeterministicPulseExecutor(task, ctx)
        collected: list[AgentEvent] = []

        async def drive():
            async for ev in executor.execute(task, ctx):
                collected.append(ev)

        async def main():
            run = asyncio.create_task(drive())
            deadline = time.time() + 10
            while time.time() < deadline:
                if task.id in _RUNNING_CANCEL_EVENTS:
                    break
                await asyncio.sleep(0.02)
            # Cancellation is genuinely wired to the running executor.
            assert task.id in _RUNNING_CANCEL_EVENTS
            assert cancel_pulse_execution(task.id) is True
            await asyncio.wait_for(run, timeout=15)

        _run(main())
        health = next(e for e in collected if e.kind == EventKind.HEALTH)
        report = health.meta.get("pulse_report") or health.meta.get("health")
        assert report["status"] == "INTERRUPTED"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cancellation_midrun_stops_loop_and_sets_interrupted():
    root = _home_tmp()
    port = _listening_port()
    try:
        with socket.socket() as keep:
            keep.bind(("127.0.0.1", port))
            keep.listen(1)
            urls = [
                f"http://127.0.0.1:{port}/health",
                f"http://127.0.0.1:{port}/big",
            ]
            task = Task(
                title="cek service",
                pulse_request={"health_urls": urls},
            )
            ctx = _base_ctx(task, root)
            executor = DeterministicPulseExecutor(task, ctx)
            http_calls = {"n": 0}

            original = executor._check_http

            def cancelling_http(url):
                result = original(url)
                http_calls["n"] += 1
                if http_calls["n"] >= 1:
                    executor._cancel_event.set()
                return result

            executor._check_http = cancelling_http

            _, report = _collect(executor, task, ctx)
            assert http_calls["n"] == 1  # second pending check was not run
            assert report["status"] == "INTERRUPTED"
            assert report["summary"] == "PULSE dibatalkan oleh user"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_engine_cancel_running_signals_pulse(monkeypatch):
    from ai_dev_agent_core import engine as engine_mod

    registry = AgentRegistry()
    engine = OrchestrationEngine(
        registry,
        orchestrator_agent="atlas",
        broadcast=_async_broadcast,
    )
    engine._running = type("T", (), {"id": "pulse-task-123"})()
    engine._cancelled.clear()
    called = {"n": 0}

    calls = {}

    def fake_cancel_pulse(task_id):
        calls["task_id"] = task_id
        called["n"] += 1
        return True

    monkeypatch.setattr(
        "ai_dev_agent_pulse.executor.cancel_pulse_execution", fake_cancel_pulse
    )
    assert engine.cancel_running("pulse-task-123") is True
    assert called["n"] == 1
    assert calls["task_id"] == "pulse-task-123"


# ---------------------------------------------------------------------------
# Real manual E2E (Section 18): healthy then unhealthy with a real local HTTP
# service, driven through ATLAS dispatch.
# ---------------------------------------------------------------------------

class _RecordingEngine(OrchestrationEngine):
    """Engine that records every streamed agent event for evidence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.events: list[tuple] = []

    async def _apply(self, event, task):
        meta = dict(event.meta or {})
        self.events.append((event.agent_id, event.kind, event.message, meta))
        await super()._apply(event, task)


def _run_engine_task(text: str, workspace_root: Path, port: int):
    """Drive ATLAS -> PULSE for an explicit health task; return (task, report)."""
    from ai_dev_api.agents import build_registry

    registry = build_registry()
    engine = _RecordingEngine(
        registry,
        orchestrator_agent="atlas",
        broadcast=_async_broadcast,
        settings={
            "speed": 99.0,
            "forge_workspace_root": str(workspace_root),
            "cleanup_workspace": False,
        },
    )
    task = Task(
        title="Gunakan PULSE",
        description=(
            "Gunakan PULSE.\n"
            f"Periksa apakah service lokal di http://127.0.0.1:{port}/health sehat."
        ),
    )

    async def go():
        await engine.enqueue(task)
        deadline = time.time() + 60
        while time.time() < deadline:
            await asyncio.sleep(0.05)
            if task.status in (
                TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.INTERRUPTED,
            ):
                return
            if engine._worker is None:
                return
        raise TimeoutError("PULSE E2E pipeline did not finish")

    _run(go())

    report = None
    for agent_id, kind, message, meta in engine.events:
        if agent_id == "pulse" and kind == EventKind.HEALTH:
            report = meta.get("pulse_report") or meta.get("health")
    return task, report, engine


def test_real_e2e_healthy_then_unhealthy(http_server):
    from ai_dev_api.config import settings

    root = _home_tmp(".ado-pulse-e2e-")
    port = http_server.server_address[1]
    try:
        # Healthy while the local service is up.
        task1, report1, engine1 = _run_engine_task(
            "Gunakan PULSE\nPeriksa service lokal", root, port
        )
        assert task1.status == TaskStatus.DONE
        assert report1 is not None, "PULSE emitted a HEALTH report"
        assert report1["status"] == "HEALTHY"
        assert report1["verified"] is True
        http_check = next(c for c in report1["checks"] if c["type"] == "http")
        assert http_check["evidence"]["status_code"] == 200
        # ATLAS indeed routed to PULSE (agent events present).
        assert any(a == "pulse" for a, _, _, _ in engine1.events)

        # Stop the service; the SAME task shape must now be UNHEALTHY.
        http_server.shutdown()
        http_server.server_close()
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    time.sleep(0.1)
            except OSError:
                break

        task2, report2, engine2 = _run_engine_task(
            "Gunakan PULSE\nPeriksa service lokal", root, port
        )
        assert report2 is not None
        # UNHEALTHY -> ATLAS fails the task (existing health gate).
        assert report2["status"] == "UNHEALTHY"
        assert report2["verified"] is True
        assert not report2["checks"] or all(
            not c["ok"] for c in report2["checks"] if c["type"] == "http"
        )
        assert task2.status in (TaskStatus.FAILED, TaskStatus.DONE)
    finally:
        try:
            http_server.server_close()
        except Exception:
            pass
        shutil.rmtree(root, ignore_errors=True)


def test_real_e2e_service_is_really_probed_not_faked():
    """No fake: the port/URL must actually be answered by the fixture."""
    root = _home_tmp(".ado-pulse-e2e2-")
    try:
        port = _listening_port()
        task1, report1, _ = _run_engine_task(
            "Gunakan PULSE\nPeriksa service lokal", root, port
        )
        assert report1["status"] == "UNHEALTHY"
        assert report1["verified"] is True
        assert task1.status in (TaskStatus.FAILED, TaskStatus.DONE)
    finally:
        shutil.rmtree(root, ignore_errors=True)