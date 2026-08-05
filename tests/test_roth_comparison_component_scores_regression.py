import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.planning_engines import _roth_strategy_metrics


def test_roth_strategy_metrics_assigns_legacy_estate_survivor_liquidity_scores():
    c = {
        'plan_start': 2026,
        'inf': 0.025,
        'roth_target_rate': 0.24,
        'roth_optimize_terminal_weight': 1.0,
        'roth_optimize_tax_weight': 0.25,
        'roth_legacy_objective_mode': 'BALANCED',
        'roth_future_tax_rate_stress_pct': 0.10,
        'roth_future_tax_risk_weight': 0.35,
        'roth_inheritance_tax_burden_weight': 0.25,
        'roth_heir_ordinary_tax_rate_assumption': 0.24,
        'roth_pre_tax_bequest_penalty_pct': 0.15,
        'roth_bequest_preference_bonus_pct': 0.05,
        'roth_survivor_tax_risk_weight': 0.25,
        'estate_tax_objective_mode': 'BALANCED',
        'fed_exempt': 30_000_000,
        'il_exempt': 4_000_000,
        'model_state_est': True,
        'federal_portability_enabled': True,
        'h_death_yr': 2030,
        'w_death_yr': 2032,
        'roth_objective_mode': 'BALANCED_RETIREMENT',
    }
    rows = [
        {'year': 2026, 'pretax_nw': 1_500_000, 'roth_nw': 400_000, 'trust_nw': 200_000, 'hsa_nw': 50_000, 'total_nw': 5_300_000, 'total_tax': 50_000},
        {'year': 2027, 'pretax_nw': 1_200_000, 'roth_nw': 650_000, 'trust_nw': 175_000, 'hsa_nw': 55_000, 'total_nw': 5_100_000, 'total_tax': 55_000},
        {'year': 2030, 'pretax_nw': 800_000, 'roth_nw': 900_000, 'trust_nw': 120_000, 'hsa_nw': 40_000, 'total_nw': 4_800_000, 'total_tax': 45_000},
        {'year': 2031, 'pretax_nw': 600_000, 'roth_nw': 950_000, 'trust_nw': 100_000, 'hsa_nw': 30_000, 'total_nw': 4_600_000, 'total_tax': 40_000},
        {'year': 2032, 'pretax_nw': 0, 'roth_nw': 0, 'trust_nw': 0, 'hsa_nw': 0, 'total_nw': 3_500_000, 'total_tax': 35_000},
    ]
    metrics = _roth_strategy_metrics(c, rows)
    assert metrics['roth_legacy_score'] != 0
    assert metrics['estate_tax_score'] != 0
    assert metrics['survivor_risk_score'] != 0
    assert metrics['liquidity_score'] != 0
    for key in ('roth_legacy_score', 'estate_tax_score', 'survivor_risk_score', 'liquidity_score'):
        assert key in metrics
