"""Plan schema v20: the transaction log tables and ``store.transactions``."""
import pytest

from src.stores import PlanStore, db
from src.stores.errors import NotFoundError, ValidationError
from src.stores.plan_store import PLAN_MIGRATIONS

BUY = dict(txn_date="2026-05-12", account="Member_1_IRA", type="buy", symbol="TOTL", shares=10, price=100.0,
           amount=-1000.0, lot_type="buy", source="manual")


@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


def test_migration_from_v19_keeps_existing_data(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:19])
    con.execute("INSERT INTO broker_account_map (file_pattern, account) VALUES ('fidelity:1234', 'Member_1_HSA')")
    con.commit(); con.close()
    with PlanStore.open(path) as s:
        assert s.schema_version == 22 and s.broker.account_for("fidelity:1234") == "Member_1_HSA"
        assert s.transactions.list() == []


def test_type_check_rejects_unknown_type(store):
    with pytest.raises(ValidationError):
        store.transactions.insert(**{**BUY, "type": "gift"})


def test_monarch_source_rejected(store):
    with pytest.raises(ValidationError, match="Monarch"):
        store.transactions.insert(**{**BUY, "source": "monarch"})


@pytest.mark.parametrize("shares", [0, -1, None, "x"])
def test_shares_must_be_positive(store, shares):
    with pytest.raises(ValidationError):
        store.transactions.insert(**{**BUY, "shares": shares})


def test_void_keeps_row_and_disposals_round_trip(store):
    t = store.transactions
    lot = t.insert(**BUY)
    sell = t.insert(**{**BUY, "type": "sell", "shares": 4, "txn_date": "2026-06-01"})
    t.add_disposal(sell, lot, 4)
    assert t.disposals(sell) == [{"lot_txn_id": lot, "shares": 4.0}]
    t.void(sell)
    assert [r["txn_id"] for r in t.list()] == [lot]
    assert [r["status"] for r in t.list(include_voided=True)] == ["active", "voided"]
    with pytest.raises(NotFoundError):
        t.void(999)


def test_list_filters(store):
    t = store.transactions
    t.insert(**BUY)
    t.insert(**{**BUY, "account": "Member_1_HSA", "symbol": "ITOT", "txn_date": "2025-01-02"})
    assert len(t.list(account="Member_1_IRA")) == 1 and len(t.list(symbol="itot")) == 1
    assert len(t.list(year=2025)) == 1 and len(t.list(types=["sell"])) == 0
