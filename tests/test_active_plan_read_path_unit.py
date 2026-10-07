"""WP4.2: the engine, the build and the server read plan rows from the active plan file."""
from __future__ import annotations

import pytest

from src import active_plan
from src.csv_exchange import parse_plan_csv, sync_plan_rows
from src.stores import PlanStore
from tests import plan_fixture as pf

HEADER = "section,subsection,label,value,units,notes\n"


def _rows(text):
    return parse_plan_csv(HEADER + text, "client_household.csv").rows


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A fixture plan laid down as its own workspace (plan.rpx beside input/)."""
    ws = pf.make_plan(tmp_path)
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    return ws


# ---------------------------------------------------------------- where the plan file is
def test_active_plan_path_is_the_workspace_plan_file_or_the_env_override(workspace, tmp_path, monkeypatch):
    assert active_plan.active_plan_path() == workspace.plan_db == tmp_path / "plan.rpx"
    monkeypatch.setenv(active_plan.PLAN_DB_ENV, str(tmp_path / "other.rpx"))
    assert active_plan.active_plan_path() == tmp_path / "other.rpx"
    monkeypatch.setenv(active_plan.PLAN_DB_ENV, "rel/plan.rpx")
    assert active_plan.active_plan_path() == tmp_path / "rel" / "plan.rpx"
    env = active_plan.plan_db_env({})
    assert env == {active_plan.PLAN_DB_ENV: str(tmp_path / "rel" / "plan.rpx")}


# ---------------------------------------------------------------------- the read path
def test_load_active_config_reads_the_plan_file_not_the_csvs(workspace):
    from src.config_backend import load_active_config

    with workspace.store() as store:
        store.set_value("Household", "", "member_1_name", "From The Plan File")
    # the CSVs still say otherwise; the plan file wins
    assert "From The Plan File" not in (workspace.input_dir / "client_household.csv").read_text(encoding="utf-8")
    data, meta = load_active_config()
    assert data["Household"][""]["member_1_name"] == "From The Plan File"
    assert meta["plan_db"] == str(workspace.plan_db) and meta["backend"] == "SQLITE"


def test_load_active_config_view_equals_the_csv_loader_for_the_fixture(workspace):
    from src.config_backend import _merge_system_config_sections, load_active_config
    from src.system_config import discover_system_config_csv, load_system_config

    data, _ = load_active_config()
    expected = _merge_system_config_sections(workspace.data(), load_system_config(discover_system_config_csv()))
    assert data == expected and list(data) == list(expected)


def test_an_empty_plan_file_is_filled_from_the_csv_set_on_first_read(workspace):
    from src.config_backend import load_active_config

    workspace.plan_db.unlink()
    data, _ = load_active_config()
    assert workspace.plan_db.is_file()
    assert data["Household"] == workspace.data()["Household"]
    with workspace.store(readonly=True) as store:
        assert store.sectioned_data() == workspace.data()


def test_edit_then_read_goes_through_the_sync(workspace):
    """A CSV writer's edit reaches the readers only through the sync, as it reached the
    old snapshot; the sync is what every writer calls after writing."""
    from src.config_backend import load_active_config

    path = workspace.input_dir / "client_household.csv"
    text = path.read_text(encoding="utf-8")
    old_name = workspace.data()["Household"][""]["member_1_name"]
    path.write_text(text.replace(f",member_1_name,{old_name},", ",member_1_name,Edited Name,"), encoding="utf-8")
    assert load_active_config()[0]["Household"][""]["member_1_name"] == old_name
    result = active_plan.sync_active_plan_from_csv(workspace.input_dir)
    assert result.counts["updated"] == 1 and result.counts["inserted"] == 0
    assert load_active_config()[0]["Household"][""]["member_1_name"] == "Edited Name"
    assert "client_household.csv" in result.texts


def test_sync_drops_the_old_loaders_retired_labels(tmp_path, monkeypatch):
    monkeypatch.setenv(active_plan.PLAN_DB_ENV, str(tmp_path / "plan.rpx"))
    (tmp_path / "client_policy.csv").write_text(
        HEADER + "Scenarios,Sell Home,home_value,900000,,\nScenarios,Sell Home,home_sale_year,2045,,\n"
        "Household,,label,x,,\n", encoding="utf-8")
    data = active_plan.sync_active_plan_from_csv(tmp_path).data
    assert data == {"Scenarios": {"Sell Home": {"home_sale_year": "2045"}}}


# ------------------------------------------------------------- csv_exchange.sync_plan_rows
def test_sync_plan_rows_keeps_row_ids_and_writes_nothing_when_unchanged():
    with PlanStore.open() as store:
        sync_plan_rows(store, _rows("Household,,a,1,,\nHousehold,,b,2,,\nIncome,,c,3,,\n"))
        ids = {r["label"]: r["row_id"] for r in store.all_rows()}
        rev = store.revision()
        assert sync_plan_rows(store, _rows("Household,,a,1,,\nHousehold,,b,2,,\nIncome,,c,3,,\n")) == \
            {"updated": 0, "inserted": 0, "deleted": 0, "rewritten": 0}
        assert store.revision() == rev
        counts = sync_plan_rows(store, _rows("Household,,a,9,,\nHousehold,,new,5,,\nIncome,,c,3,,\n"))
        assert counts == {"updated": 1, "inserted": 1, "deleted": 1, "rewritten": 0}
        after = {r["label"]: r["row_id"] for r in store.all_rows()}
        assert after["a"] == ids["a"] and after["c"] == ids["c"] and "b" not in after
        assert store.sectioned_data() == {"Household": {"": {"a": "9", "new": "5"}}, "Income": {"": {"c": "3"}}}


def test_sync_plan_rows_matches_repeated_keys_by_occurrence_and_keeps_display_order():
    with PlanStore.open() as store:
        sync_plan_rows(store, _rows("S,,k,first,,\nS,,x,1,,\nS,,k,second,,\n"))
        first, _, second = [r["row_id"] for r in store.rows("S")]
        sync_plan_rows(store, _rows("S,,x,1,,\nS,,k,first,,\nS,,k,last,,\n"))
        rows = store.rows("S")
        assert [(r["label"], r["value"]) for r in rows] == [("x", "1"), ("k", "first"), ("k", "last")]
        assert [r["row_id"] for r in rows if r["label"] == "k"] == [first, second]
        assert store.sectioned_data() == {"S": {"": {"x": "1", "k": "last"}}}


def test_sync_plan_rows_rewrites_when_the_section_order_would_change():
    with PlanStore.open() as store:
        sync_plan_rows(store, _rows("A,,a,1,,\nB,,b,2,,\n"))
        counts = sync_plan_rows(store, _rows("B,,b,2,,\nA,,a,1,,\n"))
        assert counts["rewritten"] == 1
        assert list(store.sectioned_data()) == ["B", "A"] == store.section_order()


# --------------------------------------------------------------------- /api/plan/forms
def test_plan_forms_read_and_write_the_plan_rows(workspace):
    from src.server_services import plan_forms_service as forms

    got = forms.get_forms_payload()
    assert got["sections"] == workspace.store_data()
    payload, status = forms.patch_forms_payload("Household/", {"member_1_name": "Form Name"})
    assert status == 400  # needs section/subsection
    payload, status = forms.patch_forms_payload("Economic Assumptions/Rates", {"new_rate": "3%"})
    assert status == 200 and payload["values"]["new_rate"] == "3%"
    assert workspace.store_data()["Economic Assumptions"]["Rates"]["new_rate"] == "3%"
    payload, status = forms.save_forms_payload({"Household": {"": {"member_1_name": "Only"}}})
    assert status == 200 and workspace.store_data() == {"Household": {"": {"member_1_name": "Only"}}}
    assert forms.save_forms_payload([])[1] == 400
