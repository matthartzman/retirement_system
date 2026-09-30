"""Paired-path scalar vs. vectorized Monte Carlo agreement (nightly).

The independent-sample gates (``test_monte_carlo_default_engine_mode``, the
survivor reconciliation test) compare two success rates that were each
estimated from DIFFERENT random draws (stdlib ``random`` vs. numpy), so their
difference carries ~2.4pp (n=800) to ~4.8pp (n=200) of pure sampling noise
before any engine bias shows up. This test removes that noise: it samples ONE
set of paths (death years, asset-class returns, inflation) with the vectorized
engine's own generators and feeds the identical paths to both engines --
``project()`` per path for the exact scalar engine, ``_mc_vectorized_projection``
for the vectorized one -- then compares path by path.

What it pins is the *measured* state of the vectorized engine, not a promise of
parity: see ``documentation/archive/reports/N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md``
for the decomposition of the residual gap. Measured on the frozen sample plan
(n=1000, seed 11, survivor economics ON, wellness shocks off, 30-year horizon):

    roth_policy none:          scalar 0.631, vectorized 0.804, agree 82.7%
    roth_policy fill_to_bracket: scalar 0.673, vectorized 0.609, agree 90.8%

The floors below sit ~2 standard errors under those figures at the default
n=200, so they catch a real degradation of path-level fidelity without
flaking. Raise them when the residual-gap fixes in the report land.
"""

from __future__ import annotations

import copy
import os

import numpy as np
import pytest

from conftest import TEST_INPUT_DIR
from src import planning_engines as pe
from src.data_io import load_csv, parse_client

pytestmark = pytest.mark.nightly

N_PATHS = int(os.environ.get("RETIREMENT_PAIRED_PARITY_SIMS", "200"))
SEED = 11


def _config(roth_policy: str | None):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    if roth_policy:
        c["roth_policy"] = roth_policy
    c["plan_end"] = int(c["plan_start"]) + 30
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c["mc_sims"] = N_PATHS
    return c


def _paired_success(c: dict, n: int, seed: int):
    """Return (scalar_success, vectorized_success) boolean arrays over ``n`` paths."""
    base_rows = pe.project(c)
    years = [int(r["year"]) for r in base_rows]
    _classes, _weights, _means, _cov, mu, sig = pe._portfolio_asset_class_inputs(c)
    rng = np.random.default_rng(seed)
    h_death, w_death, max_death = pe._mc_vectorized_death_years(c, rng, n)
    returns, _diag = pe._mc_vectorized_return_paths(c, rng, n, years, mu, sig)
    infl = pe._mc_vectorized_inflation_health_paths(c, rng, returns, mu, sig)
    survivor = pe._mc_survivor_bucket_flows(c, base_rows)
    floor = float(pe.monte_carlo(copy.deepcopy(c), n_sims=1, seed=1, base_rows=base_rows)["success_liquid_floor"])

    proj = pe._mc_vectorized_projection(
        c, base_rows, returns, infl, max_death,
        h_death_years=h_death, w_death_years=w_death, survivor_buckets=survivor)
    active = np.array(years).reshape(1, -1) <= max_death.reshape(-1, 1)
    vec_fail = ((proj["unfunded"] > 1.0) | (proj["liquid"] <= floor)) & active
    vec_ok = ~vec_fail.any(axis=1)

    def series(matrix, i):
        return {y: float(matrix[i, j]) for j, y in enumerate(years)}

    scalar_ok = np.zeros(n, dtype=bool)
    for i in range(n):
        c2 = pe._clone_for_mc(c)
        c2.update({
            "h_death_yr": int(h_death[i]), "w_death_yr": int(w_death[i]),
            "first_death_yr": int(min(h_death[i], w_death[i])), "plan_end": int(c["plan_end"]),
        })
        rets = series(returns, i)
        c2["return_by_year"] = rets
        c2["return_by_account_by_year"] = pe._apply_account_return_adjustments(c2, rets, years)
        c2.update({
            "inflation_by_year": series(infl["inflation_by_year_matrix"], i),
            "inflation_index_by_year": series(infl["inflation_index_matrix"], i),
            "ss_cola_index_by_year": series(infl["ss_cola_index_matrix"], i),
            "bracket_index_by_year": series(infl["bracket_index_matrix"], i),
            "medical_index_by_year": series(infl["medical_index_matrix"], i),
            "wellness_shock_by_year": {},
            "sampled_inflation_geometric": float(c["inf"]),
            "sampled_bracket_inflation_geometric": float(c.get("brk_inf", 0.02) or 0.02),
        })
        scalar_ok[i] = pe._funding_success(pe.project(c2), floor)
    return scalar_ok, vec_ok


@pytest.fixture(scope="module", params=[("none", 0.77), (None, 0.85)], ids=["roth_none", "roth_fill_to_bracket"])
def paired(request):
    policy, floor = request.param
    scalar_ok, vec_ok = _paired_success(_config(policy), N_PATHS, SEED)
    return {"scalar": scalar_ok, "vec": vec_ok, "floor": floor}


def test_path_level_agreement_holds_the_measured_floor(paired):
    agree = float(np.mean(paired["scalar"] == paired["vec"]))
    assert agree >= paired["floor"], (
        f"paired-path scalar/vectorized agreement {agree:.3f} fell below the measured floor "
        f"{paired['floor']:.2f} (scalar success {paired['scalar'].mean():.3f}, vectorized "
        f"{paired['vec'].mean():.3f}); see N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md"
    )


def test_engines_see_the_same_paths(paired):
    # Sanity on the harness itself: identical inputs must give a non-degenerate
    # mix of outcomes in both engines, or agreement above would be vacuous.
    for key in ("scalar", "vec"):
        rate = float(paired[key].mean())
        assert 0.05 < rate < 0.98, f"{key} success rate {rate:.3f} is degenerate; paired harness broken"
