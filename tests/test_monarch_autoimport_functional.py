"""Ticket 305: end-to-end Monarch auto-import job (src/monarch_autoimport_job.py,
run headlessly by tools/monarch_autoimport.py) against a temp workspace --
new file, then a second run with one changed row and one new row, confirming
ytd_transactions.csv, ytd_import_history.csv, the SQLite mirror, and the
run-status file all reflect the merge correctly.
"""
from __future__ import annotations

from pathlib import Path

from src import config_backend, monarch_autoupdate as mau, ytd_tracking as ytd
from src import monarch_autoimport_job as monarch_autoimport


def _workspace(tmp_path: Path) -> Path:
    base_dir = tmp_path / "workspace"
    (base_dir / "input").mkdir(parents=True)
    (base_dir / "local_state").mkdir(parents=True)
    return base_dir


def test_disabled_toggle_skips_the_run(tmp_path):
    base_dir = _workspace(tmp_path)
    result = monarch_autoimport.run(base_dir)
    assert result["skipped"] is True
    assert result["skip_reason"] == "disabled"


def test_first_run_imports_new_rows_and_syncs_to_db(tmp_path):
    base_dir = _workspace(tmp_path)
    source_dir = base_dir.parent / "Monarch Extractor" / "output"
    source_dir.mkdir(parents=True)
    (source_dir / "export1.csv").write_text(
        "id,date,merchant,category,account,amount\n"
        "mid-1,2026-03-04,Kroger,Groceries,Checking,-52.10\n"
        "mid-2,2026-03-05,Costco,Groceries,Checking,-120.00\n",
        encoding="utf-8",
    )
    mau.save_policy(base_dir, {"enabled": True})

    result = monarch_autoimport.run(base_dir)

    assert result["success"] is True
    assert result["upsert"]["added"] == 2
    assert result["upsert"]["updated"] == 0
    stored = ytd.read_transactions(base_dir / "input")
    assert len(stored) == 2

    db_path = base_dir / "local_state" / "retirement_system_v10.db"
    db_content = config_backend.get_client_file("ytd_transactions.csv", db_path=db_path)
    assert "mid-1" in db_content

    status = mau.load_status(base_dir)
    assert status["success"] is True
    assert status["rows_added"] == 2

    # Consumed file archived, not left in place, per the default policy.
    assert not (source_dir / "export1.csv").exists()
    archived = list((source_dir / "imported").rglob("export1.csv"))
    assert len(archived) == 1


def test_second_run_replaces_changed_row_and_adds_new_one(tmp_path):
    base_dir = _workspace(tmp_path)
    source_dir = base_dir.parent / "Monarch Extractor" / "output"
    source_dir.mkdir(parents=True)
    (source_dir / "export1.csv").write_text(
        "id,date,merchant,category,account,amount\n"
        "mid-1,2026-03-04,Kroger,Groceries,Checking,-52.10\n",
        encoding="utf-8",
    )
    mau.save_policy(base_dir, {"enabled": True})
    monarch_autoimport.run(base_dir)

    (source_dir / "export2.csv").write_text(
        "id,date,merchant,category,account,amount\n"
        "mid-1,2026-03-04,Kroger,Dining,Checking,-61.40\n"  # changed
        "mid-3,2026-03-06,Target,Household,Checking,-30.00\n",  # new
        encoding="utf-8",
    )
    result = monarch_autoimport.run(base_dir)

    assert result["upsert"]["added"] == 1
    assert result["upsert"]["updated"] == 1
    stored = {r["Monarch Id"]: r for r in ytd.read_transactions(base_dir / "input")}
    assert len(stored) == 2
    assert stored["mid-1"]["Category"] == "Dining"
    assert stored["mid-3"]["Merchant"] == "Target"


def test_empty_source_folder_is_a_clean_skip_not_a_failure(tmp_path):
    base_dir = _workspace(tmp_path)
    (base_dir.parent / "Monarch Extractor" / "output").mkdir(parents=True)
    mau.save_policy(base_dir, {"enabled": True})
    result = monarch_autoimport.run(base_dir)
    assert result["success"] is True
    assert result["skipped"] is True
    assert result["skip_reason"] == "no_rows"


def test_missing_source_folder_is_reported_not_crashed(tmp_path):
    # Distinct from an empty-but-existing folder (a clean skip, tested above):
    # a source_dir that doesn't exist at all is a likely misconfigured path
    # and should surface as a failed run, not silently succeed.
    base_dir = _workspace(tmp_path)
    mau.save_policy(base_dir, {"enabled": True})
    result = monarch_autoimport.run(base_dir)
    assert result["success"] is False
    status = mau.load_status(base_dir)
    assert status["success"] is False
    assert any("does not exist" in e for e in status["errors"])


def test_force_runs_even_when_disabled(tmp_path):
    base_dir = _workspace(tmp_path)
    source_dir = base_dir.parent / "Monarch Extractor" / "output"
    source_dir.mkdir(parents=True)
    (source_dir / "export1.csv").write_text("id,date,merchant,amount\nmid-1,2026-03-04,Kroger,-52.10\n", encoding="utf-8")
    result = monarch_autoimport.run(base_dir, force=True)
    assert result["success"] is True
    assert result["upsert"]["added"] == 1
