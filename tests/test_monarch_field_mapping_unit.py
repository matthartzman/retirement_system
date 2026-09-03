"""Ticket 305: Monarch Extractor output columns are mapped to this app's
internal transaction schema through a configurable field map (column names
are not controlled by this app -- see src/monarch_field_map.json).
"""
from __future__ import annotations

from src import monarch_import as mi


def _map():
    return mi.load_field_map()


def test_default_field_map_loads_from_shipped_json():
    field_map = mi.load_field_map()
    assert field_map["id_column"] == "id"
    assert field_map["date_column"] == "date"


def test_missing_config_file_falls_back_to_built_in_guesses(tmp_path):
    field_map = mi.load_field_map(tmp_path / "does_not_exist.json")
    assert field_map == mi._FALLBACK_FIELD_MAP


def test_maps_a_well_formed_export():
    text = "id,date,merchant,category,account,amount\nabc-1,2026-03-04,Kroger,Groceries,Checking,-52.10\n"
    rows, errors = mi.map_monarch_csv_text(text, _map())
    assert errors == []
    assert len(rows) == 1
    assert rows[0]["Monarch Id"] == "abc-1"
    assert rows[0]["Date"] == "2026-03-04"
    assert rows[0]["Merchant"] == "Kroger"
    assert rows[0]["Amount"] == "-52.10"


def test_header_matching_is_case_and_whitespace_tolerant():
    text = " ID , Date ,Merchant\nabc-1,2026-03-04,Kroger\n"
    rows, errors = mi.map_monarch_csv_text(text, _map())
    assert errors == []
    assert rows[0]["Monarch Id"] == "abc-1"


def test_missing_id_column_is_a_clear_error_not_a_crash():
    text = "date,merchant,amount\n2026-03-04,Kroger,-52.10\n"
    rows, errors = mi.map_monarch_csv_text(text, _map())
    assert rows == []
    assert errors and "id" in errors[0].lower()


def test_row_missing_an_id_value_is_dropped_not_upserted():
    text = "id,date,merchant\n,2026-03-04,Kroger\nabc-2,2026-03-05,Costco\n"
    rows, errors = mi.map_monarch_csv_text(text, _map())
    assert errors == []
    assert len(rows) == 1
    assert rows[0]["Monarch Id"] == "abc-2"


def test_read_monarch_output_folder_reads_only_the_two_pending_files(tmp_path):
    (tmp_path / "new_transactions.csv").write_text(
        "run_id,id,date,merchant\nrun-1,abc-1,2026-03-04,Kroger\n", encoding="utf-8"
    )
    # transactions.csv (full history) and duplicates_removed.csv must never
    # be read, even though they sit in the same output folder.
    (tmp_path / "transactions.csv").write_text("id,date,merchant\nabc-1,2026-03-04,Kroger\n", encoding="utf-8")
    (tmp_path / "duplicates_removed.csv").write_text("id,date,merchant\nabc-9,2026-03-04,Dup\n", encoding="utf-8")

    result = mi.read_monarch_output_folder(tmp_path)
    assert result["files_consumed"] == ["new_transactions.csv"]
    assert len(result["rows"]) == 1
    assert result["rows"][0]["Monarch Id"] == "abc-1"


def test_read_monarch_output_folder_collects_run_ids(tmp_path):
    (tmp_path / "new_transactions.csv").write_text(
        "run_id,id,date,merchant\nrun-1,abc-1,2026-03-04,Kroger\nrun-2,abc-2,2026-03-05,Costco\n",
        encoding="utf-8",
    )
    (tmp_path / "changed_transactions.csv").write_text(
        "run_id,id,date,merchant\nrun-1,abc-3,2026-03-06,Target\n", encoding="utf-8"
    )
    result = mi.read_monarch_output_folder(tmp_path)
    assert result["run_ids"] == ["run-1", "run-2"]


def test_read_monarch_output_folder_missing_file_is_skipped_not_an_error(tmp_path):
    # A cycle with no changed transactions has no changed_transactions.csv
    # at all -- that must be a normal, error-free skip.
    (tmp_path / "new_transactions.csv").write_text("id,date,merchant\nabc-1,2026-03-04,Kroger\n", encoding="utf-8")
    result = mi.read_monarch_output_folder(tmp_path)
    assert result["errors"] == {}
    assert result["files_consumed"] == ["new_transactions.csv"]


def test_read_monarch_output_folder_reports_mapping_errors(tmp_path):
    (tmp_path / "new_transactions.csv").write_text("date,merchant\n2026-03-04,Kroger\n", encoding="utf-8")
    result = mi.read_monarch_output_folder(tmp_path)
    assert result["rows"] == []
    assert "new_transactions.csv" in result["errors"]


def test_read_monarch_output_folder_missing_dir_reports_error(tmp_path):
    result = mi.read_monarch_output_folder(tmp_path / "does_not_exist")
    assert result["rows"] == []
    assert result["files_consumed"] == []
    assert result["run_ids"] == []
    assert result["errors"]
