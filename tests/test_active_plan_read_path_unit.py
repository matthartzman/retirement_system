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


def test_sync_plan_rows_collapses_repeated_keys_last_wins_at_the_first_position():
    with PlanStore.open() as store:
        sync_plan_rows(store, _rows("S,,k,first,,\nS,,x,1,,\nS,,k,second,,\n"))
        rows = store.rows("S")
        assert [(r["label"], r["value"]) for r in rows] == [("k", "second"), ("x", "1")]
        k_id = rows[0]["row_id"]
        sync_plan_rows(store, _rows("S,,x,1,,\nS,,k,first,,\nS,,k,last,,\n"))
        rows = store.rows("S")
        assert [(r["label"], r["value"]) for r in rows] == [("x", "1"), ("k", "last")]
        assert rows[1]["row_id"] == k_id          # the surviving key keeps its row
        assert store.sectioned_data() == {"S": {"": {"x": "1", "k": "last"}}}
        # a plan that still holds both copies (older import) loses the stale one at the next sync
        store.insert_row("S", sort_order=9, subsection="", label="x", value="stale", units="", notes="")
        assert len(store.rows("S")) == 3
        sync_plan_rows(store, _rows("S,,x,1,,\nS,,k,last,,\n"))
        assert [(r["label"], r["value"]) for r in store.rows("S")] == [("x", "1"), ("k", "last")]


def test_sync_plan_rows_rewrites_when_the_section_order_would_change():
    with PlanStore.open() as store:
        sync_plan_rows(store, _rows("A,,a,1,,\nB,,b,2,,\n"))
        counts = sync_plan_rows(store, _rows("B,,b,2,,\nA,,a,1,,\n"))
        assert counts["rewritten"] == 1
        assert list(store.sectioned_data()) == ["B", "A"] == store.section_order()


# --------------------------------------------------------------------- /api/plan/forms
def test_plan_forms_read_and_write_the_plan_rows(workspace):
    from src.server_services import plan_forms_service as forms

    def edit():
        return active_plan.edit_active_plan(
            workspace.input_dir, lambda n, c: (workspace.input_dir / n).write_text(c, encoding="utf-8"))

    got = forms.get_forms_payload()
    assert got["sections"] == workspace.store_data()
    payload, status = forms.patch_forms_payload("Household/", {"member_1_name": "Form Name"}, edit_plan=edit)
    assert status == 400  # needs section/subsection
    payload, status = forms.patch_forms_payload("Economic Assumptions/Rates", {"new_rate": "3%"}, edit_plan=edit)
    assert status == 200 and payload["values"]["new_rate"] == "3%"
    assert workspace.store_data()["Economic Assumptions"]["Rates"]["new_rate"] == "3%"
    before = workspace.store_data()
    payload, status = forms.save_forms_payload({"Household": {"": {"member_1_name": "Only"}}}, edit_plan=edit)
    assert status == 200 and workspace.store_data()["Household"][""]["member_1_name"] == "Only"
    assert set(workspace.store_data()["Household"][""]) == set(before["Household"][""])  # upsert only: nothing deleted
    payload, status = forms.save_forms_payload({"Household": {"": {"member_1_name": "Only"}}}, edit_plan=edit, replace=True)
    only = {"Household": {"": {"member_1_name": "Only"}}}
    assert status == 200 and workspace.store_data()["Household"] == only["Household"]
    assert {k: v for k, v in workspace.store_data().items() if k != "Household"} == \
        {k: v for k, v in before.items() if k != "Household"}  # sections not posted are kept
    assert forms.save_forms_payload([], edit_plan=edit)[1] == 400


# ------------------------------------------------- WP4.3 review fixes: edit safety, reads, change check
def _writer(workspace, log=None, fail_on=None):
    def write(name, text):
        if name == fail_on:
            raise OSError(f"disk full writing {name}")
        (workspace.input_dir / name).write_text(text, encoding="utf-8")
        if log is not None:
            log.append(name)
        return workspace.input_dir / name
    return write


def _csv_texts(workspace):
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(workspace.input_dir.glob("*.csv"))}


def _two_file_edit(edit):
    edit.store.set_value("Household", "", "member_1_name", "Changed Name")
    edit.store.set_value("Other Assets", "Home", "value_as_of_plan_start", "$7,777,777")


def test_a_failed_file_write_restores_the_files_already_written_and_the_rows(workspace):
    texts, rows = _csv_texts(workspace), workspace.store_data()
    log: list[str] = []
    with pytest.raises(OSError):
        with active_plan.edit_active_plan(workspace.input_dir, _writer(workspace, log, fail_on="client_assets.csv"),
                                      _writer(workspace)) as edit:
            _two_file_edit(edit)
    assert log == ["client_household.csv"]  # the first file really was written before the failure
    assert _csv_texts(workspace) == texts and workspace.store_data() == rows


def test_a_failed_second_bridge_run_restores_the_files_and_the_rows(workspace, monkeypatch):
    texts, rows = _csv_texts(workspace), workspace.store_data()
    real, calls = active_plan._pull, []

    def pull(store, input_dir):
        calls.append(1)
        if len(calls) == 2:
            raise active_plan.PlanCsvError("second bridge run failed")
        return real(store, input_dir)

    monkeypatch.setattr(active_plan, "_pull", pull)
    log: list[str] = []
    with pytest.raises(active_plan.PlanCsvError):
        with active_plan.edit_active_plan(workspace.input_dir, _writer(workspace, log), _writer(workspace)) as edit:
            _two_file_edit(edit)
    assert sorted(log) == ["client_assets.csv", "client_household.csv"]  # both were written ...
    assert _csv_texts(workspace) == texts and workspace.store_data() == rows  # ... and put back


def test_a_file_the_failed_edit_created_is_removed_again(workspace):
    (workspace.input_dir / "client_business.csv").unlink()
    texts = _csv_texts(workspace)
    plain = _writer(workspace)

    def write(name, text):
        path = plain(name, text)
        if name == "client_business.csv":
            raise OSError("fails right after creating the file")
        return path

    with pytest.raises(OSError):
        with active_plan.edit_active_plan(workspace.input_dir, write, plain) as edit:
            edit.store.set_value("Household", "", "member_1_name", "Changed Name")
            edit.store.insert_row("Business Succession", subsection="", label="entity_name", value="Acme")
    assert _csv_texts(workspace) == texts and not (workspace.input_dir / "client_business.csv").exists()


def test_a_successful_edit_still_writes_and_keeps_both_sides_equal(workspace):
    with active_plan.edit_active_plan(workspace.input_dir, _writer(workspace)) as edit:
        _two_file_edit(edit)
    assert "Changed Name" in (workspace.input_dir / "client_household.csv").read_text(encoding="utf-8")
    assert edit.final_values[("Household", "", "member_1_name")] == "Changed Name"
    assert workspace.store_data()["Other Assets"]["Home"]["value_as_of_plan_start"] == "$7,777,777"


def test_a_read_with_an_unparsable_part_file_serves_the_stored_rows_with_a_warning(workspace):
    rows = workspace.store_data()
    (workspace.input_dir / "client_policy.csv").write_text("not,a,plan\n1,2,3\n", encoding="utf-8")
    warning = active_plan.refresh_active_plan(workspace.input_dir)
    assert "client_policy.csv" in warning and workspace.store_data() == rows
    # an edit truly needs the CSV set: it refuses and changes nothing
    with pytest.raises(active_plan.PlanCsvError):
        with active_plan.edit_active_plan(workspace.input_dir, _writer(workspace)) as edit:
            edit.store.set_value("Household", "", "member_1_name", "Nope")
    assert workspace.store_data() == rows


def test_an_unchanged_csv_set_is_no_bridge_run_and_no_write_lock(workspace, monkeypatch):
    runs = []
    real = active_plan.sync_active_plan_from_csv
    monkeypatch.setattr(active_plan, "sync_active_plan_from_csv", lambda d: (runs.append(1), real(d))[1])
    assert active_plan.refresh_active_plan(workspace.input_dir) == "" and len(runs) == 1  # first read syncs
    for _ in range(3):
        assert active_plan.refresh_active_plan(workspace.input_dir) == ""
    assert len(runs) == 1  # nothing changed: no further run
    # a held write lock on the plan file does not block an unchanged read
    import sqlite3
    blocker = sqlite3.connect(workspace.plan_db, timeout=0.1)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        assert active_plan.refresh_active_plan(workspace.input_dir) == "" and len(runs) == 1
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    # a CSV change runs it once, then it is quiet again
    household = workspace.input_dir / "client_household.csv"
    household.write_text(household.read_text(encoding="utf-8").replace("member_1_name,", "member_1_name,Z", 1), encoding="utf-8")
    active_plan.refresh_active_plan(workspace.input_dir)
    active_plan.refresh_active_plan(workspace.input_dir)
    assert len(runs) == 2
    assert workspace.store_data()["Household"][""]["member_1_name"].startswith("Z")
    # a change of the plan itself (another writer, a swapped plan file) runs it too
    with workspace.store() as store:
        store.set_value("Household", "", "member_1_name", "Other Writer")
    active_plan.refresh_active_plan(workspace.input_dir)
    assert len(runs) == 3 and workspace.store_data()["Household"][""]["member_1_name"].startswith("Z")
