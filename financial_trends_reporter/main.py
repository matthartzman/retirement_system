#!/usr/bin/env python3
"""Financial trends reporter -- standalone entry point (ticket 306).

A small local server (reusing retirement_system's stdlib HTTP runtime, not a
new web framework) that serves the trend dashboard and the JSONL log history
as JSON. Run this to view trends interactively; the weekday-5pm log entry
itself is written by tools/append_trends_log.py (headless, via Windows Task
Scheduler), not by this server.

Usage: python financial_trends_reporter/main.py [--retirement-system-dir PATH] [--port 5057] [--host 127.0.0.1]
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
from datetime import date, timedelta
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.http_runtime.host_guard import assert_safe_to_bind  # noqa: E402
from src.http_runtime.server import LocalHTTPServer, _configured_token  # noqa: E402
from src.http_runtime.wsgi_facade import Flask, Response, request  # noqa: E402
from src.stores import SchemaVersionError  # noqa: E402

from financial_trends_reporter import account_registry, balance_series, flows, live_snapshot, percent_view, realized_view, spending_window  # noqa: E402
from financial_trends_reporter.access_routes import register_access  # noqa: E402
from financial_trends_reporter.access_store import DB_FILENAME as ACCESS_DB_FILENAME, AccessStore  # noqa: E402
from financial_trends_reporter.listeners import ListenerApp, check_funnel_target  # noqa: E402
from financial_trends_reporter.sessions import SessionTable  # noqa: E402
from financial_trends_reporter.app_sync import sync_from_app  # noqa: E402
from financial_trends_reporter.balance_store import DB_FILENAME, freshness  # noqa: E402
from financial_trends_reporter.passthrough_decisions import decisions_path_for_log, save_decision  # noqa: E402
from financial_trends_reporter.trends_job import run as run_trends_job  # noqa: E402
from financial_trends_reporter.trends_log import default_log_path, read_history  # noqa: E402
from src.active_plan import plan_path_for_workspace  # noqa: E402
from src import spending_tracker  # noqa: E402

INDEX_HTML_PATH = _APP_ROOT / "frontend" / "index.html"
# A run newer than this is fresh enough that the page skips its automatic update on open.
FRESH_RUN_SECONDS = 900
# /api/spending keeps at most this many windows in memory.
SPENDING_CACHE_MAX = 64


def _today() -> date:
    return date.today()


def _parse_spending_window(args) -> tuple[date, date]:
    """``(from, to)`` from /api/spending's query, or ValueError with a message for the page."""
    raw_from, raw_to = str(args.get("from") or ""), str(args.get("to") or "")
    try:
        start, end = date.fromisoformat(raw_from), date.fromisoformat(raw_to)
    except ValueError:
        raise ValueError("from and to must be dates in YYYY-MM-DD form") from None
    if start > end:
        raise ValueError("from must be on or before to")
    if end > _today() + timedelta(days=1):
        raise ValueError("to cannot be later than tomorrow")
    if (end - start).days + 1 > round(365.25 * spending_window.MAX_SPAN_YEARS):
        raise ValueError(f"the window cannot be longer than {spending_window.MAX_SPAN_YEARS} years")
    return start, end


def create_app(retirement_system_dir: Path, log_path: Path | None = None, access_store: AccessStore | None = None,
               sessions: SessionTable | None = None, clock=time.time, percent_basis=None) -> Flask:
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

    @app.route("/live_snapshot.js", methods=["GET"])
    def live_snapshot_js():
        # The Live Snapshot view's module (toggle, render, 60 s poll), loaded by index.html.
        return Response(
            (_APP_ROOT / "frontend" / "live_snapshot.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/live_groups.js", methods=["GET"])
    def live_groups_js():
        # Group By for the Live Snapshot table (grouping, ordering, totals), imported by live_snapshot.js.
        return Response(
            (_APP_ROOT / "frontend" / "live_groups.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/realized.js", methods=["GET"])
    def realized_js():
        # The Realized gains and losses view (ledger sales in the Time scope), loaded by index.html.
        return Response(
            (_APP_ROOT / "frontend" / "realized.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/spending_dock.js", methods=["GET"])
    def spending_dock_js():
        # The Spending card's breakdown panels (hover, pin, transactions), imported by index.html.
        return Response(
            (_APP_ROOT / "frontend" / "spending_dock.js").read_text(encoding="utf-8"),
            content_type="text/javascript; charset=utf-8",
        )

    @app.route("/money_view.js", methods=["GET"])
    def money_view_js():
        # The one money formatter ($ or % of net worth) imported by charts.js, live_snapshot.js and index.html.
        return Response(
            (_APP_ROOT / "frontend" / "money_view.js").read_text(encoding="utf-8"),
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
        # on the next snapshot (the update the page starts after a decision), which re-reads them.
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

    # /api/spending: the Spending card for any window. Results are cached per (from, to) and the
    # plan file's mtime (transactions, taxonomy, aliases and budget all live in it); a run-now
    # clears the cache.
    spending_cache: dict = {}
    spending_cache_lock = threading.Lock()

    def _spending_inputs_mtime():
        try:
            return plan_path_for_workspace(retirement_system_dir).stat().st_mtime_ns
        except OSError:
            return None

    @app.route("/api/spending", methods=["GET"])
    def spending():
        try:
            start, end = _parse_spending_window(request.args)
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        key = (start.isoformat(), end.isoformat(), _spending_inputs_mtime())
        with spending_cache_lock:
            cached = spending_cache.get(key)
        if cached is None:
            try:
                cached = json.dumps(spending_window.spending_window_payload(retirement_system_dir, start, end))
            except Exception as exc:  # noqa: BLE001 - the page falls back to the logged YTD figures
                logging.getLogger(__name__).exception("spending window failed")
                return _json({"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500)
            with spending_cache_lock:
                if len(spending_cache) >= SPENDING_CACHE_MAX:
                    spending_cache.clear()
                spending_cache[key] = cached
        return Response(cached, content_type="application/json")

    @app.route("/api/spending/transactions", methods=["GET"])
    def spending_transactions():
        # The transactions behind one merchant line of /api/spending's hierarchy. A line that no
        # longer exists (data changed underneath) yields an empty list, not an error.
        try:
            start, end = _parse_spending_window(request.args)
        except ValueError as exc:
            return _json({"success": False, "error": str(exc)}, 400)
        tracking_type, group, category, merchant = (
            request.args.get(name) or "" for name in ("type", "group", "category", "merchant"))
        if not all(v.strip() for v in (tracking_type, group, category, merchant)):
            return _json({"success": False, "error": "type, group, category and merchant are required"}, 400)
        key = ("txns", start.isoformat(), end.isoformat(), tracking_type, group, category, merchant,
               _spending_inputs_mtime())
        with spending_cache_lock:
            cached = spending_cache.get(key)
        if cached is None:
            try:
                cached = json.dumps(spending_tracker.spending_transactions_window(
                    retirement_system_dir, start, end, tracking_type, group, category, merchant))
            except Exception as exc:  # noqa: BLE001 - the panel shows the cause
                logging.getLogger(__name__).exception("spending transactions failed")
                return _json({"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500)
            with spending_cache_lock:
                if len(spending_cache) >= SPENDING_CACHE_MAX:
                    spending_cache.clear()
                spending_cache[key] = cached
        return Response(cached, content_type="application/json")

    @app.route("/api/live-snapshot", methods=["GET"])
    def live_snapshot_endpoint():
        # Live Snapshot view: holdings at live (delayed) prices plus the balance-sheet roll-up.
        # Quotes are shared for 30 s across requests; ?refresh=1 (Refresh now) refetches, at most
        # once per 10 s. Inputs other than prices are cached 10 min and cleared by run-now.
        # ?from=YYYY-MM-DD is the Time scope's first day (returns are measured from the close before it).
        force = str(request.args.get("refresh") or "") in {"1", "true"}
        try:
            inputs = live_snapshot.load_inputs(retirement_system_dir, resolved_log_path, balances_db)
            return _json(live_snapshot.build(inputs=inputs, data_dir=resolved_log_path.parent, force=force,
                                             start_from=request.args.get("from")))
        except Exception as exc:  # noqa: BLE001 - the page shows the cause and keeps its last good values
            logging.getLogger(__name__).exception("live snapshot failed")
            return _json({"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500)

    @app.route("/api/realized", methods=["GET"])
    def realized_endpoint():
        # Realized gains and losses from the sales ledger. ?from= is the Time scope's first day; ?tax_year=YYYY
        # replaces it; ?group=symbol|account, ?taxable=1, ?wash=1, ?unconfirmed=1 (display-only estimate).
        args = request.args
        flag = lambda name: str(args.get(name) or "") in {"1", "true"}
        try:
            year = int(args["tax_year"]) if str(args.get("tax_year") or "").strip() else None
            return _json(realized_view.build(**realized_view.load(retirement_system_dir), today=_today(), start=args.get("from"),
                                             tax_year=year, group=str(args.get("group") or "symbol"), taxable_only=flag("taxable"),
                                             wash_only=flag("wash"), include_unconfirmed=flag("unconfirmed")))
        except ValueError:
            return _json({"success": False, "error": "tax_year must be a year"}, 400)
        except Exception as exc:  # noqa: BLE001 - the page shows the cause
            logging.getLogger(__name__).exception("realized view failed")
            return _json({"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500)

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

    # Run lock: at most one job run at a time. A caller that arrives while a run is in flight
    # waits for it and shares its (payload, status) instead of starting a second run.
    run_lock = threading.Lock()
    current_run: dict = {}
    cancel_requested = threading.Event()

    def _execute_run():
        try:
            cancel_requested.clear()
            result = run_trends_job(retirement_system_dir, log_path=resolved_log_path, cancel=cancel_requested.is_set)
        except SchemaVersionError as exc:
            # This process loaded its code before the app database was upgraded.
            logging.getLogger(__name__).exception("run-now: reporter code is older than the app database")
            return {"success": False, "error": f"This reporter is running older code than the app database ({exc}). Close it and start it again."}, 500
        except Exception as exc:  # noqa: BLE001 - surface the cause instead of a bare HTTP 500
            logging.getLogger(__name__).exception("run-now failed")
            return {"success": False, "error": f"{exc.__class__.__name__}: {exc}"}, 500
        if result.get("cancelled"):
            return result, 409
        return result, 200 if result.get("success") else 400

    @app.route("/api/run-status", methods=["GET"])
    def run_status():
        history_rows = read_history(resolved_log_path)
        last = history_rows[-1].get("run_at") if history_rows else None
        return _json({"running": bool(current_run), "last_run_at": last or None, "fresh_seconds": FRESH_RUN_SECONDS})

    @app.route("/api/run-cancel", methods=["POST"])
    def run_cancel():
        # Cooperative: the job stops at its next step (the price refresh is killed outright).
        with run_lock:
            running = bool(current_run)
        if running:
            cancel_requested.set()
        return _json({"success": True, "cancelling": running})

    @app.route("/api/run-now", methods=["POST"])
    def run_now():
        with run_lock:
            holder = current_run.get("holder")
            is_runner = holder is None
            if is_runner:
                holder = current_run["holder"] = {"done": threading.Event(), "response": None}
        if is_runner:
            try:
                holder["response"] = _execute_run()
            finally:
                with run_lock:
                    current_run.clear()
                holder["done"].set()
        else:
            holder["done"].wait()
        payload, status = holder["response"] or ({"success": False, "error": "update did not finish"}, 500)
        if status == 200:
            with spending_cache_lock:
                spending_cache.clear()
            live_snapshot.clear_inputs_cache()
        return Response(json.dumps(payload), status=status, content_type="application/json")

    @app.route("/api/exit", methods=["POST"])
    def exit_app():
        # Exit never stops the server; remote guests end their session through /api/signout.
        return _json({"success": True})

    register_access(
        app,
        access_store or AccessStore(resolved_log_path.with_name(ACCESS_DB_FILENAME)),
        sessions or SessionTable(),
        clock=clock,
        percent_basis=percent_basis or (lambda: percent_view.scale_basis(balances_db, read_history(resolved_log_path))),
    )
    return app


def _local_host(host: str) -> str:
    # A wildcard bind (0.0.0.0 / ::) can't be connected to or browsed on Windows; use loopback locally.
    return "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host


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
    parser.add_argument("--remote-port", type=int, default=5058, help="Loopback port Tailscale Funnel points at (sign-in required)")
    parser.add_argument("--no-remote", action="store_true", help="Don't start the remote (sign-in) listener")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open a browser tab")
    args = parser.parse_args(argv)

    if _port_in_use(_local_host(args.host), args.port):
        url = f"http://{_local_host(args.host)}:{args.port}"
        print(f"Financial trends reporter is already running; opening {url}.")
        if not args.no_open:
            webbrowser.open(url)
        return 0
    # Re-read account types/mapping from the app so a fix to the sync applies without waiting for the next import.
    sync_from_app(default_log_path(_APP_ROOT).with_name(DB_FILENAME), args.retirement_system_dir)
    assert_safe_to_bind(args.host, _configured_token())
    if (problem := check_funnel_target(args.port)):
        print(problem, file=sys.stderr)
        return 1
    app = create_app(Path(args.retirement_system_dir))
    server = LocalHTTPServer((args.host, int(args.port)), ListenerApp(app, "local"))
    if not args.no_remote:
        if _port_in_use("127.0.0.1", args.remote_port):
            print(f"Remote port {args.remote_port} is busy; the remote listener was not started.", file=sys.stderr)
        else:
            assert_safe_to_bind("127.0.0.1", _configured_token())
            remote = LocalHTTPServer(("127.0.0.1", int(args.remote_port)), ListenerApp(app, "remote"))
            threading.Thread(target=remote.serve_forever, daemon=True).start()
            print(f"Remote listener (sign-in required) on 127.0.0.1:{args.remote_port}")
    url = f"http://{_local_host(args.host)}:{args.port}"
    print(f"Financial trends reporter listening on {url}")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
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
