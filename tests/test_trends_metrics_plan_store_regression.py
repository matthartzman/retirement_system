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
