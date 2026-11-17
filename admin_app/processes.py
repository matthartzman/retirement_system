"""Start, stop and report on the two apps the Admin app can control: the Retirement Planner and Financial Insights.

Only the two fixed names in ``SPECS`` can ever be launched. A request chooses *which* of them, never a command, an
argument or a path, so nothing a caller sends reaches a command line. The commands are the ones the launchers use.

A record of each child (``<workspace>/local_state/admin_processes/<name>.json``: pid, port, start time, process start
stamp) is the primary way to track it; the port answering is the fallback for an app started somewhere else. Children
are detached: closing the Admin app leaves them running, and a later Admin app finds them again by their record.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:  # optional: with it a recorded pid is only trusted if the process start time still matches (pid reuse)
    import psutil
except ImportError:  # pragma: no cover - psutil is not a declared dependency
    psutil = None

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOPBACK = "127.0.0.1"
STARTING_GRACE_SECONDS = 45.0
STOP_WAIT_SECONDS = 6.0
WORKSPACE_ENV = "RETIREMENT_SYSTEM_WORKSPACE_ROOT"  # src.platform_runtime.WORKSPACE_ROOT_ENV


@dataclass(frozen=True)
class Spec:
    label: str
    script: str  # relative to the repo root; also what an unmanaged process's command line must contain
    default_port: int
    extra_ports: tuple[int, ...] = ()


SPECS: dict[str, Spec] = {
    "planner": Spec("Retirement Planner", "main.py", 5050),
    "insights": Spec("Financial Insights", "financial_trends_reporter/main.py", 5057, (5058,)),
}


def listening(port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(timeout)
        return probe.connect_ex((LOOPBACK, int(port))) == 0


def pid_alive(pid: int) -> bool:
    if psutil is not None:
        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _create_time(pid: int) -> float | None:
    try:
        return round(psutil.Process(pid).create_time(), 1) if psutil is not None else None
    except Exception:  # noqa: BLE001 - psutil raises its own family
        return None


def kill_tree(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(int(pid)), "/T", "/F"], capture_output=True, check=False, timeout=15)
    else:
        os.kill(pid, 15)


class ProcessManager:
    def __init__(self, root: Path, planner_port: Callable[[], int] = lambda: SPECS["planner"].default_port,
                 popen=subprocess.Popen, clock: Callable[[], float] = time.time, probe=listening, alive=pid_alive,
                 kill=kill_tree, graceful_stop: Callable[[], bool] | None = None) -> None:
        self.root = Path(root)
        self.dir = self.root / "local_state" / "admin_processes"
        self._planner_port, self._popen, self._clock = planner_port, popen, clock
        self._probe, self._alive, self._kill, self._graceful = probe, alive, kill, graceful_stop

    # ---- records ----
    def _file(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def _record(self, name: str) -> dict | None:
        """The child this Admin app (or an earlier one) launched, if its process is still the same process."""
        try:
            rec = json.loads(self._file(name).read_text(encoding="utf-8"))
            pid = int(rec["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not self._alive(pid):
            return None
        stamp = rec.get("create_time")
        if stamp is not None and _create_time(pid) not in (None, stamp):
            return None  # the pid now belongs to some other process
        return rec

    def port(self, name: str) -> int:
        return int(self._planner_port()) if name == "planner" else SPECS[name].default_port

    # ---- status ----
    def status(self, name: str) -> dict:
        spec, port = SPECS[name], self.port(name)
        rec, up = self._record(name), self._probe(port)
        started = rec.get("started_at") if rec else None
        if up:
            state = "running"
        elif rec and started and self._clock() - started < STARTING_GRACE_SECONDS:
            state = "starting"
        else:
            state = "stopped"
        return {"name": name, "label": spec.label, "state": state, "running": up, "port": port,
                "pid": rec["pid"] if rec else None, "managed": bool(rec), "started_at": started,
                "extra_ports": [{"port": p, "listening": self._probe(p)} for p in spec.extra_ports]}

    def statuses(self) -> list[dict]:
        return [self.status(n) for n in SPECS]

    # ---- start ----
    def command(self, name: str) -> tuple[list[str], dict[str, str]]:
        env = dict(os.environ)
        if name == "planner":  # what START_APP.bat runs, but in server mode so it has a port and a pid
            env[WORKSPACE_ENV] = str(self.root)
            return [sys.executable, "main.py", "--mode", "server"], env
        return [sys.executable, SPECS[name].script, "--retirement-system-dir", str(self.root), "--no-open"], env

    def start(self, name: str) -> tuple[dict, int]:
        cur = self.status(name)
        if cur["state"] in ("running", "starting"):
            return {"success": True, "already": True, "app": cur}, 200
        if self._probe(cur["port"]):
            return {"success": False, "error": f"Port {cur['port']} is in use by another program."}, 409
        cmd, env = self.command(name)
        self.dir.mkdir(parents=True, exist_ok=True)
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
        extra = {"start_new_session": True} if sys.platform != "win32" else {}
        try:
            with open(self.dir / f"{name}.log", "ab") as log:
                proc = self._popen(cmd, cwd=str(REPO_ROOT), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=flags, **extra)
        except OSError as exc:
            return {"success": False, "error": f"Could not start {SPECS[name].label}: {exc}"}, 500
        rec = {"pid": proc.pid, "port": cur["port"], "started_at": self._clock(), "create_time": _create_time(proc.pid)}
        self._file(name).write_text(json.dumps(rec), encoding="utf-8")
        return {"success": True, "app": self.status(name)}, 200

    # ---- stop ----
    def stop(self, name: str) -> tuple[dict, int]:
        cur = self.status(name)
        if cur["state"] == "stopped":
            return {"success": True, "already": True, "app": cur}, 200
        if name == "planner" and self._graceful and cur["running"]:
            self._graceful()
            if self._wait_down(cur["port"]):
                self._file(name).unlink(missing_ok=True)
                return {"success": True, "app": self.status(name)}, 200
        pid = cur["pid"]
        if pid is None:
            return {"success": False, "error": f"{SPECS[name].label} was started outside the Admin app, so the Admin app "
                                               "does not know which process to stop. Close it from its own window."}, 409
        self._kill(pid)
        self._wait_down(cur["port"])
        self._file(name).unlink(missing_ok=True)
        after = self.status(name)
        if after["running"]:
            return {"success": False, "error": f"{SPECS[name].label} did not stop.", "app": after}, 500
        return {"success": True, "app": after}, 200

    def _wait_down(self, port: int) -> bool:
        deadline = time.monotonic() + STOP_WAIT_SECONDS
        while time.monotonic() < deadline:
            if not self._probe(port):
                return True
            time.sleep(0.2)
        return not self._probe(port)
