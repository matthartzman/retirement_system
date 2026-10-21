"""Roth-conversion helpers lifted out of plan_roth_conversion and _roth_strategy_metrics (WI-034, ARC-005).

Former nested closures with their captured locals as explicit leading
parameters; bodies verbatim.  Module-level names are imported at call time from
``src.planning_engines`` so monkeypatches there still apply and no import cycle
is created.
"""
from __future__ import annotations

from typing import Mapping



def _ranked_caps(caps_seen, caps: list[tuple[str, float]]) -> tuple[float, str, str]:
    from ..engine_kernels import roth_guardrail_id
    clean = [(name, max(0.0, float(val))) for name, val in caps if val is not None]
    clean.sort(key=lambda x: x[1])
    caps_seen[:] = [{"id": roth_guardrail_id(n), "name": n, "cap": round(v, 2)} for n, v in clean]
    if not clean:
        return 0.0, "", ""
    primary = clean[0]
    secondary = clean[1] if len(clean) > 1 else ("", 0.0)
    return primary[1], primary[0], secondary[0]


def _ltcg_niit_caps(c, filing, note_int_yr, portfolio_ordinary, portfolio_qualified, pre_agi, std, year) -> list[tuple[str, float]]:
    """NIIT-cliff and LTCG-rate-tier caps, sized off income already known
    at conversion-sizing time (before this year's realized capital gains
    are computed later in the projection loop, so this can only protect
    the qualified-dividend/interest income already visible here -- it
    cannot see gains TLH/gain-harvesting/portfolio draws realize later
    this same year).
    """
    from ..engine_kernels import _roth_ltcg_thresholds_base, _roth_niit_threshold_base, _tk
    extra: list[tuple[str, float]] = []
    # WI-306 / FIN-014: use the kernel's signed-off indexing convention
    # (compounded from FEDERAL_BRACKETS_VALUE_YEAR, not plan_start) so the
    # guardrail threshold matches what tax_kernel.ltcg_tax_on_gain uses.
    bracket_factor = _tk.bracket_factor_for_year(c, year)

    if c.get("roth_ltcg_cap", True) and portfolio_qualified > 0:
        ltcg_top0, ltcg_top15 = _roth_ltcg_thresholds_base(c, filing)
        ltcg_top0 *= bracket_factor
        ltcg_top15 *= bracket_factor
        # WI-023 / FIN-003: qualified dividends are now taxed in the 0/15/20%
        # preferential stack, directly below any realized gain. ``pre_agi``
        # already includes ``portfolio_qualified`` (see pre_non_ss above), so the
        # stack position tested here contains the dividends, and the band tops
        # come from the verified 2026 dataset via _roth_ltcg_thresholds_base and
        # the kernel's bracket factor -- the same tops tax_kernel.ltcg_tax_on_gain
        # applies.
        # WI-023b (planner decision): the band tops are TAXABLE-income thresholds,
        # so the stack position is pre-conversion AGI less the deduction (the
        # standard deduction is the floor available at sizing time, as in the
        # bracket-room calculation above). A conversion adds ordinary income
        # dollar for dollar, so headroom is measured from this position.
        _stack_pos = max(0.0, pre_agi - std)
        # roth_ltcg_band: 'auto' stays within whichever band income is in
        # today; '0%' / '15%' name the band to stay within. A named band
        # income has already passed cannot be stayed within, so it adds no
        # cap (a cap of $0 would silently block every conversion).
        _band = str(c.get("roth_ltcg_band", "auto") or "auto").strip().lower()
        if _band in ("0%", "0", "zero"):
            ltcg_ceiling = ltcg_top0 if _stack_pos < ltcg_top0 else None
        elif _band in ("15%", "15", "fifteen"):
            ltcg_ceiling = ltcg_top15 if _stack_pos < ltcg_top15 else None
        elif _stack_pos < ltcg_top0:
            ltcg_ceiling = ltcg_top0
        elif _stack_pos < ltcg_top15:
            ltcg_ceiling = ltcg_top15
        else:
            ltcg_ceiling = None
        if ltcg_ceiling is not None:
            cap_ltcg = max(0.0, ltcg_ceiling - _stack_pos) * float(c.get('roth_ltcg_headroom_usage_pct', 0.95) or 0.95)
            extra.append(("LTCG rate tier", cap_ltcg))

    nii_known_est = max(0.0, float(note_int_yr) + float(portfolio_ordinary) + float(portfolio_qualified))
    if c.get("roth_niit_cap", True) and nii_known_est > 0:
        niit_thr = _roth_niit_threshold_base(c, filing)
        cap_niit = max(0.0, niit_thr - pre_agi) * float(c.get('roth_niit_headroom_usage_pct', 0.95) or 0.95)
        extra.append(("NIIT threshold", cap_niit))

    return extra


def _would_allow(_have, caps_seen, gid: str, name: str, cap: float) -> None:
    if gid not in _have:
        caps_seen.append({"id": gid, "name": name, "cap": round(max(0.0, float(cap)), 2), "active": False})
        _have.add(gid)


def _disc(discount, plan_start, row: Mapping) -> float:
    return (1.0 + discount) ** max(0, int(row.get('year', plan_start) or plan_start) - plan_start)


def _pv_avg(discount, plan_start, rows, field: str) -> float:
    weights = [1.0 / _disc(discount, plan_start, r) for r in rows]
    denom = sum(weights) or 1.0
    return sum(max(0.0, float(r.get(field, 0.0) or 0.0)) * w for r, w in zip(rows, weights)) / denom


def _peak(rows, field: str) -> float:
    return max((max(0.0, float(r.get(field, 0.0) or 0.0)) for r in rows), default=0.0)


def _avg_pretax(row_list) -> float:
    return (sum(max(0.0, float(r.get('pretax_nw', 0.0) or 0.0)) for r in row_list) / len(row_list)) if row_list else 0.0


def _estate_tax_for_row(c, fed_exempt_base, row: Mapping) -> float:
    from ..engine_kernels import (
        indexed_federal_estate_exemption,
        resolved_state_estate_exemption,
        state_estate_tax,
        state_for_year,
    )
    row_total = max(0.0, float(row.get('total_nw', 0.0) or 0.0))
    row_cst = max(0.0, float(row.get('cst_excluded_from_survivor_estate', 0.0) or 0.0))
    row_year = int(row.get('year', c.get('plan_start', 0)) or 0)
    fed_exempt = indexed_federal_estate_exemption(fed_exempt_base, c.get('plan_start', row_year), row_year, c.get('brk_inf', 0.02))
    federal_taxable = max(0.0, row_total - (row_cst if c.get('federal_portability_enabled', True) else 0.0))
    state_taxable = max(0.0, row_total - row_cst)
    federal_tax = max(0.0, federal_taxable - fed_exempt) * 0.40 if fed_exempt else 0.0
    # Item 3.6 (F5): New York's 3-year gift add-back.
    gift_addback = max(0.0, float(row.get('gift_total_last_3yr', 0.0) or 0.0))
    # #302: resolve BOTH the resident state and its exemption per-row-year
    # (state_for_year), not once at the top of this function -- a
    # household with a residency schedule can be a different state in a
    # later row-year, and item 3.6 (F5)'s resolved_state_estate_exemption
    # corrects the shipped $4M (Illinois's own exemption) default for a
    # non-Illinois resident state to that state's real statutory
    # exemption instead.
    row_state = state_for_year(c, row_year)
    row_state_exempt = resolved_state_estate_exemption(row_state, float(c.get('il_exempt', 0.0) or 0.0))
    state_tax = (
        state_estate_tax(row_state, state_taxable, row_state_exempt, gift_addback=gift_addback)[0]
        if c.get('model_state_est', True) and row_state_exempt
        else 0.0
    )
    return federal_tax + state_tax


def _roth_conversion_amount_and_caps(aca_bridge_people, bal, base_tax_est, bracket_room, c, filing, h_age, income_streams, note_int_yr, policy, portfolio_ordinary, portfolio_qualified, pre_agi, spend, std, target_rate, top_target, total_spend_need, w_age, year):
    """Size the conversion amount against the binding bracket, ACA, LTCG and NIIT caps."""
    from ..engine_kernels import (
        ConversionPlan,
        _ar,
        _available_by_owner,
        _log_fallback,
        _ltcg_niit_caps,
        _ranked_caps,
        _roth_irmaa_guardrail_age_gate_met,
        _roth_irmaa_target_threshold,
        _roth_ltcg_thresholds_base,
        _roth_niit_threshold_base,
        _sum_bal,
        _tk,
        _would_allow,
        aca_fpl_for_year,
        aca_guardrail_max_fpl_multiple,
        json,
        liquidity_reserve_floor,
    )
    # Trust headroom is taxable dollars above the reserve -- but only when the
    # reserve is actually held in taxable. A Roth or HSA reserve leaves the
    # taxable bucket entirely free to fund conversions, and subtracting it here
    # (as every reserve did before P8) understated conversion capacity.
    taxable_ids = c.get("taxable_ids") or _ar.taxable_ids(c.get("account_registry", []))
    trust_surf = max(0.0, _sum_bal(bal, taxable_ids)
                     - liquidity_reserve_floor(c, year, "taxable", spend))
    non_roth_surplus = income_streams + trust_surf - total_spend_need - base_tax_est

    primary_avail = _available_by_owner(c, bal, 0)
    secondary_avail = _available_by_owner(c, bal, 1)
    # An IRA reserve must survive conversions too: converting pre-tax dollars to
    # Roth empties the bucket the reserve is meant to preserve just as surely as
    # spending them would.
    ira_total = max(0.0, primary_avail + secondary_avail
                    - liquidity_reserve_floor(c, year, "pretax", spend))
    amount = 0.0
    binding = ""
    secondary_binding = ""

    max_pct = float(c.get("roth_max_annual_conversion_pct_of_traditional_ira", 0.20) or 0.20)
    max_pct = min(1.0, max(0.0, max_pct))
    max_pct_cap = ira_total * max_pct if max_pct > 0 else float("inf")

    caps_seen: list[dict] = []

    if policy == "fixed_dollar":
        fixed_amt = float(c.get("roth_fixed_amount", 50000) or 0.0)
        if ira_total > 5000 and fixed_amt > 1000:
            cap, binding, secondary_binding = _ranked_caps(caps_seen, [
                ("Fixed dollar", fixed_amt), ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ])
            amount = cap
    elif policy == "fill_to_irmaa":
        irmaa_thr = _roth_irmaa_target_threshold(c, filing, year)
        cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
        # Caps are sized even when the IRMAA tier has no room left (cap_irmaa
        # <= 1000): the amount then stays 0 (reset below), but the guardrail
        # panel can show the IRMAA tier as the limit actually holding it down.
        if ira_total > 5000:
            caps = [
                (str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa),
                ("IRA balance", ira_total),
                ("Annual IRA percentage cap", max_pct_cap),
            ]
            if aca_bridge_people and c.get('aca_ptc_enabled', True) and c.get('roth_aca_cap', True):
                # P1 (system review 2026-07-21): this policy caps to the IRMAA
                # threshold alone, which sits far above 400% FPL -- with no
                # ACA guardrail, an ACA-bridge client on "fill to IRMAA" gets
                # conversions sized straight into subsidy-destroying MAGI.
                # Mirrors the fill_to_bracket branch's guardrail above.
                fpl = aca_fpl_for_year(c, year)
                max_fpl = aca_guardrail_max_fpl_multiple(c, year)
                caps.append(("ACA PTC MAGI guardrail", max(0.0, max_fpl * fpl - pre_agi)))
            caps.extend(_ltcg_niit_caps(c, filing, note_int_yr, portfolio_ordinary, portfolio_qualified, pre_agi, std, year))
            cap, binding, secondary_binding = _ranked_caps(caps_seen, caps)
            amount = cap
    else:
        # roth_bracket_cap off: the target bracket no longer limits conversions
        # (the other active guardrails still do).
        _bracket_on = bool(c.get('roth_bracket_cap', True))
        # Caps are sized every year, even when the bracket has no room left
        # (the amount then stays 0), so the guardrail panel can show why.
        cap_bracket = bracket_room * float(c.get('roth_headroom_usage_pct', 0.95) or 0.95)
        caps = [("IRA balance", ira_total), ("Annual IRA percentage cap", max_pct_cap)]
        if _bracket_on:
            caps.insert(0, (f"{int(target_rate * 100)}% bracket", cap_bracket))
        if aca_bridge_people and c.get('aca_ptc_enabled', True) and c.get('roth_aca_cap', True):
            # Roth conversions in bridge years can destroy ACA premium tax
            # credits.  Add a guardrail that keeps MAGI below the point where
            # the configured benchmark subsidy is largely lost.
            fpl = aca_fpl_for_year(c, year)
            max_fpl = aca_guardrail_max_fpl_multiple(c, year)
            caps.append(("ACA PTC MAGI guardrail", max(0.0, max_fpl * fpl - pre_agi)))
        guard_mode = str(c.get("irmaa_guardrail_mode", "AVOID_NEXT_TIER") or "AVOID_NEXT_TIER").upper()
        if (
            c.get("roth_irmaa_cap", True)
            and guard_mode not in ("IGNORE", "WARN_ONLY")
            and _roth_irmaa_guardrail_age_gate_met(c, h_age, w_age)
        ):
            irmaa_thr = _roth_irmaa_target_threshold(c, filing, year)
            cap_irmaa = max(0.0, irmaa_thr - pre_agi) * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95)
            caps.append((str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(), cap_irmaa))
        caps.extend(_ltcg_niit_caps(c, filing, note_int_yr, portfolio_ordinary, portfolio_qualified, pre_agi, std, year))
        if ira_total > 5000:
            cap, binding, secondary_binding = _ranked_caps(caps_seen, caps)
            if cap > 1000:
                amount = cap

    if amount < 1000:
        amount = 0.0
        binding = ""
        secondary_binding = ""

    # Every guardrail is quantified every year. The ones enforced this year are
    # the real caps ("active": True); the rest (switched off, or not applicable
    # this year -- IRMAA before the age gate, ACA outside bridge years, no
    # qualified income, a different policy) carry the dollars they WOULD allow
    # with "active": False, so the panel can always show a number.
    for _e in caps_seen:
        _e["active"] = True
    _have = {_e["id"] for _e in caps_seen}

    try:
        _bf = _tk.bracket_factor_for_year(c, year)
        _would_allow(_have, caps_seen, "bracket", f"{int(target_rate * 100)}% bracket",
                     bracket_room * float(c.get('roth_headroom_usage_pct', 0.95) or 0.95))
        _would_allow(_have, caps_seen, "irmaa", str(c.get("roth_irmaa_target_tier", "TIER_2")).replace("_", " ").title(),
                     (_roth_irmaa_target_threshold(c, filing, year) - pre_agi)
                     * float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95))
        _t0, _t15 = _roth_ltcg_thresholds_base(c, filing)
        _sp = max(0.0, pre_agi - std)  # same stack position as the active cap in _ltcg_niit_caps
        _ceil = _t0 * _bf if _sp < _t0 * _bf else (_t15 * _bf if _sp < _t15 * _bf else None)
        if _ceil is not None:
            _would_allow(_have, caps_seen, "ltcg", "LTCG rate tier",
                         (_ceil - _sp) * float(c.get('roth_ltcg_headroom_usage_pct', 0.95) or 0.95))
        _would_allow(_have, caps_seen, "niit", "NIIT threshold",
                     (_roth_niit_threshold_base(c, filing) - pre_agi)
                     * float(c.get('roth_niit_headroom_usage_pct', 0.95) or 0.95))
        if aca_bridge_people:
            _would_allow(_have, caps_seen, "aca", "ACA PTC MAGI guardrail",
                         aca_guardrail_max_fpl_multiple(c, year) * aca_fpl_for_year(c, year) - pre_agi)
        _would_allow(_have, caps_seen, "pct", "Annual IRA percentage cap", ira_total * max_pct)
        _would_allow(_have, caps_seen, "balance", "IRA balance", ira_total)
    except (TypeError, ValueError, KeyError, ZeroDivisionError) as _exc:
        _log_fallback("roth_guardrail.trace", _exc, year=year)
    # Record which bracket rate this year's bracket cap used (a phase-varying or
    # optimizer-chosen strategy can differ from the configured target bracket).
    for _e in caps_seen:
        if _e["id"] == "bracket":
            _e["rate"] = round(float(target_rate), 4)

    return ConversionPlan(
        amount=amount,
        pre_agi=pre_agi,
        top_target=top_target,
        bracket_room=bracket_room,
        non_roth_surplus=non_roth_surplus,
        primary_pretax_available=primary_avail,
        secondary_pretax_available=secondary_avail,
        binding_limit=binding,
        secondary_binding_limit=secondary_binding,
        guardrail_caps=json.dumps(caps_seen) if caps_seen else "",
    )


def _roth_candidate_sweep(_evaluate_roth_candidate, _score_candidate, auto_optimize, base, c, requested_policy):
    """Evaluate the candidate Roth strategies and choose the winner."""
    from ..planning_engines import (
        LCV_FEASIBILITY_GATE_THRESHOLD,
        _roth_legacy_mode_multiplier,
        _roth_strategy_candidate_specs,
        _roth_strategy_comparison_specs,
        run_scenario,
        strategy_sweep,
    )
    # Item 2.3 (A4), need-based gating: the full ~30-candidate sweep is only
    # needed when the engine is actually choosing the policy (auto_optimize)
    # or the user explicitly asked to compare a specific strategy FAMILY via
    # roth_bracket_strategy. An explicit top-level policy with no family
    # request left at its OPTIMIZER_CHOOSES default was running that same
    # full sweep purely to populate a disclosure table whose SELECTED policy
    # never depends on it (see the explicit-policy branch below, which always
    # scores the exact configured policy directly) -- that case now gets
    # _roth_strategy_comparison_specs' small fixed set instead.
    #
    # Narrowed after a real diff surfaced against test_synthetic_golden_master.py
    # (2026-09-01): several full-set specs share the exact SAME policy and
    # target_rate as each other for a 'fill_to_bracket' policy (e.g.
    # FILL_CURRENT_BRACKET, SURVIVOR_TAX_AWARE, RMD_REDUCTION, and
    # LEGACY_TARGETED all reduce to target_rate == configured_target once
    # configured_target already clears their own max(configured_target, X)
    # floors) -- the explicit-policy match below picks whichever of those
    # happens to score highest, so shrinking the field can silently change
    # WHICH near-duplicate spec's label gets disclosed as "selected" even
    # though every one of them scores and projects identically for the
    # actual plan (see the match logic's own comment: it never applies a
    # matched candidate's overrides back onto c, only its label/strategy_code
    # for disclosure). 'none' and 'fill_to_irmaa' have exactly one full-set
    # spec each -- no ambiguity, safe to reduce. 'fixed_dollar' matches on
    # fixed_amount to 1e-6 precision and _roth_strategy_candidate_specs'
    # own seen-key dedup already collapses a configured amount that
    # coincides with one of its literal amounts -- also unambiguous.
    # 'fill_to_bracket' is the one policy where reduction can change the
    # disclosed label, so it always gets the full sweep.
    _requested_bracket_strategy = str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').strip().upper()
    _use_full_roth_sweep = (
        auto_optimize
        or _requested_bracket_strategy != 'OPTIMIZER_CHOOSES'
        or requested_policy == 'fill_to_bracket'
    )
    _roth_specs = _roth_strategy_candidate_specs(c) if _use_full_roth_sweep else _roth_strategy_comparison_specs(c)

    # Item 2.3 (A4): shared enumerate/evaluate/rank/gate shape -- see
    # src/strategy_sweep.py's own docstring. The candidate scoring itself
    # (_score_candidate/_roth_strategy_metrics above) is untouched; this
    # only replaces the loop/sort/feasibility-gate-with-fallback plumbing
    # around it, byte-for-byte equivalent to the inline version this
    # replaced (verified against the golden master and the frozen Roth
    # candidate table).
    #
    # Optimization-refactor Phase 4 (Option C, full sign-off): a candidate
    # that fails the feasibility gate is hard-excluded from selection --
    # never chosen no matter how favorable its LCV score is. Ranking/
    # reporting still shows every candidate (candidates list below, used by
    # Sheet 11's disclosure table) so a failing candidate remains visible for
    # comparison; only the *selection* below is restricted. If every
    # candidate fails the gate, fall back to ranking the full set so a
    # recommendation is still produced, flagged via
    # roth_all_candidates_infeasible below.
    _sweep = strategy_sweep.run_sweep(
        _roth_specs,
        _evaluate_roth_candidate,
        sort_key=lambda x: (x['score'], x['after_tax_terminal_nw'], -x['lifetime_tax']),
        fallback_best={'policy': 'none', 'label': 'No voluntary conversions'},
    )
    candidates = _sweep.candidates
    _all_candidates_infeasible = _sweep.all_infeasible
    best = _sweep.best

    if auto_optimize:
        selected = best
        c['roth_policy_requested'] = requested_policy
        c['roth_policy'] = selected.get('policy', 'none')
        c['roth_optimized_policy'] = c['roth_policy']
        if selected.get('target_rate') is not None:
            c['roth_target_rate'] = float(selected['target_rate'])
            c['roth_brk'] = float(selected['target_rate'])
        if selected.get('fixed_amount') is not None:
            c['roth_fixed_amount'] = float(selected['fixed_amount'])
    else:
        # Explicit user-selected policy: keep it as configured. Identify the
        # matching candidate (by policy/target_rate/fixed_amount) so the sheet
        # can mark it "selected" and explain why the others were not used.
        current_target = None if c.get('roth_target_rate') is None else float(c.get('roth_target_rate'))
        current_fixed = None if c.get('roth_fixed_amount') is None else float(c.get('roth_fixed_amount'))
        selected = next(
            (cand for cand in candidates
             if cand.get('policy') == requested_policy
             and (cand.get('target_rate') is None or current_target is None or abs(cand['target_rate'] - current_target) < 1e-9)
             and (cand.get('fixed_amount') is None or current_fixed is None or abs(cand['fixed_amount'] - current_fixed) < 1e-6)),
            None,
        )
        if selected is None:
            # Score the exact configured policy directly so it always has a row.
            c2, rows = run_scenario(base, {'roth_policy': requested_policy})
            metrics = _score_candidate(c2, rows)
            selected = {
                'label': f'Configured strategy ({requested_policy})',
                'policy': requested_policy,
                'strategy_code': requested_policy.upper(),
                'target_rate': current_target,
                'fixed_amount': current_fixed,
                **metrics,
            }
            candidates.append(selected)
            candidates.sort(key=lambda x: (x['score'], x['after_tax_terminal_nw'], -x['lifetime_tax']), reverse=True)
        c['roth_policy_requested'] = requested_policy

    if selected.get('overrides'):
        c.update(selected['overrides'])

    # Item 4.3: surface the effective (derived-or-overridden) heir/terminal
    # pre-tax ordinary rates actually used to score the SELECTED strategy, so the
    # workbook can disclose the real numbers rather than the flat config default.
    c['roth_heir_ordinary_tax_rate_effective'] = float(selected.get('heir_ordinary_tax_rate_effective', 0.0) or 0.0)
    c['roth_terminal_pretax_tax_rate_effective'] = float(selected.get('terminal_pretax_tax_rate_effective', 0.0) or 0.0)

    c['roth_optimization'] = {
        'requested_policy': requested_policy,
        'auto_optimized': auto_optimize,
        'selected_label': selected.get('label', ''),
        'selected_policy': c['roth_policy'],
        'selected_strategy_code': selected.get('strategy_code', c['roth_policy']),
        'roth_bracket_strategy': str(c.get('roth_bracket_strategy', 'OPTIMIZER_CHOOSES') or 'OPTIMIZER_CHOOSES').upper(),
        'objective_mode': str(c.get('roth_objective_mode', 'BALANCED_RETIREMENT') or 'BALANCED_RETIREMENT').upper(),
        'estate_tax_objective_mode': str(c.get('estate_tax_objective_mode', 'BALANCED') or 'BALANCED').upper(),
        'headroom_usage_pct': float(c.get('roth_headroom_usage_pct', 0.95) or 0.95),
        'irmaa_headroom_usage_pct': float(c.get('roth_irmaa_headroom_usage_pct', 0.95) or 0.95),
        'irmaa_guardrail_mode': str(c.get('irmaa_guardrail_mode', 'AVOID_NEXT_TIER') or 'AVOID_NEXT_TIER').upper(),
        'irmaa_target_tier': str(c.get('roth_irmaa_target_tier', 'TIER_2') or 'TIER_2').upper(),
        'terminal_weight': float(c.get('roth_optimize_terminal_weight', 1.0) or 1.0),
        'tax_weight': float(c.get('roth_optimize_tax_weight', 0.25) or 0.0),
        'target_bracket': float(c.get('roth_target_rate', c.get('roth_brk', 0.22)) or 0.22),
        'terminal_tax_rate': float(c.get('roth_optimize_terminal_tax_rate', c.get('roth_target_rate', 0.22)) or 0.22),
        'max_annual_conversion_pct_of_traditional_ira': float(c.get('roth_max_annual_conversion_pct_of_traditional_ira', 0.20) or 0.20),
        'max_conversion_years': int(float(c.get('roth_max_conversion_years', 10) or 10)),
        'legacy_objective_mode': str(c.get('roth_legacy_objective_mode', 'OFF') or 'OFF').upper(),
        'legacy_mode_multiplier': _roth_legacy_mode_multiplier(c),
        'future_tax_rate_stress_pct': float(c.get('roth_future_tax_rate_stress_pct', 0.0) or 0.0),
        'future_tax_risk_weight': float(c.get('roth_future_tax_risk_weight', 0.0) or 0.0),
        'inheritance_tax_burden_weight': float(c.get('roth_inheritance_tax_burden_weight', 0.0) or 0.0),
        'heir_ordinary_tax_rate_assumption': float(c.get('roth_heir_ordinary_tax_rate_assumption', 0.0) or 0.0),
        'heir_filing_status': str(c.get('roth_heir_filing_status', 'Single') or 'Single'),
        'heir_ordinary_tax_rate_effective': float(selected.get('heir_ordinary_tax_rate_effective', 0.0) or 0.0),
        'terminal_pretax_tax_rate_effective': float(selected.get('terminal_pretax_tax_rate_effective', 0.0) or 0.0),
        'pre_tax_bequest_penalty_pct': float(c.get('roth_pre_tax_bequest_penalty_pct', 0.0) or 0.0),
        'roth_bequest_preference_bonus_pct': float(c.get('roth_bequest_preference_bonus_pct', 0.0) or 0.0),
        'survivor_tax_risk_weight': float(c.get('roth_survivor_tax_risk_weight', 0.0) or 0.0),
        'feasibility_gate_threshold': LCV_FEASIBILITY_GATE_THRESHOLD,
        'all_candidates_infeasible': _all_candidates_infeasible,
        'candidates': candidates,
    }
    return c
