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


def test_v1_file_upgrades_to_current_keeping_rows(tmp_path):
    p = tmp_path / "old.rpx"
    con = db.connect(str(p))
    db.migrate(con, (_SCHEMA_V1,))
    con.execute("INSERT INTO plan_rows (section, sort_order) VALUES ('Household', 0)")
    con.commit()
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == 8
        assert [r["section"] for r in s.all_rows()] == ["Household"]
        assert s.holdings.rows() == []


def test_extra_columns_survive_the_round_trip(store):
    text = "account,symbol,shares,market_value\nA_IRA,VTI,10,\"1,500\"\n"
    replace_dataset_from_csv_text(store.holdings, text)
    row = store.holdings.rows()[0]
    assert row["market_value"] == "1,500" and row["purchase_price"] == ""
    assert store.holdings.extra_columns() == ["market_value"]
    assert dataset_csv_text(store.holdings).splitlines()[0].endswith("note,market_value")


# ------------------------------------------------------------ WP6.3a: the spending set
TAXONOMY_CSV = (
    "tracking_type,group,category_id,label,origin,status,notes\n"
    "Core Expenses,Food & Dining,groceries,Groceries,template,active,\"weekly, mostly\"\n"
    "Housing,Mortgage,mortgage,Mortgage,custom,deleted,\n"
)
ALIASES_CSV = (
    "match_value,match_field,exact,priority,category_id,source\n"
    "Groceries,category,1,90,groceries,user\n"
    "WHOLE FOODS,merchant,0,50,groceries,seed\n"
)


def test_v2_file_upgrades_to_v3_with_empty_spending_tables(tmp_path):
    from src.stores.datasets import SCHEMA_V2_DDL
    p = tmp_path / "v2.rpx"
    con = db.connect(str(p))
    db.migrate(con, (_SCHEMA_V1, SCHEMA_V2_DDL))
    con.execute("INSERT INTO holdings_lots (position, account) VALUES (0, 'A_IRA')")
    con.commit()
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == 8
        assert s.holdings.rows()[0]["account"] == "A_IRA"
        assert s.spending.taxonomy.rows() == [] and s.spending.aliases.rows() == []


def test_v3_file_upgrades_to_v4_with_empty_budget_tables(tmp_path):
    from src.stores.datasets import SCHEMA_V2_DDL, SCHEMA_V3_DDL
    p = tmp_path / "v3.rpx"
    con = db.connect(str(p))
    db.migrate(con, (_SCHEMA_V1, SCHEMA_V2_DDL, SCHEMA_V3_DDL))
    con.execute("INSERT INTO spending_aliases (position, match_value, category_id) VALUES (0, 'X', 'groceries')")
    con.commit()
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == 8
        assert s.spending.aliases.rows()[0]["category_id"] == "groceries"
        assert s.spending.budget.rows() == [] and s.spending.budget_lines.rows() == []
        assert s.spending.tier_overrides.rows() == []


def test_budget_tables_round_trip_lossless_with_extra_columns(store):
    budget = "kind,key,label,annual_budget,no_annualize,future_col\ncategory,groceries,Groceries,12000,TRUE,x\n"
    lines = "section,line_id,label,category_id,amount_per_year\ntravel,t1,Trip,travel,5000\n"
    tiers = "category_id,tier,notes\ngroceries,discretionary,\"a, b\"\n"
    for repo, text in ((store.spending.budget, budget), (store.spending.budget_lines, lines),
                       (store.spending.tier_overrides, tiers)):
        assert replace_dataset_from_csv_text(repo, text) == 1
        header = text.splitlines()[0].split(",")
        assert set(header) <= set(repo.columns) | set(repo.extra_columns())
    assert store.spending.budget.extra_columns() == ["future_col"]
    assert store.spending.budget.rows()[0]["future_col"] == "x"
    assert store.spending.tier_overrides.rows()[0]["notes"] == "a, b"
    assert store.dataset("spending_budget").table == "spending_budget"


def test_spending_repo_shape_and_planned_stubs(store):
    from src.stores import SpendingRepository
    from src.stores.spending_repo import PLANNED_SPENDING_DATASETS, SPENDING_DATASETS
    repo = store.spending
    assert isinstance(repo, SpendingRepository)
    for name in SPENDING_DATASETS:
        ds = repo.dataset(name)
        assert isinstance(ds, DatasetRepository) and ds.rows() == []
        assert store.dataset(f"spending_{name}").table == ds.table
    assert repo.taxonomy.columns == ("tracking_type", "group", "category_id", "label", "origin", "status", "notes")
    assert repo.aliases.columns == ("match_value", "match_field", "exact", "priority", "category_id", "source")
    assert repo.budget.columns[:4] == ("kind", "key", "label", "annual_budget")
    assert repo.budget_lines.columns[:2] == ("section", "line_id")
    assert repo.tier_overrides.columns == ("category_id", "tier", "notes")
    assert set(SPENDING_DATASETS) == {"taxonomy", "aliases", "budget", "budget_lines", "tier_overrides",
                                      "rules", "category_map", "group_budget"}
    assert repo.rules.columns == ("keyword", "category_id", "match_field", "exact", "priority")
    assert repo.category_map.columns == ("super_group", "group", "category", "tracking")
    assert repo.group_budget.columns == ("group", "budget_pct", "budget_override", "notes")
    assert PLANNED_SPENDING_DATASETS == {}
    for name, unit in PLANNED_SPENDING_DATASETS.items():
        with pytest.raises(NotImplementedError, match=unit):
            repo.dataset(name)
    with pytest.raises(KeyError):
        repo.dataset("nope")
    with pytest.raises(KeyError):
        store.dataset("spending_nope")


def test_spending_tables_round_trip_lossless_in_file_order(store):
    assert replace_dataset_from_csv_text(store.spending.taxonomy, TAXONOMY_CSV) == 2
    assert replace_dataset_from_csv_text(store.spending.aliases, ALIASES_CSV) == 2
    assert dataset_csv_text(store.spending.taxonomy) == TAXONOMY_CSV
    assert dataset_csv_text(store.spending.aliases) == ALIASES_CSV
    rows = store.spending.taxonomy.rows()
    assert [r["category_id"] for r in rows] == ["groceries", "mortgage"]
    assert rows[0]["group"] == "Food & Dining" and rows[0]["notes"] == "weekly, mostly"


def test_spending_extra_columns_and_transactions(store):
    replace_dataset_from_csv_text(store.spending.aliases, "match_value,category_id,comment\nX,groceries,kept\n")
    assert store.spending.aliases.extra_columns() == ["comment"]
    assert store.spending.aliases.rows()[0]["comment"] == "kept"
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.spending.taxonomy.replace_all([{"category_id": "x"}])
            raise RuntimeError("roll back")
    assert store.spending.taxonomy.rows() == []
    with pytest.raises(ValidationError):
        store.spending.taxonomy.replace_all([{"category_id": 5}])
