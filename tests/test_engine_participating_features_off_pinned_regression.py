"""WP1.5: pin what the projection does with each engine-participating feature off.

"Off" means the engine ignores the feature while its data stays in the plan
(design 2026-10-04 section 3). Each test flips the one switch on the frozen
sample plan and pins the projection-side effect, so a later change to how a
switch is stored (WP4) cannot silently change a number.

Disability income is pinned in test_engine_module_gate_agrees_with_sheets_
regression.py (benefit years with the gate on/off); not repeated here.
"""
from __future__ import annotations

from datetime import date

import src.module_catalog as mc
from src.data_io import parse_client
from tests.golden_pricing import frozen_holdings_prices
from tests.plan_fixture import plan_data
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace


def _config(**switches):
    """Sample plan with ``{module_key: bool}`` written to its Optional Functions."""
    data = plan_data("sample_frozen")
    opts = data["Optional Functions"][""]
    for key, on in switches.items():
        opts[key] = "TRUE" if on else "FALSE"
    return data, parse_client(data, "")


def _project(c):
    from src.planning_engines import project
    with empty_workspace(), frozen_holdings_prices():
        return project(c)


def test_every_engine_participant_is_pinned_here_or_named():
    pinned = {"equity_compensation", "business_succession", "housing_location_search",
              "spending_tracker_ytd", "disability_income_insurance"}
    assert set(mc.engine_participants()) == pinned


def test_equity_compensation_off_projects_as_if_no_grants():
    _, on = _config(equity_compensation=True)
    _, off = _config(equity_compensation=False)
    assert off["equity_comp"] and on["equity_comp"]          # data kept either way
    rows_on, rows_off = _project(on), _project(off)
    assert rows_on != rows_off                                # the switch matters
    no_grants = dict(on)
    no_grants["equity_comp"] = []
    assert _project(no_grants) == rows_off                    # off == ignored


def test_business_succession_off_adds_nothing_to_the_estate():
    from src.after_tax import business_taxable_estate_value
    _, on = _config(business_succession=True)
    _, off = _config(business_succession=False)
    assert on["business_succession"] and off["business_succession"]  # data kept
    assert business_taxable_estate_value(on) > 0.0
    assert business_taxable_estate_value(off) == 0.0
    # Pinned current behavior: this read needs an explicit ON; an absent
    # toggle reads off here (unlike feature_enabled's default-on).
    absent = dict(on)
    absent["opt"] = {}
    assert business_taxable_estate_value(absent) == 0.0


def test_next_housing_move_off_blanks_the_engine_view_only():
    data, on = _config(housing_location_search=True)
    data_off, off = _config(housing_location_search=False)
    assert len(on["next_housing_steps"]) >= 1
    assert off["home_sale_yr"] == 0
    assert off["home_sale_splits"] == []
    assert off["next_housing_steps"] == []
    assert off["residency_schedule"] == []
    # the rows themselves are untouched, so switching back on restores them
    assert {k: v for k, v in data.items() if k != "Optional Functions"} == \
           {k: v for k, v in data_off.items() if k != "Optional Functions"}


def test_spending_tracker_off_turns_off_the_ytd_flow_blend():
    from src.ytd_projection_blend import compute_current_year_overrides
    today = date(2026, 6, 30)
    _, on = _config(spending_tracker_ytd=True)
    _, off = _config(spending_tracker_ytd=False)
    meta_on = compute_current_year_overrides(on, "/nonexistent", today=today)["ytd_blend_applied"]
    meta_off = compute_current_year_overrides(off, "/nonexistent", today=today)["ytd_blend_applied"]
    assert meta_on["flow_blend_enabled"] is True
    assert meta_off["flow_blend_enabled"] is False
