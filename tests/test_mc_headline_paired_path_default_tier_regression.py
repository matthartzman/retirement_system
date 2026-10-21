"""WI-036: default-tier guard on the vectorized replay headline vs the exact scalar engine.

Small-n version of the study in documentation/reference/MC_PARITY_MEASUREMENT_WI036.md
(n=1000, three seeds). Paired paths remove sampling noise, so the bounds below are
the measured gaps widened for n=40 granularity (one path is 2.5pp).

* Funded household, all three Roth regimes: the signed gap measured within +-1.7pp
  and path agreement >= 98.3%; asserted at 6pp and 90%.
* Household whose deterministic plan runs into shortfall: the headline is
  optimistic by +15 to +24pp (n=1000). This is a KNOWN limitation with a repair
  item raised, so the test pins it from both sides: it fails if the bias grows
  or if a repair lands (update the bounds and the measurement document then).
"""
from __future__ import annotations

import pytest

from tests.golden_pricing import frozen_holdings_prices
from tests.paired_path_harness import ROTH_REGIMES, _paired_success, build_config

N = 40
SEED = 11


def _gap(shape: str, regime: str):
    with frozen_holdings_prices():
        scalar_ok, vec_ok = _paired_success(build_config(shape, regime, N), N, SEED)
    return float(vec_ok.mean() - scalar_ok.mean()), float((scalar_ok == vec_ok).mean())


@pytest.mark.parametrize("regime", ROTH_REGIMES)
def test_funded_household_headline_matches_scalar(regime):
    gap, agree = _gap("baseline_balanced_couple", regime)
    assert abs(gap) <= 0.06, f"{regime}: signed gap {gap:+.3f} exceeds 6pp on a funded household"
    assert agree >= 0.90, f"{regime}: path agreement {agree:.3f} below 0.90"


def test_known_optimistic_bias_when_the_base_plan_has_a_shortfall():
    gap, _agree = _gap("pressure:0.6:150000", "fill_to_bracket")
    assert 0.08 <= gap <= 0.45, (
        f"signed gap {gap:+.3f} left the measured +8..+45pp band for a base plan in shortfall; "
        "if the replay headline was repaired, update this bound and MC_PARITY_MEASUREMENT_WI036.md"
    )


def test_headline_status_reflects_whether_the_base_plan_is_funded():
    """Option 1 of the WI-036 repair: no tolerance label for a base plan in shortfall."""
    from src import planning_engines as pe

    for shape, expected, flagged in (
        ("baseline_balanced_couple", "TOLERANCE_BOUNDED", False),
        ("pressure:0.6:150000", "BASE_PLAN_SHORTFALL", True),
    ):
        with frozen_holdings_prices():
            c = build_config(shape, "fill_to_bracket", 10)
            result = pe.monte_carlo(c, n_sims=10, seed=SEED)
        assert result["mc_base_plan_shortfall"] is flagged, shape
        assert result["mc_approximation_status"] == expected, shape
        expected_rating = "APPROXIMATE_VECTORIZED_MC" if flagged else "TOLERANCE_BOUNDED_VECTORIZED_MC"
        assert result["model_risk_rating"] == expected_rating, shape
