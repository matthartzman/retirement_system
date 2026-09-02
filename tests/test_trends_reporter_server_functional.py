"""Ticket 306: financial_trends_reporter/main.py's local server -- serves the
dashboard, the JSONL history as JSON, and a manual "run now" trigger, all
using retirement_system's existing stdlib HTTP runtime (no new web
framework)."""
from __future__ import annotations

import json
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
