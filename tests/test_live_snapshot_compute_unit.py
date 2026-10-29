"""Current Snapshot step 3: valuation, grouping, net-of-contribution returns, tax estimate, roll-up.

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
    "ITOT": {"asset_class": "US EQUITY", "style": "Broad Market", "notes": "iShares Core S&P Total U.S. Stock Market ETF"},
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


# ---- the flat lot list the page re-groups ----

def _groups(out, key, only=lambda p: True):
    """Group totals over the lot list with the server's own ``_summarize``: what each row of the page's
    table must show. Shares are over the whole liquid book, as on the page."""
    positions = out["liquid"]["positions"]
    total_current = sum(p["current"] for p in positions)
    total_gain = sum(p["current"] - p["start"] - p["new_money"] for p in positions)
    groups = {}
    for p in positions:
        if only(p):
            groups.setdefault(key(p), []).append(p)
    return {name: ls._summarize(name, ms, total_current, total_gain, out["days"]) for name, ms in groups.items()}


def test_positions_are_one_row_per_lot_with_what_the_page_needs():
    positions = _compute()["liquid"]["positions"]
    assert len(positions) == 4                                  # ITOT, IXUS, AVUV, and the Trust's CASH lot
    itot = next(p for p in positions if p["symbol"] == "ITOT")
    assert itot["account"] == "Member_1_IRA" and itot["asset_class"] == "Equity" and itot["subclass"] == "US Total Equity"
    assert itot["title"] == "iShares Core S&P Total U.S. Stock Market ETF"
    assert (itot["purchase_date"], itot["shares"], itot["purchase_price"], itot["reinvested"]) == ("2025-06-01", 100, 100, False)
    assert (itot["start"], itot["current"], itot["new_money"], itot["day"]) == pytest.approx((12000, 13000, 0, 100))
    cash = next(p for p in positions if p["symbol"] == "CASH")
    assert cash["asset_class"] == "Cash" and cash["subclass"] is None
    assert all(set(p) >= {"account", "symbol", "title", "asset_class", "subclass", "purchase_date", "shares",
                          "purchase_price", "reinvested", "start", "new_money", "weighted", "current", "day"} for p in positions)


def test_lots_sum_to_the_liquid_total():
    out = _compute(lots=LOTS + [{"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2026-10-01", "shares": "10", "purchase_price": "125"}])
    liquid = out["liquid"]
    for k in ("current", "start", "new_money", "day"):
        assert sum(p[k] for p in liquid["positions"]) == pytest.approx(liquid[k]), k
    for key in (lambda p: p["asset_class"], lambda p: p["symbol"], lambda p: p["account"]):
        groups = _groups(out, key)
        assert sum(g["current"] for g in groups.values()) == pytest.approx(liquid["current"])
        assert sum(g["share"] for g in groups.values()) == pytest.approx(1.0)
        assert sum(g["market_gain"] for g in groups.values()) == pytest.approx(liquid["market_gain"])


def test_a_lot_with_no_day_change_stays_null():
    lots = [{**LOTS[0], "symbol": "ZZZZ"}]
    positions = _compute(lots=lots, quotes={"ZZZZ": {"price": 10.0, "previous_close": None, "stale": False}},
                         baseline={**BASELINE, "prices": {"ZZZZ": {"price": 9.0}}})["liquid"]["positions"]
    assert positions[0]["day"] is None


# ---- group totals (the page groups the lot list; these pin the server's formulas on known numbers) ----

def test_class_totals():
    groups = _groups(_compute(), lambda p: p["asset_class"])
    assert sorted(groups) == ["Cash", "Equity"]
    eq = groups["Equity"]
    assert eq["current"] == pytest.approx(31200)
    assert eq["start"] == pytest.approx(24000)               # ITOT + IXUS at 12/31
    assert eq["new_money"] == pytest.approx(4000)            # AVUV
    assert eq["market_gain"] == pytest.approx(3200)
    assert eq["return_pct"] == pytest.approx(3200 / (24000 + 3200))
    assert eq["share"] == pytest.approx(31200 / 32200)
    assert eq["share_of_gain"] == pytest.approx(1.0)
    assert eq["day"] == pytest.approx(100)
    cash = groups["Cash"]
    assert (cash["current"], cash["market_gain"], cash["day"]) == (1000, 0, 0)


def test_equity_subclass_totals():
    groups = _groups(_compute(), lambda p: p["subclass"], only=lambda p: p["subclass"])
    assert {n: g["current"] for n, g in groups.items()} == {"International Equity": 13200, "US Total Equity": 13000, "Small-Cap Value": 5000}


# ---- lots ----
# ITOT is one lot in Member_1_IRA: 100 sh held at 12/31, start 100 x 120 = 12000, now 100 x 130 = 13000.
def test_a_lot_carries_its_account_dates_and_values():
    itot = next(p for p in _compute()["liquid"]["positions"] if p["symbol"] == "ITOT")
    assert itot["account"] == "Member_1_IRA"
    assert (itot["purchase_date"], itot["shares"], itot["purchase_price"], itot["reinvested"]) == ("2025-06-01", 100, 100, False)
    assert (itot["start"], itot["current"]) == pytest.approx((12000, 13000))


def test_fund_name_comes_from_the_security_master_and_is_never_invented():
    positions = _compute()["liquid"]["positions"]
    assert {p["title"] for p in positions if p["symbol"] == "ITOT"} == {"iShares Core S&P Total U.S. Stock Market ETF"}
    assert {p["title"] for p in positions if p["symbol"] == "IXUS"} == {""}


# A second ITOT lot bought 10/1 in the Trust: new money 10 x 125 = 1250, now 10 x 130 = 1300 (< 13000).
def test_same_ticker_in_two_accounts_is_two_lots():
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2026-10-01", "shares": "10", "purchase_price": "125"}]
    itot = [p for p in _compute(lots=lots)["liquid"]["positions"] if p["symbol"] == "ITOT"]
    assert sorted(p["account"] for p in itot) == ["Member_1_IRA", "Member_1_Trust"]
    assert next(p for p in itot if p["account"] == "Member_1_Trust")["new_money"] == pytest.approx(1250)


def test_lot_bought_this_year_is_new_money():
    out = _compute()
    avuv = _groups(out, lambda p: p["symbol"])["AVUV"]
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
    out = _compute(lots=lots, quotes=quotes, baseline=baseline)
    assert out["liquid"]["unclassified_symbols"] == ["ZZZZ"]
    assert _groups(out, lambda p: p["asset_class"])["Other"]["current"] == pytest.approx(110)


def test_cash_tbill_priced_at_par():
    lots = [{"account": "Member_1_Trust", "symbol": "CASH (T-BILL)", "purchase_date": "2026-09-24", "shares": "1000", "purchase_price": "0.99"}]
    out = _compute(lots=lots, quotes={})
    assert out["liquid"]["current"] == pytest.approx(1000)
    assert _groups(out, lambda p: p["asset_class"])["Cash"]["market_gain"] == pytest.approx(10)


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


# ---- reconciliation by account ----
# Member_1_IRA: ITOT 13000 (day +100) + IXUS 13200 (day -50) = 26200, at Monarch's date 26150 vs 26000: +150 (0.58%).
# Member_1_Trust: AVUV 5000 (day +50) + CASH 1000 (day 0) = 6000, at Monarch's date 5950 vs 6000: -50.

def _row_by(rows, account):
    return next(r for r in rows if r["holdings_account"] == account)


def test_accounts_reconcile_and_foot_to_total():
    rec = _compute()["reconciliation"]
    ira, trust = rec["accounts"]                      # |150| before |-50|
    assert (ira["holdings_account"], ira["monarch_accounts"]) == ("Member_1_IRA", ["IRA - Matt"])
    assert ira["holdings_value"] == pytest.approx(26150) and ira["delta"] == pytest.approx(150)
    assert ira["monarch_value"] == pytest.approx(26000) and ira["delta_pct"] == pytest.approx(150 / 26000)
    assert ira["flag"] is False and ira["hints"] == []
    assert trust["delta"] == pytest.approx(-50)
    assert rec["footing"] == pytest.approx(rec["holdings_value"]) == pytest.approx(32100)
    assert rec["unmapped_monarch"] == [] and rec["unmapped_holdings"] == [] and rec["monarch_stale"] is False


def test_flag_needs_both_one_percent_and_100_dollars():
    small = {**MONARCH, "by_account": [dict(a, value=5850.0) if a["account"] == "Trust - Matt" else a for a in MONARCH["by_account"]]}
    trust = _row_by(_compute(monarch=small)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["delta"] == pytest.approx(100) and trust["flag"] is False          # 1.7% but not > $100


def test_matches_position_and_direction_hints():
    # Gap 26150 - 12950 = 13200. IXUS lot at Monarch's date: 200 x 66.25 = 13250 (0.4% off); ITOT 12900 (2.3%).
    m = {**MONARCH, "by_account": [dict(a, value=12950.0) if a["account"] == "IRA - Matt" else a for a in MONARCH["by_account"]]}
    ira = _row_by(_compute(monarch=m)["reconciliation"]["accounts"], "Member_1_IRA")
    assert ira["flag"] is True
    assert ira["hints"] == [
        {"kind": "matches_position", "symbol": "IXUS", "shares": 200, "purchase_date": "2025-06-01", "value": pytest.approx(13250)},
        {"kind": "direction", "higher": "holdings"}]


def test_after_balance_date_and_stale_price_hints():
    # No AVUV quote: priced at the 90 baseline, no day move. Trust = 4500 + 1800 + 1000 = 7300 vs 6000.
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "AVUV", "purchase_date": "2026-10-27", "shares": "20", "purchase_price": "100"}]
    quotes = {k: v for k, v in QUOTES.items() if k != "AVUV"}                      # AVUV falls back to baseline
    trust = _row_by(_compute(lots=lots, quotes=quotes)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["flag"] is True
    assert trust["hints"][0] == {"kind": "after_balance_date", "count": 1, "value": pytest.approx(1800)}
    assert trust["hints"][1] == {"kind": "stale_prices", "symbols": ["AVUV"]}
    assert trust["hints"][-1] == {"kind": "direction", "higher": "holdings"}


def test_lot_bought_on_balance_date_counts_as_included():
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "AVUV", "purchase_date": "2026-10-26", "shares": "20", "purchase_price": "100"}]
    trust = _row_by(_compute(lots=lots)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["flag"] is True                                                    # 7930 vs 6000
    assert all(h["kind"] != "after_balance_date" for h in trust["hints"])


def test_mapped_account_with_no_lots_flags_at_zero():          # Review Focus 2
    lots = [l for l in LOTS if l["account"] != "Member_1_Trust"]
    rec = _compute(lots=lots)["reconciliation"]
    trust = _row_by(rec["accounts"], "Member_1_Trust")
    assert trust["holdings_value"] == 0 and trust["delta"] == pytest.approx(-6000) and trust["flag"] is True
    assert trust["delta_pct"] == pytest.approx(-1.0)
    assert trust["hints"] == [{"kind": "direction", "higher": "monarch"}]
    assert rec["footing"] == pytest.approx(rec["holdings_value"]) == pytest.approx(26150)


def test_both_sides_zero_does_not_divide_or_flag():
    lots = [l for l in LOTS if l["account"] != "Member_1_Trust"]
    m = {**MONARCH, "by_account": [dict(a, value=0.0) if a["account"] == "Trust - Matt" else a for a in MONARCH["by_account"]]}
    trust = _row_by(_compute(lots=lots, monarch=m)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["delta"] == 0 and trust["delta_pct"] is None and trust["flag"] is False and trust["hints"] == []


def test_unmapped_both_ways_and_two_monarch_accounts_to_one():
    accounts = ACCOUNTS + [{"account": "IRA 2 - Matt", "role": "Investment", "mapped_investment_account": "Member_1_IRA"}]
    monarch = {**MONARCH, "by_account": MONARCH["by_account"] + [
        {"account": "IRA 2 - Matt", "type": "Retirement", "value": 100.0},
        {"account": "Old 401k", "type": "Retirement", "value": 900.0}]}
    lots = LOTS + [{"account": "Member_2_Roth", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "1", "purchase_price": "100"}]
    rec = _compute(accounts=accounts, monarch=monarch, lots=lots)["reconciliation"]
    ira = _row_by(rec["accounts"], "Member_1_IRA")
    assert ira["monarch_accounts"] == ["IRA - Matt", "IRA 2 - Matt"] and ira["monarch_value"] == pytest.approx(26100)
    assert rec["unmapped_monarch"] == [{"name": "Old 401k", "value": 900.0}]
    assert rec["unmapped_holdings"] == [{"account": "Member_2_Roth", "value": pytest.approx(129)}]
    assert rec["footing"] == pytest.approx(rec["holdings_value"])


def test_monarch_older_than_previous_session_is_noted():
    assert _compute(monarch={**MONARCH, "latest_date": "2026-10-22"})["reconciliation"]["monarch_stale"] is True


def test_matches_symbol_total_when_no_single_lot_fits():
    # IXUS in two 100-share lots (6625 each at Monarch's date), no ITOT: the gap of 13200 fits neither
    # lot but the symbol's 13250 total, so the hint carries summed shares and no purchase date.
    lots = [l for l in LOTS if l["account"] != "Member_1_IRA"] + [
        {"account": "Member_1_IRA", "symbol": "IXUS", "purchase_date": "2025-06-01", "shares": "100", "purchase_price": "50"},
        {"account": "Member_1_IRA", "symbol": "IXUS", "purchase_date": "2025-07-01", "shares": "100", "purchase_price": "50"}]
    m = {**MONARCH, "by_account": [dict(a, value=50.0) if a["account"] == "IRA - Matt" else a for a in MONARCH["by_account"]]}
    ira = _row_by(_compute(lots=lots, monarch=m)["reconciliation"]["accounts"], "Member_1_IRA")
    assert ira["flag"] is True
    assert ira["hints"][0] == {"kind": "matches_position", "symbol": "IXUS", "shares": 200, "purchase_date": None,
                               "value": pytest.approx(13250)}


def test_monarch_balance_of_zero_flags_on_dollars_alone():
    m = {**MONARCH, "by_account": [dict(a, value=0.0) if a["account"] == "Trust - Matt" else a for a in MONARCH["by_account"]]}
    trust = _row_by(_compute(monarch=m)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["holdings_value"] > 100 and trust["monarch_value"] == 0
    assert trust["delta_pct"] is None and trust["flag"] is True
    assert {"kind": "direction", "higher": "holdings"} in trust["hints"]


def test_monday_with_friday_balances_is_not_stale():
    # 2026-10-26 is a Monday; the previous session was Friday 10-23, so Friday's balances are current.
    rec = _compute(today=date(2026, 10, 26), monarch={**MONARCH, "latest_date": "2026-10-23"})["reconciliation"]
    assert rec["monarch_stale"] is False


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


NOTE_CFG = {"note_items": [{"name": "RedMane Note", "first_payment_year": 2026, "last_payment_year": 2029,
                             "interest_by_year": {2026: 9000.0, 2027: 6000.0, 2028: 4000.0, 2029: 2000.0}}]}


def test_note_receivable_taxes_interest_still_to_come():
    out = _compute(planner_cfg=NOTE_CFG)
    assert _row(out["non_liquid"]["rows"], "RedMane Note Jan 2026")["tax_treatment"] == "note_interest"
    tax = out["tax"]
    assert tax["note_interest"] == pytest.approx(12000)      # 2027-2029: the 2026 payment was in January
    assert tax["note_rows"] == [{"name": "RedMane Note Jan 2026", "note": "RedMane Note", "interest": 12000.0}]
    assert tax["flat_total"] == pytest.approx((26200 + 100000 + 12000) * 0.25 + 1000 * 0.15)
    assert tax["ordinary_tax"] == pytest.approx((26200 + 100000 + 12000) * tax["pre_tax_rate"], rel=1e-3)  # rate shown to 4 dp


def test_note_receivable_interest_capped_at_value_and_override_wins():
    cfg = {"note_items": [{**NOTE_CFG["note_items"][0], "interest_by_year": {2027: 80000.0}}]}
    assert _compute(planner_cfg=cfg)["tax"]["note_interest"] == pytest.approx(50000)
    rates = {**TAX, "non_liquid_tax": {"RedMane Note Jan 2026": "none"}}
    out = _compute(planner_cfg=NOTE_CFG, tax_rates=rates)
    assert _row(out["non_liquid"]["rows"], "RedMane Note Jan 2026")["tax_treatment"] == "none"
    assert out["tax"]["note_interest"] == 0 and out["tax"]["note_rows"] == []


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


# ---- each account compared at its imported balance's own date ----
# Today is Tue 2026-10-27, so the previous session is Mon 10-26 (today's day move backs that out).
# An IRA balance from Thu 10-22 is valued at 10-22's closes: ITOT 100 x 125 + IXUS 200 x 65 = 25,500.

def _monarch_with(ira_value, ira_as_of, trust_as_of="2026-10-26"):
    rows = [dict(r) for r in MONARCH["by_account"]]
    for r in rows:
        if r["account"] == "IRA - Matt":
            r.update(value=ira_value, as_of=ira_as_of)
        if r["account"] == "Trust - Matt":
            r["as_of"] = trust_as_of
    return {**MONARCH, "by_account": rows}


def test_late_sync_is_valued_at_that_days_close_and_does_not_flag():
    closes = {"2026-10-22": {"ITOT": 125.0, "IXUS": 65.0}}
    rec = _compute(monarch=_monarch_with(25700.0, "2026-10-22"), closes_by_day=closes)["reconciliation"]
    ira = next(a for a in rec["accounts"] if a["holdings_account"] == "Member_1_IRA")
    assert ira["holdings_value"] == pytest.approx(25500.0)        # not today's 26,150, which would be 450 (1.75%) apart
    assert ira["delta"] == pytest.approx(-200.0) and ira["flag"] is False
    assert ira["balance_as_of"] == "2026-10-22" and ira["balance_stale"] is True


def test_fresh_balance_keeps_the_day_move_rule_and_says_nothing_about_dates():
    rec = _compute(monarch=_monarch_with(26000.0, "2026-10-26"))["reconciliation"]
    ira = next(a for a in rec["accounts"] if a["holdings_account"] == "Member_1_IRA")
    assert ira["holdings_value"] == pytest.approx(26150.0) and ira["balance_stale"] is False


def test_late_sync_still_flags_a_real_gap_and_names_symbols_with_no_close():
    # No 10-22 close for IXUS: it falls back to today's back-off (13,200 + 50) and is named as an old price.
    closes = {"2026-10-22": {"ITOT": 125.0}}
    rec = _compute(monarch=_monarch_with(24000.0, "2026-10-22"), closes_by_day=closes)["reconciliation"]
    ira = next(a for a in rec["accounts"] if a["holdings_account"] == "Member_1_IRA")
    assert ira["holdings_value"] == pytest.approx(12500.0 + 13250.0)
    assert ira["flag"] is True
    assert {"kind": "stale_prices", "symbols": ["IXUS"]} in ira["hints"]


def test_friday_balance_on_a_saturday_compares_with_fridays_close():
    # Sat 10-31: the latest session is Fri 10-30, which the live quotes already hold, so nothing is backed out.
    rec = _compute(monarch=_monarch_with(26000.0, "2026-10-30", "2026-10-30"), today=date(2026, 10, 31))["reconciliation"]
    ira = next(a for a in rec["accounts"] if a["holdings_account"] == "Member_1_IRA")
    assert ira["holdings_value"] == pytest.approx(26200.0) and ira["balance_stale"] is False


def test_imported_balance_days_lists_only_balances_older_than_the_previous_session():
    assert ls.imported_balance_days(_monarch_with(1.0, "2026-10-22"), TODAY) == [date(2026, 10, 22)]
    assert ls.imported_balance_days(_monarch_with(1.0, "2026-10-26"), TODAY) == []
    assert ls.imported_balance_days(_monarch_with(1.0, "2026-10-24"), TODAY) == [date(2026, 10, 23)]   # a Saturday sync is Friday's close


def test_closes_on_caches_hits_and_retries_misses_later():
    calls, clock = [], [0.0]

    def snapshots(symbols, after, before):
        calls.append(tuple(symbols))
        return {"ITOT": 125.0}

    def closes(symbol, start, end):
        calls.append(symbol)
        return {}

    ls._CLOSES_ON.clear()
    day = date(2026, 10, 22)
    kw = dict(snapshots=snapshots, closes=closes, clock=lambda: clock[0])
    assert ls.closes_on(["ITOT", "IXUS"], day, **kw) == {"ITOT": 125.0}
    assert ls.closes_on(["ITOT", "IXUS"], day, **kw) == {"ITOT": 125.0} and len(calls) == 2    # no refetch
    clock[0] = ls.CLOSES_MISS_RETRY_SECONDS + 1
    ls.closes_on(["ITOT", "IXUS"], day, **kw)
    assert calls[-2:] == [("IXUS",), "IXUS"]                                                       # only the miss retried
    ls._CLOSES_ON.clear()


def test_setup_tax_inputs_and_case_insensitive_lookup(tmp_path):
    from financial_trends_reporter import live_snapshot as ls
    from src import ytd_tracking

    (tmp_path / "input").mkdir()
    ytd_tracking.write_account_setup(tmp_path / "input", [
        {"Account": "Acme Annuity", "Role": "Annuity", "Tax Treatment": "taxed above premium", "After-Tax Premium": "$100,000"},
        {"Account": "Old Pension", "Role": "Pension", "Tax Treatment": "Taxed in full"},
        {"Account": "Checking", "Role": "Cash / spending"},
    ])
    treatment, premium = ls.setup_tax_inputs(tmp_path / "input")
    assert treatment == {"Acme Annuity": "after_tax", "Old Pension": "pre_tax"}
    assert premium == {"Acme Annuity": 100000.0}
    assert ls.non_liquid_tax_treatment("acme annuity", "Annuity/Pension", treatment) == "after_tax"
    assert ls.non_liquid_tax_treatment("Unknown joint", "Annuity/Pension", treatment) == "pre_tax"


def test_setup_tax_inputs_follow_saved_mapping_aliases(tmp_path):
    from financial_trends_reporter import live_snapshot as ls
    from src import ytd_tracking

    (tmp_path / "input").mkdir()
    ytd_tracking.write_account_setup(tmp_path / "input", [
        {"Account": "Plan Annuity", "Role": "Annuity", "Tax Treatment": "Taxed above premium", "After-Tax Premium": "50000"},
    ])
    treatment, premium = ls.setup_tax_inputs(tmp_path / "input", {"Carrier XYZ ****1234": "Plan Annuity"})
    assert treatment["Carrier XYZ ****1234"] == "after_tax"
    assert premium["Carrier XYZ ****1234"] == 50000.0
    assert ls.saved_setup_aliases(tmp_path, tmp_path / "missing.db") == {}


def test_saved_setup_aliases_use_registry_matches(tmp_path, monkeypatch):
    from financial_trends_reporter import live_snapshot as ls, account_registry

    monkeypatch.setattr(account_registry, "list_accounts", lambda db: [
        {"account_key": "k1", "display_name": "Carrier XYZ", "app_account": "Plan Annuity"},
        {"account_key": "k2", "display_name": "Checking", "app_account": ""}])
    assert ls.saved_setup_aliases(tmp_path, tmp_path / "x.db") == {"Carrier XYZ": "Plan Annuity"}


def _planner_cfg():
    from pathlib import Path
    from src.data_io import load_csv, parse_client

    return parse_client(load_csv(Path(__file__).resolve().parent.parent / "input" / "demo" / "client_data.csv"), "", skip_live_pricing=True)


def _positions_for_planner():
    return [
        {"account": "Member_1_401k", "symbol": "VTI", "tax": "pre_tax", "current": 600000.0, "basis": 400000.0},
        {"account": "Member_1_Trust", "symbol": "VTI", "tax": "taxable", "current": 500000.0, "basis": 300000.0},
        {"account": "Member_1_Trust", "symbol": "CASH", "tax": "taxable", "current": 50000.0, "basis": 50000.0},
        {"account": "Member_1_HSA", "symbol": "VTI", "tax": "hsa", "current": 20000.0, "basis": 10000.0},
    ]


def test_planner_tax_uses_the_planners_after_tax_method():
    from datetime import date
    from financial_trends_reporter import live_snapshot as ls
    from src import after_tax

    cfg = _planner_cfg()
    out = ls._planner_tax(cfg, date(2026, 10, 28), 600000.0, _positions_for_planner(),
                          {"pre_tax_rate": 0.25, "ltcg_rate": 0.15, "explicit": []})
    assert out["method"] == "planner" and out["rate_source"] == "planner"
    assert out["pre_tax_rate"] == round(after_tax.resolve_terminal_pretax_rate(cfg, 600000.0, 2026), 4)
    assert out["unrealized_gain"] == 200000.0          # lot basis ratio, cash excluded from gain, no step-up
    assert out["ltcg_tax"] > 0 and out["ltcg_detail"]["federal"] > 0
    assert out["hsa_balance"] == 20000.0 and out["hsa_tax"] == 0.0   # sample HSA goes to a spouse


def test_planner_tax_settings_override():
    from datetime import date
    from financial_trends_reporter import live_snapshot as ls

    rates = {"pre_tax_rate": 0.3, "ltcg_rate": 0.2, "explicit": ["pre_tax_rate", "ltcg_rate"]}
    out = ls._planner_tax(_planner_cfg(), date(2026, 10, 28), 100000.0, _positions_for_planner(), rates)
    assert out["ordinary_tax"] == 30000.0 and out["ltcg_tax"] == 40000.0 and out["rate_source"] == "settings"
