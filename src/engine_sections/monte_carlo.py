"""Sections of the vectorized Monte Carlo functions (WI-034, ARC-005).

Contiguous blocks of ``_mc_vectorized_projection`` and ``_mc_vectorized_batch``
moved verbatim into functions whose parameters are the locals the block read
and whose return values are the locals later code reads.  Module-level names
are imported at call time from ``src.planning_engines``.
"""
from __future__ import annotations


def _mc_projection_init_balances(allocation, base_rows, eff, n_sims, n_years, spending_scale, starts):
    """Initial bucket balances and per-path tier arrays for the vectorized recursion."""
    from ..planning_engines import _np
    balances = {
        'pretax': _np.full(n_sims, starts['pretax'], dtype=float),
        'roth': _np.full(n_sims, starts['roth'], dtype=float),
        'taxable': _np.full(n_sims, starts['taxable'], dtype=float),
        'hsa': _np.full(n_sims, starts['hsa'], dtype=float),
        'cash': _np.full(n_sims, starts['cash'], dtype=float),
    }
    out = {k: _np.zeros((n_sims, n_years), dtype=float) for k in ('pretax', 'roth', 'taxable', 'hsa', 'cash', 'liquid', 'total', 'unfunded')}

    # Non-liquid net worth is deterministic/non-market for MC display.  It is
    # held separate so liquidity success remains driven only by spendable assets.
    nonliquid = _np.array([
        float(r.get('total_nw', 0.0) or 0.0)
        - float(r.get('pretax_nw', 0.0) or 0.0)
        - float(r.get('roth_nw', 0.0) or 0.0)
        - float(r.get('trust_nw', 0.0) or 0.0)
        - float(r.get('hsa_nw', 0.0) or 0.0)
    for r in base_rows], dtype=float)

    tax_drag = _np.clip(
        _np.divide(eff['total_tax'], _np.maximum(1.0, eff['gross_income']),
                   out=_np.zeros((n_sims, n_years)), where=_np.maximum(1.0, eff['gross_income']) > 0),
        0.0, 0.55
    )

    # Optimization-refactor "Not done" item, Option B ("Genuinely
    # redirecting withdrawal requests... by tier priority" --
    # documentation/archive/superpowers/plans/2026-08-27-mc-tier-priority-
    # withdrawal-redirection-spec.md): computed BEFORE the recursion below (unlike the
    # pre-existing reporting-only version of this block, which ran after the
    # recursion had already finalized withdrawals/balances) because these
    # per-tier real dollar needs now DRIVE which bucket the cascade below
    # draws from, not just how a completed cut is attributed after the fact.
    # tier_scaled/tier_retained empty (falsy) => every branch below is a
    # provable no-op and this engine is bit-identical to a plan whose rows
    # never carried spend_by_tier (Phase 0 never ran).
    tier_scaled = {tier: det_arr * spending_scale for tier, det_arr in eff['spend_by_tier'].items()}
    if allocation == 'replay':
        # The replayed deterministic draws already include tax on themselves.
        tax_drag = tax_drag * 0.0
        tier_scaled = {}
    return balances, nonliquid, out, tax_drag, tier_scaled


def _mc_projection_real_matrices(c, eff, inf_idx, out, spending_scale, tier_actual_spend, tier_retained, years):
    """Real-dollar spend, tax, cash-flow and gift/charity matrices plus the guardrail band."""
    from ..planning_engines import _np, _roth_discount_rate
    # Phase 1 items 1-3 (optimization refactor): real (plan-start-dollar)
    # spend/tax/cash-flow/gift-charity matrices, using the SAME
    # survivor-blended eff[...] values as the driving recursion above (items
    # 4-6), so these figures are consistent with the withdrawals that
    # actually happened. Deflates by this path's own cumulative inflation
    # index -- consistent with "real spending: deflated to plan-start dollars
    # using each path's sampled inflation index" (plan §7). Purely additive:
    # does not affect unfunded/liquid/total or the success/failure
    # calculation above, which already ran. Skips gracefully if base_rows
    # never carried spend_by_tier.
    # spend_{tier}_real / spend_total_real report each tier's GENUINELY
    # funded spend (tier_actual_spend, tracked during the per-tier cascade
    # above), not the pre-cut/pre-shortfall tier_retained demand -- under
    # Option B a tier can now fall short of its own demand independent of
    # any other tier (e.g. discretionary runs out of taxable/pretax while
    # essential is still fully funded), and that reality should be what
    # these figures show.
    real_total = None
    for tier in tier_retained:
        real = tier_actual_spend[tier] / _np.maximum(1e-9, inf_idx)
        out[f'spend_{tier}_real'] = real
        real_total = real if real_total is None else real_total + real
    if real_total is not None:
        out['spend_total_real'] = real_total
    # Tax/gross-cash-flow: NOT scaled by cut_mult (a spending cut doesn't
    # proportionally reduce tax owed or gross income) but still scaled by
    # this path's own inflation ratio and deflated to real dollars.
    for flow_field, out_key in (('total_tax', 'tax_total_real'), ('gross_cash_flow_yr', 'gross_cash_flow_real')):
        if flow_field in eff:
            out[out_key] = eff[flow_field] * spending_scale / _np.maximum(1e-9, inf_idx)
    gift_charity_total = None
    for flow_field in ('daf_contrib_yr', 'qcd_total_yr', 'gift_total_yr'):
        if flow_field in eff:
            real = eff[flow_field] * spending_scale / _np.maximum(1e-9, inf_idx)
            gift_charity_total = real if gift_charity_total is None else gift_charity_total + real
    if gift_charity_total is not None:
        out['gift_charity_real'] = gift_charity_total

    # Phase 3 (optimization refactor): tax NPV / ELTR (effective lifetime
    # tax rate), per documentation/archive/superpowers/plans/2026-08-27-phase3-tax-npv-eltr-
    # spec.md's Option A. Generalizes the PV-discounting pattern
    # _roth_strategy_metrics already uses to score a single deterministic
    # Roth-conversion candidate (planning_engines.py's _roth_discount_rate)
    # to a per-path figure across the whole MC distribution -- the
    # "state-contingent" half of the phase name, since a single
    # deterministic number cannot be state-contingent. gross_cash_flow_yr
    # was built in Phase 1 explicitly for this ("for ELTR ... reporting")
    # and was unconsumed until now.
    #
    # Uses each path's own NOMINAL (sampled-inflation) dollar trajectory --
    # eff[field] * spending_scale, the same pre-deflation figure
    # tax_total_real/gross_cash_flow_real above divide by inf_idx to reach
    # real dollars -- discounted year-by-year to plan-start PV, matching
    # _roth_strategy_metrics's own convention (it discounts the
    # deterministic engine's nominal total_tax, never a CPI-deflated
    # figure). A PV is already expressed in year-0-equivalent dollars, so
    # no separate real-dollar deflation is layered on top.
    #
    # Reporting-only: reads eff[...]/spending_scale, both already finalized
    # before this point, and never feeds back into unfunded/liquid/total/
    # path_success/success_rate.
    if 'total_tax' in eff and 'gross_cash_flow_yr' in eff:
        discount = _roth_discount_rate(c)
        plan_start = int(c.get('plan_start', years[0] if len(years) else 0))
        discount_factor = 1.0 / _np.power(1.0 + discount, _np.maximum(0, years - plan_start)).reshape(1, -1)
        tax_nominal = eff['total_tax'] * spending_scale
        gross_cash_flow_nominal = eff['gross_cash_flow_yr'] * spending_scale
        tax_npv = _np.sum(tax_nominal * discount_factor, axis=1)
        gross_cash_flow_npv = _np.sum(gross_cash_flow_nominal * discount_factor, axis=1)
        out['tax_npv'] = tax_npv
        out['gross_cash_flow_npv'] = gross_cash_flow_npv
        out['effective_lifetime_tax_rate'] = _np.divide(
            tax_npv, gross_cash_flow_npv,
            out=_np.full_like(tax_npv, _np.nan), where=gross_cash_flow_npv > 1e-6,
        )

    # Phase 5 (optimization refactor): Guyton-Klinger adaptive-guardrail
    # SHADOW simulation, per documentation/archive/superpowers/plans/2026-08-27-phase5-
    # adaptive-guardrails-spec.md's Option A (full 4-rule GK, fixed default
    # bands, both engines together -- per explicit user sign-off, since no
    # prior implementation existed anywhere in this codebase to anchor a
    # formula against, unlike Phases 3-4).
    #
    # This is a genuinely SEPARATE, self-contained alternate spending
    # trajectory -- not a transformation of the plan's own real
    # total_spend path. It answers "what would this household's spending
    # have looked like if it had followed GK's dynamic rule from year 1
    # forward instead of its own planned spend growth," starting from the
    # SAME year-1 nominal spend and the SAME starting liquid balance, then
    # evolving under the rules below using THIS PATH'S OWN realized
    # returns/inflation (the same "reuse real path-specific data" principle
    # _mc_scalar_tier_bucket_reconstruction's growth-factor inference and
    # the tier-priority-redirection income-netting fix both established).
    #
    # Tracks ONE aggregate liquid-portfolio value per path (pretax+roth+
    # taxable+hsa+cash combined) -- GK's rules are defined against total
    # portfolio value, not a per-tax-bucket split, and this is a shadow
    # figure never fed into the real withdrawal cascade, so there is no
    # bucket-level funding-source question here (that is what
    # SPENDING_TIER_BUCKET_POLICY already answers for the REAL cascade).
    #
    # The four rules, in the order Guyton & Klinger (2006) prescribe:
    #   1. Withdrawal Rule: each year's desired withdrawal is last year's,
    #      increased by that year's realized inflation -- UNLESS the prior
    #      year's total portfolio return was negative, in which case the
    #      increase is skipped (frozen at last year's nominal dollar level).
    #   2. Capital Preservation Rule: if the current withdrawal rate
    #      (desired withdrawal / start-of-year portfolio value) exceeds the
    #      INITIAL withdrawal rate (year 1's own ratio) by more than 20%,
    #      cut the withdrawal by 10%. Suspended in the plan's final 15
    #      years (preserving capital matters less once the horizon is
    #      short) -- GK_CAPITAL_PRESERVATION_SUSPENSION_YEARS below.
    #   3. Prosperity Rule: if the current withdrawal rate falls more than
    #      20% BELOW the initial rate, raise the withdrawal by 10%. No
    #      time-based suspension in the standard formulation.
    #   4. Portfolio Management Rule: governs WHICH asset class funds a
    #      given year's withdrawal (e.g. avoid selling equities after a
    #      down year) -- deliberately OUT OF SCOPE here: it never changes
    #      the withdrawal AMOUNT, only its funding source, so it has no
    #      effect on the dollar figure (`guardrail_spend_real`) this shadow
    #      simulation reports.
    # A cut/raise is a permanent step-change to the withdrawal level (the
    # adjusted amount becomes next year's "last year's withdrawal" for
    # Rule 1), not a one-year blip -- matching GK's own definition.
    #
    # Fixed default bands (GK's own commonly-cited parameters; per user
    # sign-off, CSV-schema configurability is an explicit, separately-
    # scoped follow-up, the same "backend ready, no CSV/UI yet" pattern
    # several earlier Phase 2 metrics used):
    _gk_band = 0.20            # +/-20% of the initial withdrawal rate
    return _gk_band


def _mc_projection_tier_cascade(SPENDING_TIER_ESSENTIAL, _gk_band, active, c, eff, flows, inf_idx, inflation_paths, n_sims, n_years, out, returns, spending_scale, starts, tier_scaled, tier_shortfall, use_bucket_mask, years):
    """Spending-tier cascade and guardrail recursion over the projection years."""
    from ..planning_engines import _max_consecutive_true_per_row, _np
    _gk_adjust = 0.10          # 10% cut or raise when a guardrail triggers
    _gk_suspension_years = 15  # capital-preservation rule suspended once
                                # this many years or fewer remain in the plan
    # Item 3.5 (F6, Option 1): floor-ceiling band's own fixed default -- the
    # simpler cousin of GK's 4-rule formula. Each year's "natural" draw is
    # this path's OWN initial withdrawal rate reapplied to the CURRENT
    # portfolio value (not last year's dollar amount grown by inflation, GK's
    # own rule 1); that natural draw is then clamped to stay within +/-10% of
    # the plan's ORIGINAL (undiminished) real spending level, so spending
    # tracks the market but can never drift arbitrarily far from plan.
    _fc_band_pct = 0.10
    _spending_policy = str(c.get('spending_policy', 'fixed_real') or 'fixed_real').strip().lower()
    _guardrail_active = _spending_policy in ('guyton_klinger', 'floor_ceiling_band')
    if 'total_spend' in flows and 'income_funding' in eff and years.size:
        plan_end_gk = int(c.get('plan_end', int(years[-1])))
        total_start_liquid = float(sum(starts.values()))
        # GK's "withdrawal rate" is defined against the PORTFOLIO draw, not
        # total household spending -- most of total_spend is typically
        # covered by guaranteed income (SS/pension/wages), not the
        # portfolio, exactly the same real bug the tier-priority-
        # redirection increment found and fixed for that cascade (using
        # gross spend as the portfolio draw manufactured false shortfalls
        # there too). Anchor to this path's own actual year-1 portfolio
        # draw (the deterministic engine's own already-income-net
        # withdrawal decision, replayed forward and scaled -- the same
        # eff['withdrawals'] figure the tier cascade above reads), not
        # gross total_spend.
        buckets_gk = ('pretax', 'roth', 'taxable', 'hsa', 'cash')
        year1_portfolio_draw = _np.sum(
            [eff['withdrawals'][b][:, 0] for b in buckets_gk], axis=0
        ) * spending_scale[:, 0]
        gk_withdrawal = year1_portfolio_draw.astype(float).copy()
        gk_portfolio = _np.full(n_sims, total_start_liquid, dtype=float)
        gk_iwr = gk_withdrawal / _np.maximum(1e-9, gk_portfolio)
        gk_spend_nominal = _np.zeros((n_sims, n_years))
        gk_cut_years = _np.zeros(n_sims, dtype=int)
        gk_raise_years = _np.zeros(n_sims, dtype=int)
        gk_ever_cut = _np.zeros(n_sims, dtype=bool)
        gk_ever_raise = _np.zeros(n_sims, dtype=bool)
        # Item 3.5: shortfall tracking so a guardrail policy's own success
        # can be defined honestly -- clamping the reported portfolio at 0
        # (below, unchanged from the original shadow) silently absorbed any
        # withdrawal the portfolio couldn't actually cover; this captures
        # that gap BEFORE the clamp, per path per year, so "the guardrail
        # portfolio never ran out" is a real claim, not an artifact of the
        # floor.
        gk_ever_depleted = _np.zeros(n_sims, dtype=bool)
        worst_cut_frac = _np.zeros(n_sims, dtype=float)
        prior_return = None
        for j in range(n_years):
            act_j = active[:, j]
            if _spending_policy == 'floor_ceiling_band':
                natural = gk_iwr * gk_portfolio
                floor_j = year1_portfolio_draw * (1.0 - _fc_band_pct) * inf_idx[:, j]
                ceiling_j = year1_portfolio_draw * (1.0 + _fc_band_pct) * inf_idx[:, j]
                gk_withdrawal = _np.clip(natural, floor_j, ceiling_j)
                do_cut = act_j & (gk_withdrawal < ceiling_j) & (natural < floor_j)
                do_raise = act_j & (natural > ceiling_j)
            else:
                if j > 0:
                    infl_rate_j = inflation_paths['inflation_by_year_matrix'][:, j]
                    freeze = prior_return < 0.0
                    gk_withdrawal = _np.where(freeze, gk_withdrawal, gk_withdrawal * (1.0 + infl_rate_j))
                years_remaining = plan_end_gk - int(years[j])
                cwr = gk_withdrawal / _np.maximum(1e-9, gk_portfolio)
                do_cut = (years_remaining > _gk_suspension_years) & (cwr > gk_iwr * (1.0 + _gk_band))
                do_raise = (~do_cut) & (cwr < gk_iwr * (1.0 - _gk_band))
                gk_withdrawal = _np.where(do_cut, gk_withdrawal * (1.0 - _gk_adjust), gk_withdrawal)
                gk_withdrawal = _np.where(do_raise, gk_withdrawal * (1.0 + _gk_adjust), gk_withdrawal)
            gk_cut_years += (do_cut & act_j).astype(int)
            gk_raise_years += (do_raise & act_j).astype(int)
            gk_ever_cut |= (do_cut & act_j)
            gk_ever_raise |= (do_raise & act_j)
            actual_withdrawal = _np.where(act_j, gk_withdrawal, 0.0)
            # Reported spend is total consumption (portfolio draw + this
            # year's guaranteed income), comparable to spend_total_real --
            # only the PORTFOLIO draw is subject to GK's rules/growth above.
            income_j = _np.where(act_j, eff['income_funding'][:, j] * spending_scale[:, j], 0.0)
            gk_spend_nominal[:, j] = actual_withdrawal + income_j
            shortfall_j = _np.maximum(0.0, actual_withdrawal - gk_portfolio)
            gk_ever_depleted |= (shortfall_j > 1.0) & act_j
            gk_portfolio = _np.maximum(0.0, gk_portfolio - actual_withdrawal)
            gk_portfolio = gk_portfolio * (1.0 + returns[:, j])
            prior_return = returns[:, j]
            # Original (fixed-real, undiminished) baseline draw for THIS
            # year, to size the disclosed "worst modelled cut": year-1's own
            # draw grown by inflation only, mirroring the plan's own real-
            # spending assumption with none of this policy's cuts/raises.
            baseline_j = year1_portfolio_draw * inf_idx[:, j]
            cut_frac_j = _np.where(baseline_j > 1.0, _np.maximum(0.0, 1.0 - actual_withdrawal / _np.maximum(1e-9, baseline_j)), 0.0)
            worst_cut_frac = _np.where(act_j, _np.maximum(worst_cut_frac, cut_frac_j), worst_cut_frac)
        out['guardrail_spend_real'] = gk_spend_nominal / _np.maximum(1e-9, inf_idx)
        out['guardrail_cut_years_count'] = gk_cut_years
        out['guardrail_raise_years_count'] = gk_raise_years
        out['guardrail_ever_cut'] = gk_ever_cut
        out['guardrail_ever_raise'] = gk_ever_raise
        out['guardrail_ever_depleted'] = gk_ever_depleted
        out['guardrail_worst_cut_frac'] = worst_cut_frac
        if _guardrail_active:
            # Item 3.5: promote the shadow from reporting-only to the LIVE
            # policy -- a guardrail-active plan's own success is now defined
            # as "the guardrail-managed portfolio, reacting to this path's
            # realized returns, never failed to cover its own (self-cut)
            # withdrawal" rather than the fixed-real cascade's unfunded_gap.
            # Essential-tier funding (out['essential_fully_funded'] above,
            # computed separately) is deliberately NOT overridden here: GK/
            # floor-ceiling govern discretionary portfolio draw, matching
            # real CFP practice and this codebase's own tier-cut cascade
            # (essential is always protected last), so essential funding
            # probability keeps meaning "funded as asked" even while the
            # headline success rate's meaning changes (see the mandatory
            # relabelling this item also adds in the reporting layer).
            out['guardrail_policy_active'] = _np.ones(n_sims, dtype=bool)
            out['guardrail_success'] = ~gk_ever_depleted

    # Phase 2 (optimization refactor), superseded by Option B: previously
    # this block RECONSTRUCTED essential's shortfall by walking
    # SPENDING_TIER_CUT_ORDER against out['unfunded'] after the fact, since
    # the recursion above only tracked one blended unfunded total. Now that
    # the per-tier cascade above tracks each tier's own genuine shortfall
    # directly (tier_shortfall), essential's real funding failure is read
    # straight from the ledger instead of re-derived.
    if tier_scaled:
        essential_shortfall_nominal = tier_shortfall.get(
            SPENDING_TIER_ESSENTIAL, _np.zeros((n_sims, n_years)))
        out['essential_shortfall_real'] = essential_shortfall_nominal / _np.maximum(1e-9, inf_idx)
        out['essential_fully_funded'] = _np.all(essential_shortfall_nominal <= 1.0, axis=1)

    # Phase 2 (optimization refactor): genuine per-path MC cut statistics --
    # mirrors monte_carlo_exact_scalar's per-path accumulators above, but
    # vectorized across every path at once from the same out['unfunded'] this
    # engine already finalized. "Cut" means any unfunded > $1 (nominal) in
    # that year, matching the essential-shortfall threshold above.
    # Reporting-only: reads out['unfunded'] after the recursion already ran,
    # never feeds back into unfunded/liquid/total/path_success.
    cut_mask = out['unfunded'] > 1.0
    unfunded_real = out['unfunded'] / _np.maximum(1e-9, inf_idx)
    out['any_cut'] = _np.any(cut_mask, axis=1)
    out['cut_years_count'] = _np.sum(cut_mask, axis=1)
    out['max_annual_shortfall_real'] = _np.max(unfunded_real, axis=1)
    out['cumulative_shortfall_real'] = _np.sum(unfunded_real, axis=1)
    out['max_consecutive_cut_years'] = _max_consecutive_true_per_row(cut_mask)
    # Phase 2 (optimization refactor): expose the survivor-period mask
    # (years strictly after this path's own sampled first death) computed
    # above for bucket selection, so callers can report metrics scoped to
    # the survivor period specifically (e.g. "did a shortfall occur only
    # after the first spouse died"). All-False when survivor_buckets/death
    # years were not supplied (single-person household, or a caller that
    # didn't pass them) -- there is no survivor period to report on.
    out['use_bucket_mask'] = use_bucket_mask


def _mc_batch_success_metrics(max_death, projection, success_threshold, years):
    """Path success, failure-year and shortfall statistics for the vectorized batch."""
    from ..planning_engines import _np, _percentiles
    active = _np.array(years, dtype=int).reshape(1, -1) <= max_death.reshape(-1, 1)
    failure_matrix = ((projection['unfunded'] > 1.0) | (projection['liquid'] <= float(success_threshold))) & active
    path_success = ~_np.any(failure_matrix, axis=1)
    # Item 3.5 (F6): a guardrail spending policy (Guyton-Klinger or
    # floor-ceiling band) redefines what "success" means -- the household's
    # OWN spending flexes with portfolio performance, so the fixed-real
    # cascade's unfunded_gap (computed against the UNADJUSTED spend plan)
    # is no longer the right failure definition. Use the guardrail
    # portfolio's own survival instead: never failing to cover its own
    # (self-cut) withdrawal. This is what makes success "survived having
    # cut" rather than "funded as asked" -- the mandatory relabelling this
    # item adds in the reporting layer exists specifically to disclose that
    # meaning change, not to hide it.
    if 'guardrail_success' in projection:
        path_success = projection['guardrail_success']
    any_failure = _np.any(failure_matrix, axis=1)
    first_failure_idx = _np.argmax(failure_matrix, axis=1)
    first_failure_years = [years[int(idx)] if bool(any_failure[i]) else None for i, idx in enumerate(first_failure_idx)]
    # Phase 2 (optimization refactor): "probability essential spending is
    # fully funded" -- the fraction of paths whose essential-tier shortfall
    # (see _mc_vectorized_projection's tail) is zero in every year. None
    # when spend_by_tier was unavailable (e.g. base_rows never went through
    # Phase 0's deterministic engine).
    essential_fully_funded_probability = (
        float(_np.mean(projection['essential_fully_funded']))
        if 'essential_fully_funded' in projection else None
    )
    # Phase 2 (optimization refactor): genuine per-path MC cut statistics --
    # see _mc_vectorized_projection's tail for the per-path arrays; summarized
    # here as a probability plus percentile distributions, mirroring
    # monte_carlo_exact_scalar's equivalent aggregation.
    probability_any_cut = float(_np.mean(projection['any_cut'])) if 'any_cut' in projection else None
    cut_years_pct = _percentiles(projection['cut_years_count'].tolist(), 0.0) if 'cut_years_count' in projection else None
    max_annual_shortfall_real_pct = (
        _percentiles(projection['max_annual_shortfall_real'].tolist(), 0.0) if 'max_annual_shortfall_real' in projection else None
    )
    max_consecutive_cut_years_pct = (
        _percentiles(projection['max_consecutive_cut_years'].tolist(), 0.0) if 'max_consecutive_cut_years' in projection else None
    )
    cumulative_shortfall_real_pct = (
        _percentiles(projection['cumulative_shortfall_real'].tolist(), 0.0) if 'cumulative_shortfall_real' in projection else None
    )
    # Phase 2 (optimization refactor): survivor-period dashboard rows --
    # scope the SAME failure definition path_success/failure_matrix already
    # use (unfunded > $1 OR liquid <= floor, restricted to active years) to
    # specifically the years after each path's own sampled first death
    # (projection['use_bucket_mask'], see _mc_vectorized_projection). Only
    # meaningful for paths whose first death actually falls within the
    # modeled horizon -- reported as two figures so the conditional
    # probability isn't read without its base rate: what fraction of paths
    # have a survivor period to speak of, and among those, what fraction
    # see a funding failure specifically during it. None entirely when no
    # path in this batch has a survivor window (single-person household,
    # or survivor economics unavailable/off).
    survivor_period_applicable_probability = None
    survivor_period_failure_probability = None
    survivor_window = projection.get('use_bucket_mask')
    if survivor_window is not None:
        survivor_active = survivor_window & active
        has_survivor_window = _np.any(survivor_active, axis=1)
        if bool(_np.any(has_survivor_window)):
            survivor_period_applicable_probability = float(_np.mean(has_survivor_window))
            survivor_failure = _np.any(failure_matrix & survivor_active, axis=1)
            survivor_period_failure_probability = float(
                _np.sum(survivor_failure[has_survivor_window]) / _np.sum(has_survivor_window)
            )
    # Phase 2 (optimization refactor): liquidity coverage distribution --
    # liquid retirement assets divided by success_threshold, the SAME flat
    # nominal-dollar reserve floor path_success above already compares
    # min-liquid against (matches monte_carlo_exact_scalar's equivalent
    # metric exactly). {year: percentile-dict} plus each path's own
    # worst-year (minimum) coverage ratio, percentile-ized across paths.
    # None when success_threshold <= 0 (no floor requirement configured).
    # Not masked by each path's own active/death-year window, matching the
    # existing liquid_pct_by_year/terminal_liquid_assets convention.
    liquidity_coverage_pct_by_year = None
    worst_liquidity_coverage_ratio_pct = None
    if success_threshold > 0:
        coverage = projection['liquid'] / success_threshold
        liquidity_coverage_pct_by_year = {yr: _percentiles(coverage[:, i].tolist(), 1.0) for i, yr in enumerate(years)}
        worst_liquidity_coverage_ratio_pct = _percentiles(_np.min(coverage, axis=1).tolist(), 1.0)
    return cumulative_shortfall_real_pct, cut_years_pct, essential_fully_funded_probability, first_failure_years, liquidity_coverage_pct_by_year, max_annual_shortfall_real_pct, max_consecutive_cut_years_pct, path_success, probability_any_cut, survivor_period_applicable_probability, survivor_period_failure_probability, worst_liquidity_coverage_ratio_pct


def _mc_batch_after_tax_metrics(c, h_death, projection, w_death, years):
    """After-tax terminal net worth, tax and guardrail probability statistics."""
    from ..planning_engines import _log_fallback, _np, _percentiles
    # Phase 2 (optimization refactor): after-tax transfer/legacy value
    # distribution. Reuses the SAME estimate_after_tax_terminal_net_worth
    # helper as monte_carlo_exact_scalar and the deterministic Roth-optimizer
    # scoring path, but this engine only tracks aggregate cash/taxable/
    # pretax/roth/hsa buckets (no per-account cost basis), so the terminal
    # dict passed in sets 'trust_nw' to the aggregate taxable balance --
    # exactly the fallback branch estimate_terminal_taxable_deferred_cap_gain_tax
    # already uses "if terminal trust_nw was populated but account-level
    # taxable IDs were not" (this always takes that branch here, since a
    # synthetic dict never has the real taxable_ids keys populated). Each
    # path's own resampled h_death/w_death drives the §1014 step-up
    # classification correctly. A per-path dict copy plus this helper is
    # ~0.02ms (benchmarked directly against this repo's real fixture config,
    # 434 keys) -- negligible even at thousands of paths, unlike the earlier
    # 81x survivor-bucket regression (which was ~4,500 extra FULL project()
    # calls); this adds zero project() calls. Nominal dollars, matching the
    # sibling terminal_total_nw/terminal_liquid_assets convention.
    after_tax_terminal_nw_pct = None
    post_tax_inheritance_pct = None
    probability_legacy_floor_met = None
    try:
        from ..after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
        _n_sims_actual = int(projection['total'].shape[0])
        _after_tax_vals = []
        _post_tax_vals = []
        for _i in range(_n_sims_actual):
            _c_path = {**c, 'h_death_yr': int(h_death[_i]), 'w_death_yr': int(w_death[_i])}
            _terminal_path = {
                'year': years[-1],
                'total_nw': float(projection['total'][_i, -1]),
                'pretax_nw': float(projection['pretax'][_i, -1]),
                'hsa_nw': float(projection['hsa'][_i, -1]),
                'trust_nw': float(projection['taxable'][_i, -1]),
            }
            _m = _estimate_after_tax_terminal_net_worth(_c_path, _terminal_path)
            _after_tax_vals.append(float(_m.get('after_tax_terminal_nw', _terminal_path['total_nw']) or _terminal_path['total_nw']))
            _post_tax_vals.append(float(_m.get('post_tax_inheritance', _terminal_path['total_nw']) or _terminal_path['total_nw']))
        after_tax_terminal_nw_pct = _percentiles(_after_tax_vals, 0.0)
        post_tax_inheritance_pct = _percentiles(_post_tax_vals, 0.0)
        # Optimization-refactor Phase 2: "probability of meeting a user
        # legacy floor" -- see monte_carlo_exact_scalar's matching
        # accumulator comment for the None-when-unconfigured convention.
        _legacy_floor = float(c.get('legacy_floor', 0.0) or 0.0)
        if _legacy_floor > 0 and _post_tax_vals:
            probability_legacy_floor_met = float(_np.mean(_np.asarray(_post_tax_vals) >= _legacy_floor))
    except (TypeError, ValueError, KeyError, ZeroDivisionError) as _exc:
        _log_fallback("monte_carlo.after_tax_percentiles", _exc)
    # Phase 3 (optimization refactor): tax NPV / ELTR distribution across
    # the MC batch -- see _mc_vectorized_projection's tail for the per-path
    # computation. None when the projection didn't carry these fields
    # (e.g. base_rows never went through the deterministic engine's
    # gross_cash_flow_yr wiring), matching the None-when-inapplicable
    # convention every other optional Phase 2/3 metric here uses.
    tax_npv_pct = _percentiles(projection['tax_npv'].tolist(), 0.0) if 'tax_npv' in projection else None
    effective_lifetime_tax_rate_pct = None
    if 'effective_lifetime_tax_rate' in projection:
        _eltr_vals = projection['effective_lifetime_tax_rate']
        _eltr_finite = _eltr_vals[_np.isfinite(_eltr_vals)]
        if _eltr_finite.size:
            effective_lifetime_tax_rate_pct = _percentiles(_eltr_finite.tolist(), 0.0)
    # Phase 5 (optimization refactor): Guyton-Klinger guardrail shadow-
    # simulation summary -- probability a path ever triggered the capital-
    # preservation (cut) or prosperity (raise) rule, mirroring every other
    # probability_* convention here. None when the projection didn't carry
    # these fields (e.g. base_rows never carried total_spend/spend_by_tier).
    probability_guardrail_cut = (
        float(_np.mean(projection['guardrail_ever_cut'])) if 'guardrail_ever_cut' in projection else None
    )
    probability_guardrail_raise = (
        float(_np.mean(projection['guardrail_ever_raise'])) if 'guardrail_ever_raise' in projection else None
    )
    return after_tax_terminal_nw_pct, effective_lifetime_tax_rate_pct, post_tax_inheritance_pct, probability_guardrail_cut, probability_guardrail_raise, probability_legacy_floor_met, tax_npv_pct
