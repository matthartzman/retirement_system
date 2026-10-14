"""Item 347b: approve/deny store for near-match investment pass-through pairs."""
from __future__ import annotations

import json
from datetime import date

import pytest

from financial_trends_reporter.passthrough_decisions import load_decisions, save_decision
from financial_trends_reporter.trends_metrics import compute_snapshot
from src import ytd_tracking as ytd


def test_missing_or_corrupt_file_loads_empty(tmp_path):
    assert load_decisions(tmp_path / "none.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_decisions(bad) == {}


def test_save_round_trips_and_overwrites(tmp_path):
    path = tmp_path / "data" / "d.json"
    save_decision(path, "k1", "approve")
    save_decision(path, "k2", "deny")
    save_decision(path, "k1", "deny")
    assert load_decisions(path) == {"k1": "deny", "k2": "deny"}
    assert json.loads(path.read_text(encoding="utf-8"))["k2"] == "deny"


def test_invalid_decision_or_key_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_decision(tmp_path / "d.json", "k", "maybe")
    with pytest.raises(ValueError):
        save_decision(tmp_path / "d.json", "", "approve")


def test_snapshot_logs_pending_review_and_honours_saved_decision(tmp_path):
    base = tmp_path / "w"
    (base / "input").mkdir(parents=True)
    (base / "local_state").mkdir()
    header = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
    rows = (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household\n"
    )
    today = date(2026, 6, 12)
    ytd.import_transactions(base / "input", header + rows, mode="replace", today=today)
    ytd.write_account_setup(base / "input", [
        {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A", "Prior Year End Balance": "1"},
        {"Account": "IRA B", "Role": "Investment", "Mapped Investment Account": "IRA B", "Prior Year End Balance": "1"},
    ])
    pending = compute_snapshot(base, today=today)
    [item] = pending["passthrough_review"]
    assert pending["investment_net_flows_by_account"]["Brokerage A"]["net"] == 5000.0
    decided = compute_snapshot(base, today=today, passthrough_decisions={item["key"]: "approve"})
    assert decided["passthrough_review"] == [] and decided["investment_net_flows_by_account"] == {}
