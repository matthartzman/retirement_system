"""Item 347b: per-account investment net flows (transfers to/from checking).

Reconciles to the account-wide deposit/withdrawal totals, and the log also
carries per-account non-investment balances (decision D6, needed by 347c).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

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
        "2026-01-10,ACH,Deposit,Brokerage A,Bank,,5000,,Household\n"
        "2026-02-10,ETF Distribution,Dividends and Capital Gains,Brokerage A,Broker,,200,,Household\n"
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-1000,,Household\n"
        "2026-03-12,Transfer Out,Withdrawal,IRA B,Broker,,-7000,,Household\n"
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
        {"Account": "Visa", "Role": "Credit card", "Current Balance": "2000"},
        {"Account": "Old", "Role": "Ignore", "Current Balance": "9"},
    ])


def test_investment_net_flows_by_account_hand_checked(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    flows = compute_snapshot(base_dir, today=TODAY)["investment_net_flows_by_account"]
    # Brokerage A: 5000 contributed, 1000 withdrawn (the 200 distribution is income, not a flow).
    assert flows["Brokerage A"] == {"to_checking": 1000.0, "from_checking": 5000.0, "net": -4000.0}
    # IRA B: 7000 withdrawn, 2500 contributed -> a net withdrawal is positive.
    assert flows["IRA B"] == {"to_checking": 7000.0, "from_checking": 2500.0, "net": 4500.0}
    assert "Checking" not in flows


def test_per_account_net_reconciles_to_aggregate(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    inv = ytd.ytd_summary(base_dir / "input", today=TODAY)["investment_balance"]
    per_account = inv["net_flows_by_account"].values()
    # The aggregate is deposits - withdrawals; the per-account net is the opposite sign.
    assert round(sum(v["net"] for v in per_account), 2) == -inv["net_ytd_investment_cashflow"]
    assert round(sum(v["to_checking"] for v in per_account), 2) == inv["external_withdrawals"]
    assert round(sum(v["from_checking"] for v in per_account), 2) == inv["external_deposits"]


def test_net_worth_logs_non_investment_account_balances(tmp_path):
    base_dir = _workspace(tmp_path)
    _seed(base_dir)
    others = compute_snapshot(base_dir, today=TODAY)["net_worth"]["other_accounts"]
    by_name = {o["account"]: o for o in others}
    assert by_name["Checking"] == {"account": "Checking", "role": "Cash / spending", "value": 900.0, "liability": False}
    assert by_name["Visa"]["role"] == "Credit card" and by_name["Visa"]["value"] == 2000.0 and by_name["Visa"]["liability"] is True
    assert "Brokerage A" not in by_name and "Old" not in by_name


def _flows_for(tmp_path, rows, decisions=None):
    base_dir = _workspace(tmp_path)
    header = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"
    ytd.import_transactions(base_dir / "input", header + rows, mode="replace", today=TODAY)
    ytd.write_account_setup(base_dir / "input", [
        {"Account": "Checking", "Role": "Cash / spending", "Current Balance": "900"},
        {"Account": "Brokerage A", "Role": "Investment", "Mapped Investment Account": "Brokerage A", "Prior Year End Balance": "1"},
        {"Account": "IRA B", "Role": "Investment", "Mapped Investment Account": "IRA B", "Prior Year End Balance": "1"},
    ])
    return ytd.ytd_summary(base_dir / "input", today=TODAY, passthrough_decisions=decisions)["investment_balance"]


def test_exact_match_up_to_30_days_apart_is_excluded(tmp_path):
    inv = _flows_for(tmp_path, (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-04-09,ACH,Deposit,IRA B,Bank,,5000,,Household\n"
    ))
    assert inv["net_flows_by_account"] == {} and inv["passthrough_review"] == []


NEAR = (
    "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
    "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household\n"
)
NEAR_KEY = "2026-03-10|Brokerage A|5000.00>2026-03-14|IRA B|4950.00"


def test_near_match_within_100_dollars_is_flagged_and_counted_until_decided(tmp_path):
    inv = _flows_for(tmp_path, NEAR)
    assert inv["external_withdrawals"] == 5000.0 and inv["external_deposits"] == 4950.0
    [item] = inv["passthrough_review"]
    assert item["key"] == NEAR_KEY and item["difference"] == 50.0
    assert item["withdrawal"]["account"] == "Brokerage A" and item["deposit"]["account"] == "IRA B"


def test_approved_near_match_is_excluded_and_denied_is_counted_without_reasking(tmp_path):
    approved = _flows_for(tmp_path / "a", NEAR, {NEAR_KEY: "approve"})
    assert approved["net_flows_by_account"] == {} and approved["passthrough_review"] == []
    denied = _flows_for(tmp_path / "d", NEAR, {NEAR_KEY: "deny"})
    assert denied["external_withdrawals"] == 5000.0 and denied["passthrough_review"] == []


def test_difference_over_100_dollars_is_not_a_candidate(tmp_path):
    inv = _flows_for(tmp_path, NEAR.replace("4950", "4800"))
    assert inv["passthrough_review"] == [] and inv["external_withdrawals"] == 5000.0


def test_investment_to_investment_via_checking_is_not_a_withdrawal(tmp_path):
    inv = _flows_for(tmp_path, (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-03-12,ACH,Deposit,IRA B,Bank,,5000,,Household\n"
        "2026-04-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-300,,Household\n"
    ))
    assert inv["net_flows_by_account"] == {"Brokerage A": {"to_checking": 300.0, "from_checking": 0.0, "net": 300.0}}
    assert inv["external_withdrawals"] == 300.0 and inv["external_deposits"] == 0.0
    assert inv["excluded_passthrough_rows"] == 2


def test_tagged_rows_are_excluded_even_without_a_matching_leg(tmp_path):
    inv = _flows_for(tmp_path, (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,invest-to-invest,Household\n"
        "2026-03-12,ACH,Deposit,IRA B,Bank,pass-through to IRA,4900,,Household\n"
    ))
    assert inv["net_flows_by_account"] == {}
    assert inv["excluded_passthrough_rows"] == 2


def test_unmatched_amounts_dates_or_same_account_still_count(tmp_path):
    inv = _flows_for(tmp_path, (
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household\n"
        "2026-04-20,ACH,Deposit,IRA B,Bank,,5000,,Household\n"      # 41 days later: outside the 30-day window
        "2026-05-01,Transfer Out,Withdrawal,IRA B,Broker,,-200,,Household\n"
        "2026-05-02,ACH,Deposit,IRA B,Bank,,200,,Household\n"       # same account: not a pass-through
    ))
    assert inv["external_withdrawals"] == 5200.0 and inv["external_deposits"] == 5200.0
    assert inv["excluded_passthrough_rows"] == 0
    assert round(sum(v["net"] for v in inv["net_flows_by_account"].values()), 2) == -inv["net_ytd_investment_cashflow"]


def _csv(*rows):
    return "".join(r + chr(10) for r in rows)


def test_payroll_401k_deposits_are_never_pass_through_candidates(tmp_path):
    # A real $1,000 withdrawal must not be paired with a same-amount 401k deferral / employer match.
    inv = _flows_for(tmp_path, _csv(
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-1000,,Household",
        "2026-03-12,Contribution,401k Contribution,IRA B,Employee Deferral Curr Yr,,1000,,Household",
        "2026-03-12,Contribution,401K Match,IRA B,Employer Curr Yr,,1000,,Household",
    ))
    assert inv["external_withdrawals"] == 1000.0 and inv["external_deposits"] == 2000.0
    assert inv["excluded_passthrough_rows"] == 0 and inv["passthrough_review"] == []


def test_tagging_one_leg_also_excludes_its_exact_counterpart(tmp_path):
    inv = _flows_for(tmp_path, _csv(
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,invest-to-invest,Household",
        "2026-03-12,ACH,Deposit,IRA B,Bank,,5000,,Household",
    ))
    assert inv["net_flows_by_account"] == {} and inv["excluded_passthrough_rows"] == 2


def test_identical_lookalike_near_pairs_get_distinct_keys(tmp_path):
    inv = _flows_for(tmp_path, _csv(
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household",
        "2026-03-10,Transfer Out,Withdrawal,Brokerage A,Broker,,-5000,,Household",
        "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household",
        "2026-03-14,ACH,Deposit,IRA B,Bank,,4950,,Household",
    ))
    keys = [item["key"] for item in inv["passthrough_review"]]
    assert len(keys) == 2 and len(set(keys)) == 2
