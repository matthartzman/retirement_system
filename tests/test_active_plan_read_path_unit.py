"""WP4.2 / WP4.5: the engine, the build and the server read plan rows from the active plan file,
and every writer edits it through one transaction (``edit_active_plan``)."""
from __future__ import annotations

import pytest

from src import active_plan
from tests import plan_fixture as pf


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


def test_a_csv_edit_on_disk_never_reaches_the_plan(workspace):
    """Nothing reads the part files at runtime (WP4.5): editing one changes nothing."""
    from src.config_backend import load_active_config

    path = workspace.input_dir / "client_household.csv"
    old_name = workspace.data()["Household"][""]["member_1_name"]
    path.write_text(path.read_text(encoding="utf-8").replace(f",member_1_name,{old_name},", ",member_1_name,Edited Name,"),
                    encoding="utf-8")
    assert load_active_config()[0]["Household"][""]["member_1_name"] == old_name


def test_a_plan_file_with_no_rows_reads_as_an_empty_plan(tmp_path, monkeypatch):
    """There is no CSV bootstrap any more: a fresh plan file is empty until rows are written
    (a new plan, the demo, Load, or the converter)."""
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    (tmp_path / "input").mkdir()
    (tmp_path / "input" / "client_data.csv").write_text("section,subsection,label,value,units,notes\nA,,k,1,,\n", encoding="utf-8")
    assert active_plan.active_plan_data() == {}
    assert active_plan.peek_plan_data() == {}
    assert active_plan.active_plan_path().is_file()  # active_plan_data created the empty plan


def test_peek_plan_data_never_creates_the_plan_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv(active_plan.PLAN_DB_ENV, raising=False)
    assert active_plan.peek_plan_data() == {}
    assert not (tmp_path / "plan.rpx").exists()
    other = tmp_path / "other_ws"
    other.mkdir()
    assert active_plan.peek_plan_data(other) == {} and not (other / "plan.rpx").exists()


def test_peek_plan_data_for_input_dir_finds_the_plan_beside_the_input_folder(workspace, tmp_path):
    ws2 = pf.make_plan(tmp_path / "ws2")
    with ws2.store() as store:
        store.set_value("Household", "", "member_1_name", "Second Workspace")
    assert active_plan.peek_plan_data_for_input_dir(ws2.input_dir)["Household"][""]["member_1_name"] == "Second Workspace"
    assert active_plan.peek_plan_data_for_input_dir(workspace.input_dir) == workspace.store_data()


# --------------------------------------------------------------------- /api/plan/forms
def test_plan_forms_read_and_write_the_plan_rows(workspace):
    from src.server_services import plan_forms_service as forms

    edit = active_plan.edit_active_plan

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


# ------------------------------------------------------------- the edit transaction
def test_an_edit_commits_in_one_transaction_and_reports_the_revision(workspace):
    before = workspace.store_data()
    with active_plan.edit_active_plan() as edit:
        edit.store.set_value("Household", "", "member_1_name", "Changed Name")
        edit.store.set_value("Other Assets", "Home", "value_as_of_plan_start", "$7,777,777")
    assert edit.final_values[("Household", "", "member_1_name")] == "Changed Name"
    assert workspace.store_data()["Other Assets"]["Home"]["value_as_of_plan_start"] == "$7,777,777"
    with workspace.store(readonly=True) as store:
        assert edit.revision == store.revision()
    assert workspace.store_data() != before


def test_an_exception_inside_an_edit_rolls_everything_back(workspace):
    rows = workspace.store_data()
    with pytest.raises(RuntimeError):
        with active_plan.edit_active_plan() as edit:
            edit.store.set_value("Household", "", "member_1_name", "Changed Name")
            edit.store.insert_row("Business Succession", subsection="", label="entity_name", value="Acme")
            raise RuntimeError("boom")
    assert workspace.store_data() == rows


def test_roth_controls_are_made_canonical_before_the_commit(workspace):
    key = ("Withdrawal Policy", "Roth Conversion", "roth_target_bracket_rate")
    with active_plan.edit_active_plan() as edit:
        edit.store.set_value(*key, "22%")
    assert edit.final_values[key] == "22.00%" and workspace.store_data()[key[0]][key[1]][key[2]] == "22.00%"


def test_a_blanked_protected_date_is_put_back_unless_protection_is_off(workspace):
    key = ("Household", "", "member_1_retirement_date")
    kept = workspace.store_data()[key[0]][key[1]][key[2]]
    assert kept
    with active_plan.edit_active_plan() as edit:
        edit.store.set_value(*key, "")
    assert edit.final_values[key] == kept and workspace.store_data()["Household"][""][key[2]] == kept
    with active_plan.edit_active_plan() as edit:  # a replaced value is not blank: it wins
        edit.store.set_value(*key, "2031-06-01")
    assert workspace.store_data()["Household"][""][key[2]] == "2031-06-01"
    with active_plan.edit_active_plan(protect_values=False) as edit:  # a blank plan clears it on purpose
        edit.store.set_value(*key, "")
    assert workspace.store_data()["Household"][""][key[2]] == ""
