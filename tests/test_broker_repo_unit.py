"""Plan schema v19: broker activity imports, the broker sale source, and the rebuilt ledger/queue tables."""
import pytest

from src.stores import PlanStore, db
from src.stores.errors import ValidationError
from src.stores.plan_store import PLAN_MIGRATIONS

SALE = dict(sale_date="2026-08-12", account="Member_1_HSA", tax_class="hsa", symbol="TOTL", shares=6.5, proceeds=682.47,
            fees=0.03, basis=600.0, purchase_date="2025-12-30", holding_period="short", gain=None, source="broker")
ROW = dict(row_key="k#0", broker="fidelity", account="Member_1_HSA", run_date="2026-08-12", settle_date="2026-08-13",
           kind="sell", sweep=False, action="YOU SOLD", symbol="TOTL", description="", quantity=-6.0, price=105.0,
           commission=None, fees=0.03, accrued_interest=None, amount=629.97)


@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


def test_v18_plan_upgrades_keeping_sales_and_candidates(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:18])
    con.execute("INSERT INTO realized_sales (sale_date, account, tax_class, symbol, shares, proceeds, basis, holding_period, "
                "source, created_at, updated_at, statement_id) VALUES ('2025-01-02','A','taxable','X',1,1,1,'short','manual','t','t',7)")
    con.execute("INSERT INTO sale_candidates (source, sale_date, account, monarch_id, state, created_at, updated_at) "
                "VALUES ('monarch','2025-01-02','A','m1','dismissed','t','t')")
    con.commit()
    con.close()
    with PlanStore.open(path) as s:
        assert s.schema_version == 19
        assert s.sales.get_sale(1)["statement_id"] == 7
        c = s.sales.list_candidates()[0]
        assert (c["monarch_id"], c["state"], c["broker_key"]) == ("m1", "dismissed", None)
        assert s.sales.insert_sale(**{**SALE, "source": "broker"}) == 2
        assert s.sales.add_candidate(source="monarch", sale_date="2025-01-02", account="A", monarch_id="m1") == (1, False)


def test_broker_candidate_is_idempotent_on_broker_key(store):
    a = store.sales.add_candidate(source="broker", sale_date="2026-08-12", account="Member_1_HSA", symbol="totl", shares=6.5,
                                  amount=682.47, fees=0.03, settle_date="2026-08-13", broker_key="k#0")
    assert a[1] is True
    assert store.sales.add_candidate(source="broker", sale_date="2026-08-12", account="Member_1_HSA", broker_key="k#0") == (a[0], False)
    c = store.sales.list_candidates()[0]
    assert (c["symbol"], c["fees"], c["settle_date"]) == ("TOTL", 0.03, "2026-08-13")
    store.sales.set_candidate_state(a[0], "superseded")
    store.sales.delete_candidate(a[0])
    assert store.sales.list_candidates() == []


def test_confirmed_candidate_cannot_be_deleted(store):
    cid, _ = store.sales.add_candidate(source="broker", sale_date="2026-08-12", account="A", broker_key="x#0")
    store.sales.set_candidate_state(cid, "confirmed", confirmed_sale_ids=[1])
    with pytest.raises(ValidationError):
        store.sales.delete_candidate(cid)


def test_imports_rows_and_keys(store):
    iid = store.broker.add_import(broker="fidelity", account="Member_1_HSA", file_name="f.csv", date_from="2026-01-16",
                                  date_to="2026-09-30", rows_total=3, rows_new=2, summary={"lots_added": 1})
    store.broker.add_rows(iid, [ROW, {**ROW, "row_key": "k#1", "kind": "reinvest", "lot_ref": {"created": True}}])
    assert store.broker.existing_keys(["k#0", "k#9"]) == {"k#0"}
    rows = store.broker.activity(account="Member_1_HSA", year=2026)
    assert [r["kind"] for r in rows] == ["sell", "reinvest"] and rows[1]["lot_ref"] == {"created": True}
    assert store.broker.activity(kinds=["sell"])[0]["sweep"] is False
    with pytest.raises(ValidationError):
        store.broker.add_rows(iid, [ROW])
    assert store.broker.get_import(iid)["summary"] == {"lots_added": 1}
    store.broker.set_import_status(iid, "reverted")
    assert store.broker.delete_import_rows(iid) == 2
    assert store.broker.list_imports(account="Member_1_HSA")[0]["status"] == "reverted"


def test_account_map(store):
    assert store.broker.account_for("fidelity:5678") is None
    store.broker.remember_account("fidelity:5678", "Member_1_HSA")
    store.broker.remember_account("fidelity:5678", "Member_1_Trust")
    assert store.broker.account_for("fidelity:5678") == "Member_1_Trust"
