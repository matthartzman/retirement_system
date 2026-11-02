"""Transaction log service: replay, add, revise, void (date order, negative positions, named sales)."""
import pytest

from src import active_plan, transactions
from src.sales_ledger import ValidationError


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "input").mkdir()
    with active_plan.workspace_store(tmp_path, write=True):
        pass
    return tmp_path / "input"


def buy(ws, date="2026-01-05", shares=10, **kw):
    return transactions.add(ws, txn_date=date, account="A", type=kw.pop("type", "buy"), symbol="TOTL", shares=shares,
                            price=100.0, lot_type="buy", **kw)


def sell(ws, date, shares, **kw):
    return transactions.add(ws, txn_date=date, account="A", type="sell", symbol="TOTL", shares=shares, price=110.0, **kw)


def lots(ws, **kw):
    with active_plan.workspace_store(ws.parent) as store:
        return transactions.open_lots(store, **kw)


def test_open_lots_replays_buys_and_sells(ws):
    a, b = buy(ws, "2026-01-05", 10), buy(ws, "2026-02-05", 5)
    sell(ws, "2026-03-01", 12)
    assert [(l["lot_txn_id"], l["shares"]) for l in lots(ws)] == [(b, 3.0)]
    assert [l["shares"] for l in lots(ws, as_of="2026-02-10")] == [10.0, 5.0]
    assert a != b


def test_sale_with_too_few_shares_is_refused(ws):
    buy(ws, shares=10)
    with pytest.raises(ValidationError, match="only 10"):
        sell(ws, "2026-03-01", 11)


def test_date_order_independent_of_entry_order(ws):
    buy(ws, "2026-01-05", 10)
    sell(ws, "2026-03-01", 10)
    with pytest.raises(ValidationError):          # back-dated buy after the sale: still fine; a sale before its buy is not
        sell(ws, "2026-01-01", 1)
    buy(ws, "2026-02-01", 5)                       # entered after the sale, dated before it
    assert [l["shares"] for l in lots(ws)] == [5.0]


def test_same_day_buy_counts_before_sale(ws):
    buy(ws, "2026-03-01", 4)
    sell(ws, "2026-03-01", 4)
    assert lots(ws) == []


def test_void_buy_refused_when_later_sale_consumed_it(ws):
    b = buy(ws, shares=10)
    sell(ws, "2026-03-01", 3)
    with pytest.raises(ValidationError, match="undo it in the queue"):
        transactions.void(ws, b)


def test_revise_voids_old_and_links_revision(ws):
    b = buy(ws, shares=10)
    new = transactions.revise(ws, b, shares=12)
    with active_plan.workspace_store(ws.parent) as store:
        assert store.transactions.get(b)["status"] == "voided"
        assert store.transactions.get(new)["revision_ref"] == b
    assert [l["shares"] for l in lots(ws)] == [12.0]


def test_revise_refused_if_lot_goes_negative_later(ws):
    b = buy(ws, shares=10)
    sell(ws, "2026-03-01", 8)
    with pytest.raises(ValidationError, match="more shares"):
        transactions.revise(ws, b, shares=5)
    new = transactions.revise(ws, b, shares=9)      # still covers the sale, which follows the lot
    assert [l["shares"] for l in lots(ws)] == [1.0] and new != b


def test_revise_sale_keeps_allocation_and_refuses_back_dating_before_purchase(ws):
    buy(ws, "2026-02-01", 10)
    s = sell(ws, "2026-03-01", 4)
    transactions.revise(ws, s, price=120.0)
    assert [l["shares"] for l in lots(ws)] == [6.0]
    with pytest.raises(ValidationError):
        transactions.revise(ws, s, txn_date="2026-01-01")


def test_explicit_allocation_and_wrong_symbol_lot(ws):
    a, b = buy(ws, "2026-01-05", 10), buy(ws, "2026-02-05", 10)
    sell(ws, "2026-03-01", 4, allocation={b: 4})
    assert {l["lot_txn_id"]: l["shares"] for l in lots(ws)} == {a: 10.0, b: 6.0}
    other = transactions.add(ws, txn_date="2026-01-05", account="A", type="buy", symbol="ITOT", shares=5, price=1.0)
    with pytest.raises(ValidationError, match="different account or symbol"):
        sell(ws, "2026-03-02", 1, allocation={other: 1})


# ------------------------------------------------------------------------------------------------ transfers
def _plan_with_accounts(ws, accounts=("A", "Member_1_Roth")):
    with active_plan.workspace_store(ws.parent, write=True) as store:
        store.dataset("holdings").replace_all([{"account": a, "symbol": "ZZZ", "purchase_date": "2020-01-01", "shares": "1",
                                                "purchase_price": "1", "lot_type": "buy", "note": ""} for a in accounts])


def test_transfer_preserves_date_price_and_lot_type_and_writes_no_ledger_row(ws):
    _plan_with_accounts(ws)
    a = buy(ws, "2026-01-05", 10)
    out = transactions.transfer(ws, from_account="A", to_account="Member_1_Roth", symbol="TOTL", allocation={a: 4},
                                txn_date="2026-04-01")
    assert [l["shares"] for l in lots(ws, account="A")] == [6.0]
    moved = lots(ws, account="Member_1_Roth")
    assert [(l["shares"], l["purchase_date"], l["price"], l["lot_type"]) for l in moved] == [(4.0, "2026-01-05", 100.0, "buy")]
    assert out["flags"]            # taxable-looking to a Roth: flagged
    with active_plan.workspace_store(ws.parent) as store:
        assert store.sales.list_sales() == [] and store.sales.list_candidates() == []


def test_transfer_more_than_lot_refused_and_nothing_written(ws):
    _plan_with_accounts(ws)
    a = buy(ws, shares=10)
    with pytest.raises(ValidationError, match="more shares"):
        transactions.transfer(ws, from_account="A", to_account="Member_1_Roth", symbol="TOTL", allocation={a: 11}, txn_date="2026-04-01")
    assert [l["shares"] for l in lots(ws)] == [10.0]


def test_transfer_same_or_unknown_account_refused(ws):
    _plan_with_accounts(ws)
    a = buy(ws, shares=10)
    for dest in ("A", "Nowhere"):
        with pytest.raises(ValidationError):
            transactions.transfer(ws, from_account="A", to_account=dest, symbol="TOTL", allocation={a: 1}, txn_date="2026-04-01")


def test_transfer_atomic_when_destination_write_fails(ws, monkeypatch):
    _plan_with_accounts(ws)
    a = buy(ws, shares=10)
    from src.stores.transactions_repo import TransactionsRepo
    real = TransactionsRepo.insert

    def flaky(self, **f):
        if f.get("type") == "transfer_in":
            raise RuntimeError("disk full")
        return real(self, **f)
    monkeypatch.setattr(TransactionsRepo, "insert", flaky)
    with pytest.raises(RuntimeError):
        transactions.transfer(ws, from_account="A", to_account="Member_1_Roth", symbol="TOTL", allocation={a: 4}, txn_date="2026-04-01")
    assert [l["shares"] for l in lots(ws, account="A")] == [10.0]
    with active_plan.workspace_store(ws.parent) as store:
        assert len(store.transactions.list(types=["transfer_out"])) == 0


def test_same_tax_class_transfer_has_no_flag(ws):
    _plan_with_accounts(ws, ("A", "Member_1_Trust"))
    a = buy(ws, shares=10)
    out = transactions.transfer(ws, from_account="A", to_account="Member_1_Trust", symbol="TOTL", allocation={a: 1}, txn_date="2026-04-01")
    assert out["flags"] == []
