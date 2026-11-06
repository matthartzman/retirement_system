"""A checking-side row tagged invest-deposit / invest-withdrawal is a real investment flow.

Monarch often has only the checking leg of a contribution (the investment account's own
deposit row is missing), so the tag on the checking row must reach Investment Net Flows,
attributed to the investment account named in Notes.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from financial_trends_reporter.trends_metrics import compute_snapshot
from src import ytd_tracking as ytd

TODAY = date(2026, 6, 12)


def _snapshot(tmp_path: Path, tx_rows: str) -> dict:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    header = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
    ytd.import_transactions(base_dir / "input", header + tx_rows, mode="replace", today=TODAY)
    ytd.write_account_setup(base_dir / "input", [
        {"Account": "Hartzman Checking", "Role": "Cash / spending", "Current Balance": "900"},
        {"Account": "Trust - Matt", "Role": "Investment", "Mapped Investment Account": "Trust - Matt",
         "Prior Year End Balance": "100000", "Current Value": "110000"},
    ])
    return compute_snapshot(base_dir, today=TODAY)


def test_tagged_checking_outflow_counts_as_a_contribution_to_the_named_account(tmp_path):
    snap = _snapshot(tmp_path,
        "2026-02-10,Morgan Stanley,Transfer,Hartzman Checking,MSPBNA ACH TRNSFR,to Trust - Matt,-75000,invest-deposit,Household\n")
    assert snap["investment_net_flows_by_account"]["Trust - Matt"] == {
        "to_checking": 0.0, "from_checking": 75000.0, "net": -75000.0}


def test_tagged_checking_row_without_a_named_account_is_still_counted(tmp_path):
    snap = _snapshot(tmp_path,
        "2026-02-10,Morgan Stanley,Transfer,Hartzman Checking,MSPBNA ACH TRNSFR,,-75000,invest-deposit,Household\n")
    flows = snap["investment_net_flows_by_account"]
    assert sum(v["from_checking"] for v in flows.values()) == 75000.0
    assert "Unassigned investment (via Hartzman Checking)" in flows


def test_untagged_checking_transfer_is_not_a_flow(tmp_path):
    snap = _snapshot(tmp_path,
        "2026-02-10,Morgan Stanley,Transfer,Hartzman Checking,MSPBNA ACH TRNSFR,,-75000,,Household\n")
    assert not snap["investment_net_flows_by_account"]
