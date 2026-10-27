"""The HSA schedule may not plan a draw in the second-death year or later.

Regression: the default `second_death_p90` deadline clamps to the plan horizon, which is
usually the second-death year itself. In that year the projection consolidates the HSA
into the estate before the year's withdrawals, so a draw scheduled there can never be
taken -- the optimizer planned money into a year the engine cannot reach and reported
a deadline the account could not meet.
"""
import openpyxl
import pytest

from src.hsa_schedule import (
    _schedule_years, build_schedule, generate_default_schedule, last_draw_year,
    resolve_consume_by_year, second_death_year,
)


def _config(**kw):
    c = {
        "plan_start": 2026, "plan_end": 2050, "hsa_consume_by": "2050", "ret": 0.05,
        "household_size": 2, "members": [{"dob_yr": 1960}, {"dob_yr": 1962}],
        "h_death_yr": 2040, "w_death_yr": 2045,
        "hsa_beneficiary_type": "spouse", "hsa_withdrawal_mode": "optimize",
        "hsa_ids": ["H"], "balances": {"H": 100_000.0},
    }
    c.update(kw)
    return c


def _rows():
    rows = [{"year": y, "filing": "MFJ", "effective_marginal_rate": 0.22, "irmaa_tier": 0}
            for y in range(2026, 2051)]
    rows[0]["hsa_nw"] = 100_000.0
    return rows


def test_the_second_death_year_is_the_later_of_the_two():
    assert second_death_year(_config()) == 2045
    assert second_death_year(_config(h_death_yr=2046, w_death_yr=2041)) == 2046


@pytest.mark.parametrize("override", [
    {"household_size": 1, "members": [{"dob_yr": 1960}]},   # no consolidation event
    {"h_death_yr": 0},
    {"w_death_yr": None},
])
def test_no_second_death_year_when_the_projection_has_none(override):
    assert second_death_year(_config(**override)) is None


def test_the_last_draw_year_stops_before_the_second_death():
    c = _config()
    assert resolve_consume_by_year(c, _rows()) == 2050          # the disclosed deadline is untouched
    assert last_draw_year(c, _rows()) == 2044
    assert _schedule_years(c, _rows())[-1] == 2044


def test_an_earlier_deadline_still_wins_and_a_missing_death_year_changes_nothing():
    assert last_draw_year(_config(hsa_consume_by="2040"), _rows()) == 2040
    assert last_draw_year(_config(h_death_yr=0), _rows()) == 2050


def test_the_schedule_plans_nothing_from_the_second_death_year_on_and_still_closes():
    out = build_schedule(_config(), _rows())
    assert max(out["by_year"]) == 2044
    assert out["feasibility"] == "feasible"
    assert out["residual"] == pytest.approx(0.0, abs=1e-6)
    assert sum(1 for v in out["by_year"].values() if v > 0) > 0


def test_the_default_level_schedule_also_ends_before_the_second_death():
    years = [r["year"] for r in generate_default_schedule(_config())]
    assert years[-1] == 2044


def test_the_sheet_says_why_the_table_stops_before_the_deadline():
    from src.reporting.sheets_strategy import build_hsa_schedule_section
    ws = openpyxl.Workbook().active
    build_hsa_schedule_section(ws, _config(), _rows(), 1)
    text = "\n".join(str(cell) for row in ws.iter_rows(values_only=True) for cell in row if cell is not None)
    assert "Draws end in 2044" in text
    assert "second death falls in 2045" in text
