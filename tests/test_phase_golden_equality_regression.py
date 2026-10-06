"""WP0.1 golden before/after equality across the file-elimination phases.

Builds the frozen sample plan and the demo plan in a throwaway workspace and
compares full-row engine output, required-sheet workbook cell values, headline
plan_summary.json KPIs and the spending-history/YTD aggregates against the
baseline committed in tests/fixtures/golden_phase_baseline/. A failure means a
phase changed observable output; fix the phase, do not re-record. The only
sanctioned re-record is ``python tools/golden_compare.py record --reason ...``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import golden_compare as gc  # noqa: E402

pytestmark = [pytest.mark.slow, pytest.mark.e2e, pytest.mark.golden_master]


@pytest.mark.parametrize("plan", sorted(gc.PLAN_SOURCES))
def test_live_output_equals_baseline(plan):
    base = json.loads(gc._baseline_path(plan).read_text(encoding="utf-8"))
    live = json.loads(json.dumps(gc.capture(plan)))
    problems = gc.diff(base, live)
    assert not problems, f"[{plan}] golden drift:\n" + "\n".join(problems)


@pytest.mark.parametrize("plan", sorted(gc.PLAN_SOURCES))
def test_baseline_covers_spending_history_and_ytd(plan):
    base = json.loads(gc._baseline_path(plan).read_text(encoding="utf-8"))
    assert base["engine_rows"], "baseline has no engine rows"
    assert base["spending_ytd"]["n_transactions"] > 0, "baseline lacks YTD transactions"
    assert base["spending_ytd"]["group_actuals"], "baseline lacks spending history actuals"
    assert all(base["workbook_sheets"].get(s) for s in base["workbook_sheets"]), "a required sheet is empty"
    assert base["headline_kpis"], "baseline lacks plan_summary KPIs"
