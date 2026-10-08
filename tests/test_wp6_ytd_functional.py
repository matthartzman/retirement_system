"""WP6.4: the YTD transactions, account setup and import history live in plan.db tables
(schema v6); conversion step C4c fills them from the legacy files; the YTD readers and writers,
the Monarch import and the plan-data file routes use the plan's tables."""
import csv
import io
from datetime import date

import pytest

from src import ytd_tracking as ytd
from src.csv_exchange import FLAT_DATASET_FILES, dataset_csv_text, replace_dataset_from_csv_text
from src.legacy_conversion.steps import c4c_ytd
from src.stores import PlanStore
from src.stores import db
from src.stores.plan_store import _SCHEMA_V1
from tests.plan_fixture import fixture_dir, plan_dataset_rows, write_plan_dataset

FILES = {"ytd_transactions": "ytd_transactions.csv", "ytd_account_setup": "ytd_account_setup.csv",
         "ytd_import_history": "ytd_import_history.csv"}
TX_HEADER = "Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n"


def _csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# --------------------------------------------------------------------- schema
def test_the_ytd_files_are_registered_as_plan_datasets():
    assert {n: FLAT_DATASET_FILES[n] for n in FILES} == FILES
    from src.plan_data_registry import PLAN_TABLE_DATASET_FILES, YTD_PLAN_DATA_FILES
    assert set(YTD_PLAN_DATA_FILES) == set(FILES.values()) <= PLAN_TABLE_DATASET_FILES


def test_v5_file_upgrades_to_v6_with_empty_ytd_tables(tmp_path):
    from src.stores.datasets import SCHEMA_V2_DDL, SCHEMA_V3_DDL, SCHEMA_V4_DDL, SCHEMA_V5_DDL
    p = tmp_path / "v5.rpx"
    con = db.connect(str(p))
    db.migrate(con, (_SCHEMA_V1, SCHEMA_V2_DDL, SCHEMA_V3_DDL, SCHEMA_V4_DDL, SCHEMA_V5_DDL))
    con.execute("INSERT INTO holdings_lots (position, account) VALUES (0, 'A_IRA')")
    con.commit()
    con.close()
    with PlanStore.open(p) as s:
        assert s.schema_version == 8
        assert s.holdings.rows()[0]["account"] == "A_IRA"
        assert all(s.dataset(n).count() == 0 for n in FILES)


def test_ytd_tables_round_trip_lossless_in_file_order_with_extra_columns(tmp_path):
    text = ("Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner,Monarch Id,MappedCategoryId\n"
            "2026-02-01, Spaced ,Groceries,Checking,\"STMT, with comma\",,-12.50,,Shared,m-2,groceries\n"
            "2026-01-01,Early,Dining,Checking,,,-3,,Shared,m-1,\n")
    with PlanStore.open(tmp_path / "p.rpx") as store:
        repo = store.dataset("ytd_transactions")
        assert replace_dataset_from_csv_text(repo, text) == 2
        rows = repo.rows()
        assert [r["Monarch Id"] for r in rows] == ["m-2", "m-1"]  # file order, not sorted
        assert rows[0]["Merchant"] == " Spaced " and rows[0]["Original Statement"] == "STMT, with comma"
        assert repo.extra_columns() == ["MappedCategoryId"] and rows[0]["MappedCategoryId"] == "groceries"
        assert list(csv.DictReader(io.StringIO(dataset_csv_text(repo)))) == list(csv.DictReader(io.StringIO(text)))


# ------------------------------------------------------------------ conversion
def test_c4c_converts_the_fixture_files_cell_for_cell_and_is_idempotent(tmp_path):
    src = fixture_dir("sample_frozen")
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4c_ytd.run(src, store)
        assert not report.skipped
        for name, file in FILES.items():
            want = _csv_rows(src / file)
            got = store.dataset(name).rows()
            assert len(got) == len(want) == report.rows_written[name] > 0 or name == "ytd_import_history"
            assert [{k: r[k] for k in w} for r, w in zip(got, want)] == want
        assert store.get_meta(c4c_ytd.MARKER_KEY).startswith("rows=")
        store.dataset("ytd_transactions").replace_all([])
        assert c4c_ytd.run(src, store).skipped  # the marker makes the second run a no-op
        assert store.dataset("ytd_transactions").count() == 0


def test_c4c_keeps_a_bom_and_missing_files_leave_tables_empty(tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "ytd_transactions.csv").write_bytes("﻿".encode("utf-8") + (TX_HEADER + "2026-01-02,A,B,C,,,-1,,\n").encode())
    with PlanStore.open(tmp_path / "p.rpx") as store:
        report = c4c_ytd.run(folder, store)
        assert report.rows_written == {"ytd_transactions": 1}
        assert store.dataset("ytd_transactions").rows()[0]["Date"] == "2026-01-02"  # BOM not in the header
        assert store.dataset("ytd_account_setup").count() == 0 and store.dataset("ytd_import_history").count() == 0
    with PlanStore.open(tmp_path / "q.rpx") as store:
        assert c4c_ytd.run(tmp_path / "nothing_here", store).rows_written == {}
        assert store.get_meta(c4c_ytd.MARKER_KEY) == "rows="


# ------------------------------------------------------- readers and writers
def test_ytd_functions_read_and_write_the_plan_beside_the_input_folder(tmp_path):
    root = tmp_path / "input"
    assert ytd.read_transactions(root) == [] and ytd.read_account_setup(root) == [] and ytd.read_import_history(root) == []
    assert not (tmp_path / "plan.rpx").exists()  # reading never creates the plan
    out = ytd.import_transactions(root, TX_HEADER + "2026-03-01,B,Groceries,Checking,,,-5,,Shared\n"
                                  "2026-01-01,A,Groceries,Savings,,,-7,,Shared\n", mode="replace", today=date(2026, 6, 1))
    assert out["success"] and out["added"] == 2
    rows = ytd.read_transactions(root)
    assert [r["Merchant"] for r in rows] == ["A", "B"]  # the import sorts by date
    assert {r["Account"] for r in ytd.read_account_setup(root)} == {"Checking", "Savings"}
    assert [r["Mode"] for r in ytd.read_import_history(root)] == ["replace"]
    again = ytd.import_transactions(root, TX_HEADER + "2026-04-01,C,Groceries,Checking,,,-9,,Shared\n", mode="incremental", today=date(2026, 6, 1))
    assert again["added"] == 1 and len(ytd.read_transactions(root)) == 3
    assert [r["Mode"] for r in ytd.read_import_history(root)] == ["replace", "incremental"]
    # the data is in the plan file's tables, in the legacy column names
    assert [r["Merchant"] for r in plan_dataset_rows(tmp_path, "ytd_transactions.csv")] == ["A", "B", "C"]
    assert len(plan_dataset_rows(tmp_path, "ytd_import_history.csv")) == 2
    assert not list(root.glob("*")) and not list(tmp_path.glob("ytd_*"))  # no workspace file


def test_account_setup_dedupes_case_insensitively_and_drops_blank_accounts(tmp_path):
    root = tmp_path / "input"
    ytd.write_account_setup(root, [{"Account": "Checking"}, {"Account": " checking "}, {"Account": ""}, {"Account": "Roth", "Role": "Investment"}])
    assert [r["Account"] for r in ytd.read_account_setup(root)] == ["Checking", "Roth"]


def test_ytd_rows_ignore_columns_the_file_never_wrote(tmp_path):
    write_plan_dataset(tmp_path, "ytd_transactions.csv", TX_HEADER.rstrip("\n") + ",MappedCategoryId\n2026-01-01,A,B,C,,,-1,,,x\n")
    root = tmp_path / "input"
    assert "MappedCategoryId" not in ytd.read_transactions(root)[0]
    from src import spending_tracker as st
    assert st.load_transactions_extended(tmp_path)[0]["mapped_category_id"] == "x"


# ------------------------------------------------------------------ the product
def test_plan_data_file_reads_writes_and_the_zip_use_the_tables(tmp_path, monkeypatch):
    import zipfile

    import src.server.app_core as app_core
    from src.active_plan import PLAN_DB_ENV
    from src.server_services.admin_service import build_csv_backup_zip

    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    text = TX_HEADER.rstrip("\n") + ",Monarch Id\n2026-01-01,A,B,C,,,-1,,,m-1\n"  # the table's own columns
    assert app_core._normalize_plan_data_file_name("ytd_import_history.csv") == "ytd_import_history.csv"
    assert app_core._write_plan_data_file("ytd_transactions.csv", text) == plan
    assert app_core._read_plan_data_file("ytd_transactions.csv") == text
    assert app_core._read_plan_data_file("ytd_account_setup.csv") is None  # an empty table reads as "no file"
    blob, _name = build_csv_backup_zip(tmp_path)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.read("ytd_transactions.csv").decode() == text


def test_no_flat_file_is_left_to_materialize_or_swap():
    from src.plan_data_registry import FLAT_PLAN_DATA_CSV_FILES, PLAN_TABLE_DATASET_FILES, YTD_PLAN_DATA_FILES
    assert [f for f in [*FLAT_PLAN_DATA_CSV_FILES, *YTD_PLAN_DATA_FILES] if f not in PLAN_TABLE_DATASET_FILES] == []


def test_the_dataset_fingerprint_follows_the_ytd_tables(tmp_path):
    from src.active_plan import dataset_fingerprint
    write_plan_dataset(tmp_path, "ytd_transactions.csv", TX_HEADER + "2026-01-01,A,B,C,,,-1,,\n")
    before = dataset_fingerprint(tmp_path / "plan.rpx")
    assert "ytd_transactions.csv" in before
    write_plan_dataset(tmp_path, "ytd_transactions.csv", TX_HEADER + "2026-01-01,A,B,C,,,-2,,\n")
    assert dataset_fingerprint(tmp_path / "plan.rpx")["ytd_transactions.csv"] != before["ytd_transactions.csv"]


def test_account_setup_recovery_reads_the_table_and_a_user_named_file(tmp_path):
    from src.server_services.ytd_service import YtdService, YtdServiceContext
    root = tmp_path / "input"
    ytd.write_account_setup(root, [{"Account": "Checking"}])
    other = tmp_path / "old_pkg"
    other.mkdir()
    (other / "ytd_account_setup.csv").write_text(
        "Account,Role,Mapped Investment Account,Prior Year End Date,Prior Year End Balance,Current Value,Current Balance,Notes\n"
        "Checking,Cash / spending,,2025-12-31,5000,6000,6000,\nBrokerage,Investment,Acct,2025-12-31,9000,9500,9500,\n", encoding="utf-8")
    svc = YtdService(YtdServiceContext(
        base_dir=tmp_path / "ws" / "code", plan_data_path=lambda name, prefer_existing=True: root / name,
        path_roots_from_config=lambda: [], server_path_allowed=lambda p: (True, ""), audit=lambda *a, **k: None))
    result = svc.recover_account_setup(force=False, extra_path=str(other))
    assert result["recovered"] and result["source"] == str(other / "ytd_account_setup.csv")
    assert {r["Account"] for r in ytd.read_account_setup(root)} == {"Checking", "Brokerage"}
    assert not (root / "ytd_account_setup.csv").exists()


def test_monarch_upsert_lands_in_the_plan_tables(tmp_path):
    root = tmp_path / "input"
    row = {"Date": "2026-03-04", "Merchant": "K", "Category": "Groceries", "Account": "Checking", "Amount": "-5", "Monarch Id": "mid-1"}
    assert ytd.upsert_transactions_by_monarch_id(root, [row])["added"] == 1
    assert [r["Monarch Id"] for r in plan_dataset_rows(tmp_path, "ytd_transactions.csv")] == ["mid-1"]
    assert plan_dataset_rows(tmp_path, "ytd_import_history.csv")[0]["Mode"]
