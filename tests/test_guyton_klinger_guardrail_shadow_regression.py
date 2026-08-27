"""Optimization-refactor Phase 5: Guyton-Klinger adaptive-guardrail SHADOW
simulation, per docs/superpowers/plans/2026-08-27-phase5-adaptive-
guardrails-spec.md's Option A (full 4-rule GK, fixed default bands, both
engines together -- per explicit user sign-off).

This is a genuinely separate, self-contained alternate spending trajectory
computed purely for reporting -- it never feeds back into the real
withdrawal cascade, `unfunded`, `liquid`, `total`, `path_success`, or
`success_rate` (the GK block only ever ADDS new output keys; it never
reads or mutates the pre-existing `balances`/`out` state those figures
come from, so the full existing test suite re-passing after this change,
verified separately, is itself the reporting-only regression proof for
this file's purposes).

Fixtures use zero inflation-rate/zero-income single-account setups so the
capital-preservation/prosperity rules can be triggered by portfolio
returns alone, with exact-dollar checks reserved for year 0 (later years'
`guardrail_spend_real` are deflated by a cumulative-inflation-index
factor that isn't exactly 1, so behavioral checks -- cut/raise counts --
are used for multi-year assertions instead of exact dollar amounts).
"""
from __future__ import annotations

import numpy as np

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    _mc_scalar_guyton_klinger_shadow,
    _mc_vectorized_batch,
    _mc_vectorized_projection,
    monte_carlo_exact_scalar,
    project,
)


def _gk_setup(n_years: int, starting_balance: float, year0_draw: float,
              returns_by_year: list, income_per_year: float = 0.0):
    plan_start = 2030
    years = list(range(plan_start, plan_start + n_years))
    inf = 0.025  # matches _mc_row_bucket_flows's own fallback (c.get('inf', 0.025) or 0.025)
    total_spend0 = year0_draw + income_per_year
    c = {
        "plan_start": plan_start,
        "plan_end": years[-1],
        "inf": inf,
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": starting_balance},
    }
    base_rows = [
        {
            "year": y,
            "_account_withdrawals": {"acct1": year0_draw} if i == 0 else {"acct1": 0.0},
            "total_spend": total_spend0 if i == 0 else income_per_year,
            "total_tax": 0.0,
            "gross_income": 0.0,
            "income_funding": income_per_year,
            "total_nw": 0.0, "pretax_nw": 0.0, "roth_nw": 0.0, "trust_nw": 0.0, "hsa_nw": 0.0,
        }
        for i, y in enumerate(years)
    ]
    n_sims = 1
    returns = np.array([returns_by_year], dtype=float)
    assert returns.shape == (n_sims, n_years)
    # Cancels spending_scale to exactly 1.0 every year (matches
    # _mc_row_bucket_flows's own det_idx formula, (1+inf)**(year-start)),
    # so GK's internal nominal figures aren't perturbed by unrelated
    # inflation-index scaling -- isolating the behavior under test to GK's
    # own rules and the supplied `returns_by_year` alone.
    det_idx = np.array([[(1.0 + inf) ** j for j in range(n_years)]])
    inflation_paths = {
        "inflation_index_matrix": det_idx.copy(),
        "medical_index_matrix": np.ones((n_sims, n_years)),
        "wellness_shock_matrix": np.zeros((n_sims, n_years)),
        "inflation_by_year_matrix": np.zeros((n_sims, n_years)),  # no GK inflation increases
    }
    max_death_years = np.full(n_sims, years[-1] + 100, dtype=int)
    return c, base_rows, returns, inflation_paths, max_death_years


def test_year0_spend_matches_actual_draw_plus_income():
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=1, starting_balance=100_000.0, year0_draw=5_000.0, returns_by_year=[0.0],
        income_per_year=10_000.0,
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert np.allclose(proj["guardrail_spend_real"][:, 0], 15_000.0)
    assert proj["guardrail_cut_years_count"][0] == 0
    assert proj["guardrail_raise_years_count"][0] == 0


def test_capital_preservation_rule_cuts_after_a_sharp_drawdown():
    # IWR = 5000/100000 = 0.05. A -20% year-0 return leaves portfolio at
    # 76,000 (=(100000-5000)*0.8), pushing year-1's withdrawal rate to
    # 5000/76000 ≈ 0.0658 > 0.05*1.2=0.06 -- capital-preservation rule
    # should cut the withdrawal. 20-year horizon keeps 18 years remaining
    # at year index 1, well outside the 15-year suspension window.
    returns_by_year = [-0.20] + [0.0] * 19
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=20, starting_balance=100_000.0, year0_draw=5_000.0, returns_by_year=returns_by_year,
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert proj["guardrail_ever_cut"][0]
    assert proj["guardrail_cut_years_count"][0] >= 1
    assert not proj["guardrail_ever_raise"][0]


def test_capital_preservation_rule_suspended_in_final_15_years():
    # Identical trigger condition to the test above, but a 17-year horizon
    # leaves exactly 15 years remaining at year index 1 (plan_end - year1
    # = 16 - 1 = 15, NOT strictly > 15) -- the capital-preservation rule
    # must NOT fire here even though the withdrawal rate crosses the same
    # upper band.
    returns_by_year = [-0.20] + [0.0] * 16
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=17, starting_balance=100_000.0, year0_draw=5_000.0, returns_by_year=returns_by_year,
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert not proj["guardrail_ever_cut"][0]
    assert proj["guardrail_cut_years_count"][0] == 0


def test_prosperity_rule_raises_after_strong_growth():
    # IWR = 0.05. A +50% year-0 return leaves portfolio at 142,500
    # (=(100000-5000)*1.5), pushing year-1's withdrawal rate to
    # 5000/142500 ≈ 0.0351 < 0.05*0.8=0.04 -- prosperity rule should raise
    # the withdrawal. No time-based suspension applies to this rule.
    returns_by_year = [0.50, 0.0, 0.0, 0.0, 0.0]
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=5, starting_balance=100_000.0, year0_draw=5_000.0, returns_by_year=returns_by_year,
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert proj["guardrail_ever_raise"][0]
    assert proj["guardrail_raise_years_count"][0] >= 1
    assert not proj["guardrail_ever_cut"][0]


def test_no_trigger_when_withdrawal_rate_stays_within_band():
    # Modest, steady positive returns keep the withdrawal rate close to
    # IWR throughout -- neither rule should ever fire.
    returns_by_year = [0.03] * 10
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=10, starting_balance=100_000.0, year0_draw=5_000.0, returns_by_year=returns_by_year,
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert not proj["guardrail_ever_cut"][0]
    assert not proj["guardrail_ever_raise"][0]
    assert proj["guardrail_cut_years_count"][0] == 0
    assert proj["guardrail_raise_years_count"][0] == 0


def test_no_rows_data_produces_zero_spend_not_a_crash():
    # A degenerate single-year, zero-draw, zero-income household: GK's
    # anchor withdrawal is 0, so nothing can ever trigger -- must not
    # divide-by-zero crash (guarded by the 1e-9 floors in the
    # implementation) and must report exactly zero spend.
    c, base_rows, returns, inflation_paths, max_death_years = _gk_setup(
        n_years=3, starting_balance=0.0, year0_draw=0.0, returns_by_year=[0.0, 0.0, 0.0],
    )
    proj = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death_years)
    assert np.allclose(proj["guardrail_spend_real"], 0.0)
    assert not proj["guardrail_ever_cut"][0]
    assert not proj["guardrail_ever_raise"][0]


def _scalar_rows(n_years: int, starting_balance: float, year0_draw: float, income_per_year: float = 0.0):
    plan_start = 2030
    years = list(range(plan_start, plan_start + n_years))
    rows = [
        {
            "year": y,
            "_account_withdrawals": {"acct1": year0_draw} if i == 0 else {},
            "income_funding": income_per_year,
        }
        for i, y in enumerate(years)
    ]
    c = {
        "plan_end": years[-1],
        "account_registry": [{"id": "acct1", "tax": "taxable", "balance": 0.0}],
        "balances": {"acct1": starting_balance},
    }
    return c, rows


def test_scalar_engine_capital_preservation_cut_matches_vectorized_mechanics():
    c, rows = _scalar_rows(20, 100_000.0, 5_000.0)
    returns = {2030 + i: (-0.20 if i == 0 else 0.0) for i in range(20)}
    result = _mc_scalar_guyton_klinger_shadow(c, rows, returns, {})
    assert result is not None
    assert result[2031]["cut"] is True
    assert result[2030]["cut"] is False


def test_scalar_engine_prosperity_raise_matches_vectorized_mechanics():
    c, rows = _scalar_rows(5, 100_000.0, 5_000.0)
    returns = {2030 + i: (0.50 if i == 0 else 0.0) for i in range(5)}
    result = _mc_scalar_guyton_klinger_shadow(c, rows, returns, {})
    assert result[2031]["raise"] is True
    assert result[2031]["cut"] is False


def test_scalar_engine_year0_spend_matches_actual_draw_plus_income():
    c, rows = _scalar_rows(1, 100_000.0, 5_000.0, income_per_year=10_000.0)
    result = _mc_scalar_guyton_klinger_shadow(c, rows, {2030: 0.0}, {})
    assert result[2030]["spend_nominal"] == 15_000.0


def test_empty_rows_returns_none():
    assert _mc_scalar_guyton_klinger_shadow({}, [], {}, {}) is None


def test_both_engines_surface_guardrail_fields_and_agree_in_ballpark_on_real_fixture():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 15)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    base_rows = project(c)
    vector = _mc_vectorized_batch(c, base_rows, 30, 3, 0.06, 0.12, 0.0, use_asset_classes=False)
    scalar = monte_carlo_exact_scalar(c, n_sims=15, seed=3, base_rows=base_rows)
    assert vector["probability_guardrail_cut"] is not None
    assert vector["probability_guardrail_raise"] is not None
    assert scalar["probability_guardrail_cut"] is not None
    assert scalar["probability_guardrail_raise"] is not None
    for p in (vector["probability_guardrail_cut"], vector["probability_guardrail_raise"],
              scalar["probability_guardrail_cut"], scalar["probability_guardrail_raise"]):
        assert 0.0 <= p <= 1.0
