from __future__ import annotations
"""Headless remote worker: one user's planner server behind the multi-user gateway.

Run by the supervisor (Phase 3), one process per signed-in user::

    python -m src.remote_worker --workspace <data/users/<id>> --provision demo|blank|none
        [--port-file <path>] [--parent-pid <pid>]

with ``RETIREMENT_SYSTEM_SERVER_API_TOKEN`` set in the environment to a random per-worker token
(never on the command line, which other accounts can read from the process list).

What it does, in order (modelled on ``tools/e2e_server.py``, not ``main.py --mode server``,
which opens a browser on the host and does not provision the workspace):

1. Switches remote mode on (``RETIREMENT_SYSTEM_REMOTE_MODE=1``) and points the workspace,
   the legacy database, ``app.db`` and the output folder at ``--workspace`` through the
   environment, before any application module that caches the workspace is imported. Values
   the supervisor already pinned are kept (they still have to lie inside the workspace).
2. Refuses to start (exit code 2, message on stderr) without a token.
3. Provisions the plan explicitly: ``demo`` copies the shipped seed plan, ``blank`` copies it
   and clears the household's facts (Start New Plan), ``none`` leaves the workspace as it is.
   A plan that already has rows is never overwritten.
4. Runs the usual startup bootstrap (env defaults, logging into the workspace, migration).
5. Binds ``127.0.0.1`` on port 0 and reports the chosen port: one JSON line on stdout,
   ``RETIREMENT_WORKER_READY {"port": ..., "pid": ..., "provisioned": ...}``, and the same JSON
   written atomically to ``--port-file`` when given.
6. With ``--parent-pid``, exits as soon as that process ends (the parent-death watchdog), so a
   crashed supervisor never leaves workers behind.

Phase 0 measured about 1 s to listening on an empty workspace and 2.5 s seeded (source run).
"""

import argparse
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path

READY_PREFIX = "RETIREMENT_WORKER_READY "
PROVISION_CHOICES = ("demo", "blank", "none")
EXIT_REFUSED = 2


def _pin_environment(workspace: Path) -> None:
    os.environ["RETIREMENT_SYSTEM_REMOTE_MODE"] = "1"
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace)
    os.environ["RETIREMENT_SYSTEM_NO_AUTO_OPEN"] = "1"
    os.environ["RETIREMENT_SYSTEM_DASHBOARD_HOST"] = "127.0.0.1"
    os.environ.setdefault("RETIREMENT_SYSTEM_SQLITE_DB", str(workspace / "local_state" / "retirement_system_v10.db"))
    os.environ.setdefault("RETIREMENT_SYSTEM_APP_DB", str(workspace / "local_state" / "app.db"))
    os.environ.setdefault("RETIREMENT_SYSTEM_OUTPUT_DIR", str(workspace / "output"))


def provision(workspace: Path, how: str) -> str:
    """Make the workspace's plan explicit. Returns what was done: ``demo``, ``blank``,
    ``existing`` (a plan with rows was already there) or ``none`` (left empty)."""
    from src import platform_runtime  # noqa: PLC0415
    from src.active_plan import PLAN_FILE_NAME, plan_file_has_rows  # noqa: PLC0415

    platform_runtime.ensure_workspace_dirs()
    plan_file = workspace / PLAN_FILE_NAME
    if plan_file_has_rows(plan_file):
        return "existing"
    if how == "none":
        return "none"
    seed = platform_runtime.demo_seed_path()
    if not seed.is_file():
        raise RuntimeError("the shipped demo seed plan file is missing from this install")
    tmp = plan_file.with_name(plan_file.name + ".provision")
    shutil.copy2(seed, tmp)
    for suffix in ("", "-wal", "-shm"):
        plan_file.with_name(plan_file.name + suffix).unlink(missing_ok=True)
    tmp.replace(plan_file)
    if how == "blank":
        # Start New Plan on the fresh copy: the workspace plan is the active plan at this point
        # (the registry bootstraps to it), and plan rows are edited only through active_plan.
        from src import plan_registry  # noqa: PLC0415
        from src.active_plan import active_plan_path, edit_active_plan  # noqa: PLC0415
        from src.blank_plan import blank_plan_rows  # noqa: PLC0415

        if not plan_registry.same_path(active_plan_path(), plan_file):
            raise RuntimeError("blank provisioning needs the workspace plan to be the active plan")
        with edit_active_plan(protect_values=False) as edit:
            blank_plan_rows(edit.store)
    if not plan_file_has_rows(plan_file):
        raise RuntimeError("provisioning the workspace plan imported no rows")
    return how


def _parent_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes  # noqa: PLC0415
        from ctypes import wintypes  # noqa: PLC0415

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)  # QUERY_LIMITED_INFORMATION | SYNCHRONIZE
        if not handle:
            return False
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT: still running
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def start_parent_watchdog(pid: int, *, interval: float = 1.0) -> threading.Thread:
    """Exit this process (status 3) once ``pid`` is gone. Polls, so it also covers a parent
    that ends before the watchdog starts."""
    def watch() -> None:
        while _parent_alive(pid):
            time.sleep(interval)
        sys.stderr.write(f"remote worker: parent process {pid} ended; exiting\n")
        sys.stderr.flush()
        os._exit(3)

    thread = threading.Thread(target=watch, name="parent-watchdog", daemon=True)
    thread.start()
    return thread


def _exclusive_server_class():
    """``LocalHTTPServer`` without address reuse, and with ``SO_EXCLUSIVEADDRUSE`` on Windows.

    The desktop server sets ``allow_reuse_address`` (``SO_REUSEADDR``), and on Windows a socket
    bound that way can have its port taken over by a later bind from another process. With one
    worker per mutually untrusted user that would let one user's worker capture another's
    traffic, so the worker's listening socket is exclusive.
    """
    import socket  # noqa: PLC0415

    from src.http_runtime.server import LocalHTTPServer  # noqa: PLC0415

    class ExclusiveLocalHTTPServer(LocalHTTPServer):
        allow_reuse_address = False

        def server_bind(self) -> None:
            exclusive = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
            if exclusive is not None:
                self.socket.setsockopt(socket.SOL_SOCKET, exclusive, 1)
            super().server_bind()

    return ExclusiveLocalHTTPServer


def _write_port_file(path: Path, info: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(info), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headless remote worker: one user's planner server behind the gateway.")
    parser.add_argument("--workspace", required=True, help="the user's own workspace folder")
    parser.add_argument("--provision", choices=PROVISION_CHOICES, required=True,
                        help="demo: the shipped demo plan; blank: a new plan; none: as it is")
    parser.add_argument("--port-file", help="where to write the chosen port as JSON")
    parser.add_argument("--parent-pid", type=int, help="exit when this process ends")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    _pin_environment(workspace)
    if args.parent_pid:
        start_parent_watchdog(args.parent_pid)

    from src import remote_mode  # noqa: PLC0415 - after the environment is pinned

    try:
        remote_mode.assert_startup_ok()
        for name in ("RETIREMENT_SYSTEM_SQLITE_DB", "RETIREMENT_SYSTEM_APP_DB", "RETIREMENT_SYSTEM_OUTPUT_DIR"):
            remote_mode.confine_path(os.environ[name], what=name)
    except (remote_mode.RemoteModeError, remote_mode.PathOutsideWorkspace) as exc:
        sys.stderr.write(f"remote worker: {exc}\n")
        return EXIT_REFUSED

    provisioned = provision(workspace, args.provision)

    from src.bootstrap import run_startup_bootstrap  # noqa: PLC0415

    run_startup_bootstrap()

    from src.http_runtime.host_guard import assert_safe_to_bind  # noqa: PLC0415
    from src.server import create_app  # noqa: PLC0415

    assert_safe_to_bind("127.0.0.1", remote_mode.worker_token())
    server = _exclusive_server_class()(("127.0.0.1", 0), create_app())
    info = {"port": int(server.server_address[1]), "pid": os.getpid(), "provisioned": provisioned}
    if args.port_file:
        _write_port_file(Path(args.port_file), info)
    sys.stdout.write(READY_PREFIX + json.dumps(info) + "\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
