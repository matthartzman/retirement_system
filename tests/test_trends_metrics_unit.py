"""Ticket 306: the standalone financial trends reporter computes its four
metric groups (YTD expenses by category, holdings, net worth, cashflow)
almost entirely via src.ytd_tracking.ytd_summary() -- the same engine the
main app's YTD dashboard already uses -- plus a plain liabilities-CSV sum
for net worth.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from financial_trends_reporter.trends_metrics import compute_snapshot
from src import config_backend, ytd_tracking as ytd


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


def _seed(base_dir: Path) -> None:
    input_dir = base_dir / "input"
    ytd.write_transactions(input_dir, [
        {"Date": "2026-01-10", "Merchant": "Kroger", "Category": "Groceries", "Account": "Checking",
         "Amount": "-100.00", "Owner": "Member_1"},
        {"Date": "2026-01-15", "Merchant": "Employer", "Category": "Paychecks", "Account": "Checking",
         "Amount": "5000.00", "Owner": "Member_1"},
    ], today=date(2026, 1, 20))
    ytd.write_account_setup(input_dir, [
        {"Account": "Checking", "Role": "Cash / spending", "Prior Year End Balance": "1000", "Current Balance": "1500"},
        {"Account": "Brokerage", "Role": "Investment", "Mapped Investment Account": "Brokerage",
         "Prior Year End Balance": "100000", "Current Value": "110000"},
        {"Account": "Visa", "Role": "Credit card", "Current Balance": "2000"},
    ])
    db_path = base_dir / "local_state" / "retirement_system_v10.db"
    config_backend.set_client_file("client_liabilities.csv", "balance\n50000\n", db_path=db_path)


def test_ytd_expenses_by_category(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    snapshot = compute_snapshot(base_dir, today=date(2026, 1, 20))
    assert snapshot["ytd_expenses_by_category"]["Groceries"] == 100.0


def test_cashflow_income_and_expenses(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    snapshot = compute_snapshot(base_dir, today=date(2026, 1, 20))
    cashflow = snapshot["cashflow"]
    assert cashflow["income"] == 5000.0
    assert cashflow["expenses"] == 100.0
    assert cashflow["net"] == 4900.0


def test_net_worth_combines_account_setup_and_liabilities_csv(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    snapshot = compute_snapshot(base_dir, today=date(2026, 1, 20))
    nw = snapshot["net_worth"]
    # assets: Checking 1500 + Brokerage 110000 = 111500
    assert nw["assets"] == 111500.0
    # liabilities: Visa 2000 (account_setup) + client_liabilities.csv 50000
    assert nw["liabilities"] == 52000.0
    assert nw["total"] == 111500.0 - 52000.0


def test_holdings_value_and_growth(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    snapshot = compute_snapshot(base_dir, today=date(2026, 1, 20))
    holdings = snapshot["holdings"]
    assert holdings["current_value"] == 110000.0
    assert holdings["prior_year_end_balance"] == 100000.0
    assert holdings["ytd_growth"] == 10000.0


def test_no_transactions_yet_does_not_crash(tmp_path):
    base_dir = _workspace(tmp_path)
    snapshot = compute_snapshot(base_dir, today=date(2026, 1, 20))
    assert snapshot["ytd_expenses_by_category"] == {}
    assert snapshot["as_of_date"]
