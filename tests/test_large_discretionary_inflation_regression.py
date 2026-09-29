"""WI-310 / FIN-011: Large Discretionary amounts are plan-start dollars, inflated to their year."""
from src.data_io import build_plan_from_json
from src.large_discretionary import LdItem, ld_budget_for_year, expand_repeatable
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from tests.synthetic_plans import _no_voluntary_roth, base_plan


def _lumps(ld_lump):
    c = ensure_engine_config(build_plan_from_json(base_plan(), ""), source="test")
    _no_voluntary_roth(c)
    c["lump"] = dict(ld_lump)
    c["lump_by_tracking_type"] = {y: {"Large Discretionary": a} for y, a in ld_lump.items()}
    return {r["year"]: r for r in project(c)}, c


def test_ld_row_ten_years_out_projects_inflated_lump():
    rows, c = _lumps({2036: 10_000.0})
    assert abs(rows[2036]["lump"] - 10_000.0 * (1 + c["inf"]) ** 10) < 1.0


def test_ld_row_in_plan_start_year_is_not_inflated():
    rows, _ = _lumps({2026: 10_000.0})
    assert abs(rows[2026]["lump"] - 10_000.0) < 0.01


def test_budget_display_stays_in_entered_dollars():
    items = [LdItem("Weddings", 10_000.0, 2036, "")]
    assert ld_budget_for_year(items, 2036) == 10_000.0


def test_migrated_repeating_row_inflates_each_year():
    items, _ = expand_repeatable("Auto", 5_000.0, 2030, 2032)
    rows, c = _lumps({i.year: i.amount for i in items})
    for i in items:
        assert abs(rows[i.year]["lump"] - 5_000.0 * (1 + c["inf"]) ** (i.year - 2026)) < 1.0
