"""Ticket 291, Class 3: cost-of-living comparisons must read relative to the
household's own resident state, not present Illinois as a neutral/implicit
baseline.

The underlying computation (tgt_col[key] / cur_col[key] in build_sheet13)
was already state-relative before this ticket -- the defect was the
DISCLOSURE text unconditionally saying "indexed to Illinois = 1.00"
regardless of which state the household actually lives in. For a Florida
household reading a number that's already relative to Florida, "Illinois"
appearing anywhere in that sentence is confusing, alienating, and exactly
the pattern this ticket removes elsewhere -- but the disclosure that the
underlying STATE_COL_FACTORS table is itself Illinois-derived data must
still appear somewhere, deliberately, per the human's own decision: dropping
it would relabel Illinois-derived data as neutral, which is the same defect
in new clothes.
"""
from __future__ import annotations

from openpyxl import Workbook

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet13

from conftest import TEST_INPUT_DIR


def _config_for_state(state):
    data = load_csv(TEST_INPUT_DIR / "client_data.csv")
    c = parse_client(data, "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    c = ensure_engine_config(c, source="test")
    c["state"] = state
    return c


def _sheet13_text(state):
    c = _config_for_state(state)
    rows = project(c)
    wb = Workbook()
    ws = wb.active
    build_sheet13(ws, c, rows)
    return "\n".join(
        str(cell) for row in ws.iter_rows(values_only=True) for cell in row if cell is not None
    )


def test_florida_household_comparison_names_florida_as_the_basis_not_illinois():
    text = _sheet13_text("Florida")
    assert "vs. Florida" in text or "vs Florida" in text
    assert "Florida (Current)" in text
    # The comparison itself must never present Illinois as the implicit
    # baseline for a Florida household -- but the deliberate disclosure that
    # the underlying source data is Illinois-derived is required and stays.
    assert "indexed to Illinois = 1.00" not in text
    assert "Illinois-derived data" in text


def test_florida_household_retirement_callout_does_not_claim_illinois_exempts_it():
    """Florida ALSO exempts retirement income (like Illinois), so this
    specifically tests the callout picks Florida's own real exemption status
    rather than defaulting to a hardcoded Illinois assumption -- covered
    separately by the North-Carolina-shaped case below, which does not
    exempt it."""
    text = _sheet13_text("Florida")
    assert "Florida exempts" in text
    assert "Illinois exempts" not in text


def test_north_carolina_household_retirement_callout_is_accurate_not_the_illinois_default():
    """North Carolina does NOT exempt retirement income -- the pre-fix
    callout would have said "Illinois exempts..." regardless, which is
    simply false for this household."""
    text = _sheet13_text("North Carolina")
    assert "North Carolina taxes qualified retirement income" in text
    assert "Illinois exempts" not in text
    assert "North Carolina exempts" not in text


def test_illinois_household_still_reads_correctly_unchanged_claim():
    """Golden-master-adjacent safety check: an Illinois household's own
    callout text must still be accurate (it genuinely does exempt retirement
    income), not accidentally broken by making the callout state-aware."""
    text = _sheet13_text("Illinois")
    assert "Illinois exempts" in text
    assert "even in Illinois" in text


def test_new_york_estate_tax_not_modeled_flagged_not_silently_estimated():
    """Class 2 dispatches New York's estate tax to 'not_modeled'. This
    cross-state comparison table must not contradict that by silently
    applying the Illinois-only 8%-of-excess heuristic to New York."""
    text = _sheet13_text("New York")
    assert "Not modeled *" in text
    assert "does not yet model" in text
