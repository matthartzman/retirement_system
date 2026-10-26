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
    assert "<title>" in body or "Financial trends" in body


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


def test_second_instance_refuses_to_start_when_the_port_is_taken(capsys):
    import socket

    from financial_trends_reporter import main as reporter_main

    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        assert reporter_main.main(["--port", str(port), "--no-open"]) == 1
    assert "already running" in capsys.readouterr().err


def test_exit_endpoint_stops_the_server(tmp_path):
    from financial_trends_reporter.main import Lifecycle

    stopped = threading.Event()
    app = create_app(_workspace(tmp_path), log_path=tmp_path / "log.jsonl", lifecycle=Lifecycle(stopped.set))
    assert app.test_client().post("/api/exit").status_code == 200
    assert stopped.wait(2)


def test_closed_page_stops_the_server_after_the_grace_period_but_a_reload_does_not():
    from financial_trends_reporter.main import CLOSE_GRACE_SECONDS, Lifecycle

    now = [0.0]
    life = Lifecycle(lambda: None, clock=lambda: now[0])
    assert not life.expired()  # never armed: an API-only server is not stopped
    life.ping()
    life.closing()
    now[0] = CLOSE_GRACE_SECONDS - 1
    life.ping()  # the reloaded page pings again
    now[0] = CLOSE_GRACE_SECONDS + 5
    assert not life.expired()
    life.closing()
    now[0] += CLOSE_GRACE_SECONDS + 1
    assert life.expired()


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
