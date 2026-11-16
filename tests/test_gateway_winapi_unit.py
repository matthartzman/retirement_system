"""The ctypes Win32 layer, unelevated: Job Objects (kill-on-close, memory cap), suspended start,
listening-port owners, SIDs and DPAPI."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest

from src.gateway import winapi
from src.gateway.launchers import LaunchSpec, SameAccountLauncher

pytestmark = [pytest.mark.unit, pytest.mark.skipif(os.name != "nt", reason="Windows-only")]


def test_closing_a_job_kills_the_whole_tree_including_grandchildren(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    code = ("import subprocess, sys, time\n"
            "c = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            f"open({str(pid_file)!r}, 'w').write(str(c.pid))\n"
            "time.sleep(120)\n")
    proc = SameAccountLauncher().launch(LaunchSpec(1, [sys.executable, "-c", code], tmp_path, {}, None, 16))
    deadline = time.time() + 20
    while not pid_file.exists() and time.time() < deadline:
        time.sleep(0.05)
    grandchild = int(pid_file.read_text())
    assert proc.job.active_processes() >= 2  # the worker, its child (and a launcher shim, if any)
    proc.kill()
    deadline = time.time() + 10
    while time.time() < deadline and (proc.poll() is None):
        time.sleep(0.05)
    assert proc.poll() is not None
    out = subprocess.run(["tasklist", "/FI", f"PID eq {grandchild}", "/NH"], capture_output=True, text=True).stdout
    assert str(grandchild) not in out


def test_the_job_memory_cap_stops_an_allocation_but_not_the_cap_itself(tmp_path):
    code = "b = bytearray(400 * 1024 * 1024)\nprint('allocated')\n"
    proc = SameAccountLauncher().launch(LaunchSpec(1, [sys.executable, "-c", code], tmp_path, {}, 150 * 1024 * 1024, None))
    deadline = time.time() + 30
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    assert proc.poll() not in (None, 0), "a 400 MB allocation succeeded under a 150 MB job cap"
    proc.kill()


def test_a_suspended_process_runs_only_once_resumed(tmp_path):
    marker = tmp_path / "ran"
    proc = subprocess.Popen([sys.executable, "-c", f"open({str(marker)!r}, 'w').write('1')"],
                            creationflags=winapi.CREATE_SUSPENDED | winapi.CREATE_NO_WINDOW)
    try:
        time.sleep(1.0)
        assert not marker.exists()
        winapi.resume_process(int(proc._handle))
        proc.wait(timeout=20)
        assert marker.exists()
    finally:
        proc.kill()


def test_listening_port_owner():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen()
    try:
        port = s.getsockname()[1]
        assert winapi.tcp_listener_pids(port) == {os.getpid()}
    finally:
        s.close()
    assert winapi.tcp_listener_pids(port) == set()


def test_sids_and_dpapi():
    sid = winapi.current_user_sid()
    assert sid.startswith("S-1-")
    assert winapi.lookup_account_sid("SYSTEM") == "S-1-5-18"
    assert winapi.lookup_account_sid("rpw_no_such_account_xyz") is None
    blob = winapi.dpapi_protect(b"not a real password")
    assert b"not a real password" not in blob
    assert winapi.dpapi_unprotect(blob) == b"not a real password"
