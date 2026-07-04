from __future__ import annotations

"""Regression test for the "Load Saved Plan" CSV-resync bug (E2E Finding B).

Root cause: `/api/plan/load-file` swaps the SQLite database wholesale but the
on-disk `input/*.csv` files are read *first* by `_read_plan_data_file()` (see
documentation/CLAUDE.md's data storage hierarchy), so a load left every guided
page showing the previous session's stale CSV content. The fix in
`src/server/plan_routes.py::plan_load_file` widened the file list passed to
`materialize_workspace_files()` from a narrow hardcoded set (holdings,
allocation, spending taxonomy/aliases/budget files only) to the full
`PLAN_DATA_CSV_FILES` + `YTD_PLAN_DATA_FILES` list, so section/subsection/label
files like `client_household.csv` are also rewritten from the just-loaded
SQLite `client_files` table.
"""

import re
from pathlib import Path

import src.config_backend as config_backend
from src.config_backend import materialize_workspace_files, set_client_file
from src.server.plan_data_files import PLAN_DATA_CSV_FILES, YTD_PLAN_DATA_FILES

ROOT = Path(__file__).resolve().parents[1]


def test_plan_load_file_route_materializes_full_csv_file_set():
    """The route must pass a file list that includes client_household.csv,
    not just the narrow flat-table default `materialize_workspace_files` uses
    when file_names is omitted."""
    routes_src = (ROOT / "src" / "server" / "plan_routes.py").read_text(encoding="utf-8")
    match = re.search(r"materialize_workspace_files\((.*?)\)\s*$", routes_src, re.MULTILINE | re.DOTALL)
    assert match, "materialize_workspace_files call not found in plan_load_file"
    call_src = match.group(1)
    assert "PLAN_DATA_CSV_FILES" in call_src
    assert "YTD_PLAN_DATA_FILES" in call_src
    assert "overwrite_existing=True" in call_src


def test_materialize_workspace_files_overwrites_stale_household_csv_from_loaded_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config_backend, "PROJECT_ROOT", tmp_path)
    input_dir = tmp_path / "input"
    input_dir.mkdir(parents=True)

    db_path = tmp_path / "local_state" / "loaded.db"
    loaded_household_csv = "Household,Client,member_1_name,Alex Tester\n"
    set_client_file("client_household.csv", loaded_household_csv, db_path=db_path)

    stale_household_csv = "Household,Client,member_1_name,STALE MARKER VALUE\n"
    (input_dir / "client_household.csv").write_text(stale_household_csv, encoding="utf-8")

    file_names = [n for n in PLAN_DATA_CSV_FILES if n != "client_data.csv"] + YTD_PLAN_DATA_FILES
    materialize_workspace_files(db_path=db_path, file_names=file_names, overwrite_existing=True)

    result = (input_dir / "client_household.csv").read_text(encoding="utf-8")
    assert result == loaded_household_csv
    assert "STALE MARKER VALUE" not in result


def test_materialize_workspace_files_default_list_does_not_cover_household_csv():
    """Documents why the narrow default list was the bug: calling
    materialize_workspace_files() with no file_names (the old call site's
    effective behavior before the fix) never touches client_household.csv."""
    assert "client_household.csv" not in [
        "client_holdings.csv", "target_allocation.csv", "manual_pricing_validation.csv",
        "client_spending_taxonomy.csv", "client_spending_aliases.csv",
        "client_spending_budget.csv", "client_spending_budget_lines.csv",
    ]
    assert "client_household.csv" in PLAN_DATA_CSV_FILES
