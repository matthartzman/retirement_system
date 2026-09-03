"""Ticket 305: the headless Monarch import writes ytd_transactions.csv to
disk with no Flask request context, so it must separately push those files
into the SQLite client_files table (the app's canonical Plan Data store) or
the running desktop app -- which reads the DB first -- never sees the update.
"""
from __future__ import annotations

from src import config_backend, monarch_db_sync


def test_sync_pushes_existing_ytd_files_into_client_files_table(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "ytd_transactions.csv").write_text("Date,Amount\n2026-01-01,-10\n", encoding="utf-8")
    (input_dir / "ytd_account_setup.csv").write_text("Account\nChecking\n", encoding="utf-8")
    db_path = tmp_path / "local_state" / "test.db"

    synced = monarch_db_sync.sync_ytd_files_to_db(input_dir, db_path)

    assert set(synced) == {"ytd_transactions.csv", "ytd_account_setup.csv"}
    stored = config_backend.get_client_file("ytd_transactions.csv", db_path=db_path)
    assert "2026-01-01" in stored


def test_sync_skips_files_absent_on_disk(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    db_path = tmp_path / "local_state" / "test.db"
    synced = monarch_db_sync.sync_ytd_files_to_db(input_dir, db_path)
    assert synced == []


def test_sync_overwrites_a_previously_stale_db_row(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    db_path = tmp_path / "local_state" / "test.db"
    config_backend.set_client_file("ytd_transactions.csv", "Date,Amount\nstale,0\n", db_path=db_path)

    (input_dir / "ytd_transactions.csv").write_text("Date,Amount\n2026-02-02,-20\n", encoding="utf-8")
    monarch_db_sync.sync_ytd_files_to_db(input_dir, db_path)

    stored = config_backend.get_client_file("ytd_transactions.csv", db_path=db_path)
    assert "2026-02-02" in stored
    assert "stale" not in stored
