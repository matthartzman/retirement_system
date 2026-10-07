"""WP6.3a: the spending taxonomy and aliases live in plan.db tables (``store.spending``);
conversion step C4b fills them from the legacy files; the spending readers and writers, the
import preview, the generic plan-data file routes and the at-rest category renames all use the
active plan's tables, never the workspace files."""
import csv
import io

import pytest

from src import spending_tracker as st
from src.csv_exchange import dataset_csv_text
from src.legacy_conversion.steps import c4b_spending
from src.stores import PlanStore
from tests.plan_fixture import fixture_dir, make_plan, plan_dataset_rows, write_plan_dataset

TAXONOMY = "client_spending_taxonomy.csv"
ALIASES = "client_spending_aliases.csv"


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A fixture plan that is the live workspace's active plan."""
    plan = make_plan(tmp_path / "ws")
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(plan.root))
    monkeypatch.delenv("RETIREMENT_SYSTEM_PLAN_DB", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_BASE_DIR", raising=False)
    return plan


# ----------------------------------------------------------------------- conversion C4b
def test_c4b_converts_the_fixture_files_cell_for_cell_and_is_idempotent(tmp_path):
    src = fixture_dir("sample_frozen")
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4b_spending.run(src, store)
        assert not report.skipped and not report.legacy_taxonomy_layout and not report.aliases_ignored
        for name, file in c4b_spending.FILES.items():
            want = _csv_rows(src / file)
            repo = store.spending.dataset(name)
            assert repo.count() == len(want) == report.rows_written[name]
            got = list(csv.DictReader(io.StringIO(dataset_csv_text(repo))))
            assert [{k: r[k] for k in w} for r, w in zip(got, want)] == want
        assert store.get_meta(c4b_spending.MARKER_KEY)
        assert store.holdings.count() == 0  # C4a's datasets are not this step's
        store.spending.aliases.replace_all([])
        assert c4b_spending.run(src, store).skipped
        assert store.spending.aliases.count() == 0  # a second run changes nothing


def test_c4b_missing_files_leave_tables_empty(tmp_path):
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4b_spending.run(tmp_path / "nothing_here", store)
        assert report.rows_written == {} and store.spending.taxonomy.count() == 0
        assert store.get_meta(c4b_spending.MARKER_KEY) == "rows="


def test_c4b_converts_the_legacy_taxonomy_layout_as_the_old_reader_read_it(tmp_path):
    (tmp_path / TAXONOMY).write_text(
        "section,subsection,label,value,notes\n"
        "Core Expenses,Food & Dining,groceries,Groceries,weekly\n"
        "Housing,,mortgage,,\n", encoding="utf-8")
    with PlanStore.open(tmp_path / "plan.rpx") as store:
        report = c4b_spending.run(tmp_path, store)
        assert report.legacy_taxonomy_layout
        rows = store.spending.taxonomy.rows()
    assert [(r["tracking_type"], r["group"], r["category_id"], r["label"], r["origin"], r["status"], r["notes"])
            for r in rows] == [("Core Expenses", "Food & Dining", "groceries", "Groceries", "template", "active", "weekly"),
                               ("Housing", "", "mortgage", "", "template", "active", "")]
    flat = st.taxonomy_flat(tmp_path)
    assert flat["groceries"]["group"] == "Food & Dining" and flat["groceries"]["origin"] == "template"
    assert flat["mortgage"]["label"] == "mortgage" and flat["mortgage"]["tracking_type"] == "Housing"


def test_c4b_ignores_an_aliases_file_the_old_reader_ignored(tmp_path):
    (tmp_path / ALIASES).write_text("keyword,category_id\nWHOLE FOODS,groceries\n", encoding="utf-8")
    with PlanStore.open(tmp_path / "plan.rpx") as store:
        report = c4b_spending.run(tmp_path, store)
        assert report.aliases_ignored and store.spending.aliases.count() == 0


# ------------------------------------------------------------------ readers and writers
def test_spending_readers_follow_the_active_plan_tables_not_the_files(ws):
    want = [r["category_id"] for r in _csv_rows(ws.input_dir / TAXONOMY) if r["status"] != "deleted"]
    (ws.input_dir / TAXONOMY).unlink()
    (ws.input_dir / ALIASES).unlink()
    flat = st.taxonomy_flat(ws.root)
    assert sorted(flat) == sorted(set(want))
    assert st.load_aliases(ws.root)  # the fixture's aliases, from the plan file
    assert st.taxonomy_flat() == flat  # root=None is the live workspace -> the active plan

    write_plan_dataset(ws.root, TAXONOMY, "tracking_type,group,category_id,label,origin,status,notes\n"
                                          "Travel,Travel,only_one,Only One,custom,active,\n")
    assert list(st.taxonomy_flat(ws.root)) == ["only_one"]


def test_an_explicit_plan_db_override_is_the_one_read(ws, tmp_path, monkeypatch):
    other = tmp_path / "other.rpx"
    with PlanStore.open(other) as store:
        store.spending.taxonomy.replace_all([{"tracking_type": "Travel", "group": "Travel",
                                              "category_id": "elsewhere", "label": "Elsewhere"}])
    monkeypatch.setenv("RETIREMENT_SYSTEM_PLAN_DB", str(other))
    assert list(st.taxonomy_flat(ws.root)) == ["elsewhere"]


def test_taxonomy_and_alias_writes_go_to_the_plan_tables(ws):
    before = (ws.input_dir / TAXONOMY).read_bytes(), (ws.input_dir / ALIASES).read_bytes()
    st.save_taxonomy_category(ws.root, "Travel", "Travel", "new_cat", "New Category")
    st.add_alias(ws.root, "NEW MERCHANT", "new_cat", match_field="merchant", exact=False, priority=95)
    assert ((ws.input_dir / TAXONOMY).read_bytes(), (ws.input_dir / ALIASES).read_bytes()) == before
    rows = plan_dataset_rows(ws.root, TAXONOMY)
    assert any(r["category_id"] == "new_cat" and r["label"] == "New Category" and r["origin"] == "custom" for r in rows)
    alias = [r for r in plan_dataset_rows(ws.root, ALIASES) if r["match_value"] == "NEW MERCHANT"]
    assert alias == [{"match_value": "NEW MERCHANT", "match_field": "merchant", "exact": "0",
                      "priority": "95", "category_id": "new_cat", "source": "user"}]
    assert st.delete_taxonomy_category(ws.root, "new_cat")
    assert "new_cat" not in st.taxonomy_flat(ws.root) and "new_cat" in st.taxonomy_flat(ws.root, include_deleted=True)


def test_a_root_without_a_plan_file_reads_empty_and_a_write_creates_it(tmp_path):
    assert st.taxonomy_flat(tmp_path) == {} and st.load_aliases(tmp_path) == []
    st.save_taxonomy_category(tmp_path, "Core Expenses", "Food", "groceries", "Groceries")
    assert (tmp_path / "plan.rpx").is_file() and not (tmp_path / "input").exists()
    assert list(st.taxonomy_flat(tmp_path)) == ["groceries"]


def test_empty_aliases_table_still_seeds_from_the_rules_file(tmp_path):
    """The rules file stays a file until WP6.3c: with no aliases in the plan, the readers seed
    aliases from it as before."""
    write_plan_dataset(tmp_path, TAXONOMY, "tracking_type,group,category_id,label,origin,status,notes\n"
                                           "Core Expenses,Food,groceries,Groceries,template,active,\n")
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "client_spending_rules.csv").write_text(
        "keyword,category_id,match_field,exact,priority\nWHOLE FOODS,groceries,merchant,0,70\n", encoding="utf-8")
    aliases = st.load_aliases(tmp_path)
    assert [(a["match_value"], a["category_id"], a["source"]) for a in aliases] == [("WHOLE FOODS", "groceries", "seed")]


def test_import_preview_knows_the_plan_taxonomy(ws):
    from src.import_preview import _load_known_categories
    (ws.input_dir / TAXONOMY).unlink()
    known = _load_known_categories(ws.input_dir)
    first = _csv_rows(fixture_dir("sample_frozen") / TAXONOMY)[0]
    assert first["category_id"].lower() in known and first["label"].lower() in known


def test_plan_data_file_routes_read_and_write_the_tables(ws):
    import src.server.app_core as app_core
    text = app_core._read_plan_data_file(TAXONOMY)
    assert text.splitlines()[0] == "tracking_type,group,category_id,label,origin,status,notes"
    new = "match_value,match_field,exact,priority,category_id,source\nX,category,1,50,groceries,user\n"
    before = (ws.input_dir / ALIASES).read_bytes()
    assert app_core._write_plan_data_file(ALIASES, new) == ws.plan_db
    assert (ws.input_dir / ALIASES).read_bytes() == before
    assert app_core._read_plan_data_file(ALIASES) == new


def test_the_spending_files_travel_with_the_plan_file_not_as_files():
    from src.plan_data_registry import FLAT_PLAN_DATA_CSV_FILES, PLAN_TABLE_DATASET_FILES
    assert {TAXONOMY, ALIASES} <= PLAN_TABLE_DATASET_FILES <= set(FLAT_PLAN_DATA_CSV_FILES)


def test_at_rest_category_renames_reach_the_plan_tables(tmp_path):
    from src.plan_data_migration import migrate_plan_file
    write_plan_dataset(tmp_path, TAXONOMY, "tracking_type,group,category_id,label,origin,status,notes\n"
                                           "Wellness,Healthcare Premium,pre65_wellness_premium,Premium,template,active,\n")
    write_plan_dataset(tmp_path, ALIASES, "match_value,match_field,exact,priority,category_id,source\n"
                                          "Healthcare Premium,category,0,50,pre65_wellness_premium,user\n")
    plan = tmp_path / "plan.rpx"
    assert migrate_plan_file(plan, dry_run=True)["plan_datasets"] == 2
    assert plan_dataset_rows(tmp_path, ALIASES)[0]["category_id"] == "pre65_wellness_premium"
    report = migrate_plan_file(plan)
    assert report["plan_datasets"] == 2 and report["total_changed"] == 2
    assert plan_dataset_rows(tmp_path, TAXONOMY)[0]["category_id"] == "pre65_healthcare_premium"
    assert plan_dataset_rows(tmp_path, ALIASES)[0]["category_id"] == "pre65_healthcare_premium"
    assert migrate_plan_file(plan)["total_changed"] == 0
