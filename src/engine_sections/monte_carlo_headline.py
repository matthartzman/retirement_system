"""Sections of monte_carlo_exact_scalar and monte_carlo (WI-034, ARC-005).

Both functions were linear scripts: configuration, a simulation or batch step,
summary statistics, then one large result dict, with dozens of locals flowing
between the steps.  Each step is now a function taking a shared
``types.SimpleNamespace`` (``st``): it unpacks the locals it reads from ``st``,
runs the original statements unchanged, and writes back the locals that later
steps read.  Module-level names are imported at call time from
``src.planning_engines`` so monkeypatches there still apply and no import cycle
is created.
"""
from __future__ import annotations


def _scalar_mc_setup(st):
    """Configuration, success threshold and accumulator initialisation for the exact scalar Monte Carlo."""
    from ..planning_engines import (
        _portfolio_asset_class_inputs,
        _roth_discount_rate,
        defaultdict,
        ensure_engine_config,
        project,
        random,
    )
    base_rows, c, n_sims, seed = st.base_rows, st.c, st.n_sims, st.seed
    c = ensure_engine_config(c, source='monte_carlo')
    rng = random.Random(seed)
    # A4: the caller (report_compute.run_projection_artifacts) has usually
    # already run this exact deterministic projection once; accept its rows
    # instead of re-running the full year-by-year engine a second time.
    base_rows = project(c) if base_rows is None else base_rows
    base_years = [r['year'] for r in base_rows]
    configured_mu = float(c.get('ret', 0.06))
    configured_sig = float(c.get('mc_sigma', 0.12))
    mu = configured_mu
    sig = configured_sig
    portfolio_diag = {'return_model': 'single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    if bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            _classes, _weights, _means, _cov, _pmu, _psig = _portfolio_asset_class_inputs(c)
            mu, sig = float(_pmu), float(max(1e-6, _psig))
            portfolio_diag = {
                'return_model': 'asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': _classes,
                'asset_weights': {_classes[i]: _weights[i] for i in range(len(_classes))},
            }
        except Exception as exc:
            portfolio_diag['return_model_warning'] = str(exc)
    N = int(c.get('mc_sims', n_sims or 1000))
    # Phase 3 (optimization refactor): tax NPV / ELTR -- see the vectorized
    # engine's matching comment (_mc_vectorized_projection) for the full
    # rationale. Shares _roth_discount_rate(c) with the Roth optimizer's own
    # PV objective so this reporting figure and the plan's actual scoring
    # can never silently disagree about what "the" discount rate is.
    _tax_npv_discount = _roth_discount_rate(c)
    _tax_npv_plan_start = int(c.get('plan_start', base_years[0] if base_years else 0))
    configured_threshold = float(c.get('mc_success_liquid_floor', 0.0) or 0.0)
    # If the CSV leaves the floor at 0, use the plan's own reserve policy.
    # A zero-year reserve policy therefore produces a zero reserve floor.
    if configured_threshold > 0:
        success_threshold = configured_threshold
        success_threshold_source = 'configured success_liquid_floor'
    else:
        buffer_years = max(0.0, float(c.get('near_term_buffer_years', 0.0) or 0.0))
        success_threshold = float(c.get('spend_base', 0.0) or 0.0) * buffer_years
        success_threshold_source = f'{buffer_years:g} years of base spending'

    # Keep sensitivity analysis real but bounded.  The default is now 200 per
    # cell for statistical honesty; explicit small overrides remain honored for
    # unit tests and smoke builds.
    sens_N = int(c.get('mc_sensitivity_sims', 200) or 200)
    sens_N = max(1, min(2000, sens_N))

    # Home equity contingency settings
    he_contingency_enabled = bool(c.get('mc_home_equity_contingency', False))
    he_haircut = float(c.get('mc_home_equity_haircut', 0.20) or 0.20)
    he_lag = int(c.get('mc_home_equity_access_lag_years', 1) or 1)
    gross_home_equity = max(0.0, float(c.get('home_val', 0) or 0) - float(c.get('mortgage_bal', 0) or 0))
    he_reserve = gross_home_equity * (1.0 - he_haircut) if he_contingency_enabled else 0.0

    all_total_by_year = defaultdict(list)
    all_liquid_by_year = defaultdict(list)
    # Phase 1 (optimization refactor): per-path, per-year spend-by-tier,
    # deflated to plan-start (real) dollars using EACH path's own sampled
    # inflation_index_by_year -- not the blanket deterministic assumption.
    # rows already carry spend_by_tier (Phase 0, deterministic_engine.py)
    # in this path's own nominal dollars, since project(c2) above consumes
    # c2['inflation_index_by_year'] directly. Purely additive: does not
    # affect success/failure, terminal values, or any existing output.
    all_spend_by_tier_by_year: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    # Phase 1 items 2-3: same per-path, real-dollar aggregation pattern for
    # tax/gross-cash-flow (tax NPV / ELTR inputs) and realized lifetime
    # gift/charity transfers. gift_total/qcd_total/daf_contrib are the only
    # REALIZED cash/asset-transfer fields (daf_grant_yr and the *_deduction_yr
    # fields are tax/DAF-internal bookkeeping and would double-count if summed
    # here -- see deterministic_engine.py's daf_grant_yr/charitable_deduction_yr
    # comments).
    all_tax_by_year: dict[int, list] = defaultdict(list)
    all_gross_cash_flow_by_year: dict[int, list] = defaultdict(list)
    _GIFT_CHARITY_FIELDS = (('daf_contrib', 'daf_contrib_yr'), ('qcd_total', 'qcd_total_yr'), ('gift_total', 'gift_total_yr'))
    all_gift_charity_by_year: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    all_lifetime_gift_charity_pv: list = []
    # Phase 3 (optimization refactor): tax NPV / ELTR -- per-path PV of
    # total_tax and gross_cash_flow_yr, discounted nominal-dollar (not
    # CPI-real) figures, matching _roth_strategy_metrics's own convention.
    # Reporting-only, same as every accumulator in this block.
    all_tax_npv: list = []
    all_eltr: list = []
    # Phase 5 (optimization refactor): Guyton-Klinger guardrail shadow
    # simulation -- per-year real "what would consumption have looked
    # like under GK's rules" plus per-path cut/raise-ever counts.
    # Reporting-only, same as every accumulator in this block.
    all_guardrail_spend_by_year: dict[int, list] = defaultdict(list)
    all_guardrail_cut_years: list = []
    all_guardrail_raise_years: list = []
    guardrail_ever_cut_count = 0
    guardrail_ever_raise_count = 0
    # Phase 2 (optimization refactor): "probability essential spending is
    # fully funded" -- counts paths whose essential-tier shortfall (the
    # discretionary -> important -> essential cascade against each year's
    # row['unfunded_gap'], same logic as spending_priority_cut_check) is
    # zero in every year. This engine already has row['unfunded_gap'] and
    # row['spend_by_tier'] for free (each path is a full deterministic
    # rerun), so no new engine computation is needed -- just attribution.
    essential_fully_funded_count = 0
    # Phase 2 (optimization refactor): genuine per-path MC cut statistics --
    # "probability of any cut," worst annual cut depth, longest consecutive
    # run of cut years, and cumulative real-dollar shortfall -- computed from
    # each path's own realized row['unfunded_gap'] (the same figure the
    # essential-fully-funded cascade above already reads), not a single
    # hypothetical solved cut_frac (that is spending_priority_cut_check's
    # job, a reporting-layer re-label of ONE scenario). "Cut" here means any
    # unfunded_gap > $1 (nominal, matching the essential-shortfall threshold
    # above) in that year, regardless of which tier the shortfall would
    # ultimately spill into. Reporting-only: never feeds back into
    # unfunded/liquid/total/path_success/success_rate.
    any_cut_count = 0
    cut_years_list: list = []
    max_annual_shortfall_real_list: list = []
    max_consecutive_cut_years_list: list = []
    cumulative_shortfall_real_list: list = []
    # Phase 2 (optimization refactor): liquidity coverage distribution --
    # liquid retirement assets (the same _liquid_value figure the funding-
    # success test already uses) divided by success_threshold, the SAME
    # flat nominal-dollar reserve floor _funding_success already compares
    # min_liquid against -- so this reuses success/failure's own existing
    # floor definition rather than inventing a new one. Undefined (None)
    # when there is no floor requirement (threshold <= 0), since a ratio
    # against zero is meaningless.
    all_liquidity_coverage_by_year: dict[int, list] = defaultdict(list)
    path_min_liquidity_coverage: list = []
    # Phase 2 (optimization refactor): survivor-period dashboard rows --
    # among paths whose sampled first death actually falls within this
    # path's own modeled years (years strictly after first death, up to and
    # including the second death -- mirrors the vectorized engine's
    # use_bucket_mask & active), what fraction see a funding failure (the
    # SAME unfunded>$1-or-liquid<=floor definition _funding_success/
    # path_success already use) specifically during that window. Only
    # meaningful for two-member households -- a single-person household has
    # no survivor to report on (sample_household_death_years defaults its
    # synthetic "spouse" death year to the member's own, degenerating the
    # window to nothing).
    _household_has_two_members = len(c.get('members') or []) >= 2
    survivor_period_paths_with_window = 0
    survivor_period_paths_with_failure = 0
    # Phase 2 (optimization refactor): after-tax transfer/legacy value
    # distribution. Reuses estimate_after_tax_terminal_net_worth (the SAME
    # helper already used for the deterministic Roth-optimizer scoring path,
    # see the estimate_after_tax_terminal_net_worth call a few hundred lines
    # above in this file) against each path's own last_row -- which, unlike
    # the vectorized engine, is already a full deterministic terminal row
    # with real per-account balances, so no aggregate-bucket approximation
    # is needed here. path_c2 (this path's own resampled h_death_yr/
    # w_death_yr) drives the §1014 step-up classification correctly per
    # path. Wrapped defensively: an unusual per-path config/terminal state
    # should reduce this one path's legacy figure to a fallback, not abort
    # the whole MC batch.
    from ..after_tax import estimate_after_tax_terminal_net_worth as _estimate_after_tax_terminal_net_worth
    from ..spending_budget_resolver import SPENDING_TIER_CUT_ORDER
    all_after_tax_terminal_nw: list = []
    all_post_tax_inheritance: list = []
    first5_avgs = []
    terminal_total = []
    terminal_liquid = []
    terminal_success_flags = []
    first_failure_years = []
    liquid_successes = 0
    # #202: "success" against success_threshold also requires keeping the
    # configured reserve floor, so a user testing "what if I need less
    # reserve" sees the success rate jump even though the plan didn't get
    # more resilient -- the bar for success just moved. Track true-ruin
    # success (threshold 0.0) separately so both numbers can be reported.
    no_ruin_successes = 0
    he_contingency_successes = 0
    total_nw_positive = 0
    sampled_returns = []
    sampled_inflation_rates = []
    sampled_wellness_shocks = []
    return_model_counts = defaultdict(int)

    progress_step = max(1, N // 10)
    print(f'Monte Carlo exact scalar paths: 0/{N}', flush=True)
    st.N, st.SPENDING_TIER_CUT_ORDER, st._GIFT_CHARITY_FIELDS, st._estimate_after_tax_terminal_net_worth, st._household_has_two_members, st._tax_npv_discount, st._tax_npv_plan_start, st.all_after_tax_terminal_nw, st.all_eltr, st.all_gift_charity_by_year, st.all_gross_cash_flow_by_year, st.all_guardrail_cut_years, st.all_guardrail_raise_years, st.all_guardrail_spend_by_year, st.all_lifetime_gift_charity_pv, st.all_liquid_by_year, st.all_liquidity_coverage_by_year, st.all_post_tax_inheritance, st.all_spend_by_tier_by_year, st.all_tax_by_year, st.all_tax_npv, st.all_total_by_year, st.any_cut_count, st.base_rows, st.base_years, st.c, st.configured_mu, st.configured_sig, st.cumulative_shortfall_real_list, st.cut_years_list, st.essential_fully_funded_count, st.first5_avgs, st.first_failure_years, st.guardrail_ever_cut_count, st.guardrail_ever_raise_count, st.he_contingency_enabled, st.he_contingency_successes, st.he_haircut, st.he_lag, st.he_reserve, st.liquid_successes, st.max_annual_shortfall_real_list, st.max_consecutive_cut_years_list, st.mu, st.no_ruin_successes, st.path_min_liquidity_coverage, st.portfolio_diag, st.progress_step, st.return_model_counts, st.rng, st.sampled_inflation_rates, st.sampled_returns, st.sampled_wellness_shocks, st.sens_N, st.sig, st.success_threshold, st.success_threshold_source, st.survivor_period_paths_with_failure, st.survivor_period_paths_with_window, st.terminal_liquid, st.terminal_success_flags, st.terminal_total, st.total_nw_positive = N, SPENDING_TIER_CUT_ORDER, _GIFT_CHARITY_FIELDS, _estimate_after_tax_terminal_net_worth, _household_has_two_members, _tax_npv_discount, _tax_npv_plan_start, all_after_tax_terminal_nw, all_eltr, all_gift_charity_by_year, all_gross_cash_flow_by_year, all_guardrail_cut_years, all_guardrail_raise_years, all_guardrail_spend_by_year, all_lifetime_gift_charity_pv, all_liquid_by_year, all_liquidity_coverage_by_year, all_post_tax_inheritance, all_spend_by_tier_by_year, all_tax_by_year, all_tax_npv, all_total_by_year, any_cut_count, base_rows, base_years, c, configured_mu, configured_sig, cumulative_shortfall_real_list, cut_years_list, essential_fully_funded_count, first5_avgs, first_failure_years, guardrail_ever_cut_count, guardrail_ever_raise_count, he_contingency_enabled, he_contingency_successes, he_haircut, he_lag, he_reserve, liquid_successes, max_annual_shortfall_real_list, max_consecutive_cut_years_list, mu, no_ruin_successes, path_min_liquidity_coverage, portfolio_diag, progress_step, return_model_counts, rng, sampled_inflation_rates, sampled_returns, sampled_wellness_shocks, sens_N, sig, success_threshold, success_threshold_source, survivor_period_paths_with_failure, survivor_period_paths_with_window, terminal_liquid, terminal_success_flags, terminal_total, total_nw_positive


def _scalar_mc_run_paths(st):
    """Simulate every path and accumulate per-year, per-path and success statistics."""
    from ..planning_engines import (
        _first_failure_year,
        _funding_success,
        _funding_success_with_home_equity,
        _liquid_value,
        _mc_scalar_guyton_klinger_shadow,
        _mc_scalar_tier_bucket_reconstruction,
        _run_one_mc_path,
    )
    N, SPENDING_TIER_CUT_ORDER, _GIFT_CHARITY_FIELDS, _estimate_after_tax_terminal_net_worth, _household_has_two_members, _tax_npv_discount, _tax_npv_plan_start, all_after_tax_terminal_nw, all_eltr, all_gift_charity_by_year, all_gross_cash_flow_by_year, all_guardrail_cut_years, all_guardrail_raise_years, all_guardrail_spend_by_year, all_lifetime_gift_charity_pv, all_liquid_by_year, all_liquidity_coverage_by_year, all_post_tax_inheritance, all_spend_by_tier_by_year, all_tax_by_year, all_tax_npv, all_total_by_year, any_cut_count, base_years, c, cumulative_shortfall_real_list, cut_years_list, essential_fully_funded_count, first5_avgs, first_failure_years, guardrail_ever_cut_count, guardrail_ever_raise_count, he_contingency_enabled, he_contingency_successes, he_lag, he_reserve, liquid_successes, max_annual_shortfall_real_list, max_consecutive_cut_years_list, mu, no_ruin_successes, path_min_liquidity_coverage, progress_step, return_model_counts, rng, sampled_inflation_rates, sampled_returns, sampled_wellness_shocks, sig, success_threshold, survivor_period_paths_with_failure, survivor_period_paths_with_window, terminal_liquid, terminal_success_flags, terminal_total, total_nw_positive = st.N, st.SPENDING_TIER_CUT_ORDER, st._GIFT_CHARITY_FIELDS, st._estimate_after_tax_terminal_net_worth, st._household_has_two_members, st._tax_npv_discount, st._tax_npv_plan_start, st.all_after_tax_terminal_nw, st.all_eltr, st.all_gift_charity_by_year, st.all_gross_cash_flow_by_year, st.all_guardrail_cut_years, st.all_guardrail_raise_years, st.all_guardrail_spend_by_year, st.all_lifetime_gift_charity_pv, st.all_liquid_by_year, st.all_liquidity_coverage_by_year, st.all_post_tax_inheritance, st.all_spend_by_tier_by_year, st.all_tax_by_year, st.all_tax_npv, st.all_total_by_year, st.any_cut_count, st.base_years, st.c, st.cumulative_shortfall_real_list, st.cut_years_list, st.essential_fully_funded_count, st.first5_avgs, st.first_failure_years, st.guardrail_ever_cut_count, st.guardrail_ever_raise_count, st.he_contingency_enabled, st.he_contingency_successes, st.he_lag, st.he_reserve, st.liquid_successes, st.max_annual_shortfall_real_list, st.max_consecutive_cut_years_list, st.mu, st.no_ruin_successes, st.path_min_liquidity_coverage, st.progress_step, st.return_model_counts, st.rng, st.sampled_inflation_rates, st.sampled_returns, st.sampled_wellness_shocks, st.sig, st.success_threshold, st.survivor_period_paths_with_failure, st.survivor_period_paths_with_window, st.terminal_liquid, st.terminal_success_flags, st.terminal_total, st.total_nw_positive
    for sim_idx in range(N):
        rows, years, returns, return_diag, inflation_paths, path_c2 = _run_one_mc_path(c, rng, mu, sig, use_asset_classes=True)
        return_model_counts[str(return_diag.get('return_model', 'unknown'))] += 1
        by_year = {r['year']: r for r in rows}
        # Optimization-refactor "Not done" item, Option B: genuine per-tier
        # withdrawal redirection, scalar-engine parity. NOTE this is
        # deliberately narrower than the vectorized engine's version: it
        # drives essential_fully_funded_probability/cut-statistics/
        # spend_{tier}_real reporting below, but NOT path_success/
        # success_rate (those stay computed from `rows`' own real
        # unfunded_gap, unchanged) -- redefining the scalar engine's
        # headline success probability around a reconstructed, approximated
        # balance trajectory is a materially bigger and more consequential
        # decision than adding genuine tier-attribution reporting, and was
        # not part of what this increment's product decision covered. See
        # documentation/reference/OPTIMIZATION_REFACTOR_STATUS.md for the open
        # question this leaves: the vectorized engine's headline success
        # rate DOES already reflect genuine redirection (its unfunded/
        # success computation and its tier cascade share one recursion), so
        # the two engines now disagree about whether tier redirection
        # affects overall funding success, not just tier attribution.
        tier_recon = _mc_scalar_tier_bucket_reconstruction(c, rows)
        gk_shadow = _mc_scalar_guyton_klinger_shadow(c, rows, returns, inflation_paths.get('inflation_by_year') or {})
        _path_guardrail_cut_years = 0
        _path_guardrail_raise_years = 0
        _path_guardrail_ever_cut = False
        _path_guardrail_ever_raise = False
        last_row = rows[-1]
        path_returns = [returns[y] for y in years[:5]]
        sampled_returns.extend(returns[y] for y in years)
        sampled_inflation_rates.extend(float(inflation_paths.get('inflation_by_year', {}).get(y, c.get('inf', 0.025)) or 0.0) for y in years)
        sampled_wellness_shocks.extend(float(v or 0.0) for v in inflation_paths.get('wellness_shock_by_year', {}).values())
        first5_avgs.append(sum(path_returns) / max(1, len(path_returns)))

        path_infl_index = inflation_paths.get('inflation_index_by_year') or {}
        _path_lifetime_gift_charity = 0.0
        _path_tax_npv = 0.0
        _path_gross_cash_flow_npv = 0.0
        _path_essential_shortfall_ever = False
        _path_any_cut = False
        _path_cut_years = 0
        _path_max_annual_shortfall_real = 0.0
        _path_cumulative_shortfall_real = 0.0
        _path_consecutive_run = 0
        _path_max_consecutive_cut_years = 0
        _path_min_liquidity_coverage = None
        _path_first_death = int(path_c2.get('first_death_yr', 0) or 0)
        _path_second_death = max(int(path_c2.get('h_death_yr', 0) or 0), int(path_c2.get('w_death_yr', 0) or 0))
        _path_has_survivor_window = False
        _path_survivor_failure = False
        for yr in base_years:
            r = by_year.get(yr) or last_row
            liquid = _liquid_value(r)
            if success_threshold > 0:
                _coverage_yr = liquid / success_threshold
                all_liquidity_coverage_by_year[yr].append(_coverage_yr)
                _path_min_liquidity_coverage = _coverage_yr if _path_min_liquidity_coverage is None else min(_path_min_liquidity_coverage, _coverage_yr)
            if _household_has_two_members and _path_first_death > 0 and _path_first_death < yr <= _path_second_death:
                _path_has_survivor_window = True
                if float(r.get('unfunded_gap', 0.0) or 0.0) > 1.0 or liquid <= success_threshold:
                    _path_survivor_failure = True
            all_total_by_year[yr].append(float(r.get('total_nw', 0) or 0))
            all_liquid_by_year[yr].append(liquid)
            _infl_idx_yr = float(path_infl_index.get(yr, 1.0) or 1.0)
            _gk_yr = gk_shadow.get(yr) if gk_shadow is not None else None
            if _gk_yr is not None:
                all_guardrail_spend_by_year[yr].append(_gk_yr['spend_nominal'] / max(1e-9, _infl_idx_yr))
                if _gk_yr['cut']:
                    _path_guardrail_cut_years += 1
                    _path_guardrail_ever_cut = True
                if _gk_yr['raise']:
                    _path_guardrail_raise_years += 1
                    _path_guardrail_ever_raise = True
            _recon_yr = tier_recon.get(yr) if tier_recon is not None else None
            if _recon_yr is not None:
                # Genuine per-tier funded spend (Option B), not the gross
                # spend_by_tier demand -- mirrors the vectorized engine's
                # spend_{tier}_real, which also reports tier_actual_spend
                # rather than pre-shortfall demand.
                for _tier, _actual in _recon_yr['tier_actual_spend'].items():
                    all_spend_by_tier_by_year[_tier][yr].append(float(_actual) / max(1e-9, _infl_idx_yr))
            else:
                for _tier, _nominal in (r.get('spend_by_tier') or {}).items():
                    all_spend_by_tier_by_year[_tier][yr].append(float(_nominal or 0.0) / max(1e-9, _infl_idx_yr))
            all_tax_by_year[yr].append(float(r.get('total_tax', 0.0) or 0.0) / max(1e-9, _infl_idx_yr))
            all_gross_cash_flow_by_year[yr].append(float(r.get('gross_cash_flow_yr', 0.0) or 0.0) / max(1e-9, _infl_idx_yr))
            # Phase 3 (optimization refactor): tax NPV / ELTR -- nominal
            # (not CPI-real) dollars discounted to plan-start PV, matching
            # _roth_strategy_metrics's own convention.
            _pv_factor_yr = 1.0 / ((1.0 + _tax_npv_discount) ** max(0, int(yr) - _tax_npv_plan_start))
            _path_tax_npv += float(r.get('total_tax', 0.0) or 0.0) * _pv_factor_yr
            _path_gross_cash_flow_npv += float(r.get('gross_cash_flow_yr', 0.0) or 0.0) * _pv_factor_yr
            for _label, _key in _GIFT_CHARITY_FIELDS:
                _real_amt = float(r.get(_key, 0.0) or 0.0) / max(1e-9, _infl_idx_yr)
                all_gift_charity_by_year[_label][yr].append(_real_amt)
                _path_lifetime_gift_charity += _real_amt
            if _recon_yr is not None:
                # Genuine per-tier shortfall (Option B): essential's own
                # tracked shortfall, not a post-hoc SPENDING_TIER_CUT_ORDER
                # reconstruction against one blended unfunded_gap number.
                _unfunded_nominal_yr = float(_recon_yr['unfunded'])
                if float(_recon_yr['tier_shortfall'].get('essential', 0.0)) > 1.0:
                    _path_essential_shortfall_ever = True
            else:
                _unfunded_nominal_yr = float(r.get('unfunded_gap', 0.0) or 0.0)
                _remaining_unfunded = _unfunded_nominal_yr
                _tiers_yr = r.get('spend_by_tier') or {}
                for _tier in SPENDING_TIER_CUT_ORDER:
                    _avail = float(_tiers_yr.get(_tier, 0.0) or 0.0)
                    _taken = min(_avail, _remaining_unfunded)
                    if _tier == 'essential' and _taken > 1.0:
                        _path_essential_shortfall_ever = True
                    _remaining_unfunded -= _taken
            if _unfunded_nominal_yr > 1.0:
                _path_any_cut = True
                _path_cut_years += 1
                _path_consecutive_run += 1
                _path_max_consecutive_cut_years = max(_path_max_consecutive_cut_years, _path_consecutive_run)
            else:
                _path_consecutive_run = 0
            _unfunded_real_yr = _unfunded_nominal_yr / max(1e-9, _infl_idx_yr)
            _path_cumulative_shortfall_real += _unfunded_real_yr
            _path_max_annual_shortfall_real = max(_path_max_annual_shortfall_real, _unfunded_real_yr)
        all_lifetime_gift_charity_pv.append(_path_lifetime_gift_charity)
        all_tax_npv.append(_path_tax_npv)
        if _path_gross_cash_flow_npv > 1e-6:
            all_eltr.append(_path_tax_npv / _path_gross_cash_flow_npv)
        if gk_shadow is not None:
            all_guardrail_cut_years.append(_path_guardrail_cut_years)
            all_guardrail_raise_years.append(_path_guardrail_raise_years)
            guardrail_ever_cut_count += int(_path_guardrail_ever_cut)
            guardrail_ever_raise_count += int(_path_guardrail_ever_raise)
        if not _path_essential_shortfall_ever:
            essential_fully_funded_count += 1
        any_cut_count += int(_path_any_cut)
        cut_years_list.append(_path_cut_years)
        max_annual_shortfall_real_list.append(_path_max_annual_shortfall_real)
        max_consecutive_cut_years_list.append(_path_max_consecutive_cut_years)
        cumulative_shortfall_real_list.append(_path_cumulative_shortfall_real)
        if _path_min_liquidity_coverage is not None:
            path_min_liquidity_coverage.append(_path_min_liquidity_coverage)
        if _path_has_survivor_window:
            survivor_period_paths_with_window += 1
            if _path_survivor_failure:
                survivor_period_paths_with_failure += 1

        final_total = float(last_row.get('total_nw', 0) or 0)
        final_liquid = _liquid_value(last_row)
        try:
            _after_tax_metrics = _estimate_after_tax_terminal_net_worth(path_c2, last_row)
            all_after_tax_terminal_nw.append(float(_after_tax_metrics.get('after_tax_terminal_nw', final_total) or final_total))
            all_post_tax_inheritance.append(float(_after_tax_metrics.get('post_tax_inheritance', final_total) or final_total))
        except Exception:
            all_after_tax_terminal_nw.append(final_total)
            all_post_tax_inheritance.append(final_total)
        path_success = _funding_success(rows, success_threshold)
        path_success_no_ruin = path_success if success_threshold <= 0 else _funding_success(rows, 0.0)
        terminal_total.append(final_total)
        terminal_liquid.append(final_liquid)
        terminal_success_flags.append(path_success)
        first_failure_years.append(_first_failure_year(rows, success_threshold))

        if final_total > 0:
            total_nw_positive += 1
        if path_success:
            liquid_successes += 1
        if path_success_no_ruin:
            no_ruin_successes += 1
        if he_contingency_enabled:
            if _funding_success_with_home_equity(rows, success_threshold, he_reserve, he_lag):
                he_contingency_successes += 1
        if (sim_idx + 1) % progress_step == 0 or (sim_idx + 1) == N:
            print(f'Monte Carlo exact scalar paths: {sim_idx + 1}/{N}', flush=True)
    st.any_cut_count, st.essential_fully_funded_count, st.guardrail_ever_cut_count, st.guardrail_ever_raise_count, st.he_contingency_successes, st.liquid_successes, st.no_ruin_successes, st.survivor_period_paths_with_failure, st.survivor_period_paths_with_window, st.total_nw_positive = any_cut_count, essential_fully_funded_count, guardrail_ever_cut_count, guardrail_ever_raise_count, he_contingency_successes, liquid_successes, no_ruin_successes, survivor_period_paths_with_failure, survivor_period_paths_with_window, total_nw_positive


def _scalar_mc_summarize(st):
    """Percentile summaries, quintiles, sensitivity grid and first-failure distribution."""
    from ..planning_engines import _percentiles, _sensitivity_success_rate, _success_rate_ci, math
    N, all_eltr, all_gift_charity_by_year, all_gross_cash_flow_by_year, all_guardrail_cut_years, all_guardrail_raise_years, all_guardrail_spend_by_year, all_lifetime_gift_charity_pv, all_liquid_by_year, all_spend_by_tier_by_year, all_tax_by_year, all_tax_npv, all_total_by_year, base_years, c, first5_avgs, first_failure_years, guardrail_ever_cut_count, guardrail_ever_raise_count, liquid_successes, no_ruin_successes, seed, sens_N, success_threshold, terminal_liquid, terminal_success_flags, terminal_total = st.N, st.all_eltr, st.all_gift_charity_by_year, st.all_gross_cash_flow_by_year, st.all_guardrail_cut_years, st.all_guardrail_raise_years, st.all_guardrail_spend_by_year, st.all_lifetime_gift_charity_pv, st.all_liquid_by_year, st.all_spend_by_tier_by_year, st.all_tax_by_year, st.all_tax_npv, st.all_total_by_year, st.base_years, st.c, st.first5_avgs, st.first_failure_years, st.guardrail_ever_cut_count, st.guardrail_ever_raise_count, st.liquid_successes, st.no_ruin_successes, st.seed, st.sens_N, st.success_threshold, st.terminal_liquid, st.terminal_success_flags, st.terminal_total
    pct_by_year = {yr: _percentiles(all_total_by_year[yr], 0.0) for yr in base_years}
    liquid_pct_by_year = {yr: _percentiles(all_liquid_by_year[yr], success_threshold) for yr in base_years}
    spend_by_tier_real_pct_by_year = {
        tier: {yr: _percentiles(vals, 0.0) for yr, vals in year_map.items()}
        for tier, year_map in all_spend_by_tier_by_year.items()
    }
    total_tax_real_pct_by_year = {yr: _percentiles(vals, 0.0) for yr, vals in all_tax_by_year.items()}
    gross_cash_flow_real_pct_by_year = {yr: _percentiles(vals, 0.0) for yr, vals in all_gross_cash_flow_by_year.items()}
    gift_charity_real_pct_by_year = {
        label: {yr: _percentiles(vals, 0.0) for yr, vals in year_map.items()}
        for label, year_map in all_gift_charity_by_year.items()
    }
    # Lifetime PV is a per-path scalar (summed across years for that path,
    # THEN percentile-ized) -- percentiles aren't additive across correlated
    # per-year draws, so this must not be derived from the per-year
    # percentiles above. Mirrors how terminal_total_nw is already computed.
    lifetime_gift_charity_pv_real = _percentiles(all_lifetime_gift_charity_pv, 0.0)
    # Phase 3 (optimization refactor): tax NPV / ELTR distribution --
    # mirrors the vectorized engine's matching percentile summary. None for
    # ELTR specifically when every path had zero PV'd gross cash flow (no
    # paths to divide by), the scalar-engine analogue of the vectorized
    # engine's NaN-filtered percentile guard.
    tax_npv_pct = _percentiles(all_tax_npv, 0.0)
    effective_lifetime_tax_rate_pct = _percentiles(all_eltr, 0.0) if all_eltr else None
    # Phase 5 (optimization refactor): Guyton-Klinger guardrail shadow
    # simulation summary -- mirrors the vectorized engine's matching
    # percentile/probability summary.
    guardrail_spend_real_pct_by_year = {yr: _percentiles(vals, 0.0) for yr, vals in all_guardrail_spend_by_year.items()}
    probability_guardrail_cut = float(guardrail_ever_cut_count) / N if all_guardrail_cut_years else None
    probability_guardrail_raise = float(guardrail_ever_raise_count) / N if all_guardrail_raise_years else None

    # Quintiles are sorted by first-5-year returns, but success is now funded-plan
    # success and terminal values are terminal liquid assets. Total terminal net
    # worth remains in mc_data for charts/reporting transparency.
    sorted_sims = sorted(zip(first5_avgs, terminal_total, terminal_liquid, terminal_success_flags))
    q_size = max(1, N // 5)
    qlabels = ['Q1 — Worst 20%', 'Q2', 'Q3 — Middle 20%', 'Q4', 'Q5 — Best 20%']
    quintiles = []
    for q in range(5):
        sl = sorted_sims[q * q_size:(q + 1) * q_size]
        if not sl:
            sl = sorted_sims[-q_size:]
        liquid_ends = sorted(s[2] for s in sl)
        total_ends = sorted(s[1] for s in sl)
        quintiles.append({
            'label': qlabels[q],
            'avg_r5': sum(s[0] for s in sl) / len(sl),
            'p10_end': liquid_ends[int(0.10 * (len(liquid_ends) - 1))],
            'med_end': liquid_ends[len(liquid_ends) // 2],
            'p90_end': liquid_ends[min(len(liquid_ends) - 1, int(0.90 * (len(liquid_ends) - 1)))],
            'avg_end': sum(liquid_ends) / len(liquid_ends),
            'med_total_nw': total_ends[len(total_ends) // 2],
            'success': sum(1 for s in sl if s[3]) / len(sl),
        })

    mus_grid = [0.04, 0.05, 0.06, 0.07, 0.08]
    sigs_grid = [0.08, 0.10, 0.12, 0.14, 0.16]
    sensitivity = {}
    total_cells = max(1, len(mus_grid) * len(sigs_grid))
    done_cells = 0
    print(f'Monte Carlo sensitivity grid: 0/{total_cells} cells × {sens_N} paths', flush=True)
    for i, mu_s in enumerate(mus_grid):
        for j, sig_s in enumerate(sigs_grid):
            cell_seed = seed + 10_000 + i * 100 + j
            sensitivity[(mu_s, sig_s)] = _sensitivity_success_rate(
                c, mu_s, sig_s, sens_N, cell_seed, success_threshold
            )
            done_cells += 1
            print(f'Monte Carlo sensitivity grid: {done_cells}/{total_cells} cells × {sens_N} paths', flush=True)

    failures = [y for y in first_failure_years if y is not None]
    first_failure_distribution = {}
    for y in failures:
        first_failure_distribution[y] = first_failure_distribution.get(y, 0) + 1

    success_rate = liquid_successes / max(1, N)
    success_ci_low, success_ci_high = _success_rate_ci(liquid_successes, N)
    success_se = math.sqrt(max(0.0, success_rate * (1.0 - success_rate) / max(1, N)))
    success_rate_no_ruin = no_ruin_successes / max(1, N)
    success_no_ruin_ci_low, success_no_ruin_ci_high = _success_rate_ci(no_ruin_successes, N)
    st.effective_lifetime_tax_rate_pct, st.first_failure_distribution, st.gift_charity_real_pct_by_year, st.gross_cash_flow_real_pct_by_year, st.guardrail_spend_real_pct_by_year, st.lifetime_gift_charity_pv_real, st.liquid_pct_by_year, st.mus_grid, st.pct_by_year, st.probability_guardrail_cut, st.probability_guardrail_raise, st.quintiles, st.sensitivity, st.sigs_grid, st.spend_by_tier_real_pct_by_year, st.success_ci_high, st.success_ci_low, st.success_no_ruin_ci_high, st.success_no_ruin_ci_low, st.success_rate, st.success_rate_no_ruin, st.success_se, st.tax_npv_pct, st.total_tax_real_pct_by_year = effective_lifetime_tax_rate_pct, first_failure_distribution, gift_charity_real_pct_by_year, gross_cash_flow_real_pct_by_year, guardrail_spend_real_pct_by_year, lifetime_gift_charity_pv_real, liquid_pct_by_year, mus_grid, pct_by_year, probability_guardrail_cut, probability_guardrail_raise, quintiles, sensitivity, sigs_grid, spend_by_tier_real_pct_by_year, success_ci_high, success_ci_low, success_no_ruin_ci_high, success_no_ruin_ci_low, success_rate, success_rate_no_ruin, success_se, tax_npv_pct, total_tax_real_pct_by_year


def _scalar_mc_result(st):
    """Assemble the exact scalar Monte Carlo result dictionary."""
    from ..planning_engines import _percentiles, math
    N, all_after_tax_terminal_nw, all_liquidity_coverage_by_year, all_post_tax_inheritance, any_cut_count, base_rows, base_years, c, configured_mu, configured_sig, cumulative_shortfall_real_list, cut_years_list, effective_lifetime_tax_rate_pct, essential_fully_funded_count, first_failure_distribution, gift_charity_real_pct_by_year, gross_cash_flow_real_pct_by_year, guardrail_spend_real_pct_by_year, he_contingency_enabled, he_contingency_successes, he_haircut, he_reserve, lifetime_gift_charity_pv_real, liquid_pct_by_year, max_annual_shortfall_real_list, max_consecutive_cut_years_list, mu, mus_grid, path_min_liquidity_coverage, pct_by_year, portfolio_diag, probability_guardrail_cut, probability_guardrail_raise, quintiles, return_model_counts, sampled_inflation_rates, sampled_returns, sampled_wellness_shocks, seed, sens_N, sensitivity, sig, sigs_grid, spend_by_tier_real_pct_by_year, success_ci_high, success_ci_low, success_no_ruin_ci_high, success_no_ruin_ci_low, success_rate, success_rate_no_ruin, success_se, success_threshold, success_threshold_source, survivor_period_paths_with_failure, survivor_period_paths_with_window, tax_npv_pct, terminal_liquid, terminal_total, total_nw_positive, total_tax_real_pct_by_year = st.N, st.all_after_tax_terminal_nw, st.all_liquidity_coverage_by_year, st.all_post_tax_inheritance, st.any_cut_count, st.base_rows, st.base_years, st.c, st.configured_mu, st.configured_sig, st.cumulative_shortfall_real_list, st.cut_years_list, st.effective_lifetime_tax_rate_pct, st.essential_fully_funded_count, st.first_failure_distribution, st.gift_charity_real_pct_by_year, st.gross_cash_flow_real_pct_by_year, st.guardrail_spend_real_pct_by_year, st.he_contingency_enabled, st.he_contingency_successes, st.he_haircut, st.he_reserve, st.lifetime_gift_charity_pv_real, st.liquid_pct_by_year, st.max_annual_shortfall_real_list, st.max_consecutive_cut_years_list, st.mu, st.mus_grid, st.path_min_liquidity_coverage, st.pct_by_year, st.portfolio_diag, st.probability_guardrail_cut, st.probability_guardrail_raise, st.quintiles, st.return_model_counts, st.sampled_inflation_rates, st.sampled_returns, st.sampled_wellness_shocks, st.seed, st.sens_N, st.sensitivity, st.sig, st.sigs_grid, st.spend_by_tier_real_pct_by_year, st.success_ci_high, st.success_ci_low, st.success_no_ruin_ci_high, st.success_no_ruin_ci_low, st.success_rate, st.success_rate_no_ruin, st.success_se, st.success_threshold, st.success_threshold_source, st.survivor_period_paths_with_failure, st.survivor_period_paths_with_window, st.tax_npv_pct, st.terminal_liquid, st.terminal_total, st.total_nw_positive, st.total_tax_real_pct_by_year
    return {
        'pct_by_year': pct_by_year,                         # total net worth distribution
        'liquid_pct_by_year': liquid_pct_by_year,           # liquid funding distribution
        # Phase 1 (optimization refactor): {tier: {year: percentile-dict}},
        # real (plan-start-dollar) spending by SPENDING_TIERS tier, deflated
        # per path by that path's own sampled inflation. Empty dict if rows
        # never carried spend_by_tier (e.g. a fixture calling this without
        # going through project()/deterministic_engine.py).
        'spend_by_tier_real_pct_by_year': spend_by_tier_real_pct_by_year,
        # Phase 1 items 2-3: real (plan-start-dollar) tax, gross-external-
        # cash-flow, and realized lifetime gift/charity distributions, each
        # deflated per path by that path's own sampled inflation. Purely
        # additive new keys.
        'total_tax_real_pct_by_year': total_tax_real_pct_by_year,
        'gross_cash_flow_real_pct_by_year': gross_cash_flow_real_pct_by_year,
        'gift_charity_real_pct_by_year': gift_charity_real_pct_by_year,
        'lifetime_gift_charity_pv_real': lifetime_gift_charity_pv_real,
        'tax_npv_pct': tax_npv_pct,
        'effective_lifetime_tax_rate_pct': effective_lifetime_tax_rate_pct,
        'guardrail_spend_real_pct_by_year': guardrail_spend_real_pct_by_year,
        'probability_guardrail_cut': probability_guardrail_cut,
        'probability_guardrail_raise': probability_guardrail_raise,
        'quintiles': quintiles,
        'sensitivity': sensitivity,
        'sensitivity_sims': sens_N,
        'years': base_years,
        'mus': mus_grid,
        'sigs': sigs_grid,
        'mu': mu,
        'sig': sig,
        'configured_mu': configured_mu,
        'configured_sig': configured_sig,
        'portfolio_return_model': max(return_model_counts, key=return_model_counts.get) if return_model_counts else portfolio_diag.get('return_model'),
        'portfolio_return_diagnostics': portfolio_diag,
        'sampled_mean_return': (sum(sampled_returns) / len(sampled_returns)) if sampled_returns else mu,
        'sampled_geometric_return': (
            math.exp(sum(math.log1p(max(-0.999999, r)) for r in sampled_returns) / len(sampled_returns)) - 1
            if sampled_returns else mu
        ),
        'sampled_mean_inflation': (sum(sampled_inflation_rates) / len(sampled_inflation_rates)) if sampled_inflation_rates else float(c.get('inf', 0.025) or 0.025),
        'sampled_wellness_shock_count': len(sampled_wellness_shocks),
        'sampled_wellness_shock_mean_cost': (sum(sampled_wellness_shocks) / len(sampled_wellness_shocks)) if sampled_wellness_shocks else 0.0,
        'return_recentered': bool(c.get('mc_recenter_regime_returns', True)),
        'n_sims': N,
        'seed': seed,
        'success_definition': 'No unfunded annual spending gap and liquid retirement assets remain above configured floor in every projected year.',
        'success_liquid_floor': success_threshold,
        'success_liquid_floor_source': success_threshold_source,
        'success_rate': success_rate,
        'success_rate_ci_low': success_ci_low,
        'success_rate_ci_high': success_ci_high,
        'success_rate_standard_error': success_se,
        # #202: a second, always-present success rate that only asks "did the
        # plan run out of money" -- independent of the configured reserve
        # floor above, so lowering/raising the reserve requirement changes
        # this number only if it actually changes withdrawal behavior, not
        # because the definition of success moved.
        'success_definition_no_ruin': 'No unfunded annual spending gap in any projected year (ignores the reserve-floor buffer required by success_liquid_floor above).',
        'success_rate_no_ruin': success_rate_no_ruin,
        'success_rate_no_ruin_ci_low': success_no_ruin_ci_low,
        'success_rate_no_ruin_ci_high': success_no_ruin_ci_high,
        'liquid_success_rate': success_rate,
        'total_nw_success_rate': total_nw_positive / max(1, N),
        # Optimization-refactor Phase 2: fraction of paths whose essential-
        # tier spending was never left unfunded in any year.
        'essential_fully_funded_probability': essential_fully_funded_count / max(1, N),
        # Optimization-refactor Phase 2: genuine per-path MC cut statistics --
        # see the accumulator comment above the sim loop for definitions.
        # Distributions are percentile-ized across paths (one scalar per
        # path, summarized the same way terminal_total_nw is).
        'probability_any_cut': any_cut_count / max(1, N),
        'cut_years_pct': _percentiles(cut_years_list, 0.0),
        'max_annual_shortfall_real_pct': _percentiles(max_annual_shortfall_real_list, 0.0),
        'max_consecutive_cut_years_pct': _percentiles(max_consecutive_cut_years_list, 0.0),
        'cumulative_shortfall_real_pct': _percentiles(cumulative_shortfall_real_list, 0.0),
        # Optimization-refactor Phase 2: liquidity coverage distribution --
        # {year: percentile-dict} of liquid / success_threshold (the same
        # reserve floor _funding_success already compares against), plus
        # each path's own worst-year (minimum) coverage ratio, percentile-
        # ized across paths. None when success_threshold <= 0 (no floor
        # requirement configured, so the ratio is undefined).
        'liquidity_coverage_pct_by_year': (
            {yr: _percentiles(vals, 1.0) for yr, vals in all_liquidity_coverage_by_year.items()}
            if success_threshold > 0 else None
        ),
        'worst_liquidity_coverage_ratio_pct': (
            _percentiles(path_min_liquidity_coverage, 1.0) if success_threshold > 0 else None
        ),
        # Optimization-refactor Phase 2: after-tax transfer/legacy value
        # distribution -- same estimate_after_tax_terminal_net_worth used by
        # the deterministic Roth-optimizer scoring path, applied per MC path
        # against that path's own terminal row and resampled death years.
        # Nominal dollars, matching the sibling terminal_total_nw/
        # terminal_liquid_assets convention (neither of those deflates
        # either).
        'after_tax_terminal_nw_pct': _percentiles(all_after_tax_terminal_nw, 0.0),
        'post_tax_inheritance_pct': _percentiles(all_post_tax_inheritance, 0.0),
        # Optimization-refactor Phase 2: "probability of meeting a user
        # legacy floor" -- fraction of paths whose post-tax inheritance
        # (the same after-tax bequest figure above, per path rather than
        # percentile-ized) meets or exceeds a household-configured
        # legacy_floor dollar target. No CSV/UI wiring exists for
        # legacy_floor yet (a future product decision, not a code
        # blocker) -- this reads it defensively via c.get() so it's
        # already correct once that field exists, and reports None (not a
        # misleading 0.0 or 1.0) when no floor is configured, matching the
        # None-when-inapplicable convention used elsewhere in this file
        # (liquidity_coverage_pct_by_year, survivor_period_*).
        'probability_legacy_floor_met': (
            sum(1 for v in all_post_tax_inheritance if v >= float(c.get('legacy_floor', 0.0) or 0.0)) / max(1, N)
            if float(c.get('legacy_floor', 0.0) or 0.0) > 0 else None
        ),
        # Optimization-refactor Phase 2: survivor-period dashboard rows --
        # see the accumulator comment above the sim loop for definitions.
        'survivor_period_applicable_probability': (
            survivor_period_paths_with_window / max(1, N) if survivor_period_paths_with_window > 0 else None
        ),
        'survivor_period_failure_probability': (
            survivor_period_paths_with_failure / survivor_period_paths_with_window if survivor_period_paths_with_window > 0 else None
        ),
        'failure_rate': 1.0 - success_rate,
        'home_equity_contingency_enabled': he_contingency_enabled,
        'home_equity_contingency_reserve': he_reserve,
        'home_equity_contingency_haircut': he_haircut,
        'success_rate_with_home_equity': he_contingency_successes / max(1, N) if he_contingency_enabled else None,
        'deterministic_projection_label': 'No-volatility deterministic reference path; Monte Carlo median is the probabilistic planning number.',
        'first_failure_distribution': first_failure_distribution,
        'terminal_total_nw': _percentiles(terminal_total, 0.0),
        'terminal_liquid_assets': _percentiles(terminal_liquid, success_threshold),
        'nw0': base_rows[0]['pretax_nw'] + base_rows[0]['roth_nw'] + base_rows[0]['trust_nw'] + base_rows[0]['hsa_nw'],
        'invest0': base_rows[0]['pretax_nw'] + base_rows[0]['roth_nw'] + base_rows[0]['trust_nw'] + base_rows[0]['hsa_nw'],
        'net_draws': [],
        'survival_curve': [
            {'year': yr, 'pct_funded': liquid_pct_by_year[yr]['success'] * 100}
            for yr in base_years
        ],
        'mc_engine': 'exact_scalar',
        'mc_engine_label': 'Exact scalar Monte Carlo validation mode',
        'mc_approximation_status': 'EXACT',
        'model_risk_rating': 'EXACT_SCALAR_MC',
    }


def _mc_headline_setup(st):
    """Configuration, success threshold and survivor-bucket setup for the vectorized headline run."""
    from ..planning_engines import (
        _mc_survivor_bucket_flows,
        _portfolio_asset_class_inputs,
        ensure_engine_config,
        project,
    )
    base_rows, c, n_sims, survivor_buckets = st.base_rows, st.c, st.n_sims, st.survivor_buckets
    c = ensure_engine_config(c, source='monte_carlo')
    base_rows = project(c) if base_rows is None else base_rows
    base_years = [int(r['year']) for r in base_rows]
    base_plan_shortfall = any(float(r.get('unfunded_gap', 0) or 0) > 1.0 for r in base_rows)
    configured_mu = float(c.get('ret', 0.06))
    configured_sig = float(c.get('mc_sigma', 0.12))
    mu = configured_mu
    sig = configured_sig
    portfolio_diag = {'return_model': 'vectorized_single_blended_mu_sigma', 'portfolio_expected_return': mu, 'portfolio_sigma': sig}
    if bool(c.get('mc_use_asset_class_covariance', True)):
        try:
            _classes, _weights, _means, _cov, _pmu, _psig = _portfolio_asset_class_inputs(c)
            mu, sig = float(_pmu), float(max(1e-6, _psig))
            portfolio_diag = {
                'return_model': 'vectorized_asset_class_covariance',
                'portfolio_expected_return': mu,
                'portfolio_sigma': sig,
                'asset_classes': _classes,
                'asset_weights': {_classes[i]: _weights[i] for i in range(len(_classes))},
            }
        except Exception as exc:
            portfolio_diag['return_model_warning'] = str(exc)

    N = int(c.get('mc_sims', n_sims or 1000))
    configured_threshold = float(c.get('mc_success_liquid_floor', 0.0) or 0.0)
    if configured_threshold > 0:
        success_threshold = configured_threshold
        success_threshold_source = 'configured success_liquid_floor'
    else:
        buffer_years = max(0.0, float(c.get('near_term_buffer_years', 0.0) or 0.0))
        success_threshold = float(c.get('spend_base', 0.0) or 0.0) * buffer_years
        success_threshold_source = f'{buffer_years:g} years of base spending'

    sens_N = int(c.get('mc_sensitivity_sims', 200) or 200)
    sens_N = max(1, min(2000, sens_N))

    # Home equity contingency settings (vectorized engine uses terminal-liquid approximation)
    he_contingency_enabled_v = bool(c.get('mc_home_equity_contingency', False))
    he_haircut_v = float(c.get('mc_home_equity_haircut', 0.20) or 0.20)
    gross_home_equity_v = max(0.0, float(c.get('home_val', 0) or 0) - float(c.get('mortgage_bal', 0) or 0))
    he_reserve_v = gross_home_equity_v * (1.0 - he_haircut_v) if he_contingency_enabled_v else 0.0

    # Phase 1 items 4-6 (optimization refactor): build the survivor-period
    # bucket trajectories ONCE for this whole monte_carlo() call and thread
    # the same object through the main batch, every sensitivity-grid cell,
    # and the required-cut/sustainable-spending bisections below -- rebuilding
    # it per call would multiply its cost (2 * n_years project() calls) by
    # every one of those ~26-90 invocations. mc_vectorized_survivor_economics
    # defaults True (matches this codebase's other mc_* toggles, which all
    # default on); kept only as an emergency kill switch, not a rollout gate.
    if survivor_buckets == '__unset__':
        survivor_buckets = (
            _mc_survivor_bucket_flows(c, base_rows)
            if bool(c.get('mc_vectorized_survivor_economics', True)) else None
        )
    st.N, st.base_plan_shortfall, st.base_rows, st.base_years, st.c, st.configured_mu, st.configured_sig, st.he_contingency_enabled_v, st.he_haircut_v, st.he_reserve_v, st.mu, st.portfolio_diag, st.sens_N, st.sig, st.success_threshold, st.success_threshold_source, st.survivor_buckets = N, base_plan_shortfall, base_rows, base_years, c, configured_mu, configured_sig, he_contingency_enabled_v, he_haircut_v, he_reserve_v, mu, portfolio_diag, sens_N, sig, success_threshold, success_threshold_source, survivor_buckets


def _mc_headline_batch(st):
    """Run the vectorized batch and derive path-success arrays."""
    from ..planning_engines import _mc_vectorized_batch, _np
    N, base_rows, base_years, c, mu, seed, sig, success_threshold, survivor_buckets = st.N, st.base_rows, st.base_years, st.c, st.mu, st.seed, st.sig, st.success_threshold, st.survivor_buckets
    print(f'Monte Carlo vectorized batch: sampling {max(1, N)} paths', flush=True)
    batch = _mc_vectorized_batch(c, base_rows, max(1, N), int(seed), mu, sig, success_threshold, use_asset_classes=True, survivor_buckets=survivor_buckets, allocation='replay', tier_shadow=True)
    print('Monte Carlo vectorized batch: main batch complete', flush=True)
    proj = batch['projection']
    returns = batch['returns']
    infl = batch['inflation_paths']
    path_success = _np.array(batch['path_success'], dtype=bool)
    # #202: a second, threshold-independent success flag ("did it run out of
    # money at all") computed from the same already-simulated liquid/unfunded
    # arrays -- no need to re-run the batch simulation just to change the
    # reserve-floor threshold to 0.0.
    _no_ruin_active = _np.array(base_years, dtype=int).reshape(1, -1) <= batch['max_death_years'].reshape(-1, 1)
    _no_ruin_failure = ((proj['unfunded'] > 1.0) | (proj['liquid'] <= 0.0)) & _no_ruin_active
    path_success_no_ruin = ~_np.any(_no_ruin_failure, axis=1)
    st.batch, st.infl, st.path_success, st.path_success_no_ruin, st.proj, st.returns = batch, infl, path_success, path_success_no_ruin, proj, returns


def _mc_headline_distributions(st):
    """Per-year percentiles, quintiles, sensitivity grid and first-failure distribution."""
    from ..planning_engines import _mc_vectorized_sensitivity_success_rate, _np, _percentiles
    N, base_rows, base_years, batch, c, path_success, proj, returns, seed, sens_N, success_threshold, survivor_buckets = st.N, st.base_rows, st.base_years, st.batch, st.c, st.path_success, st.proj, st.returns, st.seed, st.sens_N, st.success_threshold, st.survivor_buckets
    pct_by_year = {yr: _percentiles(proj['total'][:, i].tolist(), 0.0) for i, yr in enumerate(base_years)}
    liquid_pct_by_year = {yr: _percentiles(proj['liquid'][:, i].tolist(), success_threshold) for i, yr in enumerate(base_years)}

    terminal_total = proj['total'][:, -1]
    terminal_liquid = proj['liquid'][:, -1]
    first5_avgs = _np.mean(returns[:, :max(1, min(5, returns.shape[1]))], axis=1)
    sorted_idx = _np.argsort(first5_avgs)
    q_size = max(1, int(N) // 5)
    qlabels = ['Q1 — Worst 20%', 'Q2', 'Q3 — Middle 20%', 'Q4', 'Q5 — Best 20%']
    quintiles = []
    for q in range(5):
        idx = sorted_idx[q * q_size:(q + 1) * q_size]
        if idx.size == 0:
            idx = sorted_idx[-q_size:]
        liquid_ends = _np.sort(terminal_liquid[idx])
        total_ends = _np.sort(terminal_total[idx])
        quintiles.append({
            'label': qlabels[q],
            'avg_r5': float(_np.mean(first5_avgs[idx])),
            'p10_end': float(_np.percentile(liquid_ends, 10)),
            'med_end': float(_np.percentile(liquid_ends, 50)),
            'p90_end': float(_np.percentile(liquid_ends, 90)),
            'avg_end': float(_np.mean(liquid_ends)),
            'med_total_nw': float(_np.percentile(total_ends, 50)),
            'success': float(_np.mean(path_success[idx])),
        })

    mus_grid = [0.04, 0.05, 0.06, 0.07, 0.08]
    sigs_grid = [0.08, 0.10, 0.12, 0.14, 0.16]
    sensitivity = {}
    total_cells = max(1, len(mus_grid) * len(sigs_grid))
    done_cells = 0
    print(f'Monte Carlo sensitivity grid: 0/{total_cells} cells × {sens_N} paths', flush=True)
    for i, mu_s in enumerate(mus_grid):
        for j, sig_s in enumerate(sigs_grid):
            cell_seed = int(seed) + 10_000 + i * 100 + j
            sensitivity[(mu_s, sig_s)] = _mc_vectorized_sensitivity_success_rate(
                c, base_rows, mu_s, sig_s, sens_N, cell_seed, success_threshold, survivor_buckets=survivor_buckets
            )
            done_cells += 1
            print(f'Monte Carlo sensitivity grid: {done_cells}/{total_cells} cells × {sens_N} paths', flush=True)

    failures = [y for y in batch['first_failure_years'] if y is not None]
    first_failure_distribution = {}
    for y in failures:
        first_failure_distribution[y] = first_failure_distribution.get(y, 0) + 1
    st.first_failure_distribution, st.liquid_pct_by_year, st.mus_grid, st.pct_by_year, st.quintiles, st.sensitivity, st.sigs_grid, st.terminal_liquid, st.terminal_total = first_failure_distribution, liquid_pct_by_year, mus_grid, pct_by_year, quintiles, sensitivity, sigs_grid, terminal_liquid, terminal_total


def _mc_headline_success_stats(st):
    """Required-cut and sustainable-spending solves plus success-rate statistics."""
    from ..planning_engines import (
        _mc_required_cut_distribution,
        _np,
        _success_rate_ci,
        math,
        sustainable_spending_solve,
    )
    N, base_rows, batch, c, he_contingency_enabled_v, he_reserve_v, infl, path_success, path_success_no_ruin, portfolio_diag, returns, success_threshold, terminal_liquid = st.N, st.base_rows, st.batch, st.c, st.he_contingency_enabled_v, st.he_reserve_v, st.infl, st.path_success, st.path_success_no_ruin, st.portfolio_diag, st.returns, st.success_threshold, st.terminal_liquid
    required_cut_distribution = _mc_required_cut_distribution(c, base_rows, batch, success_threshold)
    sustainable_spending = sustainable_spending_solve(c, base_rows, batch, success_threshold)

    liquid_successes = int(_np.sum(path_success))
    success_rate = float(liquid_successes / max(1, N))
    success_ci_low, success_ci_high = _success_rate_ci(liquid_successes, N)
    success_se = math.sqrt(max(0.0, success_rate * (1.0 - success_rate) / max(1, N)))
    no_ruin_successes = int(_np.sum(path_success_no_ruin))
    success_rate_no_ruin = float(no_ruin_successes / max(1, N))
    success_no_ruin_ci_low, success_no_ruin_ci_high = _success_rate_ci(no_ruin_successes, N)
    # Vectorized approximation: contingency counts paths where terminal_liquid + reserve > threshold
    if he_contingency_enabled_v and he_reserve_v > 0:
        he_contingency_success_v = float(_np.mean(
            path_success | (terminal_liquid + he_reserve_v > success_threshold)
        ))
    else:
        he_contingency_success_v = None
    sampled_returns = returns.reshape(-1)
    sampled_inflation_rates = infl['inflation_by_year_matrix'].reshape(-1)
    sampled_wellness_shocks = infl['wellness_shock_matrix']
    return_model = str(batch['return_diag'].get('return_model') or portfolio_diag.get('return_model'))
    st.he_contingency_success_v, st.required_cut_distribution, st.return_model, st.sampled_inflation_rates, st.sampled_returns, st.sampled_wellness_shocks, st.success_ci_high, st.success_ci_low, st.success_no_ruin_ci_high, st.success_no_ruin_ci_low, st.success_rate, st.success_rate_no_ruin, st.success_se, st.sustainable_spending = he_contingency_success_v, required_cut_distribution, return_model, sampled_inflation_rates, sampled_returns, sampled_wellness_shocks, success_ci_high, success_ci_low, success_no_ruin_ci_high, success_no_ruin_ci_low, success_rate, success_rate_no_ruin, success_se, sustainable_spending


def _mc_headline_result(st):
    """Assemble the vectorized headline result dictionary."""
    from ..planning_engines import (
        MC_PARITY_DEMONSTRATED_POLICIES,
        MC_VECTORIZED_PARITY_TOLERANCE_PP,
        _np,
        _percentiles,
        mc_scalar_spotcheck,
    )
    N, base_plan_shortfall, base_rows, base_years, batch, c, configured_mu, configured_sig, first_failure_distribution, he_contingency_enabled_v, he_contingency_success_v, he_haircut_v, he_reserve_v, liquid_pct_by_year, mu, mus_grid, pct_by_year, portfolio_diag, proj, quintiles, required_cut_distribution, return_model, sampled_inflation_rates, sampled_returns, sampled_wellness_shocks, seed, sens_N, sensitivity, sig, sigs_grid, success_ci_high, success_ci_low, success_no_ruin_ci_high, success_no_ruin_ci_low, success_rate, success_rate_no_ruin, success_se, success_threshold, success_threshold_source, sustainable_spending, terminal_liquid, terminal_total = st.N, st.base_plan_shortfall, st.base_rows, st.base_years, st.batch, st.c, st.configured_mu, st.configured_sig, st.first_failure_distribution, st.he_contingency_enabled_v, st.he_contingency_success_v, st.he_haircut_v, st.he_reserve_v, st.liquid_pct_by_year, st.mu, st.mus_grid, st.pct_by_year, st.portfolio_diag, st.proj, st.quintiles, st.required_cut_distribution, st.return_model, st.sampled_inflation_rates, st.sampled_returns, st.sampled_wellness_shocks, st.seed, st.sens_N, st.sensitivity, st.sig, st.sigs_grid, st.success_ci_high, st.success_ci_low, st.success_no_ruin_ci_high, st.success_no_ruin_ci_low, st.success_rate, st.success_rate_no_ruin, st.success_se, st.success_threshold, st.success_threshold_source, st.sustainable_spending, st.terminal_liquid, st.terminal_total
    return {
        'pct_by_year': pct_by_year,
        'liquid_pct_by_year': liquid_pct_by_year,
        'quintiles': quintiles,
        'sensitivity': sensitivity,
        'sensitivity_sims': sens_N,
        'years': base_years,
        'mus': mus_grid,
        'sigs': sigs_grid,
        'mu': mu,
        'sig': sig,
        'configured_mu': configured_mu,
        'configured_sig': configured_sig,
        'portfolio_return_model': return_model.replace('vectorized_', ''),
        'portfolio_return_diagnostics': {**portfolio_diag, **batch['return_diag'], 'mc_engine': 'vectorized_batched_tax_withdrawal', 'hybrid_tax_kernel_note': 'Scalar deterministic tax/withdrawal rows seed a vectorized bucket recursion; exact scalar MC remains available for validation.'},
        'sampled_mean_return': float(_np.mean(sampled_returns)) if sampled_returns.size else mu,
        'sampled_geometric_return': float(_np.exp(_np.mean(_np.log1p(_np.clip(sampled_returns, -0.999999, None)))) - 1.0) if sampled_returns.size else mu,
        'sampled_mean_inflation': float(_np.mean(sampled_inflation_rates)) if sampled_inflation_rates.size else float(c.get('inf', 0.025) or 0.025),
        'sampled_wellness_shock_count': int(_np.count_nonzero(sampled_wellness_shocks > 0.0)),
        'sampled_wellness_shock_mean_cost': float(_np.mean(sampled_wellness_shocks[sampled_wellness_shocks > 0.0])) if _np.any(sampled_wellness_shocks > 0.0) else 0.0,
        'return_recentered': bool(c.get('mc_recenter_regime_returns', True)),
        'n_sims': N,
        'seed': seed,
        'success_definition': (
            'The guardrail-managed portfolio (Guyton-Klinger / floor-ceiling band) never failed to '
            "cover its own, dynamically self-cut withdrawal -- this is conditional on the modelled "
            "spending cuts (see worst_modeled_spending_cut_pct), not funded-as-asked."
            if bool(proj.get('guardrail_policy_active') is not None and _np.any(proj.get('guardrail_policy_active')))
            else 'No unfunded annual spending gap and liquid retirement assets remain above configured floor in every active projected year '
                 '(funded as asked: any account, including Roth as a last resort, may fund any spending).'
        ),
        'success_rate_within_tier_policy': (
            float(_np.mean(batch['within_policy_path_success']))
            if batch.get('within_policy_path_success') is not None else None
        ),
        'success_definition_within_tier_policy': (
            'Same test, but each spending tier may draw only from the account types its policy allows '
            '(important/discretionary spending never draws Roth; discretionary never draws HSA). '
            'Approximate: per-path tax is not recomputed. Answers "would I get through without ever '
            'dipping into Roth for extras", not "will the money last".'
        ),
        'success_liquid_floor': success_threshold,
        'success_liquid_floor_source': success_threshold_source,
        'success_rate': success_rate,
        'success_rate_ci_low': success_ci_low,
        'success_rate_ci_high': success_ci_high,
        'success_rate_standard_error': success_se,
        'success_definition_no_ruin': 'No unfunded annual spending gap in any active projected year (ignores the reserve-floor buffer required by success_liquid_floor above).',
        'success_rate_no_ruin': success_rate_no_ruin,
        'success_rate_no_ruin_ci_low': success_no_ruin_ci_low,
        'success_rate_no_ruin_ci_high': success_no_ruin_ci_high,
        'liquid_success_rate': success_rate,
        'total_nw_success_rate': float(_np.mean(terminal_total > 0.0)),
        'failure_rate': 1.0 - success_rate,
        'home_equity_contingency_enabled': he_contingency_enabled_v,
        'home_equity_contingency_reserve': he_reserve_v,
        'home_equity_contingency_haircut': he_haircut_v,
        'success_rate_with_home_equity': he_contingency_success_v,
        'deterministic_projection_label': 'No-volatility deterministic reference path; Monte Carlo median is the probabilistic planning number.',
        'first_failure_distribution': first_failure_distribution,
        'required_cut_distribution': required_cut_distribution,
        'sustainable_spending_solve': sustainable_spending,
        # Item 3.5 (F6): mandatory disclosure of the modelled spending cut's
        # size and duration whenever a guardrail spending policy is active
        # (§5.4's own acceptance criterion) -- and success_definition/
        # success_rate's meaning change made explicit rather than silent.
        'spending_policy': str(c.get('spending_policy', 'fixed_real') or 'fixed_real').strip().lower(),
        'spending_policy_active': bool(proj.get('guardrail_policy_active') is not None and _np.any(proj.get('guardrail_policy_active'))),
        'worst_modeled_spending_cut_pct': (
            float(_np.max(proj['guardrail_worst_cut_frac'])) if 'guardrail_worst_cut_frac' in proj else None
        ),
        'median_modeled_spending_cut_years': (
            float(_np.median(proj['guardrail_cut_years_count'])) if 'guardrail_cut_years_count' in proj else None
        ),
        'max_modeled_spending_cut_years': (
            int(_np.max(proj['guardrail_cut_years_count'])) if 'guardrail_cut_years_count' in proj else None
        ),
        'guardrail_probability_ever_cut': (
            float(_np.mean(proj['guardrail_ever_cut'])) if 'guardrail_ever_cut' in proj else None
        ),
        # Optimization-refactor Phase 2: fraction of paths whose essential-
        # tier spending was never left unfunded (see _mc_vectorized_batch).
        'essential_fully_funded_probability': batch.get('essential_fully_funded_probability'),
        # Optimization-refactor Phase 2: genuine per-path MC cut statistics
        # (see _mc_vectorized_batch/monte_carlo_exact_scalar for definitions).
        'probability_any_cut': batch.get('probability_any_cut'),
        'cut_years_pct': batch.get('cut_years_pct'),
        'max_annual_shortfall_real_pct': batch.get('max_annual_shortfall_real_pct'),
        'max_consecutive_cut_years_pct': batch.get('max_consecutive_cut_years_pct'),
        'cumulative_shortfall_real_pct': batch.get('cumulative_shortfall_real_pct'),
        # Optimization-refactor Phase 2: liquidity coverage distribution
        # (see _mc_vectorized_batch/monte_carlo_exact_scalar for definitions).
        'liquidity_coverage_pct_by_year': batch.get('liquidity_coverage_pct_by_year'),
        'worst_liquidity_coverage_ratio_pct': batch.get('worst_liquidity_coverage_ratio_pct'),
        # Optimization-refactor Phase 2: after-tax transfer/legacy value
        # distribution (see _mc_vectorized_batch/monte_carlo_exact_scalar).
        'after_tax_terminal_nw_pct': batch.get('after_tax_terminal_nw_pct'),
        'post_tax_inheritance_pct': batch.get('post_tax_inheritance_pct'),
        # Optimization-refactor Phase 2: "probability of meeting a user
        # legacy floor" (see _mc_vectorized_batch/monte_carlo_exact_scalar).
        'probability_legacy_floor_met': batch.get('probability_legacy_floor_met'),
        # Optimization-refactor Phase 2: survivor-period dashboard rows
        # (see _mc_vectorized_batch for definitions).
        'survivor_period_applicable_probability': batch.get('survivor_period_applicable_probability'),
        'survivor_period_failure_probability': batch.get('survivor_period_failure_probability'),
        'terminal_total_nw': _percentiles(terminal_total.tolist(), 0.0),
        'terminal_liquid_assets': _percentiles(terminal_liquid.tolist(), success_threshold),
        'nw0': float(proj['pretax'][0, 0] + proj['roth'][0, 0] + proj['taxable'][0, 0] + proj['hsa'][0, 0]),
        'invest0': float(proj['pretax'][0, 0] + proj['roth'][0, 0] + proj['taxable'][0, 0] + proj['hsa'][0, 0]),
        'net_draws': [],
        'survival_curve': [
            {'year': yr, 'pct_funded': liquid_pct_by_year[yr]['success'] * 100}
            for yr in base_years
        ],
        'mc_engine': 'vectorized_batched_tax_withdrawal',
        'mc_engine_label': 'Tolerance-bounded vectorized Monte Carlo',
        # WI-036: the replay headline re-uses the deterministic engine's per-bucket
        # draws, so a base plan that already runs into a shortfall is not
        # re-funded in full on each sampled path and the headline is optimistic
        # by 6 to 65pp (documentation/reference/MC_PARITY_MEASUREMENT_WI036.md).
        # The +/-tolerance holds only when the base plan is fully funded.
        'mc_base_plan_shortfall': base_plan_shortfall,
        'mc_approximation_status': 'BASE_PLAN_SHORTFALL' if base_plan_shortfall else 'TOLERANCE_BOUNDED',
        'mc_parity_tolerance_pp': MC_VECTORIZED_PARITY_TOLERANCE_PP,
        'mc_parity_policy_demonstrated': (
            str(c.get('roth_policy') or 'optimize_terminal_tax').lower() in MC_PARITY_DEMONSTRATED_POLICIES),
        'scalar_spotcheck': (
            mc_scalar_spotcheck(c, n=int(c.get('mc_scalar_spotcheck_n') or 0), base_rows=base_rows)
            if int(c.get('mc_scalar_spotcheck_n') or 0) > 0
            else {'status': 'not_run', 'note': 'Set mc_scalar_spotcheck_n > 0 to run a small-N paired scalar spot-check.'}),
        'model_risk_rating': 'APPROXIMATE_VECTORIZED_MC' if base_plan_shortfall else 'TOLERANCE_BOUNDED_VECTORIZED_MC',
    }
