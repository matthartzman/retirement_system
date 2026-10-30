"""Plan schema v18: imported tax statements, their lines, and the per-row pre-correction audit (step 5.2)."""
import pytest

from src.stores import PlanStore, db
from src.stores.errors import NotFoundError, ValidationError
from src.stores.plan_store import PLAN_MIGRATIONS

SALE = dict(sale_date="2025-09-10", account="Trust", tax_class="taxable", symbol="ABCD", shares=10.0, proceeds=1490.0,
            fees=0.0, basis=1400.0, purchase_date="2025-03-04", holding_period="short", gain=90.0, source="manual")
LINE = {"symbol": "ABCD", "date_sold": "2025-09-10", "quantity": 10.0, "proceeds": 1500.0}


@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


def stmt(store, **kw):
    return store.sales.add_statement(**{"broker": "etrade", "account": "Trust", "tax_year": 2025, **kw})


def test_new_plan_is_v18_with_empty_statement_tables(store):
    assert store.schema_version == len(PLAN_MIGRATIONS) == 19
    assert store.sales.list_statements() == []


def test_old_v17_plan_file_upgrades(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:17])
    con.execute("INSERT INTO realized_sales (sale_date, account, tax_class, symbol, shares, proceeds, basis, holding_period, source, created_at, updated_at) "
                "VALUES ('2025-01-02','A','taxable','X',1,1,1,'short','manual','t','t')")
    con.commit()
    con.close()
    with PlanStore.open(path) as s:
        assert s.schema_version == 19
        assert s.sales.get_sale(1)["statement_id"] is None


def test_statement_with_lines_round_trips(store):
    sid = stmt(store, corrected=True, statement_date="2026-02-20", control={"status": "ok"})
    store.sales.add_line(sid, 0, LINE, [3, 4])
    s = store.sales.get_statement(sid)
    assert (s["broker"], s["tax_year"], s["status"], s["corrected"]) == ("etrade", 2025, "applied", 1)
    assert s["statement_date"] == "2026-02-20" and s["control"] == {"status": "ok"}
    assert store.sales.statement_lines(sid) == [{"line_no": 0, "line": LINE, "sale_ids": [3, 4]}]
    assert store.sales.active_statement("etrade", "Trust", 2025)["statement_id"] == sid
    assert store.sales.active_statement("etrade", "Other", 2025) is None


def test_statement_validation(store):
    with pytest.raises(ValidationError):
        stmt(store, broker="")
    with pytest.raises(NotFoundError):
        store.sales.get_statement(99)


def test_correct_sale_updates_fields_and_writes_before_after_audit(store):
    sale = store.sales.insert_sale(**SALE)
    sid = stmt(store)
    store.sales.correct_sale(sale, sid, {"proceeds": 1500.0, "gain": 100.0, "official_proceeds": 1500.0, "holding_period": "long"})
    row = store.sales.get_sale(sale)
    assert (row["proceeds"], row["gain"], row["official_proceeds"], row["holding_period"]) == (1500.0, 100.0, 1500.0, "long")
    (a,) = store.sales.audit(statement_id=sid)
    assert a["action"] == "correct" and a["sale_id"] == sale
    assert a["before"] == {"proceeds": 1490.0, "gain": 90.0, "official_proceeds": None, "holding_period": "short"}
    assert a["after"]["proceeds"] == 1500.0


def test_correct_sale_rejects_unknown_and_invalid_fields(store):
    sale = store.sales.insert_sale(**SALE)
    sid = stmt(store)
    with pytest.raises(ValidationError):
        store.sales.correct_sale(sale, sid, {"symbol": "ZZZ"})
    with pytest.raises(ValidationError):
        store.sales.correct_sale(sale, sid, {"holding_period": "forever"})
    with pytest.raises(ValidationError):
        store.sales.correct_sale(sale, sid, {"sale_date": "09/10/2025"})
    with pytest.raises(NotFoundError):
        store.sales.correct_sale(99, sid, {"proceeds": 1.0})
    assert store.sales.audit() == []


def test_inserted_1099b_sale_carries_its_statement(store):
    sid = stmt(store)
    sale = store.sales.insert_sale(**{**SALE, "source": "1099b", "statement_id": sid})
    store.sales.record_added(sale, sid)
    assert store.sales.get_sale(sale)["statement_id"] == sid
    assert store.sales.audit(sale_id=sale)[0]["action"] == "add"


def test_revert_statement_restores_rows_voids_added_rows_and_marks_superseded(store):
    s1 = store.sales.insert_sale(**SALE)
    sid = stmt(store)
    store.sales.correct_sale(s1, sid, {"proceeds": 1500.0, "gain": 100.0, "official_proceeds": 1500.0})
    store.sales.correct_sale(s1, sid, {"proceeds": 1600.0})            # a second change to the same row
    added = store.sales.insert_sale(**{**SALE, "source": "1099b", "statement_id": sid, "symbol": "NEW"})
    store.sales.record_added(added, sid)
    store.sales.revert_statement(sid)
    row = store.sales.get_sale(s1)
    assert (row["proceeds"], row["gain"], row["official_proceeds"]) == (1490.0, 90.0, None)
    assert store.sales.get_sale(added)["status"] == "voided"
    assert store.sales.get_statement(sid)["status"] == "superseded"
    assert store.sales.active_statement("etrade", "Trust", 2025) is None
    assert [a["action"] for a in store.sales.audit(statement_id=sid)].count("revert") == 3


def test_revert_twice_is_refused(store):
    sid = stmt(store)
    store.sales.revert_statement(sid)
    with pytest.raises(ValidationError):
        store.sales.revert_statement(sid)
