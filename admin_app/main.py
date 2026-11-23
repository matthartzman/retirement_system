#!/usr/bin/env python3
"""Admin app: people, access grants, activity and the admin audit (loopback only; a per-boot local token gates every request).

Usage: python -m admin_app [--retirement-system-dir PATH] [--port 5056] [--no-open] [--print-open-url]
       python -m admin_app create-admin --username NAME      (makes the first administrator)

The trust boundary is described in ``admin_app/trust.py`` and ``src/http_runtime/local_token_gate.py``. There is no ``--host``: the server
binds 127.0.0.1 only. Browsers get in through the launcher's one-time handoff; ``--print-open-url`` prints that one-time URL
for an already-running Admin app instead of opening it.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.http_runtime.server import LocalHTTPServer  # noqa: E402
from src.http_runtime.wsgi_facade import Flask, Response, request  # noqa: E402
from src.identity import DB_FILENAME, LEGACY_ACCESS_DB, IdentityStore, open_identity_store  # noqa: E402
from src.http_runtime import data_exposure_check  # noqa: E402
from src.http_runtime.local_token_gate import LocalTokenGate, open_running_app, token_file_path  # noqa: E402

from admin_app import DEFAULT_PORT  # noqa: E402
from admin_app.processes import ProcessManager
from admin_app.routes_processes import register_processes
from admin_app.routes_system import register_system  # noqa: E402
from admin_app.routes_users import register_users  # noqa: E402
from admin_app.settings import SettingsService  # noqa: E402
from admin_app.trust import add_security_headers, check_funnel_target, check_request  # noqa: E402

LOOPBACK = "127.0.0.1"
GATE_NAME = "admin"  # token file: <workspace>/local_state/admin_local_token
FRONTEND = Path(__file__).resolve().parent / "frontend"
# Served files: exactly these and nothing else, so a path can never reach outside the frontend folder.
PAGES = {"/": (FRONTEND / "index.html", "text/html"), "/users.js": (FRONTEND / "users.js", "text/javascript"),
         "/admin.js": (FRONTEND / "admin.js", "text/javascript"),
         "/processes.js": (FRONTEND / "processes.js", "text/javascript"), "/admin.css": (FRONTEND / "admin.css", "text/css"),
         # the settings renderer is shared with the planner's Plan assumptions page: one file, served from the repo
         "/settings_renderer.js": (_REPO_ROOT / "frontend" / "js" / "settings_renderer.js", "text/javascript"),
         "/settings_renderer.css": (_REPO_ROOT / "frontend" / "css" / "settings_renderer.css", "text/css")}


def identity_db_path(retirement_system_dir: Path) -> Path:
    return Path(retirement_system_dir) / "local_state" / DB_FILENAME


def legacy_access_path(retirement_system_dir: Path) -> Path:
    return Path(retirement_system_dir) / "financial_trends_reporter" / "data" / LEGACY_ACCESS_DB


def create_app(store: IdentityStore, clock=time.time, settings: SettingsService | None = None,
               processes: ProcessManager | None = None, local_gate: LocalTokenGate | None = None) -> Flask:
    """``local_gate`` is the per-boot token gate (X-1). ``main()`` always passes one; ``None`` is for in-process tests only."""
    app = Flask("admin_app", static_folder=str(FRONTEND))
    app.local_gate = local_gate
    app.data_exposure_warnings = []  # main() fills it (F-11); the front page shows it as a banner
    app.before_request(check_request)
    if local_gate is not None:
        app.before_request(local_gate.check)  # after the Host/Origin/proxy checks, before any route
        local_gate.register(app)
    app.after_request(add_security_headers)

    def page(path: str) -> Response:
        file, mime = PAGES[path]
        text = file.read_text(encoding="utf-8")
        if path == "/":  # F-11: a visible notice when the data or token file is open to other accounts or under OneDrive
            text = data_exposure_check.inject_banner(text, app.data_exposure_warnings)
        return Response(text, content_type=f"{mime}; charset=utf-8")

    for route in PAGES:
        app.route(route, methods=["GET"])(lambda route=route: page(route))

    @app.route("/api/ping", methods=["GET"])
    def ping():
        return Response('{"success": true, "app": "admin"}', content_type="application/json")

    register_users(app, store, clock)
    if settings is not None:
        register_system(app, store, settings, clock)
        register_processes(app, store, processes or ProcessManager(
            settings.root, settings.planner_port, graceful_stop=lambda: bool(settings.shutdown_planner().get("success"))), clock)
    return app


def _port_in_use(port: int) -> bool:
    # LocalHTTPServer sets SO_REUSEADDR, which on Windows lets a second server bind a port that is
    # already serving, so probe before binding rather than trust bind().
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((LOOPBACK, port)) == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retirement-system-dir", default=str(_REPO_ROOT), help="workspace root; defaults to this repo's own root")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open a browser tab")
    parser.add_argument("--print-open-url", action="store_true",
                        help="Print a one-time sign-in URL for the running Admin app (valid 60 seconds) instead of opening it")
    args = parser.parse_args(argv)

    url = f"http://{LOOPBACK}:{args.port}/"
    root = Path(args.retirement_system_dir)
    if _port_in_use(args.port):
        if args.print_open_url:
            return open_running_app(url, root, GATE_NAME, print_only=True, opener=webbrowser.open)
        print(f"Admin app is already running; opening {url}")
        if args.no_open:
            return 0
        return open_running_app(url, root, GATE_NAME, print_only=False, opener=webbrowser.open)
    if args.print_open_url:
        print("The Admin app is not running; start it first.", file=sys.stderr)
        return 1
    if (problem := check_funnel_target(args.port)):
        print(problem, file=sys.stderr)
        return 1
    store = open_identity_store(identity_db_path(root), legacy_access_path=legacy_access_path(root))
    gate = LocalTokenGate.start(GATE_NAME, root, module="-m admin_app")
    flask_app = create_app(store, settings=SettingsService(root), local_gate=gate)
    flask_app.data_exposure_warnings = data_exposure_check.check_paths(
        [("identity database folder", identity_db_path(root).parent), ("local token file", token_file_path(root, GATE_NAME))])
    data_exposure_check.announce("Admin app", flask_app.data_exposure_warnings)
    server = LocalHTTPServer((LOOPBACK, int(args.port)), flask_app)
    print(f"Admin app listening on {url} (this computer only)")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(gate.open_url(url))).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Admin app stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
