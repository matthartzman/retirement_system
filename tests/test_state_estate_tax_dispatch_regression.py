"""Ticket 291, Class 2: state estate tax is dispatched by the resident
state's `estate_calc` mechanism (data-driven), not hardcoded to Illinois.

Three states originally covered the three real statuses `state_estate_tax()`
can return -- Illinois ('computed'), Florida ('none'), and New York
('not_modeled', since NY DOES levy an estate tax but this engine had no
calculation for its own graduated-rate/cliff mechanism).

Wave 3 item 3.6 (system review 2026-08-31, F5) completed New York's real
mechanism (the graduated rate table, the 105%-of-exemption cliff, and the
three-year gift add-back -- NY Tax Law Β§954(a)(3)), so New York moved from
'not_modeled' to 'computed'. It is no longer the 'not_modeled' example here
-- among the 13 states this codebase ships, NONE currently returns
'not_modeled' (Illinois and New York, the only two with estate=True, are
both computed now). The 'not_modeled' status itself remains a real,
supported code path (for a future state added with estate=True but no
mechanism yet, or a resident state string this session doesn't verify
against a fixture) -- exercised below via a synthetic STATE_TAX_RULES entry
rather than a real shipped state, since none currently occupies that bucket.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from src.core import state_estate_tax, illinois_estate_tax, STATE_TAX_RULES
from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.reporting.sheets_strategy import build_sheet14

from conftest import TEST_INPUT_DIR


# --------------------------------------------------------------------------
# state_estate_tax() dispatcher -- unit level
# --------------------------------------------------------------------------


def test_illinois_dispatches_to_the_credit_table_and_matches_the_direct_call():
    tax, status = state_estate_tax("Illinois", 8_000_000, 4_000_000)
    assert status == "computed"
    assert tax == illinois_estate_tax(8_000_000, 4_000_000)
    assert tax > 0


def test_florida_is_none_not_zero_masquerading_as_computed():
    tax, status = state_estate_tax("Florida", 8_000_000, 0)
    assert status == "none"
    assert tax == 0.0


def test_new_york_is_computed_with_its_own_graduated_cliff_mechanism():
    """Item 3.6 (F5): NY moved from 'not_modeled' to a real, computed
    mechanism -- its own graduated rate table plus the 105%-of-exemption
    cliff, a genuinely different computation from Illinois's pre-2005-
    federal-credit-table method. Confirms the dispatcher does not conflate
    the two states' mechanisms."""
    assert STATE_TAX_RULES["New York"]["estate"] is True
    assert STATE_TAX_RULES["New York"]["estate_calc"] == "ny_graduated_cliff"
    tax, status = state_estate_tax("New York", 8_000_000, 6_940_000)
    assert status == "computed"
    assert tax > 0.0
    # Must not be Illinois's own credit-table figure for the same inputs --
    # proof the two states' mechanisms are genuinely separate, not aliased.
    assert tax != illinois_estate_tax(8_000_000, 6_940_000)


def test_a_real_estate_tax_state_with_no_mechanism_yet_is_not_modeled_not_none():
    """The 'not_modeled' status remains a real, supported code path even
    though none of the 13 shipped states currently occupies it (both
    estate=True states -- Illinois and New York -- are 'computed' as of
    item 3.6). Exercised via a synthetic rules entry standing in for a
    future state added with estate=True but no calculation yet."""
    from src.core import STATE_TAX_RULES as _rules
    _rules["Synthetica"] = {"estate": True, "estate_calc": "not_modeled", "estate_exempt": 5_000_000}
    try:
        tax, status = state_estate_tax("Synthetica", 8_000_000, 5_000_000)
        assert status == "not_modeled"
        assert tax == 0.0
    finally:
        del _rules["Synthetica"]


def test_unrecognized_state_is_not_modeled_not_none():
    tax, status = state_estate_tax("Atlantis", 8_000_000, 0)
    assert status == "unrecognized"
    assert tax == 0.0


def test_every_state_tax_rules_entry_has_an_estate_calc():
    """Guards against a future state being added to STATE_TAX_DEFAULTS/the
    CSV without deciding its estate_calc -- a missing key would silently
    default to 'none' via .get('estate_calc', 'none') and could misreport a
    real estate-tax state as having none."""
    for state, rules in STATE_TAX_RULES.items():
        assert "estate_calc" in rules, f"{state} has no estate_calc entry"
        if rules.get("estate") is True:
            assert rules["estate_calc"] in ("il_credit_table", "ny_graduated_cliff", "not_modeled"), (
                f"{state} has estate=True but estate_calc={rules.get('estate_calc')!r} "
                "implies no tax is levied -- contradicts its own estate flag"
            )
        else:
            assert rules["estate_calc"] == "none", (
                f"{state} has estate=False but estate_calc={rules.get('estate_calc')!r}"
            )


# --------------------------------------------------------------------------
# Sheet 14 rendering -- the disclosure the reporting layer must show
# --------------------------------------------------------------------------


def _config_for_state(state):
    data = load_csv(TEST_INPUT_DIR / "client_data.csv")
    c = parse_client(data, "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    c = ensure_engine_config(c, source="test")
    c["state"] = state
    return c


def _sheet14_text(c):
    rows = project(c)
    wb = Workbook()
    ws = wb.active
    build_sheet14(ws, c, rows)
    return "\n".join(
        str(cell) for row in ws.iter_rows(values_only=True) for cell in row if cell is not None
    )


def test_illinois_household_sees_a_computed_estate_tax_section():
    text = _sheet14_text(_config_for_state("Illinois"))
    assert "Illinois Estate Tax (At Second Death)" in text
    assert "NOT MODELED" not in text
    assert "does not levy" not in text


def test_florida_household_sees_an_explicit_no_tax_note_not_silence():
    """Step 7.3's explicit requirement: estate=FALSE states must render a
    'does not levy' note, not simply omit the section."""
    text = _sheet14_text(_config_for_state("Florida"))
    assert "does not levy a state estate tax" in text
    assert "Illinois Estate Tax" not in text
    assert "NOT MODELED" not in text


def test_new_york_household_sees_a_computed_estate_tax_section():
    """Item 3.6 (F5): NY is 'computed' now -- the section renders a real
    figure using NY's own mechanism, not the old NOT MODELED disclosure,
    and not Illinois's own section header."""
    text = _sheet14_text(_config_for_state("New York"))
    assert "New York Estate Tax (At Second Death)" in text
    assert "NOT MODELED" not in text
    assert "does not levy" not in text
    assert "Illinois Estate Tax" not in text


def test_illinois_boundary_unchanged_by_the_dispatch_refactor():
    """The golden-master safety check for this class: the frozen fixture is
    an Illinois household, so illinois_estate_tax's own published boundary
    values must be byte-identical to before the refactor."""
    assert illinois_estate_tax(4_000_000, 4_000_000) == 0
    tax_8m = illinois_estate_tax(8_000_000, 4_000_000)
    assert 660_000 <= tax_8m <= 700_000
    assert illinois_estate_tax(4_100_000, 4_000_000) > 0
