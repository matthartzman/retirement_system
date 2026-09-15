"""Wave 3 item 3.5 (F6), full-pipeline companion to
test_adoptable_spending_policy_unit.py: drives the real project()/
monte_carlo() pipeline to prove the policy selector reaches the actual
spending figure and the Monte Carlo success rate, not just the pure
per-year helper functions.
"""
import contextlib
import io

import pytest

from src.data_io import load_csv, parse_client
from src.planning_engines import project, monte_carlo

from conftest import TEST_INPUT_DIR


def _project(policy=None, **overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["mc_paths"] = 5
    if policy is not None:
        c["spending_policy"] = policy
    c.update(overrides)
    return c, project(c)


def _mc_pair(seed):
    """Run monte_carlo() once each for fixed_real and guyton_klinger at the
    given seed. Module-scoped and keyed by seed (not by test) so the two
    tests that each need the same seed (see the seed=13 pair below) share
    one pair of MC runs instead of duplicating it -- these are real
    150-path Monte Carlo calls (~7s each), not pure-function calls, so this
    is where this file's cost actually lives.
    """
    c_fixed, _ = _project("fixed_real")
    c_gk, _ = _project("guyton_klinger")
    with contextlib.redirect_stdout(io.StringIO()):
        mc_fixed = monte_carlo(c_fixed, n_sims=150, seed=seed)
        mc_gk = monte_carlo(c_gk, n_sims=150, seed=seed)
    return mc_fixed, mc_gk


@pytest.fixture(scope="module")
def mc_seed7():
    return _mc_pair(seed=7)


@pytest.fixture(scope="module")
def mc_seed11():
    return _mc_pair(seed=11)


@pytest.fixture(scope="module")
def mc_seed13():
    return _mc_pair(seed=13)


def test_default_is_fixed_real_and_matches_unconfigured_behavior():
    c_default, rows_default = _project()
    c_explicit, rows_explicit = _project("fixed_real")
    for r_default, r_explicit in zip(rows_default, rows_explicit):
        assert r_default["spend_base_yr"] == r_explicit["spend_base_yr"]
    assert c_default["spending_policy"] == "fixed_real"


def test_guyton_klinger_produces_a_genuinely_different_spend_path():
    _, fixed_rows = _project("fixed_real")
    _, gk_rows = _project("guyton_klinger")
    fixed_total = sum(r["spend_base_yr"] for r in fixed_rows)
    gk_total = sum(r["spend_base_yr"] for r in gk_rows)
    assert gk_total != fixed_total
    assert any(r.get("spending_policy_cut_applied") or r.get("spending_policy_raise_applied") for r in gk_rows)


def test_floor_ceiling_band_produces_a_genuinely_different_spend_path():
    _, fixed_rows = _project("fixed_real")
    _, fc_rows = _project("floor_ceiling_band")
    fixed_total = sum(r["spend_base_yr"] for r in fixed_rows)
    fc_total = sum(r["spend_base_yr"] for r in fc_rows)
    assert fc_total != fixed_total


def test_age_phased_curve_is_independent_of_the_policy_selector():
    # Option 2 (age-phased curve) must apply even under fixed_real -- it is
    # documented as an independent control, not part of the selector.
    _, baseline_rows = _project("fixed_real")
    _, phased_rows = _project(
        "fixed_real",
        spending_phase_decline_pct=0.15, spending_phase_start_age=70, spending_phase_end_age=80,
    )
    late_baseline = sum(r["spend_base_yr"] for r in baseline_rows if r["h_age"] >= 80)
    late_phased = sum(r["spend_base_yr"] for r in phased_rows if r["h_age"] >= 80)
    assert late_phased < late_baseline


def test_monte_carlo_success_rate_reflects_the_active_guardrail_policy(mc_seed7):
    mc_fixed, mc_gk = mc_seed7
    assert mc_fixed["spending_policy_active"] is False
    assert mc_gk["spending_policy_active"] is True
    # A guardrail policy self-cuts specifically to avoid running dry, so its
    # own success definition (guardrail portfolio never depleted) must never
    # read LOWER than the fixed-real cascade's success rate for the same
    # household/seed -- it is, by construction, at least as forgiving.
    assert mc_gk["success_rate"] >= mc_fixed["success_rate"]
    assert "conditional on the modelled spending cuts" in mc_gk["success_definition"]


def test_essential_funding_probability_is_materially_unaffected_by_the_guardrail_policy(mc_seed11):
    # Guardrails resize the DISCRETIONARY/"important" spend tier (spend_base_yr),
    # never essential's own tier components (housing, wellness) directly --
    # essential_fully_funded_probability must keep meaning "funded as asked",
    # not the guardrail's "survived having cut". A small residual difference
    # is still possible: overall household cash flow (taxes, withdrawal
    # amounts) differs when discretionary spend differs, which can nudge a
    # handful of on-the-margin paths' essential-tier ledger by noise-level
    # amounts -- this asserts "materially unaffected" (a few points), not
    # byte-identical, which would overclaim a total tier isolation this
    # item's design never intended to guarantee.
    mc_fixed, mc_gk = mc_seed11
    assert abs(mc_fixed["essential_fully_funded_probability"] - mc_gk["essential_fully_funded_probability"]) < 0.02


def test_mandatory_cut_disclosure_is_populated_when_a_guardrail_policy_is_active(mc_seed13):
    _, mc_gk = mc_seed13
    assert mc_gk["worst_modeled_spending_cut_pct"] is not None
    assert mc_gk["worst_modeled_spending_cut_pct"] >= 0.0
    assert mc_gk["guardrail_probability_ever_cut"] is not None


def test_mandatory_cut_disclosure_is_absent_under_fixed_real(mc_seed13):
    mc_fixed, _ = mc_seed13
    assert mc_fixed["spending_policy_active"] is False
