"""Unit tests for src/strategy_sweep.py's run_sweep() (item 2.3, finding A4).

Exercises the shared enumerate/evaluate/rank/gate shape directly, isolated
from either real sweep's own scoring formula -- see planning_engines.py's
optimize_roth_conversion_strategy and reporting/sheets_strategy.py's SS
claim-age grid for the real call sites, both validated against the golden
master when this module was adopted.
"""
from __future__ import annotations

from src.strategy_sweep import run_sweep


def test_ranks_candidates_by_sort_key_descending():
    specs = [{'id': 'a'}, {'id': 'b'}, {'id': 'c'}]
    scores = {'a': 1.0, 'b': 3.0, 'c': 2.0}

    result = run_sweep(
        specs,
        lambda spec: {'score': scores[spec['id']], 'feasibility_gate_met': True},
        sort_key=lambda x: x['score'],
    )

    assert [c['id'] for c in result.candidates] == ['b', 'c', 'a']
    assert result.best['id'] == 'b'
    assert result.all_infeasible is False


def test_selects_best_from_feasible_subset_only():
    specs = [{'id': 'a'}, {'id': 'b'}]
    # 'a' scores higher but fails feasibility; 'b' must win despite scoring lower.
    metrics = {
        'a': {'score': 10.0, 'feasibility_gate_met': False},
        'b': {'score': 1.0, 'feasibility_gate_met': True},
    }

    result = run_sweep(
        specs,
        lambda spec: metrics[spec['id']],
        sort_key=lambda x: x['score'],
    )

    assert result.best['id'] == 'b'
    assert result.all_infeasible is False
    # Both candidates still appear, ranked, for disclosure -- feasibility only
    # restricts selection, not visibility.
    assert [c['id'] for c in result.candidates] == ['a', 'b']


def test_falls_back_to_full_ranked_set_when_everything_fails_the_gate():
    specs = [{'id': 'a'}, {'id': 'b'}]
    metrics = {
        'a': {'score': 1.0, 'feasibility_gate_met': False},
        'b': {'score': 2.0, 'feasibility_gate_met': False},
    }

    result = run_sweep(
        specs,
        lambda spec: metrics[spec['id']],
        sort_key=lambda x: x['score'],
    )

    assert result.all_infeasible is True
    assert result.best['id'] == 'b'  # top of the full set, not excluded


def test_empty_specs_returns_fallback_best():
    result = run_sweep(
        [],
        lambda spec: {},
        sort_key=lambda x: 0,
        fallback_best={'policy': 'none', 'label': 'No voluntary conversions'},
    )

    assert result.candidates == []
    assert result.all_infeasible is False
    assert result.best == {'policy': 'none', 'label': 'No voluntary conversions'}


def test_empty_specs_with_no_fallback_returns_empty_best():
    result = run_sweep([], lambda spec: {}, sort_key=lambda x: 0)

    assert result.best == {}


def test_merges_spec_fields_with_evaluate_fn_metrics():
    specs = [{'label': 'candidate-1', 'target_rate': 0.24}]

    result = run_sweep(
        specs,
        lambda spec: {'score': 5.0, 'feasibility_gate_met': True},
        sort_key=lambda x: x['score'],
    )

    assert result.candidates[0]['label'] == 'candidate-1'
    assert result.candidates[0]['target_rate'] == 0.24
    assert result.candidates[0]['score'] == 5.0


def test_custom_feasibility_key():
    specs = [{'id': 'a'}, {'id': 'b'}]
    metrics = {
        'a': {'score': 5.0, 'passes': False},
        'b': {'score': 1.0, 'passes': True},
    }

    result = run_sweep(
        specs,
        lambda spec: metrics[spec['id']],
        sort_key=lambda x: x['score'],
        feasibility_key='passes',
    )

    assert result.best['id'] == 'b'
