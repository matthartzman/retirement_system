"""Excel summary sheet builder — executive summary and assumptions.

This module provides the high-level Excel sheet builders for summary reports:
- build_sheet1: Executive Summary (headline numbers, recommendations, build assumptions)
- build_sheet2: Assumptions & Tax Law (configurable input tables)

System review 2026-08-04, architect finding `reporting-facade-theater`
(Wave 4.10): this was a facade re-importing from sheets_summary.py; it is now
the canonical source for these builders. _workbook_pricing_source_label and
_rebalance_settings are reused from sheets_allocation_helpers.py rather than
duplicated, since Sheet 4 also uses both.
"""

from .workbook_common import (
    BLUE,
    DGRAY,
    FMT_DOLLAR,
    FMT_PCT,
    FMT_YEAR,
    GRAY,
    LGRAY,
    NAVY,
    ORANGE,
    TAX_BASE_YEAR,
    WHITE,
    _ao,
    datetime,
    input_style,
    module_enabled,
    qc,
    section_title,
    write_cell,
    write_hdr,
)
from .. import allocation_policy as _ap
from . import summary_figures
from ..governance import readiness_label as _readiness_label
from ..planning_engines import compute_baseline_lcv_and_eltr, compute_future_lcv_and_eftr
from .sheets_allocation_helpers import _workbook_pricing_source_label, _rebalance_settings

def _tlh_recommendation_row(c, rows, rec_no):
    """Executive Summary recommendation row for tax-loss harvesting.

    When tlh_policy is 'apply', the value is the actual lifetime tax value
    realized in the projection net of transaction cost. Otherwise it's the
    net value of opportunities available today (analyze_only/off), so the
    line still appears when there's something worth acting on.
    """
    from .. import tlh as _tlh
    policy = str(c.get('tlh_policy', 'off') or 'off')
    if policy == 'apply':
        lifetime_value = sum(float(r.get('tlh_tax_value', 0) or 0) - float(r.get('tlh_transaction_cost', 0) or 0)
                              for r in rows)
        if lifetime_value <= 0:
            return None
        return (rec_no, 'Tax-Loss Harvesting (Active)',
                'Qualifying loss lots in taxable accounts are harvested annually against gains, then up to $3,000/yr of ordinary income, with carryforward tracked.',
                f"~{c.get('tlh_transaction_cost_bps', 2):.0f} bps transaction cost",
                f"~${lifetime_value:,.0f} lifetime tax value (net of cost)", 'Sheet 2I')
    plan_start = int(c.get('plan_start', rows[0]['year'] if rows else 2026))
    first_row = rows[0] if rows else {}
    scan = _tlh.scan_harvest_opportunities(
        c, plan_start,
        ordinary_income=float(first_row.get('taxable_inc', 0) or 0),
        existing_lt_gain=float(first_row.get('ltcg_gain', 0) or 0),
        annual_return=float(c.get('ret', 0.06) or 0.06),
        years_to_step_up=max(1, int(c.get('h_death_yr', plan_start + 20)) - plan_start),
        fraction_sold_before_death=float(c.get('tlh_fraction_sold_before_death', 0.5) or 0.5),
        transaction_cost_bps=float(c.get('tlh_transaction_cost_bps', 2.0) or 0.0),
        min_loss_dollars=float(c.get('tlh_min_loss_dollars', 500.0) or 0.0),
        min_loss_pct=float(c.get('tlh_min_loss_pct', 0.05) or 0.0),
        annual_ceiling=float(c.get('tlh_annual_ceiling', 0.0) or 0.0),
    )
    net = scan['totals']['net_value']
    if net <= 0:
        return None
    return (rec_no, 'Tax-Loss Harvesting Opportunity Available',
            f"{len(scan['opportunities'])} loss lot(s) in taxable accounts meet the harvesting threshold this year.",
            f"~${scan['totals']['transaction_cost']:,.0f} transaction cost",
            f"~${net:,.0f} net lifetime value; set tlh_policy=apply to automate", 'Sheet 2I')

def build_sheet1(ws, c, rows, mc_data, ss_sweep=None):
    """Executive Summary"""
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 55
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 20

    section_title(ws, 1, f"EXECUTIVE SUMMARY — {c['h_name']} & {c['w_name']} Family", 6)

    write_hdr(ws, 2, 1, 'Plan Overview', BLUE, WHITE, span=6)
    data = [
        ('Plan Prepared',          str(datetime.date.today())),
        ('Clients',                f"{c['h_name']} (DOB: {c['h_dob_yr']}) & {c['w_name']} (DOB: {c['w_dob_yr']})"),
        ('Residence State',        c['state']),
        ('Plan Horizon',           f"{c['plan_start']} – {c['plan_end']}"),
        ('Statutory Version',      'OBBBA (One Big Beautiful Bill Act), signed July 4 2025'),
        ('Workbook Pricing Source', _workbook_pricing_source_label()[0]),
    ]
    r = 3
    for label, value in data:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, value)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    # Headline Numbers
    r += 1
    write_hdr(ws, r, 1, 'Headline Numbers', NAVY, WHITE, span=6); r+=1
    yr0 = rows[0]; yrn = rows[-1]
    success = mc_data.get('success_rate', 0.0)
    # #293: the headline figures are Expected After-Tax LCV, NPV of Future
    # Taxes, and Worst-Case (5th percentile Monte Carlo) Ending Wealth --
    # replacing raw Terminal Net Worth, nominal lifetime tax, and Plan
    # Success Rate. compute_baseline_lcv_and_eltr already computes lcv/
    # npv_future_taxes from the same rows; the 5th percentile is already in
    # mc_data['terminal_total_nw'] (same percentile dict the P10/P90/median
    # figures elsewhere in the workbook already read).
    _baseline_metrics = compute_baseline_lcv_and_eltr(c, rows)
    lcv = _baseline_metrics.get('lcv', 0.0)
    npv_future_taxes = _baseline_metrics.get('npv_future_taxes', 0.0)
    worst_case_ending_wealth = (mc_data.get('terminal_total_nw') or {}).get(5, 0.0)
    # Selected-vs-next-best from the Sheet 11 candidate contract. Previously a
    # flat 22% of gross conversions labelled "tax saved", which contradicted
    # Sheet 11 and overstated the case (conversions cost tax in the year taken).
    roth_headline = summary_figures.roth_strategy_benefit(c)

    _h_nick = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _w_nick = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    _ss_best = (ss_sweep or {}).get('best') or {}
    _h_ss_age = _ss_best.get('h_age', c.get('h_ss_claim_age', c.get('ss_claim_age', 70)))
    _w_ss_age = _ss_best.get('w_age', c.get('w_ss_claim_age', c.get('ss_claim_age', 70)))
    _ss_age_label = f"{_h_nick} {_h_ss_age} / {_w_nick} {_w_ss_age}"

    # Monte Carlo headline rows are shown only when the market-luck module is
    # enabled — otherwise mc_data is {} and these would read a misleading 0%.
    _mc_on = module_enabled(c, 'market_luck_stress_test')
    _ss_on = module_enabled(c, 'social_security_timing')
    headlines = [
        ('Starting Net Worth (Y0)',        yr0['total_nw'],  FMT_DOLLAR),
        ('Expected After-Tax LCV',          lcv,               FMT_DOLLAR),
        ('NPV of Future Taxes',             npv_future_taxes,  FMT_DOLLAR),
    ]
    if _mc_on:
        headlines += [
            ('Worst-Case Ending Wealth (5th %ile)', worst_case_ending_wealth, FMT_DOLLAR),
            ('Model Risk Rating', (mc_data.get('model_risk') or {}).get('rating', mc_data.get('model_risk_rating','')), None),
        ]
    # Plain language, not the raw enum. ADVISOR_READY/BLOCKED/REVIEW_REQUIRED
    # are internal constants and no legend for them exists anywhere in the
    # workbook or the app.
    _readiness = c.get('advisor_readiness') or {}
    headlines.append((
        'Advisor-ready status',
        _readiness.get('status_label') or _readiness_label(_readiness.get('status')),
        None))
    if _mc_on:
        headlines += [
            ('MC Success 95% CI Low',       mc_data.get('success_rate_ci_low', success), FMT_PCT),
            ('MC Success 95% CI High',      mc_data.get('success_rate_ci_high', success), FMT_PCT),
        ]
    # Omitted entirely when fewer than two candidates were scored: a
    # "versus next best" figure has no meaning without a next best, and an
    # invented number on the flagship page is the defect being removed here.
    if roth_headline:
        headlines.append((
            f"Lifetime Tax vs. Next-Best Roth Strategy ({roth_headline['runner_up_label']})",
            roth_headline['lifetime_tax_delta'], FMT_DOLLAR))
        headlines.append((
            'After-Tax Terminal NW vs. Next-Best Roth Strategy',
            roth_headline['terminal_nw_delta'], FMT_DOLLAR))
    if _ss_on:
        headlines.append(('Recommended SS Claim Age',        _ss_age_label,     None))
    for label, value, fmt in headlines:
        c1 = write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        c2 = write_cell(ws, r, 2, value, fmt=fmt, bold=True, bg=GRAY)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    # Forward-Looking Metrics (From Today) -- FCV/EFTR are the future-only
    # counterparts of LCV/ELTR: everything already elapsed as of today is
    # excluded, and present value is taken from today rather than plan_start.
    # Kept as its own labeled sub-section rather than folded into Headline
    # Numbers above, since it answers a different question ("from here
    # forward") than the whole-lifetime headline figures.
    r += 1
    write_hdr(ws, r, 1, 'Forward-Looking Metrics (From Today)', NAVY, WHITE, span=6); r += 1
    future_metrics = compute_future_lcv_and_eftr(c, rows)
    for label, value, fmt in [
        ('Future Consumption Value (FCV, from today)', future_metrics.get('fcv', 0.0), FMT_DOLLAR),
        ('Effective Future Tax Rate (EFTR, from today)', future_metrics.get('eftr', 0.0), FMT_PCT),
    ]:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, value, fmt=fmt, bold=True, bg=GRAY)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    # Recommendations
    r += 1
    write_hdr(ws, r, 1, 'Priority Recommendations & Action Items', ORANGE, WHITE, span=6); r+=1
    hdrs = ['#','Recommendation','Rationale','Est. Cost ($/yr)','Est. Value ($/yr)','Source Sheet']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r+=1
    # #244: each candidate recommendation is paired with whether the plan is
    # ALREADY configured exactly as recommended -- those don't get a numbered
    # row (recommending what's already done isn't a priority action item).
    # Rows are renumbered sequentially after filtering, so there's no gap
    # where an excluded item used to sit.
    entity_label = {'s_corp': 'S-Corp', 'sole_prop': 'Sole Prop', 'w2': 'W2'}.get(
        str(c.get('entity', '')).strip().lower(), str(c.get('entity', '')).strip() or 'Sole Prop')
    # Same source as Sheet 14's own CST block, so the two can never disagree.
    # Previously '$4M'/'~$320K' were hardcoded here, then a flat 8% of the
    # funding amount -- both published without ever asking whether THIS
    # household's projected estate exceeds the exemption. It now returns None
    # (and the row below does not render at all) when the trust is not a live
    # planning question for this estate; see finding F2, SYSTEM_REVIEW
    # 2026-08-31. require_enabled=False because the whole point of the
    # recommendation row is that the trust is not yet in place.
    _cst = summary_figures.credit_shelter_trust_savings(c, rows, require_enabled=False)
    # Item 2.11: generalizes 1.10/F2's materiality gating to the QTIP row --
    # previously fired purely on `not c.get('qtip_enabled')`, with no
    # reference to whether this household's estate is even a federal
    # estate-tax question. A QTIP trust with nothing behind it to shelter
    # is not a recommendation; it is noise.
    _qtip_estate, _qtip_fed_exempt, _qtip_exposed = summary_figures.federal_estate_materiality(c, rows)
    if _cst and _cst['tax_saved'] is not None:
        _cst_value = (f"~${_cst['tax_saved']:,.0f} state estate tax avoided on the "
                      f"${_cst['funding_amount']:,.0f} bypass amount "
                      f"({_cst['avg_rate']:.1%} effective rate on the projected "
                      f"${_cst['projected_estate']:,.0f} estate)")
    elif _cst:
        # Near-miss band: worth recommending, but there is no dollar figure to
        # publish, so say why instead of printing a fabricated or $0 saving.
        _cst_value = (f"Projected estate ${_cst['projected_estate']:,.0f} is just under the "
                      f"${_cst['state_exemption']:,.0f} exemption — no tax sheltered at current "
                      f"projections, but the exemption is lost at first death without the trust")
    else:
        _cst_value = 'See Sheet 14'
    candidate_recs = [
        (True, 'Claim Social Security — ' + _ss_age_label,
           'Highest-scoring pair from the full 62-70 x 62-70 projection sweep on Sheet 10; weighs lifetime SS income against lifetime tax and IRMAA drag, not terminal net worth alone.',
           '$0', (f"~${_ss_best.get('delta_ss', 0.0):,.0f} more lifetime SS vs current configured claim age"
                   if _ss_best else 'See Sheet 10'), 'Sheet 10'),
        (True, 'Roth conversions through the configured conversion window',
           'Use the selected Roth strategy from Sheet 11; forced conversions are separated from voluntary optimizer choices.',
           'Tax cost depends on selected strategy','Compare candidate scores, lifetime tax, terminal value, and legacy/estate components on Sheet 11','Sheet 11'),
        # Materiality-gated (F2): fires only when the trust is not already in
        # place AND the projected second-death estate is at or near the state
        # exemption. Below that, the row is suppressed entirely rather than
        # shown with a $0 or a stale figure.
        (bool(_cst) and not c.get('cst_enabled'), 'Credit Shelter Trust at First Death',
           (f"Preserves the ${_cst['state_exemption']:,.0f} state exemption at first death; assets bypass "
            f"the survivor estate for state estate-tax purposes" if _cst else
            'Preserves the state estate-tax exemption at first death; assets bypass the survivor estate'),
           'Typical legal setup: $2,500–$5,000',
           _cst_value, 'Sheet 14'),
        (not (c.get('daf_amount', 0) or 0) > 0, 'DAF contribution in the highest-income planning year',
           'Fund a DAF in a high-income year to claim the deduction while SALT is still elevated, then grant out over following years',
           '$0 (charitable intent)','See Sheet 12 for the modeled deduction and carryforward','Sheet 12'),
        (not c.get('ltc_enabled'), 'Hybrid Life/LTC Policy',
           'Covers facility-care risk that would otherwise be self-funded from the portfolio',
           'Varies by age, health, and face value','See Sheet 17 for the modeled cost of self-funding care','Sheet 19'),
        (str(c.get('entity', '')).strip().lower() != 's_corp', f'S-Corporation vs LLC (Current: {entity_label})',
           'An S-Corp election splits earnings into reasonable W-2 salary and distributions, so self-employment tax applies only to the salary portion',
           'Added payroll/admin cost','See Sheet 9 for this household’s modeled SE tax','Sheet 9'),
        (not c.get('qtip_enabled') and _qtip_exposed, 'QTIP Trust to Manage Annuity Post-First-Death',
           'Annuity income flows to QTIP for survivor benefit; controls ultimate disposition to heirs',
           'Typical legal setup: $3,000–$5,000',
           (f"Qualifies for marital deduction; defers estate tax on the projected "
            f"${_qtip_estate:,.0f} estate against a ${_qtip_fed_exempt:,.0f} federal exemption"
            if _qtip_estate is not None else 'Qualifies for marital deduction; defers estate tax'),
           'Sheet 14'),
        (not any(float(entry.get('years_of_expenses', 0) or 0) > 0
                 for entry in (c.get('liquidity_buffer_schedule') or [])),
           'Set Reserve Requirement by Year Range',
           'Use start year, end year, and years of expenses to retain; default is 0 years',
           '$0 (allocation only)','Can reduce sequence-of-returns risk when a reserve is intentionally selected','Sheet 6'),
        (str(c.get('state', '')).strip().lower() == 'illinois', 'Illinois Residency Review',
           'Moving to a no-estate-tax state saves no income tax (IL already exempts retirement income) but can avoid IL estate tax',
           'Relocation costs',
           # The avoided tax here is the state estate tax on the WHOLE
           # projected estate, not the CST's marginal shelter -- reusing
           # tax_saved for it (as this row previously did) understated it.
           (f"~${_cst['estate_tax_without_cst']:,.0f} IL estate tax on the projected "
            f"${_cst['projected_estate']:,.0f} estate vs. the ${_cst['state_exemption']:,.0f} "
            f"exemption; no income tax savings" if _cst else 'See Sheet 13'), 'Sheet 13'),
    ]
    _tlh_rec = _tlh_recommendation_row(c, rows, 0)
    if _tlh_rec:
        candidate_recs.append((True,) + _tlh_rec[1:])
    recs = [(i,) + rec[1:] for i, rec in enumerate((r for r in candidate_recs if r[0]), 1)]
    for rec in recs:
        for i, val in enumerate(rec, 1):
            write_cell(ws, r, i, val, bold=(i==1), align='left' if i>1 else 'center')
        r+=1

    # Assumptions used in this build. Formerly headed "Release Notes", which
    # reads like a software changelog and is not what this block contains --
    # it is build provenance plus two modelling assumptions (finding D4,
    # SYSTEM_REVIEW_2026-08-31). The bullets are audited for internal config
    # paths at the same time: the auto-depreciation CSV pointer
    # ("Other Assets > Autos > depreciation_years") is genuinely useful to a
    # maintainer, so it moved to the QC sheet's Modeling Adjustments table
    # (sheets_qc_reference.build_sheet21) rather than being deleted. No other
    # bullet here names a file, CSV field, table, or code path.
    r+=1
    write_cell(ws, r, 1, 'Assumptions Used in This Build', bold=True, bg=LGRAY)
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
    r+=1
    _pricing_label, _pricing_note = _workbook_pricing_source_label()
    notes = [
        f"Built: {datetime.date.today()}",
        f"Workbook pricing source: {_pricing_label}. {_pricing_note}",
        "Annuity Model: Age-86 principal recovery; 20% dividends reinvested, 80% cash; flat guaranteed payment continues post-recovery",
        "Auto Depreciation: Straight-line over 7 years",
    ]
    for note in notes:
        write_cell(ws, r, 1, note, bg=GRAY)
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
        r+=1

    qc('1. Executive Summary','Headline numbers present', True, f"LCV: ${lcv:,.0f}")

def build_sheet2(ws, c, rows):
    """Assumptions & Tax Law"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'ASSUMPTIONS & TAX LAW — Editable Input Tables', 8)

    def write_section(start_row, title, items):
        r = start_row
        write_hdr(ws, r, 1, title, BLUE, WHITE, span=4); r+=1
        write_hdr(ws, r, 1, 'Parameter', DGRAY, WHITE)
        write_hdr(ws, r, 2, 'Value', DGRAY, WHITE)
        write_hdr(ws, r, 3, 'Units', DGRAY, WHITE)
        write_hdr(ws, r, 4, 'Note', DGRAY, WHITE); r+=1
        for label, value, units, note in items:
            write_cell(ws, r, 1, label, bg=LGRAY)
            cell = ws.cell(row=r, column=2, value=value)
            input_style(ws, cell)
            # Apply number format based on units
            if units in ('decimal', '%', 'pct'):
                cell.number_format = '0.0%'  # 0.025 → 2.5%
            elif units == 'USD':
                if isinstance(value, (int, float)) and value != float('inf'):
                    cell.number_format = '$#,##0'  # 23200 → $23,200
            elif units == 'years':
                cell.number_format = '0'
            write_cell(ws, r, 3, units)
            write_cell(ws, r, 4, note)
            r+=1
        return r+1

    r = 2
    _heard = c.get('model_heard_assumptions') or {}
    def _onoff(v):
        return 'On' if bool(v) else 'Off'
    def _pct(v):
        try:
            n = float(v or 0.0)
            if abs(n) <= 1.0:
                n *= 100.0
            return f'{n:.2f}%'
        except Exception:
            return 'not set'
    def _money(v):
        try:
            return f'${float(v or 0.0):,.0f}'
        except Exception:
            return 'not set'
    if _heard:
        _ss = _heard.get('social_security') or {}
        _hc = _heard.get('wellness') or {}
        _taxable = _heard.get('taxable_income') or {}
        _roth = _heard.get('roth_and_irmaa') or {}
        _estate = _heard.get('tax_and_estate') or {}
        _mc = _heard.get('monte_carlo') or {}
        _alloc = _heard.get('allocation') or {}
        _rep = _heard.get('reporting') or {}
        _cya = _heard.get('current_year_actuals') or {}
        if _cya:
            _remaining_pct = _pct(_cya.get('remaining_fraction'))
            if _cya.get('flows_blended'):
                _overrides = []
                if _cya.get('earned_remainder_overridden'):_overrides.append('earned income')
                if _cya.get('spend_remainder_overridden'):_overrides.append('spending')
                _override_note = f" Remainder-of-year {' and '.join(_overrides)} used a manual override instead of the linear pro-rated estimate." if _overrides else ''
                _cya_text = f"{_cya.get('current_year')}: income/spending actual through {_cya.get('ytd_end')}, projected for the remaining {_remaining_pct} of the year; account growth/contributions prorated to that same remainder.{_override_note}"
            elif _cya.get('flow_blend_skipped_by_user_choice'):
                _cya_text = f"{_cya.get('current_year')}: modeled as fully hypothetical by user choice (ytd_blend_enabled = FALSE) — real income/spending actuals tracked through {_cya.get('ytd_end')} were excluded; income/spending shown as a full-year projection. Account growth/contributions are still prorated to the remaining {_remaining_pct} of the year, since that proration is date math, not real-data blending."
            else:
                _cya_text = f"{_cya.get('current_year')}: account growth/contributions prorated to the remaining {_remaining_pct} of the year; income/spending shown as a full-year projection (add YTD actuals in Settings to blend real results)."
        else:
            _cya_text = 'Not available for this build.'
        _heard_items = [
            ('Current-year actuals blend', _cya_text, 'text', 'Action: keep YTD transactions and each account\'s Prior Year End Balance current every January so the current-year row reflects real results, not just a full-year assumption.'),
            ('Time horizon', _heard.get('plan_years'), 'text', 'Sets the years included in every income, tax, spending, and terminal-net-worth calculation.'),
            ('Social Security income', f"Claim ages {str(c.get('h_nick') or c.get('h_name') or 'Member 1')}/{str(c.get('w_nick') or c.get('w_name') or 'Member 2')}: {_ss.get('husband_claim_age')}/{_ss.get('wife_claim_age')}; funding haircut {_pct(_ss.get('funding_discount_pct'))} starting {_ss.get('funding_discount_year')}", 'text', 'Action: set the funding haircut to 0% for one scenario if you want to isolate this drag on terminal net worth.'),
            ('Wellness cash flow', f"Bridge monthly {_money(_hc.get('bridge_premium_monthly_today') or (float(_hc.get('bridge_premium_today') or 0)/12))}; Medicare B/D/G monthly {_money(float(_hc.get('part_b_monthly_today') or 0)+float(_hc.get('part_d_monthly_today') or 0)+float(_hc.get('part_g_monthly_today') or 0))}; OOP {_money(_hc.get('oop_estimate_today'))}; ACA PTC {_onoff(_hc.get('aca_ptc_enabled'))}", 'text', 'Action: if terminal net worth fell, temporarily zero bridge/Medicare/OOP costs to quantify wellness impact, then restore realistic values.'),
            ('Taxable portfolio income', _taxable.get('portfolio_distributions_mode'), 'text', 'Annual dividends/interest can raise AGI, Social Security taxation, IRMAA, NIIT, and reduce Roth-conversion room. Action: review asset location and distribution yields.'),
            ('Roth / IRMAA guardrails', f"Policy {_roth.get('roth_policy')}; IRMAA mode {_roth.get('irmaa_guardrail_mode')}; target {_roth.get('irmaa_target_tier')}; headroom {_pct(_roth.get('irmaa_headroom_usage_pct'))}", 'text', 'Action: if conversions look unexpectedly low, check the IRMAA guardrail and ACA PTC-loss weight before overriding the Roth policy.'),
            ('Estate and survivor treatment', f"Basis step-up {_onoff(_estate.get('basis_step_up_at_death'))}; CST {_onoff(_estate.get('credit_shelter_trust_enabled'))}; CST funded/excluded {_money(_estate.get('cst_funded_total'))}; portability {_onoff(_estate.get('federal_portability_enabled'))}", 'text', 'Action: compare one rebuild with CST or estate objective off if you need to isolate estate-policy impact.'),
            ('Monte Carlo risk mode', f"{_mc.get('engine_mode', 'not set')} with {_mc.get('simulation_count', 'not set')} main paths and {_mc.get('sensitivity_simulation_count', 'not set')} sensitivity paths", 'text', 'Action: raise path counts for final advisor review; raise max_build_seconds if exact scalar MC runs too long.'),
            ('Allocation and real-dollar reporting', f"Allocation mode {_alloc.get('selection_mode')}; real-dollar rows {_onoff(_rep.get('real_dollar_rows_available'))} using base year {_rep.get('real_dollar_base_year')}", 'text', 'Action: use real-dollar outputs for purchasing-power comparisons and nominal outputs only for like-for-like workbook runs.'),
        ]
        r = write_section(r, 'What the Model Used — Plain-English Impact Checks', _heard_items)

    r = write_section(r, 'Economic Assumptions', [
        ('Inflation (General)',        c['inf'],       'decimal', '2.50% annual'),
        ('SS COLA',                    c['ss_cola'],   'decimal', '2.00% annual'),
        ('Medicare Inflation',         c['med_inf'],   'decimal', '5.50% annual'),
        ('Portfolio Nominal Return',   c['ret'],       'decimal', 'No-volatility deterministic reference return; MC may use asset-class covariance and sampled geometric returns'),
        ('Fed Bracket Inflator',       c['brk_inf'],   'decimal', '2.00%/yr'),
        ('SS Taxable Fraction',        c['ss_taxable'],'decimal', '85%'),
        ('Roth Conversion Target Bracket', c['roth_brk'], 'decimal', 'Configured target bracket used when the selected strategy fills bracket headroom.'),
        ('Roth Legacy Objective Mode', c.get('roth_legacy_objective_mode', 'OFF'), 'text', 'OFF, LOW, BALANCED, or STRONG; weights future tax-rate risk and inheritance tax burden in Roth conversion selection.'),
        ('Roth Future Tax Stress', c.get('roth_future_tax_rate_stress_pct', 0.0), 'decimal', 'Additional ordinary-tax-rate stress used only in the Roth conversion objective.'),
        ('Assumed Heir Filing Status', c.get('roth_heir_filing_status', 'Single'), 'text', 'Beneficiary filing status assumed when deriving the effective inherited-IRA tax rate below.'),
        ('Heir Ordinary Tax Rate (effective)',
         (c.get('roth_heir_ordinary_tax_rate_effective') or c.get('roth_heir_ordinary_tax_rate_assumption', 0.0)),
         'decimal',
         'Effective ordinary rate on inherited pre-tax (IRA/401k) balances, used to score the Roth objective. Derived per SECURE Act 10-year rule: the terminal pre-tax balance is spread level over 10 years and each slice taxed at the assumed heir filing status, so a larger balance scores a higher rate than a flat 24% would. An explicit assumption override, if set, is honored instead.'),
    ])

    # Version 7.5.2: make optimizer assumptions visible in the workbook. These
    # values affect the recommended allocation engine only. They do not change
    # deterministic projection return, Monte Carlo return distribution, or live
    # market pricing unless those separate assumptions are edited.
    _cm_diag = _ao.apply_capital_market_config(c)
    _asset_items = [
        ('Capital Market Assumption Mode', _cm_diag.get('assumption_mode', 'PRESET'), 'text', 'PRESET uses built-in selectable horizon/preset assumptions; CUSTOM_FILE reads expert CSV assumptions.'),
        ('Capital Market Horizon', _cm_diag.get('horizon_years', 30), 'years', 'Supported horizons: 1, 3, 5, 10, 20, 25, 30 years. 30 is the long-term baseline.'),
        ('Capital Market Preset', _cm_diag.get('preset', 'BASELINE'), 'text', 'CONSERVATIVE, BASELINE, or AGGRESSIVE. These are planning assumptions, not live forecasts.'),
        ('Correlation Mode', _cm_diag.get('correlation_assumption_mode', 'PRESET'), 'text', 'PRESET, ADVANCED, or CUSTOM_FILE. Pairwise correlations affect diversification benefit.'),
        ('Correlation Preset', _cm_diag.get('correlation_preset', 'MODERATE'), 'text', 'LOW, MODERATE, HIGH, or STRESS. Stress assumes weaker diversification.'),
    ]
    _targets = _ap.normalize_targets(c.get('allocation_target_pct') or getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}))
    _target_sum = c.get('allocation_target_sum', sum(_targets.values()))
    _alloc_mode = _ap.normalize_allocation_mode(c.get('allocation_selection_mode', 'user_target'))
    _alloc_source_label = 'Optimizer-defined allocation' if _alloc_mode == _ap.ALLOCATION_MODE_OPTIMIZER else 'User-defined allocation'
    _pricing_label, _pricing_note = _workbook_pricing_source_label()
    _asset_items.append(('Workbook Pricing Source', _pricing_label, 'text',
                         _pricing_note or 'Actual quote source used for this workbook build.'))
    _asset_items.append(('Asset Allocation Recommendation Source', _alloc_source_label, 'text',
                         f'Selected in the UI and stored in Plan Data CSV as allocation_selection_mode={_alloc_mode}; this drives the workbook asset allocation recommendations.'))
    _asset_items.append(('Allocation Selection Mode', _ap.allocation_mode_label(_alloc_mode), 'text',
                         'UI toggle: use the optimizer recommendation or use the user-specified target_pct allocation.'))
    _asset_items.append(('Optimizer Recommendation Basis', 'Visible as recommendation', 'text',
                         getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', '')) )
    _asset_items.append(('User-Specified Allocation Total', _target_sum, 'decimal',
                         'Must equal 100%. If selected as the allocation mode, these target_pct rows drive allocation recommendations.'))
    _override_targets = c.get('allocation_optimizer_override_pct') or {}
    _override_sum = c.get('allocation_optimizer_override_sum', sum(float(v or 0) for v in _override_targets.values()) if isinstance(_override_targets, dict) else 0.0)
    _asset_items.append(('Optimizer Override Total', _override_sum, 'decimal',
                         '0% or blank means the computed optimizer target is used. If any optimizer override is entered, override percentages must total 100%.'))
    for _cls in getattr(_ap, 'DEFAULT_ALLOCATION_TARGETS', {}):
        _ov = float((_override_targets or {}).get(_cls, 0.0) or 0.0)
        _asset_items.append((f'Optimizer Override — {_cls}', _ov, 'decimal',
                             'Optional optimizer-mode override. If any override row is nonzero, the optimizer override replaces the computed optimizer target and must total 100%.'))
    for _cls, _pct in _targets.items():
        _defs = _ao.ASSET_CLASSES.get(_cls, {})
        _examples = ', '.join(_ap.ETF_CANDIDATES.get(_cls, [])[:3])
        _edu_note = _defs.get('education', '') if isinstance(_defs, dict) else ''
        _asset_items.append((f'User Target — {_cls}', _pct, 'decimal',
                             f'{_ap.default_note(_cls)} User may override this percentage; all target_pct rows must total 100%. {_edu_note}'))
        if _examples:
            _asset_items.append((f'{_cls} Example Vehicles', _examples, 'text',
                                 'Three examples used when the class is recommended but not currently represented. These are examples, not personalized trade instructions.'))
    try:
        _optimizer_view = _ao.compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER, projection_rows=rows)
        for _cls, _pct in (_optimizer_view.get('liquid_targets') or {}).items():
            _asset_items.append((f'Optimizer Target — {_cls}', _pct, 'decimal',
                                 'Computed recommendation using risk tolerance, withdrawal rate, guaranteed-income/home-equity coverage, capital-market assumptions, correlations, glide path, and inflation-sensitive spending.'))
    except Exception as _ex:
        _asset_items.append(('Optimizer Target Snapshot', 'Unavailable', 'text', str(_ex)))
    r = write_section(r, 'Asset Allocation Selection and Recommendations', _asset_items)

    _reb = _rebalance_settings(c)
    r = write_section(r, 'Global Tax-Location Rebalancing Controls', [
        ('Trade Optimizer Mode', _reb['mode'], 'text', 'GLOBAL_TAX_AWARE solves household-level drift/tax/location tradeoffs; HEURISTIC uses the prior account-by-account engine.'),
        ('Objective', 'Minimize drift + tax cost + turnover + location inefficiency', 'text', 'A conservative linear objective balances diversification against taxes, turnover, and account-location fit.'),
        ('Maximum Turnover', _reb['max_turnover_pct'], 'decimal', 'Addresses unintended consequence: excessive turnover and noisy small improvements.'),
        ('Minimum Trade Amount', _reb['min_trade_amount'], 'USD', 'Addresses false precision and operational burden.'),
        ('Taxable Gain Policy', _reb['taxable_gain_policy'], 'text', 'NEVER, DRIFT_THRESHOLD, WITHIN_BUDGET, or ALWAYS; controls tax tail wagging the dog and income-timing effects.'),
        ('Taxable Gain Budget', _reb['taxable_gain_budget_annual'], 'USD', 'Limits estimated tax cost from taxable gain sales in one workbook cycle.'),
        ('Max Tax Cost', _reb['max_tax_cost_bps'], 'bps', 'Basis-point tax-drag limit for taxable sales before deferral.'),
        ('Asset Location Strength', _reb['asset_location_strength'], 'text', 'LIGHT/BALANCED/STRONG controls how hard the optimizer pushes Roth growth, pre-tax income assets, and taxable tax-efficient equity.'),
        ('Max Account Single Asset', _reb['max_account_single_asset_pct'], 'decimal', 'Reduces account-level concentration risk.'),
        ('Max Roth High-Growth Tilt', _reb['max_roth_high_growth_pct'], 'decimal', 'Limits unintended high-volatility concentration in Roth accounts.'),
        ('Annuity calibration dependency', 'Carrier-illustration dependent', 'text', 'PV/reserve and death-benefit figures use editable calibration assumptions; refresh against current carrier illustrations before annuity sale, replacement, or valuation decisions.'),
        ('Max Pre-Tax Fixed Income Tilt', _reb['max_pre_tax_fixed_income_pct'], 'decimal', 'Limits unintended bond-heavy pre-tax allocation and future RMD concentration risk.'),
        ('Wash-Sale Policy', _reb['wash_sale_policy'], 'text', 'Workbook flags review items; it does not certify wash-sale compliance or see outside/spousal trades.'),
        ('Solver Fallback Policy', _reb['solver_fallback_policy'], 'text', 'HEURISTIC keeps workbook usable if the global optimization problem is infeasible.'),
    ])

    r = write_section(r, 'Federal Tax Brackets — Tax Reference Year', [
        ('10% bracket top',     23200,  'USD', 'inflates at bracket inflator'),
        ('12% bracket top',     94300,  'USD', ''),
        ('22% bracket top',    201050,  'USD', ''),
        ('24% bracket top',    383900,  'USD', ''),
        ('32% bracket top',    487450,  'USD', ''),
        ('35% bracket top',    731200,  'USD', ''),
        ('37%+',               float('inf'), 'USD', ''),
    ])

    r = write_section(r, 'SALT Cap Schedule', [
        ('2025 SALT Cap', 40000, 'USD', 'Phase-down: max(cap - 0.30×max(MAGI-500K,0), 10000)'),
        ('Reference-Year SALT Cap', 40400, 'USD', ''),
        ('2027 SALT Cap', 40804, 'USD', ''),
        ('Reference-Year + 2 SALT Cap', 41212, 'USD', ''),
        ('Reference-Year + 3 SALT Cap', 41624, 'USD', ''),
        ('Post-Schedule SALT Cap', 10000, 'USD', 'REVERTS to $10K — model must honor this'),
    ])

    if c.get('cs_enabled'):
        _il_exempt_note = f'Plus up to ${c.get("il_cst_shelter_cap", 0):,.0f} shelterable via a funded Credit Shelter Trust (separate from this exemption), cliff structure'
    else:
        _il_exempt_note = 'No portability, cliff structure'
    r = write_section(r, 'Other Statutory Parameters', [
        ('§121 Exclusion (MFJ)',         500000,   'USD', 'Home sale gain exclusion'),
        ('QCD Annual Limit (per person)', 108000,   'USD', '2025, indexed'),
        ('Federal Estate Exemption (MFJ)',30000000, 'USD', 'Indexed from the tax reference year'),
        ('IL State Estate Exemption',     c['il_exempt'],  'USD', _il_exempt_note),
        ('Annual Gift-Tax Exclusion',     19000,    'USD', 'tax reference year, per donee'),
        ('RMD Start Age',                 75,       'years','SECURE 2.0 §107 ramp: 72 (born ≤1950), 73 (born 1951–1959), 75 (born 1960+)'),
        ('NIIT Rate',                     0.038,    'decimal','3.8% on NII above MAGI threshold'),
        ('NIIT MAGI Threshold (MFJ)',     250000,   'USD', 'NOT indexed'),
        ('Standard Deduction MFJ — Reference Year',  31500,    'USD', '+ $1,650/spouse age 65+'),
        ('IRMAA Tier 2 Threshold (MFJ)', 268000,   'USD', 'reference-year threshold, inflated annually'),
    ])

    # Projected brackets table (simplified)
    r += 1
    write_hdr(ws, r, 1, 'Projected Target-Bracket Reference — MFJ', NAVY, WHITE, span=6); r+=1
    write_hdr(ws, r, 1, 'Year', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Reference Bracket Top', DGRAY, WHITE)
    r += 1
    for yr in range(c['plan_start'], min(c['plan_end']+1, c['plan_start']+31)):
        top = 201050 * (1+c['brk_inf'])**(yr - TAX_BASE_YEAR)
        write_cell(ws, r, 1, yr, fmt=FMT_YEAR, align='center')
        write_cell(ws, r, 2, top, fmt=FMT_DOLLAR)
        r += 1

    qc('2. Assumptions', 'All major parameters in editable cells', True, '')


__all__ = ['build_sheet1', 'build_sheet2']
