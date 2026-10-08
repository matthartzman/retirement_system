"""Monarch upsert reads and replaces ytd_transactions in one plan-file transaction; the flat
importer reads legacy files leniently (cp1252 / NUL bytes)."""
from __future__ import annotations

import sqlite3

import pytest

from src import ytd_tracking
from src.active_plan import transform_dataset_rows_for_input_dir


def _use_plan(tmp_path, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("RETIREMENT_SYSTEM_PLAN_DB", str(tmp_path / "plan.rpx"))
    (tmp_path / "input").mkdir(exist_ok=True)
    return tmp_path / "input"


def test_transform_holds_the_write_lock_between_read_and_write(tmp_path, monkeypatch):
    input_dir = _use_plan(tmp_path, monkeypatch)
    ytd_tracking.write_transactions(input_dir, [{"Date": "2026-01-02", "Merchant": "A", "Account": "x", "Amount": "-1"}])
    seen = {}

    def fn(rows):
        con = sqlite3.connect(str(tmp_path / "plan.rpx"), timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError):
                con.execute("BEGIN IMMEDIATE")  # a second writer cannot slip in mid-merge
                seen["slipped_in"] = True
        finally:
            con.close()
        return rows + [{"Date": "2026-01-03", "Merchant": "B", "Account": "x", "Amount": "-2"}]

    transform_dataset_rows_for_input_dir(input_dir, "ytd_transactions", fn)
    assert "slipped_in" not in seen
    assert [r["Merchant"] for r in ytd_tracking.read_transactions(input_dir)] == ["A", "B"]


def test_upsert_merges_and_keeps_rows(tmp_path, monkeypatch):
    input_dir = _use_plan(tmp_path, monkeypatch)
    ytd_tracking.write_transactions(input_dir, [{"Date": "2026-01-02", "Merchant": "A", "Account": "x", "Amount": "-1"}])
    out = ytd_tracking.upsert_transactions_by_monarch_id(
        input_dir, [{"Date": "2026-01-03", "Merchant": "B", "Account": "x", "Amount": "-2", "Monarch Id": "m1"}]
    )
    assert out["added"] == 1 and out["total"] == 2


def test_flat_import_reads_cp1252_and_nul_files(tmp_path, monkeypatch):
    from src.active_plan import build_plan_file_from_csv_folder
    from src.plan_datasets import active_dataset_rows
    _use_plan(tmp_path, monkeypatch)
    folder = tmp_path / "legacy"
    folder.mkdir()
    (folder / "client_liabilities.csv").write_bytes("name,balance\nCaf\xe9 loan,10\n".encode("cp1252"))
    (folder / "client_holdings.csv").write_bytes(b"symbol,quantity\nAB\x00C,5\n")
    build_plan_file_from_csv_folder(tmp_path / "plan.rpx", folder)
    assert any("loan" in " ".join(r.values()) for r in active_dataset_rows("liabilities"))
    assert any("ABC" in " ".join(r.values()) for r in active_dataset_rows("holdings"))
