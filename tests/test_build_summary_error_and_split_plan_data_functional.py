from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_load_csv_accepts_split_plan_data_without_client_data_anchor(tmp_path):
    from src.config_backend import load_csv

    part = tmp_path / "client_household.csv"
    with part.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([
            ["section", "subsection", "label", "value", "units", "notes"],
            ["Household", "Husband", "current_age", "60", "years", ""],
        ])

    data = load_csv(tmp_path / "client_data.csv")
    assert data["Household"]["Husband"]["current_age"] == "60"


def test_build_failure_error_does_not_mask_traceback_as_missing_summary():
    src = (ROOT / "src/server_services/build_job_service.py").read_text(encoding="utf-8")
    assert "def build_error_message" in src
    assert "returncode != 0" in src
    assert "Build failed before producing a current plan_summary.json" in src
    # The no-summary message should only be used after a zero-return build.
    assert "if returncode != 0" in src
    assert re.search(r"if returncode != 0:.*?if stale_summary:.*?if not summary:", src, re.S)


def test_workbook_builder_validates_active_backend_not_client_data_file_only():
    src = (ROOT / "src/reporting/workbook_builder.py").read_text(encoding="utf-8")
    assert "_ensure_active_plan_data_loaded(data, config_meta)" in src
    assert "No Plan Data found. Add client_data.csv" not in src
