"""A headless script has no Flask request context, so it must read Plan Data
the same DB-first way _read_plan_data_file does inside the running app, or
it sees stale/disk-only data once the SQLite store has a newer row.
"""
from __future__ import annotations

from src import config_backend, plan_data_read


def test_reads_from_db_when_present(tmp_path):
    db_path = tmp_path / "local_state" / "test.db"
    config_backend.set_client_file("client_liabilities.csv", "balance\n100\n", db_path=db_path)
    content = plan_data_read.read_plan_data_file("client_liabilities.csv", tmp_path, db_path)
    assert content == "balance\n100\n"


def test_falls_back_to_disk_when_db_has_no_row(tmp_path):
    db_path = tmp_path / "local_state" / "test.db"
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "client_liabilities.csv").write_text("balance\n200\n", encoding="utf-8")
    content = plan_data_read.read_plan_data_file("client_liabilities.csv", tmp_path, db_path)
    assert content == "balance\n200\n"


def test_returns_none_when_neither_source_has_the_file(tmp_path):
    db_path = tmp_path / "local_state" / "test.db"
    content = plan_data_read.read_plan_data_file("client_liabilities.csv", tmp_path, db_path)
    assert content is None


def test_db_row_takes_priority_over_a_stale_disk_copy(tmp_path):
    db_path = tmp_path / "local_state" / "test.db"
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "client_liabilities.csv").write_text("balance\nstale\n", encoding="utf-8")
    config_backend.set_client_file("client_liabilities.csv", "balance\nfresh\n", db_path=db_path)
    content = plan_data_read.read_plan_data_file("client_liabilities.csv", tmp_path, db_path)
    assert "fresh" in content
