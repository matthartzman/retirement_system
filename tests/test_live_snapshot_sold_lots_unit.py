"""Sales ledger 4.1: confirmed ledger sales in the Live Snapshot returns (Modified Dietz).

Window: baseline 2025-12-31 to 2026-10-27 = 300 days. A sale on 2026-09-27 (day 270) leaves 30 days, weight 0.1;
a purchase on 2026-03-01 (day 60) has 240 days left, weight 0.8. Proceeds stay in brokerage cash, so the sale is
a swap inside the account: the lot's group sees the proceeds go out, the Cash group sees the same amount come in
at the same weight, and the total return is the one the sale's gain alone explains.
Remaining holdings: ITOT 100 sh (start 12000, now 13000) and the Trust cash balance 1000 + proceeds, held since 2025-06-01.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import pytest

from financial_trends_reporter import live_snapshot as ls
from tests.test_live_snapshot_compute_unit import BASELINE, MONARCH, SECURITY_MASTER, TAX, TODAY

SALE_DAY = "2026-09-27"
PROCEEDS = 5500.0


def _lots(extra_cash=0.0):
    return [
        {"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "100", "purchase_price": "100"},
        {"account": "Member_1_Trust", "symbol": "CASH", "purchase_date": "2025-06-01", "shares": str(1000 + extra_cash), "purchase_price": "1"},
    ]


QUOTES = {"ITOT": {"price": 130.0, "previous_close": 129.0, "stale": False}}
BASE = {"baseline_date": "2025-12-31", "prices": {"ITOT": {"price": 120.0}, "AVUV": {"price": 90.0}}, "missing": []}


def _sale(**over):
    return {"sale_id": 1, "sale_date": SALE_DAY, "account": "Member_1_Trust", "symbol": "AVUV", "shares": 50.0, "proceeds": PROCEEDS,
            "basis": 4000.0, "purchase_date": "2025-06-01", "status": "confirmed", **over}


def _compute(sales, extra_cash=0.0, lots=None, **kw):
    kw = {"accounts": [], "flows_daily": {}, **kw}
    return ls.compute(lots=lots or _lots(extra_cash), quotes=QUOTES, baseline=BASE, security_master=SECURITY_MASTER,
                      monarch=MONARCH, tax_rates=TAX, today=TODAY, sales=sales, **kw)


def _group(out, **match):
    rows = [p for p in out["liquid"]["positions"] if all(p[k] == v for k, v in match.items())]
    cur, st, nm, w = (sum(p[k] for p in rows) for k in ("current", "start", "new_money", "weighted"))
    gain = cur - st - nm
    return {"gain": gain, "ret": gain / (st + w), "start": st, "new": nm, "weighted": w, "current": cur}


def test_lot_held_at_the_baseline_and_sold():
    # AVUV: start 50 x 90 = 4500, sold for 5500 -> gain 1000 over 4500 - 5500 * 0.1 = 3950.
    out = _compute([_sale()], extra_cash=PROCEEDS)
    liq = out["liquid"]
    # Total: start 12000 + 1000 + 4500, current 13000 + 6500; the sale adds no net new money (-5500 + 5500).
    assert liq["start"] == pytest.approx(17500) and liq["current"] == pytest.approx(19500)
    assert liq["new_money"] == pytest.approx(0)
    assert liq["market_gain"] == pytest.approx(2000)                 # ITOT 1000 + AVUV 1000
    assert liq["return_pct"] == pytest.approx(2000 / 17500)          # weights cancel: unchanged by the swap itself
    avuv = _group(out, symbol="AVUV")
    assert avuv["gain"] == pytest.approx(1000) and avuv["ret"] == pytest.approx(1000 / 3950)
    equity = _group(out, asset_class="Equity")                       # ITOT + AVUV
    assert equity["gain"] == pytest.approx(2000) and equity["ret"] == pytest.approx(2000 / (16500 - 550))
    cash = _group(out, asset_class="Cash")                           # start 1000, now 6500, 5500 came in at weight 0.1
    assert cash["gain"] == pytest.approx(0) and cash["ret"] == pytest.approx(0)
    assert liq["sold"] == {"count": 1}
    assert sum(1 for p in liq["positions"] if p["sold"]) == 2        # the sold lot and its Cash counterpart


def test_lot_bought_and_sold_inside_the_window():
    # Bought 3/1 for 4000 (weight 0.8), sold 9/27 for 5500 (weight 0.1): gain 1500 over 3200 - 550.
    out = _compute([_sale(purchase_date="2026-03-01")], extra_cash=PROCEEDS)
    liq = out["liquid"]
    assert liq["start"] == pytest.approx(13000)
    assert liq["new_money"] == pytest.approx(4000)                   # buy 4000 - proceeds 5500 + cash in 5500
    assert liq["market_gain"] == pytest.approx(2500)                 # ITOT 1000 + 1500
    assert liq["return_pct"] == pytest.approx(2500 / (13000 + 3200))
    avuv = _group(out, symbol="AVUV")
    assert avuv["gain"] == pytest.approx(1500) and avuv["ret"] == pytest.approx(1500 / 2650)
    assert _group(out, asset_class="Cash")["gain"] == pytest.approx(0)


def test_cash_lot_dated_inside_the_window_is_not_counted_twice():
    # The Trust cash is one lot dated 2026-06-01 (day 152) that already holds the proceeds: it is all new money at
    # its own weight, so the Cash row takes nothing out of start. Gain is still ITOT 1000 + AVUV 1000.
    lots = _lots(PROCEEDS)
    lots[1]["purchase_date"] = "2026-06-01"
    out, plain = _compute([_sale()], lots=lots), _compute([], lots=lots)
    liq = out["liquid"]
    assert liq["start"] == pytest.approx(12000 + 4500)
    assert liq["market_gain"] == pytest.approx(2000) and plain["liquid"]["market_gain"] == pytest.approx(1000)
    weights = lambda o: sum(p["weighted"] for p in o["liquid"]["positions"])
    assert weights(out) == pytest.approx(weights(plain))             # proceeds out and in at the same weight
    assert _group(out, asset_class="Cash")["gain"] == pytest.approx(0)


def test_sold_before_the_window_is_excluded():
    plain = _compute([])
    for day in ("2025-11-15", "2025-12-31"):                          # before the baseline close, and on it
        out = _compute([_sale(sale_date=day)])
        assert out["liquid"]["positions"] == plain["liquid"]["positions"]
        assert out["liquid"]["market_gain"] == plain["liquid"]["market_gain"]
        assert out["liquid"]["sold"] == {"count": 0}


def test_scope_start_after_the_sale_excludes_it():
    later = {**BASE, "baseline_date": "2026-09-30"}
    rows, n = ls.sold_lot_rows([_sale()], later, SECURITY_MASTER, date(2026, 9, 30), TODAY)
    assert rows == [] and n == 0


def test_unconfirmed_sales_are_counted_not_estimated():
    plain = _compute([])
    out = _compute([], unconfirmed_dates=[SALE_DAY, "2026-02-02", "2025-11-01"])   # the last is before the window
    assert out["liquid"]["unconfirmed_sales"] == {"count": 2}
    assert out["liquid"]["positions"] == plain["liquid"]["positions"]
    assert out["liquid"]["market_gain"] == plain["liquid"]["market_gain"]


def test_sale_is_not_a_checking_flow():
    accounts = [{"account": "Trust - Matt", "role": "Investment", "mapped_investment_account": "Member_1_Trust"}]
    flows = {"Trust - Matt": {"2026-10-01": {"from_checking": 0.0, "to_checking": 2000.0}}}
    out = _compute([_sale()], extra_cash=PROCEEDS, accounts=accounts, flows_daily=flows)
    assert out["liquid"]["checking_net_flows"] == pytest.approx(-2000)    # only the real transfer; proceeds add nothing


def test_sold_rows_stay_out_of_tax_and_reconciliation_inputs():
    plain, sold = _compute([]), _compute([_sale()], extra_cash=PROCEEDS)
    assert sold["tax"]["unrealized_gain"] == plain["tax"]["unrealized_gain"]
    assert sold["totals"]["gross_assets"] == pytest.approx(plain["totals"]["gross_assets"] + PROCEEDS)  # cash is a holding


def test_cash_account_and_bad_rows_are_skipped():
    rows, n = ls.sold_lot_rows([_sale(account="Family_Checking"), _sale(sale_date="not a date"), _sale(symbol="")],
                               BASE, SECURITY_MASTER, date(2025, 12, 31), TODAY)
    assert rows == [] and n == 0


def test_build_prices_sold_symbols_at_the_baseline(tmp_path):
    from tests.test_live_snapshot_build_unit import INDEX_QUOTES, NOW, FakeQuotes
    import json

    (tmp_path / "baseline_prices_2026.json").write_text(json.dumps({"baseline_date": "2025-12-31", "prices": BASE["prices"]}))
    asked = []
    real = ls.baseline_prices
    ls.baseline_prices = lambda symbols, *a, **k: (asked.append(sorted(symbols)), real(symbols, *a, **k))[1]
    try:
        inputs = {"lots": _lots(), "security_master": SECURITY_MASTER, "accounts": [], "flows_daily": {}, "monarch": MONARCH,
                  "tax_rates": TAX, "log_as_of": "2026-10-26", "sales": [_sale()], "unconfirmed_dates": []}
        out = ls.build(inputs=inputs, quote_cache=FakeQuotes({**QUOTES, **INDEX_QUOTES}), data_dir=tmp_path, now=NOW,
                       previous_close_lookup=lambda symbols, today: {})
    finally:
        ls.baseline_prices = real
    assert asked == [["AVUV", "ITOT"]]
    assert out["liquid"]["sold"] == {"count": 1}
    assert out["baseline_missing"] == []


def test_ledger_sales_reads_the_plan_through_the_workspace_store(tmp_path, monkeypatch):
    from src import active_plan
    from src.stores import PlanStore

    with PlanStore.open(tmp_path / "plan.rpx") as store:
        store.sales.insert_sale(sale_date=SALE_DAY, account="Member_1_Trust", tax_class="taxable", symbol="avuv", shares=50.0,
                                proceeds=PROCEEDS, basis=4000.0, holding_period="long", source="manual")
        voided = store.sales.insert_sale(sale_date=SALE_DAY, account="Member_1_Trust", tax_class="taxable", symbol="IXUS", shares=1.0,
                                         proceeds=1.0, basis=1.0, holding_period="long", source="manual")
        store.sales.void_sale(voided)
        store.sales.add_candidate(source="monarch", sale_date="2026-02-02", account="Member_1_Trust")

        @contextmanager
        def fake(root, *, write=False):
            yield store

        monkeypatch.setattr(active_plan, "workspace_store", fake)
        sales, waiting = ls.ledger_sales(tmp_path)
    assert [s["symbol"] for s in sales] == ["AVUV"] and waiting == ["2026-02-02"]

    def broken(root, *, write=False):
        raise OSError("locked")

    monkeypatch.setattr(active_plan, "workspace_store", broken)
    assert ls.ledger_sales(tmp_path) == ([], [])
