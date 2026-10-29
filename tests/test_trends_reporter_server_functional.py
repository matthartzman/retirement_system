"""Ticket 306: financial_trends_reporter/main.py's local server -- serves the
dashboard, the JSONL history as JSON, and a manual "run now" trigger, all
using retirement_system's existing stdlib HTTP runtime (no new web
framework)."""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path

from financial_trends_reporter.main import create_app
from financial_trends_reporter.trends_log import append_or_replace_entry
from src import ytd_tracking as ytd


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


def test_index_serves_the_dashboard_html(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "<title>" in body or "Financial Insight" in body


def test_charts_js_is_served_with_a_js_capable_content_type(tmp_path):
    # Finding QUA-302 (Wave 6 item W6-11): index.html's <script type="module">
    # imports ./charts.js -- it must actually be served by this app, and
    # with a Content-Type a browser will execute as a module script.
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get("/charts.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("Content-Type", "").lower()
    assert "export function barChartSvg" in resp.get_data(as_text=True)


def test_shared_runtime_history_js_is_served_with_a_js_capable_content_type(tmp_path):
    # The planner's run-time helpers are served to the trends page from the planner's own file.
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    resp = client.get("/shared/runtime_history.js")
    assert resp.status_code == 200
    assert "javascript" in resp.headers.get("Content-Type", "").lower()
    assert "averageRuntimeText" in resp.get_data(as_text=True)


def test_history_endpoint_returns_the_jsonl_log(tmp_path):
    log_path = tmp_path / "log.jsonl"
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01", "net_worth": {"total": 100}})
    app = create_app(_workspace(tmp_path), log_path=log_path)
    client = app.test_client()
    resp = client.get("/api/history")
    body = json.loads(resp.get_data(as_text=True))
    assert len(body) == 1
    assert body[0]["as_of_date"] == "2026-01-01"


def test_run_now_appends_a_fresh_snapshot(tmp_path):
    base_dir = _workspace(tmp_path)
    ytd.write_transactions(base_dir / "input", [
        {"Date": "2026-01-10", "Merchant": "Kroger", "Category": "Groceries", "Account": "Checking", "Amount": "-50.00"},
    ], today=date(2026, 1, 20))
    log_path = tmp_path / "log.jsonl"
    app = create_app(base_dir, log_path=log_path)
    client = app.test_client()
    resp = client.post("/api/run-now", json={})
    assert resp.status_code == 200
    resp2 = client.get("/api/history")
    body = json.loads(resp2.get_data(as_text=True))
    assert len(body) == 1
    assert body[0]["ytd_expenses_by_category"]["Groceries"] == 50.0


def test_run_now_tells_the_user_to_restart_when_the_app_database_is_newer(tmp_path, monkeypatch):
    from financial_trends_reporter import main as reporter_main
    from src.stores import SchemaVersionError

    def _stale(*_a, **_k):
        raise SchemaVersionError("app schema v3 is newer than supported v2")

    monkeypatch.setattr(reporter_main, "run_trends_job", _stale)
    app = reporter_main.create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    resp = app.test_client().post("/api/run-now")
    assert resp.status_code == 500
    assert "older code" in resp.get_json()["error"]


def test_second_instance_opens_the_browser_and_exits_cleanly(monkeypatch):
    import socket

    from financial_trends_reporter import main as reporter_main

    opened = []
    monkeypatch.setattr(reporter_main.webbrowser, "open", opened.append)
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert reporter_main.main(["--port", str(port)]) == 0
    assert opened == [f"http://127.0.0.1:{port}"]


def test_exit_endpoint_does_not_stop_the_server(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    client = app.test_client()
    assert client.post("/api/exit").status_code == 200
    assert client.get("/api/history").status_code == 200


def test_closing_endpoint_is_gone(tmp_path):
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    assert app.test_client().post("/api/closing").status_code == 404


def test_run_status_reports_last_run_at_from_the_log(tmp_path):
    from financial_trends_reporter import main as reporter_main

    log_path = tmp_path / "log.jsonl"
    app = create_app(_workspace(tmp_path), log_path=log_path)
    empty = app.test_client().get("/api/run-status").get_json()
    assert empty == {"running": False, "last_run_at": None, "fresh_seconds": reporter_main.FRESH_RUN_SECONDS}
    assert reporter_main.FRESH_RUN_SECONDS == 900
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-01", "run_at": "2026-01-01T22:00:00Z"})
    append_or_replace_entry(log_path, {"as_of_date": "2026-01-02", "run_at": "2026-01-02T22:00:00Z"})
    status = app.test_client().get("/api/run-status").get_json()
    assert status["last_run_at"] == "2026-01-02T22:00:00Z"
    assert status["running"] is False


def test_concurrent_run_now_calls_share_one_job_run(tmp_path, monkeypatch):
    from financial_trends_reporter import main as reporter_main

    calls = []
    entered = threading.Event()
    release = threading.Event()

    def _slow_job(*_a, **_k):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return {"success": True, "marker": len(calls)}

    monkeypatch.setattr(reporter_main, "run_trends_job", _slow_job)
    app = reporter_main.create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    results = []

    def _call():
        resp = app.test_client().post("/api/run-now")
        results.append((resp.status_code, resp.get_json()))

    first = threading.Thread(target=_call)
    first.start()
    assert entered.wait(5)
    assert app.test_client().get("/api/run-status").get_json()["running"] is True
    second = threading.Thread(target=_call)
    second.start()
    time.sleep(0.2)  # the second caller must be waiting, not running the job
    release.set()
    first.join(5)
    second.join(5)
    assert calls == [1]
    assert results == [(200, {"success": True, "marker": 1})] * 2
    assert app.test_client().get("/api/run-status").get_json()["running"] is False


def test_a_failed_run_is_shared_with_the_waiting_caller_and_clears_the_lock(tmp_path, monkeypatch):
    from financial_trends_reporter import main as reporter_main

    attempts = []

    def _job(*_a, **_k):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("boom")
        return {"success": True}

    monkeypatch.setattr(reporter_main, "run_trends_job", _job)
    app = reporter_main.create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    bad = app.test_client().post("/api/run-now")
    assert bad.status_code == 500
    assert "RuntimeError: boom" in bad.get_json()["error"]
    assert app.test_client().post("/api/run-now").status_code == 200  # a later call runs again



# --- Trends Phase 5: /api/spending (Spending by window) -------------------------------------

def _spending_workspace(tmp_path: Path) -> Path:
    from tests.test_spending_window_unit import ROWS, _txn, _workspace as _seeded
    return _seeded(tmp_path, ROWS + [_txn("2025-01-04", "Kroger", "Groceries", -55), _txn("2025-01-25", "Kroger", "Groceries", -45)])


def _get_json(client, url):
    resp = client.get(url)
    return resp.status_code, json.loads(resp.get_data(as_text=True))


def test_spending_endpoint_shape(tmp_path):
    app = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    status, body = _get_json(app.test_client(), "/api/spending?from=2026-01-01&to=2026-01-10")
    assert status == 200
    assert set(body) == {"window", "hierarchy", "prior", "budget", "full_year_budget"}
    assert body["window"] == {"from": "2026-01-01", "to": "2026-01-10", "days": 10}
    assert body["hierarchy"]["Core Expenses"]["Food"]["Groceries"] == {"Kroger": 70.0, "Aldi": 20.0}
    assert set(body["prior"]) == {"window", "by_type", "detail"}
    assert body["prior"]["by_type"] == {"Core Expenses": 55.0}
    assert set(body["budget"]) == {"by_type", "by_category"}
    assert body["budget"]["by_type"] == {"Core Expenses": 100.0}
    assert body["full_year_budget"]["year"] == 2026
    assert body["full_year_budget"]["by_type"] == {"Core Expenses": 3650.0}


def test_spending_full_year_budget_is_the_end_years(tmp_path):
    app = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    status, body = _get_json(app.test_client(), "/api/spending?from=2025-12-01&to=2026-01-31")
    assert status == 200 and body["full_year_budget"]["year"] == 2026
    assert body["prior"] is None  # Dec 2024 is before the first transaction year (2025)


def test_spending_rejects_bad_windows_with_400(tmp_path):
    import financial_trends_reporter.main as reporter_main
    client = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    tomorrow = reporter_main._today().toordinal() + 1
    too_late = date.fromordinal(tomorrow + 1).isoformat()
    for query in ("", "?from=2026-01-01", "?from=2026-13-01&to=2026-12-31", "?from=jan&to=feb",
                  "?from=2026-02-01&to=2026-01-01", f"?from=2026-01-01&to={too_late}",
                  "?from=2000-01-01&to=2020-01-02"):
        status, body = _get_json(client, "/api/spending" + query)
        assert status == 400, query
        assert body["success"] is False and body["error"], query
    status, _ = _get_json(client, f"/api/spending?from=2026-01-01&to={date.fromordinal(tomorrow).isoformat()}")
    assert status == 200  # today + 1 day is allowed
    status, _ = _get_json(client, "/api/spending?from=2000-01-02&to=2020-01-01")
    assert status == 200  # just under 20 years


def test_spending_is_cached_and_run_now_clears_the_cache(tmp_path, monkeypatch):
    import financial_trends_reporter.main as reporter_main
    calls = []
    real = reporter_main.spending_window.spending_window_payload

    def counting(*args, **kwargs):
        calls.append(args[1:])
        return real(*args, **kwargs)

    monkeypatch.setattr(reporter_main.spending_window, "spending_window_payload", counting)
    monkeypatch.setattr(reporter_main, "run_trends_job", lambda *_a, **_k: {"success": True})
    client = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    url = "/api/spending?from=2026-01-01&to=2026-01-10"
    first = _get_json(client, url)
    assert _get_json(client, url) == first
    assert len(calls) == 1  # second request is a cache hit
    _get_json(client, "/api/spending?from=2026-01-01&to=2026-01-11")
    assert len(calls) == 2  # a different window is computed
    assert client.post("/api/run-now", json={}).status_code == 200
    assert _get_json(client, url) == first
    assert len(calls) == 3  # the run cleared the cache


def test_spending_cache_follows_the_plan_file_mtime(tmp_path, monkeypatch):
    import os
    import financial_trends_reporter.main as reporter_main
    base = _spending_workspace(tmp_path)
    calls = []
    real = reporter_main.spending_window.spending_window_payload
    monkeypatch.setattr(reporter_main.spending_window, "spending_window_payload",
                        lambda *a, **k: calls.append(1) or real(*a, **k))
    client = create_app(base, log_path=tmp_path / "log.jsonl").test_client()
    url = "/api/spending?from=2026-01-01&to=2026-01-10"
    _get_json(client, url)
    plan = reporter_main.plan_path_for_workspace(base)
    st = plan.stat()
    os.utime(plan, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    _get_json(client, url)
    assert len(calls) == 2


def test_spending_at_ytd_equals_the_snapshot(tmp_path):
    # The key regression guard: GET Jan 1 -> today matches what the logged snapshot carries
    # for the same day (hierarchy, prior-year totals and prior-year detail, budgets).
    from financial_trends_reporter.trends_metrics import compute_snapshot
    base = _spending_workspace(tmp_path)
    today = date(2026, 3, 1)  # the fixture's last transaction: the snapshot's tree has no end date
    snap = compute_snapshot(base, today=today)
    client = create_app(base, log_path=tmp_path / "log.jsonl").test_client()
    status, body = _get_json(client, f"/api/spending?from=2026-01-01&to={today.isoformat()}")
    assert status == 200
    assert body["hierarchy"] == snap["ytd_expense_hierarchy"]
    assert body["prior"]["by_type"] == snap["ytd_expense_prior_year"]
    assert body["prior"]["detail"] == snap["ytd_expense_prior_detail"]
    assert body["prior"]["by_type"] == {"Core Expenses": 100.0}  # Jan 4 + Jan 25, 2025
    assert body["full_year_budget"]["by_type"] == snap["annual_budget_by_tracking_type"]
    assert body["full_year_budget"]["by_category"] == snap["annual_budget_by_category"]


def test_run_cancel_stops_a_running_job_and_run_now_reports_cancelled(tmp_path, monkeypatch):
    from financial_trends_reporter import main as reporter_main

    entered = threading.Event()

    def _job(*_a, cancel=None, **_k):
        entered.set()
        assert cancel is not None
        deadline = time.time() + 5
        while not cancel() and time.time() < deadline:
            time.sleep(0.02)
        return {"success": False, "cancelled": True, "error": "Cancelled."}

    monkeypatch.setattr(reporter_main, "run_trends_job", _job)
    app = reporter_main.create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    assert app.test_client().post("/api/run-cancel").get_json()["cancelling"] is False  # nothing running
    out = []
    t = threading.Thread(target=lambda: out.append(app.test_client().post("/api/run-now").status_code))
    t.start()
    assert entered.wait(5)
    assert app.test_client().post("/api/run-cancel").get_json()["cancelling"] is True
    t.join(5)
    assert out == [409]
    assert app.test_client().get("/api/run-status").get_json()["running"] is False


# --- /api/spending/transactions (merchant-line drill-down) ----------------------------------

_TXN_URL = ("/api/spending/transactions?from=2026-01-01&to=2026-01-10"
            "&type=Core%20Expenses&group=Food&category=Groceries&merchant={merchant}")


def test_spending_transactions_endpoint_returns_the_merchant_lines_transactions(tmp_path):
    app = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl")
    status, body = _get_json(app.test_client(), _TXN_URL.format(merchant="Kroger"))
    assert status == 200
    assert set(body) == {"transactions", "total"}
    assert body["transactions"] and body["total"] == 70.0
    assert {t["merchant"] for t in body["transactions"]} == {"Kroger"}


def test_spending_transactions_requires_all_four_params_and_a_valid_window(tmp_path):
    client = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    base = {"from": "2026-01-01", "to": "2026-01-10", "type": "Core Expenses", "group": "Food",
            "category": "Groceries", "merchant": "Kroger"}
    from urllib.parse import urlencode
    for missing in ("type", "group", "category", "merchant"):
        for blank in (False, True):
            args = {k: v for k, v in base.items() if k != missing or blank}
            if blank:
                args[missing] = "  "
            status, body = _get_json(client, "/api/spending/transactions?" + urlencode(args))
            assert status == 400, (missing, blank)
            assert body == {"success": False, "error": "type, group, category and merchant are required"}
    status, body = _get_json(client, "/api/spending/transactions?from=jan&to=feb&type=a&group=b&category=c&merchant=d")
    assert status == 400 and body["success"] is False


def test_spending_transactions_for_an_unknown_merchant_is_an_empty_list(tmp_path):
    client = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    status, body = _get_json(client, _TXN_URL.format(merchant="Nowhere"))
    assert status == 200 and body["transactions"] == [] and body["total"] == 0.0


def test_spending_transactions_cache_key_covers_every_param_and_the_plan_mtime(tmp_path, monkeypatch):
    import os
    import financial_trends_reporter.main as reporter_main
    base = _spending_workspace(tmp_path)
    calls = []
    real = reporter_main.spending_tracker.spending_transactions_window
    monkeypatch.setattr(reporter_main.spending_tracker, "spending_transactions_window",
                        lambda *a, **k: calls.append(a[1:]) or real(*a, **k))
    client = create_app(base, log_path=tmp_path / "log.jsonl").test_client()
    _get_json(client, _TXN_URL.format(merchant="Kroger"))
    _get_json(client, _TXN_URL.format(merchant="Kroger"))
    assert len(calls) == 1  # cache hit
    _get_json(client, _TXN_URL.format(merchant="Aldi"))
    assert len(calls) == 2  # merchant is part of the key
    _get_json(client, _TXN_URL.format(merchant="Kroger").replace("category=Groceries", "category=Other"))
    assert len(calls) == 3  # category is part of the key
    plan = reporter_main.plan_path_for_workspace(base)
    st = plan.stat()
    os.utime(plan, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    _get_json(client, _TXN_URL.format(merchant="Kroger"))
    assert len(calls) == 4  # plan mtime is part of the key


def test_spending_transactions_failure_is_a_500_with_the_error_shape(tmp_path, monkeypatch):
    import financial_trends_reporter.main as reporter_main

    def boom(*_a, **_k):
        raise RuntimeError("nope")

    monkeypatch.setattr(reporter_main.spending_tracker, "spending_transactions_window", boom)
    client = create_app(_spending_workspace(tmp_path), log_path=tmp_path / "log.jsonl").test_client()
    status, body = _get_json(client, _TXN_URL.format(merchant="Kroger"))
    assert status == 500 and body == {"success": False, "error": "RuntimeError: nope"}
