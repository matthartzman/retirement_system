"""Phase 5 of the Monarch balances feed: monthly investment flows (backend).

The monthly ledger must reconcile to the existing YTD per-account flows, extend across
imported years, and aggregate/toggle through the Monarch registry mapping.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from financial_trends_reporter import balance_store as bs
from financial_trends_reporter import flows
from financial_trends_reporter.main import create_app
from financial_trends_reporter.trends_log import append_or_replace_entry
from financial_trends_reporter.trends_metrics import compute_snapshot
from src import ytd_tracking as ytd

TODAY = date(2026, 6, 12)


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


def _seed(base_dir: Path) -> None:
    input_dir = base_dir / "input"
    tx = (
        "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
        "2025-11-05,ACH,Deposit,Brokerage A,Bank,,3000,,Household\n"
        "2025-12-20,Transfer Out,Withdrawal,Brokerage A,Broker,,-400,,Household\n"
        "2026-01-10,ACH,Deposit,Brokerage A,Bank,,5000,,Household\n"
        "2026-02-10,ETF Distribution,Dividends and Capital Gains,Brokerage A,Broker,,200,,Household\n"
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-1000,,Household\n"
        "2026-03-12,Transfer Out,Withdrawal,IRA B,Broker,,-7000,,Household\n"
        "2026-03-20,ACH,Deposit,Brokerage A,Bank,,250,,Household\n"
        "2026-04-01,ACH,Deposit,IRA B,Bank,,2500,,Household\n"
        "2026-04-02,Groceries,Groceries,Checking,Bank,,-50,,Household\n"
    )
    ytd.import_transactions(input_dir, tx, mode="replace", today=TODAY)
    ytd.write_account_setup(input_dir, [
        {"Account": "Checking", "Role": "Cash / spending", "Current Balance": "900"},
        {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A",
         "Prior Year End Balance": "100000", "Current Value": "110000"},
        {"Account": "IRA B", "Role": "Investment", "Mapped Investment Account": "IRA B",
         "Prior Year End Balance": "50000", "Current Value": "46000"},
    ])


def test_monthly_ledger_hand_checked_across_years(tmp_path):
    base = _workspace(tmp_path)
    _seed(base)
    monthly = compute_snapshot(base, today=TODAY)["investment_flows_monthly"]
    assert monthly["Brokerage A"] == {
        "2025-11": {"to_checking": 0.0, "from_checking": 3000.0},
        "2025-12": {"to_checking": 400.0, "from_checking": 0.0},
        "2026-01": {"to_checking": 0.0, "from_checking": 5000.0},
        "2026-03": {"to_checking": 1000.0, "from_checking": 250.0},
    }
    assert monthly["IRA B"] == {
        "2026-03": {"to_checking": 7000.0, "from_checking": 0.0},
        "2026-04": {"to_checking": 0.0, "from_checking": 2500.0},
    }
    assert "Checking" not in monthly  # not an investment account


def test_monthly_current_year_reconciles_to_ytd_per_account(tmp_path):
    base = _workspace(tmp_path)
    _seed(base)
    snap = compute_snapshot(base, today=TODAY)
    ytd_flows = snap["investment_net_flows_by_account"]
    for acct, months in snap["investment_flows_monthly"].items():
        cur = [v for m, v in months.items() if m.startswith("2026-")]
        assert round(sum(v["to_checking"] for v in cur), 2) == ytd_flows[acct]["to_checking"]
        assert round(sum(v["from_checking"] for v in cur), 2) == ytd_flows[acct]["from_checking"]


def test_existing_ytd_fields_are_unchanged_by_the_monthly_ledger(tmp_path):
    base = _workspace(tmp_path)
    _seed(base)
    flows_ytd = compute_snapshot(base, today=TODAY)["investment_net_flows_by_account"]
    assert flows_ytd["Brokerage A"] == {"to_checking": 1000.0, "from_checking": 5250.0, "net": -4250.0}


# ---- flows.py -------------------------------------------------------------------------

MONTHLY = {
    "Brokerage A": {"2025-12": {"to_checking": 400.0, "from_checking": 0.0}, "2026-02": {"to_checking": 0.0, "from_checking": 100.0}},
    "IRA B": {"2026-02": {"to_checking": 50.0, "from_checking": 10.0}},
}


def test_monthly_series_fills_gap_months_and_sums_accounts():
    s = flows.monthly_series(MONTHLY)
    assert [p["month"] for p in s] == ["2025-12", "2026-01", "2026-02"]
    assert s[1] == {"month": "2026-01", "credits": 0.0, "debits": 0.0, "net": 0.0}
    assert s[2] == {"month": "2026-02", "credits": 110.0, "debits": 50.0, "net": 60.0}
    assert s[0]["net"] == -400.0


def test_monthly_series_respects_account_selection_and_empty():
    only_ira = flows.monthly_series(MONTHLY, ["IRA B"])
    assert [p["month"] for p in only_ira] == ["2026-02"] and only_ira[0]["credits"] == 10.0
    assert flows.monthly_series(MONTHLY, []) == []
    assert flows.monthly_series({}) == []


def test_ytd_summary_totals_one_year():
    s = flows.monthly_series(MONTHLY)
    assert flows.ytd_summary(s, 2026) == {"year": 2026, "credits": 110.0, "debits": 50.0, "total": 60.0}
    assert flows.ytd_summary(s, 2025) == {"year": 2025, "credits": 0.0, "debits": 400.0, "total": -400.0}
    assert flows.ytd_summary(s, 2024)["total"] == 0.0


def _registry():
    return [
        {"account_key": "ira", "display_name": "IRA - X", "app_account": "IRA B", "enabled": {"flows": True}},
        {"account_key": "brk", "display_name": "Brokerage A", "app_account": "", "enabled": {"flows": False}},
    ]


def test_resolve_by_mapping_then_display_name_and_unmapped_stay_included():
    r = {a["flow_account"]: a for a in flows.resolve_flow_accounts(["IRA B", "Brokerage A", "Mystery"], _registry())}
    assert r["IRA B"] == {"flow_account": "IRA B", "account_keys": ["ira"], "mapped": True, "enabled": True}
    assert r["Brokerage A"]["mapped"] and r["Brokerage A"]["enabled"] is False     # matched by display name, toggled off
    assert r["Mystery"] == {"flow_account": "Mystery", "account_keys": [], "mapped": False, "enabled": True}


def test_many_registry_accounts_one_flow_account_enabled_if_any_on():
    reg = [{"account_key": "a", "display_name": "A", "app_account": "Pool", "enabled": {"flows": False}},
           {"account_key": "b", "display_name": "B", "app_account": "pool", "enabled": {"flows": True}}]
    assert flows.resolve_flow_accounts(["Pool"], reg)[0]["enabled"] is True


def test_payload_applies_toggles_and_reports_ytd_for_the_entry_year():
    entry = {"as_of_date": "2026-03-01", "investment_flows_monthly": MONTHLY}
    p = flows.flows_payload(entry, _registry())
    assert [a["flow_account"] for a in p["accounts"]] == ["Brokerage A", "IRA B"]
    assert [pt["month"] for pt in p["series"]] == ["2026-02"]                    # only IRA B included
    assert p["ytd"] == {"year": 2026, "credits": 10.0, "debits": 50.0, "total": -40.0}
    assert p["monthly"] == MONTHLY                                               # client re-sums on toggle


def test_payload_with_no_entry_or_no_flows():
    assert flows.flows_payload(None, [])["series"] == []
    assert flows.flows_payload({"as_of_date": "2026-01-01"}, [])["ytd"] == {"year": 2026, "credits": 0.0, "debits": 0.0, "total": 0.0}


def test_flows_endpoint(tmp_path):
    ws = _workspace(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    log = data / "log.jsonl"
    append_or_replace_entry(log, {"as_of_date": "2026-03-01", "investment_flows_monthly": MONTHLY})
    body = json.loads(create_app(ws, log_path=log).test_client().get("/api/flows").get_data(as_text=True))
    assert body["ytd"]["year"] == 2026 and len(body["series"]) == 3                 # unmapped accounts stay included
    empty = json.loads(create_app(ws, log_path=data / "none.jsonl").test_client().get("/api/flows").get_data(as_text=True))
    assert empty["series"] == [] and empty["ytd"] is None
