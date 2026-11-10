"""Possible wash-sale detector: rules W1 (same-sale shares are not replacements), W2 (each buy serves one sale), W3 (proportional)."""
from __future__ import annotations

import pytest

from src.stores import PlanStore
from src.stores.errors import NotFoundError, ValidationError
from src.wash_sales import buys_from_rows, detect_wash_sales, plan_flag_updates

KEY = "Brokerage|VTI|2026-06-10"
LOSS = dict(sale_id=1, sale_date="2026-06-10", account="Brokerage", tax_class="taxable", symbol="VTI",
            shares=10.0, gain=-400.0, status="confirmed", wash_flag="none", purchase_date="2025-01-02")


def buy(date, symbol="VTI", shares=10.0, account="Spouse IRA", source="holdings"):
    return dict(date=date, symbol=symbol, shares=shares, account=account, source=source)


def detect(buys, sale=None, **kw):
    return detect_wash_sales([sale or LOSS], buys, **kw)


def test_buy_twelve_days_after_in_another_account_flags_possible():
    out = detect([buy("2026-06-22")], accounts={"Spouse IRA": {"label": "Spouse IRA", "tax_class": "pre_tax"}})
    r = out[KEY]
    assert r["flag"] == "possible" and r["repurchased_shares"] == 10.0 and r["ira"] is True
    assert r["matches"][0]["days"] == 12 and r["matches"][0]["reason"] == "same symbol"
    assert "Loss on VTI; bought VTI 12 days later in Spouse IRA" in r["note"]
    assert "no basis add-back" in r["note"]


def test_taxable_repurchase_has_no_ira_warning():
    out = detect([buy("2026-06-01", account="Joint")], accounts={"Joint": {"tax_class": "taxable"}})
    r = out[KEY]
    assert r["ira"] is False and "9 days earlier in Joint" in r["note"] and "add-back" not in r["note"]


@pytest.mark.parametrize("date,flagged", [("2026-05-11", True), ("2026-05-10", False),
                                          ("2026-07-10", True), ("2026-07-11", False),
                                          ("2026-06-10", True)])
def test_window_is_thirty_days_each_side_inclusive(date, flagged):
    assert (KEY in detect([buy(date)])) is flagged


def test_same_day_buy_says_same_day():
    assert "same day" in detect([buy("2026-06-10")])[KEY]["note"]


@pytest.mark.parametrize("override", [dict(gain=0.0), dict(gain=50.0), dict(gain=None), dict(status="voided"),
                                      dict(tax_class="roth")])
def test_only_confirmed_taxable_losses_are_checked(override):
    assert detect([buy("2026-06-12")], sale=dict(LOSS, **override)) == {}


def test_different_symbol_is_not_flagged_but_an_identical_group_is():
    other = [buy("2026-06-12", symbol="ITOT")]
    assert detect(other) == {}
    out = detect(other, identical_groups={"VTI": "total-us", "ITOT": "total-us"})
    assert out[KEY]["matches"][0]["reason"] == "same group total-us"


def test_the_sold_lots_own_purchase_is_not_a_repurchase():
    sale = dict(LOSS, purchase_date="2026-06-01", account="Brokerage")
    assert detect([buy("2026-06-01", account="Brokerage")], sale=sale) == {}
    # a different account's buy on that date is a real repurchase
    assert KEY in detect([buy("2026-06-01", account="Joint")], sale=sale)


def test_repurchased_shares_sum_and_partial_is_stated():
    out = detect([buy("2026-06-12", shares=3.0), buy("2026-06-20", shares=2.5, account="Joint")])
    r = out[KEY]
    assert r["repurchased_shares"] == 5.5
    assert "5.5 of 10 shares" in r["note"]


def test_symbol_case_is_ignored():
    assert KEY in detect([buy("2026-06-12", symbol="vti")])


def test_buys_from_rows_normalizes_and_filters():
    rows = [
        {"account": "A", "symbol": "vti", "purchase_date": "2026-06-01", "shares": "4", "lot_type": "reinvest"},
        {"account": "A", "symbol": "CASH", "purchase_date": "2026-06-01", "shares": 100},
        {"account": "A", "symbol": "VXUS", "purchase_date": "2026-06-01", "shares": -5},
        {"account": "A", "symbol": "VXUS", "purchase_date": "", "shares": 5},
    ]
    out = buys_from_rows(rows, source="holdings")
    assert out == [dict(date="2026-06-01", symbol="VTI", shares=4.0, account="A", source="holdings", is_reinvest=True)]
    out = buys_from_rows([{"account": "B", "symbol": "X", "date": "2026-02-02", "quantity": 2}], source="monarch")
    assert out[0]["shares"] == 2.0 and out[0]["date"] == "2026-02-02"


def test_plan_flag_updates_sets_clears_and_preserves():
    sales = [dict(LOSS, sale_id=1),
             dict(LOSS, sale_id=2, wash_flag="possible", wash_note="old"),
             dict(LOSS, sale_id=3, wash_flag="confirmed_by_user", wash_note="user"),
             dict(LOSS, sale_id=4, wash_flag="possible", wash_note="same")]
    detected = {KEY: {"flag": "possible", "note": "n1"}}
    sales = [dict(x, sale_id=i) for i, x in enumerate(sales, 1)]
    sales[3] = dict(sales[3], wash_note="n1")
    sales[1] = dict(sales[1], sale_date="2026-07-01")         # a different sale: not detected, so its stale flag clears
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


# ------------------------------------------------------------------------------ Sales Ledger v3 rules W1-W3 (the spec's 2026 numbers)
def lot(sale_id, account, symbol, sale_date, purchase_date, shares, gain, **kw):
    return dict(sale_id=sale_id, sale_date=sale_date, account=account, tax_class="taxable", symbol=symbol, shares=shares, gain=gain,
                status="confirmed", wash_flag="none", purchase_date=purchase_date, **kw)


def test_w1_same_sale_reinvests_are_not_replacements():
    """VGSH and VTEB: the reinvests dated 4-01 were sold on 4-01 in the same sale, so they never count."""
    sales = [lot(1, "Trust", "VGSH", "2026-04-01", "2026-04-01", 2.0, -3.0), lot(2, "Trust", "VGSH", "2026-04-01", "2025-06-01", 98.0, -40.0),
             lot(3, "Trust", "VTEB", "2026-04-01", "2026-04-01", 1.0, -1.0)]
    buys = [buy("2026-04-01", symbol="VGSH", shares=2.0, account="Trust"), buy("2026-04-01", symbol="VTEB", shares=1.0, account="Trust")]
    assert detect_wash_sales(sales, buys) == {}


def test_w3_proportional_disallowance():
    sale = lot(1, "Member_1_Trust", "MUB", "2026-04-01", "2025-05-01", 160.848, -123.61)
    buys = [buy("2026-04-10", symbol="MUB", shares=0.860, account="Spouse_Trust"), buy("2026-04-20", symbol="MUB", shares=0.412, account="Spouse_Trust")]
    r = detect_wash_sales([sale], buys)["Member_1_Trust|MUB|2026-04-01"]
    assert r["loss"] == pytest.approx(123.61)
    assert r["shares_sold"] == pytest.approx(160.848)
    assert r["replacement_shares"] == pytest.approx(1.272)
    assert r["disallowed"] == pytest.approx(0.98, abs=0.005)
    assert r["deductible"] == pytest.approx(122.63, abs=0.005)
    assert sum(m["amount"] for m in r["matches"]) == pytest.approx(r["disallowed"], abs=0.01)


def test_w2_each_buy_serves_one_sale():
    early = lot(1, "Brokerage", "VTI", "2026-06-10", "2025-01-02", 10.0, -100.0)
    late = lot(2, "Brokerage", "VTI", "2026-06-20", "2025-02-02", 10.0, -100.0)
    out = detect_wash_sales([late, early], [buy("2026-06-15", shares=10.0, account="Joint")])
    assert out["Brokerage|VTI|2026-06-10"]["disallowed"] == pytest.approx(100.0)
    assert "Brokerage|VTI|2026-06-20" not in out                      # the earlier sale claimed the only buy


def test_ira_replacement_marks_amount_lost_permanently():
    r = detect([buy("2026-06-12", account="Roth")], accounts={"Roth": {"label": "Roth", "tax_class": "roth"}})[KEY]
    assert r["matches"][0]["taxable"] is False and r["ira"] is True
    assert detect([buy("2026-06-12", account="Joint")], accounts={"Joint": {"tax_class": "taxable"}})[KEY]["matches"][0]["taxable"] is True


def test_not_wash_review_removes_flag():
    assert detect([buy("2026-06-12")], reviews={KEY: {"outcome": "not_wash", "reason": "x"}}) == {}
    assert KEY in detect([buy("2026-06-12")], reviews={KEY: {"outcome": "wash"}})


def test_two_same_day_orders_one_key_do_not_double_count_replacements():
    """RF: two ledger rows of one sale (same day, same account and symbol) are one group; a buy serves it once."""
    a = lot(1, "Brokerage", "VTI", "2026-06-10", "2025-01-02", 4.0, -40.0)
    b = lot(2, "Brokerage", "VTI", "2026-06-10", "2025-03-02", 6.0, -60.0)
    r = detect_wash_sales([a, b], [buy("2026-06-12", shares=10.0)])[KEY]
    assert r["replacement_shares"] == pytest.approx(10.0) and r["disallowed"] == pytest.approx(100.0)
    assert r["sale_ids"] == [1, 2]
    half = detect_wash_sales([a, b], [buy("2026-06-12", shares=5.0)])[KEY]
    assert half["disallowed"] == pytest.approx(50.0)                   # 5 of 10 shares: half the loss, not 5 per row


def test_gain_sales_never_flag():
    assert detect([buy("2026-06-12")], sale=dict(LOSS, gain=250.0)) == {}


def test_w1_a_gain_lots_own_purchase_is_not_a_replacement():
    """Review finding: every lot of the sale is excluded as a replacement, gain lots too."""
    loss = lot(1, "Brokerage", "VTI", "2026-06-10", "2025-01-02", 10.0, -100.0)
    gain = lot(2, "Brokerage", "VTI", "2026-06-10", "2026-06-01", 5.0, 40.0)
    assert detect_wash_sales([loss, gain], [buy("2026-06-01", shares=5.0, account="Brokerage")]) == {}


def test_broker_reported_amount_replaces_ours_and_a_pending_row_gets_no_flag():
    sale = lot(1, "Brokerage", "VTI", "2026-06-10", "2025-01-02", 10.0, -100.0)
    r = detect_wash_sales([sale], [buy("2026-06-12", shares=10.0, account="Brokerage")], reviews={KEY: {"outcome": "broker_reported", "broker_amount": 30.0}})[KEY]
    assert r["disallowed"] == 30.0 and r["deductible"] == 70.0
    other = detect_wash_sales([sale], [buy("2026-06-12", shares=10.0, account="Joint")], reviews={KEY: {"outcome": "broker_reported", "broker_amount": 30.0}})[KEY]
    assert other["disallowed"] == 100.0        # a purchase in another account is on no 1099-B, so ours still counts
    pending = dict(sale, sale_id=2, status="pending")
    detected = detect_wash_sales([sale], [buy("2026-06-12", shares=10.0)])
    assert [u[0] for u in plan_flag_updates([sale, pending], detected)] == [1]
