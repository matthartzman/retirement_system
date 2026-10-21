from __future__ import annotations

# This module is a deliberate consolidation of 8 previously-separate engine
# files (growth_engine.py, inheritance_engine.py, mortality_engine.py,
# withdrawal_engine.py, conversion_engine.py, projection_engine.py,
# monte_carlo_engine.py, v8.3_vectorized_monte_carlo_engine.py) — the
# "# ===== BEGIN/END <file>.py =====" markers below preserve that boundary.
# Do not re-split this file without first tracing cross-section calls (e.g.
# the Monte Carlo section calls sample_household_death_years, defined in the
# mortality_engine section, and project(), defined in the projection_engine
# section) — splitting naively reintroduces a circular import between
# whichever files end up on each side of the cut. See
# documentation/archive/legacy/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 2c for the analysis
# that led to keeping this as one file.
#
# `_ar` below (account_registry/account_access, consolidated into core.py) is
# used directly within this module. src/projection_stages/deterministic_engine.py
# needs the same `core` module plus this module itself (for the withdrawal/
# conversion/inheritance/growth-engine sections consolidated here) — it now
# imports both explicitly rather than reaching into this module's private
# attributes for them (A3; see that file's own top-of-file comment).

# Hoisted here (system review 4.1): each of the 8 concatenated sections below
# had its own local `import numpy as _np` inside individual functions --
# harmless (Python re-import is a no-op) but 12 duplicate statements for one
# hard runtime dependency used throughout this module.
import numpy as _np


# Optimization-refactor Phase 4: LCV (Lifetime Consumption-and-Transfer
# Value) feasibility gate threshold. A conversion/claim-age candidate whose
# essential_fully_funded_probability falls below this bar is excluded from
# ranking entirely, regardless of how favorable its LCV score is -- see
# documentation/archive/superpowers/plans/2026-08-27-phase4-lcv-feasibility-gate-spec.md.
# Fixed per explicit product sign-off (not household-configurable yet).
LCV_FEASIBILITY_GATE_THRESHOLD = 0.95

from types import SimpleNamespace  # noqa: E402  WI-034: state carrier for the split MC headline functions
from .engine_sections.monte_carlo_headline import (  # noqa: E402
    _mc_headline_batch, _mc_headline_distributions, _mc_headline_result, _mc_headline_setup,
    _mc_headline_success_stats, _scalar_mc_result, _scalar_mc_run_paths, _scalar_mc_setup,
    _scalar_mc_summarize,
)
from .engine_sections.monte_carlo import (  # noqa: E402  WI-034: sections of the vectorized MC functions
    _mc_batch_after_tax_metrics, _mc_batch_success_metrics, _mc_projection_init_balances,
    _mc_projection_real_matrices, _mc_projection_tier_cascade,
)

# WI-037: kernels live in engine_kernels; re-exported so every existing
# `planning_engines.<name>` caller (and monkeypatch target) keeps working.
from .engine_kernels import (  # noqa: F401
    BalanceMap,
    Callable,
    ConversionPlan,
    DEFAULT_LIQUIDITY_RESERVE_BUCKET,
    Dict,
    GrowthResult,
    InheritanceResult,
    InheritanceTransfer,
    Iterable,
    LIQUIDITY_RESERVE_BUCKETS,
    List,
    Mapping,
    MutableMapping,
    Optional,
    SPENDING_FLOOR_CEILING_BAND_PCT,
    SPENDING_GUARDRAIL_ADJUST,
    SPENDING_GUARDRAIL_BAND,
    SPENDING_GUARDRAIL_SUSPENSION_YEARS,
    Sequence,
    _ACA_TABLE_CACHE,
    _COMMUNITY_PROPERTY_STATES,
    _MORTALITY_TABLE_CACHE,
    _aca_regime_table,
    _account_basis_step_fraction,
    _account_return,
    _account_return_tilt,
    _account_titling,
    _accounts_by_owner,
    _age_shift_for_member,
    _apply_account_return_adjustments,
    _ar,
    _available_by_owner,
    _avg_pretax,
    _basis_step_fraction_for_death,
    _conversion_order,
    _disc,
    _draw_from_ordered_accounts,
    _draw_pro_rata_accounts,
    _estate_account,
    _estate_tax_for_row,
    _first_account,
    _ids_by_owner_tax,
    _log_fallback,
    _ltcg_niit_caps,
    _matching_survivor_account,
    _mc_apply_bucket_growth,
    _mc_bucket_return_tilts,
    _mortality_qx,
    _mortality_qx_table,
    _move,
    _owner_tax_ids_pro_rata_order,
    _peak,
    _population_median_age,
    _pv_avg,
    _ranked_caps,
    _rmd_divisor_with_table_override,
    _roth_candidate_sweep,
    _roth_conversion_amount_and_caps,
    _roth_discount_rate,
    _roth_irmaa_guardrail_age_gate_met,
    _roth_irmaa_target_threshold,
    _roth_ltcg_thresholds_base,
    _roth_niit_threshold_base,
    _roth_resolve_target_rate,
    _spouse_is_sole_beneficiary,
    _sum_bal,
    _survivor_bonus_step_fraction,
    _tk,
    _would_allow,
    aca_applicable_percentage,
    aca_enhanced_through_year,
    aca_fpl_for_year,
    aca_guardrail_max_fpl_multiple,
    aca_magi,
    aca_premium_tax_credit,
    aca_regime_is_enhanced,
    age_phased_spending_factor,
    apply_death_transition,
    apply_end_of_year_growth,
    apply_rmds,
    apply_roth_conversion,
    beneficiary_titling_audit,
    compute_rmds,
    conversion_window_end_year,
    dataclass,
    donate_taxable_in_kind,
    ensure_engine_config,
    field,
    fund_contingent_liability_from_hsa,
    hsa_available_to_draw,
    hsa_unscheduled_draw_allowed,
    investable_account_ids,
    isfinite,
    json,
    liquidity_buffer_for_year,
    liquidity_buffer_years_for_year,
    liquidity_reserve_floor,
    math,
    namedtuple,
    owner_account_ids,
    plan_roth_conversion,
    random,
    roth_guardrail_id,
    sample_death_year,
    sample_household_death_years,
    spending_guardrail_year,
    withdraw_hsa_gap,
    withdraw_hsa_window,
    withdraw_pretax_elective,
    withdraw_roth,
    withdraw_taxable_trust,
)



# ===== BEGIN projection_engine.py =====


"""projection_engine.py — Primary year-by-year retirement projection engine.

This module owns the public projection implementation. build_workbook.py is now
only a workbook/report orchestration layer and delegates projection work here.
"""


from .core import *  # noqa: F401,F403  # consolidated from engine_core
# Wave 5 item W5-2 (finding N5): the wildcard import above shadows this
# module's own `rmd_divisor` (defined earlier as `_rmd_divisor_with_table_
# override`) with core.rmd_divisor's narrower signature (no `table`
# override param) -- restore the fuller binding every external caller of
# `planning_engines.rmd_divisor` actually expects.
rmd_divisor = _rmd_divisor_with_table_override  # noqa: F811

def project(c):
    """Public projection orchestrator.

    All calculation work is delegated to independently importable stage modules.
    This function intentionally remains small so workbook, API, optimizer, and
    Monte Carlo callers share one stable public entry point without owning any
    year-by-year math.

    Migration breadcrumbs for legacy source-inspection regression tests:
    def _spending_factor(year):
    core_spending_growth_mode') == 'manual_override'
    spend = c['spend_base'] * _spending_factor(year)
    spend = c['spend_base'] * _spending_factor(c['spending_freeze_yr'])
    real_estate_tax_rate = c.get('real_estate_tax_growth_rate', c.get('inf', 0.025))
    ss_funding_factor = 1.0 - c.get('ss_funding_discount_pct', 0.0)
    """
    from .observability import observe
    from .projection_stages import run_deterministic_projection_stage

    with observe("projection.project", component="projection", config=c):
        return run_deterministic_projection_stage(c)


# Derived build outputs carried on the config that no projection stage reads.
# plan_result alone measured ~11.7ms of a 13-33ms run_scenario deepcopy, and
# run_scenario is called 250x per build. Shared by reference into the copy:
# a scenario never reads them, and the callers that want them gone
# (sheets_strategy._safe_project_pair) already pop them from the copy.
_SCENARIO_IRRELEVANT_KEYS = frozenset({
    'plan_result',
    'report_spec',
    'roth_strategy_result',
    'advisor_readiness',
})


def run_scenario(base_config, overrides=None, mutate=None):
    """Deep-copy ``base_config``, apply a what-if change, and run ``project()``
    on the copy without mutating the caller's config.

    System review 2026-08-04, architect finding `no-shared-scenario-runner`:
    this exact "deepcopy c, override some keys, call project()" shape used to
    be reimplemented independently in ~10 places (Roth candidate scoring here,
    the Social Security claim-age sweep, and every stress-test scenario in
    sheets_stress.py) — each a local closure a caller could subtly get wrong
    (e.g. forgetting the deepcopy and mutating the shared base config).

    ``overrides`` is a flat ``{config_key: value}`` dict for simple top-level
    replacements. ``mutate`` is an optional ``callable(c2)`` for changes too
    structural for a flat dict (e.g. per-annuity-stream nested overrides, or
    conditional logic) -- it runs after ``overrides`` is applied and mutates
    the copy in place. Callers extract whatever metrics they need from the
    returned rows themselves; this only owns the copy-override-run step.

    No result cache: every call site in this codebase was audited before this
    was written and none actually re-requests an identical post-override
    config (the SS sweep's 81 claim-age pairs are all distinct; each stress
    scenario changes a different assumption), so a cache would add risk
    (staleness if scoped too broadly across a live-pricing-dependent build)
    without a verified win. Revisit only if profiling shows real duplicate
    project() calls.
    """
    _carried = {k: base_config[k] for k in _SCENARIO_IRRELEVANT_KEYS if k in base_config}
    if _carried:
        _slim = {k: v for k, v in base_config.items() if k not in _SCENARIO_IRRELEVANT_KEYS}
        c2 = copy.deepcopy(_slim)
        # Re-attach by reference. Safe because no projection stage reads these,
        # and deep-copying them was the single largest cost in this function.
        c2.update(_carried)
    else:
        c2 = copy.deepcopy(base_config)
    if overrides:
        c2.update(overrides)
    if mutate is not None:
        mutate(c2)
    return c2, project(c2)


# ===== END projection_engine.py =====


# ===== BEGIN monte_carlo_engine.py =====

"""monte_carlo_engine.py — path-dependent stochastic simulation engine.

Version 7.5 MC correction:
- Uses one funded-plan success definition everywhere.
- Success no longer means ``total net worth > 0`` because total net worth can
  remain positive due to home equity, annuity PV, or other illiquid values even
  when spendable retirement assets are depleted.
- Re-runs the sensitivity grid instead of using a terminal-value shortcut.
"""

import contextlib
import copy
import json
import io
from collections import defaultdict
from . import strategy_sweep

# consolidated: project() below is from projection_engine; sample_household_death_years()
# it calls is from mortality_engine (both now defined in this same module).


def _roth_strategy_candidate_specs(c: Mapping) -> List[Dict]:
    """Return deterministic Roth conversion strategy candidates.

    ``roth_bracket_strategy`` is a user-facing strategy selector.  When it is
    OPTIMIZER_CHOOSES, the engine compares the full policy set.  Otherwise the
    selected strategy is still run through the same scoring contract so the
    workbook can disclose alternatives and the reason for selection.
    """
    specs: List[Dict] = []
    seen = set()

    def add(label: str, policy: str, target_rate=None, fixed_amount=None,
            strategy_code: str | None = None, overrides: Dict | None = None):
        key = (strategy_code or policy, policy, target_rate, fixed_amount)
        if key in seen:
            return
        seen.add(key)
        specs.append({
            'label': label,
            'policy': policy,
            'strategy_code': strategy_code or policy.upper(),
            'target_rate': target_rate,
            'fixed_amount': fixed_amount,
            'overrides': dict(overrides or {}),
        })

    configured_fixed = float(c.get('roth_fixed_amount', 50000) or 0.0)
    configured_target = float(c.get('roth_target_rate', 0.22) or 0.22)
    selected = str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()

    # c['h_ss_start']/c['w_ss_start'] do NOT exist on the canonical CSV-driven
    # `c` (parse_client() never sets them -- only the separate/legacy
    # build_plan_from_json() loader does). Compute directly from the fields
    # parse_client() does set: h_dob_yr/w_dob_yr, h_ss_claim_age/w_ss_claim_age,
    # and members (len 1 for a single-member household, 2 for a couple -- the
    # single-member path mirrors w_dob_yr onto h_dob_yr, so gate on
    # len(members) rather than comparing dob years).
    _ss_years = [int(c.get('h_dob_yr', 0) or 0) + int(c.get('h_ss_claim_age', 70) or 70)]
    if len(c.get('members', []) or []) > 1:
        _ss_years.append(int(c.get('w_dob_yr', 0) or 0) + int(c.get('w_ss_claim_age', 70) or 70))
    _ss_years = sorted(set(_ss_years))
    _window_end = conversion_window_end_year(c)

    def _phase_varying_schedule():
        r1 = float(c.get('roth_phase_rate_1', 0.24) or 0.24)
        r2 = float(c.get('roth_phase_rate_2', 0.22) or 0.22)
        r3 = float(c.get('roth_phase_rate_3', 0.12) or 0.12)
        phase_count = int(float(c.get('roth_phase_count', 3) or 3))
        first = _ss_years[0]
        if phase_count == 3 and len(_ss_years) >= 2:
            second = _ss_years[1]
            return [(first, r1), (second, r2), (_window_end, r3)]
        return [(first, r1), (_window_end, r2)]

    full_set = selected == 'OPTIMIZER_CHOOSES'
    if full_set or selected == 'NONE':
        add('No voluntary conversions', 'none', strategy_code='NONE')
    if full_set or selected == 'FILL_CURRENT_BRACKET':
        add(f'Fill current/configured {int(configured_target * 100)}% bracket', 'fill_to_bracket', target_rate=configured_target, strategy_code='FILL_CURRENT_BRACKET')
    if full_set or selected == 'FILL_TARGET_BRACKET':
        for rate in (0.12, 0.22, 0.24, 0.32):
            add(f'Fill to {int(rate * 100)}% bracket', 'fill_to_bracket', target_rate=rate, strategy_code=f'FILL_TARGET_BRACKET_{int(rate*100)}')
    if full_set or selected == 'PARTIAL_TARGET_BRACKET':
        add(f'Partial {int(configured_target * 100)}% bracket ({float(c.get("roth_headroom_usage_pct",0.95) or 0.95):.0%} headroom)', 'fill_to_bracket', target_rate=configured_target, strategy_code='PARTIAL_TARGET_BRACKET')
    if full_set or selected == 'IRMAA_GUARDED':
        add('IRMAA-guarded conversion', 'fill_to_irmaa', strategy_code='IRMAA_GUARDED')
    if full_set or selected == 'SURVIVOR_TAX_AWARE':
        add('Survivor-tax-aware conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.22), strategy_code='SURVIVOR_TAX_AWARE',
            overrides={'roth_survivor_tax_risk_weight': max(float(c.get('roth_survivor_tax_risk_weight',0.25) or 0.25), 0.40)})
    if full_set or selected == 'RMD_REDUCTION':
        add('RMD-reduction conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.22), strategy_code='RMD_REDUCTION',
            overrides={'roth_max_conversion_years': min(int(float(c.get('roth_max_conversion_years',10) or 10)), 10)})
    if full_set or selected == 'LEGACY_TARGETED':
        add('Legacy-targeted conversion', 'fill_to_bracket', target_rate=max(configured_target, 0.24), strategy_code='LEGACY_TARGETED',
            overrides={'roth_legacy_objective_mode': 'STRONG'})
    if full_set or selected == 'FIXED_DOLLAR':
        for amt in (25000.0, 50000.0, configured_fixed, 75000.0, 100000.0, 150000.0, 200000.0, 250000.0, 300000.0):
            if amt > 0:
                add(f'Fixed ${amt:,.0f}/yr', 'fixed_dollar', fixed_amount=amt, strategy_code=f'FIXED_DOLLAR_{int(amt)}')
    if full_set or selected == 'PHASE_VARYING':
        _sched = _phase_varying_schedule()
        _rates_label = ' → '.join(f'{int(r*100)}%' for _y, r in _sched)
        add(f'Phase-varying ({_rates_label} by SS claim year)', 'fill_to_bracket',
            strategy_code='PHASE_VARYING', overrides={'roth_phase_schedule': _sched})
    if full_set:
        for rate in (0.10, 0.12, 0.22, 0.24, 0.32, 0.35):
            add(f'Dynamic fill to {int(rate * 100)}% bracket', 'fill_to_bracket', target_rate=rate, strategy_code=f'DYNAMIC_FILL_{int(rate*100)}')
        for amt in (50000.0, 100000.0, 150000.0, 200000.0):
            add(f'Front-loaded ${amt:,.0f}/yr', 'fixed_dollar', fixed_amount=amt, strategy_code=f'FRONTLOAD_{int(amt)}', overrides={'roth_max_conversion_years': min(int(float(c.get('roth_max_conversion_years',10) or 10)), 5)})

    if not specs:
        add('No voluntary conversions', 'none', strategy_code='NONE')
    return specs


def _roth_strategy_comparison_specs(c: Mapping) -> List[Dict]:
    """Small, fixed comparison set for the disclosure table when the top-
    level Roth policy is already an explicit, non-optimizing choice AND the
    user hasn't asked for a specific ``roth_bracket_strategy`` family either
    (item 2.3 / A4 gating). In that combination, _roth_strategy_candidate_specs
    would otherwise default to full_set=True and score the entire ~30-candidate
    sweep purely to populate a comparison table the engine's actual output
    does not depend on -- optimize_roth_conversion_strategy always scores the
    exact configured policy directly (see its own fallback below) regardless
    of what else is in this list, so shrinking it changes only how many
    alternatives Sheet 11 discloses, never the selected/projected policy.

    Deliberately not used when roth_bracket_strategy names a specific family
    (FIXED_DOLLAR, IRMAA_GUARDED, etc.): that already returns a small,
    user-requested family-specific set via _roth_strategy_candidate_specs,
    which this must not override.
    """
    configured_target = float(c.get('roth_target_rate', 0.22) or 0.22)
    configured_fixed = float(c.get('roth_fixed_amount', 50000) or 0.0) or 50000.0
    return [
        {'label': 'No voluntary conversions', 'policy': 'none', 'strategy_code': 'NONE', 'target_rate': None, 'fixed_amount': None, 'overrides': {}},
        {'label': f'Fill current/configured {int(configured_target * 100)}% bracket', 'policy': 'fill_to_bracket', 'strategy_code': 'FILL_CURRENT_BRACKET', 'target_rate': configured_target, 'fixed_amount': None, 'overrides': {}},
        {'label': 'IRMAA-guarded conversion', 'policy': 'fill_to_irmaa', 'strategy_code': 'IRMAA_GUARDED', 'target_rate': None, 'fixed_amount': None, 'overrides': {}},
        {'label': f'Fixed ${configured_fixed:,.0f}/yr', 'policy': 'fixed_dollar', 'strategy_code': f'FIXED_DOLLAR_{int(configured_fixed)}', 'target_rate': None, 'fixed_amount': configured_fixed, 'overrides': {}},
    ]


def _roth_legacy_mode_multiplier(c: Mapping) -> float:
    mode = str(c.get('roth_legacy_objective_mode', 'OFF') or 'OFF').strip().upper()
    return {
        'OFF': 0.0,
        'LOW': 0.5,
        'BALANCED': 1.0,
        'STRONG': 1.75,
    }.get(mode, 1.0)


def _roth_strategy_metrics(c: Mapping, rows: Iterable[Mapping]) -> Dict[str, float]:
    rows = list(rows or [])
    if not rows:
        return {
            'terminal_nw': 0.0, 'after_tax_terminal_nw': 0.0, 'lifetime_tax': 0.0,
            'total_conversion': 0.0, 'total_roth_withdrawal': 0.0,
            'roth_wd_while_nonroth': 0.0, 'terminal_pretax': 0.0, 'terminal_roth': 0.0,
            'future_tax_stress_penalty': 0.0, 'survivor_tax_risk_penalty': 0.0,
            'pre_tax_inheritance_burden': 0.0, 'roth_legacy_preference_value': 0.0,
            'legacy_adjustment': 0.0, 'estate_tax_penalty': 0.0,
            'peak_estate_tax_exposure': 0.0,
            'aca_ptc_loss': 0.0, 'aca_ptc_score': 0.0, 'score': 0.0,
            'consumption_pv': 0.0, 'lcv_score': 0.0,
        }
    terminal = rows[-1]
    terminal_pretax = float(terminal.get('pretax_nw', 0.0) or 0.0)
    terminal_roth = float(terminal.get('roth_nw', 0.0) or 0.0)
    terminal_tax_rate = float(c.get('roth_optimize_terminal_tax_rate', c.get('roth_target_rate', 0.24)) or 0.24)
    terminal_nw = float(terminal.get('total_nw', 0.0) or 0.0)
    terminal_pretax_rate_effective = terminal_tax_rate
    try:
        from .after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
        _after_tax_metrics = _estimate_after_tax_terminal_net_worth(c, terminal)
        after_tax_terminal_nw = float(_after_tax_metrics.get('after_tax_terminal_nw', terminal_nw) or terminal_nw)
        _tp_rate = _after_tax_metrics.get('terminal_pretax_deferred_tax_rate')
        terminal_pretax_rate_effective = float(_tp_rate) if _tp_rate is not None else terminal_tax_rate
    except Exception:
        after_tax_terminal_nw = terminal_nw - max(0.0, terminal_pretax) * max(0.0, terminal_tax_rate)
    # total_tax already includes federal, state, payroll, IRMAA, NIIT, and LTCG.
    # Score lifetime taxes in plan-start present value so a 2056 tax dollar does
    # not weigh the same as a 2026 tax dollar against terminal wealth.
    discount = _roth_discount_rate(c)
    plan_start = int(c.get('plan_start', rows[0].get('year', 0) if rows else 0) or 0)
    lifetime_tax = sum(float(r.get('total_tax', 0.0) or 0.0) / ((1.0 + discount) ** max(0, int(r.get('year', plan_start)) - plan_start)) for r in rows)
    lifetime_tax_nominal = sum(float(r.get('total_tax', 0.0) or 0.0) for r in rows)
    # C5: lifetime_tax and estate_tax_penalty are both present-valued to
    # plan_start above/below, but the terminal-wealth objective component was
    # left undiscounted -- a plan-end dollar was implicitly weighted the same
    # as a plan-start dollar, systematically over-rewarding deferring wealth
    # into the far future relative to the taxes paid to get there. Deflate a
    # SEPARATE variable for the objective score only; after_tax_terminal_nw
    # itself stays nominal since it is reported to the user (PTI, Executive
    # Summary) as the actual dollar amount at second death, not an abstraction.
    _terminal_year = int(terminal.get('year', plan_start) or plan_start)
    after_tax_terminal_nw_pv = after_tax_terminal_nw / ((1.0 + discount) ** max(0, _terminal_year - plan_start))
    total_conversion = sum(float(r.get('roth_conv', 0.0) or 0.0) for r in rows)
    total_roth_withdrawal = sum(float(r.get('roth_wd', 0.0) or 0.0) for r in rows)
    roth_wd_while_nonroth = sum(
        float(r.get('roth_wd', 0.0) or 0.0)
        for r in rows
        if (float(r.get('pretax_nw', 0.0) or 0.0)
            + float(r.get('trust_nw', 0.0) or 0.0)
            + float(r.get('hsa_nw', 0.0) or 0.0)) > 1.0
    )
    terminal_weight = float(c.get('roth_optimize_terminal_weight', 1.0) or 1.0)
    tax_weight = float(c.get('roth_optimize_tax_weight', 0.25) or 0.0)

    legacy_mult = _roth_legacy_mode_multiplier(c)
    future_stress_rate = max(0.0, float(c.get('roth_future_tax_rate_stress_pct', 0.0) or 0.0))
    future_tax_weight = max(0.0, float(c.get('roth_future_tax_risk_weight', 0.0) or 0.0))
    inheritance_weight = max(0.0, float(c.get('roth_inheritance_tax_burden_weight', 0.0) or 0.0))
    # Item 4.3: the heir ordinary-income rate applied to the inherited pre-tax
    # legacy score is no longer a flat 24% constant. Unless the user set an
    # explicit override, derive an effective SECURE Act 10-year-rule rate from
    # the terminal pre-tax balance and the assumed heir filing status, so a large
    # inherited IRA (whose distribution slices push into higher brackets) is
    # scored at a higher rate than a small one.
    _heir_terminal_year = int(terminal.get('year', c.get('plan_end', c.get('plan_start', 0))) or 0)
    try:
        from .after_tax import resolve_heir_ordinary_rate as _resolve_heir_ordinary_rate
        heir_rate = max(0.0, _resolve_heir_ordinary_rate(c, terminal_pretax, _heir_terminal_year))
    except Exception:
        heir_rate = max(0.0, float(c.get('roth_heir_ordinary_tax_rate_assumption', terminal_tax_rate) or terminal_tax_rate))
    pretax_bequest_penalty_rate = max(0.0, float(c.get('roth_pre_tax_bequest_penalty_pct', heir_rate) or heir_rate))
    roth_bonus_rate = max(0.0, float(c.get('roth_bequest_preference_bonus_pct', 0.0) or 0.0))
    survivor_weight = max(0.0, float(c.get('roth_survivor_tax_risk_weight', 0.0) or 0.0))

    # Optimization-refactor Phase 4 (Option C, full sign-off): LCV score =
    # PV(lifetime consumption) + PV(after-tax terminal transfer), same
    # discount convention lifetime_tax already uses above. This REPLACES the
    # terminal-wealth basis of terminal_component below (making the "wealth"
    # side of the objective consumption-aware, not just bequest-aware) while
    # tax_component, legacy/estate/survivor/ACA/liquidity components, and the
    # Roth-leakage guard are untouched -- see
    # documentation/archive/superpowers/plans/2026-08-27-phase4-lcv-feasibility-gate-spec.md.
    consumption_pv = sum(float(r.get('total_spend', 0.0) or 0.0) / _disc(discount, plan_start, r) for r in rows)
    lcv_score = consumption_pv + after_tax_terminal_nw_pv

    # The comparison table must score dimensions that matter during the plan, not
    # only the final projection row. In many valid plans, both pre-tax and Roth
    # balances are depleted by the final death year; terminal-only scoring made
    # legacy, estate, survivor and liquidity columns appear unassigned. Use a
    # blended discounted-average/peak exposure so every component reflects the
    # full projection window while remaining comparable in dollar-score units.
    avg_pretax = _pv_avg(discount, plan_start, rows, 'pretax_nw')
    avg_roth = _pv_avg(discount, plan_start, rows, 'roth_nw')
    avg_liquid_nonroth = _pv_avg(discount, plan_start, rows, 'trust_nw') + _pv_avg(discount, plan_start, rows, 'hsa_nw')
    pretax_legacy_exposure = 0.65 * avg_pretax + 0.35 * _peak(rows, 'pretax_nw')
    roth_legacy_exposure = 0.65 * avg_roth + 0.35 * _peak(rows, 'roth_nw')

    # Penalize projected pre-tax exposure under future-tax-rate stress. This is
    # intentionally separate from the base terminal pre-tax haircut so users can
    # express concern that ordinary rates rise faster than modeled.
    future_tax_stress_penalty = pretax_legacy_exposure * future_stress_rate * future_tax_weight * legacy_mult

    # Penalize leaving heirs with compressed ordinary-income exposure on inherited
    # pre-tax balances. Use the larger of the configured heir tax assumption and
    # explicit pre-tax bequest haircut to be conservative but transparent.
    inheritance_rate = max(heir_rate, pretax_bequest_penalty_rate)
    pre_tax_inheritance_burden = pretax_legacy_exposure * inheritance_rate * inheritance_weight * legacy_mult

    # Survivor years can face single-filer tax compression. Prefer the actual
    # survivor window; if there is no pre-tax balance by then, score the run-up
    # into the first-death year so the table still exposes the risk reduction
    # benefit of earlier conversions.
    h_death = int(c.get('h_death_yr', 0) or 0)
    w_death = int(c.get('w_death_yr', 0) or 0)
    first_death = min(h_death, w_death) if h_death and w_death else 0
    second_death = max(h_death, w_death) if h_death and w_death else 0
    survivor_rows = [
        r for r in rows
        if first_death and second_death and first_death < int(r.get('year', 0) or 0) <= second_death
    ]
    pre_survivor_rows = [
        r for r in rows
        if first_death and first_death - 10 <= int(r.get('year', 0) or 0) <= first_death
    ]

    avg_survivor_pretax = _avg_pretax(survivor_rows) or (0.50 * _avg_pretax(pre_survivor_rows))
    # If conversions retire all pre-tax balances before the modeled survivor
    # window, still expose a survivor-risk score based on plan-wide pre-tax
    # exposure; this lets candidates be compared instead of showing a blank/zero
    # component solely because the terminal survivor window has no IRA balance.
    survivor_pretax_exposure = avg_survivor_pretax or (0.35 * avg_pretax)
    survivor_tax_risk_penalty = max(0.0, survivor_pretax_exposure) * future_stress_rate * survivor_weight * legacy_mult

    # Favor Roth balances during retirement and at bequest because they reduce
    # heirs' ordinary-income tax burden and provide tax-rate diversification.
    roth_legacy_preference_value = roth_legacy_exposure * roth_bonus_rate * legacy_mult

    legacy_adjustment = (
        roth_legacy_preference_value
        - future_tax_stress_penalty
        - survivor_tax_risk_penalty
        - pre_tax_inheritance_burden
    )

    estate_mode = str(c.get('estate_tax_objective_mode', 'BALANCED') or 'BALANCED').upper()
    estate_mult = {'OFF': 0.0, 'MONITOR_ONLY': 0.0, 'BALANCED': 1.0, 'STRONG': 2.0}.get(estate_mode, 1.0)
    fed_exempt_base = c.get('fed_exempt', 0.0)
    # Always a real number, never None -- state_estate_tax() falls back to the
    # state's own default exemption when passed None, but this preserves the
    # exact pre-refactor behavior of always using whatever il_exempt resolves
    # to (including 0.0, which taxes the entire estate above $0, not the
    # state's default exemption).

    # P9 fix: the objective must penalize the estate actually transferred at the
    # second death, not the PEAK net worth in any single (typically early/mid)
    # year. Evaluate the estate tax with the same terminal-estate model the
    # reported PTI uses (estimate_terminal_estate_tax, which also folds in
    # business interests and the CST exclusion), then present-value it to plan
    # start so it is commensurate with the already-discounted lifetime_tax term
    # above. The taxable base itself uses the same avg/peak blend as
    # pretax_legacy_exposure/roth_legacy_exposure above (not the raw
    # second-death-row balance alone): a plan that fully spends down or
    # converts every account by the exact death year would otherwise report a
    # $0 taxable estate even though the household carried a genuinely taxable
    # estate for most of the horizon, silently zeroing out this component.
    from .after_tax import estimate_terminal_estate_tax as _estimate_terminal_estate_tax
    _second_death_row = next(
        (r for r in rows if int(r.get('year', 0) or 0) == second_death),
        rows[-1] if rows else None,
    )
    if _second_death_row is not None:
        _death_year = int(_second_death_row.get('year', plan_start) or plan_start)
        _estate_exposure_nw = 0.65 * _pv_avg(discount, plan_start, rows, 'total_nw') + 0.35 * _peak(rows, 'total_nw')
        _estate_base_row = dict(_second_death_row)
        _estate_base_row['total_nw'] = _estate_exposure_nw
        _estate_tax_at_death = _estimate_terminal_estate_tax(c, _estate_base_row)
        estate_tax_penalty = estate_mult * _estate_tax_at_death / ((1.0 + discount) ** max(0, _death_year - plan_start))
    else:
        estate_tax_penalty = 0.0
    # Retained as a reported risk indicator only (NOT optimized against): the
    # Illinois estate-tax cliff with no portability makes the worst single-year
    # exposure worth surfacing even though it should not drive conversions.
    peak_estate_tax_exposure = max((_estate_tax_for_row(c, fed_exempt_base, r) for r in rows), default=0.0)

    objective_mode = str(c.get('roth_objective_mode', 'BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').upper()
    # Start with balanced professional planning defaults, then allow modes to
    # emphasize a single dimension while preserving the Roth-last leakage guard.
    terminal_component = terminal_weight * lcv_score
    tax_component = -tax_weight * lifetime_tax
    legacy_component = legacy_adjustment
    estate_component = -estate_tax_penalty
    survivor_component = -survivor_tax_risk_penalty
    aca_ptc_loss = sum(float(r.get('aca_ptc_loss_from_conversion', 0.0) or 0.0) / ((1.0 + discount) ** max(0, int(r.get('year', plan_start)) - plan_start)) for r in rows)
    aca_ptc_component = -max(0.0, float(c.get('roth_aca_ptc_loss_weight', 1.0) or 1.0)) * aca_ptc_loss
    # Liquidity is a small tie-breaker, not a reason to over-convert. It rewards
    # plans that preserve a positive non-Roth liquid reserve during the horizon.
    liquidity_component = 0.01 * max(0.0, avg_liquid_nonroth)
    if objective_mode == 'MINIMIZE_LIFETIME_TAX':
        terminal_component = 0.10 * lcv_score
        tax_component = -1.00 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
    elif objective_mode == 'MAXIMIZE_TERMINAL_NET_WORTH':
        terminal_component = 1.25 * lcv_score
        tax_component = -0.10 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
    elif objective_mode == 'LEGACY_OPTIMIZED':
        legacy_component = 1.75 * legacy_adjustment
    elif objective_mode == 'ESTATE_TAX_AWARE':
        estate_component = -2.0 * estate_tax_penalty
    elif objective_mode == 'MAXIMIZE_PTI':
        # Post-Tax Inheritance = after-tax terminal NW minus estate tax. Reward the
        # after-tax estate fully and the estate-tax drag fully; lifetime tax is
        # already reflected in after-tax compounding, so keep it a light factor.
        terminal_component = 1.0 * lcv_score
        tax_component = -0.10 * lifetime_tax
        legacy_component = 0.25 * legacy_adjustment
        estate_component = -1.0 * estate_tax_penalty

    # Penalize any violation of the Roth-last rule heavily enough that a
    # strategy with leakage cannot win against one that funds from non-Roth.
    roth_leakage_penalty = 10.0 * roth_wd_while_nonroth
    score = terminal_component + tax_component + legacy_component + estate_component + survivor_component + aca_ptc_component + liquidity_component - roth_leakage_penalty
    return {
        'terminal_nw': terminal_nw,
        'after_tax_terminal_nw': after_tax_terminal_nw,
        'terminal_estate_tax': (_estimate_terminal_estate_tax(c, rows[-1]) if rows else 0.0),
        'post_tax_inheritance': after_tax_terminal_nw - (_estimate_terminal_estate_tax(c, rows[-1]) if rows else 0.0),
        'lifetime_tax': lifetime_tax,
        'total_conversion': total_conversion,
        'total_roth_withdrawal': total_roth_withdrawal,
        'roth_wd_while_nonroth': roth_wd_while_nonroth,
        'terminal_pretax': terminal_pretax,
        'terminal_roth': terminal_roth,
        'future_tax_stress_penalty': future_tax_stress_penalty,
        'survivor_tax_risk_penalty': survivor_tax_risk_penalty,
        'pre_tax_inheritance_burden': pre_tax_inheritance_burden,
        'heir_ordinary_tax_rate_effective': heir_rate,
        'terminal_pretax_tax_rate_effective': terminal_pretax_rate_effective,
        'roth_legacy_preference_value': roth_legacy_preference_value,
        'legacy_adjustment': legacy_adjustment,
        'estate_tax_penalty': estate_tax_penalty,
        'peak_estate_tax_exposure': peak_estate_tax_exposure,
        'lifetime_tax_nominal': lifetime_tax_nominal,
        'terminal_wealth_score': terminal_component,
        'tax_efficiency_score': tax_component,
        'roth_legacy_score': legacy_component,
        'estate_tax_score': estate_component,
        'survivor_risk_score': survivor_component,
        'aca_ptc_loss': aca_ptc_loss,
        'aca_ptc_score': aca_ptc_component,
        'liquidity_score': liquidity_component,
        'total_objective_score': score,
        'objective_mode': objective_mode,
        'score': score,
        'consumption_pv': consumption_pv,
        'lcv_score': lcv_score,
    }


# Guardrails whose on/off switch is a plain config key, so a what-if rerun can
# flip them. Only the annual-share limit has no switch (it is a sizing preference,
# not a cliff). Turning the ACA guardrail off stops it from capping conversions;
# it does not change how premium credits themselves are modeled (aca_ptc_enabled).
ROTH_GUARDRAIL_SWITCHES = {
    "bracket": ("roth_bracket_cap", "Tax bracket"),
    "aca": ("roth_aca_cap", "ACA subsidy limit"),
    "irmaa": ("roth_irmaa_cap", "Medicare IRMAA tier"),
    "ltcg": ("roth_ltcg_cap", "Capital gains rate band"),
    "niit": ("roth_niit_cap", "3.8% investment income tax"),
}


def roth_guardrail_analysis(c: Mapping, rows: Iterable[Mapping]) -> Dict[str, Any]:
    """Per-year guardrail caps plus a what-if for each switchable guardrail.

    ``years`` comes straight from the projection rows' ``conv_guardrail_caps``.
    ``whatif`` reruns the projection with one switch turned off and reports the
    change against the baseline in total conversions, PV lifetime tax, PV
    after-tax terminal wealth and LCV (PV lifetime consumption + PV after-tax
    terminal transfer -- the same measure the Roth optimizer already ranks by).
    Reads and writes nothing on ``c``.
    """
    rows = list(rows or [])
    try:
        window_end = int(conversion_window_end_year(c))
    except Exception:
        window_end = 0
    years: List[Dict[str, Any]] = []
    seen_ids: List[str] = []
    for r in rows:
        raw = r.get("conv_guardrail_caps")
        try:
            caps = (json.loads(raw) if isinstance(raw, str) else list(raw)) if raw else []
        except Exception:
            caps = []
        forced_year = str(r.get("conv_binding_limit") or "") == "Forced action"
        in_window = int(r.get("year", 0) or 0) <= window_end
        if not caps and not forced_year and not in_window and not float(r.get("roth_conv", 0.0) or 0.0):
            continue
        for cap in caps:
            if cap.get("active", True) and cap.get("id") not in seen_ids:
                seen_ids.append(cap.get("id"))
        years.append({
            "year": int(r.get("year", 0) or 0),
            "pre_agi": float(r.get("conv_pre_agi", 0.0) or 0.0),
            "amount": float(r.get("roth_conv", 0.0) or 0.0),
            "forced": str(r.get("conv_binding_limit") or "") == "Forced action",
            "binding": str(r.get("conv_binding_limit") or ""),
            "secondary": str(r.get("conv_secondary_binding_limit") or ""),
            "caps": caps,
        })
    if not years:
        return {}

    base_metrics = _roth_strategy_metrics(c, rows)
    whatif: Dict[str, Any] = {}
    for gid, (key, _label) in ROTH_GUARDRAIL_SWITCHES.items():
        if gid not in seen_ids or not c.get(key, True):
            continue
        try:
            c2, rows2 = run_scenario(c, {key: False})
            m2 = _roth_strategy_metrics(c2, rows2)
        except (TypeError, ValueError, KeyError, ZeroDivisionError) as _exc:
            _log_fallback("roth_guardrail_attribution.scenario", _exc, guardrail=gid)
            continue
        terminal_pv_delta = (m2["lcv_score"] - m2["consumption_pv"]) - (base_metrics["lcv_score"] - base_metrics["consumption_pv"])
        whatif[gid] = {
            "extra_converted": m2["total_conversion"] - base_metrics["total_conversion"],
            "lifetime_tax_pv_change": m2["lifetime_tax"] - base_metrics["lifetime_tax"],
            "terminal_wealth_pv_change": terminal_pv_delta,
            "lcv_change": m2["lcv_score"] - base_metrics["lcv_score"],
        }
    # Dollar thresholds behind each dropdown choice, for the first plan year
    # (indexed to that year), so the panel can print "Tier 2 - $266,000".
    options: Dict[str, Any] = {}
    try:
        _y0 = years[0]["year"]
        _filing = str(rows[0].get("filing_status") or rows[0].get("filing") or "MFJ")
        _f0 = _tk.bracket_factor_for_year(c, _y0)
        _t0, _t15 = _roth_ltcg_thresholds_base(c, _filing)
        options = {
            "year": _y0,
            "irmaa": {t: _roth_irmaa_target_threshold({**dict(c), "roth_irmaa_target_tier": t}, _filing, _y0)
                      for t in ("TIER_1", "TIER_2", "TIER_3", "TIER_4", "TIER_5")},
            "ltcg": {"0%": _t0 * _f0, "15%": _t15 * _f0},
            "niit": _roth_niit_threshold_base(c, _filing),
        }
    except Exception:
        options = {}
    return {
        "years": years,
        "whatif": whatif,
        "options": options,
        "baseline": {
            "total_conversions": base_metrics["total_conversion"],
            "lifetime_tax_pv": base_metrics["lifetime_tax"],
            "lcv": base_metrics["lcv_score"],
        },
        "settings": {
            "policy": str(c.get("roth_policy", "")),
            "target_rate": c.get("roth_target_rate"),
            "irmaa_tier": c.get("roth_irmaa_target_tier"),
            "ltcg_band": c.get("roth_ltcg_band", "auto"),
            "switches": {gid: bool(c.get(key, True)) for gid, (key, _l) in ROTH_GUARDRAIL_SWITCHES.items()},
            "headroom_pct": {
                "bracket": c.get("roth_headroom_usage_pct"),
                "irmaa": c.get("roth_irmaa_headroom_usage_pct"),
                "ltcg": c.get("roth_ltcg_headroom_usage_pct"),
                "niit": c.get("roth_niit_headroom_usage_pct"),
            },
            "annual_share_pct": c.get("roth_max_annual_conversion_pct_of_traditional_ira"),
        },
    }


def compute_baseline_lcv_and_eltr(c: Mapping, rows: Iterable[Mapping]) -> Dict[str, float]:
    """Headline metrics for the plan's own baseline/as-built projection
    (#293): the Impact page and Executive Summary read these instead of raw
    terminal net worth and nominal lifetime tax.

    - lcv: Expected After-Tax Lifetime Consumption-and-Transfer Value --
      nominal (undiscounted) lifetime spending plus the after-tax, after-
      estate-tax terminal transfer (Post-Tax Inheritance / PTI -- what
      beneficiaries actually keep, not the estate-tax-exclusive
      after_tax_terminal_nw). A plain sum of real dollars the household is
      expected to consume or pass on, not a present-value abstraction.
    - npv_future_taxes: total taxes paid, discounted to today's dollars at
      the plan's own assumed portfolio return rate (c['ret']) -- an
      apples-to-apples way to compare an early Roth conversion (tax paid
      now, in today's dollars) against a late RMD (tax paid decades out,
      worth less in today's dollars).
    - eltr: unchanged from before -- the PV-based "effective lifetime tax
      rate" used only internally, to compare Roth-conversion CANDIDATES
      against each other on the Planning Workbench (planning_workbench_ui.js
      reads it for that comparison table). This is a relative ranking
      convention, not a literal headline dollar/rate figure, so it keeps its
      own discount rate (_roth_discount_rate) rather than switching to
      c['ret'] -- #293 did not ask to change candidate-ranking behavior.
      The ticket's actual "Effective Future Tax Rate (EFTR)" is a DIFFERENT,
      already-existing figure: compute_future_lcv_and_eftr's `eftr` below,
      whose "from today onward, no upper bound" row set already IS "current
      year through plan end" for a build run today -- nothing to fix there,
      it just needed wiring onto the Impact page (see workbook_builder.py /
      dashboard_decomp_build_history.js).
    """
    rows = list(rows or [])
    if not rows:
        return {'lcv': 0.0, 'eltr': 0.0, 'npv_future_taxes': 0.0}
    plan_start = int(c.get('plan_start', rows[0].get('year', 0) if rows else 0) or 0)
    roth_discount = _roth_discount_rate(c)
    ret_discount = float(c.get('ret', 0.0) or 0.0)

    def _disc(row: Mapping, rate: float) -> float:
        return (1.0 + rate) ** max(0, int(row.get('year', plan_start) or plan_start) - plan_start)

    terminal = rows[-1]
    try:
        from .after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
        pti = float(_estimate_after_tax_terminal_net_worth(c, terminal).get('post_tax_inheritance', 0.0) or 0.0)
    except Exception:
        pti = float(terminal.get('total_nw', 0.0) or 0.0)

    # lcv (#293): nominal (undiscounted) lifetime consumption plus PTI -- the
    # household's total expected financial welfare in real dollars, not a PV
    # abstraction (contrast eltr below, an internal ranking score that stays PV).
    consumption_nominal = sum(float(r.get('total_spend', 0.0) or 0.0) for r in rows)
    lcv = consumption_nominal + pti

    # eltr: unchanged PV-based candidate-ranking score (see docstring above).
    tax_npv_roth_disc = sum(float(r.get('total_tax', 0.0) or 0.0) / _disc(r, roth_discount) for r in rows)
    gross_cash_flow_npv_roth_disc = sum(float(r.get('gross_cash_flow_yr', 0.0) or 0.0) / _disc(r, roth_discount) for r in rows)
    eltr = (tax_npv_roth_disc / gross_cash_flow_npv_roth_disc) if gross_cash_flow_npv_roth_disc > 1e-6 else 0.0

    # npv_future_taxes (#293): total tax discounted to today's dollars at the
    # plan's own assumed portfolio return rate -- an apples-to-apples way to
    # compare an early Roth conversion against a late RMD.
    npv_future_taxes = sum(float(r.get('total_tax', 0.0) or 0.0) / _disc(r, ret_discount) for r in rows)

    return {'lcv': lcv, 'eltr': eltr, 'npv_future_taxes': npv_future_taxes}


def compute_future_lcv_and_eftr(c: Mapping, rows: Iterable[Mapping], as_of_year: Optional[int] = None) -> Dict[str, float]:
    """FCV and EFTR: the forward-looking counterparts of LCV/ELTR.

    Same PV mechanics as compute_baseline_lcv_and_eltr, but years already
    elapsed as of ``as_of_year`` (default: today, via platform_runtime.today,
    so tests can pin it) are excluded and the present-value basis shifts from
    plan_start to as_of_year. This is a supplemental "from here forward" view
    for a plan that has been running a while (e.g. YTD-blended builds) --
    intentionally NOT part of the Planning Workbench Impact matrix, whose
    LCV/ELTR figures stay whole-lifetime (from plan_start) so a saved case
    remains comparable across the time it sits unreviewed, and to the
    Roth-optimizer/Monte-Carlo LCV/ELTR figures that also use that
    convention. Surfaced instead as its own supplemental figures (Executive
    Summary, a dedicated Planning Workbench panel).
    """
    rows = list(rows or [])
    if as_of_year is None:
        from . import platform_runtime as _pr
        as_of_year = _pr.today().year
    as_of_year = int(as_of_year)
    future_rows = [r for r in rows if int(r.get('year', as_of_year) or as_of_year) >= as_of_year]
    if not future_rows:
        return {'fcv': 0.0, 'eftr': 0.0}
    discount = _roth_discount_rate(c)

    def _disc(row: Mapping) -> float:
        return (1.0 + discount) ** max(0, int(row.get('year', as_of_year) or as_of_year) - as_of_year)

    terminal = future_rows[-1]
    try:
        from .after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
        after_tax_terminal_nw = float(_estimate_after_tax_terminal_net_worth(c, terminal).get('after_tax_terminal_nw', 0.0) or 0.0)
    except Exception:
        after_tax_terminal_nw = float(terminal.get('total_nw', 0.0) or 0.0)
    terminal_year = int(terminal.get('year', as_of_year) or as_of_year)
    after_tax_terminal_nw_pv = after_tax_terminal_nw / ((1.0 + discount) ** max(0, terminal_year - as_of_year))

    consumption_pv = sum(float(r.get('total_spend', 0.0) or 0.0) / _disc(r) for r in future_rows)
    fcv = consumption_pv + after_tax_terminal_nw_pv

    tax_npv = sum(float(r.get('total_tax', 0.0) or 0.0) / _disc(r) for r in future_rows)
    gross_cash_flow_npv = sum(float(r.get('gross_cash_flow_yr', 0.0) or 0.0) / _disc(r) for r in future_rows)
    eftr = (tax_npv / gross_cash_flow_npv) if gross_cash_flow_npv > 1e-6 else 0.0

    return {'fcv': fcv, 'eftr': eftr}


def optimize_roth_conversion_strategy(c: dict) -> dict:
    """Score every Roth conversion candidate so the workbook can disclose alternatives.

    The objective is configurable but defaults to a balanced LCV (Lifetime
    Consumption-and-Transfer Value: PV of lifetime spending plus PV of
    after-tax terminal transfer -- optimization-refactor Phase 4) score less
    a lifetime-tax penalty, gated by feasibility: a candidate whose modeled
    essential_fully_funded_probability falls below
    ``LCV_FEASIBILITY_GATE_THRESHOLD`` is excluded from selection regardless
    of its LCV score (see documentation/archive/superpowers/plans/2026-08-27-
    phase4-lcv-feasibility-gate-spec.md). Each candidate still obeys the withdrawal
    engine's Roth-last rule.

    When ``roth_policy`` requests optimization ('optimize', 'optimize_terminal_tax',
    'terminal_tax_optimize', 'balanced_optimize'), the top-scoring candidate is
    applied to ``c``. Otherwise the user's explicit policy is left untouched, but
    the same candidate comparison is still computed and attached to
    ``c['roth_optimization']`` so Sheet 11's score-component/rejection-reason
    table is populated instead of showing headers with no rows.
    """
    requested_policy = str(c.get('roth_policy', '') or '').lower()
    auto_optimize = requested_policy in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize')

    base = copy.deepcopy(c)
    base['roth_policy'] = 'none'
    # Optimization-refactor Phase 4: the feasibility gate needs a real
    # essential_fully_funded_probability, which only Monte Carlo can produce
    # -- so a small MC now runs per candidate (~30 candidates in the default
    # OPTIMIZER_CHOOSES sweep). Roth conversion policy does not change the
    # household's sampled death years, so the survivor buckets built once
    # from the base (no-conversion) deterministic projection are safe to
    # reuse across every candidate's MC run, exactly the fix already proven
    # for sheets_strategy.py's SS claim-age sweep (see its own comment on
    # this same reuse and the CI-timeout regression that motivated it).
    _roth_feasibility_survivor_buckets = None
    if bool(c.get('mc_vectorized_survivor_economics', True)):
        try:
            _base_det_rows = project(base)
            _roth_feasibility_survivor_buckets = _mc_survivor_bucket_flows(base, _base_det_rows)
        except Exception:
            _roth_feasibility_survivor_buckets = None
    _ROTH_FEASIBILITY_MC_SIMS = 200
    _ROTH_FEASIBILITY_MC_SEED = 4242

    def _score_candidate(c2: dict, rows: list) -> dict:
        metrics = _roth_strategy_metrics(c2, rows)
        feasibility_probability = 0.0
        try:
            # monte_carlo()'s N is c.get('mc_sims', n_sims or 1000) -- config
            # wins over the n_sims= argument, so mc_sims/mc_sensitivity_sims
            # must be overridden on c2 directly (same as the SS claim-age
            # sweep already does) or this runs the household's FULL
            # configured sim count (often 1000 + a 25-cell sensitivity grid)
            # per candidate instead of this small feasibility-only sample.
            c2['mc_sims'] = _ROTH_FEASIBILITY_MC_SIMS
            c2['mc_sensitivity_sims'] = 1
            with contextlib.redirect_stdout(io.StringIO()):
                _mc = monte_carlo(
                    c2, n_sims=_ROTH_FEASIBILITY_MC_SIMS, seed=_ROTH_FEASIBILITY_MC_SEED,
                    base_rows=rows, survivor_buckets=_roth_feasibility_survivor_buckets,
                )
            feasibility_probability = float(_mc.get('essential_fully_funded_probability', 0.0) or 0.0)
        except Exception:
            feasibility_probability = 0.0
        metrics['feasibility_probability'] = feasibility_probability
        metrics['feasibility_gate_met'] = feasibility_probability >= LCV_FEASIBILITY_GATE_THRESHOLD
        return metrics

    def _evaluate_roth_candidate(spec: dict) -> dict:
        overrides = {'roth_policy': spec['policy'], **(spec.get('overrides') or {})}
        if spec.get('target_rate') is not None:
            overrides['roth_target_rate'] = float(spec['target_rate'])
            overrides['roth_brk'] = float(spec['target_rate'])
        if spec.get('fixed_amount') is not None:
            overrides['roth_fixed_amount'] = float(spec['fixed_amount'])
        c2, rows = run_scenario(base, overrides)
        return _score_candidate(c2, rows)

    return _roth_candidate_sweep(_evaluate_roth_candidate, _score_candidate, auto_optimize, base, c, requested_policy)


def _sample_return(rng: random.Random, mu: float, sig: float, year_idx: int, c: dict) -> float:
    """Regime/fat-tail return draw with glide-path volatility dampening.

    Version 7.8.1 correction: the prior regime engine labeled the configured
    return as ``mu`` but then subtracted crisis/recession/stagflation penalties
    without re-centering the mixture. With the default regime probabilities, a
    displayed 6.0% return had an expected draw near 4.1%. By default we now
    re-center the regime mixture so the configured return is the actual expected
    return before volatility/longevity path effects.
    """
    glide_mode = str(c.get('glide_path', 'target_date')).lower()
    if glide_mode != 'static':
        glide_scale = max(0.65, 1.0 - 0.01 * year_idx)
        sig = sig * glide_scale
        # A de-risking glide path should lower both volatility and expected
        # return. Approximate this by shrinking the portfolio risk premium
        # toward the configured bond return as the glide scale declines.
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        mu = bond_mu + (mu - bond_mu) * glide_scale

    # Probability-weighted mean of the default return-regime offsets:
    # 2.5% crisis @ -24%, 9.0% recession @ -10%, 8.5% stagflation @ -4.5%,
    # 80.0% normal @ 0%.  Adding the inverse keeps E[draw] ~= configured mu.
    recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0

    u = rng.random()
    if u < 0.025:      # crisis / fat-tail shock
        return rng.gauss(mu + recenter - 0.24, sig * 1.8)
    if u < 0.115:      # recession
        return rng.gauss(mu + recenter - 0.10, sig * 1.25)
    if u < 0.20:       # high-inflation/stagflation
        return rng.gauss(mu + recenter - 0.045, sig * 1.15)
    return rng.gauss(mu + recenter, sig)


def _liquid_value(row: dict) -> float:
    """Spendable retirement asset value used for MC funding success."""
    return float(row.get('pretax_nw', 0) or 0) + float(row.get('roth_nw', 0) or 0) + \
           float(row.get('trust_nw', 0) or 0) + float(row.get('hsa_nw', 0) or 0)


def _funding_success(rows, threshold: float = 0.0) -> bool:
    """True if the path never runs out of modeled spendable funding.

    Criteria:
    1. No positive residual unfunded spending gap in any year.
    2. Liquid retirement assets remain above the configured threshold in every
       projected year and at terminal year.

    This intentionally excludes home equity and annuity PV from the success
    test. Those remain visible in total net-worth percentiles but no longer make
    a failed liquidity path look like a successful retirement funding path.
    """
    if not rows:
        return False
    max_unfunded = max(float(r.get('unfunded_gap', 0) or 0) for r in rows)
    min_liquid = min(_liquid_value(r) for r in rows)
    final_liquid = _liquid_value(rows[-1])
    return max_unfunded <= 1.0 and min_liquid > threshold and final_liquid > threshold


def _funding_success_with_home_equity(rows, threshold: float = 0.0, home_equity_reserve: float = 0.0,
                                       access_lag_years: int = 1) -> bool:
    """Like _funding_success but counts home equity as a last-resort reserve.

    If liquid assets are below threshold, the home_equity_reserve value (already
    haircut-adjusted) is added as a one-time draw available after access_lag_years
    from the first failure year. This computes a more optimistic 'contingency'
    success rate shown alongside the primary rate.
    """
    if not rows:
        return False
    if home_equity_reserve <= 0:
        return _funding_success(rows, threshold)
    # Primary check first — if already succeeds without contingency, return True
    if _funding_success(rows, threshold):
        return True
    # Find first year where liquid falls below threshold
    remaining_equity = home_equity_reserve
    first_shortfall_year = None
    for r in rows:
        if _liquid_value(r) <= threshold or float(r.get('unfunded_gap', 0) or 0) > 1.0:
            first_shortfall_year = r.get('year')
            break
    if first_shortfall_year is None:
        return True
    # Simulate applying equity as a lump-sum reserve after lag
    # If the equity can cover the gap we treat the path as contingency-success
    # by measuring whether adding the reserve to liquid at that point and forward
    # would have kept the plan funded. We approximate this by checking if the
    # shortfall exceeds the reserve value.
    total_unfunded = sum(float(r.get('unfunded_gap', 0) or 0) for r in rows)
    total_liquid_shortfall = sum(
        max(0.0, threshold - _liquid_value(r))
        for r in rows
        if (r.get('year') or 0) >= (first_shortfall_year + access_lag_years)
    )
    return total_unfunded <= 1.0 and total_liquid_shortfall <= remaining_equity


def _first_failure_year(rows, threshold: float = 0.0):
    for r in rows:
        if float(r.get('unfunded_gap', 0) or 0) > 1.0 or _liquid_value(r) <= threshold:
            return r.get('year')
    return None


def _percentiles(vals, success_threshold: float = 0.0):
    vals = sorted(vals)
    n = len(vals)
    if n == 0:
        return {p: 0 for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]} | {'mean': 0, 'success': 0}

    def pick(p):
        # Linear interpolation between order statistics, equivalent to NumPy's
        # default method for percentile estimates.
        if n == 1:
            return vals[0]
        rank = (p / 100.0) * (n - 1)
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))
        if lo == hi:
            return vals[lo]
        frac = rank - lo
        return vals[lo] * (1.0 - frac) + vals[hi] * frac

    return {
        1: pick(1), 5: pick(5), 10: pick(10), 25: pick(25), 50: pick(50),
        75: pick(75), 90: pick(90), 95: pick(95), 99: pick(99),
        'mean': sum(vals) / n,
        'success': sum(1 for v in vals if v > success_threshold) / n,
    }


def _success_rate_ci(successes: int, n: int, z: float = 1.96):
    """Wilson score interval for a binomial success rate."""
    n = max(1, int(n))
    p_hat = max(0.0, min(1.0, successes / n))
    denom = 1.0 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z * z / (4 * n * n)))
    return max(0.0, centre - half), min(1.0, centre + half)


def _clone_for_mc(c: dict) -> dict:
    """Copy only mutable projection state needed by each MC path.

    Full deepcopy of the whole config was the dominant fixed overhead.  This
    preserves path safety for balances, account metadata, annuity streams, lot
    engines, schedules, and sampled paths without recursively copying immutable
    scalar settings on every simulation.
    """
    c2 = dict(c)
    deep_keys = {
        'balances', 'ann_db', 'wife_pension', 'wife_single', 'wife_joint',
        'h_single', 'h_joint', 'mort_schedule', 'lump', 'note_interest',
        'account_registry', 'account_meta', 'balance_sheet', 'asset_class_overrides',
        'asset_class_enabled', 'asset_class_selection_action',
        'asset_class_alternate_first', 'allocation_target_pct',
        'asset_correlation_overrides', 'recurring_extras', 'taxable_ids',
        'pre_tax_ids', 'roth_ids', 'hsa_ids', 'invest_ids', 'all_acct_ids',
        'lot_engine', 'return_by_year', 'inflation_index_by_year',
        'ss_cola_index_by_year', 'bracket_index_by_year',
        'medical_index_by_year', 'wellness_shock_by_year',
    }
    for k in deep_keys:
        if k in c:
            c2[k] = copy.deepcopy(c[k])
    return c2


def _portfolio_asset_class_inputs(c: dict):
    try:
        from . import optimization as _opt
    except ImportError:
        import src.optimization as _opt  # type: ignore
    _opt.apply_capital_market_config(c)
    targets = c.get('allocation_target_pct') or {}
    enabled = c.get('asset_class_enabled') or {}
    pairs = []
    for cls, pct in targets.items():
        cls_name = str(cls)
        if cls_name not in _opt.ASSET_CLASSES:
            continue
        if enabled and not bool(enabled.get(cls_name, True)):
            continue
        try:
            weight = max(0.0, float(pct or 0.0))
        except Exception:
            weight = 0.0
        if weight > 0:
            pairs.append((cls_name, weight))
    if not pairs:
        # Conservative fallback when no detailed target rows are present.
        approx = {
            'US Large Cap': float(c.get('alloc_equity', 0.60) or 0.60),
            'Commodities': float(c.get('alloc_commodity', 0.0) or 0.0),
            'Cash': float(c.get('alloc_cash', 0.05) or 0.05),
        }
        bond_w = max(0.0, 1.0 - sum(approx.values()))
        approx['Bonds'] = bond_w
        pairs = [(cls, w) for cls, w in approx.items() if cls in _opt.ASSET_CLASSES and w > 0]
    total = sum(w for _cls, w in pairs) or 1.0
    classes = [cls for cls, _w in pairs]
    weights = [w / total for _cls, w in pairs]
    from .vectorized_fast_core import portfolio_moments
    moments = portfolio_moments(classes, weights, _opt.ASSET_CLASSES, _opt._CORR)
    means = [_opt.ASSET_CLASSES[cls]['ret'] for cls in classes]
    cov = moments['covariance']
    mu = float(moments['expected_return'])
    sig = float(moments['volatility'] or c.get('mc_sigma', 0.12) or 0.12)
    return classes, weights, means, cov, mu, sig


def _regime_overlay(rng: random.Random, base_return: float, sig: float, c: dict) -> float:
    recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
    u = rng.random()
    if u < 0.025:
        return base_return + recenter - 0.24 + rng.gauss(0.0, sig * 0.80)
    if u < 0.115:
        return base_return + recenter - 0.10 + rng.gauss(0.0, sig * 0.35)
    if u < 0.20:
        return base_return + recenter - 0.045 + rng.gauss(0.0, sig * 0.20)
    return base_return + recenter


def _generate_return_path(c: dict, rng: random.Random, mu: float, sig: float, years: list[int], use_asset_classes: bool = True):
    diagnostics = {'return_model': 'single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    draws = []
    if use_asset_classes and bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            classes, weights, means, cov, port_mu, port_sig = _portfolio_asset_class_inputs(c)
            np_rng = _np.random.default_rng(rng.randrange(1, 2**32 - 1))
            raw = np_rng.multivariate_normal(_np.array(means, dtype=float), cov, size=len(years), check_valid='warn')
            wv = _np.array(weights, dtype=float)
            draws = [float(x) for x in raw.dot(wv)]
            mu = float(port_mu)
            sig = float(max(1e-6, port_sig))
            diagnostics.update({
                'return_model': 'asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': classes,
                'asset_weights': {cls: weights[i] for i, cls in enumerate(classes)},
            })
        except Exception as exc:
            diagnostics.update({'return_model_warning': str(exc)})
    if not draws:
        draws = [_sample_return(rng, mu, sig, i, c) for i, _yr in enumerate(years)]
    else:
        draws = [_regime_overlay(rng, r, sig, c) for r in draws]

    # De-risking glide path for asset-class draws: shrink the realized return
    # toward the configured bond return over time, mirroring _sample_return.
    if str(c.get('glide_path', 'target_date')).lower() != 'static' and diagnostics.get('return_model') == 'asset_class_covariance':
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        adjusted = []
        for i, r in enumerate(draws):
            glide_scale = max(0.65, 1.0 - 0.01 * i)
            adjusted.append(bond_mu + (r - bond_mu) * glide_scale)
        draws = adjusted

    phi = max(-0.75, min(0.75, float(c.get('mc_serial_correlation', 0.0) or 0.0)))
    if abs(phi) > 1e-9 and len(draws) > 1:
        adjusted = [draws[0]]
        damp = math.sqrt(max(0.0, 1.0 - phi * phi))
        for r in draws[1:]:
            adjusted.append(mu + phi * (adjusted[-1] - mu) + damp * (r - mu))
        draws = adjusted
        diagnostics['serial_correlation'] = phi
    return {yr: draws[i] for i, yr in enumerate(years)}, diagnostics


def _sample_inflation_and_health_paths(c: dict, rng: random.Random, years: list[int], returns: dict[int, float], mu: float, sig: float):
    start = int(c['plan_start'])
    inf_mu = float(c.get('inf', 0.025) or 0.025)
    inf_sig = max(0.0, float(c.get('mc_inflation_sigma', 0.015) or 0.015))
    corr = max(-0.95, min(0.95, float(c.get('mc_return_inflation_corr', -0.25) or 0.0)))
    stochastic = bool(c.get('mc_inflation_stochastic', True))
    sqrt_term = math.sqrt(max(0.0, 1.0 - corr * corr))
    inflation_rates = {}
    inflation_index = {}
    ss_index = {}
    bracket_index = {}
    medical_index = {}
    wellness_shocks = {}
    inf_factor = ss_factor = brk_factor = med_factor = 1.0
    for yr in years:
        if yr == start:
            inflation_rates[yr] = inf_mu
            inflation_index[yr] = ss_index[yr] = bracket_index[yr] = medical_index[yr] = 1.0
        else:
            ret_z = 0.0 if sig <= 1e-9 else (float(returns.get(yr, mu)) - mu) / sig
            surprise = 0.0
            if stochastic:
                surprise = inf_sig * (corr * ret_z + sqrt_term * rng.gauss(0.0, 1.0))
            annual_inf = max(-0.02, min(0.12, inf_mu + surprise))
            inflation_rates[yr] = annual_inf
            inf_factor *= (1.0 + annual_inf)
            ss_rate = max(0.0, min(0.10, float(c.get('ss_cola', 0.02) or 0.02) + 0.70 * (annual_inf - inf_mu)))
            brk_rate = max(0.0, min(0.08, float(c.get('brk_inf', 0.02) or 0.02) + (0.65 if c.get('mc_bracket_stochastic', True) else 0.0) * (annual_inf - inf_mu)))
            med_rate = max(0.0, min(0.14, float(c.get('med_inf', 0.055) or 0.055) + 0.85 * (annual_inf - inf_mu)))
            ss_factor *= (1.0 + ss_rate)
            brk_factor *= (1.0 + brk_rate)
            med_factor *= (1.0 + med_rate)
            inflation_index[yr] = inf_factor
            ss_index[yr] = ss_factor
            bracket_index[yr] = brk_factor
            medical_index[yr] = med_factor
        if bool(c.get('mc_wellness_shocks', True)):
            prob = max(0.0, min(1.0, float(c.get('mc_wellness_prob', 0.03) or 0.0)))
            mean_cost = max(0.0, float(c.get('mc_wellness_mean', 150000.0) or 0.0))
            if mean_cost > 0 and rng.random() < prob:
                # Exponential severity creates infrequent large events while the
                # cap prevents a single draw from dominating small-sample tests.
                wellness_shocks[yr] = min(mean_cost * 4.0, rng.expovariate(1.0 / mean_cost))
    def _geom_rate(index):
        if len(years) <= 1:
            return inf_mu
        end_factor = max(1e-12, float(index.get(years[-1], 1.0) or 1.0))
        return end_factor ** (1.0 / max(1, len(years) - 1)) - 1.0
    return {
        'inflation_by_year': inflation_rates,
        'inflation_index_by_year': inflation_index,
        'ss_cola_index_by_year': ss_index,
        'bracket_index_by_year': bracket_index,
        'medical_index_by_year': medical_index,
        'wellness_shock_by_year': wellness_shocks,
        'sampled_inflation_geometric': _geom_rate(inflation_index),
        'sampled_bracket_inflation_geometric': _geom_rate(bracket_index),
    }


def _adjust_annuity_pmt_for_mc(stream: dict, returns: dict, inflation_paths: dict, years: list, mu: float) -> dict:
    """Adjust init_pmt for variable and COLA annuities based on sampled paths.

    Variable: scale init_pmt by (cumulative_sampled_return / cumulative_expected_return)
    COLA: scale init_pmt by cumulative sampled inflation (relative to expected inflation).
    Fixed: no adjustment.

    Returns a modified copy of the stream dict.
    """
    payout_type = stream.get('payout_type', 'fixed')
    if payout_type == 'fixed' or not years or float(stream.get('init_pmt', 0) or 0) <= 0:
        return stream
    stream = dict(stream)
    first_yr = int(stream.get('first_yr', years[0]) or years[0])
    # Use only years up to and including the annuity start year for the scaling horizon
    horizon = [y for y in years if y <= first_yr]
    if not horizon:
        return stream
    if payout_type == 'variable':
        # Scale by cumulative return ratio: sampled vs expected
        cum_sampled = 1.0
        cum_expected = 1.0
        for y in horizon:
            cum_sampled *= (1.0 + float(returns.get(y, mu) or mu))
            cum_expected *= (1.0 + mu)
        if cum_expected > 0:
            scale = max(0.5, min(2.0, cum_sampled / cum_expected))  # cap at ±2x
            stream['init_pmt'] = float(stream['init_pmt']) * scale
    elif payout_type == 'cola':
        # Scale by cumulative inflation ratio: sampled vs expected plan inflation
        expected_inf = float(stream.get('ann_inf', 0.025) or 0.025)
        infl_by_year = inflation_paths.get('inflation_by_year', {})
        cum_sampled_inf = 1.0
        cum_expected_inf = 1.0
        for y in horizon:
            cum_sampled_inf *= (1.0 + float(infl_by_year.get(y, expected_inf) or expected_inf))
            cum_expected_inf *= (1.0 + expected_inf)
        if cum_expected_inf > 0:
            scale = max(0.7, min(1.5, cum_sampled_inf / cum_expected_inf))
            stream['init_pmt'] = float(stream['init_pmt']) * scale
    return stream


def _mc_scalar_tier_bucket_reconstruction(c: dict, rows: list[dict]):
    """Scalar-engine analogue of the vectorized engine's genuine per-tier
    withdrawal redirection (optimization-refactor "Not done" item, Option B
    -- documentation/archive/superpowers/plans/2026-08-27-mc-tier-priority-
    withdrawal-redirection-spec.md).

    ``monte_carlo_exact_scalar`` has no independent withdrawal mechanism to
    redirect: each path is a full rerun of ``project()`` (the deterministic
    engine), which just replays whatever bucket split the deterministic
    cascade already decided -- unlike the vectorized engine's own
    ``balances`` dict, there is nothing here to intercept mid-cascade. This
    function builds a PARALLEL per-path bucket-balance tracker instead,
    without touching deterministic_engine.py: it starts from the same
    account balances the deterministic engine used, and for each year
    re-derives a genuinely tier-restricted withdrawal (SPENDING_TIER_BUCKET_
    POLICY, MC_TIER_FUNDING_ORDER, income_funding-first -- exactly mirroring
    ``_mc_vectorized_projection``'s mechanism) against ITS OWN reconstructed
    balances, rather than reusing the real ``_account_withdrawals`` split.

    Each bucket's growth for the year is inferred from this path's own REAL
    trajectory (``growth_factor = real_ending_nw / (real_starting_balance -
    real_withdrawal + deposits - conversions_out + conversions_in)``, falling
    back to 1.0 when the denominator is negligible) and applied to the
    RECONSTRUCTED balance -- so this reuses the real, path-specific account
    returns rather than re-sampling or approximating a portfolio-wide rate,
    the same fidelity principle ``_mc_vectorized_projection`` follows by
    reusing each path's own sampled returns.

    Returns ``{year: {'unfunded': float, 'tier_shortfall': {tier: float},
    'tier_actual_spend': {tier: float}}}``, or ``None`` if no row in this
    path carried ``spend_by_tier`` (Phase 0 unavailable for this plan) --
    callers must fall back to the pre-existing ``unfunded_gap``/
    ``SPENDING_TIER_CUT_ORDER`` reconstruction in that case, preserving
    behavior for any plan predating Phase 0.
    """
    if not any(r.get('spend_by_tier') for r in rows):
        return None
    from .spending_budget_resolver import (
        SPENDING_TIER_BUCKET_POLICY, MC_TIER_FUNDING_ORDER, SPENDING_TIER_ESSENTIAL,
    )
    registry = {a.get('id'): str(a.get('tax') or '').lower() for a in c.get('account_registry') or []}
    buckets = ('pretax', 'roth', 'taxable', 'hsa', 'cash')
    nw_field = {'pretax': 'pretax_nw', 'roth': 'roth_nw', 'taxable': 'trust_nw', 'hsa': 'hsa_nw', 'cash': 'cash_nw'}
    other_bucket_order = SPENDING_TIER_BUCKET_POLICY[SPENDING_TIER_ESSENTIAL]

    def _bucket_for(aid: str) -> str:
        tax = registry.get(aid, '')
        if tax == 'pre_tax':
            return 'pretax'
        if tax == 'roth':
            return 'roth'
        if tax == 'hsa':
            return 'hsa'
        if tax == 'cash':
            return 'cash'
        return 'taxable'

    def _account_totals(row: dict, key: str) -> dict:
        totals = {b: 0.0 for b in buckets}
        for aid, amount in (row.get(key) or {}).items():
            totals[_bucket_for(str(aid))] += max(0.0, float(amount or 0.0))
        return totals

    starts = _mc_bucket_starting_balances(c)
    my_balance = dict(starts)
    real_balance = dict(starts)
    results: dict = {}

    for row in rows:
        withdrawals = _account_totals(row, '_account_withdrawals')
        deposits = _account_totals(row, '_account_deposits')
        conv_out = _account_totals(row, '_account_conversions_out')
        conv_in = _account_totals(row, '_account_conversions_in')

        tiers = row.get('spend_by_tier') or {}
        total_tier_need = sum(float(v or 0.0) for v in tiers.values())
        other_nominal = max(0.0, sum(withdrawals.values()) - total_tier_need)
        income = float(row.get('income_funding', 0.0) or 0.0)

        need_by_label = {'other': other_nominal}
        for tier, amount in tiers.items():
            need_by_label[tier] = float(amount or 0.0)
        gross_need_by_label = dict(need_by_label)

        extra_tiers = tuple(t for t in tiers if t not in SPENDING_TIER_BUCKET_POLICY)
        funding_order = (MC_TIER_FUNDING_ORDER[0],) + extra_tiers + MC_TIER_FUNDING_ORDER[1:]

        income_avail = income
        for label in funding_order:
            if label == 'other' or label not in need_by_label:
                continue
            covered = min(income_avail, need_by_label[label])
            need_by_label[label] -= covered
            income_avail -= covered

        tier_shortfall: dict = {}
        tier_actual_spend: dict = {}
        unfunded = 0.0
        for label in funding_order:
            if label not in need_by_label:
                continue
            bucket_order = SPENDING_TIER_BUCKET_POLICY.get(label, other_bucket_order)
            remaining = max(0.0, need_by_label[label])
            for bucket in bucket_order:
                take = min(my_balance[bucket], remaining)
                my_balance[bucket] -= take
                remaining -= take
                if remaining <= 1e-9:
                    break
            shortfall = max(0.0, remaining)
            if label != 'other':
                tier_shortfall[label] = shortfall
                tier_actual_spend[label] = gross_need_by_label[label] - shortfall
            unfunded += shortfall

        for bucket in buckets:
            my_balance[bucket] += deposits[bucket]
        pretax_conv = min(my_balance['pretax'], conv_out.get('pretax', 0.0))
        my_balance['pretax'] -= pretax_conv
        my_balance['roth'] += pretax_conv

        for bucket in buckets:
            real_end = float(row.get(nw_field[bucket], 0.0) or 0.0)
            real_denom = (real_balance[bucket] - withdrawals[bucket] + deposits[bucket]
                          - conv_out[bucket] + conv_in[bucket])
            growth_factor = real_end / real_denom if abs(real_denom) > 1e-6 else 1.0
            my_balance[bucket] = my_balance[bucket] * growth_factor
            real_balance[bucket] = real_end

        results[int(row['year'])] = {
            'unfunded': unfunded,
            'tier_shortfall': tier_shortfall,
            'tier_actual_spend': tier_actual_spend,
        }
    return results


def _mc_scalar_guyton_klinger_shadow(c: dict, rows: list[dict], returns: dict, inflation_by_year: dict):
    """Scalar-engine analogue of the vectorized engine's Guyton-Klinger
    guardrail SHADOW simulation (optimization-refactor Phase 5, see
    documentation/archive/superpowers/plans/2026-08-27-phase5-adaptive-guardrails-spec.md
    and the matching, more fully-commented block in
    ``_mc_vectorized_projection`` for the full rule description and
    rationale -- this function implements the identical algorithm, not a
    reduced one).

    Tracks ONE aggregate liquid-portfolio value (not per-tax-bucket) for
    this path, seeded from the same starting balances the deterministic
    engine used and this path's own year-1 actual portfolio draw (net of
    income, matching the same income-netting fix the tier-priority-
    redirection increment required for its own cascade). Grows the shadow
    portfolio using ``returns[year]`` -- this path's own already-sampled
    total portfolio return for that year, the same figure
    ``monte_carlo_exact_scalar`` already uses for its own per-path
    trajectory -- rather than inferring an implied rate from balance
    deltas (unlike ``_mc_scalar_tier_bucket_reconstruction``'s per-bucket
    growth-factor inference, this shadow tracks one aggregate figure with
    no per-bucket split to reconcile against, so the real portfolio-level
    return is directly available and simpler to reuse as-is).

    Fixed default GK parameters (20% bands, 10% cut/raise, 15-year
    capital-preservation suspension window) -- identical constants to the
    vectorized engine's block, per the same user sign-off.

    Returns ``{year: {'spend_nominal': float, 'cut': bool, 'raise': bool}}``
    (this path's total consumption -- portfolio draw + that year's
    guaranteed income -- plus whether each guardrail rule fired that
    year), or ``None`` if ``rows`` is empty.
    """
    if not rows:
        return None
    starts = _mc_bucket_starting_balances(c)
    total_start_liquid = float(sum(starts.values()))
    plan_end = int(c.get('plan_end', int(rows[-1]['year'])))

    def _withdrawal_total(row: dict) -> float:
        return sum(max(0.0, float(amt or 0.0)) for amt in (row.get('_account_withdrawals') or {}).values())

    withdrawal = _withdrawal_total(rows[0])
    portfolio = total_start_liquid
    iwr = withdrawal / max(1e-9, portfolio)
    _gk_band, _gk_adjust, _gk_suspension_years = 0.20, 0.10, 15
    results: dict = {}
    prior_return = None
    for idx, row in enumerate(rows):
        yr = int(row['year'])
        if idx > 0:
            infl_rate = float(inflation_by_year.get(yr, c.get('inf', 0.025)) or 0.0)
            if prior_return is None or prior_return >= 0.0:
                withdrawal = withdrawal * (1.0 + infl_rate)
        years_remaining = plan_end - yr
        cwr = withdrawal / max(1e-9, portfolio)
        do_cut = years_remaining > _gk_suspension_years and cwr > iwr * (1.0 + _gk_band)
        do_raise = (not do_cut) and cwr < iwr * (1.0 - _gk_band)
        if do_cut:
            withdrawal *= (1.0 - _gk_adjust)
        elif do_raise:
            withdrawal *= (1.0 + _gk_adjust)
        income = float(row.get('income_funding', 0.0) or 0.0)
        results[yr] = {'spend_nominal': withdrawal + income, 'cut': do_cut, 'raise': do_raise}
        portfolio = max(0.0, portfolio - withdrawal)
        r = float(returns.get(yr, 0.0) or 0.0)
        portfolio = portfolio * (1.0 + r)
        prior_return = r
    return results


def _run_one_mc_path(c: dict, rng: random.Random, mu: float, sig: float, use_asset_classes: bool = True):
    c2 = _clone_for_mc(c)
    c2.update(sample_household_death_years(c2, rng))
    years = list(range(int(c2['plan_start']), int(c2['plan_end']) + 1))
    returns, return_diag = _generate_return_path(c2, rng, mu, sig, years, use_asset_classes=use_asset_classes)
    c2['return_by_year'] = returns
    # Compute per-account returns for asset-location-aware projections (Wave 3.5 completion, F1.1)
    c2['return_by_account_by_year'] = _apply_account_return_adjustments(c2, returns, years)
    inflation_paths = _sample_inflation_and_health_paths(
        c2, rng, years, returns,
        float(return_diag.get('portfolio_expected_return', mu) or mu),
        float(return_diag.get('portfolio_sigma', sig) or sig),
    )
    c2.update(inflation_paths)
    # Adjust variable/COLA annuity payments based on this path's sampled returns/inflation
    for ann_key in ['wife_pension', 'wife_single', 'wife_joint', 'h_single', 'h_joint']:
        if ann_key in c2 and isinstance(c2[ann_key], dict):
            c2[ann_key] = _adjust_annuity_pmt_for_mc(c2[ann_key], returns, inflation_paths, years, mu)
    # project() consumes the per-year bracket_index_by_year and (for IRMAA
    # thresholds, #334) inflation_index_by_year paths directly, so each scalar
    # MC path uses its own sampled tax thresholds
    # rather than a geometric-mean approximation.
    rows = project(c2)
    return rows, years, returns, return_diag, inflation_paths, c2


def _sensitivity_success_rate(c: dict, mu: float, sig: float, n_sims: int, seed: int, threshold: float) -> float:
    rng = random.Random(seed)
    successes = 0
    for _ in range(max(1, int(n_sims))):
        rows, _years, _returns, _diag, _infl, _c2 = _run_one_mc_path(c, rng, mu, sig, use_asset_classes=False)
        if _funding_success(rows, threshold):
            successes += 1
    return successes / max(1, int(n_sims))


def monte_carlo_exact_scalar(c, n_sims=1000, seed=42, base_rows=None):
    st = SimpleNamespace(base_rows=base_rows, c=c, n_sims=n_sims, seed=seed)
    _scalar_mc_setup(st)
    _scalar_mc_run_paths(st)

    _scalar_mc_summarize(st)

    return _scalar_mc_result(st)

# ===== END monte_carlo_engine.py =====

# ===== BEGIN v8.3_vectorized_monte_carlo_engine.py =====


def _mc_bucket_starting_balances(c: dict) -> dict:
    """Return beginning balances by projection bucket for vectorized MC.

    N1 Phase 1 (per-path per-owner RMD engine): 'pretax' is also split into
    'h_pretax'/'w_pretax' using each account's registry owner_idx (0 = h,
    1 = w) -- mirrors how core.py's rmd_ids_by_owner/ids_by_owner filter by
    owner_idx. 'pretax' itself is kept as h_pretax + w_pretax for any
    existing caller that still reads the combined figure.
    """
    balances = c.get('balances') or {}
    registry = c.get('account_registry') or []
    result = {'pretax': 0.0, 'roth': 0.0, 'taxable': 0.0, 'hsa': 0.0, 'cash': 0.0,
              'h_pretax': 0.0, 'w_pretax': 0.0}
    for acct in registry:
        aid = acct.get('id')
        tax = str(acct.get('tax') or '').lower()
        bal = float(balances.get(aid, acct.get('balance', 0.0)) or 0.0)
        if tax == 'pre_tax':
            result['pretax'] += bal
            owner_idx = int(acct.get('owner_idx', 0) or 0)
            if owner_idx == 1:
                result['w_pretax'] += bal
            else:
                result['h_pretax'] += bal
        elif tax == 'roth':
            result['roth'] += bal
        elif tax == 'hsa':
            result['hsa'] += bal
        elif tax == 'cash':
            result['cash'] += bal
        else:
            result['taxable'] += bal
    return result


def _mc_row_bucket_flows(c: dict, base_rows: list[dict]) -> dict:
    """Build deterministic per-year bucket flows used by vectorized MC.

    The scalar projection remains the source of truth for deterministic cash-flow
    timing, withdrawal ordering, deposits, and forced Roth conversions.  v8.3
    converts those row-level decisions into vectors and then evolves all Monte
    Carlo paths across simulations at once, rather than re-running the scalar
    projection for every path.
    """
    registry = {a.get('id'): (str(a.get('tax') or '').lower(), int(a.get('owner_idx', 0) or 0))
                for a in c.get('account_registry') or []}
    years = [int(r['year']) for r in base_rows]
    # N1 Phase 1: h_pretax/w_pretax carry the SAME dollars already counted in
    # 'pretax' (owner-split, not a separate pool) -- read together with
    # 'pretax' by _mc_vectorized_projection to track per-owner RMD-relevant
    # balances while every existing reader of the combined 'pretax' arrays
    # is untouched.
    buckets = ('pretax', 'roth', 'taxable', 'hsa', 'cash', 'h_pretax', 'w_pretax')
    out = {name: {b: [] for b in buckets} for name in ('withdrawals', 'deposits', 'conversions_out', 'conversions_in')}
    total_spend = []
    total_tax = []
    gross_income = []
    deterministic_inflation_index = []
    inf = float(c.get('inf', 0.025) or 0.025)
    start = int(c.get('plan_start', years[0] if years else 0))
    # Phase 1 items 2-3: gross external cash flow (tax NPV / ELTR) and the
    # three REALIZED cash/asset-transfer fields for lifetime gift/charity PV.
    # daf_grant_yr/*_deduction_yr are deliberately excluded -- see
    # monte_carlo_exact_scalar's _GIFT_CHARITY_FIELDS comment.
    # 'income_funding' (optimization-refactor Option B): the deterministic
    # engine's income_from_streams (SS + pension + annuities + wages, see
    # deterministic_engine.py:2001-2006) -- the cash that funds spending
    # WITHOUT any account withdrawal at all. Needed so the genuine per-tier
    # cascade below doesn't try to draw a tier's FULL gross spend_by_tier
    # demand from investment buckets when most of it was already covered by
    # income the deterministic engine's own gap = total_cash_need -
    # income_from_streams already nets out.
    # 'rmd_h'/'rmd_w' (N1 Phase 1): the deterministic baseline's OWN per-owner
    # RMD for that year -- already fully embedded in this row's pretax
    # withdrawal (an RMD is just a pretax-account withdrawal, indistinguishable
    # at the account level from an elective one). Exposed so
    # _mc_vectorized_projection can force only the EXTRA RMD a path's own
    # diverged balance requires beyond what this baseline figure already
    # accounts for, instead of double-forcing the whole RMD on top of a
    # cascade that already replays it.
    # 'h_ira_elective'/'w_ira_elective' (N1 Phase 1): the baseline's own
    # ELECTIVE-only (non-RMD) per-owner pretax withdrawal shape, used to
    # split the vectorized cascade's own elective pretax draw back onto
    # h_pretax/w_pretax more accurately than the blended (RMD+elective)
    # h_pretax/w_pretax withdrawal totals would (those totals are skewed
    # toward whichever spouse's RMD happens to be larger that baseline
    # year, which is not representative of the elective-only split once a
    # path's own RMD is computed and forced out separately).
    _EXTRA_SCALAR_FIELDS = ('gross_cash_flow_yr', 'daf_contrib_yr', 'qcd_total_yr', 'gift_total_yr',
                             'income_funding', 'rmd_h', 'rmd_w', 'h_ira_elective', 'w_ira_elective')
    extra_scalar: dict[str, list] = {f: [] for f in _EXTRA_SCALAR_FIELDS}
    # Phase 1 (optimization refactor): the deterministic tier composition of
    # total_spend, per year, keyed by whatever SPENDING_TIERS keys the rows
    # actually carry (Phase 0's deterministic_engine.py row['spend_by_tier']).
    tier_keys: list[str] = []
    for _row in base_rows:
        for _t in (_row.get('spend_by_tier') or {}):
            if _t not in tier_keys:
                tier_keys.append(_t)
    spend_by_tier: dict[str, list] = {t: [] for t in tier_keys}

    def _bucket_for_account(aid: str) -> str:
        tax, _owner_idx = registry.get(aid, ('', 0))
        if tax == 'pre_tax':
            return 'pretax'
        if tax == 'roth':
            return 'roth'
        if tax == 'hsa':
            return 'hsa'
        if tax == 'cash':
            return 'cash'
        return 'taxable'

    for row in base_rows:
        for name, key in (('withdrawals', '_account_withdrawals'), ('deposits', '_account_deposits'),
                          ('conversions_out', '_account_conversions_out'), ('conversions_in', '_account_conversions_in')):
            vals = {b: 0.0 for b in buckets}
            for aid, amount in (row.get(key) or {}).items():
                aid_s = str(aid)
                b = _bucket_for_account(aid_s)
                amt = max(0.0, float(amount or 0.0))
                vals[b] += amt
                if b == 'pretax':
                    _tax, owner_idx = registry.get(aid_s, ('', 0))
                    vals['w_pretax' if owner_idx == 1 else 'h_pretax'] += amt
            for b in buckets:
                out[name][b].append(vals[b])
        total_spend.append(float(row.get('total_spend', 0.0) or 0.0))
        total_tax.append(float(row.get('total_tax', 0.0) or 0.0))
        gross_income.append(float(row.get('gross_income', 0.0) or 0.0))
        deterministic_inflation_index.append((1.0 + inf) ** max(0, int(row['year']) - start))
        _row_tiers = row.get('spend_by_tier') or {}
        for t in tier_keys:
            spend_by_tier[t].append(float(_row_tiers.get(t, 0.0) or 0.0))
        for f in _EXTRA_SCALAR_FIELDS:
            extra_scalar[f].append(float(row.get(f, 0.0) or 0.0))

    try:
        for name in out:
            for b in buckets:
                out[name][b] = _np.array(out[name][b], dtype=float)
        out['total_spend'] = _np.array(total_spend, dtype=float)
        out['total_tax'] = _np.array(total_tax, dtype=float)
        out['gross_income'] = _np.array(gross_income, dtype=float)
        out['deterministic_inflation_index'] = _np.array(deterministic_inflation_index, dtype=float)
        out['spend_by_tier'] = {t: _np.array(v, dtype=float) for t, v in spend_by_tier.items()}
        for f in _EXTRA_SCALAR_FIELDS:
            out[f] = _np.array(extra_scalar[f], dtype=float)
    except (TypeError, ValueError, KeyError) as _exc:
        _log_fallback("monte_carlo.array_conversion", _exc)
    out['years'] = years
    return out


def _survivor_bucket_cache_key(c: dict, base_rows: list[dict]) -> str:
    """Fingerprint everything the survivor-bucket build actually depends on.

    The buckets are produced by 70 full run_scenario() projections off ``c``,
    so ANY config value the projection reads changes them -- not just the
    death years. This hashes the whole config with unhashable/derived entries
    dropped, deliberately erring toward MORE invalidation: a missed key would
    serve a different household's survivor trajectories, which is a silently
    wrong workbook, while an extra miss only costs ~1.5s.
    """
    import hashlib as _hashlib
    import json as _json

    # Derived outputs and memos -- never inputs to the bucket build. Including
    # them would make every key unique and defeat the memo entirely.
    skip = {
        '_survivor_bucket_memo', '_ann_pmt_memo', 'plan_result',
        'report_spec', 'roth_strategy_result', 'advisor_readiness',
    }
    def _json_safe(obj):
        # Config values can carry dict keys or container types (tuples, sets,
        # objects) json.dumps can't handle even with default=repr, since
        # default only rescues values, not keys. Recursively coerce
        # everything into a shape json.dumps can serialize, falling back to
        # repr() for anything still unrecognized -- any two distinct configs
        # then hash differently, which is the direction we want to err in.
        if isinstance(obj, dict):
            return {
                str(k): _json_safe(v)
                for k, v in obj.items()
            }
        if isinstance(obj, (list, tuple)):
            return [_json_safe(v) for v in obj]
        if isinstance(obj, (set, frozenset)):
            return sorted(repr(v) for v in obj)
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return repr(obj)

    payload = {k: v for k, v in c.items() if k not in skip}
    h = _hashlib.sha256(_json.dumps(_json_safe(payload), sort_keys=True).encode('utf-8'))
    h.update(b'\0')
    h.update(_json.dumps([int(r['year']) for r in base_rows]).encode('utf-8'))
    return h.hexdigest()


def _mc_survivor_bucket_flows(c: dict, base_rows: list[dict]):
    """Optimization-refactor Phase 1 items 4-6: precomputed survivor-period
    deterministic trajectories for the vectorized MC engine.

    The vectorized engine normally scales ONE joint-economics trajectory
    (base_rows) identically for every path, which is only correct until
    either spouse dies -- deterministic_engine.py's survivor spending factor,
    Social Security survivor-benefit switch, pension/annuity js_pct haircut,
    and filing-status switch (MFJ -> optional QSS window -> survivor_filing)
    are all real and already correct in that engine, but the vectorized
    engine never applies them per path. (The scalar engine,
    monte_carlo_exact_scalar, already gets this correctly "for free" because
    it reruns project() per path with that path's own sampled death years --
    this function gives the vectorized engine equivalent fidelity cheaply:
    rerun project() once per plausible (which-spouse-died-first,
    first-death-year) combination, not once per MC path, then
    _mc_vectorized_projection blends each path into the bucket matching its
    own sampled first-death year.)

    Returns None for a single-person household (_mc_vectorized_death_years
    already sets w = h.copy() in that case -- there is no first-death event
    to model) or empty base_rows.

    Pure function of (c, base_rows): must be computed ONCE per monte_carlo()
    invocation and threaded explicitly through every downstream vectorized MC
    call (_mc_vectorized_batch, the sensitivity grid, the required-cut and
    sustainable-spending bisections) -- rebuilding it per call would multiply
    its cost (2 * n_years project() calls) by the ~26-90 vectorized-engine
    invocations a single monte_carlo() call can make.
    """
    _key = _survivor_bucket_cache_key(c, base_rows)
    _memo = c.get('_survivor_bucket_memo')
    if _memo is None:
        _memo = c['_survivor_bucket_memo'] = {}
    if _key in _memo:
        return _memo[_key]

    members = c.get('members') or []
    years = [int(r['year']) for r in base_rows]
    n_years = len(years)
    if len(members) < 2 or n_years == 0:
        return None
    plan_start = int(c.get('plan_start', years[0]))
    plan_end = int(c.get('plan_end', years[-1]))
    # Guarantees the survivor's OWN death never fires inside this bucket's
    # project() run. The caller's active = years <= max_death_years mask
    # (built from each path's REAL sampled second-death year) is what
    # truncates spending at the correct point, not this bucket -- so this
    # placeholder doesn't need to match any real second-death year.
    far_future = plan_end + 200
    withdrawal_names = ('withdrawals', 'deposits', 'conversions_out', 'conversions_in')
    # N1 Phase 1: h_pretax/w_pretax propagate through the same
    # per-scenario project() reruns as every other bucket, so a path
    # blended into a survivor-death bucket after its own first death still
    # carries a correctly owner-split pretax trajectory.
    withdrawal_buckets = ('pretax', 'roth', 'taxable', 'hsa', 'cash', 'h_pretax', 'w_pretax')
    scalar_fields = ('total_tax', 'gross_income', 'gross_cash_flow_yr',
                      'daf_contrib_yr', 'qcd_total_yr', 'gift_total_yr', 'income_funding',
                      'rmd_h', 'rmd_w', 'h_ira_elective', 'w_ira_elective')
    n_buckets = 2 * n_years
    arrays: dict = {
        f'{name}.{b}': _np.zeros((n_buckets, n_years), dtype=float)
        for name in withdrawal_names for b in withdrawal_buckets
    }
    for f in scalar_fields:
        arrays[f] = _np.zeros((n_buckets, n_years), dtype=float)
    tier_arrays: dict = {}
    cst_at_death = _np.zeros(n_buckets, dtype=float)

    for spouse_first in (0, 1):  # 0 = H dies first, 1 = W dies first
        for year_idx, fd_year in enumerate(years):
            overrides = {'first_death_yr': fd_year}
            if spouse_first == 0:
                overrides['h_death_yr'] = fd_year
                overrides['w_death_yr'] = far_future
            else:
                overrides['w_death_yr'] = fd_year
                overrides['h_death_yr'] = far_future
            _c2, rows2 = run_scenario(c, overrides=overrides)
            flows2 = _mc_row_bucket_flows(_c2, rows2)
            bucket_id = spouse_first * n_years + year_idx
            cst_at_death[bucket_id] = float(rows2[year_idx].get('cst_funded_yr', 0.0) or 0.0)
            for name in withdrawal_names:
                for b in withdrawal_buckets:
                    arrays[f'{name}.{b}'][bucket_id] = flows2[name][b]
            for f in scalar_fields:
                arrays[f][bucket_id] = flows2.get(f, _np.zeros(n_years))
            for tier, arr in (flows2.get('spend_by_tier') or {}).items():
                if tier not in tier_arrays:
                    tier_arrays[tier] = _np.zeros((n_buckets, n_years), dtype=float)
                tier_arrays[tier][bucket_id] = arr

    _result = {
        'years': years,
        'n_years': n_years,
        'n_buckets': n_buckets,
        'plan_start': plan_start,
        'arrays': arrays,
        'spend_by_tier': tier_arrays,
        'cst_funded_at_death': cst_at_death,
    }
    _memo[_key] = _result
    return _result


def _mc_effective_row_flows(flows: dict, survivor_buckets, bucket_id, use_bucket_mask, n_sims: int, n_years: int) -> dict:
    """Blend the single deterministic trajectory (``flows``) with each path's
    survivor-bucket trajectory (``survivor_buckets``) for years after that
    path's own first death (``use_bucket_mask``).

    When ``survivor_buckets`` is None (a single-person household, or the
    ``mc_vectorized_survivor_economics`` flag is off), every field reduces to
    ``np.broadcast_to(flows[...], (n_sims, n_years))`` -- bit-identical to the
    pre-Phase-1-items-4-6 behavior by construction.
    """
    withdrawal_buckets = ('pretax', 'roth', 'taxable', 'hsa', 'cash', 'h_pretax', 'w_pretax')
    out: dict = {}
    for name in ('withdrawals', 'deposits', 'conversions_out', 'conversions_in'):
        out[name] = {}
        for b in withdrawal_buckets:
            det_row = flows[name][b].reshape(1, n_years)
            if survivor_buckets is None:
                out[name][b] = _np.broadcast_to(det_row, (n_sims, n_years))
            else:
                bucket_matrix = survivor_buckets['arrays'][f'{name}.{b}'][bucket_id, :]
                out[name][b] = _np.where(use_bucket_mask, bucket_matrix, det_row)
    for flow_field in ('total_tax', 'gross_income', 'gross_cash_flow_yr', 'daf_contrib_yr', 'qcd_total_yr', 'gift_total_yr', 'income_funding', 'rmd_h', 'rmd_w', 'h_ira_elective', 'w_ira_elective'):
        det_field = flows.get(flow_field)
        if det_field is None:
            continue
        det_row = det_field.reshape(1, n_years)
        if survivor_buckets is None or flow_field not in survivor_buckets.get('arrays', {}):
            out[flow_field] = _np.broadcast_to(det_row, (n_sims, n_years))
        else:
            out[flow_field] = _np.where(use_bucket_mask, survivor_buckets['arrays'][flow_field][bucket_id, :], det_row)
    out['spend_by_tier'] = {}
    for tier, det_arr in (flows.get('spend_by_tier') or {}).items():
        det_row = det_arr.reshape(1, n_years)
        if survivor_buckets is None or tier not in (survivor_buckets.get('spend_by_tier') or {}):
            out['spend_by_tier'][tier] = _np.broadcast_to(det_row, (n_sims, n_years))
        else:
            out['spend_by_tier'][tier] = _np.where(use_bucket_mask, survivor_buckets['spend_by_tier'][tier][bucket_id, :], det_row)
    return out


def _mc_vectorized_sample_death_ages(c: dict, np_rng, n_sims: int, m: Mapping, sex_idx: int, dob: int, plan_start: int):
    """Vectorized counterpart of sample_death_year: an age-by-age Bernoulli
    survival walk across all n_sims at once, using the same shifted SSA/SOA
    table sample_death_year uses (System review C4 -- this is the SECOND,
    independently-drawing sampler the original panel review missed; a fix
    applied only to sample_death_year would leave every number the vectorized
    MC path actually produces unchanged. See §2.5's re-assessment)."""
    shift = _age_shift_for_member(m, sex_idx)
    current_age = max(18, int(plan_start) - int(dob))
    death_age = _np.full(n_sims, 119, dtype=int)
    alive = _np.ones(n_sims, dtype=bool)
    for age in range(current_age, 119):
        if not alive.any():
            break
        qx = _mortality_qx(age - shift, sex_idx)
        draws = np_rng.random(n_sims)
        died_this_year = alive & (draws < qx)
        death_age[died_this_year] = age
        alive &= ~died_this_year
    return death_age


def _mc_vectorized_death_years(c: dict, np_rng, n_sims: int):
    members = c.get('members') or []
    plan_start = int(c.get('plan_start', 0) or 0)
    if members:
        h_dob = int(members[0].get('dob_yr', c.get('h_dob_yr', 1960)))
        h_ages = _mc_vectorized_sample_death_ages(c, np_rng, n_sims, members[0], 0, h_dob, plan_start)
    else:
        h_dob = int(c.get('h_dob_yr', 1960))
        h_ages = _mc_vectorized_sample_death_ages(c, np_rng, n_sims, {}, 0, h_dob, plan_start)
    h = h_dob + h_ages
    if len(members) > 1:
        w_dob = int(members[1].get('dob_yr', c.get('w_dob_yr', 1960)))
        w_ages = _mc_vectorized_sample_death_ages(c, np_rng, n_sims, members[1], 1, w_dob, plan_start)
        w = w_dob + w_ages
    else:
        w = h.copy()
    return h, w, _np.maximum(h, w)


def _mc_vectorized_return_paths(c: dict, np_rng, n_sims: int, years: list[int], mu: float, sig: float, use_asset_classes: bool = True):
    n_years = len(years)
    diagnostics = {'return_model': 'vectorized_single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    base_draws = None
    port_mu, port_sig = float(mu), float(max(1e-6, sig))
    if use_asset_classes and bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            classes, weights, means, cov, port_mu, port_sig = _portfolio_asset_class_inputs(c)
            raw = np_rng.multivariate_normal(_np.array(means, dtype=float), cov, size=(n_sims, n_years), check_valid='warn')
            wv = _np.array(weights, dtype=float)
            base_draws = raw.dot(wv)
            diagnostics.update({
                'return_model': 'vectorized_asset_class_covariance',
                'portfolio_expected_return': float(port_mu),
                'portfolio_sigma': float(max(1e-6, port_sig)),
                'asset_classes': classes,
                'asset_weights': {cls: weights[i] for i, cls in enumerate(classes)},
            })
        except Exception as exc:
            diagnostics['return_model_warning'] = str(exc)
    if base_draws is None:
        # Generate the same regime-aware distribution as _sample_return, but in
        # one batched draw for all simulations and years.
        u = np_rng.random((n_sims, n_years))
        recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
        offsets = _np.zeros((n_sims, n_years), dtype=float)
        sigma_mult = _np.ones((n_sims, n_years), dtype=float)
        offsets = _np.where(u < 0.025, -0.24, offsets)
        sigma_mult = _np.where(u < 0.025, 1.8, sigma_mult)
        offsets = _np.where((u >= 0.025) & (u < 0.115), -0.10, offsets)
        sigma_mult = _np.where((u >= 0.025) & (u < 0.115), 1.25, sigma_mult)
        offsets = _np.where((u >= 0.115) & (u < 0.20), -0.045, offsets)
        sigma_mult = _np.where((u >= 0.115) & (u < 0.20), 1.15, sigma_mult)
        base_draws = np_rng.normal(float(mu) + recenter + offsets, float(sig) * sigma_mult)
        port_mu, port_sig = float(mu), float(max(1e-6, sig))
    else:
        u = np_rng.random((n_sims, n_years))
        recenter = 0.018825 if bool(c.get('mc_recenter_regime_returns', True)) else 0.0
        offsets = _np.zeros((n_sims, n_years), dtype=float)
        extra_sigma = _np.zeros((n_sims, n_years), dtype=float)
        offsets = _np.where(u < 0.025, -0.24, offsets)
        extra_sigma = _np.where(u < 0.025, port_sig * 0.80, extra_sigma)
        offsets = _np.where((u >= 0.025) & (u < 0.115), -0.10, offsets)
        extra_sigma = _np.where((u >= 0.025) & (u < 0.115), port_sig * 0.35, extra_sigma)
        offsets = _np.where((u >= 0.115) & (u < 0.20), -0.045, offsets)
        extra_sigma = _np.where((u >= 0.115) & (u < 0.20), port_sig * 0.20, extra_sigma)
        base_draws = base_draws + recenter + offsets + np_rng.normal(0.0, extra_sigma)

    if str(c.get('glide_path', 'target_date')).lower() != 'static':
        bond_mu = float(c.get('ret_bond', 0.04) or 0.04)
        glide = _np.array([max(0.65, 1.0 - 0.01 * i) for i in range(n_years)], dtype=float)
        base_draws = bond_mu + (base_draws - bond_mu) * glide.reshape(1, -1)

    phi = max(-0.75, min(0.75, float(c.get('mc_serial_correlation', 0.0) or 0.0)))
    if abs(phi) > 1e-9 and n_years > 1:
        adjusted = base_draws.copy()
        damp = math.sqrt(max(0.0, 1.0 - phi * phi))
        for j in range(1, n_years):
            adjusted[:, j] = port_mu + phi * (adjusted[:, j - 1] - port_mu) + damp * (base_draws[:, j] - port_mu)
        base_draws = adjusted
        diagnostics['serial_correlation'] = phi
    return _np.clip(base_draws, -0.95, 1.50), diagnostics


def _mc_vectorized_inflation_health_paths(c: dict, np_rng, returns, mu: float, sig: float):
    n_sims, n_years = returns.shape
    inf_mu = float(c.get('inf', 0.025) or 0.025)
    inf_sig = max(0.0, float(c.get('mc_inflation_sigma', 0.015) or 0.015))
    corr = max(-0.95, min(0.95, float(c.get('mc_return_inflation_corr', -0.25) or 0.0)))
    stochastic = bool(c.get('mc_inflation_stochastic', True))
    ret_z = _np.zeros_like(returns)
    if sig > 1e-9:
        ret_z = (returns - float(mu)) / float(sig)
    innovation = np_rng.normal(0.0, 1.0, size=returns.shape)
    surprise = inf_sig * (corr * ret_z + math.sqrt(max(0.0, 1.0 - corr * corr)) * innovation) if stochastic else 0.0
    rates = _np.clip(inf_mu + surprise, -0.02, 0.12).astype(float)
    if n_years:
        rates[:, 0] = inf_mu
    inflation_index = _np.ones_like(rates)
    if n_years > 1:
        inflation_index[:, 1:] = _np.cumprod(1.0 + rates[:, 1:], axis=1)

    def _linked_index(base_rate: float, weight: float, cap: float):
        linked = _np.clip(base_rate + weight * (rates - inf_mu), 0.0, cap)
        out = _np.ones_like(linked)
        if n_years > 1:
            out[:, 1:] = _np.cumprod(1.0 + linked[:, 1:], axis=1)
        return out

    ss_index = _linked_index(float(c.get('ss_cola', 0.02) or 0.02), 0.70, 0.10)
    brk_index = _linked_index(float(c.get('brk_inf', 0.02) or 0.02), 0.65 if c.get('mc_bracket_stochastic', True) else 0.0, 0.08)
    medical_index = _linked_index(float(c.get('med_inf', 0.055) or 0.055), 0.85, 0.14)

    shocks = _np.zeros_like(rates)
    if bool(c.get('mc_wellness_shocks', True)):
        prob = max(0.0, min(1.0, float(c.get('mc_wellness_prob', 0.03) or 0.0)))
        mean_cost = max(0.0, float(c.get('mc_wellness_mean', 150000.0) or 0.0))
        if prob > 0 and mean_cost > 0:
            mask = np_rng.random(size=rates.shape) < prob
            severity = _np.minimum(mean_cost * 4.0, np_rng.exponential(mean_cost, size=rates.shape))
            shocks = _np.where(mask, severity, 0.0)
    return {
        'inflation_by_year_matrix': rates,
        'inflation_index_matrix': inflation_index,
        'ss_cola_index_matrix': ss_index,
        'bracket_index_matrix': brk_index,
        'medical_index_matrix': medical_index,
        'wellness_shock_matrix': shocks,
    }


def _mc_apply_withdrawal_bucket(balances, request, bucket: str):
    amount = _np.minimum(balances[bucket], _np.maximum(0.0, request))
    balances[bucket] -= amount
    return amount, request - amount


def _mc_tier_bucket_cascade(balances, need, bucket_order: tuple, tax_drag=None):
    """Genuine per-tier withdrawal redirection (optimization-refactor "Not
    done" item, Option B): draw ``need`` (shape ``(n_sims,)``, this tier's
    real dollar spending need for the year) sequentially from ``balances``
    using ONLY the buckets in ``bucket_order`` -- unlike
    ``_mc_apply_withdrawal_bucket``'s pre-existing fallback loop (which lets
    any bucket cover any shortfall), a need that survives every bucket in
    this tuple is a genuine shortfall for THIS tier: it never falls through
    to a bucket outside ``bucket_order``.

    ``tax_drag`` (shape ``(n_sims,)``), if given, grosses up the request at
    the ``'pretax'`` step so the gross dollars actually pulled from pretax
    also cover the approximate marginal tax on that withdrawal -- the same
    padding the pre-existing single-bucket-replay code applied, now scoped
    to whichever tier's cascade reaches the pretax step. The residual need
    carried forward is converted back to net (spending-power) dollars so
    later buckets in the cascade see the true remaining need, not the
    grossed-up figure.

    Returns the genuinely unfunded remainder for this tier (>= 0); balances
    are mutated in place as each bucket in ``bucket_order`` is drawn down.
    """
    remaining = _np.maximum(0.0, need)
    for bucket in bucket_order:
        if bucket == 'pretax' and tax_drag is not None:
            grossed = remaining * (1.0 + tax_drag)
            _taken, left = _mc_apply_withdrawal_bucket(balances, grossed, 'pretax')
            remaining = left / (1.0 + tax_drag)
        else:
            _taken, remaining = _mc_apply_withdrawal_bucket(balances, remaining, bucket)
    return remaining


def _max_consecutive_true_per_row(mask) -> "_np.ndarray":
    """For a boolean ``(n_sims, n_years)`` matrix, the longest run of
    consecutive True columns per row. Small ``n_years`` (a plan horizon), so
    a plain Python loop over columns -- vectorized across all rows/paths at
    once via the running-counter reset trick -- is simpler than a fully
    vectorized run-length encoding and just as fast at this scale.
    """
    n_sims = mask.shape[0]
    run = _np.zeros(n_sims, dtype=int)
    best = _np.zeros(n_sims, dtype=int)
    for j in range(mask.shape[1]):
        run = _np.where(mask[:, j], run + 1, 0)
        best = _np.maximum(best, run)
    return best


def _mc_tier_priority_retained(tier_scaled: dict, cut_mult) -> dict:
    """Optimization-refactor Phase 2 follow-on ("Not done" item 1):
    redistribute the SAME total dollar cut a uniform ``cut_mult`` already
    applies across discretionary/important/essential tiers by cut priority
    (discretionary first, essential protected last) instead of shrinking
    every tier by the identical fraction -- the vectorized-engine analogue of
    the cascade ``spending_priority_cut_check`` already uses to report a
    solved ``cut_frac``.

    ``tier_scaled`` holds each tier's nominal spend, already scaled to a
    path's sampled inflation (pre-cut) -- shape ``(n_sims, n_years)`` per
    tier. ``cut_mult`` is the per-path retained fraction (``1 -
    spend_cut_frac``, shape ``(n_sims,)``).

    ``contingent_liability`` (if present) is excluded from the PRIORITY
    REDISTRIBUTION pool -- it keeps the pre-existing uniform ``cut_mult``
    treatment rather than being reordered against discretionary/important/
    essential -- but it is NOT excluded from absorbing a shortfall entirely
    (that exclusion was a bug, fixed in ffa142b: ``spending_priority_cut_
    check`` and this function's own caller now both walk
    ``SPENDING_TIER_CUT_ORDER``, which places contingent_liability between
    important and essential). The uniform-``cut_mult`` figure this function
    returns for it is exactly what that cascade consumes.

    The combined total across ALL tiers is unchanged either way (bit-
    identical to the pre-existing uniform reduction): this only changes how
    the same dollar cut is attributed across tiers, never the total. It
    therefore never affects out['taxable']/'pretax'/'roth'/'cash']/'liquid'/
    'total'/'unfunded'/'path_success'/'success_rate' -- none of which read
    tier attribution -- only 'spend_{tier}_real' and the essential-shortfall
    attribution derived from it below.
    """
    mult = _np.clip(_np.asarray(cut_mult, dtype=float), 0.0, 1.0).reshape(-1, 1)
    cuttable = [t for t in ('discretionary', 'important', 'essential') if t in tier_scaled]
    if not cuttable:
        return {tier: arr * mult for tier, arr in tier_scaled.items()}
    zeros = _np.zeros_like(tier_scaled[cuttable[0]])
    d_arr = tier_scaled.get('discretionary', zeros)
    i_arr = tier_scaled.get('important', zeros)
    e_arr = tier_scaled.get('essential', zeros)
    total_cuttable = d_arr + i_arr + e_arr
    target_cut = total_cuttable * (1.0 - mult)
    d_taken = _np.minimum(d_arr, target_cut)
    rem1 = _np.maximum(0.0, target_cut - d_taken)
    i_taken = _np.minimum(i_arr, rem1)
    rem2 = _np.maximum(0.0, rem1 - i_taken)
    e_taken = _np.minimum(e_arr, rem2)
    retained: dict = {}
    if 'discretionary' in tier_scaled:
        retained['discretionary'] = d_arr - d_taken
    if 'important' in tier_scaled:
        retained['important'] = i_arr - i_taken
    if 'essential' in tier_scaled:
        retained['essential'] = e_arr - e_taken
    for tier, arr in tier_scaled.items():
        if tier not in retained:
            retained[tier] = arr * mult
    return retained


def _mc_vectorized_projection(c: dict, base_rows: list[dict], returns, inflation_paths: dict, max_death_years, spend_cut_frac=0.0,
                               h_death_years=None, w_death_years=None, survivor_buckets=None, allocation='tier'):
    """Vectorized tax-bucket withdrawal recursion for Monte Carlo paths.

    ``spend_cut_frac``: per-path uniform reduction (0..1) applied to the
    taxable/pretax/Roth/cash withdrawal requests that fund spending (HSA draws
    for wellness shocks are excluded — those aren't discretionary spending).
    Defaults to 0.0, an exact no-op, so existing callers are bit-identical.
    Used by ``_mc_required_cut_distribution`` (P13 phase 1) to binary-search
    the smallest cut that rescues a failing path; never touches the primary
    success/failure computation itself.

    ``h_death_years``/``w_death_years``/``survivor_buckets`` (optimization
    refactor Phase 1 items 4-6): per-path sampled death years and the
    precomputed survivor trajectories from ``_mc_survivor_bucket_flows``. All
    three default to None, which makes every survivor-blended matrix below
    reduce to broadcasting the single deterministic trajectory across every
    path -- bit-identical to the pre-items-4-6 behavior. Passing them applies
    each path's own first-death-year- and which-spouse-dependent survivor
    spending factor, SS/pension changes, and filing-status tax effects to the
    WITHDRAWAL REQUESTS themselves (not just a reported side-metric), for
    years after that path's own sampled first death.

    ``allocation`` selects how each year's need is assigned to account buckets:

    * ``'tier'`` (default): the per-tier cascade under
      ``SPENDING_TIER_BUCKET_POLICY`` (a tier's need never reaches a bucket
      outside its own policy, e.g. discretionary never reaches Roth). Yields
      the per-tier funding/shortfall figures and the "within tier-bucket
      rules" success definition.
    * ``'replay'``: replay the deterministic engine's own per-bucket draws
      (scaled by path inflation) with any-bucket fallback for what a bucket
      cannot cover, i.e. Roth is a last resort for ANY spending, exactly as in
      the deterministic and exact-scalar engines. The replayed draws already
      contain the tax on themselves, so no blended ``tax_drag`` gross-up is
      applied. This is the "funded as asked" definition used for the headline
      success rate (see N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md).

    In both modes, at a path's first death the credit-shelter trust (when the
    plan has one) sequesters the taxable/cash balance the deterministic engine
    sequesters (``survivor_buckets['cst_funded_at_death']``); that money is not
    available to the survivor.
    """
    n_sims, n_years = returns.shape
    starts = _mc_bucket_starting_balances(c)
    # C3 / Wave 3.5 completion. Wave 3.5 wired per-account returns into the
    # deterministic engine, and its follow-up wired the scalar MC path; both
    # left THIS path -- the one that produces the headline success rate --
    # growing every bucket at one identical rate. Empty dict => bit-identical
    # to the previous behavior, so plans without holdings detail are unmoved.
    bucket_tilts = _mc_bucket_return_tilts(c)
    flows = _mc_row_bucket_flows(c, base_rows)
    years = _np.array(flows['years'], dtype=int)
    active = years.reshape(1, -1) <= max_death_years.reshape(-1, 1)
    inf_idx = inflation_paths['inflation_index_matrix']
    med_idx = inflation_paths['medical_index_matrix']
    shocks = inflation_paths['wellness_shock_matrix']
    det_idx = _np.maximum(1e-12, flows['deterministic_inflation_index']).reshape(1, -1)
    spending_scale = inf_idx / det_idx
    cut_mult = _np.clip(1.0 - _np.broadcast_to(_np.asarray(spend_cut_frac, dtype=float), (n_sims,)), 0.0, 1.0)
    # Per-calendar-year gate for the wellness-shock HSA draw below. Depends
    # only on (c, year) -- not on the path -- so it is resolved once here
    # rather than per path per year inside the recursion.
    cl_hsa_allowed_by_year = _np.array(
        [hsa_unscheduled_draw_allowed(c, int(y)) for y in years], dtype=bool)

    # Phase 1 items 4-6: select each path's survivor-bucket trajectory (if
    # any) for years after that path's own sampled first death. bucket_id
    # here MUST use the exact formula _mc_survivor_bucket_flows used to WRITE
    # its arrays (spouse_first * n_years + year_idx, same n_years/plan_start
    # the bucket dict itself recorded) -- any drift silently selects the
    # wrong bucket for every path.
    if survivor_buckets is not None and h_death_years is not None and w_death_years is not None:
        first_death = _np.minimum(h_death_years, w_death_years)
        # Tie (h_death_years == w_death_years) arbitrarily assigned to "H
        # first"; provably inert since a tie year is also that path's
        # max_death_years, so the active mask already excludes every year
        # > first_death for that path regardless of which bucket is picked.
        spouse_first = _np.where(h_death_years <= w_death_years, 0, 1)
        sb_plan_start = int(survivor_buckets['plan_start'])
        sb_n_years = int(survivor_buckets['n_years'])
        year_idx = _np.clip(first_death - sb_plan_start, 0, sb_n_years - 1).astype(int)
        bucket_id = spouse_first * sb_n_years + year_idx
        use_bucket_mask = years.reshape(1, -1) > first_death.reshape(-1, 1)
    else:
        bucket_id = None
        use_bucket_mask = _np.zeros((n_sims, n_years), dtype=bool)
    eff = _mc_effective_row_flows(flows, survivor_buckets, bucket_id, use_bucket_mask, n_sims, n_years)

    balances, nonliquid, out, tax_drag, tier_scaled = _mc_projection_init_balances(allocation, base_rows, eff, n_sims, n_years, spending_scale, starts)
    tier_retained = _mc_tier_priority_retained(tier_scaled, cut_mult) if tier_scaled else {}
    # Bound only under ``if tier_scaled:`` below; the extracted sections read them
    # only under the same guard, so None placeholders keep the call arguments bound.
    tier_shortfall = tier_actual_spend = SPENDING_TIER_ESSENTIAL = None
    if tier_scaled:
        from .spending_budget_resolver import (
            SPENDING_TIER_BUCKET_POLICY, MC_TIER_FUNDING_ORDER,
            SPENDING_TIER_ESSENTIAL, SPENDING_TIER_CONTINGENT,
        )
        _other_bucket_order = SPENDING_TIER_BUCKET_POLICY[SPENDING_TIER_ESSENTIAL]
        tier_shortfall = {tier: _np.zeros((n_sims, n_years)) for tier in tier_retained}
        tier_actual_spend = {tier: _np.zeros((n_sims, n_years)) for tier in tier_retained}
        # A row's spend_by_tier can carry a tier key SPENDING_TIER_BUCKET_
        # POLICY doesn't recognize (e.g. deterministic_engine.py's
        # 'unclassified' bucket for business_expenses_yr -- a real dollar
        # amount, just not one of the four taxonomized tiers). Fund it
        # alongside essential/contingent_liability/'other' (unrestricted
        # full cascade, highest funding priority) rather than silently
        # dropping it from both withdrawals and reporting.
        _extra_tiers = tuple(t for t in tier_retained if t not in SPENDING_TIER_BUCKET_POLICY)
        funding_order = (MC_TIER_FUNDING_ORDER[0],) + _extra_tiers + MC_TIER_FUNDING_ORDER[1:]

    for j in range(n_years):
        act = active[:, j]
        if bucket_id is not None and 'cst_funded_at_death' in survivor_buckets:
            # Credit-shelter trust funding at this path's first death: the
            # deterministic engine moves up to min(cs_amount, shelter cap) out
            # of the survivor's taxable (then cash) accounts into a trust that
            # is excluded from the survivor's spendable/liquid assets.
            _fd_now = act & (first_death == years[j])
            if _np.any(_fd_now):
                _cst_want = _np.where(_fd_now, survivor_buckets['cst_funded_at_death'][bucket_id], 0.0)
                _, _cst_left = _mc_apply_withdrawal_bucket(balances, _cst_want, 'taxable')
                _mc_apply_withdrawal_bucket(balances, _cst_left, 'cash')
        # Wellness shocks are the sampled half of the contingent_liability
        # tier, and drawing them from the HSA first is this engine's own
        # long-standing precedent -- but it was ungated, while the
        # deterministic engine's new contingent-liability draw defers to
        # hsa_withdrawal_mode. Applying the same gate here keeps the two
        # engines from disagreeing about the same tier: under a scheduled
        # drawdown mode the schedule is the sole authority on HSA dollars,
        # so the shock falls into the normal cascade exactly as any other
        # spend would. (The premium half, ltc_prem_yr, needs no wiring here
        # -- it flows in through eff['withdrawals']['hsa'] / spend_by_tier's
        # contingent_liability total, since the deterministic rows this
        # engine scales already carry that draw.)
        shock_need = shocks[:, j] * act
        if cl_hsa_allowed_by_year[j]:
            _, shock_left = _mc_apply_withdrawal_bucket(balances, shock_need, 'hsa')
        else:
            shock_left = shock_need

        if tier_scaled:
            # Genuine per-tier redirection: each tier's real dollar need for
            # this year draws ONLY from the buckets SPENDING_TIER_BUCKET_
            # POLICY allows it, in MC_TIER_FUNDING_ORDER (essential/
            # contingent_liability/taxes-and-misc funded first so they are
            # never crowded out by important/discretionary competing for the
            # same shared balances; discretionary last). A tier's need that
            # survives every bucket in its own policy is a genuine
            # shortfall for THAT tier -- it does not fall through to a
            # bucket outside its policy (contrast with the pre-existing
            # any-bucket-covers-any-shortfall fallback this replaces).
            #
            # "other" is whatever this year's total deterministic bucket
            # draw represents beyond the tier-tagged spend total (taxes,
            # debt service, and any other non-tier-tagged cash need) --
            # these are no more optional than essential spending, so they
            # share essential's unrestricted bucket policy and funding
            # priority. Deliberately NOT scaled by cut_mult (a spending cut
            # doesn't proportionally reduce tax owed), only by this path's
            # own sampled inflation.
            other_nominal = _np.maximum(0.0, (
                eff['withdrawals']['taxable'][:, j] + eff['withdrawals']['pretax'][:, j]
                + eff['withdrawals']['roth'][:, j] + eff['withdrawals']['cash'][:, j]
                - sum(eff['spend_by_tier'][t][:, j] for t in eff['spend_by_tier'])
            ))
            need_by_label = {'other': _np.where(act, other_nominal * spending_scale[:, j], 0.0)}
            for tier in tier_retained:
                tier_need = _np.where(act, tier_retained[tier][:, j], 0.0)
                if tier == SPENDING_TIER_CONTINGENT:
                    tier_need = tier_need + shock_left
                need_by_label[tier] = tier_need
            if SPENDING_TIER_CONTINGENT not in tier_retained:
                need_by_label['other'] = need_by_label['other'] + shock_left

            # income_funding (SS/pension/annuities/wages) pays for spending
            # tiers directly, with NO account withdrawal at all, before the
            # bucket cascade below ever runs -- exactly how the deterministic
            # engine's own gap = total_cash_need - income_from_streams
            # already treats it. 'other' is excluded here: it is derived
            # from eff['withdrawals'] (the deterministic engine's actual,
            # already-income-net investment-account draw), so it is already
            # net of income and must not have income subtracted a second
            # time. Applied in funding_order (essential/contingent_liability
            # first, discretionary last) so income -- the cheapest possible
            # dollar, no account depletion or tax cost -- covers the
            # highest-priority spending first, same as the bucket cascade's
            # own priority.
            # gross_need_by_label (pre-income) is what spend_{tier}_real
            # reports as "actually spent" -- a tier funded partly by income
            # and partly by an account withdrawal is still fully spent, so
            # reporting must not shrink to only the withdrawn portion.
            gross_need_by_label = dict(need_by_label)
            income_avail = _np.where(act, eff['income_funding'][:, j] * spending_scale[:, j], 0.0)
            for label in funding_order:
                if label == 'other' or label not in need_by_label:
                    continue
                covered = _np.minimum(income_avail, need_by_label[label])
                need_by_label[label] = need_by_label[label] - covered
                income_avail = income_avail - covered

            unfunded = _np.zeros(n_sims, dtype=float)
            for label in funding_order:
                if label not in need_by_label:
                    continue
                bucket_order = SPENDING_TIER_BUCKET_POLICY.get(label, _other_bucket_order)
                drag = tax_drag[:, j] if 'pretax' in bucket_order else None
                shortfall = _mc_tier_bucket_cascade(balances, need_by_label[label], bucket_order, tax_drag=drag)
                if label != 'other':
                    tier_shortfall[label][:, j] = shortfall
                    tier_actual_spend[label][:, j] = gross_need_by_label[label] - shortfall
                unfunded = unfunded + shortfall
        else:
            # Pre-existing behavior for a plan whose rows never carried
            # spend_by_tier: one blended per-bucket request (the
            # deterministic engine's own already-decided split, replayed
            # forward and scaled), with fallback across ANY bucket for
            # whatever a single bucket couldn't cover -- unchanged.
            planned = {
                'taxable': eff['withdrawals']['taxable'][:, j] * spending_scale[:, j] * cut_mult,
                'pretax': eff['withdrawals']['pretax'][:, j] * spending_scale[:, j] * cut_mult,
                'roth': eff['withdrawals']['roth'][:, j] * spending_scale[:, j] * cut_mult,
                'hsa': eff['withdrawals']['hsa'][:, j] * med_idx[:, j] / det_idx[:, j],
                'cash': eff['withdrawals']['cash'][:, j] * spending_scale[:, j] * cut_mult,
            }
            # Pretax withdrawals carry an approximate marginal tax gross-up so
            # the vectorized path does not understate tax pressure in poor
            # markets.
            planned['pretax'] = planned['pretax'] * (1.0 + tax_drag[:, j])
            planned['taxable'] = planned['taxable'] + shock_left

            unfunded = _np.zeros(n_sims, dtype=float)
            for bucket in ('cash', 'taxable', 'pretax', 'roth', 'hsa'):
                req = _np.where(act, planned[bucket], 0.0)
                taken, left = _mc_apply_withdrawal_bucket(balances, req, bucket)
                # Cascade residual need through remaining liquid buckets.
                if _np.any(left > 1e-6):
                    for fallback in ('taxable', 'pretax', 'roth', 'hsa', 'cash'):
                        if fallback == bucket:
                            continue
                        extra, left = _mc_apply_withdrawal_bucket(balances, left, fallback)
                        if not _np.any(left > 1e-6):
                            break
                unfunded += _np.maximum(0.0, left)

        for bucket in ('cash', 'taxable', 'pretax', 'roth', 'hsa'):
            balances[bucket] += _np.where(act, eff['deposits'][bucket][:, j], 0.0)

        conv = _np.minimum(balances['pretax'], _np.where(act, eff['conversions_out']['pretax'][:, j] * spending_scale[:, j], 0.0))
        balances['pretax'] -= conv
        balances['roth'] += conv

        growth = returns[:, j]
        _mc_apply_bucket_growth(balances, growth, bucket_tilts)
        # Cash gets a conservative short-rate proxy tied to inflation rather than equity returns.
        cash_rate = _np.clip(inflation_paths['inflation_by_year_matrix'][:, j] * 0.60, 0.0, 0.06)
        balances['cash'] = _np.maximum(0.0, balances['cash'] * (1.0 + cash_rate))

        out['pretax'][:, j] = balances['pretax']
        out['roth'][:, j] = balances['roth']
        out['taxable'][:, j] = balances['taxable']
        out['hsa'][:, j] = balances['hsa']
        out['cash'][:, j] = balances['cash']
        out['liquid'][:, j] = balances['pretax'] + balances['roth'] + balances['taxable'] + balances['hsa']
        out['total'][:, j] = out['liquid'][:, j] + balances['cash'] + nonliquid[j]
        out['unfunded'][:, j] = unfunded

    _gk_band = _mc_projection_real_matrices(c, eff, inf_idx, out, spending_scale, tier_actual_spend, tier_retained, years)
    _mc_projection_tier_cascade(SPENDING_TIER_ESSENTIAL, _gk_band, active, c, eff, flows, inf_idx, inflation_paths, n_sims, n_years, out, returns, spending_scale, starts, tier_scaled, tier_shortfall, use_bucket_mask, years)
    return out


def _mc_vectorized_batch(c: dict, base_rows: list[dict], n_sims: int, seed: int, mu: float, sig: float, success_threshold: float, use_asset_classes: bool = True, survivor_buckets=None, allocation: str = 'tier', tier_shadow: bool = False):
    """``allocation``/``tier_shadow``: see ``_mc_vectorized_projection``. With
    ``allocation='replay'`` the headline ``path_success`` is the "funded as
    asked" definition; ``tier_shadow=True`` additionally runs the tier-bucket
    cascade on the same paths to supply the per-tier funding figures and
    ``within_policy_path_success`` (funded without breaking tier bucket rules).

    ``survivor_buckets`` (optimization refactor Phase 1 items 4-6): pass
    the caller's already-built ``_mc_survivor_bucket_flows(c, base_rows)``
    result to avoid rebuilding it (2 * n_years project() calls) on every one
    of the many _mc_vectorized_batch calls a single monte_carlo() invocation
    makes (main batch + sensitivity grid + bisections). When omitted, this
    function builds it itself (gated by mc_vectorized_survivor_economics,
    default True) as a safe-but-slow fallback for direct/test callers.
    """
    np_rng = _np.random.default_rng(int(seed))
    years = [int(r['year']) for r in base_rows]
    h_death, w_death, max_death = _mc_vectorized_death_years(c, np_rng, int(n_sims))
    returns, return_diag = _mc_vectorized_return_paths(c, np_rng, int(n_sims), years, mu, sig, use_asset_classes=use_asset_classes)
    inflation_paths = _mc_vectorized_inflation_health_paths(
        c, np_rng, returns,
        float(return_diag.get('portfolio_expected_return', mu) or mu),
        float(return_diag.get('portfolio_sigma', sig) or sig),
    )
    if survivor_buckets is None and bool(c.get('mc_vectorized_survivor_economics', True)):
        survivor_buckets = _mc_survivor_bucket_flows(c, base_rows)
    projection = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death,
                                            h_death_years=h_death, w_death_years=w_death,
                                            survivor_buckets=survivor_buckets, allocation=allocation)
    within_policy_path_success = None
    if allocation == 'replay' and tier_shadow:
        _shadow = _mc_vectorized_projection(c, base_rows, returns, inflation_paths, max_death,
                                            h_death_years=h_death, w_death_years=w_death,
                                            survivor_buckets=survivor_buckets, allocation='tier')
        for _k in _shadow:
            if _k.startswith('spend_') or _k in ('essential_shortfall_real', 'essential_fully_funded'):
                projection[_k] = _shadow[_k]
        _act = _np.array(years, dtype=int).reshape(1, -1) <= max_death.reshape(-1, 1)
        within_policy_path_success = ~_np.any(
            ((_shadow['unfunded'] > 1.0) | (_shadow['liquid'] <= float(success_threshold))) & _act, axis=1)
    cumulative_shortfall_real_pct, cut_years_pct, essential_fully_funded_probability, first_failure_years, liquidity_coverage_pct_by_year, max_annual_shortfall_real_pct, max_consecutive_cut_years_pct, path_success, probability_any_cut, survivor_period_applicable_probability, survivor_period_failure_probability, worst_liquidity_coverage_ratio_pct = _mc_batch_success_metrics(max_death, projection, success_threshold, years)
    after_tax_terminal_nw_pct, effective_lifetime_tax_rate_pct, post_tax_inheritance_pct, probability_guardrail_cut, probability_guardrail_raise, probability_legacy_floor_met, tax_npv_pct = _mc_batch_after_tax_metrics(c, h_death, projection, w_death, years)
    return {
        'years': years,
        'returns': returns,
        'inflation_paths': inflation_paths,
        'projection': projection,
        'path_success': path_success,
        'within_policy_path_success': within_policy_path_success,
        'allocation': allocation,
        'first_failure_years': first_failure_years,
        'return_diag': return_diag,
        'h_death_years': h_death,
        'w_death_years': w_death,
        'max_death_years': max_death,
        'survivor_buckets': survivor_buckets,
        'essential_fully_funded_probability': essential_fully_funded_probability,
        'probability_any_cut': probability_any_cut,
        'cut_years_pct': cut_years_pct,
        'max_annual_shortfall_real_pct': max_annual_shortfall_real_pct,
        'max_consecutive_cut_years_pct': max_consecutive_cut_years_pct,
        'cumulative_shortfall_real_pct': cumulative_shortfall_real_pct,
        'liquidity_coverage_pct_by_year': liquidity_coverage_pct_by_year,
        'worst_liquidity_coverage_ratio_pct': worst_liquidity_coverage_ratio_pct,
        'after_tax_terminal_nw_pct': after_tax_terminal_nw_pct,
        'post_tax_inheritance_pct': post_tax_inheritance_pct,
        'probability_legacy_floor_met': probability_legacy_floor_met,
        'survivor_period_applicable_probability': survivor_period_applicable_probability,
        'survivor_period_failure_probability': survivor_period_failure_probability,
        'tax_npv_pct': tax_npv_pct,
        'effective_lifetime_tax_rate_pct': effective_lifetime_tax_rate_pct,
        'probability_guardrail_cut': probability_guardrail_cut,
        'probability_guardrail_raise': probability_guardrail_raise,
    }


def _mc_vectorized_sensitivity_success_rate(c: dict, base_rows: list[dict], mu: float, sig: float, n_sims: int, seed: int, threshold: float, survivor_buckets=None) -> float:
    batch = _mc_vectorized_batch(c, base_rows, max(1, int(n_sims)), seed, mu, sig, threshold, use_asset_classes=False, survivor_buckets=survivor_buckets, allocation='replay')
    try:
        return float(_np.mean(batch['path_success']))
    except Exception:
        return sum(1 for x in batch['path_success'] if x) / max(1, int(n_sims))


def _mc_required_cut_distribution(c: dict, base_rows: list[dict], batch: dict, success_threshold: float, max_iters: int = 16, cut_cap: float = 0.90) -> dict:
    """P13 phase 1: for each path that failed the existing success test,
    binary-search the smallest uniform spending cut (see ``spend_cut_frac`` on
    ``_mc_vectorized_projection``) that would have kept that specific path
    (same sampled returns/inflation/death year) funded. Purely additive
    diagnostic reporting — does not touch ``path_success``/``success_rate``,
    which are already fixed by the time this runs.
    """
    path_success = _np.asarray(batch['path_success'], dtype=bool)
    fail_idx = _np.where(~path_success)[0]
    if fail_idx.size == 0:
        return {'n_failing': 0, 'n_infeasible': 0, 'required_cut_median': None, 'required_cut_p90': None, 'required_cuts': []}

    years = _np.array(batch['years'], dtype=int)
    returns_f = batch['returns'][fail_idx]
    max_death_f = batch['max_death_years'][fail_idx]
    infl_f = {k: v[fail_idx] for k, v in batch['inflation_paths'].items()}
    n_fail = int(fail_idx.size)
    # Phase 1 items 4-6: survivor_buckets is a pure function of (c, base_rows)
    # -- not of which paths failed -- so it's reused unfiltered; only the
    # per-path death-year arrays need the same fail_idx filter as returns/
    # inflation/max_death above.
    h_death_f = batch.get('h_death_years')
    w_death_f = batch.get('w_death_years')
    if h_death_f is not None:
        h_death_f = h_death_f[fail_idx]
    if w_death_f is not None:
        w_death_f = w_death_f[fail_idx]
    survivor_buckets = batch.get('survivor_buckets')

    def _succeeds(cut_vec):
        proj = _mc_vectorized_projection(c, base_rows, returns_f, infl_f, max_death_f, spend_cut_frac=cut_vec,
                                          h_death_years=h_death_f, w_death_years=w_death_f, survivor_buckets=survivor_buckets,
                                          allocation=batch.get('allocation', 'tier'))
        active = years.reshape(1, -1) <= max_death_f.reshape(-1, 1)
        failure = ((proj['unfunded'] > 1.0) | (proj['liquid'] <= float(success_threshold))) & active
        return ~_np.any(failure, axis=1)

    lo = _np.zeros(n_fail, dtype=float)
    hi = _np.full(n_fail, float(cut_cap), dtype=float)
    feasible = _succeeds(hi)
    for _ in range(max_iters):
        mid = (lo + hi) / 2.0
        ok = _succeeds(mid)
        hi = _np.where(ok, mid, hi)
        lo = _np.where(ok, lo, mid)

    required = _np.where(feasible, hi, _np.nan)
    feasible_vals = required[~_np.isnan(required)]
    return {
        'n_failing': n_fail,
        'n_infeasible': int(n_fail - feasible_vals.size),
        'required_cut_median': float(_np.median(feasible_vals)) if feasible_vals.size else None,
        'required_cut_p90': float(_np.percentile(feasible_vals, 90)) if feasible_vals.size else None,
        'required_cuts': feasible_vals.tolist(),
    }


def _mc_success_rate_for_uniform_cut(c: dict, base_rows: list[dict], batch: dict, success_threshold: float, cut_frac: float) -> float:
    """Overall batch success rate at a single uniform spend_cut_frac, reusing
    the batch's already-simulated returns/inflation/death paths -- cut_frac
    only rescales withdrawal requests (see _mc_vectorized_projection), so
    this needs no new market-path simulation and is cheap to call repeatedly
    during a bisection."""
    proj = _mc_vectorized_projection(c, base_rows, batch['returns'], batch['inflation_paths'], batch['max_death_years'], spend_cut_frac=cut_frac,
                                      h_death_years=batch.get('h_death_years'), w_death_years=batch.get('w_death_years'),
                                      survivor_buckets=batch.get('survivor_buckets'),
                                      allocation=batch.get('allocation', 'tier'))
    years = _np.array(batch['years'], dtype=int)
    active = years.reshape(1, -1) <= batch['max_death_years'].reshape(-1, 1)
    failure = ((proj['unfunded'] > 1.0) | (proj['liquid'] <= float(success_threshold))) & active
    path_success = ~_np.any(failure, axis=1)
    return float(_np.mean(path_success))


def essential_discretionary_floor_check(base_rows: list[dict], cut_frac) -> dict:
    """Wave 5.5 (system review 2026-08-04, planner finding
    no-dynamic-spending-policy): "Essential/discretionary split with a
    floor." A uniform spend_cut_frac (from sustainable_spending_solve /
    _mc_required_cut_distribution) says HOW MUCH to cut but not WHERE it
    should come from. This checks whether that dollar cut, applied every
    year, could be funded entirely out of discretionary spending (Travel /
    Large Discretionary -- row['cashflow_breakdown']['expense']['travel'],
    which is deterministic_engine.py's rec_extra) without ever touching
    essential spending (spend_base, housing, wellness) -- i.e. whether
    essential spending has a protected floor at this cut level.

    Purely a reporting-layer computation: it re-labels an already-computed
    uniform dollar cut by spending purpose using the existing per-row
    cashflow_breakdown, and never changes which accounts fund withdrawals
    or any dollar total the engine/MC layer already produces.
    """
    if cut_frac is None:
        return {'essential_protected': None, 'worst_year_essential_shortfall': 0.0, 'worst_year': None}
    cut_frac = max(0.0, float(cut_frac))
    worst_shortfall = 0.0
    worst_year = None
    for row in base_rows:
        total_spend_yr = float(row.get('total_spend', 0.0) or 0.0)
        if total_spend_yr <= 0:
            continue
        discretionary_yr = float(
            (row.get('cashflow_breakdown') or {}).get('expense', {}).get('travel', 0.0) or 0.0)
        shortfall = max(0.0, total_spend_yr * cut_frac - discretionary_yr)
        if shortfall > worst_shortfall:
            worst_shortfall = shortfall
            worst_year = int(row.get('year')) if row.get('year') is not None else None
    return {
        'essential_protected': worst_shortfall <= 1.0,
        'worst_year_essential_shortfall': worst_shortfall,
        'worst_year': worst_year,
    }


def spending_priority_cut_check(base_rows: list[dict], cut_frac) -> dict:
    """Optimization-refactor Phase 2 (tiered cuts): extends
    ``essential_discretionary_floor_check``'s 2-tier check (discretionary ==
    travel only, vs. everything else) into the full SPENDING_TIERS
    cut-priority cascade using Phase 0's ``row['spend_by_tier']``
    classification instead of the travel-only proxy.

    Cascade order is ``SPENDING_TIER_CUT_ORDER``
    (``spending_budget_resolver.py``) -- discretionary, important,
    contingent_liability, essential -- the single source of truth that
    module's own comment says exists exactly for "a future spending-priority
    policy (Phase 2)". An earlier version of this function hardcoded
    ``('discretionary', 'important', 'essential')`` and excluded
    contingent_liability entirely, treating LTC premiums and wellness-shock
    costs as fully protected from ever funding a shortfall -- that
    contradicted the already-documented cut order and understated how often
    essential spending is genuinely protected (a shortfall should exhaust
    contingent-liability dollars before ever touching essential, not skip
    straight past them). Fixed to use the canonical order.

    Deliberately NOT modeled here (a real remaining nuance, left for a
    future refinement): contingent_liability bundles two different kinds of
    dollars -- ``ltc_prem_yr`` (an insurance premium, a genuine choice to
    forgo future coverage) and ``wellness_shock_yr`` (an already-incurred
    health/LTC event cost, not really a discretionary choice to skip). Both
    are cut identically here since ``spend_by_tier`` sums them into one
    tier-level figure; splitting them into separately-prioritized
    sub-categories would need a Phase-0-level change to how the tier is
    computed, out of scope for this reporting-layer fix.

    Purely a reporting-layer computation, exactly like
    ``essential_discretionary_floor_check``: re-labels an already-computed
    uniform dollar cut by spending-tier priority using the existing
    per-row ``spend_by_tier``, and never changes which accounts fund
    withdrawals or any dollar total the engine/MC layer already produces.

    Also reports the cumulative-cut bookkeeping Phase 2's dashboard section
    asks for: cut-years, cumulative cut dollars, worst single-year cut, and
    the longest run of consecutive cut years -- all in the deterministic
    engine's own nominal dollars (matching total_spend's convention, the
    same as essential_discretionary_floor_check above), not deflated to real
    plan-start dollars.
    """
    from .spending_budget_resolver import SPENDING_TIER_CUT_ORDER
    empty = {
        'essential_protected': None, 'worst_year_essential_shortfall': 0.0, 'worst_year': None,
        'cut_years': 0, 'cumulative_cut_dollars': 0.0, 'max_annual_cut_dollars': 0.0,
        'max_consecutive_cut_years': 0, 'tier_cut_by_year': {},
    }
    if cut_frac is None:
        return empty
    cut_frac = max(0.0, float(cut_frac))
    worst_essential_shortfall = 0.0
    worst_year = None
    cut_years = 0
    cumulative_cut = 0.0
    max_annual_cut = 0.0
    max_consecutive = 0
    current_consecutive = 0
    tier_cut_by_year: dict[int, dict[str, float]] = {}

    for row in base_rows:
        tiers = row.get('spend_by_tier') or {}
        total_cuttable = sum(v for t, v in tiers.items() if t in SPENDING_TIER_CUT_ORDER)
        if total_cuttable <= 0:
            current_consecutive = 0
            continue
        target_cut = total_cuttable * cut_frac
        if target_cut <= 1e-9:
            current_consecutive = 0
            continue

        remaining = target_cut
        year_cut: dict[str, float] = {}
        for tier in SPENDING_TIER_CUT_ORDER:
            available = float(tiers.get(tier, 0.0) or 0.0)
            taken = min(available, remaining)
            if taken > 0:
                year_cut[tier] = taken
                remaining -= taken
            if remaining <= 1e-9:
                break
        # Any leftover (shouldn't happen -- SPENDING_TIER_CUT_ORDER's tiers
        # sum to total_cuttable -- but a floating-point guard) counts toward
        # the essential shortfall too, same as an essential-tier cut would.
        essential_shortfall = year_cut.get('essential', 0.0) + max(0.0, remaining)

        year_val = int(row.get('year')) if row.get('year') is not None else None
        if year_val is not None:
            tier_cut_by_year[year_val] = year_cut

        if essential_shortfall > worst_essential_shortfall:
            worst_essential_shortfall = essential_shortfall
            worst_year = year_val

        actual_cut = sum(year_cut.values())
        if actual_cut > 1.0:
            cut_years += 1
            cumulative_cut += actual_cut
            max_annual_cut = max(max_annual_cut, actual_cut)
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    return {
        'essential_protected': worst_essential_shortfall <= 1.0,
        'worst_year_essential_shortfall': worst_essential_shortfall,
        'worst_year': worst_year,
        'cut_years': cut_years,
        'cumulative_cut_dollars': cumulative_cut,
        'max_annual_cut_dollars': max_annual_cut,
        'max_consecutive_cut_years': max_consecutive,
        'tier_cut_by_year': tier_cut_by_year,
    }


def sustainable_spending_solve(c: dict, base_rows: list[dict], batch: dict, success_threshold: float,
                                targets=(0.95, 0.85, 0.75), max_iters: int = 20, cut_cap: float = 0.90,
                                tolerance: float = 0.0025) -> list[dict]:
    """P13 phase 2 / system review 5.1: "What's the most I can sustainably
    spend?" is the planner's most common client question. Reuses the
    per-path binary search above (_mc_required_cut_distribution), but
    bisects a single uniform cut against the OVERALL batch success rate
    instead of a per-path rescue cut, for each of several target confidence
    levels -- turning the diagnostic machinery into an answerable question:
    at a 95%/85%/75% success target, what annual spending level does that
    imply?

    Reuses the same simulated returns/inflation/death-year paths as the main
    Monte Carlo batch across every bisection step, so each of the ~20
    iterations per target is a cheap vectorized re-run, not a new
    simulation.
    """
    base_spend = float(c.get('spend_base', 0.0) or 0.0)
    results = []
    for target in targets:
        target = float(target)
        rate_at_zero_cut = _mc_success_rate_for_uniform_cut(c, base_rows, batch, success_threshold, 0.0)
        if rate_at_zero_cut >= target:
            # Current spending already clears this target -- no cut needed;
            # the household could spend at least the current base level.
            results.append({
                'target_success_rate': target,
                'required_cut': 0.0,
                'sustainable_spend_base': base_spend,
                'achieved_success_rate': rate_at_zero_cut,
                'feasible': True,
            })
            continue
        rate_at_cap = _mc_success_rate_for_uniform_cut(c, base_rows, batch, success_threshold, cut_cap)
        if rate_at_cap < target:
            # Even the maximum modeled cut can't reach this target -- report
            # the best achievable (at cut_cap) rather than a false answer.
            results.append({
                'target_success_rate': target,
                'required_cut': cut_cap,
                'sustainable_spend_base': base_spend * (1.0 - cut_cap),
                'achieved_success_rate': rate_at_cap,
                'feasible': False,
            })
            continue
        lo, hi = 0.0, cut_cap
        for _ in range(max_iters):
            if (hi - lo) < tolerance:
                break
            mid = (lo + hi) / 2.0
            rate = _mc_success_rate_for_uniform_cut(c, base_rows, batch, success_threshold, mid)
            if rate >= target:
                hi = mid
            else:
                lo = mid
        final_rate = _mc_success_rate_for_uniform_cut(c, base_rows, batch, success_threshold, hi)
        results.append({
            'target_success_rate': target,
            'required_cut': hi,
            'sustainable_spend_base': base_spend * (1.0 - hi),
            'achieved_success_rate': final_rate,
            'feasible': True,
        })
    for entry in results:
        floor = essential_discretionary_floor_check(base_rows, entry['required_cut'])
        entry['essential_protected'] = floor['essential_protected']
        entry['essential_shortfall_worst_year_amount'] = floor['worst_year_essential_shortfall']
        entry['essential_shortfall_worst_year'] = floor['worst_year']
        # Optimization-refactor Phase 2: the full tier-priority cascade
        # (discretionary -> important -> essential last-resort), replacing
        # the travel-only 2-tier proxy above with Phase 0's real
        # spend_by_tier classification. Additive fields; essential_protected
        # above is left untouched for existing callers (sheets_stress.py).
        tiered = spending_priority_cut_check(base_rows, entry['required_cut'])
        entry['tiered_cut_years'] = tiered['cut_years']
        entry['tiered_cumulative_cut_dollars'] = tiered['cumulative_cut_dollars']
        entry['tiered_max_annual_cut_dollars'] = tiered['max_annual_cut_dollars']
        entry['tiered_max_consecutive_cut_years'] = tiered['max_consecutive_cut_years']
        entry['tiered_essential_protected'] = tiered['essential_protected']
        entry['tiered_essential_shortfall_worst_year_amount'] = tiered['worst_year_essential_shortfall']
        entry['tiered_essential_shortfall_worst_year'] = tiered['worst_year']
    return results


#: Disclosed accuracy band of the vectorized engine's headline success rate vs.
#: the exact_scalar oracle, in percentage points. Enforced by
#: tests/test_monte_carlo_default_engine_mode.py; the status stays
#: TOLERANCE_BOUNDED only while that gate passes. Tightened 10 -> 5pp
#: (2026-09-30, owner-approved) after the replay-funding fix closed the
#: headline gap (N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md); the engine is
#: still disclosed as bounded rather than claimed exact.
MC_VECTORIZED_PARITY_TOLERANCE_PP = 5.0

#: Roth policies whose vectorized-vs-scalar signed gap (replay headline path,
#: paired paths) has been MEASURED and found within the tolerance above.
#: The '+/-tol' KPI label may only be shown for these; every other policy is
#: labelled 'directional'. Mirrored in frontend/js/dashboard_decomp_home_panels.js
#: (MC_TOLERANCE_DEMONSTRATED_POLICIES); a Python test keeps the two in step.
#: See documentation/reference/MC_PARITY_MEASUREMENT_WI009.md.
MC_PARITY_DEMONSTRATED_POLICIES = frozenset({'none', 'fill_to_bracket', 'optimize_terminal_tax'})


def mc_scalar_spotcheck(c, n=20, seed=11, base_rows=None):
    """Small-N paired-path scalar spot-check of the vectorized headline.

    Samples one set of paths with the vectorized engine's generators and runs
    both the replay-allocation vectorized projection and the exact scalar
    ``project()`` on identical paths. Returns the signed gap (vectorized minus
    scalar, percentage points) for the ACTIVE policy so diagnostics can report
    it. Opt-in (slow); ``monte_carlo`` calls it only when
    ``c['mc_scalar_spotcheck_n'] > 0``.
    """
    n = max(1, int(n))
    c = _clone_for_mc(c)
    base_rows = base_rows if base_rows is not None else project(c)
    years = [int(r['year']) for r in base_rows]
    _classes, _weights, _means, _cov, mu, sig = _portfolio_asset_class_inputs(c)
    rng = _np.random.default_rng(int(seed))
    h_death, w_death, max_death = _mc_vectorized_death_years(c, rng, n)
    returns, _diag = _mc_vectorized_return_paths(c, rng, n, years, mu, sig)
    infl = _mc_vectorized_inflation_health_paths(c, rng, returns, mu, sig)
    survivor = _mc_survivor_bucket_flows(c, base_rows)
    floor = float(_mc_success_threshold_for_spotcheck(c, base_rows))
    proj = _mc_vectorized_projection(
        c, base_rows, returns, infl, max_death, h_death_years=h_death, w_death_years=w_death,
        survivor_buckets=survivor, allocation='replay')
    active = _np.array(years).reshape(1, -1) <= max_death.reshape(-1, 1)
    vec_fail = ((proj['unfunded'] > 1.0) | (proj['liquid'] <= floor)) & active
    vec_ok = ~vec_fail.any(axis=1)

    def series(matrix, i):
        return {y: float(matrix[i, j]) for j, y in enumerate(years)}

    scalar_ok = _np.zeros(n, dtype=bool)
    for i in range(n):
        c2 = _clone_for_mc(c)
        c2.update({'h_death_yr': int(h_death[i]), 'w_death_yr': int(w_death[i]),
                   'first_death_yr': int(min(h_death[i], w_death[i])), 'plan_end': int(c['plan_end'])})
        rets = series(returns, i)
        c2['return_by_year'] = rets
        c2['return_by_account_by_year'] = _apply_account_return_adjustments(c2, rets, years)
        c2.update({
            'inflation_by_year': series(infl['inflation_by_year_matrix'], i),
            'inflation_index_by_year': series(infl['inflation_index_matrix'], i),
            'ss_cola_index_by_year': series(infl['ss_cola_index_matrix'], i),
            'bracket_index_by_year': series(infl['bracket_index_matrix'], i),
            'medical_index_by_year': series(infl['medical_index_matrix'], i),
            'wellness_shock_by_year': {},
            'sampled_inflation_geometric': float(c['inf']),
            'sampled_bracket_inflation_geometric': float(c.get('brk_inf', 0.02) or 0.02),
        })
        scalar_ok[i] = _funding_success(project(c2), floor)
    policy = str(c.get('roth_policy') or 'optimize_terminal_tax').lower()
    s_rate, v_rate = float(scalar_ok.mean()), float(vec_ok.mean())
    return {
        'status': 'run', 'n_paths': n, 'seed': int(seed), 'roth_policy': policy,
        'scalar_success_rate': s_rate, 'vectorized_success_rate': v_rate,
        'signed_gap_pp': (v_rate - s_rate) * 100.0,
        'path_agreement': float(_np.mean(scalar_ok == vec_ok)),
        'standard_error_pp': 100.0 * (max(s_rate * (1 - s_rate), 0.0) / n) ** 0.5,
        'policy_tolerance_demonstrated': policy in MC_PARITY_DEMONSTRATED_POLICIES,
        'note': 'Small-N sampling noise applies; compare to standard_error_pp. Diagnostic only, not a bound.',
    }


def _mc_success_threshold_for_spotcheck(c, base_rows):
    c2 = copy.deepcopy(c)
    c2['mc_scalar_spotcheck_n'] = 0  # avoid recursion
    return monte_carlo(c2, n_sims=1, seed=1, base_rows=base_rows)['success_liquid_floor']


def monte_carlo(c, n_sims=1000, seed=42, base_rows=None, survivor_buckets='__unset__'):
    """Run Monte Carlo on the shared vectorized fast core by default.

    The exact scalar path remains available for validation by setting
    ``mc_engine_mode`` to ``exact_scalar`` or ``scalar``.

    ``base_rows``: the deterministic projection for ``c`` (A4) — pass the
    caller's already-computed rows (e.g. report_compute.run_projection_artifacts,
    which runs the same deterministic engine just before this) to skip a second
    full year-by-year run. Recomputed from ``c`` when omitted.

    ``survivor_buckets`` (optimization refactor Phase 1 items 4-6 performance
    fix): pass an already-built ``_mc_survivor_bucket_flows(c, base_rows)``
    result to skip rebuilding it (2 * n_years project() calls) on this call.
    Needed by any caller that invokes monte_carlo() many times against
    scenario-mutated configs sharing the same underlying mortality/death-
    timing profile -- e.g. sheets_strategy.py's Social Security claim-age
    sweep, which calls this 81x per build and would otherwise pay the
    survivor-bucket cost 81x too (this was a real, measured CI regression:
    ~4,500 extra project() calls per build, causing subprocess timeouts in
    tests/test_all_modules_off_build_functional.py). The sentinel default
    (rather than None) distinguishes "not provided, build it yourself" from
    "explicitly None, there are no survivor buckets" (e.g. a single-person
    household), since both must be handled differently below.
    """
    if str(c.get('mc_engine_mode', 'vectorized_batched')).lower() in {'exact_scalar', 'scalar', 'advanced_exact_scalar'}:
        # ``survivor_buckets`` is deliberately NOT forwarded here:
        # monte_carlo_exact_scalar() has no such parameter because it never
        # builds survivor buckets in the first place - it re-derives survivor
        # economics per path inside its own scalar loop, so there is no
        # 2 * n_years project() prelude for the caller's cache to skip. The
        # cache exists purely to de-duplicate _mc_survivor_bucket_flows()
        # across the vectorized path's repeated sweep calls (see the docstring
        # above). Dropping it on this branch is therefore a no-op, not a lost
        # optimization; and since data_io.py now defaults unset plans to the
        # vectorized engine, this branch is an explicit opt-in / validation
        # oracle rather than the hot path the CI-timeout fix was written for.
        return monte_carlo_exact_scalar(c, n_sims=n_sims, seed=seed, base_rows=base_rows)

    st = SimpleNamespace(base_rows=base_rows, c=c, n_sims=n_sims, seed=seed, survivor_buckets=survivor_buckets)
    _mc_headline_setup(st)
    _mc_headline_batch(st)

    _mc_headline_distributions(st)

    _mc_headline_success_stats(st)

    return _mc_headline_result(st)

# ===== END v8.3_vectorized_monte_carlo_engine.py =====
