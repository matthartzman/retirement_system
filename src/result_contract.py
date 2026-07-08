"""Canonical report result contracts for workbook, UI, PDF and governance output.

The engine still uses dictionaries internally, but report-facing surfaces should
consume these contracts instead of inventing their own Roth narrative or labels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence
from src.version import VERSION


@dataclass(frozen=True)
class RothCandidateResult:
    rank: int
    label: str
    strategy_code: str
    policy: str
    target_rate: float | None
    score: float
    terminal_wealth_score: float
    tax_efficiency_score: float
    roth_legacy_score: float
    estate_tax_score: float
    survivor_risk_score: float
    liquidity_score: float
    total_objective_score: float
    terminal_net_worth: float
    after_tax_terminal_net_worth: float
    lifetime_tax: float
    total_conversions: float
    why_selected_or_rejected: str


@dataclass(frozen=True)
class RothStrategyResult:
    selected_strategy_name: str
    selected_strategy_code: str
    selected_policy: str
    objective_mode: str
    roth_bracket_strategy: str
    target_bracket: float
    irmaa_guardrail: str
    irmaa_target_tier: str
    headroom_usage_pct: float
    irmaa_headroom_usage_pct: float
    max_annual_conversion_pct_of_traditional_ira: float
    max_conversion_years: int
    forced_conversions: float
    voluntary_conversions: float
    total_conversions: float
    lifetime_tax: float
    terminal_net_worth: float
    after_tax_terminal_net_worth: float
    roth_legacy_score: float
    estate_tax_score: float
    survivor_risk_score: float
    liquidity_score: float
    binding_constraints_by_year: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[RothCandidateResult] = field(default_factory=list)
    why_selected: str = ""
    explanation: str = ""


@dataclass(frozen=True)
class PlanResult:
    """Canonical v10 result contract consumed by UI, workbook, PDF and governance.

    This is intentionally broader than a workbook sheet model. It captures the
    projection facts, semantic renderable pages, charts/report spec, tax-law
    vintage, validation, and event log so renderers never need to parse another
    renderer's output.
    """
    schema: str
    version: str
    assumptions_used: dict[str, Any]
    projection_rows: list[dict[str, Any]]
    summary_metrics: dict[str, Any]
    result_pages: list[dict[str, Any]]
    report_spec: dict[str, Any]
    event_log: list[dict[str, Any]]
    tax_law_summary: dict[str, Any]
    roth_strategy_result: RothStrategyResult | None
    tax_result: dict[str, Any]
    estate_result: dict[str, Any]
    monte_carlo_result: dict[str, Any]
    advisor_readiness_result: dict[str, Any]
    validation_result: dict[str, Any]
    performance_observability: dict[str, Any]
    warnings: list[Any]
    narrative_tokens: dict[str, str]


def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _explain_candidate(candidate: Mapping[str, Any], selected: Mapping[str, Any], rank: int) -> str:
    label = str(candidate.get('label', 'Candidate'))
    if rank == 1 and label == str(selected.get('selected_label', label)):
        return 'Selected because it produced the highest total objective score under the configured objective, guardrails, estate-tax, survivor-risk, liquidity, and legacy weights.'
    reasons=[]
    if _f(candidate.get('lifetime_tax')) < _f(selected.get('lifetime_tax')):
        reasons.append('lower lifetime tax')
    if _f(candidate.get('after_tax_terminal_nw')) > _f(selected.get('after_tax_terminal_nw')):
        reasons.append('higher after-tax terminal wealth')
    if _f(candidate.get('estate_tax_score')) < _f(selected.get('estate_tax_score')):
        reasons.append('larger estate-tax penalty')
    if _f(candidate.get('roth_legacy_score')) < _f(selected.get('roth_legacy_score')):
        reasons.append('weaker Roth legacy score')
    if _f(candidate.get('survivor_risk_score')) < _f(selected.get('survivor_risk_score')):
        reasons.append('weaker survivor-risk score')
    if _f(candidate.get('roth_wd_while_nonroth')) > 0:
        reasons.append('violates Roth-last leakage guard')
    if not reasons:
        reasons.append('lower total objective score')
    return 'Not selected: ' + '; '.join(reasons) + '.'


def build_roth_strategy_result(c: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> RothStrategyResult | None:
    ropt = dict(c.get('roth_optimization') or {})
    if not ropt:
        return None
    row_list = list(rows or [])
    forced = sum(_f((c.get('forced_roth') or {}).get(int(r.get('year',0)))) for r in row_list)
    total = sum(_f(r.get('roth_conv')) for r in row_list)
    voluntary = max(0.0, total - forced)
    terminal = row_list[-1] if row_list else {}
    candidate_dicts = list(ropt.get('candidates') or [])
    selected_label = str(ropt.get('selected_label') or ropt.get('selected_policy') or '')
    selected = next((x for x in candidate_dicts if str(x.get('label')) == selected_label), candidate_dicts[0] if candidate_dicts else {})
    sorted_candidates = sorted(candidate_dicts, key=lambda x: _f(x.get('score')), reverse=True)
    candidates=[]
    for rank, cand in enumerate(sorted_candidates, 1):
        candidates.append(RothCandidateResult(
            rank=rank,
            label=str(cand.get('label','')),
            strategy_code=str(cand.get('strategy_code') or cand.get('policy','')).upper(),
            policy=str(cand.get('policy','')),
            target_rate=(None if cand.get('target_rate') is None else _f(cand.get('target_rate'))),
            score=_f(cand.get('score')),
            terminal_wealth_score=_f(cand.get('terminal_wealth_score')),
            tax_efficiency_score=_f(cand.get('tax_efficiency_score')),
            roth_legacy_score=_f(cand.get('roth_legacy_score')),
            estate_tax_score=_f(cand.get('estate_tax_score')),
            survivor_risk_score=_f(cand.get('survivor_risk_score')),
            liquidity_score=_f(cand.get('liquidity_score')),
            total_objective_score=_f(cand.get('total_objective_score', cand.get('score'))),
            terminal_net_worth=_f(cand.get('terminal_nw')),
            after_tax_terminal_net_worth=_f(cand.get('after_tax_terminal_nw')),
            lifetime_tax=_f(cand.get('lifetime_tax')),
            total_conversions=_f(cand.get('total_conversion')),
            why_selected_or_rejected=_explain_candidate(cand, selected, rank),
        ))
    binding=[]
    for r in row_list:
        yr = int(r.get('year', 0) or 0)
        conv = _f(r.get('roth_conv'))
        if conv or r.get('conv_binding_limit') or yr <= int(c.get('plan_start', yr))+15:
            binding.append({
                'year': yr,
                'conversion': conv,
                'primary_constraint': str(r.get('conv_binding_limit') or ''),
                'secondary_constraint': str(r.get('conv_secondary_binding_limit') or ''),
                'pre_conversion_agi': _f(r.get('conv_pre_agi')),
                'target_bracket_top': _f(r.get('conv_top_24')),
                'post_conversion_agi': _f(r.get('agi')),
            })
    objective = str(ropt.get('objective_mode','BALANCED_RETIREMENT'))
    auto_optimized = bool(ropt.get('auto_optimized', True))
    is_top_ranked = bool(candidate_dicts) and str(sorted_candidates[0].get('label')) == selected_label
    if auto_optimized:
        why = (
            f"The selected strategy is {selected_label}. It ranks first under {objective} after combining tax efficiency, "
            "after-tax terminal wealth, Roth legacy value, estate-tax exposure, survivor tax risk, liquidity, and configured Medicare/tax guardrails."
        )
    elif is_top_ranked:
        why = (
            f"The selected strategy is {selected_label}, explicitly chosen by the user rather than the optimizer. "
            f"It also happens to rank first under {objective} among the scored alternatives below."
        )
    else:
        why = (
            f"The selected strategy is {selected_label}, explicitly chosen by the user rather than the optimizer. "
            f"The candidate table below shows how it compares to the optimizer-scored alternatives under {objective}."
        )
    if selected_label.lower().startswith('no voluntary'):
        why += ' The optimizer preserved the forced conversion schedule but found no voluntary conversion candidate with a better total objective score.'
    explanation = (
        f"Forced/user-directed conversions total ${forced:,.0f}; optimizer-selected voluntary conversions total ${voluntary:,.0f}; "
        f"total conversions are ${total:,.0f}. The configured target bracket is {_f(ropt.get('target_bracket', c.get('roth_target_rate',0.22))):.0%}, "
        f"with {_f(ropt.get('headroom_usage_pct',0.95)):.0%} tax headroom and {_f(ropt.get('irmaa_headroom_usage_pct',0.95)):.0%} IRMAA headroom."
    )
    return RothStrategyResult(
        selected_strategy_name=selected_label,
        selected_strategy_code=str(ropt.get('selected_strategy_code') or selected.get('strategy_code') or ''),
        selected_policy=str(ropt.get('selected_policy') or ''),
        objective_mode=objective,
        roth_bracket_strategy=str(ropt.get('roth_bracket_strategy') or c.get('roth_bracket_strategy','OPTIMIZER_CHOOSES')),
        target_bracket=_f(ropt.get('target_bracket', c.get('roth_target_rate', 0.22))),
        irmaa_guardrail=str(ropt.get('irmaa_guardrail_mode') or c.get('irmaa_guardrail_mode','AVOID_NEXT_TIER')),
        irmaa_target_tier=str(ropt.get('irmaa_target_tier') or c.get('roth_irmaa_target_tier','TIER_2')),
        headroom_usage_pct=_f(ropt.get('headroom_usage_pct', c.get('roth_headroom_usage_pct',0.95))),
        irmaa_headroom_usage_pct=_f(ropt.get('irmaa_headroom_usage_pct', c.get('roth_irmaa_headroom_usage_pct',0.95))),
        max_annual_conversion_pct_of_traditional_ira=_f(ropt.get('max_annual_conversion_pct_of_traditional_ira', c.get('roth_max_annual_conversion_pct_of_traditional_ira',0.20))),
        max_conversion_years=int(_f(ropt.get('max_conversion_years', c.get('roth_max_conversion_years',10)), 10)),
        forced_conversions=forced,
        voluntary_conversions=voluntary,
        total_conversions=total,
        lifetime_tax=sum(_f(r.get('total_tax')) for r in row_list),
        terminal_net_worth=_f(terminal.get('total_nw')),
        after_tax_terminal_net_worth=_f(selected.get('after_tax_terminal_nw', terminal.get('total_nw'))),
        roth_legacy_score=_f(selected.get('roth_legacy_score')),
        estate_tax_score=_f(selected.get('estate_tax_score')),
        survivor_risk_score=_f(selected.get('survivor_risk_score')),
        liquidity_score=_f(selected.get('liquidity_score')),
        binding_constraints_by_year=binding,
        candidates=candidates,
        why_selected=why,
        explanation=explanation,
    )


def attach_plan_result(c: dict[str, Any], rows: Sequence[Mapping[str, Any]], mc_data: Mapping[str, Any] | None = None,
                       validation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    roth = build_roth_strategy_result(c, rows)
    if roth:
        c['roth_strategy_result'] = asdict(roth)
    terminal = rows[-1] if rows else {}
    row_list = [dict(r) for r in (rows or [])]
    lifetime_tax = sum(_f(r.get('total_tax')) for r in row_list)
    total_conversions = sum(_f(r.get('roth_conv')) for r in row_list)
    try:
        from .tax_law import dataset_freshness_summary
        tax_law_summary = dataset_freshness_summary()
    except Exception:
        tax_law_summary = {}
    try:
        from .results_model import build_result_explorer_model
        result_model = build_result_explorer_model(c, row_list, dict(mc_data or {}))
        result_pages = list(result_model.get('sheets') or [])
    except Exception:
        result_pages = []
    try:
        from .report_spec import report_spec_from_results_model
        report_spec = report_spec_from_results_model({'sheets': result_pages}).to_dict()
    except Exception:
        report_spec = {}
    plan = PlanResult(
        schema='plan_result_v10',
        version=VERSION,
        assumptions_used={
            'plan_start': c.get('plan_start'),
            'plan_end': c.get('plan_end'),
            'roth_objective_mode': c.get('roth_objective_mode'),
            'estate_tax_objective_mode': c.get('estate_tax_objective_mode'),
            'roth_target_bracket_rate': c.get('roth_target_rate'),
            'roth_headroom_usage_pct': c.get('roth_headroom_usage_pct'),
            'irmaa_guardrail_mode': c.get('irmaa_guardrail_mode'),
        },
        projection_rows=row_list,
        summary_metrics={
            'start_year': row_list[0].get('year') if row_list else None,
            'end_year': row_list[-1].get('year') if row_list else None,
            'starting_net_worth': _f(row_list[0].get('total_nw')) if row_list else 0.0,
            'terminal_net_worth': _f(terminal.get('total_nw')),
            'lifetime_tax': lifetime_tax,
            'total_roth_conversions': total_conversions,
            'monte_carlo_success_rate': _f((mc_data or {}).get('success_rate')) if isinstance(mc_data, Mapping) else 0.0,
        },
        result_pages=result_pages,
        report_spec=report_spec,
        event_log=list(c.get('projection_event_log') or []),
        tax_law_summary=tax_law_summary,
        roth_strategy_result=roth,
        tax_result={'lifetime_tax': lifetime_tax},
        estate_result={'terminal_net_worth': _f(terminal.get('total_nw')), 'estate_tax_objective_mode': c.get('estate_tax_objective_mode')},
        monte_carlo_result=dict(mc_data or {}),
        advisor_readiness_result=dict(c.get('advisor_readiness') or {}),
        validation_result=dict(validation or {}),
        performance_observability=__import__('src.observability', fromlist=['summarize_performance_events']).summarize_performance_events(list(c.get('performance_events') or [])),
        warnings=list((validation or {}).get('failures', []) if isinstance(validation, Mapping) else []),
        narrative_tokens={
            'roth_selected_strategy': roth.selected_strategy_name if roth else '',
            'roth_why_selected': roth.why_selected if roth else '',
            'roth_explanation': roth.explanation if roth else '',
        },
    )
    c['plan_result'] = asdict(plan)
    return c
