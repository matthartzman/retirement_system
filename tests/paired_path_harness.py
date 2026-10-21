"""Paired-path scalar vs. vectorized Monte Carlo harness (WI-036).

One set of sampled paths (death years, asset-class returns, inflation) is fed to
both the exact scalar engine (``project()`` per path) and the vectorized replay
headline engine, so the comparison carries no sampling noise. Shared by the
nightly paired-path test, the default-tier smoke test and
``tools/measure_mc_paired_path.py``.
"""
from __future__ import annotations

import copy

import numpy as np

from src import planning_engines as pe

ROTH_REGIMES = ("none", "fill_to_bracket", "optimize_terminal_tax")


def prepare_mc_config(c: dict, n: int) -> dict:
    """Common MC settings: 30-year horizon is the caller's, no wellness shocks, no sensitivity grid."""
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c["mc_sims"] = n
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
        h_death_years=h_death, w_death_years=w_death, survivor_buckets=survivor, allocation="replay")
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
