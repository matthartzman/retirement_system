"""Live Snapshot step 3: valuation, grouping, net-of-contribution returns, tax estimate, roll-up.

Every expected number below is worked out by hand from the fixture (see the comments), so a
failure means the formula changed, not that a pin drifted.
"""
from __future__ import annotations

from datetime import date

import pytest

from financial_trends_reporter import live_snapshot as ls

TODAY = date(2026, 10, 27)          # 300 days after the 2025-12-31 baseline

LOTS = [
    {"account": "Member_1_IRA", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "100", "purchase_price": "100"},
    {"account": "Member_1_IRA", "symbol": "IXUS", "purchase_date": "2025-06-01", "shares": "200", "purchase_price": "50"},
    {"account": "Member_1_Trust", "symbol": "AVUV", "purchase_date": "2026-03-01", "shares": "50", "purchase_price": "80"},
    {"account": "Member_1_Trust", "symbol": "CASH", "purchase_date": "2026-06-01", "shares": "1000", "purchase_price": "1"},
    {"account": "Family_Checking", "symbol": "CASH", "purchase_date": "2026-06-01", "shares": "5000", "purchase_price": "1"},
]
QUOTES = {
    "ITOT": {"price": 130.0, "previous_close": 129.0, "as_of": "2026-10-27T15:18:04Z", "source": "yahoo_live", "stale": False},
    "IXUS": {"price": 66.0, "previous_close": 66.25, "as_of": "2026-10-27T15:18:04Z", "source": "yahoo_live", "stale": False},
    "AVUV": {"price": 100.0, "previous_close": 99.0, "as_of": "2026-10-27T15:18:04Z", "source": "yahoo_live", "stale": False},
}
BASELINE = {"baseline_date": "2025-12-31", "prices": {"ITOT": {"price": 120.0}, "IXUS": {"price": 60.0}, "AVUV": {"price": 90.0}}, "missing": []}
SECURITY_MASTER = {
    "ITOT": {"asset_class": "US EQUITY", "style": "Broad Market"},
    "IXUS": {"asset_class": "INTERNATIONAL EQUITY", "style": "Broad Market"},
    "AVUV": {"asset_class": "US EQUITY", "style": "Small Value"},
    "CASH": {"asset_class": "CASH", "style": "Cash"},
}
ACCOUNTS = [  # the latest trends-log holdings.by_account rows
    {"account": "IRA - Matt", "role": "Investment", "mapped_investment_account": "Member_1_IRA", "prior_year_end_balance": 23000.0},
    {"account": "Trust - Matt", "role": "Investment", "mapped_investment_account": "Member_1_Trust", "prior_year_end_balance": 2000.0},
    {"account": "Annuity Joint - Matt", "role": "Annuity", "mapped_investment_account": "Member 1 Joint Annuity", "prior_year_end_balance": 0.0},
]
FLOWS = {
    "Trust - Matt": {"2025-12-15": {"from_checking": 9999.0, "to_checking": 0.0},     # before the baseline: ignored
                     "2026-03-01": {"from_checking": 4000.0, "to_checking": 0.0}},    # day 60, weight 0.8
    "IRA - Matt": {"2026-08-28": {"from_checking": 0.0, "to_checking": 1000.0}},      # day 240, weight 0.2
}
MONARCH = {"latest_date": "2026-10-26", "by_account": [
    {"account": "IRA - Matt", "type": "Retirement", "value": 26000.0},
    {"account": "Trust - Matt", "type": "Investment", "value": 6000.0},
    {"account": "Joint Annuity - Matt", "type": "Annuity/Pension", "value": 100000.0},
    {"account": "Home", "type": "Real estate", "value": 500000.0},
    {"account": "RedMane Note Jan 2026", "type": "Other", "value": 50000.0},
    {"account": "Art", "type": "Other", "value": 5000.0},
    {"account": "Family Checking", "type": "Cash", "value": 7000.0},
    {"account": "Mortgage 1.99% 7/34", "type": "Loan", "value": -200000.0},
    {"account": "Platinum Card", "type": "Credit card", "value": -1000.0},
]}
TAX = {"pre_tax_rate": 0.25, "ltcg_rate": 0.15}


def _compute(**over):
    kw = dict(lots=LOTS, quotes=QUOTES, baseline=BASELINE, security_master=SECURITY_MASTER, accounts=ACCOUNTS,
              flows_daily=FLOWS, monarch=MONARCH, tax_rates=TAX, today=TODAY)
    kw.update(over)
    return ls.compute(**kw)


def _row(rows, name):
    return next(r for r in rows if r["name"] == name)


# ---- liquid totals: Modified Dietz over the lots ----
# Held at 12/31: ITOT 100 x 120 + IXUS 200 x 60 = 24000 (start).
# New money: AVUV 4000 on 3/1 (day 60, weight 240/300 = 0.8); CASH 1000 on 6/1 (day 152, weight 148/300).
# Gain = 32200 - 24000 - 5000 = 3200; return = 3200 / (24000 + 3200 + 1000 * 148/300).
DENOM = 24000 + 3200 + 1000 * 148 / 300


def test_liquid_totals():
    liquid = _compute()["liquid"]
    assert liquid["current"] == pytest.approx(32200)          # 13000 + 13200 + 5000 + 1000; checking lot excluded
    assert liquid["start"] == pytest.approx(24000)
    assert liquid["new_money"] == pytest.approx(5000)
    assert liquid["market_gain"] == pytest.approx(3200)
    assert liquid["return_pct"] == pytest.approx(3200 / DENOM)
    assert liquid["annualized_pct"] == pytest.approx((1 + 3200 / DENOM) ** (365 / 300) - 1)
    assert liquid["day"] == pytest.approx(100)                # ITOT +100, IXUS -50, AVUV +50
    assert liquid["day_pct"] == pytest.approx(100 / 32100)


def test_checking_flows_are_informational():
    # +4000 contribution - 1000 withdrawal through checking, mapped accounts only, after 12/31
    assert _compute()["liquid"]["checking_net_flows"] == pytest.approx(3000)
    assert _compute(accounts=[])["liquid"]["checking_net_flows"] is None


def test_reinvested_dividend_counts_as_gain_not_new_money():
    lots = LOTS + [{"account": "Member_1_IRA", "symbol": "ITOT", "purchase_date": "2026-04-01", "shares": "2",
                    "purchase_price": "125", "lot_type": "reinvestment"}]
    liquid = _compute(lots=lots)["liquid"]
    assert liquid["new_money"] == pytest.approx(5000)
    assert liquid["market_gain"] == pytest.approx(3200 + 260)


# ---- groupings ----

def test_by_class():
    rows = _compute()["liquid"]["by_class"]
    assert [r["name"] for r in rows] == ["Equity", "Cash"]
    eq = _row(rows, "Equity")
    assert eq["current"] == pytest.approx(31200)
    assert eq["start"] == pytest.approx(24000)               # ITOT + IXUS at 12/31
    assert eq["new_money"] == pytest.approx(4000)            # AVUV
    assert eq["market_gain"] == pytest.approx(3200)
    assert eq["return_pct"] == pytest.approx(3200 / (24000 + 3200))
    assert eq["share"] == pytest.approx(31200 / 32200)
    assert eq["share_of_gain"] == pytest.approx(1.0)
    assert eq["day"] == pytest.approx(100)
    assert [t["symbol"] for t in eq["tickers"]] == ["IXUS", "ITOT", "AVUV"]   # largest first
    cash = _row(rows, "Cash")
    assert (cash["current"], cash["market_gain"], cash["day"]) == (1000, 0, 0)


def test_by_equity_subclass():
    rows = _compute()["liquid"]["by_equity_subclass"]
    assert [(r["name"], r["current"]) for r in rows] == [
        ("International Equity", 13200), ("US Total Equity", 13000), ("Small-Cap Value", 5000)]


def test_lot_bought_this_year_is_new_money():
    avuv = next(t for t in _row(_compute()["liquid"]["by_class"], "Equity")["tickers"] if t["symbol"] == "AVUV")
    assert (avuv["start"], avuv["new_money"]) == (0, 4000)
    assert avuv["market_gain"] == pytest.approx(1000)
    assert avuv["return_pct"] == pytest.approx(1000 / 3200)


# ---- degraded inputs ----

def test_missing_quote_uses_baseline_and_is_listed():
    quotes = {k: v for k, v in QUOTES.items() if k != "IXUS"}
    liquid = _compute(quotes=quotes)["liquid"]
    assert liquid["stale_symbols"] == ["IXUS"]
    assert liquid["current"] == pytest.approx(32200 - 13200 + 12000)


def test_unclassified_symbol_goes_to_other():
    lots = LOTS + [{"account": "Member_1_IRA", "symbol": "ZZZZ", "purchase_date": "2025-01-01", "shares": "10", "purchase_price": "10"}]
    quotes = {**QUOTES, "ZZZZ": {"price": 11.0, "previous_close": 11.0, "stale": False}}
    baseline = {**BASELINE, "prices": {**BASELINE["prices"], "ZZZZ": {"price": 10.0}}}
    liquid = _compute(lots=lots, quotes=quotes, baseline=baseline)["liquid"]
    assert liquid["unclassified_symbols"] == ["ZZZZ"]
    assert _row(liquid["by_class"], "Other")["current"] == pytest.approx(110)


def test_cash_tbill_priced_at_par():
    lots = [{"account": "Member_1_Trust", "symbol": "CASH (T-BILL)", "purchase_date": "2026-09-24", "shares": "1000", "purchase_price": "0.99"}]
    liquid = _compute(lots=lots, quotes={})["liquid"]
    assert liquid["current"] == pytest.approx(1000)
    assert _row(liquid["by_class"], "Cash")["market_gain"] == pytest.approx(10)


def test_annualized_hidden_in_first_90_days():
    assert _compute(today=date(2026, 3, 1))["liquid"]["annualized_pct"] is None


# ---- reconciliation with Monarch ----

def test_reconciliation_compares_previous_close_value_with_monarch():
    rec = _compute()["reconciliation"]
    assert rec["monarch_value"] == pytest.approx(32000)      # Retirement + Investment (+ HSA) types
    assert rec["holdings_value"] == pytest.approx(32100)     # live value at the previous close: Monarch is yesterday's
    assert rec["delta_pct"] == pytest.approx(100 / 32000)
    assert rec["flag"] is False


def test_reconciliation_flags_over_one_percent():
    monarch = {**MONARCH, "by_account": [dict(a, value=30000.0) if a["account"] == "IRA - Matt" else a for a in MONARCH["by_account"]]}
    assert _compute(monarch=monarch)["reconciliation"]["flag"] is True


# ---- non-liquid, debt, tax, totals ----

def test_non_liquid_rows_and_kinds():
    nl = _compute()["non_liquid"]
    assert [(r["name"], r["kind"], r["value"]) for r in nl["rows"]] == [
        ("Home", "Real Estate", 500000), ("Joint Annuity - Matt", "Fixed Income", 100000),
        ("RedMane Note Jan 2026", "Fixed Income", 50000), ("Art", "Alternatives", 5000)]
    assert nl["total"] == pytest.approx(655000)
    assert nl["as_of"] == "2026-10-26"


def test_debt_and_checking():
    out = _compute()
    assert [(r["name"], r["value"]) for r in out["debt"]["rows"]] == [("Mortgage 1.99% 7/34", 200000), ("Platinum Card", 1000)]
    assert out["debt"]["total"] == pytest.approx(201000)
    assert out["checking"]["total"] == pytest.approx(7000)


def test_tax_estimate():
    tax = _compute()["tax"]
    assert tax["pre_tax_balance"] == pytest.approx(26200)    # IRA holdings
    assert tax["pre_tax_non_liquid"] == pytest.approx(100000)  # joint annuity: IRA-funded
    assert tax["unrealized_gain"] == pytest.approx(1000)     # AVUV 5000 - 4000 basis; cash none
    assert tax["total"] == pytest.approx((26200 + 100000) * 0.25 + 1000 * 0.15)


ANNUITIES = {"latest_date": "2026-10-26", "by_account": [
    {"account": "Joint Annuity - Pat", "type": "Annuity/Pension", "value": 400000.0},
    {"account": "Annuity - Matt - Dec 2025", "type": "Annuity/Pension", "value": 160000.0},
    {"account": "Annuity - Pat - PV 6/1/26", "type": "Annuity/Pension", "value": 50000.0},
    {"account": "Pension - Pat - June 2026", "type": "Annuity/Pension", "value": 95000.0},
]}


def test_annuity_and_pension_tax_treatment():
    rates = {**TAX, "annuity_basis": {"Annuity - Matt - Dec 2025": 120000}}
    out = _compute(lots=[], monarch=ANNUITIES, tax_rates=rates)
    treatment = {r["name"]: r["tax_treatment"] for r in out["non_liquid"]["rows"]}
    assert treatment == {"Joint Annuity - Pat": "pre_tax", "Annuity - Matt - Dec 2025": "after_tax",
                         "Annuity - Pat - PV 6/1/26": "after_tax", "Pension - Pat - June 2026": "pre_tax"}
    tax = out["tax"]
    assert tax["pre_tax_non_liquid"] == pytest.approx(495000)          # joint annuity + pension, full value
    assert tax["annuity_taxable_gain"] == pytest.approx(40000)         # after-tax annuity: value - basis only
    assert tax["basis_missing"] == ["Annuity - Pat - PV 6/1/26"]       # no basis set: not taxed, listed
    assert tax["total"] == pytest.approx((495000 + 40000) * 0.25)


def test_tax_treatment_override_and_basis_above_value():
    rates = {**TAX, "non_liquid_tax": {"Joint Annuity - Pat": "none"},
             "annuity_basis": {"Annuity - Matt - Dec 2025": 200000, "Annuity - Pat - PV 6/1/26": 50000}}
    tax = _compute(lots=[], monarch=ANNUITIES, tax_rates=rates)["tax"]
    assert tax["pre_tax_non_liquid"] == pytest.approx(95000)
    assert tax["annuity_taxable_gain"] == 0 and tax["basis_missing"] == []


def test_totals():
    totals = _compute()["totals"]
    assert totals["net_assets"] == pytest.approx(32200 + 7000 + 655000 - 201000)
    assert totals["after_tax_net_worth"] == pytest.approx(493200 - 6700 - 25000)
    assert totals["by_kind"] == pytest.approx({"Equity": 31200, "Fixed Income": 150000, "Real Estate": 500000,
                                               "Alternatives": 5000, "Cash": 8000})


def test_without_monarch_only_liquid_and_tax():
    out = _compute(monarch=None)
    assert out["non_liquid"]["rows"] == [] and out["debt"]["total"] == 0
    assert out["reconciliation"] is None
    assert out["totals"]["after_tax_net_worth"] == pytest.approx(32200 - 6700)
