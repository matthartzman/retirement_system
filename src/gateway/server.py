"""Run the gateway: ``python -m src.gateway --db <gateway.db> --funnel-port 5065 --public-origin https://<node>.ts.net:8443
--data-root <data>``.

Two listeners, both bound to 127.0.0.1 and tagged by port (the trust boundary behind Funnel):
the **Funnel** listener, which Tailscale Funnel publishes (external 8443; 443 belongs to the trends
reporter), and an optional **local** listener for use on this machine. Port 0 picks a free port;
the chosen ports are printed as ``RETIREMENT_GATEWAY_READY {json}`` (and written to ``--ready-file``).

With ``--data-root`` the gateway runs the Phase 3 supervisor and proxy: one worker per signed-in user,
under the gateway's own account (``--launcher same-account``, development and CI) or the user's own
Windows account (``--launcher per-account``, needs the gateway to run as LocalSystem). Without it the
planner is not connected and authenticated requests get the Phase 2 placeholder.
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from src.access_core import is_loopback_host, tailscale_serves_port
from src.http_runtime.server import LocalHTTPServer, _Handler

from .backup_crypto import BackupCryptoError
from .app import GatewayConfig, GatewayListener, create_gateway_app
from .store import GatewayStore

READY_PREFIX = "RETIREMENT_GATEWAY_READY"
# The shared price-provider key names (``src/remote_mode._PROVIDER_KEYS``): --pass-env only, never --worker-env.
PROVIDER_KEY_NAMES = frozenset({
    "RETIREMENT_SYSTEM_FMP_API_KEY", "FMP_API_KEY", "FINANCIAL_MODELING_PREP_API_KEY",
    "RETIREMENT_SYSTEM_ALPHA_VANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY",
})
LOG = logging.getLogger("retirement.gateway.server")
# Turns on the worker's Monarch MCP connector (``src/monarch_connector.ENABLE_ENV``). Same-account workers still
# cannot connect: they have no private credential store (``src/secrets_store._remote_mode_guard``).
MONARCH_CONNECTOR_ENV = "RETIREMENT_SYSTEM_MONARCH_CONNECTOR"
CLIENT_SOCKET_TIMEOUT = 60.0
# P7-O3 defaults. 128 connections: ten users with a browser's six connections each is 60, and a proxied request
# holds its thread while the worker answers. 30 s is a generous total for a request line, headers and a body.
DEFAULT_MAX_CONNECTIONS = 128
DEFAULT_REQUEST_DEADLINE = 30.0
_BUSY = (b"HTTP/1.0 503 Service Unavailable\r\nRetry-After: 5\r\nContent-Type: text/plain\r\nContent-Length: 38\r\n"
         b"Connection: close\r\n\r\nThe server is busy. Try again shortly.\n")


class _DeadlineReader(io.RawIOBase):
    """Reads the socket under one overall deadline: each read may wait only for what is left of it, so a sender
    who dribbles a byte at a time cannot keep resetting a per-read timeout."""

    def __init__(self, sock: socket.socket, deadline_seconds: float, per_read: float) -> None:
        self._sock, self._per_read = sock, per_read
        self._deadline = time.monotonic() + deadline_seconds

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:  # noqa: ANN001
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("the request was not received in time")
        self._sock.settimeout(min(left, self._per_read))
        return self._sock.recv_into(buffer)

    def done(self) -> None:
        """The request is fully read: later socket operations (the reply) use the ordinary timeout again."""
        self._sock.settimeout(self._per_read)


class _GatewayHandler(_Handler):
    """Gate on the headers first, read a bounded body under a total deadline, then handle the request."""

    timeout = CLIENT_SOCKET_TIMEOUT

    def setup(self) -> None:
        super().setup()
        self._reader = _DeadlineReader(self.connection, getattr(self.server, "request_deadline", DEFAULT_REQUEST_DEADLINE),
                                       self.timeout)
        self.rfile = io.BufferedReader(self._reader)

    def _refuse(self, status: int, message: str) -> None:
        self._reader.done()
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        LOG.info("refused %s %s: %s", self.command, status, message)
        self.close_connection = True

    def _handle(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            return self._refuse(400, "bad Content-Length")
        app = self.server.retirement_app
        headers = {k: v for k, v in self.headers.items()}
        remote = self.client_address[0] if self.client_address else "127.0.0.1"
        refusal, limit = app.preflight(self.command, self.path, headers, remote)
        if refusal is not None:  # refused on the headers alone; the body is never read
            self._reader.done()
            self.close_connection = True
            refusal.headers["Connection"] = "close"
            return self._send_response(refusal)
        if length > limit:
            return self._refuse(413, "body over the limit")
        try:
            body = self.rfile.read(length) if length else b""
        except (TimeoutError, OSError):
            self.close_connection = True
            return None
        self._reader.done()
        self._send_response(app.handle_http(self.command, self.path, headers, body, remote))


class _GatewayHTTPServer(LocalHTTPServer):
    """No address reuse: on Windows SO_REUSEADDR lets a second process bind the same port. At most
    ``max_connections`` connections are served at once; the next one is refused with a 503 on the accept thread."""

    allow_reuse_address = False

    def __init__(self, server_address: tuple[str, int], app, *, max_connections: int = DEFAULT_MAX_CONNECTIONS,  # noqa: ANN001
                 request_deadline: float = DEFAULT_REQUEST_DEADLINE) -> None:
        ThreadingHTTPServer.__init__(self, server_address, _GatewayHandler)
        self.retirement_app = app
        self.request_deadline = float(request_deadline)
        self._slots = threading.BoundedSemaphore(max(1, int(max_connections)))

    def process_request(self, request, client_address) -> None:  # noqa: ANN001
        if not self._slots.acquire(blocking=False):
            try:
                request.settimeout(1.0)
                request.sendall(_BUSY)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:  # noqa: ANN001
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _origin(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme != "https" or not parts.hostname or parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError(f"--public-origin must be an https origin such as https://node.example.ts.net:8443, not {value!r}")
    return f"https://{parts.netloc}"


def _env_pair(value: str) -> tuple[str, str]:
    key, sep, val = value.partition("=")
    if not sep or not key.strip():
        raise argparse.ArgumentTypeError("--worker-env takes NAME=VALUE")
    if key.strip().upper() in PROVIDER_KEY_NAMES:
        raise argparse.ArgumentTypeError(f"{key.strip()} is a provider key: keep it in the gateway's environment and "
                                         "pass it with --pass-env, never on the command line")
    return key.strip(), val


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m src.gateway", description="Multi-user planner gateway.")
    p.add_argument("--db", required=True, help="path to gateway.db (created when missing)")
    p.add_argument("--host", default="127.0.0.1", help="bind address; only loopback is accepted")
    p.add_argument("--funnel-port", type=int, default=None, help="loopback port Tailscale Funnel points at")
    p.add_argument("--local-port", type=int, default=None, help="optional loopback port for use on this machine")
    p.add_argument("--public-origin", action="append", default=[], help="https origin users reach through Funnel")
    p.add_argument("--max-connections", type=int, default=DEFAULT_MAX_CONNECTIONS,
                   help="connections served at once per listener; the next gets a 503 (default 128)")
    p.add_argument("--request-deadline", type=float, default=DEFAULT_REQUEST_DEADLINE,
                   help="seconds allowed in total to receive one request's line, headers and body")
    p.add_argument("--hash-concurrency", type=int, default=4,
                   help="password hashes (32 MiB each) running at once; others wait, then get a 503")
    p.add_argument("--no-tailscale-check", action="store_true", help="skip the 'tailscale serve status' check (tests)")
    p.add_argument("--ready-file", help="also write the READY JSON to this file (the Windows service has no console)")
    w = p.add_argument_group("workers (Phase 3; all off without --data-root)")
    w.add_argument("--data-root", help="folder holding users/<id>/ workspaces")
    w.add_argument("--launcher", choices=("same-account", "per-account"), default="same-account",
                   help="run workers as the gateway's account (development, CI) or as each user's own account")
    w.add_argument("--account-prefix", default="rpw_", help="Windows account name prefix for per-account workers")
    w.add_argument("--account-rotate-days", type=float, default=90.0, help="rotate worker account passwords this often")
    w.add_argument("--provision", choices=("blank", "demo"), default="blank", help="a new user's first plan")
    w.add_argument("--install-dir", default=str(Path(__file__).resolve().parents[2]), help="the worker's code folder")
    w.add_argument("--python", default=sys.executable, help="the Python the workers run (readable by worker accounts)")
    w.add_argument("--idle-minutes", type=float, default=30.0, help="stop a worker after this long without a request")
    w.add_argument("--worker-start-timeout", type=float, default=60.0)
    w.add_argument("--worker-memory-mb", type=int, default=1792, help="Job Object memory cap per worker tree (0: none)")
    w.add_argument("--build-concurrency", type=int, default=2, help="builds running at once across all users")
    w.add_argument("--build-pool-max", type=int, default=4, help="process pool size per build (0: the build's default)")
    w.add_argument("--max-plans-per-user", type=int, default=10, help="plans one user may keep, the demo excluded (0: no limit)")
    w.add_argument("--user-disk-quota-mb", type=int, default=1024, help="disk one user's workspace may use (0: no limit)")
    w.add_argument("--max-build-minutes", type=float, default=30.0)
    w.add_argument("--worker-env", type=_env_pair, action="append", default=[],
                   help="NAME=VALUE passed to every worker (never a secret: use --pass-env)")
    w.add_argument("--pass-env", action="append", default=[],
                   help="copy this variable from the gateway's environment to workers (the shared provider key)")
    w.add_argument("--monarch-mapping-csv",
                   help="admin-curated Monarch account mapping CSV copied into each new user's workspace")
    w.add_argument("--backup-dir", help="encrypted backups go here; needs --backup-key-file (default "
                   "the ProgramData/RetirementPlannerGateway/backups folder). Never a synced or user-readable folder")
    w.add_argument("--backup-key-file", help="the backup encryption key (create it with 'ops backup-key create'); "
                   "backups are enabled only when this is given. Kept outside the backup folder")
    w.add_argument("--monarch-connector", action="store_true",
                   help="let users connect Monarch's read-only MCP connector (needs --launcher per-account)")
    w.add_argument("--backup-hours", type=float, default=24.0)
    w.add_argument("--backup-keep", type=int, default=14)
    return p


def protect_totp_at_startup(store: GatewayStore) -> None:
    """Seal clear-text TOTP secrets (P7-O1) and name any user whose sealed secret this account cannot open."""
    try:
        store.protect_totp_secrets()
    except Exception:  # noqa: BLE001 - never stop sign-in over this, but say so loudly
        LOG.error("could not seal the TOTP secrets in gateway.db; they are still in clear text", exc_info=True)
    unreadable = store.unreadable_totp_users()
    if unreadable:
        LOG.warning("the TOTP secret of user id(s) %s cannot be opened here (gateway.db from another machine or "
                    "account?); reset their two-factor from the Users page so they can enrol again",
                    ", ".join(str(u) for u in unreadable))


class _Runtime:
    """The supervisor, proxy and backups, built from the command line."""

    def __init__(self, args: argparse.Namespace, store: GatewayStore) -> None:
        from .accounts import NullAccountManager, WindowsAccountManager  # noqa: PLC0415
        from .build_queue import BuildQueue  # noqa: PLC0415
        from .launchers import PerAccountLauncher, SameAccountLauncher  # noqa: PLC0415
        from .proxy import WorkerProxy  # noqa: PLC0415
        from .supervisor import Supervisor, SupervisorConfig  # noqa: PLC0415

        data_root = Path(args.data_root).resolve()
        extra_env = dict(args.worker_env)
        for name in args.pass_env:
            if name in os.environ:
                extra_env[name] = os.environ[name]
        if args.monarch_connector:
            extra_env[MONARCH_CONNECTOR_ENV] = "1"  # src/monarch_connector.py ENABLE_ENV
        cfg = SupervisorConfig(
            data_root=data_root, install_dir=Path(args.install_dir), python=args.python, provision=args.provision,
            idle_seconds=args.idle_minutes * 60, start_timeout=args.worker_start_timeout,
            memory_limit_mb=args.worker_memory_mb or None, build_pool_max=args.build_pool_max or None,
            max_plans_per_user=args.max_plans_per_user, user_disk_quota_mb=args.user_disk_quota_mb,
            extra_env=extra_env,
            monarch_mapping_csv=Path(args.monarch_mapping_csv).resolve() if args.monarch_mapping_csv else None)
        if args.launcher == "per-account":
            accounts = WindowsAccountManager(store, data_root, prefix=args.account_prefix,
                                             rotate_days=args.account_rotate_days)
            launcher = PerAccountLauncher(accounts)
        else:
            accounts, launcher = NullAccountManager(), SameAccountLauncher()
        self.queue = BuildQueue(args.build_concurrency, max_build_seconds=args.max_build_minutes * 60)
        self.backups = None
        self.backup_dir: Path | None = None
        self.backup_interval = args.backup_hours * 3600
        self.data_root, self.store, self.started_at = data_root, store, time.time()
        if args.backup_key_file:
            from .backup_crypto import read_key_file  # noqa: PLC0415
            from .backup_dest import default_backup_dir, validate_backup_destination, validate_key_location  # noqa: PLC0415
            from .backup_store import EncryptedBackupScheduler  # noqa: PLC0415

            install = Path(args.install_dir)
            self.backup_dir = validate_backup_destination(args.backup_dir or default_backup_dir(), data_root=data_root,
                                                          install_dir=install, key_file=Path(args.backup_key_file))
            validate_key_location(Path(args.backup_key_file), backup_dir=self.backup_dir, data_root=data_root,
                                  install_dir=install)
            self.backups = EncryptedBackupScheduler(
                data_root=data_root, gateway_db=Path(args.db), dest=self.backup_dir,
                master=read_key_file(Path(args.backup_key_file)), user_ids=store.user_ids,
                interval_seconds=self.backup_interval, keep=args.backup_keep, secure_dir=self._secure_dir(args))
        elif args.backup_dir:
            raise ValueError("--backup-dir needs --backup-key-file: the gateway writes only encrypted backups")
        else:
            LOG.warning("no backups are configured (give --backup-key-file); the health page will warn")
        self.supervisor = Supervisor(cfg, launcher, accounts=accounts, build_queue=self.queue, backups=self.backups)
        self.supervisor.known_user_ids = store.user_ids
        self.proxy = WorkerProxy(self.supervisor, self.queue)

    @staticmethod
    def _secure_dir(args: argparse.Namespace):
        """Per-account mode: the backup folder is readable by the gateway account only."""
        if args.launcher != "per-account":
            return None
        from . import acl, winapi  # noqa: PLC0415

        gateway_sid = winapi.current_user_sid()
        return lambda path: acl.lock_gateway_only(path, gateway_sid=gateway_sid)

    def health(self) -> dict:
        from .health import build_health  # noqa: PLC0415

        return build_health(started_at=self.started_at, schema_version=self.store.schema_version(),
                            workers_running=self.supervisor.running_count(), build_running=len(self.queue.running()),
                            build_waiting=self.queue.waiting_count(), data_root=self.data_root,
                            backup_dir=self.backup_dir, backups=self.backups, backup_interval=self.backup_interval)

    def start(self) -> None:
        from .logs import start_housekeeping  # noqa: PLC0415

        self._log_stop = threading.Event()
        start_housekeeping(self.data_root, self.supervisor.is_running, self._log_stop)
        self.supervisor.start()
        self.proxy.start()
        if self.backups is not None:
            self.backups.start()

    def shutdown(self) -> None:
        if getattr(self, "_log_stop", None) is not None:
            self._log_stop.set()
        if self.backups is not None:
            self.backups.stop()
        self.proxy.shutdown()
        self.supervisor.shutdown()


def run_gateway(argv: list[str] | None, stop_event: threading.Event) -> int:
    """Parse the gateway's command line, serve until ``stop_event`` is set, return an exit code."""
    args = _parser().parse_args(argv)
    err = sys.stderr or sys.__stderr__
    if args.host != "127.0.0.1" and not is_loopback_host(args.host):
        print("The gateway binds loopback only (127.0.0.1); Tailscale Funnel reaches it there.", file=err)
        return 2
    if args.funnel_port is None and args.local_port is None:
        print("Give --funnel-port, --local-port or both.", file=err)
        return 2
    try:
        origins = tuple(_origin(o) for o in args.public_origin)
    except ValueError as exc:
        print(str(exc), file=err)
        return 2
    if args.funnel_port is not None and not origins:
        print("The Funnel listener needs --public-origin (the https address users open).", file=err)
        return 2
    if args.local_port and not args.no_tailscale_check and tailscale_serves_port(args.local_port):
        print(f"Tailscale is configured to serve port {args.local_port}, the gateway's local listener. Point Funnel at "
              "the --funnel-port only ('tailscale funnel reset', then 'tailscale funnel --https=8443 "
              "http://127.0.0.1:<funnel-port>').", file=err)
        return 2

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, stream=err)
    store = GatewayStore(args.db, hash_concurrency=args.hash_concurrency)
    protect_totp_at_startup(store)
    runtime = None
    try:
        runtime = _Runtime(args, store) if args.data_root else None
    except (OSError, ValueError, BackupCryptoError) as exc:
        print(f"Cannot start the workers: {exc}", file=err)
        return 2
    kwargs = {"upstream": runtime.proxy, "lifecycle": runtime.supervisor, "health": runtime.health} if runtime else {}
    app = create_gateway_app(store, config=GatewayConfig(public_origins=origins), **kwargs)
    servers: dict[str, _GatewayHTTPServer] = {}
    for kind, port in (("funnel", args.funnel_port), ("local", args.local_port)):
        if port is None:
            continue
        srv = _GatewayHTTPServer(("127.0.0.1", int(port)), None, max_connections=args.max_connections,
                                 request_deadline=args.request_deadline)
        srv.retirement_app = GatewayListener(app, kind, srv.server_address[1])
        servers[kind] = srv
    ready = {"host": "127.0.0.1", "funnel_port": servers["funnel"].server_address[1] if "funnel" in servers else None,
             "local_port": servers["local"].server_address[1] if "local" in servers else None,
             "schema_version": store.schema_version(), "workers": bool(runtime), "pid": os.getpid()}
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers.values()]
    if runtime is not None:
        runtime.start()
    for t in threads:
        t.start()
    if args.ready_file:
        ready_path = Path(args.ready_file)
        tmp = ready_path.with_name(ready_path.name + ".tmp")
        tmp.write_text(json.dumps(ready), encoding="utf-8")
        tmp.replace(ready_path)
    out = sys.stdout or sys.__stdout__
    if out is not None:
        print(f"{READY_PREFIX} {json.dumps(ready)}", file=out, flush=True)
    try:
        while not stop_event.wait(1.0):  # a timed wait keeps Ctrl+C working on Windows
            pass
    finally:
        for s in servers.values():
            s.shutdown()
            s.server_close()
        if runtime is not None:
            runtime.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    stop = threading.Event()
    try:
        return run_gateway(argv, stop)
    except KeyboardInterrupt:  # pragma: no cover
        stop.set()
        return 0
