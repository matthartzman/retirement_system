"""M5: a projection run (Roth optimizer on) gives the same rows on the first and on later runs
in one process; no module-level cache or state may leak between runs."""
from __future__ import annotations

import json
from pathlib import Path

from src.data_io import load_csv
from src.planning_engines import project
from src.report_compute import prepare_config_from_sectioned_data

PLAN = Path(__file__).resolve().parent / "fixtures" / "csv_exchange" / "sample_plan_frozen" / "client_data.csv"


def _run() -> str:
    c = prepare_config_from_sectioned_data(load_csv(PLAN), "", optimize_roth=True)
    return json.dumps(project(c), default=str, sort_keys=True)


def test_first_and_second_run_agree():
    assert _run() == _run()
