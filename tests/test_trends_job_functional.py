"""Ticket 306: end-to-end weekday trends job (financial_trends_reporter.trends_job,
run headlessly by financial_trends_reporter/tools/append_trends_log.py)
against a temp retirement_system workspace."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from financial_trends_reporter import trends_job
from financial_trends_reporter.trends_log import read_history
from src import ytd_tracking as ytd


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    ytd.write_transactions(base_dir / "input", [
        {"Date": "2026-01-10", "Merchant": "Kroger", "Category": "Groceries", "Account": "Checking", "Amount": "-100.00"},
    ], today=date(2026, 1, 20))
    return base_dir


def test_run_appends_a_snapshot_to_the_log(tmp_path):
    base_dir = _workspace(tmp_path)
    log_path = tmp_path / "log.jsonl"
    result = trends_job.run(base_dir, log_path=log_path, today=date(2026, 1, 20))
    assert result["success"] is True
    history = read_history(log_path)
    assert len(history) == 1
    assert history[0]["ytd_expenses_by_category"]["Groceries"] == 100.0
    assert history[0]["run_at"]


def test_running_twice_the_same_day_overwrites_not_duplicates(tmp_path):
    base_dir = _workspace(tmp_path)
    log_path = tmp_path / "log.jsonl"
    trends_job.run(base_dir, log_path=log_path, today=date(2026, 1, 20))
    trends_job.run(base_dir, log_path=log_path, today=date(2026, 1, 20))
    assert len(read_history(log_path)) == 1


def test_missing_workspace_input_dir_is_a_clean_no_crash(tmp_path):
    base_dir = tmp_path / "empty_workspace"
    base_dir.mkdir()
    log_path = tmp_path / "log.jsonl"
    result = trends_job.run(base_dir, log_path=log_path, today=date(2026, 1, 20))
    assert result["success"] is True


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout, self.returncode = stdout, returncode


def _fake_tool(base_dir):
    (base_dir / "tools").mkdir(exist_ok=True)
    (base_dir / "tools" / "refresh_prices.py").write_text("# stub\n")


def test_run_refreshes_prices_first_and_logs_fresh_status(tmp_path, monkeypatch):
    base_dir = _workspace(tmp_path)
    _fake_tool(base_dir)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _Proc('noise\n{"live_prices_resolved": 7, "prices_resolved": 9, "symbols_requested": 9}\n')

    monkeypatch.setattr(trends_job.subprocess, "run", fake_run)
    result = trends_job.run(base_dir, log_path=tmp_path / "log.jsonl", today=date(2026, 1, 20))
    assert len(calls) == 1
    pricing = result["snapshot"]["pricing"]
    assert pricing["refreshed"] is True and pricing["stale"] is False
    assert pricing["live_prices_resolved"] == 7


def test_failed_price_refresh_still_logs_a_snapshot_flagged_stale(tmp_path, monkeypatch):
    base_dir = _workspace(tmp_path)
    _fake_tool(base_dir)

    def boom(cmd, **kw):
        raise trends_job.subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(trends_job.subprocess, "run", boom)
    result = trends_job.run(base_dir, log_path=tmp_path / "log.jsonl", today=date(2026, 1, 20))
    assert result["success"] is True
    assert result["snapshot"]["pricing"]["stale"] is True
    assert "TimeoutExpired" in result["snapshot"]["pricing"]["error"]


def test_no_live_prices_is_flagged_stale_with_the_providers_cause(tmp_path, monkeypatch):
    base_dir = _workspace(tmp_path)
    _fake_tool(base_dir)
    monkeypatch.setattr(trends_job.subprocess, "run", lambda c, **k: _Proc(
        '{"live_prices_resolved": 0, "prices_resolved": 9, "pricing_best_guess_cause": "Stooq returned 404"}', 2))
    pricing = trends_job.run(base_dir, log_path=tmp_path / "log.jsonl", today=date(2026, 1, 20))["snapshot"]["pricing"]
    assert pricing["stale"] is True and pricing["error"] == "Stooq returned 404"


def test_missing_refresh_tool_is_flagged_stale_not_a_crash(tmp_path):
    base_dir = _workspace(tmp_path)
    result = trends_job.run(base_dir, log_path=tmp_path / "log.jsonl", today=date(2026, 1, 20))
    assert result["success"] is True
    assert result["snapshot"]["pricing"]["stale"] is True
