"""Computation orchestration for reports, APIs, and tests.

This module deliberately has no workbook/PDF/Flask dependencies.  It gives
callers one reusable path for parse -> normalize -> optimize -> project ->
validate -> Monte Carlo, which is the first step away from the old monolith.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from .data_io import parse_client, build_plan_from_json, validate_projection, summarize_validation
from .plan_config import ensure_engine_config
from .planning_engines import monte_carlo, optimize_roth_conversion_strategy
from .projection_pipeline import run_projection_pipeline
from .governance import advisor_readiness, stress_narratives, source_citations
from .result_contract import attach_plan_result
try:
    from .market_data import pricing_diagnostics
except Exception:
    pricing_diagnostics = lambda: {}


@dataclass
class ProjectionArtifacts:
    config: Dict[str, Any]
    rows: Sequence[Mapping[str, Any]]
    mc_data: Dict[str, Any]
    validation: Dict[str, Any]


def build_model_heard_assumptions(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    last = rows[-1] if rows else {}
    first = rows[0] if rows else {}
    return {
        'plan_years': f"{c.get('plan_start')}–{c.get('plan_end')}",
        'social_security': {
            'husband_claim_age': c.get('h_ss_claim_age', c.get('ss_claim_age')),
            'wife_claim_age': c.get('w_ss_claim_age', c.get('ss_claim_age')),
            'uses_pia': bool(c.get('h_ss_pia') or c.get('w_ss_pia')),
            'spousal_benefits_enabled': bool(c.get('spousal_benefits_enabled', False)),
            'survivor_uses_deceased_claim_age': bool(c.get('survivor_benefit_uses_deceased_claim_age', False)),
            'funding_discount_year': c.get('ss_funding_discount_year'),
            'funding_discount_pct': c.get('ss_funding_discount_pct', 0.0),
        },
        'home_and_property_tax': {
            'annual_real_estate_taxes_today': c.get('real_estate_tax_base', 0.0),
            'real_estate_tax_growth_rate': c.get('real_estate_tax_growth_rate', c.get('inf', 0.0)),
            'current_home_value': c.get('home_val', 0.0),
            'base_home_sale_year': c.get('home_sale_yr', 0),
            'base_home_sale_price': c.get('home_sale_px', 0.0),
            'canonical_home_basis': c.get('home_basis', 0.0),
            'sell_home_stress_year': c.get('scen_sell_yr', 0),
            'sell_home_stress_basis': c.get('scen_sell_basis', 0.0),
            'sell_home_stress_basis_source': c.get('scen_sell_basis_source', ''),
            'sell_home_stress_sale_price': c.get('scen_sell_px', 0.0),
            'sell_home_stress_sale_price_source': c.get('scen_sell_px_source', ''),
        },
        'wellness': {
            'bridge_premiums_in_spending': True,
            'bridge_premium_today': c.get('bridge_premium', 0.0),
            'bridge_premium_monthly_today': c.get('bridge_premium_monthly', 0.0),
            'medicare_bd_in_spending': True,
            'part_b_monthly_today': c.get('partb', 0.0),
            'part_d_monthly_today': c.get('partd', 0.0),
            'part_g_monthly_today': c.get('partg', 0.0),
            'oop_in_spending': True,
            'oop_estimate_today': c.get('oop', 0.0),
            'oop_utilization_pct': c.get('oop_utilization_pct', 1.0),
            'aca_ptc_enabled': bool(c.get('aca_ptc_enabled', False)),
            'aca_benchmark_premium_today': c.get('aca_benchmark_silver_premium', 0.0),
        },
        'taxable_income': {
            'portfolio_distributions_mode': 'asset-class/symbol yield assumptions',
            'tax_exempt_interest_in_magi': True,
            'trust_gain_mode': 'lot/basis-free tracking when available; gain-fraction fallback otherwise',
        },
        'roth_and_irmaa': {
            'roth_policy': c.get('roth_policy'),
            'irmaa_guardrail_mode': c.get('irmaa_guardrail_mode'),
            'irmaa_target_tier': c.get('roth_irmaa_target_tier'),
            'irmaa_headroom_usage_pct': c.get('roth_irmaa_headroom_usage_pct'),
            'aca_ptc_loss_weight': c.get('roth_aca_ptc_loss_weight', 1.0),
        },
        'monte_carlo': {
            'engine_mode': c.get('mc_engine_mode', 'exact_scalar'),
            'simulation_count': c.get('mc_simulations'),
            'sensitivity_simulation_count': c.get('mc_sensitivity_simulations'),
        },
        'tax_and_estate': {
            'filing_status_start': first.get('filing'),
            'qss_enabled_when_dependent': bool(c.get('qss_dependent', False)),
            'basis_step_up_at_death': bool(c.get('basis_step_up_at_death', False)),
            'basis_step_up_property_regime': c.get('basis_step_up_property_regime'),
            'credit_shelter_trust_enabled': bool(c.get('cs_enabled', False)),
            'cst_funded_total': last.get('cst_excluded_from_survivor_estate', 0),
            'federal_portability_enabled': bool(c.get('federal_portability_enabled', True)),
        },
        'allocation': {
            'selection_mode': c.get('allocation_selection_mode'),
            'legacy_three_bucket_hidden': False,
        },
        'reporting': {
            'real_dollar_rows_available': True,
            'real_dollar_base_year': c.get('plan_start'),
        },
    }


def prepare_config_from_sectioned_data(data: Mapping[str, Any], url_template: str = '', optimize_roth: bool = True) -> Dict[str, Any]:
    c = parse_client(data, url_template)
    c = ensure_engine_config(c, source='sectioned')
    if optimize_roth and str(c.get('roth_policy', '')).lower() in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize'):
        c = optimize_roth_conversion_strategy(c)
        c = ensure_engine_config(c, source='sectioned.optimized')
    return c


def prepare_config_from_json(plan: Mapping[str, Any], url_template: str = '', optimize_roth: bool = True) -> Dict[str, Any]:
    c = build_plan_from_json(plan, url_template)
    c = ensure_engine_config(c, source='json')
    if optimize_roth and str(c.get('roth_policy', '')).lower() in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize'):
        c = optimize_roth_conversion_strategy(c)
        c = ensure_engine_config(c, source='json.optimized')
    return c


def run_projection_artifacts(c: Mapping[str, Any], run_mc: bool = True, enforce_release_gate: bool | None = None) -> ProjectionArtifacts:
    cfg = ensure_engine_config(c, source='runtime')
    pipeline_result = run_projection_pipeline(cfg)
    rows = pipeline_result.rows
    cfg['projection_stage_order'] = [stage.name for stage in pipeline_result.stage_order]
    cfg['projection_event_log'] = pipeline_result.event_log()
    cfg['projection_stage_summaries'] = pipeline_result.stage_summary_log()
    cfg['model_heard_assumptions'] = build_model_heard_assumptions(cfg, rows)
    validation = summarize_validation(rows, cfg)
    should_gate = bool(cfg.get('enforce_release_gate', True) if enforce_release_gate is None else enforce_release_gate)
    if should_gate and validation.get('fail_count', 0):
        details = '; '.join(f'{y}:{code}:{msg}' for y, sev, code, msg in validation.get('failures', []) if sev == 'FAIL')
        raise ValueError(f'Projection release gate failed: {details}')
    mc_data = monte_carlo(cfg) if run_mc else {}
    try:
        readiness = advisor_readiness(cfg, mc_data, pricing_diagnostics())
        cfg['advisor_readiness'] = readiness
        cfg['source_citations'] = source_citations(cfg)
        cfg['stress_narratives'] = stress_narratives(cfg, rows, mc_data)
        if isinstance(mc_data, dict):
            mc_data.setdefault('model_risk', readiness.get('model_risk', {}))
    except Exception as exc:
        cfg['advisor_readiness'] = {'status': 'REVIEW_REQUIRED', 'warnings': [str(exc)], 'is_advisor_ready': False}
    try:
        cfg = attach_plan_result(cfg, rows, mc_data, validation)
    except Exception as exc:
        cfg.setdefault('config_contract_warnings', []).append(f'PlanResult contract build failed: {exc}')
    try:
        from .results_model import build_result_explorer_model
        from .report_spec import report_spec_from_results_model
        semantic_model = build_result_explorer_model(cfg, list(rows), mc_data)
        cfg['report_spec'] = report_spec_from_results_model(semantic_model).to_dict()
    except Exception as exc:
        cfg.setdefault('config_contract_warnings', []).append(f'ReportSpec contract build failed: {exc}')
    try:
        from .local_store import save_result_snapshot
        save_result_snapshot(cfg.get('plan_result', {}), cfg.get('projection_event_log', []))
    except Exception:
        pass
    return ProjectionArtifacts(cfg, rows, mc_data, validation)
