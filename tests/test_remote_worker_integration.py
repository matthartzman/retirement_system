"""The headless remote worker (``python -m src.remote_worker``) as a real process.

Each worker gets its own temp workspace, so nothing here touches the session workspace. Covers:
port 0 with the chosen port reported back (file and stdout line), explicit provisioning (demo
seed, blank, none), refusing to start without a token, refusing a build on a plan with no rows,
browser upload into an empty workspace, and the parent-death watchdog. No workbook is built.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "integration-worker-token-abcdef"


def _worker_env(workspace: Path, token: str | None = TOKEN) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("RETIREMENT_SYSTEM_")}
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    env["RETIREMENT_SYSTEM_FROZEN_TODAY"] = "2026-08-04"
    if token is not None:
        env["RETIREMENT_SYSTEM_SERVER_API_TOKEN"] = token
    return env


def _start(workspace: Path, provision: str, *, parent_pid: int | None = None, token: str | None = TOKEN):
    port_file = workspace.parent / f"{workspace.name}.port.json"
    cmd = [sys.executable, "-m", "src.remote_worker", "--workspace", str(workspace),
           "--provision", provision, "--port-file", str(port_file)]
    if parent_pid is not None:
        cmd += ["--parent-pid", str(parent_pid)]
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=_worker_env(workspace, token), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    return proc, port_file


def _wait_port(proc, port_file: Path, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_file.is_file():
            return json.loads(port_file.read_text(encoding="utf-8"))
        if proc.poll() is not None:
            raise AssertionError(f"worker exited early: {proc.returncode} {proc.stderr.read()[-2000:]}")
        time.sleep(0.1)
    raise AssertionError("worker did not report a port")


def _call(port: int, method: str, path: str, *, body: dict | None = None, token: str | None = TOKEN):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method)
    if token:
        req.add_header("X-API-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _stop(proc) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=30)
    for stream in (proc.stdout, proc.stderr):
        if stream:
            stream.close()


@pytest.fixture
def demo_worker(tmp_path):
    proc, port_file = _start(tmp_path / "user_a", "demo")
    try:
        yield proc, _wait_port(proc, port_file)
    finally:
        _stop(proc)


def test_worker_reports_its_port_and_requires_the_token(demo_worker):
    proc, info = demo_worker
    port = info["port"]
    assert port > 0 and info["pid"] == proc.pid
    status, _body, _ = _call(port, "GET", "/api/ping", token=None)
    assert status == 401
    status, body, _ = _call(port, "GET", "/api/ping")
    assert status == 200
    ping = json.loads(body)
    assert ping["remote_mode"] is True and "package_root" not in ping
    status, body, _ = _call(port, "GET", "/api/config/rows")
    assert status == 200 and json.loads(body)["rows"], "demo provisioning gave a plan with rows"
    status, _body, _ = _call(port, "POST", "/api/shutdown", body={})
    assert status == 403
    assert proc.poll() is None


def test_worker_port_cannot_be_bound_again(demo_worker):
    """The worker's socket is exclusive: another process cannot take its port over, even with
    address reuse requested (Windows ``SO_REUSEADDR`` would otherwise allow it)."""
    import socket

    _proc, info = demo_worker
    intruder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        intruder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with pytest.raises(OSError):
            intruder.bind(("127.0.0.1", info["port"]))
    finally:
        intruder.close()


def test_empty_workspace_refuses_build_then_accepts_an_uploaded_plan(demo_worker, tmp_path):
    _proc, info = demo_worker
    status, plan_bytes, _ = _call(info["port"], "GET", "/api/plan/download")
    assert status == 200 and plan_bytes[:15] == b"SQLite format 3"

    proc, port_file = _start(tmp_path / "user_b", "none")
    try:
        port = _wait_port(proc, port_file)["port"]
        status, body, _ = _call(port, "POST", "/api/build/start", body={})
        assert status == 409
        assert "no plan data" in json.loads(body)["error"].lower()
        status, body, _ = _call(port, "POST", "/api/plan/upload",
                                body={"filename": "mine.rpx", "content_base64": base64.b64encode(plan_bytes).decode(), "mode": "restore"})
        assert status == 200, body
        assert str(tmp_path) not in body.decode()
        status, body, _ = _call(port, "GET", "/api/config/rows")
        assert status == 200 and json.loads(body)["rows"]
    finally:
        _stop(proc)


def test_blank_provisioning_gives_rows_with_household_facts_cleared(tmp_path):
    from src import platform_runtime
    from src.stores import PlanStore

    def filled(path: Path) -> tuple[int, int]:
        with PlanStore.open(path, create=False, readonly=True) as store:
            rows = list(store.all_rows())
        return len(rows), sum(1 for r in rows if str(r["value"]).strip())

    workspace = tmp_path / "user_c"
    proc, port_file = _start(workspace, "blank")
    try:
        info = _wait_port(proc, port_file)
        assert info["provisioned"] == "blank"
        status, body, _ = _call(info["port"], "GET", "/api/config/rows")
        assert status == 200 and json.loads(body)["rows"]
        seed_rows, seed_filled = filled(platform_runtime.demo_seed_path())
        blank_rows, blank_filled = filled(workspace / "plan.rpx")
        assert blank_rows >= seed_rows and 0 < blank_filled < seed_filled
    finally:
        _stop(proc)


def test_worker_refuses_to_start_without_a_token(tmp_path):
    proc, _port_file = _start(tmp_path / "user_d", "none", token="")
    try:
        assert proc.wait(timeout=60) != 0
        assert "token" in proc.stderr.read().lower()
    finally:
        _stop(proc)


def test_worker_exits_when_its_parent_dies(tmp_path):
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    proc, port_file = _start(tmp_path / "user_e", "none", parent_pid=parent.pid)
    try:
        _wait_port(proc, port_file)
        parent.kill()
        parent.wait(timeout=30)
        assert proc.wait(timeout=30) is not None
    finally:
        if parent.poll() is None:
            parent.kill()
        _stop(proc)
