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
