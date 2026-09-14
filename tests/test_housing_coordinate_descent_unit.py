"""Coordinate-descent correctness (H13) --
docs/superpowers/plans/2026-09-09-housing-estimate-realism-and-dollar-
convention-design.md, §4.2 steps 1 and 3.

The design names H9/H10's silent-failure mode explicitly: a coarse-pass stage
that sweeps one axis without actually holding the PREVIOUS stage's winner
fixed, or a two-orderings comparison that quietly keeps the wrong trajectory,
still renders a sheet with plausible-looking numbers while never having
performed the search the sheet claims. Both fail invisibly against real plan
data, because the "right" answer is unknown there.

So these tests plant a known-best combination instead: the scoring function is
rigged (``_score_trajectory`` is replaced) so the objective is zero everywhere
except at a handful of hand-placed peaks, chosen so the two axis orderings
provably descend to DIFFERENT trajectories with different scores. That makes
the carry-forward and the ordering comparison observable, and costs no engine
calls at all.
"""
from __future__ import annotations

import src.housing_comparison as hc
from src.housing_comparison import AXIS_ORDERINGS, Trajectory, _coarse_descent, build_axes

# A synthetic household: a configured sale year, a purchase Step 1, and a
# configured rent Step 2, so all three axes are genuinely populated (unlike the
# frozen fixture, which has no Step 2).
PLAN_START, PLAN_END = 2030, 2060
CONFIGURED = Trajectory(sale_year=2040, step1=('purchase', 2040), step2=('rent', 2050))


def _synthetic_config():
    def _step(typ, year):
        return {'type': typ, 'start_year': year, 'end_year': 0, 'state': 'TX',
                'city_type': 'suburban', 'population_size': 50000,
                'purchase_price': 400000.0, 'down_payment_pct': 0.20,
                'mortgage_rate_pct': 0.06, 'monthly_rent': 0.0}
    return {
        'plan_start': PLAN_START,
        'plan_end': PLAN_END,
        'home_sale_yr': CONFIGURED.sale_year,
        'next_housing_steps': [_step('purchase', 2040), _step('rent', 2050)],
    }


# Peaks placed so that, starting from CONFIGURED:
#
#   ordering A (sale_year -> step1 -> step2) climbs 10 -> 20 -> 30, and
#   ordering B (step1 -> step2 -> sale_year) climbs 15 -> 25 -> 100.
#
# Each peak is the unique nonzero point on the axis line its stage sweeps, so
# the descent path is fully determined. B ends strictly higher, which is what
# makes the two-orderings comparison observable rather than a no-op.
A1 = Trajectory(2043, ('purchase', 2040), ('rent', 2050))
A2 = Trajectory(2043, ('purchase', 2043), ('rent', 2050))
A3 = Trajectory(2043, ('purchase', 2043), ('rent', 2053))
B1 = Trajectory(2040, ('rent', 2037), ('rent', 2050))
B2 = Trajectory(2040, ('rent', 2037), ('purchase', 2047))
B3 = Trajectory(0, ('rent', 2037), ('purchase', 2047))

PLANTED = {A1: 10.0, A2: 20.0, A3: 30.0, B1: 15.0, B2: 25.0, B3: 100.0}
GLOBAL_BEST = B3


def _rigged_metrics(objective):
    return {
        'objective_value': objective, 'lcv_score': objective, 'terminal_nw': 0.0,
        'after_tax_terminal_nw': 0.0, 'lcv': 0.0, 'delta_lcv': 0.0,
        'npv_future_taxes': 0.0, 'equity_at_plan_end': 0.0,
        'mc_success_rate': 1.0, 'mc_p5_terminal_nw': 0.0,
        'feasibility_probability': 1.0, 'feasibility_gate_met': True,
        'scored_with_monte_carlo': True,
    }


def _rigged_score(_c, traj, _base_lcv, *, skip_mc, mc_sims):
    return _rigged_metrics(PLANTED.get(traj, 0.0))


def _rigged_evaluator():
    return lambda traj: _rigged_metrics(PLANTED.get(traj, 0.0))


def test_each_coarse_stage_carries_the_prior_stages_winner_forward():
    axes = build_axes(_synthetic_config())
    order = AXIS_ORDERINGS[0]
    visited: list[Trajectory] = []

    def _recording(traj):
        visited.append(traj)
        return _rigged_metrics(PLANTED.get(traj, 0.0))

    winner, _axis_candidates = _coarse_descent(axes, order, CONFIGURED, _recording)

    # One full axis is swept per stage, in order, so the recorded trajectories
    # segment cleanly into the three stages.
    sizes = [len(axes[axis]) for axis in order]
    assert len(visited) == sum(sizes)
    stage1 = visited[:sizes[0]]
    stage2 = visited[sizes[0]:sizes[0] + sizes[1]]
    stage3 = visited[sizes[0] + sizes[1]:]

    # Stage 1 holds Steps 1 and 2 at the CONFIGURED values, per §4.2.
    assert {t.step1 for t in stage1} == {CONFIGURED.step1}
    assert {t.step2 for t in stage1} == {CONFIGURED.step2}

    # Stage 2 must hold the sale year at stage 1's WINNER (2043), not at the
    # configured 2040 -- this is the carry-forward H13 exists to prove.
    assert A1.sale_year != CONFIGURED.sale_year
    assert {t.sale_year for t in stage2} == {A1.sale_year}
    assert {t.step2 for t in stage2} == {CONFIGURED.step2}

    # Stage 3 must hold BOTH prior winners.
    assert A2.step1 != CONFIGURED.step1
    assert {t.sale_year for t in stage3} == {A2.sale_year}
    assert {t.step1 for t in stage3} == {A2.step1}

    assert winner == A3


def test_each_coarse_ordering_descends_to_its_own_planted_local_optimum():
    axes = build_axes(_synthetic_config())
    evaluate = _rigged_evaluator()
    a_winner, a_axes = _coarse_descent(axes, AXIS_ORDERINGS[0], CONFIGURED, evaluate)
    b_winner, b_axes = _coarse_descent(axes, AXIS_ORDERINGS[1], CONFIGURED, evaluate)
    assert a_winner == A3
    assert b_winner == B3
    # Every axis leaves a full candidate table behind for the sensitivity
    # mini-tables to render (§4.5 item 3, "nothing new to run").
    for axis_candidates, axis_name in ((a_axes, 'sale_year'), (b_axes, 'step1')):
        assert len(axis_candidates[axis_name]) == len(axes[axis_name])


def test_two_orderings_comparison_keeps_the_higher_scoring_trajectory(monkeypatch):
    monkeypatch.setattr(hc, '_score_trajectory', _rigged_score)
    monkeypatch.setattr(hc, 'compute_baseline_lcv_and_eltr', lambda _c, _rows: {'lcv': 0.0})
    result = hc.sweep_housing_trajectories(_synthetic_config(), [])

    assert result is not None
    scores = {o['order']: o['objective_value'] for o in result['orderings']}
    assert scores[AXIS_ORDERINGS[0]] == 30.0
    assert scores[AXIS_ORDERINGS[1]] == 100.0
    # The comparison is not a no-op: the orderings genuinely disagree, and the
    # higher-scoring one is what the refine pass runs on.
    assert result['winning_order']['order'] == AXIS_ORDERINGS[1]
    assert result['winning_order']['trajectory'] == GLOBAL_BEST
    assert result['recommended']['trajectory'] == GLOBAL_BEST
    assert result['recommended']['rank_score'] == 100


def test_refine_pass_scores_the_winner_plus_a_one_step_neighbourhood(monkeypatch):
    monkeypatch.setattr(hc, '_score_trajectory', _rigged_score)
    monkeypatch.setattr(hc, 'compute_baseline_lcv_and_eltr', lambda _c, _rows: {'lcv': 0.0})
    result = hc.sweep_housing_trajectories(_synthetic_config(), [])

    trajectories = [x['trajectory'] for x in result['refine_candidates']]
    assert GLOBAL_BEST in trajectories
    assert len(trajectories) == len(set(trajectories))
    # §4.2 step 2's stated budget, with all three axes populated.
    assert 5 <= len(trajectories) <= 10
    for traj in trajectories:
        differing = sum(
            getattr(traj, axis) != getattr(GLOBAL_BEST, axis) for axis in ('sale_year', 'step1', 'step2')
        )
        assert differing <= 1, f"{traj} is more than one axis away from the coarse winner"
