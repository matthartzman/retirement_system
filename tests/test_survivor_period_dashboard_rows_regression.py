"""Optimization-refactor Phase 2: survivor-period dashboard rows.

Both Monte Carlo engines already know, per path, when a two-spouse
household's first death occurs (the vectorized engine's
``use_bucket_mask`` / the scalar engine's per-path resampled
``h_death_yr``/``w_death_yr``) and already compute the SAME funding-failure
condition ``_funding_success``/``path_success`` use (unfunded > $1, or
liquid <= the configured reserve floor). This feature scopes that existing
failure condition to the survivor period specifically (years strictly after
first death, up to and including the second death) and reports it as two
numbers: what fraction of paths have a survivor period at all within the
modeled horizon (``survivor_period_applicable_probability``), and among
those, what fraction see a funding failure during it
(``survivor_period_failure_probability``).

Reporting-only: reads already-finalized unfunded/liquid tracking and never
feeds back into unfunded/liquid/total/path_success/success_rate. ``None``
for a single-person household, or when no path in the batch has a survivor
window within the modeled horizon.
"""
from __future__ import annotations

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_vectorized_batch,
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _two_spouse_config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    # A long enough horizon that at least one spouse's death plausibly
    # falls within it for most sampled paths -- short horizons (as used by
    # the other Phase 2 test files in this session) would make
    # survivor_period_applicable_probability trivially near 0, which is a
    # valid but uninteresting case already covered by the "no window"
    # tests below.
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 30)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c.update(overrides)
    return c


def test_vectorized_batch_surfaces_survivor_period_probabilities_in_range():
    c = _two_spouse_config()
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 60, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    applicable = batch["survivor_period_applicable_probability"]
    failure = batch["survivor_period_failure_probability"]
    assert applicable is not None
    assert 0.0 <= applicable <= 1.0
    assert failure is not None
    assert 0.0 <= failure <= 1.0
    # Over a 30-year horizon for a real two-spouse household, at least some
    # paths should see a first death within the modeled window.
    assert applicable > 0.0


def test_scalar_engine_reports_the_same_survivor_period_metric():
    c = _two_spouse_config()
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=40, seed=2, base_rows=base_rows)
    applicable = result["survivor_period_applicable_probability"]
    failure = result["survivor_period_failure_probability"]
    assert applicable is not None
    assert 0.0 <= applicable <= 1.0
    assert failure is not None
    assert 0.0 <= failure <= 1.0
    assert applicable > 0.0


def test_monte_carlo_output_carries_survivor_period_metrics_vectorized():
    c = _two_spouse_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=60, seed=3, base_rows=base_rows)
    assert "survivor_period_applicable_probability" in mc
    assert "survivor_period_failure_probability" in mc
    assert mc["survivor_period_applicable_probability"] is not None


def test_single_person_household_has_no_survivor_period():
    c = _two_spouse_config()
    c["members"] = c.get("members", [])[:1]
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["survivor_period_applicable_probability"] is None
    assert batch["survivor_period_failure_probability"] is None

    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert result["survivor_period_applicable_probability"] is None
    assert result["survivor_period_failure_probability"] is None


def test_short_horizon_with_no_deaths_in_window_reports_none():
    # A short enough horizon that no path's sampled first death plausibly
    # falls within it -- there is no survivor period to report on, and both
    # probabilities should be None rather than a misleading 0.0.
    c = _two_spouse_config()
    c["plan_end"] = int(c["plan_start"]) + 1
    base_rows = project(c)
    batch = _mc_vectorized_batch(c, base_rows, 20, 7, 0.06, 0.12, 0.0, use_asset_classes=False)
    assert batch["survivor_period_applicable_probability"] is None
    assert batch["survivor_period_failure_probability"] is None
