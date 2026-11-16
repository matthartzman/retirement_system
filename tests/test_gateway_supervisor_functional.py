"""The supervisor with the real same-account launcher (real processes, real Job Objects) and a stub
worker that speaks the worker contract: readiness, environment, restart, cool-down, reaping, stops."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from src.gateway import winapi
from src.gateway.build_queue import BuildQueue
from src.gateway.launchers import LaunchSpec, SameAccountLauncher
from src.gateway.supervisor import Supervisor, SupervisorConfig, WorkerUnavailable, call_worker

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "nt", reason="Job Objects are Windows-only")]

STUB = r'''
import argparse, json, os, subprocess, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
p = argparse.ArgumentParser()
for a in ("--workspace", "--provision", "--port-file", "--parent-pid", "--console-log"):
    p.add_argument(a)
a = p.parse_args()
ws = Path(a.workspace)
tok = os.environ["RETIREMENT_SYSTEM_SERVER_API_TOKEN"]
(ws / "env.json").write_text(json.dumps(dict(os.environ)), encoding="utf-8")
(ws / "argv.json").write_text(json.dumps(sys.argv), encoding="utf-8")
if (ws / "fail_start").exists():
    sys.exit(5)
if (ws / "spawn_child").exists():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    (ws / "child.pid").write_text(str(child.pid), encoding="utf-8")

class H(BaseHTTPRequestHandler):
    def log_message(self, *x):
        return
    def do_GET(self):
        if self.headers.get("X-API-Token") != tok:
            code, body = 401, {"error": "token"}
        elif self.path == "/api/ping":
            code, body = 200, {"running": True}
        elif self.path == "/api/build/status":
            code, body = 200, {"build_running": (ws / "building").exists()}
        else:
            code, body = 404, {}
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
pid = os.getpid() + (1 if (ws / "wrong_pid").exists() else 0)
pf = Path(a.port_file)
pf.parent.mkdir(parents=True, exist_ok=True)
tmp = pf.with_name(pf.name + ".tmp")
tmp.write_text(json.dumps({"port": srv.server_address[1], "pid": pid, "provisioned": a.provision}), encoding="utf-8")
tmp.replace(pf)
srv.serve_forever()
'''


class StubLauncher(SameAccountLauncher):
    """The real same-account launcher, running the stub instead of ``-m src.remote_worker``."""

    def __init__(self, stub: Path) -> None:
        super().__init__()
        self.stub = stub
        self.specs: list[LaunchSpec] = []

    def launch(self, spec: LaunchSpec):
        self.specs.append(spec)
        argv = list(spec.argv)
        i = argv.index("-m")
        argv[i:i + 2] = [str(self.stub)]
        return super().launch(replace(spec, argv=argv))


def _alive(pid: int) -> bool:
    import ctypes  # noqa: PLC0415

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x1000 | 0x00100000, False, int(pid))
    if not h:
        return False
    try:
        return winapi.process_exit_code(h) is None
    finally:
        k.CloseHandle(ctypes.c_void_p(h))


def _wait_dead(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.1)
    return False


@pytest.fixture
def make(tmp_path):
    stub = tmp_path / "stub_worker.py"
    stub.write_text(STUB, encoding="utf-8")
    made: list[Supervisor] = []
    now = [10_000.0]

    def _make(**overrides):
        cfg = SupervisorConfig(data_root=tmp_path / "data", start_timeout=20, extra_env={"RETIREMENT_SYSTEM_FROZEN_TODAY": "2026-08-04"},
                               **overrides)
        sup = Supervisor(cfg, StubLauncher(stub), build_queue=BuildQueue(2), clock=lambda: now[0])
        made.append(sup)
        return sup

    _make.now = now
    yield _make
    for sup in made:
        sup.shutdown()


def test_start_reports_a_ready_endpoint_with_a_scrubbed_pinned_environment(make, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_BASE_DIR", "C:\\owner\\data")
    monkeypatch.setenv("PYTHONPATH", "C:\\owner\\lib")
    monkeypatch.setenv("GATEWAY_SECRET_THING", "not for workers")
    sup = make()
    sup.launcher = StubLauncher(sup.launcher.stub)  # take the base environment after the monkeypatch
    ep = sup.endpoint(7)
    assert ep.port > 0 and sup.is_running(7)
    assert call_worker(ep, "GET", "/api/ping")[0] == 200
    ws = sup.workspace(7)
    env = json.loads((ws / "env.json").read_text(encoding="utf-8"))
    assert env["RETIREMENT_SYSTEM_SERVER_API_TOKEN"] == ep.token and len(ep.token) >= 40
    assert Path(env["TEMP"]) == ws / "local_state" / "tmp" == Path(env["TMP"])
    assert env["RETIREMENT_SYSTEM_BUILD_POOL_MAX"] == "4"
    assert env["RETIREMENT_SYSTEM_FROZEN_TODAY"] == "2026-08-04"
    for absent in ("RETIREMENT_SYSTEM_BASE_DIR", "PYTHONPATH", "GATEWAY_SECRET_THING"):
        assert absent not in env
    argv = json.loads((ws / "argv.json").read_text(encoding="utf-8"))
    assert "--provision" in argv and argv[argv.index("--provision") + 1] == "blank"
    assert ep.token not in " ".join(argv)  # the token is never on a command line
    spec = sup.launcher.specs[-1]
    assert spec.argv[1:6] == ["-E", "-s", "-B", "-X", "utf8"]
    assert spec.memory_limit_bytes == 1792 * 1024 * 1024
    assert sup.endpoint(7) == ep  # reused while it runs
    assert sup.port_owner_ok(ep)
    from dataclasses import replace as _r  # noqa: PLC0415
    assert not sup.port_owner_ok(_r(ep, pid=ep.pid + 4))


def test_the_worker_tree_is_in_a_kill_on_close_job(make):
    sup = make()
    ws = sup.workspace(3)
    ws.mkdir(parents=True)
    (ws / "spawn_child").write_text("1")
    sup.endpoint(3)
    child = int((ws / "child.pid").read_text())
    slot = sup._slots[3]
    assert slot.process.job.active_processes() >= 2
    sup.stop(3, "test")
    assert _wait_dead(child), "the worker's child outlived the job"


def test_variables_that_redirect_a_worker_cannot_be_configured(tmp_path):
    for bad in ("RETIREMENT_SYSTEM_BASE_DIR", "PYTHONPATH", "RETIREMENT_SYSTEM_SERVER_API_TOKEN"):
        with pytest.raises(ValueError):
            SupervisorConfig(data_root=tmp_path, extra_env={bad: "x"})
    with pytest.raises(ValueError):
        SupervisorConfig(data_root=tmp_path, provision="none")


def test_a_worker_that_exits_or_lies_about_its_pid_is_unavailable(make):
    sup = make()
    for uid, flag in ((4, "fail_start"), (5, "wrong_pid")):
        ws = sup.workspace(uid)
        ws.mkdir(parents=True)
        (ws / flag).write_text("1")
        with pytest.raises(WorkerUnavailable):
            sup.endpoint(uid)
        assert not sup.is_running(uid)


def test_a_crashed_worker_restarts_and_a_crash_loop_cools_down(make):
    sup = make(max_crashes=1)
    first = sup.endpoint(1)
    subprocess.run(["taskkill", "/F", "/PID", str(first.pid)], capture_output=True)
    assert _wait_dead(first.pid)
    sup.monitor_once()
    second = sup.current_endpoint(1)
    assert second is not None and second.pid != first.pid and second.token != first.token
    subprocess.run(["taskkill", "/F", "/PID", str(second.pid)], capture_output=True)
    assert _wait_dead(second.pid)
    sup.monitor_once()  # second crash inside the window: no restart, cool-down
    assert not sup.is_running(1)
    with pytest.raises(WorkerUnavailable):
        sup.endpoint(1)


def test_idle_workers_are_reaped_but_never_while_building(make):
    sup = make(idle_seconds=60)
    ep = sup.endpoint(2)
    building = sup.workspace(2) / "building"
    building.write_text("1")
    make.now[0] += 120
    sup.monitor_once()
    assert sup.is_running(2), "reaped while the worker reported a running build"
    building.unlink()
    sup.monitor_once()
    assert not sup.is_running(2) and _wait_dead(ep.pid)


def test_a_queued_build_also_keeps_the_worker(make):
    sup = make(idle_seconds=60)
    sup.endpoint(2)
    sup.build_queue.try_acquire(2)
    make.now[0] += 120
    sup.monitor_once()
    assert sup.is_running(2)


def test_sign_out_stops_at_once_or_after_the_build(make):
    sup = make()
    ep = sup.endpoint(8)
    building = sup.workspace(8) / "building"
    building.write_text("1")
    sup.signed_out(8, sessions_left=1)
    assert sup.is_running(8)
    sup.signed_out(8, sessions_left=0)
    assert sup.is_running(8), "stopped mid-build"
    building.unlink()
    sup.monitor_once()
    assert not sup.is_running(8) and _wait_dead(ep.pid)
    ep2 = sup.endpoint(8)
    sup.signed_out(8, sessions_left=0)
    assert not sup.is_running(8) and _wait_dead(ep2.pid)


def test_delete_and_disable_stop_the_worker_and_delete_removes_the_folder(make):
    sup = make()
    sup.endpoint(9)
    sup.user_disabled(9, True)
    assert not sup.is_running(9)
    sup.endpoint(9)
    sup.user_deleted(9)
    assert not sup.is_running(9) and not sup.workspace(9).exists()


def test_user_ids_must_be_positive(make):
    with pytest.raises(ValueError):
        make().workspace(0)
