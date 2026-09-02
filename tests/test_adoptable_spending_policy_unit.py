"""Wave 3 item 3.5 (system review 2026-08-31, finding F6, Options 1+2):
the Guyton-Klinger 4-rule guardrail was modeled only as a Monte Carlo
SHADOW -- computed and reported, never consumed as real policy
(FUNCTIONAL_SPEC.md: "shown for comparison only; it never feeds back into
the real plan"). This promotes it (plus a new, simpler floor-ceiling band
policy) to a genuine, adoptable spending policy selector that governs the
household's actual discretionary spend in BOTH engines, plus an
independent age-phased real spending curve (Option 2).

Unit-level tests for the two pure functions the deterministic engine's
single (non-vectorized) path uses: age_phased_spending_factor and
spending_guardrail_year.
"""
import pytest

from src.planning_engines import age_phased_spending_factor, spending_guardrail_year


# ── age_phased_spending_factor ──────────────────────────────────────────

def test_no_op_when_decline_pct_is_zero():
    assert age_phased_spending_factor(90, 0.0, 70, 85) == 1.0


def test_no_op_when_end_age_not_after_start_age():
    assert age_phased_spending_factor(80, 0.2, 75, 75) == 1.0
    assert age_phased_spending_factor(80, 0.2, 80, 70) == 1.0


def test_unchanged_before_the_phase_window():
    assert age_phased_spending_factor(70, 0.2, 75, 85) == 1.0


def test_linear_phase_in_midway():
    # Halfway through a 75-85 window at 20% decline: 10% reduction so far.
    assert age_phased_spending_factor(80, 0.2, 75, 85) == 0.9


def test_holds_at_the_reduced_level_past_the_end_age():
    assert age_phased_spending_factor(90, 0.2, 75, 85) == 0.8
    assert age_phased_spending_factor(120, 0.2, 75, 85) == 0.8


# ── spending_guardrail_year ──────────────────────────────────────────────

def test_fixed_real_policy_is_a_pure_passthrough():
    spend, state, cut, raised = spending_guardrail_year(
        "fixed_real", 100_000.0, 2_000_000.0, {}, inflation_rate=0.03,
    )
    assert spend == 100_000.0
    assert cut is False and raised is False


def test_first_active_year_is_unchanged_and_initializes_state():
    spend, state, cut, raised = spending_guardrail_year(
        "guyton_klinger", 100_000.0, 2_000_000.0, {}, inflation_rate=0.03,
    )
    assert spend == 100_000.0
    assert cut is False and raised is False
    assert state["initialized"] is True
    assert state["iwr"] == 100_000.0 / 2_000_000.0


def test_guyton_klinger_cuts_when_withdrawal_rate_drifts_high():
    # Portfolio dropped hard after year 1 -- the SAME nominal withdrawal
    # against a much smaller portfolio pushes the current rate well above
    # 120% of the initial rate, triggering GK's capital-preservation cut.
    _, state, _, _ = spending_guardrail_year("guyton_klinger", 100_000.0, 2_000_000.0, {})
    spend, state, cut, raised = spending_guardrail_year(
        "guyton_klinger", 100_000.0, 700_000.0, state,
        inflation_rate=0.03, years_remaining=20,
    )
    assert cut is True
    assert raised is False
    assert spend < 100_000.0 * 1.03  # cut below what inflation growth alone would have given


def test_guyton_klinger_raises_when_withdrawal_rate_drifts_low():
    _, state, _, _ = spending_guardrail_year("guyton_klinger", 100_000.0, 2_000_000.0, {})
    spend, state, cut, raised = spending_guardrail_year(
        "guyton_klinger", 100_000.0, 6_000_000.0, state,
        inflation_rate=0.03, years_remaining=20,
    )
    assert raised is True
    assert cut is False
    assert spend > 100_000.0 * 1.03


def test_guyton_klinger_capital_preservation_suspended_near_plan_end():
    _, state, _, _ = spending_guardrail_year("guyton_klinger", 100_000.0, 2_000_000.0, {})
    spend, state, cut, raised = spending_guardrail_year(
        "guyton_klinger", 100_000.0, 700_000.0, state,
        inflation_rate=0.03, years_remaining=10,  # <= 15-year suspension window
    )
    assert cut is False  # capital-preservation rule suspended this close to plan end


def test_floor_ceiling_band_clamps_within_ten_percent_of_baseline():
    _, state, _, _ = spending_guardrail_year("floor_ceiling_band", 100_000.0, 2_000_000.0, {})
    # A big portfolio drop pulls the "natural" (portfolio x IWR) draw far
    # below baseline -- the band must clamp it at exactly -10%, not let it
    # fall further, unlike GK's own -10%-per-trigger step function.
    spend, state, cut, raised = spending_guardrail_year(
        "floor_ceiling_band", 100_000.0, 200_000.0, state, inflation_rate=0.0,
    )
    assert spend == 90_000.0
    assert cut is True


def test_floor_ceiling_band_ceiling_side():
    _, state, _, _ = spending_guardrail_year("floor_ceiling_band", 100_000.0, 2_000_000.0, {})
    spend, state, cut, raised = spending_guardrail_year(
        "floor_ceiling_band", 100_000.0, 8_000_000.0, state, inflation_rate=0.0,
    )
    assert spend == pytest.approx(110_000.0)
    assert raised is True


def test_unrecognized_policy_is_also_a_passthrough():
    spend, state, cut, raised = spending_guardrail_year("not_a_real_policy", 100_000.0, 2_000_000.0, {})
    assert spend == 100_000.0
    assert cut is False and raised is False
