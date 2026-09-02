"""Item 3.2 Option 2 (docs/superpowers/specs/2026-09-02-roth-phase-varying-
conversion-design.md): a configurable PHASE_VARYING Roth conversion strategy
that steps its target bracket rate down by Social Security claim year.
"""
from __future__ import annotations

import pytest

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
import src.planning_engines as planning_engines
from src.planning_engines import (
    _roth_resolve_target_rate,
    optimize_roth_conversion_strategy,
    project,
)


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 10)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    return c


def test_resolve_target_rate_no_schedule_returns_default():
    assert _roth_resolve_target_rate({}, 2030, 0.24) == 0.24


def test_resolve_target_rate_picks_first_boundary_at_or_after_year():
    c = {"roth_phase_schedule": [(2030, 0.24), (2035, 0.22), (2040, 0.12)]}
    assert _roth_resolve_target_rate(c, 2025, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2030, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2031, 0.99) == 0.22
    assert _roth_resolve_target_rate(c, 2035, 0.99) == 0.22


def test_resolve_target_rate_uses_last_rate_past_final_boundary():
    c = {"roth_phase_schedule": [(2030, 0.24), (2035, 0.22)]}
    assert _roth_resolve_target_rate(c, 2036, 0.99) == 0.22
    assert _roth_resolve_target_rate(c, 2099, 0.99) == 0.22


def test_resolve_target_rate_single_tuple_schedule():
    c = {"roth_phase_schedule": [(2030, 0.24)]}
    assert _roth_resolve_target_rate(c, 2025, 0.99) == 0.24
    assert _roth_resolve_target_rate(c, 2031, 0.99) == 0.24


def test_plan_roth_conversion_flat_rate_unaffected_by_new_helper():
    # No roth_phase_schedule set (every existing candidate) -- confirm the
    # rewrite of the target_rate line in plan_roth_conversion changed nothing
    # about default flat-rate fill_to_bracket behavior.
    c = _base_config()
    c["roth_policy"] = "fill_to_bracket"
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    rows = project(c)
    assert any(float(r.get("roth_conv", 0.0) or 0.0) > 0 for r in rows)


from src.planning_engines import _roth_strategy_candidate_specs, conversion_window_end_year


def _phase_varying_spec(specs):
    matches = [s for s in specs if s.get('strategy_code') == 'PHASE_VARYING']
    assert len(matches) == 1, f"expected exactly one PHASE_VARYING spec, got {len(matches)}"
    return matches[0]


def test_phase_varying_absent_when_bracket_strategy_is_something_else():
    c = _base_config()
    c["roth_bracket_strategy"] = "FILL_TARGET_BRACKET"
    specs = _roth_strategy_candidate_specs(c)
    assert not any(s.get('strategy_code') == 'PHASE_VARYING' for s in specs)


def test_phase_varying_present_in_full_optimizer_sweep():
    c = _base_config()
    c["roth_bracket_strategy"] = "OPTIMIZER_CHOOSES"
    specs = _roth_strategy_candidate_specs(c)
    spec = _phase_varying_spec(specs)
    assert spec['policy'] == 'fill_to_bracket'
    assert spec['target_rate'] is None
    assert 'roth_phase_schedule' in spec['overrides']


def test_phase_varying_selectable_directly():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    specs = _roth_strategy_candidate_specs(c)
    assert len(specs) == 1
    _phase_varying_spec(specs)


def test_phase_varying_three_phase_schedule_for_couple_with_distinct_claim_years():
    # Frozen fixture: h_dob_yr=1962, w_dob_yr=1961, both claim_age=69 ->
    # w claims 2030, h claims 2031 (distinct years, w first).
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2030, 0.24), (2031, 0.22), (window_end, 0.12)]


def test_phase_varying_two_phase_schedule_when_configured():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 2
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2030, 0.24), (window_end, 0.22)]


def test_phase_varying_three_phase_degrades_to_two_for_single_member_household():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    c["members"] = [c["members"][0]]  # simulate single-member household
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2031, 0.24), (window_end, 0.22)]


def test_phase_varying_three_phase_degrades_to_two_for_same_claim_year_couple():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 3
    c["w_dob_yr"] = c["h_dob_yr"]
    c["w_ss_claim_age"] = c["h_ss_claim_age"]
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    window_end = conversion_window_end_year(c)
    assert schedule == [(2031, 0.24), (window_end, 0.22)]


def test_phase_varying_uses_configured_rates():
    c = _base_config()
    c["roth_bracket_strategy"] = "PHASE_VARYING"
    c["roth_phase_count"] = 2
    c["roth_phase_rate_1"] = 0.32
    c["roth_phase_rate_2"] = 0.24
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    assert schedule[0][1] == 0.32
    assert schedule[1][1] == 0.24


def test_phase_varying_minimal_config_never_crashes():
    # A hand-built Mapping missing h_dob_yr/h_ss_claim_age/members entirely
    # still yields a valid (if degenerate) schedule, never a crash.
    c = {"roth_bracket_strategy": "PHASE_VARYING", "roth_policy": "none",
         "plan_start": 2026, "roth_max_conversion_years": 10,
         "rmd_start_age": 75, "conv_window_offset": -1,
         "roth_fixed_amount": 50000, "roth_target_rate": 0.22}
    spec = _phase_varying_spec(_roth_strategy_candidate_specs(c))
    schedule = spec['overrides']['roth_phase_schedule']
    assert len(schedule) == 2
    assert schedule[0][1] == 0.24


def test_parse_client_sets_phase_config_defaults():
    c = _base_config()
    assert c['roth_phase_rate_1'] == pytest.approx(0.24)
    assert c['roth_phase_rate_2'] == pytest.approx(0.22)
    assert c['roth_phase_rate_3'] == pytest.approx(0.12)
    assert c['roth_phase_count'] == 3


def test_parse_client_accepts_phase_varying_as_bracket_strategy():
    from src.data_io import load_csv, parse_client as _parse_client
    raw = load_csv(TEST_INPUT_DIR / "client_data.csv")
    # Directly inject the CSV row parse_client() reads via _v(), mirroring
    # how the frozen fixture's own client_policy.csv rows are structured.
    raw['Withdrawal Policy']['Roth Conversion']['roth_bracket_strategy'] = 'PHASE_VARYING'
    c = _parse_client(raw, "")
    assert c['roth_bracket_strategy'] == 'PHASE_VARYING'


def _fake_specs_with_phase_varying_only(schedule):
    return [{
        'label': 'Phase test', 'policy': 'fill_to_bracket', 'strategy_code': 'PHASE_VARYING',
        'target_rate': None, 'fixed_amount': None,
        'overrides': {'roth_phase_schedule': schedule},
    }]


def test_auto_optimize_propagates_full_overrides_not_just_target_rate(monkeypatch):
    c = _base_config()
    c['roth_policy'] = 'optimize_terminal_tax'  # auto_optimize branch
    schedule = [(int(c['plan_start']) + 3, 0.24), (int(c['plan_start']) + 8, 0.12)]
    monkeypatch.setattr(
        planning_engines, '_roth_strategy_candidate_specs',
        lambda cfg: _fake_specs_with_phase_varying_only(schedule),
    )
    c = optimize_roth_conversion_strategy(c)
    assert c['roth_optimization']['selected_strategy_code'] == 'PHASE_VARYING'
    assert c['roth_phase_schedule'] == schedule


def test_direct_selection_propagates_full_overrides_not_just_target_rate(monkeypatch):
    c = _base_config()
    c['roth_policy'] = 'fill_to_bracket'  # explicit-selection branch (not auto_optimize)
    c['roth_bracket_strategy'] = 'PHASE_VARYING'
    schedule = [(int(c['plan_start']) + 3, 0.24), (int(c['plan_start']) + 8, 0.12)]
    monkeypatch.setattr(
        planning_engines, '_roth_strategy_candidate_specs',
        lambda cfg: _fake_specs_with_phase_varying_only(schedule),
    )
    c = optimize_roth_conversion_strategy(c)
    assert c['roth_optimization']['selected_strategy_code'] == 'PHASE_VARYING'
    assert c['roth_phase_schedule'] == schedule
