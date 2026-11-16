"""Windows service wrapper for the gateway, written directly against advapi32 with ctypes.

    python -m src.gateway.service install --config gateway.json
    python -m src.gateway.service start | stop | status | remove
    python -m src.gateway.service debug --config gateway.json     (console, no SCM)

``run`` is what the service control manager launches.  The config file is JSON:
``{"argv": ["--db", "...", ...], "log_file": "<optional path>"}`` where ``argv`` holds the
gateway's normal command-line arguments.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable

log = logging.getLogger("retirement.gateway.service")

DEFAULT_NAME = "RetirementGateway"
DEFAULT_DISPLAY_NAME = "Retirement Planner Gateway"
DESCRIPTION = "Retirement Planner multi-user gateway: sign-in, per-user workers and scheduled backups."
REPO_ROOT = Path(__file__).resolve().parents[2]

# Win32 constants
ERROR_ACCESS_DENIED = 5
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_NOT_ACTIVE = 1062
ERROR_FAILED_SERVICE_CONTROLLER_CONNECT = 1063
ERROR_SERVICE_SPECIFIC_ERROR = 1066

SC_MANAGER_CONNECT = 0x0001
SC_MANAGER_CREATE_SERVICE = 0x0002
SERVICE_QUERY_STATUS = 0x0004
SERVICE_START = 0x0010
SERVICE_STOP = 0x0020
DELETE = 0x00010000
SERVICE_ALL_ACCESS = 0xF01FF

SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_AUTO_START = 0x00000002
SERVICE_ERROR_NORMAL = 0x00000001

SERVICE_CONFIG_DESCRIPTION = 1
SERVICE_CONFIG_FAILURE_ACTIONS = 2
SERVICE_CONFIG_FAILURE_ACTIONS_FLAG = 4
SC_ACTION_RESTART = 1

SERVICE_STOPPED = 1
SERVICE_START_PENDING = 2
SERVICE_STOP_PENDING = 3
SERVICE_RUNNING = 4
STATE_NAMES = {
    1: "STOPPED",
    2: "START_PENDING",
    3: "STOP_PENDING",
    4: "RUNNING",
    5: "CONTINUE_PENDING",
    6: "PAUSE_PENDING",
    7: "PAUSED",
}

SERVICE_ACCEPT_STOP = 0x01
SERVICE_ACCEPT_SHUTDOWN = 0x04
SERVICE_CONTROL_STOP = 1
SERVICE_CONTROL_INTERROGATE = 4
SERVICE_CONTROL_SHUTDOWN = 5

JOIN_TIMEOUT_SECONDS = 30.0


# ----------------------------------------------------------------- errors / pure helpers
def win_error(code: int, what: str) -> OSError:
    if code == ERROR_ACCESS_DENIED:
        return OSError(code, f"Access denied while {what}: an elevated (Administrator) shell is needed")
    return OSError(code, f"Windows error {code} while {what}")


def _quote(text: str) -> str:
    return f'"{text}"'


def service_command_line(config: Path, name: str) -> str:
    """The service binary path the SCM runs (pure; no filesystem access).

    The script path, not ``-m src.gateway.service``: the SCM starts services in System32, where the
    ``src`` package cannot be found; ``run`` then moves to the install root itself."""
    shown_name = _quote(name) if any(c.isspace() for c in name) else name
    script = REPO_ROOT / "src" / "gateway" / "service.py"
    return (
        f"{_quote(sys.executable)} -E -s {_quote(str(script))} run "
        f"--config {_quote(os.path.abspath(str(config)))} --name {shown_name}"
    )


def config_argv(path: Path) -> list[str]:
    """Load and validate a gateway.json; return the gateway argv."""
    return _load_config(path)[0]


def _load_config(path: Path) -> tuple[list[str], str | None]:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"config file not found: {path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"config file {path} is not valid JSON: {type(exc).__name__}") from None
    if not isinstance(data, dict):
        raise ValueError("config must be a JSON object")
    argv = data.get("argv")
    if not isinstance(argv, list) or not all(isinstance(a, str) for a in argv):
        raise ValueError('config "argv" must be a list of strings')
    log_file = data.get("log_file")
    if log_file is not None and not isinstance(log_file, str):
        raise ValueError('config "log_file" must be a string')
    return list(argv), (log_file or None)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m src.gateway.service", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add_name(p: argparse.ArgumentParser) -> None:
        p.add_argument("--name", default=DEFAULT_NAME, help="service name")

    p = sub.add_parser("install", help="register the Windows service")
    p.add_argument("--config", required=True, type=Path)
    add_name(p)
    p.add_argument("--display-name", default=DEFAULT_DISPLAY_NAME)
    for cmd in ("remove", "start", "stop", "status"):
        add_name(sub.add_parser(cmd))
    p = sub.add_parser("run", help="entry point used by the service control manager")
    p.add_argument("--config", required=True, type=Path)
    add_name(p)
    p = sub.add_parser("debug", help="run the gateway in this console until Ctrl+C")
    p.add_argument("--config", required=True, type=Path)
    return parser.parse_args(argv)


# ------------------------------------------------------------------- service state machine
class ServiceRunner:
    """Drives the gateway thread and reports SCM states; testable without the SCM.

    ``run_fn(stop_event) -> int`` runs the gateway.  ``report(state, exit_code)`` is called
    for every state change (``exit_code`` is only meaningful with STOPPED).
    """

    def __init__(
        self,
        run_fn: Callable[[threading.Event], int],
        report: Callable[[int, int], None] | None = None,
        join_timeout: float = JOIN_TIMEOUT_SECONDS,
    ) -> None:
        self._run_fn = run_fn
        self._report = report or (lambda state, code: None)
        self._join_timeout = join_timeout
        self.stop_event = threading.Event()
        self.state = SERVICE_STOPPED
        self.exit_code = 0
        self._thread: threading.Thread | None = None

    def _set_state(self, state: int, code: int = 0) -> None:
        self.state = state
        self._report(state, code)

    def _target(self) -> None:
        try:
            self.exit_code = int(self._run_fn(self.stop_event) or 0)
        except Exception:  # noqa: BLE001 - logged, becomes a non-zero exit code
            log.exception("gateway crashed")
            self.exit_code = 1

    def start(self) -> None:
        self._set_state(SERVICE_START_PENDING)
        self._thread = threading.Thread(target=self._target, name="gateway-main", daemon=True)
        self._thread.start()
        self._set_state(SERVICE_RUNNING)

    def handle_control(self, code: int) -> int:
        if code in (SERVICE_CONTROL_STOP, SERVICE_CONTROL_SHUTDOWN):
            if self.state != SERVICE_STOP_PENDING:
                self._set_state(SERVICE_STOP_PENDING)
            self.stop_event.set()
        elif code == SERVICE_CONTROL_INTERROGATE:
            self._set_state(self.state)
        return 0

    def finish(self) -> int:
        """Join the gateway thread (bounded) and report STOPPED; returns the exit code."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._join_timeout)
            if thread.is_alive():
                log.error("gateway did not stop within %.0f s", self._join_timeout)
                self.exit_code = self.exit_code or 1
        self._set_state(SERVICE_STOPPED, self.exit_code)
        return self.exit_code

    def run(self) -> int:
        """Start, wait for the gateway to end (stop control or its own exit), report STOPPED."""
        self.start()
        thread = self._thread
        assert thread is not None
        while thread.is_alive():
            thread.join(timeout=0.5)
            if self.stop_event.is_set():
                break
        return self.finish()


# ------------------------------------------------------------------------------ gateway glue
def _import_run_gateway() -> Callable[[list[str], threading.Event], int]:
    from src.gateway.server import run_gateway  # lazy: not needed to install or query

    return run_gateway


def _configure_logging(log_file: str | None) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    elif not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _make_run_fn(argv: list[str]) -> Callable[[threading.Event], int]:
    def run_fn(stop_event: threading.Event) -> int:
        return _import_run_gateway()(list(argv), stop_event)

    return run_fn


def _enter_repo_root() -> None:
    os.chdir(REPO_ROOT)
    root = str(REPO_ROOT)
    if not sys.path or sys.path[0] != root:
        sys.path.insert(0, root)


# ------------------------------------------------------------------------------- ctypes layer
class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


class SERVICE_DESCRIPTION(ctypes.Structure):
    _fields_ = [("lpDescription", wintypes.LPWSTR)]


class SC_ACTION(ctypes.Structure):
    _fields_ = [("Type", wintypes.DWORD), ("Delay", wintypes.DWORD)]


class SERVICE_FAILURE_ACTIONS(ctypes.Structure):
    _fields_ = [
        ("dwResetPeriod", wintypes.DWORD),
        ("lpRebootMsg", wintypes.LPWSTR),
        ("lpCommand", wintypes.LPWSTR),
        ("cActions", wintypes.DWORD),
        ("lpsaActions", ctypes.POINTER(SC_ACTION)),
    ]


class SERVICE_FAILURE_ACTIONS_FLAG(ctypes.Structure):
    _fields_ = [("fFailureActionsOnNonCrashFailures", wintypes.BOOL)]


class SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [("lpServiceName", wintypes.LPWSTR), ("lpServiceProc", ctypes.c_void_p)]


if sys.platform == "win32":
    _SERVICE_MAIN_TYPE = ctypes.WINFUNCTYPE(None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))
    _HANDLER_EX_TYPE = ctypes.WINFUNCTYPE(wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p)
else:  # pragma: no cover - the service only exists on Windows
    _SERVICE_MAIN_TYPE = _HANDLER_EX_TYPE = None

# Callback objects must outlive the dispatcher call; keep them at module level.
_KEEPALIVE: dict[str, object] = {}
_ADVAPI: ctypes.WinDLL | None = None  # type: ignore[name-defined]


def _adv():
    global _ADVAPI
    if _ADVAPI is None:
        if sys.platform != "win32":
            raise OSError("Windows services are only available on Windows")
        dll = ctypes.WinDLL("advapi32", use_last_error=True)
        h = ctypes.c_void_p
        dll.OpenSCManagerW.restype = h
        dll.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
        dll.OpenServiceW.restype = h
        dll.OpenServiceW.argtypes = [h, wintypes.LPCWSTR, wintypes.DWORD]
        dll.CreateServiceW.restype = h
        dll.CreateServiceW.argtypes = [
            h, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.LPCWSTR,
            wintypes.LPCWSTR, wintypes.LPCWSTR,
        ]  # fmt: skip
        dll.ChangeServiceConfig2W.restype = wintypes.BOOL
        dll.ChangeServiceConfig2W.argtypes = [h, wintypes.DWORD, ctypes.c_void_p]
        dll.StartServiceW.restype = wintypes.BOOL
        dll.StartServiceW.argtypes = [h, wintypes.DWORD, ctypes.c_void_p]
        dll.ControlService.restype = wintypes.BOOL
        dll.ControlService.argtypes = [h, wintypes.DWORD, ctypes.POINTER(SERVICE_STATUS)]
        dll.QueryServiceStatus.restype = wintypes.BOOL
        dll.QueryServiceStatus.argtypes = [h, ctypes.POINTER(SERVICE_STATUS)]
        dll.DeleteService.restype = wintypes.BOOL
        dll.DeleteService.argtypes = [h]
        dll.CloseServiceHandle.restype = wintypes.BOOL
        dll.CloseServiceHandle.argtypes = [h]
        dll.StartServiceCtrlDispatcherW.restype = wintypes.BOOL
        dll.StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(SERVICE_TABLE_ENTRY)]
        dll.RegisterServiceCtrlHandlerExW.restype = h
        dll.RegisterServiceCtrlHandlerExW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
        dll.SetServiceStatus.restype = wintypes.BOOL
        dll.SetServiceStatus.argtypes = [h, ctypes.POINTER(SERVICE_STATUS)]
        _ADVAPI = dll
    return _ADVAPI


def _fail(what: str) -> OSError:
    return win_error(ctypes.get_last_error(), what)


class _Handle:
    """Context manager closing an SCM or service handle."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __enter__(self) -> int:
        return self.value

    def __exit__(self, *exc) -> None:
        _adv().CloseServiceHandle(self.value)


def _open_scm(access: int) -> _Handle:
    handle = _adv().OpenSCManagerW(None, None, access)
    if not handle:
        raise _fail("opening the service control manager")
    return _Handle(handle)


def _open_service(scm: int, name: str, access: int) -> _Handle:
    handle = _adv().OpenServiceW(scm, name, access)
    if not handle:
        raise _fail(f"opening service {name}")
    return _Handle(handle)


def install_service(name: str, display_name: str, config: Path) -> None:
    config = Path(config)
    config_argv(config)  # refuse to install a config that does not parse
    binary = service_command_line(config, name)
    adv = _adv()
    with _open_scm(SC_MANAGER_CREATE_SERVICE) as scm:
        handle = adv.CreateServiceW(
            scm, name, display_name, SERVICE_ALL_ACCESS, SERVICE_WIN32_OWN_PROCESS, SERVICE_AUTO_START,
            SERVICE_ERROR_NORMAL, binary, None, None, None, None, None,
        )  # fmt: skip
        if not handle:
            raise _fail(f"creating service {name}")
        with _Handle(handle) as svc:
            desc = SERVICE_DESCRIPTION(DESCRIPTION)
            if not adv.ChangeServiceConfig2W(svc, SERVICE_CONFIG_DESCRIPTION, ctypes.byref(desc)):
                raise _fail("setting the service description")
            actions = (SC_ACTION * 3)(*[SC_ACTION(SC_ACTION_RESTART, 10_000) for _ in range(3)])
            failure = SERVICE_FAILURE_ACTIONS(86400, None, None, 3, actions)
            if not adv.ChangeServiceConfig2W(svc, SERVICE_CONFIG_FAILURE_ACTIONS, ctypes.byref(failure)):
                raise _fail("setting the failure actions")
            flag = SERVICE_FAILURE_ACTIONS_FLAG(True)
            if not adv.ChangeServiceConfig2W(svc, SERVICE_CONFIG_FAILURE_ACTIONS_FLAG, ctypes.byref(flag)):
                raise _fail("setting the failure-actions flag")


def query_status(name: str) -> int:
    """Current service state (SERVICE_*); raises OSError(1060) when not installed."""
    status = SERVICE_STATUS()
    with _open_scm(SC_MANAGER_CONNECT) as scm, _open_service(scm, name, SERVICE_QUERY_STATUS) as svc:
        if not _adv().QueryServiceStatus(svc, ctypes.byref(status)):
            raise _fail(f"querying service {name}")
    return int(status.dwCurrentState)


def _wait_state(name: str, wanted: set[int], timeout: float) -> int:
    deadline = time.monotonic() + timeout
    state = query_status(name)
    while state not in wanted and time.monotonic() < deadline:
        time.sleep(0.5)
        state = query_status(name)
    return state


def start_service(name: str, timeout: float = 30.0) -> int:
    with _open_scm(SC_MANAGER_CONNECT) as scm, _open_service(scm, name, SERVICE_START | SERVICE_QUERY_STATUS) as svc:
        if not _adv().StartServiceW(svc, 0, None):
            raise _fail(f"starting service {name}")
    return _wait_state(name, {SERVICE_RUNNING, SERVICE_STOPPED}, timeout)


def stop_service(name: str, timeout: float = 40.0) -> int:
    status = SERVICE_STATUS()
    with _open_scm(SC_MANAGER_CONNECT) as scm, _open_service(scm, name, SERVICE_STOP | SERVICE_QUERY_STATUS) as svc:
        if not _adv().ControlService(svc, SERVICE_CONTROL_STOP, ctypes.byref(status)):
            code = ctypes.get_last_error()
            if code != ERROR_SERVICE_NOT_ACTIVE:
                raise win_error(code, f"stopping service {name}")
    return _wait_state(name, {SERVICE_STOPPED}, timeout)


def remove_service(name: str) -> None:
    with _open_scm(SC_MANAGER_CONNECT) as scm, _open_service(scm, name, DELETE) as svc:
        if not _adv().DeleteService(svc):
            raise _fail(f"deleting service {name}")


# ------------------------------------------------------------------ SCM-side service main
_ACTIVE: dict[str, object] = {}


def _start_dispatcher(name: str, main_proc: Callable) -> None:
    """Hand the thread to the SCM; returns when the service has stopped."""
    table = (SERVICE_TABLE_ENTRY * 2)()
    table[0].lpServiceName = name
    table[0].lpServiceProc = ctypes.cast(main_proc, ctypes.c_void_p)
    table[1].lpServiceName = None
    table[1].lpServiceProc = None
    _KEEPALIVE["table"] = table
    if not _adv().StartServiceCtrlDispatcherW(table):
        raise _fail("connecting to the service control manager")


def _service_main_body(name: str, run_fn: Callable[[threading.Event], int]) -> None:
    adv = _adv()
    status = SERVICE_STATUS(SERVICE_WIN32_OWN_PROCESS, SERVICE_START_PENDING, 0, 0, 0, 0, 30000)
    handle_box: dict[str, int] = {}
    checkpoint = [0]

    def report(state: int, code: int) -> None:
        status.dwCurrentState = state
        pending = state in (SERVICE_START_PENDING, SERVICE_STOP_PENDING)
        status.dwControlsAccepted = 0 if pending or state == SERVICE_STOPPED else (SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN)
        if state == SERVICE_STOPPED and code:
            status.dwWin32ExitCode = ERROR_SERVICE_SPECIFIC_ERROR
            status.dwServiceSpecificExitCode = code
        else:
            status.dwWin32ExitCode = 0
            status.dwServiceSpecificExitCode = 0
        if pending:
            checkpoint[0] += 1
            status.dwCheckPoint = checkpoint[0]
            status.dwWaitHint = 30000
        else:
            status.dwCheckPoint = 0
            status.dwWaitHint = 0
        if handle_box.get("h"):
            adv.SetServiceStatus(handle_box["h"], ctypes.byref(status))

    runner = ServiceRunner(run_fn, report)

    def handler(control, event_type, event_data, context):  # noqa: ARG001
        return runner.handle_control(int(control))

    handler_cb = _HANDLER_EX_TYPE(handler)
    _KEEPALIVE["handler"] = handler_cb
    handle = adv.RegisterServiceCtrlHandlerExW(name, ctypes.cast(handler_cb, ctypes.c_void_p), None)
    if not handle:
        log.error("RegisterServiceCtrlHandlerEx failed: %s", ctypes.get_last_error())
        return
    handle_box["h"] = handle
    _ACTIVE["runner"] = runner
    runner.run()


def run_service(name: str, config: Path) -> int:
    """Entry point for ``run``: hand control to the SCM dispatcher."""
    _enter_repo_root()
    argv, log_file = _load_config(config)
    _configure_logging(log_file)
    run_fn = _make_run_fn(argv)

    def service_main(argc, argv_ptr):  # noqa: ARG001
        try:
            _service_main_body(name, run_fn)
        except Exception:  # noqa: BLE001
            log.exception("service main failed")

    main_cb = _SERVICE_MAIN_TYPE(service_main)
    _KEEPALIVE["service_main"] = main_cb
    try:
        _start_dispatcher(name, main_cb)
    except OSError as exc:
        if exc.errno == ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
            print("Not started by the service control manager; use `debug --config <path>` to run in a console.")
            return 2
        raise
    return 0



def run_debug(config: Path) -> int:
    _enter_repo_root()
    argv, log_file = _load_config(config)
    _configure_logging(log_file)
    runner = ServiceRunner(_make_run_fn(argv))
    runner.start()
    try:
        while runner._thread is not None and runner._thread.is_alive():  # noqa: SLF001
            runner._thread.join(timeout=0.5)  # noqa: SLF001
    except KeyboardInterrupt:
        print("Stopping...")
        runner.handle_control(SERVICE_CONTROL_STOP)
    return runner.finish()


# ----------------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "install":
            install_service(args.name, args.display_name, args.config)
            print(f"Installed service {args.name}. Start it with: python -m src.gateway.service start --name {args.name}")
        elif args.command == "remove":
            try:
                stop_service(args.name)
            except OSError as exc:
                if exc.errno == ERROR_SERVICE_DOES_NOT_EXIST:
                    raise
            remove_service(args.name)
            print(f"Removed service {args.name}.")
        elif args.command == "start":
            state = start_service(args.name)
            print(f"{args.name}: {STATE_NAMES.get(state, state)}")
        elif args.command == "stop":
            state = stop_service(args.name)
            print(f"{args.name}: {STATE_NAMES.get(state, state)}")
        elif args.command == "status":
            try:
                print(f"{args.name}: {STATE_NAMES.get(query_status(args.name), 'UNKNOWN')}")
            except OSError as exc:
                if exc.errno == ERROR_SERVICE_DOES_NOT_EXIST:
                    print(f"{args.name}: not installed")
                    return 1
                raise
        elif args.command == "run":
            return run_service(args.name, args.config)
        elif args.command == "debug":
            return run_debug(args.config)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
