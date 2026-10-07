"""WP6.1: flat dataset tables of plan.db (holdings, liabilities, HSA schedule, targets)."""
import pytest

from src.csv_exchange import dataset_csv_text, replace_dataset_from_csv_text
from src.stores import DatasetRepository, PlanStore, ValidationError
from src.stores import db
from src.stores.plan_store import _SCHEMA_V1

HOLDINGS_CSV = (
    "account,symbol,purchase_date,shares,purchase_price,lot_type,note\n"
    "Member_1_IRA,VTI,2020-01-02,\"1,000.5\",$100.25,buy,first lot\n"
    "Member_1_IRA,VXUS,2021-03-04,50,60,buy,\n"
)


@pytest.fixture
def store():
    s = PlanStore.open(":memory:")
    yield s
    s.close()


@pytest.mark.parametrize("name", ["holdings", "liabilities", "hsa_schedule", "target_allocation"])
def test_repositories_satisfy_dataset_protocol(store, name):
    repo = getattr(store, name)
    assert isinstance(repo, DatasetRepository)
    assert repo.rows() == []
    assert repo.count() == 0


def test_csv_round_trip_is_lossless_text(store):
    assert replace_dataset_from_csv_text(store.holdings, "\ufeff" + HOLDINGS_CSV) == 2
    rows = store.holdings.rows()
    assert rows[0]["shares"] == "1,000.5" and rows[0]["purchase_price"] == "$100.25"
    assert [r["symbol"] for r in rows] == ["VTI", "VXUS"]
    assert dataset_csv_text(store.holdings) == HOLDINGS_CSV


def test_replace_all_is_atomic_and_ordered(store):
    store.target_allocation.replace_all([
        {"asset_class": "US Large Cap", "target_pct": "34%"},
        {"asset_class": "Bonds", "target_pct": "66%"},
    ])
    with pytest.raises(ValidationError):
        store.target_allocation.replace_all([{"asset_class": "X", "target_pct": 5}])
    assert [r["asset_class"] for r in store.target_allocation.rows()] == ["US Large Cap", "Bonds"]
    assert store.target_allocation.replace_all([]) == 0
    assert store.target_allocation.rows() == []


def test_missing_values_become_empty_and_blank_lines_skipped(store):
    replace_dataset_from_csv_text(store.hsa_schedule, "year,optimizer_amount\n2030,1000\n,\n")
    assert store.hsa_schedule.rows() == [
        {"year": "2030", "optimizer_amount": "1000", "override_amount": "", "locked": "", "note": ""}
    ]


def test_dataset_writes_join_the_enclosing_transaction(store):
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.liabilities.replace_all([{"liability_id": "L1", "balance": "5000"}])
            raise RuntimeError("roll back")
    assert store.liabilities.rows() == []


def test_v1_file_upgrades_to_v2_keeping_rows(tmp_path):
    p = tmp_path / "old.rpx"
    con = db.connect(str(p))
    db.migrate(con, (_SCHEMA_V1,))
    con.execute("INSERT INTO plan_rows (section, sort_order) VALUES ('Household', 0)")
    con.commit()
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == 2
        assert [r["section"] for r in s.all_rows()] == ["Household"]
        assert s.holdings.rows() == []


def test_extra_columns_survive_the_round_trip(store):
    text = "account,symbol,shares,market_value\nA_IRA,VTI,10,\"1,500\"\n"
    replace_dataset_from_csv_text(store.holdings, text)
    row = store.holdings.rows()[0]
    assert row["market_value"] == "1,500" and row["purchase_price"] == ""
    assert store.holdings.extra_columns() == ["market_value"]
    assert dataset_csv_text(store.holdings).splitlines()[0].endswith("note,market_value")
