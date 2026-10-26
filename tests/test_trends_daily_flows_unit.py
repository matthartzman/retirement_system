"""Trends Phase 4: a daily investment flows ledger beside the monthly one.

The daily ledger must reconcile exactly to the monthly ledger (every account, every month),
apply the same passthrough exclusions, run across every imported year in the snapshot, and be
passed through by ``/api/flows`` so the client can bucket it by the selected time scope.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from financial_trends_reporter import flows
from financial_trends_reporter.main import create_app
from financial_trends_reporter.trends_log import append_or_replace_entry
from financial_trends_reporter.trends_metrics import compute_snapshot
from src import ytd_tracking as ytd

TODAY = date(2026, 6, 12)
HEADER = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
ROWS = (
    "2025-11-05,ACH,Deposit,Brokerage A,Bank,,3000,,Household\n"
    "2025-11-05,ACH,Deposit,Brokerage A,Bank,,0.33,,Household\n"
    "2025-12-20,Transfer Out,Withdrawal,Brokerage A,Broker,,-400,,Household\n"
    "2026-01-10,ACH,Deposit,Brokerage A,Bank,,5000,,Household\n"
    "2026-02-10,ETF Distribution,Dividends and Capital Gains,Brokerage A,Broker,,200,,Household\n"
    "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-1000,,Household\n"
    "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-0.12,,Household\n"
    "2026-03-12,Transfer Out,Withdrawal,IRA B,Broker,,-7000,,Household\n"
    "2026-03-20,ACH,Deposit,Brokerage A,Bank,,250,,Household\n"
    "2026-04-01,ACH,Deposit,IRA B,Bank,,2500,,Household\n"
    "2026-04-02,Groceries,Groceries,Checking,Bank,,-50,,Household\n"
)


def _workspace(tmp_path: Path, rows: str = ROWS) -> Path:
    base = tmp_path / "workspace"
    (base / "input").mkdir(parents=True)
    (base / "local_state").mkdir(parents=True)
    ytd.import_transactions(base / "input", HEADER + rows, mode="replace", today=TODAY)
    ytd.write_account_setup(base / "input", [
        {"Account": "Checking", "Role": "Cash / spending", "Current Balance": "900"},
        {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A",
         "Prior Year End Balance": "100000", "Current Value": "110000"},
        {"Account": "IRA B", "Role": "Investment", "Mapped Investment Account": "IRA B",
         "Prior Year End Balance": "50000", "Current Value": "46000"},
    ])
    return base


def _assert_daily_reconciles_to_monthly(daily, monthly):
    assert set(daily) == set(monthly)
    for acct, months in monthly.items():
        assert {d[:7] for d in daily[acct]} == set(months), acct
        for month, cell in months.items():
            days = [v for d, v in daily[acct].items() if d[:7] == month]
            for key in ("to_checking", "from_checking"):
                assert abs(sum(v[key] for v in days) - cell[key]) < 0.005 * max(1, len(days)), (acct, month, key)


# ---- ytd_tracking ----------------------------------------------------------------------

def test_accumulate_daily_applies_the_monthly_kind_rule():
    daily: dict = {}
    ytd.accumulate_investment_flow_daily(daily, "A", date(2026, 3, 10), "investment_deposit", 100.0)
    ytd.accumulate_investment_flow_daily(daily, "A", date(2026, 3, 10), "investment_withdrawal", -40.0)
    ytd.accumulate_investment_flow_daily(daily, "A", date(2026, 3, 10), "investment_deposit", 5.5)
    ytd.accumulate_investment_flow_daily(daily, "A", date(2026, 3, 11), "investment_income", 999.0)
    assert daily == {"A": {"2026-03-10": {"to_checking": 40.0, "from_checking": 105.5}}}
    assert ytd.investment_daily_flows_by_account({}) == {}


def test_daily_ledger_reconciles_to_monthly_ledger(tmp_path):
    base = _workspace(tmp_path)
    inv = ytd.ytd_summary(base / "input", today=TODAY)["investment_balance"]
    daily = inv["daily_flows_by_account"]
    assert daily["Brokerage A"]["2026-03-10"] == {"to_checking": 1000.12, "from_checking": 0.0}
    assert daily["IRA B"] == {
        "2026-03-12": {"to_checking": 7000.0, "from_checking": 0.0},
        "2026-04-01": {"to_checking": 0.0, "from_checking": 2500.0},
    }
    assert list(daily["Brokerage A"]) == sorted(daily["Brokerage A"])
    _assert_daily_reconciles_to_monthly(daily, inv["monthly_flows_by_account"])


def test_passthrough_rows_are_excluded_from_daily_too(tmp_path):
    rows = (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-03-12,ACH,Deposit,IRA B,Bank,,5000,,Household\n"
        "2026-04-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-300,,Household\n"
    )
    inv = ytd.ytd_summary(_workspace(tmp_path, rows) / "input", today=TODAY)["investment_balance"]
    assert inv["excluded_passthrough_rows"] == 2
    assert inv["daily_flows_by_account"] == {"Brokerage A": {"2026-04-10": {"to_checking": 300.0, "from_checking": 0.0}}}
    _assert_daily_reconciles_to_monthly(inv["daily_flows_by_account"], inv["monthly_flows_by_account"])


def test_approved_near_match_is_excluded_from_daily(tmp_path):
    rows = (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household\n"
    )
    key = "2026-03-10|Brokerage A|5000.00>2026-03-14|IRA B|4950.00"
    base = _workspace(tmp_path, rows)
    pending = ytd.ytd_summary(base / "input", today=TODAY)["investment_balance"]
    assert pending["daily_flows_by_account"]["Brokerage A"] == {"2026-03-10": {"to_checking": 5000.0, "from_checking": 0.0}}
    approved = ytd.ytd_summary(base / "input", today=TODAY, passthrough_decisions={key: "approve"})["investment_balance"]
    assert approved["daily_flows_by_account"] == {} and approved["monthly_flows_by_account"] == {}


def test_no_investment_flows_gives_empty_daily(tmp_path):
    rows = "2026-04-02,Groceries,Groceries,Checking,Bank,,-50,,Household\n"
    inv = ytd.ytd_summary(_workspace(tmp_path, rows) / "input", today=TODAY)["investment_balance"]
    assert inv["daily_flows_by_account"] == {}


# ---- snapshot --------------------------------------------------------------------------

def test_snapshot_carries_daily_ledger_across_years_reconciled_to_monthly(tmp_path):
    snap = compute_snapshot(_workspace(tmp_path), today=TODAY)
    daily = snap["investment_flows_daily"]
    assert daily["Brokerage A"]["2025-11-05"] == {"to_checking": 0.0, "from_checking": 3000.33}
    assert daily["Brokerage A"]["2025-12-20"] == {"to_checking": 400.0, "from_checking": 0.0}
    assert list(daily["Brokerage A"]) == sorted(daily["Brokerage A"])
    _assert_daily_reconciles_to_monthly(daily, snap["investment_flows_monthly"])


def test_snapshot_daily_honours_passthrough_decisions(tmp_path):
    rows = (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household\n"
    )
    key = "2026-03-10|Brokerage A|5000.00>2026-03-14|IRA B|4950.00"
    snap = compute_snapshot(_workspace(tmp_path, rows), today=TODAY, passthrough_decisions={key: "approve"})
    assert snap["investment_flows_daily"] == {} and snap["investment_flows_monthly"] == {}


# ---- flows.py / endpoint ---------------------------------------------------------------

MONTHLY = {"IRA B": {"2026-02": {"to_checking": 50.0, "from_checking": 10.0}}}
DAILY = {"IRA B": {"2026-02-03": {"to_checking": 50.0, "from_checking": 0.0},
                   "2026-02-20": {"to_checking": 0.0, "from_checking": 10.0}}}


def test_payload_includes_daily_when_logged():
    p = flows.flows_payload({"as_of_date": "2026-03-01", "investment_flows_monthly": MONTHLY,
                             "investment_flows_daily": DAILY}, [])
    assert p["daily"] == DAILY and p["monthly"] == MONTHLY


def test_payload_daily_is_none_for_older_logs():
    p = flows.flows_payload({"as_of_date": "2026-03-01", "investment_flows_monthly": MONTHLY}, [])
    assert p["daily"] is None
    assert flows.flows_payload(None, [])["daily"] is None


def test_payload_lists_accounts_seen_only_in_daily():
    p = flows.flows_payload({"as_of_date": "2026-03-01", "investment_flows_monthly": {},
                             "investment_flows_daily": DAILY}, [])
    assert [a["flow_account"] for a in p["accounts"]] == ["IRA B"]


def test_flows_endpoint_returns_daily(tmp_path):
    ws = tmp_path / "ws"
    (ws / "input").mkdir(parents=True)
    (ws / "local_state").mkdir()
    log = tmp_path / "log.jsonl"
    append_or_replace_entry(log, {"as_of_date": "2026-03-01", "investment_flows_monthly": MONTHLY,
                                  "investment_flows_daily": DAILY})
    body = json.loads(create_app(ws, log_path=log).test_client().get("/api/flows").get_data(as_text=True))
    assert body["daily"] == DAILY
