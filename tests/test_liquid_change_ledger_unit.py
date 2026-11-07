"""The Liquid Investments and Cash pop-up's Change parts: the per-account daily ledger of deposits/withdrawals and
income less fees (financial_trends_reporter/liquid_change.py)."""
import pytest

from financial_trends_reporter import liquid_change as lc


def _t(day, account, category, amount):
    return {"Date": day, "Account": account, "Category": category, "Amount": str(amount)}


def _b(day, account, kind, amount, action="", fees=None, commission=None):
    return {"run_date": day, "account": account, "kind": kind, "action": action, "amount": amount,
            "fees": fees, "commission": commission}


def test_transactions_are_flows_except_trades_and_income_categories():
    out = lc.ledger([
        _t("2026-10-01", "Checking", "Paychecks", 5000),
        _t("2026-10-01", "Checking", "Groceries", -200),
        _t("2026-10-02", "Checking", "Transfer", -1000),
        _t("2026-10-02", "Brokerage", "Transfer", 1000),  # the other leg: both included, they cancel in the page's sum
        _t("2026-10-03", "Brokerage", "Buy", -900),        # trade: not a flow
        _t("2026-10-04", "Checking", "Interest", 3.5),
        _t("2026-10-04", "Checking", "Financial Fees", -10),
    ], [], {})
    assert out["daily"]["Checking"] == {"2026-10-01": {"flows": 4800.0, "income": 0.0},
                                        "2026-10-02": {"flows": -1000.0, "income": 0.0},
                                        "2026-10-04": {"flows": 0.0, "income": -6.5}}
    assert out["daily"]["Brokerage"] == {"2026-10-02": {"flows": 1000.0, "income": 0.0}}
    assert out["broker_covered"] == []


def test_broker_file_is_the_income_record_for_its_account():
    rows = [
        _b("2026-09-30", "Member_1_IRA", "dividend", 120.0),
        _b("2026-09-30", "Member_1_IRA", "foreign_tax", -4.0),
        _b("2026-09-30", "Member_1_IRA", "reinvest", -116.0),                      # trade
        _b("2026-10-01", "Member_1_IRA", "sell", 5000.0, fees=0.5, commission=4.95),  # only its fees are income
        _b("2026-10-02", "Member_1_IRA", "other", -25.0, action="Service Fee"),
        _b("2026-10-03", "Member_1_IRA", "other", 1000.0, action="Contribution"),   # a deposit, not income
        _b("2026-10-03", "Unmapped", "dividend", 99.0),
    ]
    monarch = [_t("2026-09-30", "IRA - Matt", "Dividends & Capital Gains", 120),  # duplicate of the broker row
               _t("2026-10-03", "IRA - Matt", "Transfer", 1000)]
    out = lc.ledger(monarch, rows, {"Member_1_IRA": "IRA - Matt"})
    days = out["daily"]["IRA - Matt"]
    assert days["2026-09-30"]["income"] == pytest.approx(116.0)
    assert days["2026-10-01"]["income"] == pytest.approx(-5.45)
    assert days["2026-10-02"]["income"] == pytest.approx(-25.0)
    assert days["2026-10-03"] == {"flows": 1000.0, "income": 0.0}
    assert out["broker_covered"] == ["IRA - Matt"] and "Unmapped" not in out["daily"]


def test_broker_ids_map_to_imported_names_through_accounts_and_sources():
    setup = [{"Account": "IRA - Matt", "Mapped Investment Account": "Member_1_IRA"},
             {"Account": "Trust (setup name)", "Mapped Investment Account": "Member_1_Trust"},
             {"Account": "Checking", "Mapped Investment Account": ""}]
    names = lc.broker_account_names(setup, {"Trust - Matt": "Trust (setup name)"})
    assert names == {"Member_1_IRA": "IRA - Matt", "Member_1_Trust": "Trust - Matt"}


def test_account_key_ignores_spacing_case_and_symbols():
    assert lc.account_key("Trust  Under Agreement (TRUA)") == lc.account_key("trust under agreement TRUA")
