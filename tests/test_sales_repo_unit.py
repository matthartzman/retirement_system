"""Realized-sales ledger tables (plan schema v17): ``SalesRepo``, reached as ``store.sales``."""
import pytest

from src.stores import PlanStore, db
from src.stores.errors import NotFoundError, ValidationError
from src.stores.plan_store import PLAN_MIGRATIONS

SALE = dict(sale_date="2026-03-06", account="Brokerage", tax_class="taxable", symbol="vti", shares=10.0,
            proceeds=2500.0, fees=1.0, basis=2000.0, purchase_date="2025-03-05", holding_period="long",
            gain=499.0, source="manual")


@pytest.fixture
def store(tmp_path):
    with PlanStore.open(tmp_path / "plan.rpx") as s:
        yield s


def test_new_plan_has_empty_ledger_tables(store):
    assert store.schema_version == len(PLAN_MIGRATIONS) == 17
    assert store.sales.list_sales(include_voided=True) == []
    assert store.sales.list_candidates() == []
    assert store.sales.adjustments() == []


def test_insert_sale_uppercases_symbol_and_defaults(store):
    sid = store.sales.insert_sale(**SALE)
    row = store.sales.get_sale(sid)
    assert row["symbol"] == "VTI" and row["status"] == "confirmed" and row["wash_flag"] == "none"
    assert row["created_at"] and row["official_proceeds"] is None


def test_insert_sale_validates(store):
    with pytest.raises(ValidationError):
        store.sales.insert_sale(**{**SALE, "source": "guess"})
    with pytest.raises(ValidationError):
        store.sales.insert_sale(**{**SALE, "sale_date": "03/06/2026"})
    with pytest.raises(ValidationError):
        store.sales.insert_sale(**{**SALE, "shares": 0})
    with pytest.raises(ValidationError):
        store.sales.insert_sale(**{**SALE, "tax_class": "bogus"})


def test_non_taxable_sale_has_no_gain(store):
    sid = store.sales.insert_sale(**{**SALE, "tax_class": "roth", "gain": None, "holding_period": "long"})
    assert store.sales.get_sale(sid)["gain"] is None


def test_void_and_unvoid_never_delete(store):
    a = store.sales.insert_sale(**SALE)
    b = store.sales.insert_sale(**{**SALE, "sale_date": "2025-12-31"})
    store.sales.void_sale(a)
    assert [r["sale_id"] for r in store.sales.list_sales()] == [b]
    assert {r["sale_id"] for r in store.sales.list_sales(include_voided=True)} == {a, b}
    store.sales.unvoid_sale(a)
    assert {r["sale_id"] for r in store.sales.list_sales()} == {a, b}
    with pytest.raises(NotFoundError):
        store.sales.void_sale(999)


def test_list_sales_filters_by_tax_year(store):
    store.sales.insert_sale(**SALE)
    store.sales.insert_sale(**{**SALE, "sale_date": "2025-12-31"})
    assert [r["sale_date"] for r in store.sales.list_sales(year=2026)] == ["2026-03-06"]


def test_candidate_insert_is_idempotent_on_monarch_id(store):
    cand = dict(source="monarch", sale_date="2026-03-07", account="Brokerage", symbol="VTI", shares=10.0,
                price=250.0, amount=2500.0, monarch_id="m-1")
    first, created = store.sales.add_candidate(**cand)
    again, created2 = store.sales.add_candidate(**{**cand, "amount": 9.0})
    assert created and not created2 and first == again
    assert len(store.sales.list_candidates()) == 1
    assert store.sales.list_candidates()[0]["amount"] == 2500.0  # the first row wins
    assert store.sales.list_candidates()[0]["state"] == "unmatched"


def test_candidates_without_monarch_id_are_not_deduplicated(store):
    c = dict(source="holdings_diff", sale_date="2026-03-07", account="Brokerage", symbol="VTI", shares=1.0)
    store.sales.add_candidate(**c)
    store.sales.add_candidate(**c)
    assert len(store.sales.list_candidates()) == 2


def test_candidate_state_changes_and_filter(store):
    cid, _ = store.sales.add_candidate(source="monarch", sale_date="2026-03-07", account="B", monarch_id="m-2")
    store.sales.set_candidate_state(cid, "confirmed", confirmed_sale_ids=[4, 5])
    assert store.sales.list_candidates(state="unmatched") == []
    row = store.sales.list_candidates(state="confirmed")[0]
    assert row["confirmed_sale_ids"] == [4, 5]
    with pytest.raises(ValidationError):
        store.sales.set_candidate_state(cid, "weird")
    with pytest.raises(NotFoundError):
        store.sales.set_candidate_state(999, "dismissed")


def test_adjustments_one_row_per_year(store):
    store.sales.set_adjustment(2026, carryforward_short=1000.0, carryforward_long=5000.0)
    store.sales.set_adjustment(2026, carryforward_short=1200.0, carryforward_long=5000.0, state_rate_override=0.05)
    rows = store.sales.adjustments()
    assert len(rows) == 1 and rows[0]["carryforward_short"] == 1200.0 and rows[0]["state_rate_override"] == 0.05
    assert store.sales.adjustment(2027) is None


def test_ledger_survives_revision_restore(store):
    """Restoring a plan revision rewrites plan rows, flat datasets and rental only. A sale recorded after the
    snapshot (and one recorded before it) both stay."""
    before = store.sales.insert_sale(**SALE)
    rev = store.snapshot_revision("manual", "before")
    after = store.sales.insert_sale(**{**SALE, "sale_date": "2026-04-01"})
    store.sales.add_candidate(source="monarch", sale_date="2026-03-07", account="B", monarch_id="m-3")
    store.restore_revision(rev)
    assert [r["sale_id"] for r in store.sales.list_sales()] == [before, after]
    assert len(store.sales.list_candidates()) == 1


def test_old_plan_file_is_upgraded_with_empty_ledger(tmp_path):
    path = tmp_path / "old.rpx"
    con = db.connect(path)
    db.migrate(con, PLAN_MIGRATIONS[:16])
    con.close()
    with PlanStore.open(path) as s:
        assert s.schema_version == 17
        assert s.sales.list_sales(include_voided=True) == []
        sid = s.sales.insert_sale(**SALE)
        assert s.sales.get_sale(sid)["symbol"] == "VTI"
