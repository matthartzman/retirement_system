"""Realized-sales ledger step 3a.2: possible wash-sale detector (plan section 8). Flag only, no disallowance."""
from __future__ import annotations

import pytest

from src.stores import PlanStore
from src.stores.errors import NotFoundError, ValidationError
from src.wash_sales import buys_from_rows, detect_wash_sales, plan_flag_updates

LOSS = dict(sale_id=1, sale_date="2026-06-10", account="Brokerage", tax_class="taxable", symbol="VTI",
            shares=10.0, gain=-400.0, status="confirmed", wash_flag="none", purchase_date="2025-01-02")


def buy(date, symbol="VTI", shares=10.0, account="Spouse IRA", source="holdings"):
    return dict(date=date, symbol=symbol, shares=shares, account=account, source=source)


def detect(buys, sale=None, **kw):
    return detect_wash_sales([sale or LOSS], buys, **kw)


def test_buy_twelve_days_after_in_another_account_flags_possible():
    out = detect([buy("2026-06-22")], accounts={"Spouse IRA": {"label": "Spouse IRA", "tax_class": "pre_tax"}})
    r = out[1]
    assert r["flag"] == "possible" and r["repurchased_shares"] == 10.0 and r["ira"] is True
    assert r["matches"][0]["days"] == 12 and r["matches"][0]["reason"] == "same symbol"
    assert "Loss on VTI; bought VTI 12 days later in Spouse IRA" in r["note"]
    assert "no basis add-back" in r["note"]


def test_taxable_repurchase_has_no_ira_warning():
    out = detect([buy("2026-06-01", account="Joint")], accounts={"Joint": {"tax_class": "taxable"}})
    r = out[1]
    assert r["ira"] is False and "9 days earlier in Joint" in r["note"] and "add-back" not in r["note"]


@pytest.mark.parametrize("date,flagged", [("2026-05-11", True), ("2026-05-10", False),
                                          ("2026-07-10", True), ("2026-07-11", False),
                                          ("2026-06-10", True)])
def test_window_is_thirty_days_each_side_inclusive(date, flagged):
    assert (1 in detect([buy(date)])) is flagged


def test_same_day_buy_says_same_day():
    assert "same day" in detect([buy("2026-06-10")])[1]["note"]


@pytest.mark.parametrize("override", [dict(gain=0.0), dict(gain=50.0), dict(gain=None), dict(status="voided"),
                                      dict(tax_class="roth")])
def test_only_confirmed_taxable_losses_are_checked(override):
    assert detect([buy("2026-06-12")], sale=dict(LOSS, **override)) == {}


def test_different_symbol_is_not_flagged_but_an_identical_group_is():
    other = [buy("2026-06-12", symbol="ITOT")]
    assert detect(other) == {}
    out = detect(other, identical_groups={"VTI": "total-us", "ITOT": "total-us"})
    assert out[1]["matches"][0]["reason"] == "same group total-us"


def test_the_sold_lots_own_purchase_is_not_a_repurchase():
    sale = dict(LOSS, purchase_date="2026-06-01", account="Brokerage")
    assert detect([buy("2026-06-01", account="Brokerage")], sale=sale) == {}
    # a different account's buy on that date is a real repurchase
    assert 1 in detect([buy("2026-06-01", account="Joint")], sale=sale)


def test_repurchased_shares_sum_and_partial_is_stated():
    out = detect([buy("2026-06-12", shares=3.0), buy("2026-06-20", shares=2.5, account="Joint")])
    r = out[1]
    assert r["repurchased_shares"] == 5.5
    assert "5.5 of 10 shares" in r["note"]


def test_symbol_case_is_ignored():
    assert 1 in detect([buy("2026-06-12", symbol="vti")])


def test_buys_from_rows_normalizes_and_filters():
    rows = [
        {"account": "A", "symbol": "vti", "purchase_date": "2026-06-01", "shares": "4", "lot_type": "reinvest"},
        {"account": "A", "symbol": "CASH", "purchase_date": "2026-06-01", "shares": 100},
        {"account": "A", "symbol": "VXUS", "purchase_date": "2026-06-01", "shares": -5},
        {"account": "A", "symbol": "VXUS", "purchase_date": "", "shares": 5},
    ]
    out = buys_from_rows(rows, source="holdings")
    assert out == [dict(date="2026-06-01", symbol="VTI", shares=4.0, account="A", source="holdings")]
    out = buys_from_rows([{"account": "B", "symbol": "X", "date": "2026-02-02", "quantity": 2}], source="monarch")
    assert out[0]["shares"] == 2.0 and out[0]["date"] == "2026-02-02"


def test_plan_flag_updates_sets_clears_and_preserves():
    sales = [dict(LOSS, sale_id=1),
             dict(LOSS, sale_id=2, wash_flag="possible", wash_note="old"),
             dict(LOSS, sale_id=3, wash_flag="confirmed_by_user", wash_note="user"),
             dict(LOSS, sale_id=4, wash_flag="possible", wash_note="same")]
    detected = {1: {"flag": "possible", "note": "n1"}, 3: {"flag": "possible", "note": "n3"},
                4: {"flag": "possible", "note": "same"}}
    assert plan_flag_updates(sales, detected) == [(1, "possible", "n1"), (2, "none", "")]


# ------------------------------------------------------------------------------ repo setter
@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


def test_repo_set_wash_flag(store):
    sid = store.sales.insert_sale(sale_date="2026-03-06", account="B", tax_class="taxable", symbol="vti", shares=1.0,
                                  proceeds=10.0, basis=20.0, purchase_date="2025-01-01", holding_period="long",
                                  gain=-10.0, source="manual")
    store.sales.set_wash_flag(sid, "possible", "note")
    row = store.sales.get_sale(sid)
    assert (row["wash_flag"], row["wash_note"]) == ("possible", "note")
    with pytest.raises(ValidationError):
        store.sales.set_wash_flag(sid, "bogus", "")
    with pytest.raises(NotFoundError):
        store.sales.set_wash_flag(999, "none", "")
