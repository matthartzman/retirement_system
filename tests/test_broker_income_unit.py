"""Interest and dividend reconciliation of imported broker rows against Monarch income rows."""
import pytest

from src import active_plan, broker_import, broker_income
from tests.broker_activity_fixtures import FILE_NAME, history_csv

ACCT = "Member_1_HSA"


def _b(d, amt, kind="dividend", sym="X"):
    return {"run_date": d, "amount": amt, "kind": kind, "symbol": sym}


def _m(d, amt):
    return {"date": d, "amount": amt}


def test_match_one_to_one_within_tolerance():
    out = broker_income.match_income([_b("2026-03-20", 94.95), _b("2026-03-20", 94.95), _b("2026-05-06", 4.5)],
                                     [_m("2026-03-23", 94.95), _m("2026-05-01", 4.5), _m("2026-06-01", 1.0)])
    assert out["totals"]["matched"] == 1
    assert [b["run_date"] for b in out["broker_only"]] == ["2026-03-20", "2026-05-06"]
    assert len(out["monarch_only"]) == 2
    assert out["totals"]["difference"] == round(94.95 * 2 + 4.5 - 94.95 - 4.5 - 1.0, 2)
    assert {m["month"] for m in out["months"]} == {"2026-03", "2026-05", "2026-06"}


def test_nearest_date_wins():
    out = broker_income.match_income([_b("2026-03-20", 10.0)], [_m("2026-03-23", 10.0), _m("2026-03-21", 10.0)])
    assert out["matched"][0]["monarch"]["date"] == "2026-03-21"


def test_monarch_rows_filtered_by_mapped_account_category_and_year():
    rows = [{"Date": "2026-09-18", "Account": "Health Savings Account (HSA)", "Category": "Dividends & Capital Gains", "Amount": "201"},
            {"Date": "2026-09-18", "Account": "Health Savings Account (HSA)", "Category": "Buy", "Amount": "-201"},
            {"Date": "2025-09-18", "Account": "Health Savings Account (HSA)", "Category": "Interest", "Amount": "1"},
            {"Date": "2026-09-18", "Account": "Other", "Category": "Interest", "Amount": "1"}]
    got = broker_income.monarch_income_rows(rows, {"health savings account (hsa)"}, 2026)
    assert [(r["date"], r["amount"]) for r in got] == [("2026-09-18", 201.0)]


@pytest.fixture
def ws(tmp_path):
    base = tmp_path / "ws"
    (base / "input").mkdir(parents=True)
    with active_plan.workspace_store(base, write=True) as store:
        store.dataset("ytd_account_setup").replace_all([{"Account": "Health Savings Account (HSA)", "Role": "Investment",
                                                         "Mapped Investment Account": ACCT}])
        store.dataset("ytd_transactions").replace_all([
            {"Date": "2026-09-18", "Account": "Health Savings Account (HSA)", "Category": "Dividends & Capital Gains",
             "Amount": "201", "Merchant": "Example ETF", "Monarch Id": "1"},
            {"Date": "2026-05-07", "Account": "Health Savings Account (HSA)", "Category": "Dividends & Capital Gains",
             "Amount": "4.50", "Merchant": "Example Treasury", "Monarch Id": "2"},
            {"Date": "2026-07-01", "Account": "Health Savings Account (HSA)", "Category": "Interest",
             "Amount": "0.03", "Merchant": "Interest", "Monarch Id": "3"}])
    broker_import.commit(base / "input", broker="fidelity", text=history_csv(), file_name=FILE_NAME, account=ACCT)
    return base / "input"


def test_reconcile_service(ws):
    rep = broker_income.reconcile(ws, account=ACCT, year=2026)
    assert rep["monarch_accounts"] == ["health savings account (hsa)"]
    assert rep["by_kind"] == {"dividend": 205.62}
    assert rep["totals"]["matched"] == 2
    assert [b["symbol"] for b in rep["broker_only"]] == ["FDRXX"]      # the sweep dividend Monarch did not show
    assert [m["amount"] for m in rep["monarch_only"]] == [0.03]
    reinv = {b["broker"]["symbol"]: b["broker"]["reinvested"] for b in rep["matched"]}
    assert reinv == {"SHRT": False, "TOTL": True}
    assert rep["coverage"][0]["date_from"] == "2026-01-16"
    assert broker_income.income_totals(ws, account=ACCT, year=2026) == {"dividend": 205.62}
