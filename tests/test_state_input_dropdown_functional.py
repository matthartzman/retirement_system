"""Every "state" Plan Data input is a pull-down of the 50 states plus DC.

DC is not one of the 50 states, so it must appear as its own explicit
51st entry rather than being folded silently into the state count or
omitted altogether.
"""
from __future__ import annotations

from pathlib import Path

from src.server.app_core import _choice_options_for_config_row
from src.us_states import (
    US_STATES,
    DISTRICT_OF_COLUMBIA,
    state_abbr_choice_options,
    state_name_choice_options,
    states_and_dc,
)
from tests._decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_fifty_states_plus_dc_as_a_separate_entry():
    combined = states_and_dc()
    assert len(US_STATES) == 50
    assert combined[-1] == DISTRICT_OF_COLUMBIA
    assert len(combined) == 51
    assert len(set(combined)) == 51


def test_state_name_and_abbr_choice_lists_cover_all_fifty_one():
    names = state_name_choice_options()
    abbrs = state_abbr_choice_options()
    assert len(names) == 51
    assert len(abbrs) == 51
    assert {o["value"] for o in names} == {n for n, _ in states_and_dc()}
    assert {o["value"] for o in abbrs} == {a for _, a in states_and_dc()}
    assert any(o["value"] == "District of Columbia" for o in names)
    assert any(o["value"] == "DC" for o in abbrs)


def test_residence_state_and_housing_state_use_full_state_names():
    for section, subsection, label in [
        ("Household", "", "residence_state"),
        ("Housing", "next_step_1", "state"),
        ("Housing", "next_step_2", "state"),
    ]:
        opts = _choice_options_for_config_row(section, subsection, label, "text", "", {})
        assert len(opts) == 51
        assert {o["value"] for o in opts} == {n for n, _ in states_and_dc()}


def test_target_state_uses_abbreviations():
    opts = _choice_options_for_config_row("State Comparison", "", "target_state", "text", "", {})
    assert len(opts) == 51
    assert {o["value"] for o in opts} == {a for _, a in states_and_dc()}


def test_dashboard_js_renders_state_fields_as_dropdowns_not_free_text():
    main_js = dashboard_js_text()
    state_js = (
        ROOT / "frontend" / "js" / "dashboard_decomp_state_inputs.js"
    ).read_text(encoding="utf-8")
    assert "STATE_INPUT_LABELS.has(lblNorm)" in main_js
    assert 'new Set(["state", "residence_state", "target_state"])' in state_js
    assert "District of Columbia" in state_js
