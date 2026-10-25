"""Trends net worth must read assets/mortgage/liabilities from plan.rpx, not input CSVs (WP6 regression)."""
from datetime import date

from financial_trends_reporter.trends_metrics import compute_snapshot
from src.plan_datasets import write_dataset_rows_for_input_dir
from tests.plan_fixture import make_plan


def test_net_worth_reads_plan_file_when_csvs_absent(tmp_path):
    ws = make_plan(tmp_path)
    write_dataset_rows_for_input_dir(ws.input_dir, "liabilities", [
        {"liability_id": "l1", "type": "loan", "label": "Car", "balance": "$10,000"}])
    for f in ws.input_dir.glob("*.csv"):
        f.unlink()
    nw = compute_snapshot(ws.root, today=date(2026, 9, 30))["net_worth"]
    assert nw["home"] == 1313000.0
    assert nw["other_assets"] > 0
    assert nw["mortgage"] > 0
    assert nw["liabilities"] >= nw["mortgage"] + 10000.0


def test_legacy_client_files_liabilities_are_ignored_when_plan_has_none(tmp_path):
    """ARC-004: a paid-off household must not see old converted client_liabilities.csv balances."""
    from src import config_backend

    ws = make_plan(tmp_path)
    write_dataset_rows_for_input_dir(ws.input_dir, "liabilities", [])
    legacy = tmp_path / "legacy.db"
    config_backend.init_sqlite(legacy)
    from src.sqlite_util import connect as sqlite_connect
    with sqlite_connect(legacy) as con:
        con.execute("INSERT INTO client_files(file_name, content) VALUES(?,?)",
                    ("client_liabilities.csv", "balance\n999999\n"))
    nw = compute_snapshot(ws.root, today=date(2026, 9, 30))["net_worth"]
    assert nw["liabilities"] < 999999.0
