"""Module-level, picklable evaluator for one Social Security claim-age pair.

Extracted verbatim from the ``_safe_project_pair`` closure that used to live
inside ``sheets_strategy.build_sheet10``. A closure captures its enclosing
frame and cannot be pickled, so it could never cross a process boundary --
and Windows spawns (rather than forks) worker processes, so every argument
must pickle. Keeping this as a module-level function taking only plain data
lets the same implementation serve both the serial and the parallel path.
"""
from __future__ import annotations

import contextlib as _contextlib
import io as _io

from ..after_tax import estimate_after_tax_terminal_net_worth as _est_after_tax
from ..planning_engines import (
    LCV_FEASIBILITY_GATE_THRESHOLD,
    compute_baseline_lcv_and_eltr,
    monte_carlo,
    run_scenario as _run_scenario,
    _roth_discount_rate,
)


def evaluate_claim_age_pair(config: dict, spec: dict, settings: dict) -> dict:
    """Score one (h_age, w_age) Social Security claim-age pair.

    ``spec`` carries the per-pair inputs (``h_age``, ``w_age``,
    ``h_mort_age``, ``w_mort_age``, ``skip_mc``); ``settings`` carries the
    sweep-wide constants and pre-computed base figures that used to be
    captured from the enclosing scope. Returns exactly the dict shape the
    former closure returned.
    """
    c = config
    h_age = spec['h_age']
    w_age = spec['w_age']
    h_mort_age = spec.get('h_mort_age')
    w_mort_age = spec.get('w_mort_age')
    skip_mc = spec.get('skip_mc', False)
    SWEEP_MC_SIMS = settings['SWEEP_MC_SIMS']
    SWEEP_MC_SEED = settings['SWEEP_MC_SEED']
    SS_SURVIVOR_WEIGHT = settings['SS_SURVIVOR_WEIGHT']
    base_terminal = settings['base_terminal']
    base_tax = settings['base_tax']
    base_ss = settings['base_ss']
    base_lcv = settings['base_lcv']
    _survivor_buckets_for_sweep = settings['survivor_buckets']

    # h_mort_age/w_mort_age (item 3.8, F11): override the household's
    # configured longevity assumption for this one call. None (the
    # default, used by every claim-age-grid pair) means "leave it as
    # configured" -- only the longevity-refinement pass below ever
    # passes an explicit value.
    #
    # skip_mc (item 3.8): objective_value/score below is entirely
    # deterministic -- it never depends on the Monte Carlo block further
    # down, which exists only to attach feasibility_probability/
    # mc_success_rate/mc_p10_terminal_nw. The longevity-refinement pass
    # only needs objective_value to compare which pair wins under each
    # lifespan assumption, so it sets skip_mc=True to avoid both the MC
    # sampling cost AND a survivor-bucket rebuild under the overridden
    # mortality age (a real, measured problem: an earlier version of
    # this pass that let it fall through to the MC block took several
    # minutes for a single sheet, rebuilding buckets -- 2 * n_years
    # project() calls each -- for 6 extra calls, the exact class of cost
    # the original bucket-reuse optimization above was built to avoid).
    def _mutate(c2):
        c2['h_ss_claim_age'] = int(h_age)
        c2['w_ss_claim_age'] = int(w_age)
        # h_death_yr/w_death_yr (data_io.py) are computed ONCE at parse
        # time as h_dob_yr + h_mort_age and never re-derived -- the
        # engine reads the death year, not h_mort_age itself, so
        # overriding h_mort_age/w_mort_age alone would silently have NO
        # effect on the projection (root-caused directly: an earlier
        # version of this override showed byte-identical objective_value
        # across every longevity variant). plan_end/first_death_yr must
        # move with it too, mirroring data_io.py's own derivation, or a
        # "longer lifespan" variant would be silently truncated at the
        # original (shorter) plan_end.
        if h_mort_age is not None:
            c2['h_mort_age'] = int(h_mort_age)
            c2['h_death_yr'] = int(c2['h_dob_yr']) + int(h_mort_age)
        if w_mort_age is not None and int(c2.get('w_mort_age', 0) or 0) > 0:
            # w_mort_age == 0 is data_io.py's "already dead"/single-member
            # sentinel (w_death_yr == h_dob_yr) -- applying a longevity
            # delta to it would fabricate a spouse who was never modeled.
            c2['w_mort_age'] = int(w_mort_age)
            c2['w_death_yr'] = int(c2['w_dob_yr']) + int(w_mort_age)
        if h_mort_age is not None or w_mort_age is not None:
            c2['plan_end'] = max(c2['h_death_yr'], c2['w_death_yr'])
            c2['first_death_yr'] = min(c2['h_death_yr'], c2['w_death_yr'])
        # Preserve the currently selected Roth policy so the sweep compares
        # SS timing through the same full projection engine without
        # recursively re-optimizing Roth conversions 81 times during
        # workbook generation.
        if str(c2.get('roth_policy', '')).lower() in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize'):
            c2['roth_policy'] = c2.get('roth_optimized_policy') or 'fill_to_bracket'
        c2.pop('plan_result', None)
        c2.pop('roth_strategy_result', None)
    c2, proj_rows = _run_scenario(c, mutate=_mutate)
    terminal_row = proj_rows[-1] if proj_rows else {}
    terminal = float(terminal_row.get('total_nw', 0.0) or 0.0)
    lifetime_tax = sum(float(r.get('total_tax', 0.0) or 0.0) for r in proj_rows)
    lifetime_ss = sum(float(r.get('h_ss', 0.0) or 0.0) + float(r.get('w_ss', 0.0) or 0.0) for r in proj_rows)
    irmaa = sum(float(r.get('irmaa', 0.0) or 0.0) for r in proj_rows)
    # h_alive/w_alive (set from the fixed mortality-age death years) are
    # the correct signal for "years exactly one spouse survives" -- the
    # previous (h_ss==0) != (w_ss==0) proxy also went true whenever one
    # spouse simply hadn't started claiming yet, so it mostly measured
    # claim-timing mismatch, not survivorship, and varied wildly across
    # pairs for a couple whose actual death years never move. h_alive/
    # w_alive are fixed per couple regardless of claim age, as they
    # should be; what genuinely varies by claim-age pair is the SS
    # dollars flowing during that fixed survivor window, captured below.
    survivor_rows = [r for r in proj_rows if bool(r.get('h_alive')) != bool(r.get('w_alive'))]
    survivor_years = len(survivor_rows)
    survivor_period_ss_income = sum(
        float(r.get('h_ss', 0.0) or 0.0) + float(r.get('w_ss', 0.0) or 0.0) for r in survivor_rows
    )
    after_tax_terminal_nw = float(
        _est_after_tax(c2, terminal_row).get('after_tax_terminal_nw', terminal) if proj_rows else terminal
    )
    # Optimization-refactor Phase 4 (Option C, full sign-off): the
    # after-tax-terminal-wealth basis of the score is replaced with an
    # LCV (Lifetime Consumption-and-Transfer Value) score -- PV of
    # lifetime consumption plus PV of after-tax terminal transfer, same
    # discount convention the Roth optimizer's _roth_strategy_metrics
    # already uses for its own PV terms. The survivor-period SS income
    # bonus below is untouched (still nominal, still not PV'd) -- it is
    # a distinct, deliberately-tuned incentive to delay the higher
    # earner's claim for survivor protection, not a wealth term LCV
    # should absorb. See docs/superpowers/plans/2026-08-27-phase4-lcv-
    # feasibility-gate-spec.md.
    _discount = _roth_discount_rate(c2)
    _plan_start = int(c2.get('plan_start', proj_rows[0].get('year', 0) if proj_rows else 0) or 0)
    consumption_pv = sum(
        float(r.get('total_spend', 0.0) or 0.0) / ((1.0 + _discount) ** max(0, int(r.get('year', _plan_start) or _plan_start) - _plan_start))
        for r in proj_rows
    )
    _terminal_year = int(terminal_row.get('year', _plan_start) or _plan_start) if proj_rows else _plan_start
    after_tax_terminal_nw_pv = after_tax_terminal_nw / ((1.0 + _discount) ** max(0, _terminal_year - _plan_start))
    lcv_score = consumption_pv + after_tax_terminal_nw_pv
    score = lcv_score + SS_SURVIVOR_WEIGHT * survivor_period_ss_income
    # This MC run was already made purely informational (mc_success_rate/
    # mc_p10_terminal_nw never fed the score or recommendation -- delaying
    # SS is fundamentally a longevity/market-risk hedge a single
    # deterministic mortality assumption can't show). It now ALSO
    # supplies essential_fully_funded_probability for the Phase 4
    # feasibility gate below, at no extra cost since the call already
    # runs for every pair.
    mc_success_rate = None
    mc_p10_terminal_nw = None
    mc_p5_terminal_nw = None
    feasibility_probability = 0.0
    if not skip_mc:
        try:
            c2['mc_sims'] = SWEEP_MC_SIMS
            c2['mc_sensitivity_sims'] = 1
            # The pre-built _survivor_buckets_for_sweep are keyed to the
            # household's CONFIGURED death-timing assumption -- reusing
            # them under an overridden mortality age would silently
            # score every longevity variant against the same (wrong)
            # survivor window. Let monte_carlo() build its own fresh
            # buckets instead whenever an override is in play; only the
            # claim-age grid (never overridden) gets the cheap reuse.
            _buckets_for_this_call = (
                _survivor_buckets_for_sweep if h_mort_age is None and w_mort_age is None else None
            )
            with _contextlib.redirect_stdout(_io.StringIO()):
                mc_result = monte_carlo(c2, n_sims=SWEEP_MC_SIMS, seed=SWEEP_MC_SEED, survivor_buckets=_buckets_for_this_call)
            mc_success_rate = float(mc_result.get('success_rate', 0.0) or 0.0)
            _mc_terminal_pct = mc_result.get('terminal_total_nw') or {}
            mc_p10_terminal_nw = float(_mc_terminal_pct.get(10, 0.0) or 0.0)
            # #293: worst-case (5th percentile) ending wealth -- same
            # percentile dict P10/median already read, just one more key.
            mc_p5_terminal_nw = float(_mc_terminal_pct.get(5, 0.0) or 0.0)
            feasibility_probability = float(mc_result.get('essential_fully_funded_probability', 0.0) or 0.0)
        except Exception:
            pass
    # #293: LCV (nominal lifetime spend + Post-Tax Inheritance) and NPV
    # of Future Taxes (total tax discounted at c['ret']) -- the same
    # headline figures the Impact page and Executive Summary use,
    # computed here per swept claim-age pair for this table's own
    # Terminal-NW/Lifetime-Tax columns. Deliberately NOT the score basis
    # (lcv_score/objective_value above stay on their existing PV-based
    # ranking convention) -- this only changes what's DISPLAYED. Uses
    # only proj_rows (already computed deterministically), so this stays
    # unconditional regardless of skip_mc.
    _pair_metrics = compute_baseline_lcv_and_eltr(c2, proj_rows)
    lcv = float(_pair_metrics.get('lcv', 0.0) or 0.0)
    npv_future_taxes = float(_pair_metrics.get('npv_future_taxes', 0.0) or 0.0)
    return {
        'h_age': int(h_age), 'w_age': int(w_age), 'terminal_nw': terminal,
        'after_tax_terminal_nw': after_tax_terminal_nw,
        'lifetime_tax': lifetime_tax, 'lifetime_ss': lifetime_ss,
        'irmaa': irmaa, 'survivor_years': survivor_years,
        'survivor_period_ss_income': survivor_period_ss_income, 'objective_value': score,
        'lcv_score': lcv_score,
        'lcv': lcv, 'npv_future_taxes': npv_future_taxes,
        'delta_lcv': lcv - base_lcv,
        'feasibility_probability': feasibility_probability,
        'feasibility_gate_met': feasibility_probability >= LCV_FEASIBILITY_GATE_THRESHOLD,
        'delta_terminal': terminal - base_terminal,
        'delta_tax': lifetime_tax - base_tax,
        'delta_ss': lifetime_ss - base_ss,
        'mc_success_rate': mc_success_rate,
        'mc_p10_terminal_nw': mc_p10_terminal_nw,
        'mc_p5_terminal_nw': mc_p5_terminal_nw,
    }
