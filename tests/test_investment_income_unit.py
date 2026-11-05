"""Investment income by type for the taxable accounts: rules, Treasury-bill maturity interest, per-symbol overrides, CSV."""
from __future__ import annotations

import pytest

from src import active_plan, investment_income
from src.sales_ledger import ValidationError

TRUST, IRA = "Member_1_Trust", "Member_1_IRA"


def _row(n, account, date, kind, symbol, qty, price, amount, action="", desc=""):
    return {"row_key": f"k{n}", "broker": "etrade", "account": account, "run_date": date, "settle_date": date, "kind": kind,
            "sweep": False, "action": action or kind.title(), "symbol": symbol, "description": desc, "quantity": qty,
            "price": price, "commission": 0.0, "fees": None, "accrued_interest": None, "amount": amount,
            "cash_balance": None, "candidate_id": None, "lot_ref": None}


@pytest.fixture()
def input_dir(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        for acct, rows in {
            TRUST: [
                _row(1, TRUST, "2026-03-20", "dividend", "ITOT", None, None, 100.0),
                _row(2, TRUST, "2026-03-20", "dividend", "MUB", None, None, 40.0, desc="ISHARES NAT MUN BN ETF TAX FREE INCOME"),
                _row(3, TRUST, "2026-03-20", "dividend", "SHV", None, None, 25.0),
                _row(4, TRUST, "2026-04-01", "interest", "MSBNK", None, None, 3.5),
                _row(5, TRUST, "2026-04-02", "cap_gain_long", "ITOT", None, None, 12.0),
                _row(6, TRUST, "2025-12-30", "dividend", "ITOT", None, None, 999.0),                       # another year
                _row(7, TRUST, "2026-09-24", "buy", "912797VN4", 120000.0, 0.99661155, -119593.39),
                _row(8, TRUST, "2026-10-27", "sell", "912797VN4", -120000.0, 1.0, 120000.0, action="Redemption",
                     desc="US TSY BILL 26OC27 REDEMPTION OF MATURED BOND"),
            ],
            IRA: [_row(9, IRA, "2026-03-20", "dividend", "ITOT", None, None, 5000.0)],                     # sheltered: left out
        }.items():
            iid = store.broker.add_import(broker="etrade", account=acct, date_from="2025-01-01", date_to="2026-12-31")
            store.broker.add_rows(iid, rows)
    return tmp_path / "input"


def test_taxable_accounts_only_split_by_type_with_the_bill_as_treasury_interest(input_dir):
    d = investment_income.build(input_dir, 2026)
    assert set(d["by_account"]) == {TRUST}
    t = d["totals"]
    assert t["dividend_ordinary"] == 100.0 and t["dividend_muni_fund"] == 40.0 and t["dividend_treasury_fund"] == 25.0
    assert t["interest_ordinary"] == 3.5 and t["cap_gain_distribution_long"] == 12.0
    assert t["interest_treasury"] == pytest.approx(406.61)           # 120,000 redemption less 119,593.39 cost
    assert sum(r["amount"] for r in d["rows"]) == pytest.approx(100 + 40 + 25 + 3.5 + 12 + 406.61)


def test_a_symbol_override_moves_its_rows_and_can_be_cleared(input_dir):
    investment_income.set_symbol_type(input_dir, "shv", "dividend_ordinary")
    assert investment_income.build(input_dir, 2026)["totals"]["dividend_ordinary"] == 125.0
    investment_income.set_symbol_type(input_dir, "SHV", None)
    assert investment_income.build(input_dir, 2026)["totals"]["dividend_treasury_fund"] == 25.0
    with pytest.raises(ValidationError):
        investment_income.set_symbol_type(input_dir, "SHV", "nonsense")


def test_a_bill_whose_purchase_is_not_on_file_is_noted_not_guessed(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        iid = store.broker.add_import(broker="etrade", account=TRUST)
        store.broker.add_rows(iid, [_row(1, TRUST, "2026-10-27", "sell", "912797VN4", -1000.0, 1.0, 1000.0, action="Redemption",
                                         desc="US TSY BILL REDEMPTION OF MATURED BOND")])
    d = investment_income.build(tmp_path / "input", 2026)
    assert "interest_treasury" not in d["totals"] and any("purchase is not in the broker files" in n for n in d["notes"])


def test_csv_has_one_line_per_row(input_dir):
    lines = investment_income.to_csv(investment_income.build(input_dir, 2026)).strip().splitlines()
    assert lines[0] == "date,account,symbol,type,amount,description" and len(lines) == 1 + 6
