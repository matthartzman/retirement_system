"""WP6.3a/b: the spending taxonomy, aliases, budget, budget lines and tier overrides live in
plan.db tables (``store.spending``); conversion step C4b fills them from the legacy files; the spending readers and writers, the
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
BUDGET = "client_spending_budget.csv"
LINES = "client_spending_budget_lines.csv"
TIERS = "client_spending_tier_overrides.csv"


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
            if not (src / file).is_file():  # the fixture carries no tier overrides file
                assert name not in report.rows_written and store.spending.dataset(name).count() == 0
                continue
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


def test_c4b_completes_a_plan_converted_by_the_6_3a_version_of_the_step(tmp_path):
    src = fixture_dir("sample_frozen")
    (tmp_path / "client_spending_tier_overrides.csv").write_text(
        "category_id,tier,notes\ngroceries,discretionary,mine\n", encoding="utf-8")
    for f in ("client_spending_budget.csv", "client_spending_budget_lines.csv"):
        (tmp_path / f).write_bytes((src / f).read_bytes())
    with PlanStore.open(tmp_path / "plan.rpx") as store:
        # What the 6.3a step left: taxonomy and aliases done, the step marker, no dataset markers.
        store.spending.taxonomy.replace_all([{"tracking_type": "Travel", "group": "Travel", "category_id": "kept"}])
        store.set_meta(c4b_spending.MARKER_KEY, "rows=taxonomy:1")
        report = c4b_spending.run(tmp_path, store)
        assert not report.skipped and set(report.rows_written) == {"budget", "budget_lines", "tier_overrides"}
        assert [r["category_id"] for r in store.spending.taxonomy.rows()] == ["kept"]  # untouched
        assert store.spending.tier_overrides.rows() == [{"category_id": "groceries", "tier": "discretionary", "notes": "mine"}]
        assert store.spending.budget.count() == len(_csv_rows(src / "client_spending_budget.csv"))
        assert store.get_meta(c4b_spending.MARKER_KEY).startswith("rows=")
        assert c4b_spending.run(tmp_path, store).skipped  # second run: nothing left to do
        store.spending.tier_overrides.replace_all([])
        assert c4b_spending.run(tmp_path, store).skipped and store.spending.tier_overrides.count() == 0


def test_c4b_late_conversion_never_overwrites_a_filled_table(tmp_path):
    (tmp_path / "client_spending_tier_overrides.csv").write_text("category_id,tier,notes\nx,essential,\n", encoding="utf-8")
    with PlanStore.open(tmp_path / "plan.rpx") as store:
        store.spending.tier_overrides.replace_all([{"category_id": "y", "tier": "important"}])
        c4b_spending.run(tmp_path, store)
        assert [r["category_id"] for r in store.spending.tier_overrides.rows()] == ["y"]


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


def test_empty_aliases_table_still_seeds_from_the_rules_and_map_tables(tmp_path):
    """With no aliases in the plan, the readers seed aliases from the rules and category-map
    tables (WP6.3c; they were files before)."""
    write_plan_dataset(tmp_path, TAXONOMY, "tracking_type,group,category_id,label,origin,status,notes\n"
                                           "Core Expenses,Food,groceries,Groceries,template,active,\n")
    write_plan_dataset(tmp_path, "client_spending_rules.csv",
                       "keyword,category_id,match_field,exact,priority\nWHOLE FOODS,groceries,merchant,0,70\n")
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
    assert {TAXONOMY, ALIASES, BUDGET, LINES} <= PLAN_TABLE_DATASET_FILES <= set(FLAT_PLAN_DATA_CSV_FILES)


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


# ------------------------------------------------------------ WP6.3b: budget, lines, tier overrides
def test_budget_reads_and_writes_follow_the_plan_table_not_the_file(ws):
    want = [r for r in _csv_rows(ws.input_dir / BUDGET) if r["key"]]
    (ws.input_dir / BUDGET).unlink()
    loaded = st.load_unified_budget(ws.root)
    assert [(r["kind"], r["key"]) for r in loaded] == [(r["kind"].lower(), r["key"]) for r in want]
    assert st.load_unified_budget() == loaded  # root=None is the live workspace -> the active plan
    st.save_unified_budget(ws.root, [*loaded, {"kind": "category", "key": "brand_new", "annual_budget": "1234"}])
    assert not (ws.input_dir / BUDGET).exists()  # no workspace file is written
    rows = plan_dataset_rows(ws.root, BUDGET)
    assert rows[-1]["key"] == "brand_new" and rows[-1]["annual_budget"] == "1234"
    assert set(rows[-1]) >= set(st._BUDGET_HEADER)


def test_tier_overrides_round_trip_through_the_plan_table(tmp_path):
    from src import spending_budget_resolver as sbr
    assert sbr.load_spending_tier_overrides(tmp_path) == {}
    sbr.save_spending_tier_override(tmp_path, "groceries", "Discretionary", "mine")
    sbr.save_spending_tier_override(tmp_path, "dining", "important")
    assert sbr.load_spending_tier_overrides(tmp_path) == {"groceries": "discretionary", "dining": "important"}
    assert plan_dataset_rows(tmp_path, TIERS)[0] == {"category_id": "groceries", "tier": "discretionary", "notes": "mine"}
    assert not (tmp_path / "input").exists()
    sbr.save_spending_tier_override(tmp_path, "groceries", "")
    assert sbr.load_spending_tier_overrides(tmp_path) == {"dining": "important"}


def test_build_reads_the_budget_lines_table_of_the_active_plan(ws, monkeypatch):
    """A line staged in the plan's ``spending_budget_lines`` table reaches the engine config (the
    unified budget resolver, which supersedes the legacy lines afterwards, is switched off)."""
    from src import spending_budget_resolver
    from src.data_io import parse_client
    monkeypatch.setattr(spending_budget_resolver, "apply_budget_to_engine_config", lambda c, root=None: c)
    base = parse_client(ws.data(), "")
    n_extras, lump_total = len(base["recurring_extras"]), sum(base["lump"].values())
    write_plan_dataset(ws.root, LINES, "section,line_id,label,category_id,start_year,end_year,one_time_year,amount_per_year,mode,notes\n"
                                       "travel,t1,Big trip,,,,2031,7777,summary,\n"
                                       "travel,t2,Yearly trip,,2027,2029,,500,summary,\n"
                                       "gifts_charity,g1,Giving,,,,,9999,summary,\n")
    cfg = parse_client(ws.data(), "")
    assert cfg["lump"].get(2031, 0) - base["lump"].get(2031, 0) == 7777
    assert any(e["type"] == "Yearly trip" and e["amount"] == 500 for e in cfg["recurring_extras"])
    assert len(cfg["recurring_extras"]) == n_extras + 1  # gifts_charity stays out of spending
    assert sum(cfg["lump"].values()) == lump_total + 7777


def test_budget_save_diff_reads_the_plan_table(ws, monkeypatch):
    import src.server.app_core as app_core
    before = app_core._spending_budget_table_rows()
    assert before and before[0][:4] == ["kind", "key", "label", "annual_budget"]
    events = []
    monkeypatch.setattr(app_core, "_record_admin_config_change", lambda *a, **k: events.append(a) or {"id": 1})
    monkeypatch.setattr(app_core, "jsonify", lambda p: p)
    payload, status = app_core._spending_budget_save_result(
        lambda: (st.save_unified_budget(ws.root, [{"kind": "category", "key": "x_cat", "annual_budget": "5"}]) or ({"ok": 1}, 200)))
    assert status == 200 and payload["change_event"] == {"id": 1}
    kind, name, path, old, new = events[0]
    assert (kind, name, path) == ("spending_budget", "client_spending_budget.csv", str(ws.plan_db))
    assert old == before and new[1][:2] == ["category", "x_cat"]


def test_plan_data_file_routes_serve_the_budget_tables(ws):
    import src.server.app_core as app_core
    text = app_core._read_plan_data_file(BUDGET)
    assert text.splitlines()[0].startswith("kind,key,label,annual_budget")
    new = "section,line_id,label,category_id,start_year,end_year,one_time_year,amount_per_year,mode,notes\ntravel,a,A,,,,2030,10,summary,\n"
    before = (ws.input_dir / LINES).read_bytes()
    assert app_core._write_plan_data_file(LINES, new) == ws.plan_db
    assert (ws.input_dir / LINES).read_bytes() == before
    assert app_core._read_plan_data_file(LINES) == new


def test_at_rest_category_renames_reach_lines_and_tier_overrides(tmp_path):
    from src.plan_data_migration import migrate_plan_file
    write_plan_dataset(tmp_path, LINES, "section,line_id,label,category_id\ntravel,a,A,pre65_wellness_premium\n")
    write_plan_dataset(tmp_path, TIERS, "category_id,tier,notes\npre65_wellness_premium,essential,\n")
    assert migrate_plan_file(tmp_path / "plan.rpx")["plan_datasets"] == 2
    assert plan_dataset_rows(tmp_path, LINES)[0]["category_id"] == "pre65_healthcare_premium"
    assert plan_dataset_rows(tmp_path, TIERS)[0]["category_id"] == "pre65_healthcare_premium"


# ------------------------------------------------------------------ WP6.3c
def test_c4b_converts_rules_map_group_budget_and_recovery_copies(tmp_path):
    (tmp_path / "client_spending_rules.csv").write_text("keyword,category_id,match_field,exact,priority\nShell,fuel,merchant,1,60\n", encoding="utf-8")
    (tmp_path / "spending_category_map.csv").write_text("super_group,group,category,tracking\nExpenses,Auto,Fuel,core\n", encoding="utf-8")
    (tmp_path / "spending_budget.csv").write_text("group,budget_pct,budget_override,notes\nAuto,5.2,,x\n", encoding="utf-8")
    (tmp_path / "client_spending_budget.recovery_seed.csv").write_text("kind,key,label,annual_budget\ncategory,fuel,Fuel,100\n", encoding="utf-8")
    (tmp_path / "client_spending_budget.csv.pre_recovery_backup").write_text("kind,key,label,annual_budget\ncategory,fuel,Fuel,0\n", encoding="utf-8")
    (tmp_path / "client_spending_budget.csv").write_text("category_id,annual_budget,notes\nfuel,40,a\nfuel,60,b\n", encoding="utf-8")
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4b_spending.run(tmp_path, store)
        assert report.legacy_budget_layout
        assert store.spending.rules.rows()[0]["keyword"] == "Shell"
        assert store.spending.category_map.rows()[0]["category"] == "Fuel"
        assert store.spending.group_budget.rows()[0]["budget_pct"] == "5.2"
        assert [r["annual_budget"] for r in store.spending.budget.rows()] == ["100"]
        assert store.spending.recovery_seed()[0]["annual_budget"] == "100"
        assert store.spending.restore_pre_recovery_copy() == 1
        assert store.spending.budget.rows()[0]["annual_budget"] == "0"
        assert c4b_spending.run(tmp_path, store).skipped


def test_group_budget_rules_and_map_round_trip_through_the_plan(ws):
    st.save_budget(ws.root, {"Auto": {"budget_pct": 5.2, "budget_override": 0.0, "notes": "n"}})
    assert st.load_budget(ws.root)["Auto"]["budget_pct"] == 5.2
    assert plan_dataset_rows(ws.root, "spending_budget.csv")[0]["group"] == "Auto"
    before = (ws.input_dir / "spending_budget.csv").read_bytes()
    st.save_budget(ws.root, {})
    assert (ws.input_dir / "spending_budget.csv").read_bytes() == before  # the file is never written
