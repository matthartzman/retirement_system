#!/usr/bin/env python3
"""Financial trends reporter -- standalone entry point (ticket 306).

A small local server (reusing retirement_system's stdlib HTTP runtime, not a
new web framework) that serves the trend dashboard and the JSONL log history
as JSON. Run this to view trends interactively; the weekday-5pm log entry
itself is written by tools/append_trends_log.py (headless, via Windows Task
Scheduler), not by this server.

Usage: python financial_trends_reporter/main.py [--retirement-system-dir PATH] [--port 5057]
"""
from __future__ import annotations

import argparse
import json
import logging
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.http_runtime.host_guard import assert_safe_to_bind  # noqa: E402
from src.http_runtime.server import LocalHTTPServer, _configured_token  # noqa: E402
from src.http_runtime.wsgi_facade import Flask, Response, request  # noqa: E402
from src.stores import SchemaVersionError  # noqa: E402

from financial_trends_reporter import account_registry, balance_series, flows  # noqa: E402
from financial_trends_reporter.app_sync import sync_from_app  # noqa: E402
from financial_trends_reporter.balance_store import DB_FILENAME, freshness  # noqa: E402
from financial_trends_reporter.passthrough_decisions import decisions_path_for_log, save_decision  # noqa: E402
from financial_trends_reporter.trends_job import run as run_trends_job  # noqa: E402
from financial_trends_reporter.trends_log import default_log_path, read_history  # noqa: E402

INDEX_HTML_PATH = _APP_ROOT / "frontend" / "index.html"


def create_app(retirement_system_dir: Path, log_path: Path | None = None, lifecycle: "Lifecycle | None" = None) -> Flask:
    app = Flask("financial_trends_reporter", static_folder=str(_APP_ROOT / "frontend"))
    resolved_log_path = log_path or default_log_path(_APP_ROOT)

    @app.before_request
    def _reject_cross_origin_requests():
        # Finding ARC-4 (system review 2026-09-07, Wave 6 item W6-3): this
        # server had zero auth/CORS/origin check of any kind on
        # GET /api/history (the full net-worth/spending log) and
        # POST /api/run-now. Mirrors the main app's own SEC-1 posture
        # (src/server/app_core.py: no CORS headers are ever added, since
        # nothing legitimate needs cross-origin access -- the frontend is
        # always served same-origin, from this same server) by explicitly
        # rejecting any request that carries a cross-origin Origin header,
        # rather than merely omitting a header a browser might not enforce
        # for a simple cross-origin POST. A request with no Origin header at
        # all (ordinary same-origin navigation/fetch in most browsers, and
        # every non-browser local script) is allowed through unchanged.
        if request.method == "OPTIONS":
            return None
        origin = str(request.headers.get("Origin", "") or "")
        if not origin:
            return None
        origin_netloc = origin.split("://", 1)[-1].rstrip("/")
        host = str(request.headers.get("Host", "") or "")
        if origin_netloc != host:
            return Response(
                json.dumps({"success": False, "error": "cross-origin requests are not allowed"}),
                status=403,
                content_type="application/json",
            )
        return None

    @app.route("/", methods=["GET"])
    def index():
        return Response(INDEX_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    @app.route("/charts.js", methods=["GET"])
    def charts_js():
        # Finding QUA-302 (Wave 6 item W6-11): index.html's inline
        # <script type="module"> imports this file -- it must actually be
        # served, and with a JS-capable Content-Type (module scripts are
        # rejected by browsers otherwise).
        return Response(
            (_APP_ROOT / "frontend" / "charts.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/shared/runtime_history.js", methods=["GET"])
    def runtime_history_js():
        # The planner's run-time helpers (formatElapsed, averageRuntimeText, ...), served from the
        # planner's own frontend/js so both apps run the same code.
        return Response(
            (_REPO_ROOT / "frontend" / "js" / "runtime_history.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/api/history", methods=["GET"])
    def history():
        return Response(json.dumps(read_history(resolved_log_path)), content_type="application/json")

    @app.route("/api/passthrough-decision", methods=["POST"])
    def passthrough_decision():
        # Approve/deny a near-match investment-to-investment pair. Takes effect
        # on the next snapshot (Run now), which re-reads the saved decisions.
        body = request.get_json(silent=True) or {}
        try:
            save_decision(decisions_path_for_log(resolved_log_path), str(body.get("key") or ""), str(body.get("decision") or ""))
        except ValueError as exc:
            return Response(json.dumps({"success": False, "error": str(exc)}), status=400, content_type="application/json")
        return Response(json.dumps({"success": True}), content_type="application/json")

    balances_db = resolved_log_path.with_name(DB_FILENAME)

    def _json(payload, status=200):
        return Response(json.dumps(payload), status=status, content_type="application/json")

    @app.route("/api/accounts", methods=["GET"])
    def accounts():
        # Monarch accounts with type, app-account mapping and per-chart toggles.
        return _json({
            "accounts": account_registry.list_accounts(balances_db),
            "types": list(account_registry.TYPES),
            "charts": list(account_registry.CHARTS),
            "freshness": freshness(balances_db),
        })

    @app.route("/api/balances", methods=["GET"])
    def balances():
        # Full per-account daily series (client re-sums on toggle) + merged Monarch/plan points.
        payload = balance_series.balances_payload(balances_db, read_history(resolved_log_path))
        payload["freshness"] = freshness(balances_db)
        return _json(payload)

    @app.route("/api/flows", methods=["GET"])
    def flows_endpoint():
        # Monthly investment flows from the latest log entry, toggled by the registry's Flows prefs.
        history = read_history(resolved_log_path)
        return _json(flows.flows_payload(history[-1] if history else None, account_registry.list_accounts(balances_db)))

    @app.route("/api/app-accounts", methods=["GET"])
    def app_accounts():
        return _json({"app_accounts": account_registry.list_app_accounts(retirement_system_dir)})

    @app.route("/api/account", methods=["POST"])
    def update_account():
        # Body-keyed (not a path segment): Monarch account names contain spaces, parentheses and '%'.
        body = request.get_json(silent=True) or {}
        try:
            updated = account_registry.set_account(
                balances_db, str(body.get("account_key") or ""),
                type=body.get("type"), app_account=body.get("app_account"),
            )
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        return _json({"success": True, "account": updated})

    @app.route("/api/account-prefs", methods=["POST"])
    def update_account_prefs():
        body = request.get_json(silent=True) or {}
        items = body.get("items")
        if not isinstance(items, list):
            return _json({"success": False, "error": "items must be a list"}, 400)
        try:
            count = account_registry.set_prefs(balances_db, items)
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        return _json({"success": True, "updated": count})

    @app.route("/api/run-now", methods=["POST"])
    def run_now():
        try:
            result = run_trends_job(retirement_system_dir, log_path=resolved_log_path)
        except SchemaVersionError as exc:
            # This process loaded its code before the app database was upgraded.
            logging.getLogger(__name__).exception("run-now: reporter code is older than the app database")
            return _json({"success": False, "error": f"This reporter is running older code than the app database ({exc}). Close it and start it again."}, 500)
        except Exception as exc:  # noqa: BLE001 - surface the cause instead of a bare HTTP 500
            logging.getLogger(__name__).exception("run-now failed")
            return _json({"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500)
        return Response(json.dumps(result), status=200 if result.get("success") else 400, content_type="application/json")

    @app.route("/api/ping", methods=["POST"])
    def ping():
        if lifecycle is not None:
            lifecycle.ping()
        return _json({"success": True})

    @app.route("/api/closing", methods=["POST"])
    def closing():
        if lifecycle is not None:
            lifecycle.closing()
        return _json({"success": True})

    @app.route("/api/exit", methods=["POST"])
    def exit_app():
        if lifecycle is not None:
            lifecycle.stop_soon()
        return _json({"success": True})

    return app


# The page pings every 5s. A hidden tab can be throttled to about one timer a minute, so the
# idle timeout is generous; a closed page also sends a beacon that shortens it to a short
# grace period (a reload's first ping cancels that).
IDLE_TIMEOUT_SECONDS = 150.0
CLOSE_GRACE_SECONDS = 10.0


class Lifecycle:
    """Stops the server when the browser page goes away. Armed by the first ping, so a server
    used only through the API (no page ever opened) is never stopped by it."""

    def __init__(self, stop, clock=time.monotonic) -> None:
        self._stop = stop
        self._clock = clock
        self._deadline: float | None = None
        self._lock = threading.Lock()

    def ping(self) -> None:
        with self._lock:
            self._deadline = self._clock() + IDLE_TIMEOUT_SECONDS

    def closing(self) -> None:
        with self._lock:
            if self._deadline is not None:
                self._deadline = min(self._deadline, self._clock() + CLOSE_GRACE_SECONDS)

    def expired(self) -> bool:
        with self._lock:
            return self._deadline is not None and self._clock() >= self._deadline

    def stop_soon(self) -> None:
        # shutdown() blocks until serve_forever exits, so it must not run on the request thread.
        threading.Thread(target=self._stop, daemon=True).start()

    def watch(self, interval: float = 1.0) -> None:
        def loop() -> None:
            while True:
                time.sleep(interval)
                if self.expired():
                    self._stop()
                    return
        threading.Thread(target=loop, daemon=True).start()


def _port_in_use(host: str, port: int) -> bool:
    # LocalHTTPServer sets SO_REUSEADDR, which on Windows lets a second server bind a
    # port that is already serving, so probe before binding rather than trust bind().
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retirement-system-dir", default=str(_REPO_ROOT), help="retirement_system workspace root; defaults to this repo's own root")
    # 5060 (SIP) is deliberately avoided: it's on Chrome/Chromium's built-in
    # restricted-ports list, so a browser tab opened against it fails with
    # ERR_UNSAFE_PORT even though the server itself is listening fine.
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open a browser tab")
    args = parser.parse_args(argv)

    if _port_in_use(args.host, args.port):
        print(f"Financial trends reporter is already running on port {args.port}. "
              "Close it first if it needs to pick up new code.", file=sys.stderr)
        return 1
    # Re-read account types/mapping from the app so a fix to the sync applies without waiting for the next import.
    sync_from_app(default_log_path(_APP_ROOT).with_name(DB_FILENAME), args.retirement_system_dir)
    assert_safe_to_bind(args.host, _configured_token())
    # Build the server here (not run_local_server) so Exit and the closed-page watchdog can stop it.
    holder: dict[str, LocalHTTPServer] = {}
    lifecycle = Lifecycle(lambda: holder["server"].shutdown())
    app = create_app(Path(args.retirement_system_dir), lifecycle=lifecycle)
    server = holder["server"] = LocalHTTPServer((args.host, int(args.port)), app)
    url = f"http://{args.host}:{args.port}"
    print(f"Financial trends reporter listening on {url}")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    lifecycle.watch()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("Financial trends reporter stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
