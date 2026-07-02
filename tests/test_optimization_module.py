"""Unit tests for src/optimization.py.

Focuses on direct-call coverage of the pure/near-pure helper functions
(_parse_number, _normalize_horizon, _preset_adjustment, _horizon_adjustment,
get_correlation, build_covariance_matrix, auto_risk_score, risk_to_equity_pct,
compute_human_capital, apply_glide_path, _normalized_split), plus smoke tests
for the larger config-driven entry points (compute_allocation_coverage,
compute_optimal_allocation, optimize_equity_sleeve) using the repo's sample
client_data.csv fixture.

Notes on actual (as opposed to assumed) behavior, confirmed by direct
experimentation against this module before writing assertions:

- ``build_covariance_matrix`` returns a true covariance matrix (variance,
  i.e. vol**2, on the diagonal), NOT a correlation matrix. Its diagonal is
  NOT 1.0 unless every asset class happens to have vol == 1.0. Only
  ``get_correlation`` guarantees a 1.0 "diagonal" (a == b -> 1.0). Tests
  below assert this real behavior rather than the "1.0 diagonal" assumption.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import src.optimization as opt
from src.data_io import load_csv, parse_client
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


# ---------------------------------------------------------------------------
# _parse_number
# ---------------------------------------------------------------------------


def test_parse_number_plain_float_string():
    assert opt._parse_number("42.5") == 42.5


def test_parse_number_percentage_string_divides_by_100():
    assert opt._parse_number("5%") == pytest.approx(0.05)


def test_parse_number_strips_commas_and_whitespace():
    assert opt._parse_number(" 1,234.5 ") == pytest.approx(1234.5)


def test_parse_number_none_returns_default():
    assert opt._parse_number(None, 42) == 42


def test_parse_number_empty_string_returns_default():
    assert opt._parse_number("", "fallback") == "fallback"
    assert opt._parse_number("   ") is None


def test_parse_number_unparseable_returns_default():
    assert opt._parse_number("not-a-number", "default") == "default"


def test_parse_number_numeric_input_passthrough():
    assert opt._parse_number(7) == 7.0


# ---------------------------------------------------------------------------
# _normalize_horizon
# ---------------------------------------------------------------------------


def test_normalize_horizon_exact_supported_value():
    assert opt._normalize_horizon(30) == 30
    assert opt._normalize_horizon(1) == 1


def test_normalize_horizon_rounds_to_nearest_supported():
    # Supported horizons: (1, 3, 5, 10, 20, 25, 30). 4 is equidistant-ish but
    # closer to 5 (1 away) than to 3 (1 away too) -- min() picks first tie,
    # so confirm the real tie-break behavior rather than assuming.
    assert opt._normalize_horizon(2) == 1
    assert opt._normalize_horizon(7) == 5
    assert opt._normalize_horizon(15) == 10
    assert opt._normalize_horizon(28) == 30


def test_normalize_horizon_none_defaults_to_30():
    assert opt._normalize_horizon(None) == 30


def test_normalize_horizon_out_of_range_clamps_to_nearest():
    assert opt._normalize_horizon(1000) == 30
    assert opt._normalize_horizon(-5) == 1


# ---------------------------------------------------------------------------
# _preset_adjustment
# ---------------------------------------------------------------------------


def test_preset_adjustment_conservative():
    assert opt._preset_adjustment("CONSERVATIVE") == (-0.010, 1.08)


def test_preset_adjustment_aggressive():
    assert opt._preset_adjustment("aggressive") == (0.010, 0.96)


def test_preset_adjustment_baseline_and_default():
    assert opt._preset_adjustment("BASELINE") == (0.0, 1.0)
    assert opt._preset_adjustment(None) == (0.0, 1.0)
    assert opt._preset_adjustment("") == (0.0, 1.0)


def test_preset_adjustment_unknown_falls_back_to_baseline():
    assert opt._preset_adjustment("not-a-real-preset") == (0.0, 1.0)


def test_preset_adjustment_case_and_whitespace_insensitive():
    assert opt._preset_adjustment("  conservative  ") == (-0.010, 1.08)


# ---------------------------------------------------------------------------
# _horizon_adjustment
# ---------------------------------------------------------------------------


def test_horizon_adjustment_equity_class_short_horizon_lower_return_higher_vol():
    ret_factor, vol_factor = opt._horizon_adjustment("US Large Cap", 1)
    assert ret_factor == pytest.approx(0.70)
    assert vol_factor == pytest.approx(1.22)


def test_horizon_adjustment_equity_class_full_horizon_is_baseline():
    ret_factor, vol_factor = opt._horizon_adjustment("US Large Cap", 30)
    assert ret_factor == pytest.approx(1.00)
    assert vol_factor == pytest.approx(1.00)


def test_horizon_adjustment_low_duration_class_has_gentler_adjustment():
    ret_factor, vol_factor = opt._horizon_adjustment("Cash", 1)
    assert ret_factor == pytest.approx(1.00)
    assert vol_factor == pytest.approx(1.02)


def test_horizon_adjustment_core_bond_class_uses_bond_curve():
    ret_factor, vol_factor = opt._horizon_adjustment("Bonds", 1)
    assert ret_factor == pytest.approx(0.95)
    assert vol_factor == pytest.approx(1.08)


def test_horizon_adjustment_unsupported_horizon_falls_back_to_baseline_factor():
    # horizon 7 isn't a key in the ret_factor/vol_factor dicts, so .get()
    # falls back to the 1.00 default for a plain equity class.
    ret_factor, vol_factor = opt._horizon_adjustment("US Large Cap", 7)
    assert ret_factor == pytest.approx(1.00)
    assert vol_factor == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# get_correlation / build_covariance_matrix
# ---------------------------------------------------------------------------


def test_get_correlation_same_class_is_one():
    assert opt.get_correlation("US Large Cap", "US Large Cap") == 1.0
    assert opt.get_correlation("Cash", "Cash") == 1.0


def test_get_correlation_is_symmetric_regardless_of_lookup_direction():
    a, b = "US Large Cap", "Bonds"
    assert opt.get_correlation(a, b) == opt.get_correlation(b, a)
    assert opt.get_correlation(a, b) == pytest.approx(-0.20)


def test_get_correlation_unknown_pair_defaults_to_zero():
    assert opt.get_correlation("Not A Class", "Also Not A Class") == 0.0


def test_build_covariance_matrix_is_symmetric():
    classes = ["US Large Cap", "Bonds", "Cash", "REITs"]
    m = opt.build_covariance_matrix(classes)
    assert m.shape == (4, 4)
    assert np.allclose(m, m.T)


def test_build_covariance_matrix_diagonal_is_variance_not_one():
    """Actual behavior: diagonal holds vol**2 (a real covariance matrix),
    not a correlation matrix with a 1.0 diagonal."""
    classes = ["US Large Cap", "Bonds", "Cash"]
    m = opt.build_covariance_matrix(classes)
    expected_variances = [opt.ASSET_CLASSES[c]["vol"] ** 2 for c in classes]
    assert np.allclose(np.diagonal(m), expected_variances)
    # Explicitly confirm the diagonal is NOT 1.0 (contrary to a naive
    # correlation-matrix assumption).
    assert not np.allclose(np.diagonal(m), 1.0)


def test_build_covariance_matrix_off_diagonal_matches_correlation_times_vols():
    classes = ["US Large Cap", "Bonds"]
    m = opt.build_covariance_matrix(classes)
    vol_a = opt.ASSET_CLASSES["US Large Cap"]["vol"]
    vol_b = opt.ASSET_CLASSES["Bonds"]["vol"]
    corr = opt.get_correlation("US Large Cap", "Bonds")
    assert m[0, 1] == pytest.approx(vol_a * vol_b * corr)
    assert m[1, 0] == pytest.approx(m[0, 1])


def test_build_covariance_matrix_single_class():
    m = opt.build_covariance_matrix(["Cash"])
    assert m.shape == (1, 1)
    assert m[0, 0] == pytest.approx(opt.ASSET_CLASSES["Cash"]["vol"] ** 2)


# ---------------------------------------------------------------------------
# auto_risk_score
# ---------------------------------------------------------------------------


def test_auto_risk_score_young_moderate_inputs_scores_high():
    score = opt.auto_risk_score(age=25, withdrawal_rate=0.04, funded_ratio=0.5)
    assert score == pytest.approx(10.0)


def test_auto_risk_score_clamped_to_range_1_to_10():
    low = opt.auto_risk_score(age=200, withdrawal_rate=0.10, funded_ratio=0.0)
    high = opt.auto_risk_score(age=0, withdrawal_rate=0.0, funded_ratio=1.0)
    assert 1.0 <= low <= 10.0
    assert 1.0 <= high <= 10.0
    assert low == pytest.approx(1.0)
    assert high == pytest.approx(10.0)


def test_auto_risk_score_high_withdrawal_rate_reduces_score():
    baseline = opt.auto_risk_score(age=60, withdrawal_rate=0.03, funded_ratio=0.3)
    stressed = opt.auto_risk_score(age=60, withdrawal_rate=0.06, funded_ratio=0.3)
    assert stressed < baseline


def test_auto_risk_score_high_funded_ratio_increases_score():
    low_funded = opt.auto_risk_score(age=60, withdrawal_rate=0.03, funded_ratio=0.1)
    high_funded = opt.auto_risk_score(age=60, withdrawal_rate=0.03, funded_ratio=0.9)
    assert high_funded > low_funded


# ---------------------------------------------------------------------------
# risk_to_equity_pct
# ---------------------------------------------------------------------------


def test_risk_to_equity_pct_floor_at_score_1():
    assert opt.risk_to_equity_pct(1) == pytest.approx(0.20)


def test_risk_to_equity_pct_ceiling_at_score_10():
    assert opt.risk_to_equity_pct(10) == pytest.approx(0.9497, abs=1e-4)


def test_risk_to_equity_pct_midpoint():
    assert opt.risk_to_equity_pct(5) == pytest.approx(0.20 + 4 * 0.0833)


def test_risk_to_equity_pct_out_of_range_scores_clamp():
    assert opt.risk_to_equity_pct(-5) == pytest.approx(0.20)
    assert opt.risk_to_equity_pct(100) == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# compute_human_capital
# ---------------------------------------------------------------------------


def test_compute_human_capital_zero_years_returns_zero():
    assert opt.compute_human_capital(100_000, 0) == 0.0


def test_compute_human_capital_zero_salary_returns_zero():
    assert opt.compute_human_capital(0, 10) == 0.0


def test_compute_human_capital_negative_years_returns_zero():
    assert opt.compute_human_capital(100_000, -5) == 0.0


def test_compute_human_capital_negative_salary_returns_zero():
    assert opt.compute_human_capital(-1, 10) == 0.0


def test_compute_human_capital_single_year_matches_formula():
    pv = opt.compute_human_capital(100_000, 1, stability_factor=0.8, discount_rate=0.03)
    assert pv == pytest.approx(100_000 * 0.8 / 1.03)


def test_compute_human_capital_multi_year_matches_manual_sum():
    salary, years, stability, disc = 120_000, 15, 0.5, 0.03
    expected = sum(salary * stability / (1 + disc) ** t for t in range(1, years + 1))
    assert opt.compute_human_capital(salary, years, stability, disc) == pytest.approx(expected)


def test_compute_human_capital_higher_stability_increases_pv():
    low = opt.compute_human_capital(100_000, 10, stability_factor=0.5)
    high = opt.compute_human_capital(100_000, 10, stability_factor=0.9)
    assert high > low


# ---------------------------------------------------------------------------
# apply_glide_path
# ---------------------------------------------------------------------------


def test_apply_glide_path_static_mode_returns_unchanged():
    assert opt.apply_glide_path(0.6, 5, mode="static") == 0.6
    assert opt.apply_glide_path(0.6, -5, mode="static") == 0.6


def test_apply_glide_path_target_date_far_from_retirement_unchanged():
    # years_to_retirement > 10 -> stay fully at base equity_pct.
    assert opt.apply_glide_path(0.6, 20) == 0.6
    assert opt.apply_glide_path(0.6, 11) == 0.6


def test_apply_glide_path_target_date_approaching_retirement_derisks():
    # 0 < years_to_retirement <= 10: reduce by (10 - years) * 1.5%.
    assert opt.apply_glide_path(0.6, 5) == pytest.approx(0.6 - (10 - 5) * 0.015)
    assert opt.apply_glide_path(0.6, 10) == pytest.approx(0.6)


def test_apply_glide_path_target_date_in_retirement_continues_derisking():
    # years_to_retirement <= 0: reduce by 0.015 * (10 + years_retired), floored at 0.30.
    result = opt.apply_glide_path(0.6, -5)
    assert result == pytest.approx(max(0.30, 0.6 - 0.015 * (10 + 5)))


def test_apply_glide_path_target_date_deep_retirement_hits_floor():
    result = opt.apply_glide_path(0.6, -100)
    assert result == pytest.approx(0.30)


def test_apply_glide_path_default_mode_is_target_date():
    # Default mode argument behaves the same as explicitly passing 'target_date'.
    assert opt.apply_glide_path(0.6, 5) == opt.apply_glide_path(0.6, 5, mode="target_date")


# ---------------------------------------------------------------------------
# _normalized_split
# ---------------------------------------------------------------------------


def test_normalized_split_sums_to_one():
    result = opt._normalized_split(["A", "B"], {"A": 1.0, "B": 3.0})
    assert result["A"] == pytest.approx(0.25)
    assert result["B"] == pytest.approx(0.75)
    assert sum(result.values()) == pytest.approx(1.0)


def test_normalized_split_ignores_classes_not_in_selection():
    result = opt._normalized_split(["A"], {"A": 1.0, "B": 5.0, "C": 5.0})
    assert result == {"A": 1.0}


def test_normalized_split_excludes_non_positive_weights():
    result = opt._normalized_split(["A", "B"], {"A": 1.0, "B": 0.0})
    assert result == {"A": 1.0}


def test_normalized_split_all_zero_returns_empty_dict():
    assert opt._normalized_split(["A", "B"], {"A": 0.0, "B": 0.0}) == {}


def test_normalized_split_empty_classes_returns_empty_dict():
    assert opt._normalized_split([], {"A": 1.0}) == {}


# ---------------------------------------------------------------------------
# compute_allocation_coverage — smoke tests against the sample client config
# ---------------------------------------------------------------------------


def test_compute_allocation_coverage_returns_expected_keys():
    c = sample_config()
    coverage = opt.compute_allocation_coverage(c)
    assert isinstance(coverage, dict)
    expected_keys = {
        "policy", "annuity_factor", "ss_pv", "pension_pv", "annuity_pv", "note_pv",
        "all_guaranteed_income_pv", "fixed_income_coverage_pv",
        "fixed_income_included_sources", "fixed_income_excluded_sources",
        "gross_home_equity", "home_equity_allocation_value",
        "home_equity_reit_coverage_value", "home_equity_excluded",
        "home_equity_counts_toward_reit",
    }
    assert expected_keys.issubset(coverage.keys())


def test_compute_allocation_coverage_pv_values_are_non_negative():
    c = sample_config()
    coverage = opt.compute_allocation_coverage(c)
    for key in ("ss_pv", "pension_pv", "annuity_pv", "note_pv", "fixed_income_coverage_pv"):
        assert coverage[key] >= 0


def test_compute_allocation_coverage_does_not_raise_with_explicit_year():
    c = sample_config()
    coverage = opt.compute_allocation_coverage(c, now_yr=2026)
    assert coverage["annuity_factor"] >= 0


# ---------------------------------------------------------------------------
# compute_optimal_allocation — smoke tests against the sample client config
# ---------------------------------------------------------------------------


def test_compute_optimal_allocation_returns_expected_keys():
    c = sample_config()
    result = opt.compute_optimal_allocation(c)
    expected_keys = {
        "total_targets", "liquid_targets", "equity_pct", "risk_score",
        "human_capital", "bond_pv", "funded_ratio", "home_equity",
        "allocation_coverage", "disabled_asset_classes", "diagnostics",
    }
    assert expected_keys.issubset(result.keys())


def test_compute_optimal_allocation_liquid_targets_are_non_negative_and_sum_to_one():
    c = sample_config()
    result = opt.compute_optimal_allocation(c)
    liquid_targets = result["liquid_targets"]
    assert liquid_targets, "expected at least one liquid target class"
    for weight in liquid_targets.values():
        assert weight >= -1e-9
    assert sum(liquid_targets.values()) == pytest.approx(1.0, abs=1e-6)


def test_compute_optimal_allocation_risk_score_within_bounds():
    c = sample_config()
    result = opt.compute_optimal_allocation(c)
    assert 1.0 <= result["risk_score"] <= 10.0


def test_compute_optimal_allocation_equity_pct_within_bounds():
    c = sample_config()
    result = opt.compute_optimal_allocation(c)
    assert 0.0 <= result["equity_pct"] <= 1.0


def test_compute_optimal_allocation_optimizer_force_mode_does_not_raise():
    c = sample_config()
    result = opt.compute_optimal_allocation(c, force_mode="optimizer_recommendation")
    liquid_targets = result["liquid_targets"]
    assert liquid_targets
    assert sum(liquid_targets.values()) == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# optimize_equity_sleeve — smoke tests
# ---------------------------------------------------------------------------


def test_optimize_equity_sleeve_basic_invariants():
    weights = opt.optimize_equity_sleeve(
        equity_budget=500_000,
        available_classes=["US Large Cap", "International", "Bonds"],
    )
    assert weights
    assert set(weights.keys()) <= {"US Large Cap", "International", "Bonds"}
    for w in weights.values():
        assert w >= -1e-9
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_optimize_equity_sleeve_single_class_returns_full_weight():
    weights = opt.optimize_equity_sleeve(
        equity_budget=100_000,
        available_classes=["US Large Cap"],
    )
    assert weights == {"US Large Cap": 1.0}


def test_optimize_equity_sleeve_empty_classes_returns_empty_dict():
    assert opt.optimize_equity_sleeve(100_000, []) == {}


def test_optimize_equity_sleeve_filters_unknown_classes():
    weights = opt.optimize_equity_sleeve(
        equity_budget=100_000,
        available_classes=["US Large Cap", "Not A Real Class"],
    )
    assert weights == {"US Large Cap": 1.0}


def test_optimize_equity_sleeve_respects_user_min_target_constraint():
    weights = opt.optimize_equity_sleeve(
        equity_budget=100_000,
        available_classes=["US Large Cap", "International", "Bonds"],
        class_constraints={"Bonds": {"min_target": 0.5}},
    )
    assert weights["Bonds"] >= 0.5 - 1e-6
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)
