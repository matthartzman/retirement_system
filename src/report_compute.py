"""Computation orchestration for reports, APIs, and tests.

This module deliberately has no workbook/PDF/Flask dependencies.  It gives
callers one reusable path for parse -> normalize -> optimize -> project ->
validate -> Monte Carlo, which is the first step away from the old monolith.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Sequence

from .data_io import (
    parse_client,
    build_plan_from_json,
    validate_projection,
    summarize_validation,
    _apply_allocation_projection_assumptions,
)
from .plan_config import ensure_engine_config
from .planning_engines import monte_carlo, optimize_roth_conversion_strategy, project
from .projection_pipeline import run_projection_pipeline
from .governance import advisor_readiness, stress_narratives, source_citations
from .result_contract import attach_plan_result
from . import allocation_policy as _ap
try:
    from .market_data import pricing_diagnostics
except ImportError:
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
            # Fallback matches the engine default in data_io.py / monte_carlo().
            'engine_mode': c.get('mc_engine_mode', 'vectorized'),
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
        'current_year_actuals': c.get('ytd_blend_applied', {}),
    }


def resolve_auto_horizon_and_reapply(c):
    """Optional two-pass planning-horizon discovery (opt-in via
    capital_market_config['horizon_source'] == 'auto_from_withdrawals').

    System review 2026-08-04, architect finding `data-io-calls-the-engine`:
    this used to live in data_io.py, but it runs a preliminary projection
    through planning_engines.project() to discover a better horizon, and
    parsing must not call the engine. It lives here instead; data_io.py's
    parse_client()/build_plan_from_json() still call it (via a function-scoped
    import back into this module, avoiding an import cycle) so every existing
    caller keeps the same synchronous, resolved-by-the-time-parsing-returns
    behavior.

    The manual capital-market horizon (1/3/5/10/20/25/30 years) is a guess at
    how long this household's money will stay invested. The projection
    itself already knows the answer, precisely, once it has run: it produces
    a year-by-year withdrawal ledger that src/holding_period.py turns into a
    dollar-weighted holding period. But that ledger does not exist until
    *after* _apply_allocation_projection_assumptions has already set
    c['ret']/c['mc_sigma'] from the manual/default horizon — a circular
    dependency (horizon needs withdrawal rows; rows need a return assumption
    that itself depends on the horizon).

    This resolves it the same way this codebase already resolves other
    circular tax/withdrawal dependencies (see the IRA-elective and LTCG/NIIT
    true-up loops in projection_stages/deterministic_engine.py): a bounded
    second pass. Pass 1 (the manual/default-horizon projection) already ran
    via _apply_allocation_projection_assumptions before this function is
    called. Here, pass 1's rows are used only to discover a better horizon;
    capital_market_config['horizon_years'] is then overwritten and
    _apply_allocation_projection_assumptions is re-run so c['ret']/
    c['mc_sigma'] reflect the corrected horizon before the real build
    (workbook, Monte Carlo, ...) uses them.

    Runs on a deepcopy of ``c`` (mirrors the existing Roth-strategy-candidate
    pattern in planning_engines.py: ``base = copy.deepcopy(c)``) so the
    discovery projection cannot mutate the real config's lot/account state.
    A no-op (zero cost, zero behavior change) unless horizon_source is
    explicitly set to 'auto_from_withdrawals'; any failure along the way
    silently keeps the manual/default horizon rather than breaking the build.
    """
    import copy as _copy
    from . import holding_period as _hp

    cfg = c.get('capital_market_config') or {}
    source = str(cfg.get('horizon_source', 'manual') or 'manual').strip().lower()
    if source != 'auto_from_withdrawals':
        return
    try:
        preliminary_rows = project(_copy.deepcopy(c))
        derived_horizon = _hp.withdrawal_weighted_horizon(preliminary_rows, c)
    except Exception as ex:
        cfg['horizon_source_resolved'] = 'auto_from_withdrawals_failed'
        cfg['horizon_source_error'] = str(ex)
        c['capital_market_config'] = cfg
        return
    if derived_horizon is None or derived_horizon <= 0:
        cfg['horizon_source_resolved'] = 'auto_from_withdrawals_no_signal'
        c['capital_market_config'] = cfg
        return
    cfg['manual_horizon_years'] = cfg.get('horizon_years')
    cfg['horizon_years'] = derived_horizon
    cfg['auto_derived_horizon_years'] = derived_horizon
    cfg['horizon_source_resolved'] = 'auto_from_withdrawals'
    c['capital_market_config'] = cfg
    _apply_allocation_projection_assumptions(c)


def resolve_holding_period_floors_and_reapply(c):
    """Optional two-pass holding-period real-loss floor discovery. Triggered
    by either c['holding_period_allocation_enabled'] (the opt-in floor nudge
    on optimizer/max-Sharpe modes) or allocation_selection_mode ==
    real_loss_aware (that mode's own bucket-blended solve requires this
    profile to be meaningful; selecting it is itself the opt-in).

    See resolve_auto_horizon_and_reapply's docstring for why this lives here
    rather than data_io.py (`data-io-calls-the-engine`).

    Mirrors resolve_auto_horizon_and_reapply's two-pass shape but for a
    different signal: instead of one scalar (the effective horizon), this
    discovers the full holding-period *bucket* profile (0-2yr, 3-5yr, ...,
    16+yr shares of today's liquid balance) and stores it at
    c['_holding_period_buckets'] so compute_optimal_allocation's
    optimizer/max-Sharpe branch can nudge equity_pct/cash_pct toward it, and
    its real_loss_aware branch can solve/blend per bucket (see
    optimization.py: cash is safer than equities at short holding periods,
    equities are safer than cash at long ones — the same chart-derived logic
    resolve_auto_horizon_and_reapply already uses for the scalar horizon).

    Independent of horizon_source: a plan can opt into either signal, both,
    or neither. Runs its own preliminary projection (on a deepcopy, so the
    real config's lot/balance state is never touched) rather than reusing
    resolve_auto_horizon_and_reapply's, keeping the two toggles decoupled
    and separately testable at the cost of a second discovery projection
    when both are enabled -- an acceptable tradeoff since both remain
    strictly opt-in and off by default.
    """
    import copy as _copy
    from . import holding_period as _hp

    _mode = _ap.normalize_allocation_mode(c.get('allocation_selection_mode', 'user_target'))
    if not c.get('holding_period_allocation_enabled') and _mode != _ap.ALLOCATION_MODE_REAL_LOSS_AWARE:
        return
    try:
        preliminary_rows = project(_copy.deepcopy(c))
        profile = _hp.holding_period_profile(preliminary_rows, c)
    except Exception as ex:
        c['_holding_period_buckets'] = {}
        c['_holding_period_buckets_source'] = 'error'
        c['_holding_period_buckets_error'] = str(ex)
        return
    buckets = profile.get('buckets') or {}
    c['_holding_period_buckets'] = buckets
    c['_holding_period_buckets_source'] = profile.get('source', 'unknown')
    c['_holding_period_weighted_horizon_years'] = profile.get('weighted_horizon_years')
    if buckets:
        _apply_allocation_projection_assumptions(c)


def prepare_config_from_sectioned_data(data: Mapping[str, Any], url_template: str = '', optimize_roth: bool = True, skip_live_pricing: bool = False) -> Dict[str, Any]:
    c = parse_client(data, url_template, skip_live_pricing=skip_live_pricing)
    c = ensure_engine_config(c, source='sectioned')
    if optimize_roth:
        # Always score the Roth candidate set (even for an explicit user-selected
        # policy) so the workbook's candidate comparison table is populated; the
        # function only overrides roth_policy when it was actually requested.
        c = optimize_roth_conversion_strategy(c)
        c = ensure_engine_config(c, source='sectioned.optimized')
    return c


def prepare_config_from_json(plan: Mapping[str, Any], url_template: str = '', optimize_roth: bool = True) -> Dict[str, Any]:
    c = build_plan_from_json(plan, url_template)
    c = ensure_engine_config(c, source='json')
    if optimize_roth:
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
    mc_data = monte_carlo(cfg, base_rows=rows) if run_mc else {}
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
        # Item 2.17 (finding A13): report_spec was independently derived
        # here AND inside attach_plan_result (result_contract.py), each
        # rebuilding the full semantic model via build_result_explorer_model
        # from equivalent (cfg/c, rows, mc_data) inputs -- the same
        # computation done twice per projection for the same result.
        # report_spec_from_results_model only ever reads a model's `sheets`
        # key, so attach_plan_result's own report_spec (built from that same
        # semantic model's `sheets`) is reused here instead of rebuilding it.
        _plan_report_spec = (cfg.get('plan_result') or {}).get('report_spec')
        if _plan_report_spec:
            cfg['report_spec'] = _plan_report_spec
        else:
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
