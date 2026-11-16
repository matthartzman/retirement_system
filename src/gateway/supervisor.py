"""The supervisor: one headless worker per signed-in user, started on demand, restarted after a crash,
stopped on logout, disable, delete or idle, and never reaped while a build is running.

See ``documentation/future/multi-user-server-supervisor-design.md``. The worker contract is
``src/remote_worker.py``; the launcher decides which Windows account it runs as.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import secrets
import shutil
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from . import winapi
from .build_queue import BuildQueue
from .launchers import DEDICATED_ACCOUNT_ENV, LaunchSpec, WorkerLauncher, WorkerProcess

LOG = logging.getLogger("retirement.gateway.supervisor")
ROOT = Path(__file__).resolve().parents[2]
PORT_FILE = Path("local_state") / "worker.port.json"
CONSOLE_LOG = Path("local_state") / "logs" / "worker_console.log"
TOKEN_ENV = "RETIREMENT_SYSTEM_SERVER_API_TOKEN"
POOL_ENV = "RETIREMENT_SYSTEM_BUILD_POOL_MAX"
PROVISIONS = ("demo", "blank")
# Never handed to a worker, whatever extra_env says: they would redirect it outside its workspace.
FORBIDDEN_ENV = frozenset({"RETIREMENT_SYSTEM_BASE_DIR", "RETIREMENT_SYSTEM_WORKSPACE_ROOT", "PYTHONPATH", "PYTHONHOME",
                           "PYTHONSTARTUP", TOKEN_ENV, DEDICATED_ACCOUNT_ENV})


MAPPING_SEED_RELPATH = Path("local_state") / "monarch_mapping_seed.csv"  # same as src/monarch_upload.py
MAPPING_CSV_MAX_BYTES = 1024 * 1024
MAPPING_CSV_COLUMNS = ("Monarch", "App Location", "App Field")


def check_mapping_csv(path: Path) -> None:
    """Refuse a mapping CSV the worker's seeder could not use (the gateway starts only with a good one)."""
    if not path.is_file():
        raise ValueError(f"--monarch-mapping-csv {path} is not a file")
    data = path.read_bytes()
    if len(data) > MAPPING_CSV_MAX_BYTES:
        raise ValueError("--monarch-mapping-csv is larger than 1 MiB")
    try:
        first = data.decode("utf-8-sig").splitlines()[0] if data.strip() else ""
    except UnicodeDecodeError:
        raise ValueError("--monarch-mapping-csv is not UTF-8 text") from None
    header = [h.strip().strip('"') for h in first.split(",")]
    missing = [c for c in MAPPING_CSV_COLUMNS if c not in header]
    if missing:
        raise ValueError(f"--monarch-mapping-csv is missing the column(s) {', '.join(missing)}")


class WorkerUnavailable(RuntimeError):
    """The user's worker cannot serve right now; the message is safe to show the user."""


@dataclass(frozen=True)
class Endpoint:
    user_id: int
    port: int
    pid: int
    token: str = field(repr=False)


@dataclass
class SupervisorConfig:
    data_root: Path
    install_dir: Path = ROOT
    python: str = sys.executable
    provision: str = "blank"
    idle_seconds: float = 30 * 60
    start_timeout: float = 60.0
    memory_limit_mb: int | None = 1792
    active_process_limit: int | None = 64
    build_pool_max: int | None = 4
    extra_env: dict[str, str] = field(default_factory=dict)
    monarch_mapping_csv: Path | None = None  # copied into each new workspace (MAPPING_SEED_RELPATH)
    max_crashes: int = 3
    crash_window: float = 600.0
    crash_cooldown: float = 600.0
    monitor_interval: float = 2.0
    check_port_owner: bool = True

    def __post_init__(self) -> None:
        self.data_root = Path(self.data_root)
        self.install_dir = Path(self.install_dir)
        if self.provision not in PROVISIONS:
            raise ValueError(f"provision must be one of {PROVISIONS}")
        bad = sorted(k for k in self.extra_env if k.upper() in FORBIDDEN_ENV)
        if bad:
            raise ValueError(f"these variables may not be passed to workers: {', '.join(bad)}")
        if self.monarch_mapping_csv is not None:
            self.monarch_mapping_csv = Path(self.monarch_mapping_csv)
            check_mapping_csv(self.monarch_mapping_csv)


class AccountHooks(Protocol):
    def ensure(self, user_id: int, workspace: Path) -> None: ...
    def disable(self, user_id: int, disabled: bool) -> None: ...
    def remove(self, user_id: int, workspace: Path) -> None: ...
    def housekeeping(self, known_user_ids: set[int]) -> None: ...


class BackupHook(Protocol):
    def backup_user(self, user_id: int, into: Path | None = None) -> Path: ...


@dataclass
class _Slot:
    user_id: int
    lock: threading.Lock = field(default_factory=threading.Lock)
    process: WorkerProcess | None = None
    endpoint: Endpoint | None = None
    last_used: float = 0.0
    crashes: deque = field(default_factory=deque)
    cooldown_until: float = 0.0
    stop_when_idle_of_builds: bool = False
    stopping: bool = False


def call_worker(endpoint: Endpoint, method: str, path: str, *, body: bytes | None = None, timeout: float = 10.0,
                content_type: str = "application/json") -> tuple[int, bytes]:
    """One request straight to a worker with its token (used for health checks and build polling)."""
    conn = http.client.HTTPConnection("127.0.0.1", endpoint.port, timeout=timeout)
    try:
        headers = {"Host": f"127.0.0.1:{endpoint.port}", "X-API-Token": endpoint.token,
                   "Content-Length": str(len(body or b""))}
        if body:
            headers["Content-Type"] = content_type
        conn.request(method, path, body=body or b"", headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read(8 * 1024 * 1024)
    finally:
        conn.close()


class Supervisor:
    def __init__(self, config: SupervisorConfig, launcher: WorkerLauncher, *, accounts: AccountHooks | None = None,
                 build_queue: BuildQueue | None = None, backups: BackupHook | None = None,
                 clock: Callable[[], float] = time.time) -> None:
        self.config = config
        self.launcher = launcher
        self.accounts = accounts
        self.build_queue = build_queue
        self.backups = backups
        self._clock = clock
        self._slots: dict[int, _Slot] = {}
        self._slots_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_housekeeping = 0.0
        self.known_user_ids: Callable[[], set[int]] | None = None
        (self.config.data_root / "users").mkdir(parents=True, exist_ok=True)

    # ---- paths ----
    def workspace(self, user_id: int) -> Path:
        uid = int(user_id)
        if uid <= 0:
            raise ValueError("user ids are positive integers")
        return self.config.data_root / "users" / str(uid)

    def _slot(self, user_id: int) -> _Slot:
        with self._slots_lock:
            slot = self._slots.get(int(user_id))
            if slot is None:
                slot = self._slots[int(user_id)] = _Slot(int(user_id))
            return slot

    # ---- start ----
    def endpoint(self, user_id: int) -> Endpoint:
        """The user's running worker, started (and waited for) when it is not running."""
        slot = self._slot(user_id)
        with slot.lock:
            slot.last_used = self._clock()
            if slot.process is not None and slot.process.poll() is None and slot.endpoint is not None:
                return slot.endpoint
            if slot.process is not None:  # exited since the monitor last looked
                self._on_exit(slot)
            if self._clock() < slot.cooldown_until:
                raise WorkerUnavailable("Your planner stopped unexpectedly several times. Please try again in a few minutes.")
            self._start(slot)
            assert slot.endpoint is not None
            return slot.endpoint

    def _launch_spec(self, user_id: int, workspace: Path, token: str) -> LaunchSpec:
        cfg = self.config
        tmp = workspace / "local_state" / "tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in cfg.extra_env.items()}
        env.update({TOKEN_ENV: token, "TEMP": str(tmp), "TMP": str(tmp), "PYTHONIOENCODING": "utf-8"})
        if cfg.build_pool_max:
            env[POOL_ENV] = str(int(cfg.build_pool_max))
        argv = [cfg.python, "-E", "-s", "-B", "-X", "utf8", "-m", "src.remote_worker", "--workspace", str(workspace),
                "--provision", cfg.provision, "--port-file", str(workspace / PORT_FILE), "--parent-pid", str(os.getpid()),
                "--console-log", str(workspace / CONSOLE_LOG)]
        mem = int(cfg.memory_limit_mb) * 1024 * 1024 if cfg.memory_limit_mb else None
        return LaunchSpec(user_id, argv, cfg.install_dir, env, mem, cfg.active_process_limit)

    def _start(self, slot: _Slot) -> None:
        uid = slot.user_id
        workspace = self.workspace(uid)
        workspace.mkdir(parents=True, exist_ok=True)
        if self.accounts is not None:
            self.accounts.ensure(uid, workspace)
        port_file = workspace / PORT_FILE
        port_file.unlink(missing_ok=True)
        token = secrets.token_urlsafe(32)
        started = self._clock()
        proc = self.launcher.launch(self._launch_spec(uid, workspace, token))
        slot.process, slot.endpoint, slot.stopping, slot.stop_when_idle_of_builds = proc, None, False, False
        try:
            slot.endpoint = self._wait_ready(proc, port_file, token, uid)
        except Exception:
            proc.kill()
            slot.process = None
            raise
        LOG.info("worker for user %s ready on port %s (pid %s, %s) in %.1f s", uid, slot.endpoint.port, proc.pid,
                 proc.method, self._clock() - started)

    def _wait_ready(self, proc: WorkerProcess, port_file: Path, token: str, uid: int) -> Endpoint:
        deadline = time.monotonic() + self.config.start_timeout
        info = None
        while time.monotonic() < deadline:
            code = proc.poll()
            if code is not None:
                LOG.warning("worker for user %s exited during start-up with code %s", uid, code)
                raise WorkerUnavailable("Your planner could not be started. Please try again shortly.")
            if info is None and port_file.is_file():
                try:
                    info = json.loads(port_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    info = None
                if info is not None and int(info.get("pid") or 0) != proc.pid:
                    LOG.error("port file for user %s names pid %s, not the started pid %s", uid, info.get("pid"), proc.pid)
                    raise WorkerUnavailable("Your planner could not be started. Please try again shortly.")
            if info is not None:
                ep = Endpoint(uid, int(info["port"]), proc.pid, token)
                if self.port_owner_ok(ep):
                    try:
                        status, _ = call_worker(ep, "GET", "/api/ping", timeout=5)
                    except OSError:
                        status = 0
                    if status == 200:
                        return ep
            time.sleep(0.1)
        LOG.warning("worker for user %s was not ready within %.0f s", uid, self.config.start_timeout)
        raise WorkerUnavailable("Your planner is taking too long to start. Please try again shortly.")

    def port_owner_ok(self, ep: Endpoint) -> bool:
        """The listening socket on the worker's port belongs to the worker we started (not a process
        that took the port after the worker died)."""
        if not self.config.check_port_owner or not winapi.IS_WINDOWS:
            return True
        try:
            return winapi.tcp_listener_pids(ep.port) == {ep.pid}
        except OSError:
            LOG.warning("could not read the TCP listener table", exc_info=True)
            return False

    # ---- use ----
    def touch(self, user_id: int) -> None:
        self._slot(user_id).last_used = self._clock()

    def is_running(self, user_id: int) -> bool:
        slot = self._slots.get(int(user_id))
        return bool(slot and slot.process is not None and slot.process.poll() is None)

    def running_count(self) -> int:
        with self._slots_lock:
            slots = list(self._slots.values())
        return sum(1 for s in slots if s.process is not None and s.process.poll() is None)

    def current_endpoint(self, user_id: int) -> Endpoint | None:
        slot = self._slots.get(int(user_id))
        return slot.endpoint if slot and slot.process is not None and slot.process.poll() is None else None

    def mark_dead(self, user_id: int, ep: Endpoint, reason: str) -> None:
        """The proxy found the worker unusable (port owner changed, connection refused): stop it so the
        next request starts a fresh one."""
        slot = self._slot(user_id)
        with slot.lock:
            if slot.endpoint is ep or slot.endpoint == ep:
                LOG.warning("worker for user %s marked dead: %s", user_id, reason)
                self._kill(slot)

    # ---- stop ----
    def _kill(self, slot: _Slot) -> None:
        if slot.process is not None:
            slot.stopping = True
            slot.process.kill()
        slot.process, slot.endpoint = None, None
        if self.build_queue is not None:
            self.build_queue.worker_gone(slot.user_id)

    def stop(self, user_id: int, reason: str = "") -> None:
        """Stop now, running build or not (delete, disable, shutdown)."""
        slot = self._slots.get(int(user_id))
        if slot is None:
            return
        with slot.lock:
            if slot.process is not None:
                LOG.info("stopping worker for user %s (%s)", user_id, reason or "requested")
            self._kill(slot)

    def build_busy(self, user_id: int) -> bool:
        """A build is queued or running for the user, per the gateway queue or the worker itself."""
        if self.build_queue is not None and self.build_queue.has_build(user_id):
            return True
        ep = self.current_endpoint(user_id)
        if ep is None:
            return False
        try:
            status, body = call_worker(ep, "GET", "/api/build/status", timeout=15)
            if status == 200:
                return bool(json.loads(body).get("build_running"))
        except (OSError, ValueError):
            LOG.warning("could not read build status for user %s", user_id, exc_info=True)
        return True  # unknown: keep it (the hard idle cap still applies)

    def release(self, user_id: int, reason: str = "signed out") -> None:
        """Stop when no build is running; otherwise as soon as the build ends."""
        slot = self._slots.get(int(user_id))
        if slot is None or slot.process is None:
            return
        if self.build_busy(user_id):
            slot.stop_when_idle_of_builds = True
            LOG.info("worker for user %s stays up until its build ends (%s)", user_id, reason)
            return
        self.stop(user_id, reason)

    # ---- monitor ----
    def _on_exit(self, slot: _Slot) -> None:
        proc = slot.process
        code = proc.poll() if proc else None
        expected = slot.stopping
        if proc is not None:
            proc.kill()  # releases the job, handles and profile
        slot.process, slot.endpoint = None, None
        if self.build_queue is not None:
            self.build_queue.worker_gone(slot.user_id)
        if expected:
            return
        now = self._clock()
        slot.crashes.append(now)
        while slot.crashes and now - slot.crashes[0] > self.config.crash_window:
            slot.crashes.popleft()
        LOG.warning("worker for user %s exited unexpectedly with code %s", slot.user_id, code)
        if len(slot.crashes) > self.config.max_crashes:
            slot.cooldown_until = now + self.config.crash_cooldown
            LOG.error("worker for user %s crashed %s times in %.0f s; not restarting for %.0f s", slot.user_id,
                      len(slot.crashes), self.config.crash_window, self.config.crash_cooldown)

    def monitor_once(self) -> None:
        now = self._clock()
        with self._slots_lock:
            slots = list(self._slots.values())
        for slot in slots:
            if not slot.lock.acquire(blocking=False):
                continue  # starting or stopping right now
            restart = False
            try:
                if slot.process is not None and slot.process.poll() is not None:
                    was_stopping = slot.stopping
                    self._on_exit(slot)
                    restart = (not was_stopping and now - slot.last_used < self.config.idle_seconds
                               and now >= slot.cooldown_until)
            finally:
                slot.lock.release()
            if restart:
                try:
                    self.endpoint(slot.user_id)
                    LOG.info("worker for user %s restarted after a crash", slot.user_id)
                except Exception:
                    LOG.warning("restart of the worker for user %s failed", slot.user_id, exc_info=True)
                continue
            if slot.process is None:
                continue
            idle = now - slot.last_used
            hard_cap = self.config.idle_seconds + (self.build_queue.max_build_seconds if self.build_queue else 1800)
            if slot.stop_when_idle_of_builds and not self.build_busy(slot.user_id):
                self.stop(slot.user_id, "signed out; build finished")
            elif idle > hard_cap or (idle > self.config.idle_seconds and not self.build_busy(slot.user_id)):
                self.stop(slot.user_id, f"idle for {idle / 60:.0f} minutes")
        if self.accounts is not None and self.known_user_ids is not None and now - self._last_housekeeping > 3600:
            self._last_housekeeping = now
            try:
                self.accounts.housekeeping(self.known_user_ids())
            except Exception:
                LOG.warning("account housekeeping failed", exc_info=True)

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.config.monitor_interval):
                try:
                    self.monitor_once()
                except Exception:  # pragma: no cover - the monitor must keep running
                    LOG.exception("supervisor monitor pass failed")

        self._thread = threading.Thread(target=loop, name="worker-supervisor", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        with self._slots_lock:
            uids = list(self._slots)
        for uid in uids:
            self.stop(uid, "gateway shutting down")

    # ---- gateway lifecycle hooks (called by the gateway app after the store change succeeded) ----
    def user_created(self, user_id: int) -> None:
        workspace = self.workspace(user_id)
        workspace.mkdir(parents=True, exist_ok=True)
        if self.accounts is not None:
            self.accounts.ensure(user_id, workspace)
        if self.config.monarch_mapping_csv is not None:  # after ensure, so the copy inherits the workspace ACL
            target = workspace / MAPPING_SEED_RELPATH
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.config.monarch_mapping_csv, target)

    def user_disabled(self, user_id: int, disabled: bool) -> None:
        if disabled:
            self.stop(user_id, "user disabled")
            if self.build_queue is not None:
                self.build_queue.drop_user(user_id)
        if self.accounts is not None:
            self.accounts.disable(user_id, disabled)

    def user_deleted(self, user_id: int) -> None:
        self.stop(user_id, "user deleted")
        if self.build_queue is not None:
            self.build_queue.drop_user(user_id)
        workspace = self.workspace(user_id)
        if self.backups is not None and workspace.is_dir():
            self.backups.backup_user(user_id)
        if self.accounts is not None:
            self.accounts.remove(user_id, workspace)
        if workspace.exists():
            shutil.rmtree(workspace)
        with self._slots_lock:
            self._slots.pop(int(user_id), None)

    def signed_out(self, user_id: int, sessions_left: int) -> None:
        if sessions_left <= 0:
            self.release(user_id, "signed out")
