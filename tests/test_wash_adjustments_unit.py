"""Wash-sale basis add-back: recorded apart from the log rows, applied by open_lots and the holdings rewrite."""
from __future__ import annotations

import json

import pytest

from src import active_plan, sales_service, transactions

LOSER, SPOUSE = "Matt_Trust", "Spouse_Trust"
SETUP = [{"Account": "Trust - Matt", "Role": "Investment", "Mapped Investment Account": LOSER},
         {"Account": "Trust - Spouse", "Role": "Investment", "Mapped Investment Account": SPOUSE},
         {"Account": "Roth - Spouse", "Role": "Investment", "Mapped Investment Account": "Spouse_Roth"}]
HOLDINGS = [
    {"account": LOSER, "symbol": "VTI", "purchase_date": "2024-01-10", "shares": "20", "purchase_price": "100", "lot_type": "buy", "note": ""},
    {"account": SPOUSE, "symbol": "BND", "purchase_date": "2024-01-10", "shares": "1", "purchase_price": "70", "lot_type": "buy", "note": ""},
    {"account": "Spouse_Roth", "symbol": "BND", "purchase_date": "2024-01-10", "shares": "1", "purchase_price": "70", "lot_type": "buy", "note": ""}]


def _build(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True) as store:
        store.dataset("ytd_account_setup").replace_all(SETUP)
        store.dataset("holdings").replace_all(HOLDINGS)
    with active_plan.workspace_store(tmp_path, write=True) as store, store.transaction():
        transactions.backfill(store)
    for a in (LOSER, SPOUSE, "Spouse_Roth"):
        transactions.set_managed(tmp_path / "input", a, True)
    return tmp_path


@pytest.fixture()
def ws(tmp_path):
    return _build(tmp_path)


def _sell_loser(ws, shares=20):
    lots = sales_service.open_lots(ws / "input", LOSER, "VTI", "2026-06-10")["lots"]
    lot = lots[0]
    return sales_service.add_sales(ws / "input", [dict(sale_date="2026-06-10", account=LOSER, symbol="VTI", shares=shares, proceeds=shares * 80.0, fees=0.0,
                                                       basis=shares * lot["unit_cost"], purchase_date=lot["purchase_date"], txn_lot=lot["txn_id"])])["ids"]


def _buy(ws, account, shares=20, price=85.0, date="2026-06-15"):
    return transactions.add(ws / "input", txn_date=date, account=account, type="buy", symbol="VTI", shares=shares, price=price, amount=-shares * price)


def _lots(ws, account):
    with active_plan.workspace_store(ws) as store:
        return transactions.open_lots(store, account=account, symbol="VTI")


def test_taxable_replacement_gets_basis_add_back_and_tacked_date(ws):
    _sell_loser(ws)
    _buy(ws, SPOUSE)
    (lot,) = _lots(ws, SPOUSE)
    assert lot["wash_adjustment"] == pytest.approx(400.0)
    assert lot["adjusted_unit_cost"] == pytest.approx(85.0 + 20.0)
    assert lot["tacked_date"] == "2024-01-10" and lot["price"] == 85.0          # the log's own price is unchanged
    with active_plan.workspace_store(ws) as store:
        held = [r for r in store.dataset("holdings").rows() if r["account"] == SPOUSE and r["symbol"] == "VTI"]
        assert float(held[0]["purchase_price"]) == pytest.approx(105.0) and held[0]["purchase_date"] == "2024-01-10"
        assert transactions.reconcile(store) == []                              # the log still agrees with the rewritten holdings


def test_ira_replacement_gets_no_add_back(ws):
    _sell_loser(ws)
    _buy(ws, "Spouse_Roth")
    (lot,) = _lots(ws, "Spouse_Roth")
    assert lot["wash_adjustment"] is None and lot["adjusted_unit_cost"] == 85.0 and lot["tacked_date"] is None


def test_void_of_either_side_recomputes(ws):
    ids = _sell_loser(ws)
    buy = _buy(ws, SPOUSE)
    assert _lots(ws, SPOUSE)[0]["wash_adjustment"] == pytest.approx(400.0)
    transactions.void(ws / "input", buy)                                         # the replacement goes
    assert _lots(ws, SPOUSE) == []
    buy = _buy(ws, SPOUSE)
    assert _lots(ws, SPOUSE)[0]["wash_adjustment"] == pytest.approx(400.0)
    sales_service.void_sale(ws / "input", ids[0])                                # the sale goes: no loss, no add-back
    assert _lots(ws, SPOUSE)[0]["wash_adjustment"] is None


def test_later_sale_of_adjusted_lot_includes_add_back_pro_rata(ws):
    _sell_loser(ws)
    _buy(ws, SPOUSE)
    chooser = sales_service.open_lots(ws / "input", SPOUSE, "VTI", "2026-09-01")["lots"][0]
    assert chooser["unit_cost"] == pytest.approx(105.0) and chooser["purchase_date"] == "2024-01-10" and chooser["term"] == "long"
    row = dict(sale_date="2026-09-01", account=SPOUSE, symbol="VTI", shares=5, proceeds=5 * 90.0, fees=0.0, basis=5 * chooser["unit_cost"],
               purchase_date=chooser["purchase_date"], txn_lot=chooser["txn_id"])
    ids = sales_service.add_sales(ws / "input", [row])["ids"]
    with active_plan.workspace_store(ws) as store:
        sale = store.sales.get_sale(ids[0])
        assert sale["basis"] == pytest.approx(525.0) and sale["gain"] == pytest.approx(-75.0)     # 5 of 20 shares carry a quarter of the add-back
        (rest,) = [l for l in transactions.open_lots(store, account=SPOUSE, symbol="VTI")]
    assert rest["shares"] == 15.0 and rest["wash_adjustment"] == pytest.approx(300.0)


def test_w5_chain_uses_adjusted_cost(ws):
    """The replacement, sold at a loss against its adjusted cost, is itself washed by a later buy: the second loss is measured from 105, not 85."""
    _sell_loser(ws)
    _buy(ws, SPOUSE)
    lot = sales_service.open_lots(ws / "input", SPOUSE, "VTI", "2026-07-01")["lots"][0]
    ids = sales_service.add_sales(ws / "input", [dict(sale_date="2026-07-01", account=SPOUSE, symbol="VTI", shares=20, proceeds=1800.0, fees=0.0,
                                                      basis=20 * lot["unit_cost"], purchase_date=lot["purchase_date"], txn_lot=lot["txn_id"])])["ids"]
    with active_plan.workspace_store(ws) as store:
        assert store.sales.get_sale(ids[0])["gain"] == pytest.approx(1800.0 - 2100.0)           # a $300 loss on adjusted cost (it would be a gain at 85)
    _buy(ws, LOSER, date="2026-07-10", price=88.0)
    (third,) = _lots(ws, LOSER)
    assert third["wash_adjustment"] == pytest.approx(300.0) and third["adjusted_unit_cost"] == pytest.approx(88.0 + 15.0)


def test_log_rows_are_never_edited(ws):
    _sell_loser(ws)
    before = None
    with active_plan.workspace_store(ws) as store:
        before = [dict(r) for r in store.transactions.list(include_voided=True)]
    _buy(ws, SPOUSE)
    with active_plan.workspace_store(ws) as store:
        after = [dict(r) for r in store.transactions.list(include_voided=True)]
        assert store.transactions.wash_adjustments()
    assert after[: len(before)] == before                                         # the earlier rows are untouched; only the new buy was added


def test_plan_with_no_wash_sales_is_byte_identical(ws):
    """RF: with no loss sale nothing is adjusted, so the holdings the log writes equal what they were before the feature."""
    with active_plan.workspace_store(ws) as store:
        before = json.dumps(store.dataset("holdings").rows(), sort_keys=True)
    _buy(ws, SPOUSE, price=85.0, date="2026-06-15")
    transactions.void(ws / "input", transactions_last_buy(ws))
    with active_plan.workspace_store(ws) as store:
        assert store.transactions.wash_adjustments() == []
        assert json.dumps(store.dataset("holdings").rows(), sort_keys=True) == before


def transactions_last_buy(ws):
    with active_plan.workspace_store(ws) as store:
        return max(r["txn_id"] for r in store.transactions.list() if r["type"] == "buy")
