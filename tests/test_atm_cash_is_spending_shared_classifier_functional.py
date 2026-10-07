"""ATM/cash withdrawals are always spending, and the Spending Budget Tracker
uses the same classifier as This Year Performance so the totals reconcile."""
import shutil
from datetime import date
from pathlib import Path

from src import spending_tracker as T
from src import ytd_tracking as Y
from tests.plan_fixture import reload_flat_datasets

DEMO = Path(__file__).resolve().parents[1] / "input" / "demo"


def _row(**kw):
    base = {"Date": "2026-02-20", "Merchant": "ATM Withdrawal", "Category": "Cash & ATM",
            "Account": "Family Checking", "Original Statement": "ATM WITHDRAWAL",
            "Notes": "", "Tags": "", "Amount": "-99"}
    base.update(kw)
    return base


def test_atm_and_cash_withdrawals_are_spending():
    assert Y.classify_cash_transaction(_row()) == "spending"
    # Even when miscategorised as a transfer, an ATM/cash withdrawal is spending.
    assert Y.classify_cash_transaction(_row(Category="Transfer")) == "spending"
    assert Y.classify_cash_transaction(_row(Category="Cash", Merchant="Cash Withdrawal", **{"Original Statement": ""})) == "spending"


def test_real_transfers_and_investment_withdrawals_still_excluded():
    assert Y.classify_cash_transaction(_row(Merchant="Brokerage", Category="Transfer", **{"Original Statement": "TRANSFER"})) == "transfer"
    assert Y.classify_cash_transaction(_row(Merchant="Fidelity", Category="Misc", **{"Original Statement": "FROM BROKERAGE"})) == "transfer"


def test_tracker_and_ytd_panel_agree_on_demo(tmp_path):
    root = tmp_path
    (root / "input").mkdir()
    for f in DEMO.glob("*.csv"):
        shutil.copy(f, root / f.name)
        shutil.copy(f, root / "input" / f.name)
    reload_flat_datasets(root)  # the spending taxonomy and aliases are plan file tables (WP6.3a)
    ytd = Y.ytd_summary(root, today=date(2026, 9, 29))
    tracker = T.spending_summary_taxonomy(root, 2026)
    assert round(tracker["expense_actual"], 2) == round(ytd["actual"]["spending"], 2)
    assert round(tracker["income_actual"], 2) == round(ytd["actual"]["income"], 2)
