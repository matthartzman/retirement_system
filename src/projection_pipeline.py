from __future__ import annotations

"""Explicit projection pipeline facade for v10.

The deterministic engine remains the validation oracle, but callers now invoke a
named pipeline that emits stage events and can progressively absorb individual
stage implementations behind the same public contract.
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Callable, Mapping


@dataclass
class StageEvent:
    stage: str
    event_type: str
    detail: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"))


@dataclass(frozen=True)
class PipelineStage:
    name: str
    description: str


DEFAULT_STAGE_ORDER: tuple[PipelineStage, ...] = (
    PipelineStage("DeathTransition", "Apply mortality/survivor state transitions."),
    PipelineStage("AssetAppreciation", "Apply deterministic account return assumptions."),
    PipelineStage("EarnedIncome", "Recognize employment and note income."),
    PipelineStage("PayrollTax", "Assess payroll tax on earned income."),
    PipelineStage("Contributions", "Apply retirement/HSA contributions and employer match."),
    PipelineStage("SocialSecurity", "Compute Social Security and survivor benefits."),
    PipelineStage("AnnuityIncome", "Compute annuity and pension-like income."),
    PipelineStage("Spending", "Apply core, mortgage, RE tax, wellness, and event spending."),
    PipelineStage("RMDs", "Compute required minimum distributions."),
    PipelineStage("RothConversion", "Apply voluntary and forced Roth conversions."),
    PipelineStage("TaxAssessment", "Assess federal, state, NIIT, IRMAA, and related taxes."),
    PipelineStage("WithdrawalCascade", "Fund residual cash needs from the configured account cascade."),
    PipelineStage("Growth", "Finalize account growth and income reinvestment."),
    PipelineStage("NetWorth", "Produce year-end balances and reconciliations."),
)


@dataclass(frozen=True)
class StageSummary:
    stage: str
    year_count: int
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectionPipelineResult:
    rows: list[dict[str, Any]]
    events: list[StageEvent]
    stage_order: tuple[PipelineStage, ...] = DEFAULT_STAGE_ORDER
    stage_summaries: tuple[StageSummary, ...] = ()

    def event_log(self) -> list[dict[str, Any]]:
        return [e.__dict__ for e in self.events]

    def stage_summary_log(self) -> list[dict[str, Any]]:
        return [s.__dict__ for s in self.stage_summaries]


def _n(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


# A2: stages that have been genuinely extracted as independently callable
# implementations (none yet — see the review's A3/engine-decomposition arc).
# A stage absent from this registry gets its metrics from the single
# `engine_project` call rather than its own execution, so its event reports
# "inlined", not "completed" — the pipeline doesn't yet run 14 real stages,
# it runs one and describes it 14 ways.
STAGE_IMPLEMENTATIONS: dict[str, Callable[[Mapping[str, Any]], Any]] = {}


def _summarize_all_stages(stages: tuple[PipelineStage, ...], rows: list[dict[str, Any]]) -> tuple[StageSummary, ...]:
    """Accumulate every stage's metrics in one pass over ``rows`` instead of
    one full pass per stage (14 passes over the same rows previously)."""
    totals = {
        'total_earned_income': 0.0,
        'total_social_security': 0.0,
        'total_annuity_income': 0.0,
        'total_spending': 0.0,
        'total_rmds': 0.0,
        'total_roth_conversions': 0.0,
        'total_tax': 0.0,
        'total_draws': 0.0,
    }
    for r in rows:
        totals['total_earned_income'] += _n(r.get('earned'))
        totals['total_social_security'] += _n(r.get('h_ss')) + _n(r.get('w_ss'))
        totals['total_annuity_income'] += _n(r.get('wife_single_ann')) + _n(r.get('wife_joint_ann')) + _n(r.get('h_single_ann')) + _n(r.get('h_joint_ann'))
        totals['total_spending'] += _n(r.get('spend_base_yr')) + _n(r.get('rec_extra')) + _n(r.get('lump')) + _n(r.get('mortgage')) + _n(r.get('rent_yr'))
        totals['total_rmds'] += _n(r.get('rmd_total'))
        totals['total_roth_conversions'] += _n(r.get('roth_conv'))
        totals['total_tax'] += _n(r.get('total_tax'))
        totals['total_draws'] += _n(r.get('trust_wd')) + _n(r.get('hsa_wd')) + _n(r.get('roth_wd')) + _n(r.get('ira_wd')) + _n(r.get('heloc_draw'))
    terminal_net_worth = _n(rows[-1].get('total_nw')) if rows else 0.0

    metrics_by_stage = {
        'EarnedIncome': {'total_earned_income': totals['total_earned_income']},
        'SocialSecurity': {'total_social_security': totals['total_social_security']},
        'AnnuityIncome': {'total_annuity_income': totals['total_annuity_income']},
        'Spending': {'total_spending': totals['total_spending']},
        'RMDs': {'total_rmds': totals['total_rmds']},
        'RothConversion': {'total_roth_conversions': totals['total_roth_conversions']},
        'TaxAssessment': {'total_tax': totals['total_tax']},
        'WithdrawalCascade': {'total_draws': totals['total_draws']},
        'NetWorth': {'terminal_net_worth': terminal_net_worth},
    }
    return tuple(
        StageSummary(stage=stage.name, year_count=len(rows), metrics=metrics_by_stage.get(stage.name, {}))
        for stage in stages
    )


def run_projection_pipeline(config: Mapping[str, Any], engine_project: Callable[[Mapping[str, Any]], Any] | None = None) -> ProjectionPipelineResult:
    if engine_project is None:
        from .planning_engines import project as engine_project
    from .observability import observe, summarize_performance_events
    events: list[StageEvent] = []
    for stage in DEFAULT_STAGE_ORDER:
        events.append(StageEvent(stage=stage.name, event_type="scheduled", detail={"description": stage.description}))
    events.append(StageEvent(stage="ProjectionEngine", event_type="started", detail={"compatibility_bridge": False, "stage_module": "projection_stages.deterministic_engine"}))
    with observe("projection_pipeline.engine_project", component="projection_pipeline", config=None):
        rows = [dict(r) for r in engine_project(config)]
    perf_summary = summarize_performance_events(list(config.get("performance_events") or [])) if isinstance(config, dict) else {}
    events.append(StageEvent(stage="ProjectionEngine", event_type="completed", detail={"row_count": len(rows), "performance": perf_summary}))
    summaries = _summarize_all_stages(DEFAULT_STAGE_ORDER, rows)
    for stage_summary in summaries:
        implemented = stage_summary.stage in STAGE_IMPLEMENTATIONS
        contract_detail = (
            "deterministic stage contract completed"
            if implemented
            else "computed inline by the single deterministic engine call above; not yet extracted as an independently callable stage"
        )
        events.append(StageEvent(
            stage=stage_summary.stage,
            event_type="completed" if implemented else "inlined",
            detail={"contract": contract_detail, **stage_summary.metrics},
        ))
    return ProjectionPipelineResult(rows=rows, events=events, stage_summaries=summaries)
