from .workbook_common import *
from ..person_labels import display_accounts_in_text as _display_accounts_in_text
def build_sheet9(ws, c, rows):
    """Retirement Strategy"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'RETIREMENT STRATEGY & INVESTMENT POLICY STATEMENT', 8)

    content = [
        ('WITHDRAWAL SEQUENCE STRATEGY', [
            ('Phase 1: Pre-SS / Pre-RMD',
             'Draw from: RMDs (mandatory), Trust headroom above liquidity buffer, '
             'Roth (tax-free). Defer IRA withdrawals. Execute Roth conversions only under the selected strategy and configured guardrails.'),
            ('Phase 2: Post-SS / Pre-RMD',
             'Social Security begins. Reduce taxable draws. Continue Roth conversions through the configured window.'),
            ('Phase 3: RMD Era (2037+)',
             'RMDs from IRAs drive income. Supplement with SS, annuities, Trust. '
             'Use QCDs for charitable giving to reduce AGI.'),
        ]),
        ('INVESTMENT POLICY STATEMENT', [
            ('Return Objective', f'{c["ret"]:.1%} nominal; ~{c["ret"]-c["inf"]:.1%} real'),
            ('Risk Tolerance', 'Moderate-aggressive; long horizon and annuity income reduce sequence risk'),
            ('Asset Allocation Target',
             '35% US Large | 10% US Small | 25% Intl Dev | 5% Intl Emg | 10% Commodities | 10% Cash | 5% Other'),
            ('Rebalancing', 'Annual review; rebalance when any bucket drifts >±5 percentage points'),
            ('Asset Location', 'Bonds/REIT/Commodities → IRA; High-growth small-cap → Roth; '
             'Tax-efficient equity → Trust'),
        ]),
        ('KEY RISKS & MITIGATIONS', [
            ('Longevity Risk', 'Modeled to age 92/95; annuities provide floor income for life'),
            ('Sequence-of-Returns', 'configurable reserve requirement can retain selected years of expenses; default is 0'),
            ('Long-Term Care', 'LTC stress test on Sheet 17; no LTC policy in force — consider hybrid life/LTC'),
            ('Premature Death', 'Survivor analysis on Sheet 18; joint annuities continue at 100% J&S'),
            ('Inflation Regime', 'Base case 2.5%; stress test at 4.5% on Sheet 16'),
            ('Illinois Residency', 'Estate exposure above $4M IL exemption; see Sheet 13 & 14'),
            ('Concentrated/Illiquid Holdings',
             'Startup equity $66K at 2%/yr — illiquid; annuity death benefits decline to $0 by 2042'),
        ]),
    ]

    r = 3
    for section_hdr, items in content:
        write_hdr(ws, r, 1, section_hdr, NAVY, WHITE, span=6); r+=1
        for label, detail in items:
            write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
            write_cell(ws, r, 2, detail)
            ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=6)
            r += 1
        r += 1

    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 80


    # S-Corp vs LLC comparison section
    r += 1
    section_title(ws, r, 'S-CORPORATION vs. LLC — ENTITY COMPARISON FOR MATTHEW', bg='2E75B6', span=8); r += 1

    # Current entity detection
    entity = c.get('entity','s_corp')
    salary = c.get('scorp_salary', 80000)
    gross  = c.get('earned', 290000)
    net_se = gross - c.get('biz_exp',0) - c.get('home_off',0)
    dist   = max(0, net_se - salary)   # S-Corp distribution (not subject to SE tax)
    se_tax_savings = dist * 0.153      # approx SE/payroll tax avoided on distribution

    comparison_rows = [
        ('Category',                   'S-Corporation (CURRENT)',                  'Sole-Prop / Single-Member LLC'),
        ('SE / Payroll Tax Base',       f'Salary only (${salary:,.0f}/yr)',         f'Full net income (~${net_se:,.0f}/yr)'),
        ('SE Tax Savings vs SMLLC',     f'~${se_tax_savings:,.0f}/yr',              'Baseline (max SE tax)'),
        ('QBI Deduction',               '20% of W-2 wages + allocable basis',       '20% of net income (simpler)'),
        ('Reasonable Compensation',     f'Required (${salary:,.0f} set in CSV)',     'Not applicable'),
        ('Administrative Cost',         '$1,500–$3,000/yr (payroll, returns)',       '$200–$500/yr (simpler)'),
        ('Illinois Corp Surcharge',     f'{c.get("scorp_state_rate",0.015):.1%} on taxable income', 'None'),
        ('SEHI Deduction',              'Added to W-2 box 1; deducted via Sch 1',   'Deducted directly on Sch 1'),
        ('Retirement Contributions',    'Up to $70K total (employer + employee)',    'Same cap'),
        ('Audit Risk',                  'Moderate (reasonable salary scrutiny)',     'Higher SE income triggers'),
        ('Recommended at this income',  '★ YES — net savings ~${:,.0f}/yr'.format(max(0, se_tax_savings - 2500)),
                                        'Not recommended above $100K net income'),
    ]

    write_hdr(ws, r, 1, 'Category',               DGRAY, WHITE, span=3)
    write_hdr(ws, r, 4, 'S-Corporation (Current)', BLUE,  WHITE, span=3)
    write_hdr(ws, r, 7, 'LLC / Sole-Prop',         ORANGE,WHITE, span=2); r += 1

    for row_data in comparison_rows:
        cat, scorp, llc = row_data
        if cat == 'Category':
            continue
        is_rec = '★' in scorp or '★' in llc
        bg = 'E2EFDA' if is_rec else (LGRAY if comparison_rows.index(row_data) % 2 == 1 else None)
        write_cell(ws, r, 1, cat,   bold=True, bg=bg or LGRAY)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        write_cell(ws, r, 4, scorp, bg='E2EFDA' if '★' in scorp else bg)
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
        write_cell(ws, r, 7, llc,   bg='FCE4D6' if '★' in scorp else bg)
        ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=8)
        r += 1

    r += 1
    note = (f'At ${gross:,.0f} gross income with ${salary:,.0f} reasonable salary, '
            f'the S-Corp saves approximately ${se_tax_savings:,.0f} in payroll taxes '
            f'less ~$2,500 in administrative overhead = net ${max(0,se_tax_savings-2500):,.0f}/yr benefit. '
            f'Illinois {c.get("scorp_state_rate",0.015):.1%} corporate surcharge applies on distributable income. '
            'Annuity PV/reserve figures elsewhere in the workbook are calibration-dependent and should be refreshed against current carrier illustrations before sale/replacement decisions.')
    write_cell(ws, r, 1, note, bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    r += 1

    qc('9. Retirement Strategy', 'Withdrawal cascade and key risks documented', True, '')


def build_sheet10(ws, c, rows):
    """Social Security Timing — full spouse-pair projection sweep."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'SOCIAL SECURITY CLAIMING STRATEGY', 10)

    from ..planning_engines import project, monte_carlo
    import copy as _copy
    import contextlib as _contextlib
    import io as _io

    # Reduced-cost Monte Carlo settings for the sweep only: fewer paths and a
    # single-sim sensitivity grid (the grid always runs, so this is the
    # cheapest way to neutralize its cost) keep 81 MC runs fast. A single
    # fixed seed is reused for every pair so all pairs see the same simulated
    # market/mortality paths - differences in success rate/percentile are
    # then attributable to the claim-age choice, not random noise.
    SWEEP_MC_SIMS = 200
    SWEEP_MC_SEED = 4242

    base_rows = list(rows or [])
    base_terminal = float(base_rows[-1].get('total_nw', 0.0) or 0.0) if base_rows else 0.0
    base_tax = sum(float(r.get('total_tax', 0.0) or 0.0) for r in base_rows)
    base_ss = sum(float(r.get('h_ss', 0.0) or 0.0) + float(r.get('w_ss', 0.0) or 0.0) for r in base_rows)
    h_current = int(c.get('h_ss_claim_age', c.get('ss_claim_age', 70)) or 70)
    w_current = int(c.get('w_ss_claim_age', c.get('ss_claim_age', 70)) or 70)

    def _safe_project_pair(h_age, w_age):
        c2 = _copy.deepcopy(c)
        c2['h_ss_claim_age'] = int(h_age)
        c2['w_ss_claim_age'] = int(w_age)
        # Preserve the currently selected Roth policy so the sweep compares SS
        # timing through the same full projection engine without recursively
        # re-optimizing Roth conversions 81 times during workbook generation.
        if str(c2.get('roth_policy', '')).lower() in ('optimize', 'optimize_terminal_tax', 'terminal_tax_optimize', 'balanced_optimize'):
            c2['roth_policy'] = c2.get('roth_optimized_policy') or 'fill_to_bracket'
        c2.pop('plan_result', None)
        c2.pop('roth_strategy_result', None)
        proj_rows = project(c2)
        terminal = float(proj_rows[-1].get('total_nw', 0.0) or 0.0) if proj_rows else 0.0
        lifetime_tax = sum(float(r.get('total_tax', 0.0) or 0.0) for r in proj_rows)
        lifetime_ss = sum(float(r.get('h_ss', 0.0) or 0.0) + float(r.get('w_ss', 0.0) or 0.0) for r in proj_rows)
        irmaa = sum(float(r.get('irmaa', 0.0) or 0.0) for r in proj_rows)
        survivor_years = sum(1 for r in proj_rows if (float(r.get('h_ss', 0.0) or 0.0) == 0.0) != (float(r.get('w_ss', 0.0) or 0.0) == 0.0))
        # Score on after-tax terminal wealth plus lifetime SS and explicit tax/
        # IRMAA drag. The sheet reports the components so the recommendation is
        # transparent rather than hard-coded to age 70.
        score = terminal + lifetime_ss - lifetime_tax - irmaa
        # Informational-only probabilistic metrics: do NOT feed the score or
        # the recommendation above. Delaying SS is fundamentally a longevity/
        # market-risk hedge that a single deterministic mortality assumption
        # can't show; these columns surface that without replacing the
        # deterministic ranking this sheet has always used.
        mc_success_rate = None
        mc_p10_terminal_nw = None
        try:
            c2['mc_sims'] = SWEEP_MC_SIMS
            c2['mc_sensitivity_sims'] = 1
            with _contextlib.redirect_stdout(_io.StringIO()):
                mc_result = monte_carlo(c2, n_sims=SWEEP_MC_SIMS, seed=SWEEP_MC_SEED)
            mc_success_rate = float(mc_result.get('success_rate', 0.0) or 0.0)
            mc_p10_terminal_nw = float((mc_result.get('terminal_total_nw') or {}).get(10, 0.0) or 0.0)
        except Exception:
            pass
        return {
            'h_age': int(h_age), 'w_age': int(w_age), 'terminal_nw': terminal,
            'lifetime_tax': lifetime_tax, 'lifetime_ss': lifetime_ss,
            'irmaa': irmaa, 'survivor_years': survivor_years, 'score': score,
            'delta_terminal': terminal - base_terminal,
            'delta_tax': lifetime_tax - base_tax,
            'delta_ss': lifetime_ss - base_ss,
            'mc_success_rate': mc_success_rate,
            'mc_p10_terminal_nw': mc_p10_terminal_nw,
        }

    scenarios = []
    for h_age in range(62, 71):
        for w_age in range(62, 71):
            scenarios.append(_safe_project_pair(h_age, w_age))
    scenarios.sort(key=lambda d: d['score'], reverse=True)
    best = scenarios[0] if scenarios else {'h_age': h_current, 'w_age': w_current, 'score': 0.0}
    current = next((x for x in scenarios if x['h_age'] == h_current and x['w_age'] == w_current), None)

    r = 3
    write_hdr(ws, r, 1, 'Recommended spouse-pair claim ages from full projection sweep', NAVY, WHITE, span=12); r += 1
    _s1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _s2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    summary = [
        (f'Recommended {_s1} Claim Age', best['h_age'], 'Highest score from the 62–70 × 62–70 projection sweep.'),
        (f'Recommended {_s2} Claim Age', best['w_age'], 'Projection uses the same tax, IRMAA, withdrawal, ACA, survivor, and estate machinery as the base plan.'),
        ('Current Configured Claim Ages', f"{_s1} {h_current} / {_s2} {w_current}", 'Current row shown below for comparison.'),
        ('Best vs Current Terminal NW', (best['terminal_nw'] - (current or best)['terminal_nw']) if current else 0.0, 'Positive means the sweep’s selected pair improves terminal net worth versus current config.'),
        ('Best vs Current Lifetime Tax', (best['lifetime_tax'] - (current or best)['lifetime_tax']) if current else 0.0, 'Negative means lower lifetime tax versus current config.'),
    ]
    for label, value, note in summary:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, value, fmt=FMT_DOLLAR if isinstance(value, (int, float)) and 'Age' not in label else None)
        write_cell(ws, r, 3, note)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=12)
        r += 1

    r += 1
    write_hdr(ws, r, 1, 'Top 10 claiming pairs — full projection ranking', NAVY, WHITE, span=12); r += 1
    hdrs = ['Rank', 'H Claim', 'W Claim', 'Score', 'Terminal NW', 'Δ Terminal NW', 'Lifetime SS', 'Δ Lifetime SS', 'Lifetime Tax', 'IRMAA', 'MC Success %', 'MC P10 Terminal NW']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for rank, sc in enumerate(scenarios[:10], 1):
        vals = [rank, sc['h_age'], sc['w_age'], sc['score'], sc['terminal_nw'], sc['delta_terminal'], sc['lifetime_ss'], sc['delta_ss'], sc['lifetime_tax'], sc['irmaa'], sc.get('mc_success_rate'), sc.get('mc_p10_terminal_nw')]
        bg = 'E2EFDA' if rank == 1 else ('F4F5F7' if sc is current else None)
        for i, val in enumerate(vals, 1):
            fmt = FMT_PCT if i == 11 else (FMT_DOLLAR if i >= 4 else None)
            write_cell(ws, r, i, val, fmt=fmt, bg=bg)
        r += 1

    r += 2
    write_hdr(ws, r, 1, 'Complete 62–70 × 62–70 spouse-pair sweep', NAVY, WHITE, span=12); r += 1
    hdrs = ['H Claim', 'W Claim', 'Score', 'Terminal NW', 'Δ Terminal NW', 'Lifetime SS', 'Δ Lifetime SS', 'Lifetime Tax', 'IRMAA', 'Survivor Years', 'MC Success %', 'MC P10 Terminal NW']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for sc in sorted(scenarios, key=lambda d: (d['h_age'], d['w_age'])):
        vals = [sc['h_age'], sc['w_age'], sc['score'], sc['terminal_nw'], sc['delta_terminal'], sc['lifetime_ss'], sc['delta_ss'], sc['lifetime_tax'], sc['irmaa'], sc['survivor_years'], sc.get('mc_success_rate'), sc.get('mc_p10_terminal_nw')]
        bg = 'E2EFDA' if sc is best else ('F4F5F7' if sc is current else None)
        for i, val in enumerate(vals, 1):
            fmt = FMT_PCT if i == 11 else (FMT_DOLLAR if i in (3,4,5,6,7,8,9,12) else None)
            write_cell(ws, r, i, val, fmt=fmt, bg=bg)
        r += 1

    r += 1
    note = ('This sheet runs every husband/wife claiming-age pair from 62 through 70 through the projection engine. '
            'It does not use a static break-even table or a hard-coded age-70 answer. Results remain sensitive to the selected Roth policy, mortality assumptions, ACA/IRMAA interactions, and survivor-benefit settings. '
            f'MC Success % and MC P10 Terminal NW are informational Monte Carlo metrics ({SWEEP_MC_SIMS} paths per pair, one fixed seed reused across all pairs for apples-to-apples comparison, minimal sensitivity grid) — '
            'they do not affect the score or recommendation above; a full-precision Monte Carlo run for the recommended pair is on Sheet 15.')
    write_cell(ws, r, 1, note, bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=12)

    for col in range(1, 13):
        ws.column_dimensions[get_column_letter(col)].width = 16
    qc('10. Social Security', 'Claim ages 62-70 swept by spouse against full projection', True, '')

    return {'best': best, 'current': current, 'scenarios': scenarios}

def build_sheet11(ws, c, rows):
    """Roth Conversion Plan — canonical strategy contract and diagnostics."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'ROTH CONVERSION PLAN — Canonical Strategy Result', 14)

    r = 3
    contract = c.get('roth_strategy_result') or (c.get('plan_result') or {}).get('roth_strategy_result') or {}
    ropt = c.get('roth_optimization', {}) or {}
    selected_label = contract.get('selected_strategy_name') or ropt.get('selected_label', c.get('roth_policy',''))
    target_rate = float(contract.get('target_bracket', ropt.get('target_bracket', c.get('roth_target_rate', 0.22))) or 0.22)

    auto_optimized = bool(contract.get('auto_optimized', ropt.get('auto_optimized', True)))
    write_hdr(ws, r, 1, 'AUTO-OPTIMIZED ROTH CONVERSION STRATEGY — WHY THIS STRATEGY WAS SELECTED', NAVY, WHITE, span=14); r += 1
    write_cell(ws, r, 1, 'Selected Strategy', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, selected_label, bold=True)
    write_cell(ws, r, 4, 'Objective Mode', bold=True, bg=LGRAY)
    write_cell(ws, r, 5, contract.get('objective_mode', ropt.get('objective_mode','BALANCED_RETIREMENT')))
    write_cell(ws, r, 7, 'Target Bracket', bold=True, bg=LGRAY)
    write_cell(ws, r, 8, target_rate, fmt=FMT_PCT)
    r += 1
    write_cell(ws, r, 1, 'Explanation', bold=True, bg=LGRAY)
    default_why = ('The optimizer selected the top total objective score from the candidate strategy table below.' if auto_optimized
                   else 'This strategy was explicitly selected by the user rather than chosen by the optimizer. The table below shows how it compares to the optimizer-scored alternatives.')
    why = contract.get('why_selected') or default_why
    write_cell(ws, r, 2, why, align='left')
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=14)
    ws.row_dimensions[r].height = 42
    r += 1
    write_cell(ws, r, 1, 'Conversion Totals', bold=True, bg=LGRAY)
    explanation = contract.get('explanation') or (
        f"Forced/user-directed conversions are shown separately from optimizer-selected voluntary conversions. "
        f"The strategy uses {float(c.get('roth_headroom_usage_pct',0.95)):.0%} tax-bracket headroom and "
        f"{float(c.get('roth_irmaa_headroom_usage_pct',0.95)):.0%} IRMAA headroom."
    )
    write_cell(ws, r, 2, explanation, align='left')
    ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=14)
    ws.row_dimensions[r].height = 38
    r += 2

    # Candidate table with transparent score components.
    candidates = contract.get('candidates') or ropt.get('candidates') or []
    write_hdr(ws, r, 1, 'Candidate Strategy Comparison — Score Components and Rejection Reasons', NAVY, WHITE, span=14); r += 1
    cand_hdrs = [
        'Rank', 'Candidate', 'Policy', 'Total Score', 'Terminal Wealth Score', 'Tax Efficiency Score',
        'Roth Legacy Score', 'Estate-Tax Score', 'Survivor-Risk Score', 'Liquidity Score',
        'Conversions', 'Lifetime Tax', 'After-Tax Terminal NW', 'Why selected / rejected'
    ]
    for i, h in enumerate(cand_hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE, size=8)
    r += 1
    for idx, cand in enumerate(candidates[:10], 1):
        # Candidate may be a dataclass-asdict contract row or the older raw optimizer row.
        rank = cand.get('rank', idx)
        label = cand.get('label') or cand.get('selected_strategy_name') or cand.get('Candidate')
        why_text = cand.get('why_selected_or_rejected') or ('Selected candidate.' if idx == 1 else 'Not selected: lower total objective score.')
        vals = [
            rank,
            label,
            cand.get('policy',''),
            cand.get('total_objective_score', cand.get('score')),
            cand.get('terminal_wealth_score', cand.get('terminal_component', 0.0)),
            cand.get('tax_efficiency_score', cand.get('tax_component', 0.0)),
            cand.get('roth_legacy_score', cand.get('legacy_adjustment', 0.0)),
            cand.get('estate_tax_score', -float(cand.get('estate_tax_penalty', 0.0) or 0.0)),
            cand.get('survivor_risk_score', -float(cand.get('survivor_tax_risk_penalty', 0.0) or 0.0)),
            cand.get('liquidity_score', 0.0),
            cand.get('total_conversions', cand.get('total_conversion')),
            cand.get('lifetime_tax'),
            cand.get('after_tax_terminal_net_worth', cand.get('after_tax_terminal_nw')),
            why_text,
        ]
        fmts = [None, None, None, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, None]
        for i, (val, fmt) in enumerate(zip(vals, fmts), 1):
            write_cell(ws, r, i, val, fmt=fmt, bg='E2EFDA' if idx == 1 else None, bold=(idx == 1), align='left' if i in (2,14) else 'right' if fmt else 'center')
        ws.row_dimensions[r].height = 45 if len(str(why_text)) > 70 else 24
        r += 1
    r += 2

    # Main schedule table with primary and secondary constraints.
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    hdrs = [
        'Year', 'Type', 'Source Account',
        'Pre-Conv AGI', 'Target Bracket Top', 'Brkt Headroom',
        f'{_n1} IRA Avail', f'{_n2} IRA Avail', 'Non-Roth Surplus',
        'Conversion', 'Primary Binding Limit', 'Secondary Binding Limit',
        'Post-Conv AGI', 'IRMAA Thr', 'Status',
    ]
    write_hdr(ws, r, 1, 'Year-by-Year Conversion Schedule with Binding Constraints', NAVY, WHITE, span=len(hdrs)); r += 1
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, NAVY if i in (10, 13, 15) else DGRAY, WHITE, size=8)
    r += 1

    irmaa_thr_base = float(c.get('roth_irmaa_target_threshold_mfj', c.get('irmaa_base', 268000)) or 268000)
    total_conv = total_forced = total_volun = 0.0
    for row in rows:
        yr = row['year']
        if yr > c.get('plan_start', yr) + 15 and yr > c.get('h_dob_yr', yr) + 75:
            break
        forced = c.get('forced_roth', {}).get(yr, 0.0)
        tot = float(row.get('roth_conv', 0.0) or 0.0)
        volun = max(0.0, tot - forced)
        src_lbl = _display_accounts_in_text(row.get('roth_conv_src', '—'), c)
        binding = row.get('conv_binding_limit', '—')
        secondary = row.get('conv_secondary_binding_limit', '—')
        pre_agi = row.get('conv_pre_agi', 0)
        top_target = row.get('conv_top_24', 0)
        room = row.get('conv_bracket_room', 0)
        surplus = row.get('conv_non_roth_surp', 0)
        h_avail = row.get('conv_h_ira_avail', 0)
        w_avail = row.get('conv_w_ira_avail', 0)
        irmaa_t = irmaa_thr_base * (1 + float(c.get('irmaa_inflator', 0.02))) ** (yr - TAX_BASE_YEAR)
        post_agi = row.get('agi', 0)
        if forced > 0 and volun == 0:
            conv_type, status, row_bg = 'Forced', '★ FORCED', 'FFF2CC'
        elif tot > 0:
            conv_type, status, row_bg = 'Voluntary', '✓ OK' if post_agi <= irmaa_t * 1.05 else '⚠ Near IRMAA', 'E2EFDA'
        elif yr > c['h_dob_yr'] + int(c.get('rmd_start_age',75)) - 1:
            conv_type, status, row_bg = '—', 'Post-RMD — no conv', 'F2F2F2'
        elif room <= 0:
            conv_type, status, row_bg = '—', 'AGI > target bracket', 'FCE4D6'
        elif surplus <= 0:
            conv_type, status, row_bg = '—', 'No non-Roth surplus', 'FCE4D6'
        elif h_avail + w_avail < 1000:
            conv_type, status, row_bg = '—', 'IRA exhausted', 'F4F5F7'
        else:
            conv_type, status, row_bg = '—', '—', None
        vals = [yr, conv_type, src_lbl or '—', pre_agi, top_target, room, h_avail, w_avail, surplus, tot, binding or '—', secondary or '—', post_agi, irmaa_t, status]
        fmts = [FMT_YEAR, None, None, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, FMT_DOLLAR, None, None, FMT_DOLLAR, FMT_DOLLAR, None]
        for i, (val, fmt) in enumerate(zip(vals, fmts), 1):
            bg = row_bg if i == 15 else (LGRAY if i == 10 and tot > 0 else None)
            write_cell(ws, r, i, val, fmt=fmt, bg=bg, bold=(i == 10 and tot > 0), align='left' if i in (3,11,12,15) else 'right' if fmt else 'center')
        total_conv += tot; total_forced += forced; total_volun += volun
        r += 1

    r += 1
    write_cell(ws, r, 1, f'Total Conversions in Displayed Window: ${total_conv:,.0f}', bold=True, bg=LGRAY)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    write_cell(ws, r, 9, 'Forced', bold=True, bg=LGRAY); write_cell(ws, r, 10, total_forced, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)
    write_cell(ws, r, 11, 'Voluntary', bold=True, bg=LGRAY); write_cell(ws, r, 12, total_volun, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)
    write_cell(ws, r, 13, 'Grand Total', bold=True, bg=LGRAY); write_cell(ws, r, 14, total_conv, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)

    r += 2
    write_hdr(ws, r, 1, 'Conversion Strategy — Key Rules', BLUE, WHITE, span=len(hdrs)); r += 1
    notes = [
        'The workbook renders Roth narrative, strategy labels, candidate ranking, and schedule totals from the canonical RothStrategyResult contract.',
        'The selected strategy can differ from the lowest-tax or highest-terminal-wealth candidate because Balanced Retirement also scores estate-tax exposure, survivor tax risk, Roth legacy value, liquidity, and guardrail compliance.',
        'Primary and secondary constraint columns show the binding cap and next-nearest cap for each year, such as target bracket, IRMAA tier, IRA balance, annual IRA percentage cap, fixed dollar amount, or forced action.',
        f'Current configurable headroom defaults: tax bracket {float(c.get("roth_headroom_usage_pct",0.95)):.0%}, IRMAA {float(c.get("roth_irmaa_headroom_usage_pct",0.95)):.0%}, annual IRA percentage cap {float(c.get("roth_max_annual_conversion_pct_of_traditional_ira",0.20)):.0%}.',
        f'Current explicit conversion-window cap: {int(c.get("roth_max_conversion_years",10))} year(s), also bounded by the RMD-age window.',
    ]
    for note in notes:
        write_cell(ws, r, 1, '• ' + note, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(hdrs))
        ws.row_dimensions[r].height = 32
        r += 1

    ws.column_dimensions['B'].width = 14
    ws.column_dimensions['C'].width = 28
    ws.column_dimensions['K'].width = 20
    ws.column_dimensions['L'].width = 22
    ws.column_dimensions['N'].width = 18
    ws.column_dimensions['O'].width = 20

    qc('11. Roth Conversion', 'Canonical result contract, candidate scores, rejection reasons, and binding constraints rendered', True, f'Total: ${total_conv:,.0f}  Forced: ${total_forced:,.0f}  Voluntary: ${total_volun:,.0f}')


def build_sheet12(ws, c, rows):
    """Charitable Giving"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'CHARITABLE GIVING — Cash vs DAF vs QCD', 8)

    r = 3
    write_hdr(ws, r, 1, 'Giving Vehicle Comparison', NAVY, WHITE, span=6); r+=1
    hdrs = ['Vehicle','Best Used When','Tax Savings','Net Cost to Donor',
            'Gross Value to Charity','Recommended?']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    vehicles = [
        ('Cash / Check', 'Always available; simple',
         'Deductible only if itemizing (SALT cap constrains)',
         'Dollar-for-dollar', 'Full gift', 'Secondary — use when already itemizing'),
        ('Donor Advised Fund (DAF)',
         'High-income years; bunch 3-5 years of gifts into one year',
         'Full deduction in contribution year; invest tax-free; distribute over time',
         'Reduced by tax savings', 'Full gift (potentially grown)', '★ PRIMARY — High-income years'),
        ('QCD (from IRA)',
         f"After RMD start age ({c['h_dob_yr'] + int(c.get('rmd_start_age', 75))} for {str(c.get('h_nick') or c.get('h_name') or 'Member 1')}); up to $108K/person/yr",
         'Excluded from AGI entirely — bypasses SALT calculus; counts toward RMD',
         'Reduced by avoided tax', 'Full gift direct to charity', '★ PRIMARY — 2037+'),
    ]
    for v in vehicles:
        for i, val in enumerate(v, 1):
            bg = 'E2EFDA' if '★' in v[-1] and i==6 else None
            write_cell(ws, r, i, val, bg=bg)
        r += 1

    r += 2
    write_hdr(ws, r, 1, 'SALT-Cap Strategy by Phase', BLUE, WHITE, span=6); r+=1
    phases = [
        ('Highest-income year',
         'Bundle 3 years of charitable giving into a DAF contribution. SALT cap is $40,400; '
         'likely itemizing. Deduction maximized.'),
        ('Subsequent high-income years',
         'SALT cap $40,804–$41,624. Test itemize vs. standard each year. '
         'Continue DAF distributions as desired.'),
        ('Pre-statutory-change year',
         'Consider a second large DAF contribution to capture high SALT cap before it reverts.'),
        ('Post-statutory-change years',
         'Itemizing becomes less common. Standard deduction likely wins. '
         'Shift giving to QCDs when eligible.'),
        ('2037+ (RMD Era)',
         'QCDs up to $108K/person/yr. Counts toward RMD, excluded from AGI. '
         'Optimal — no SALT impact at all.'),
    ]
    for phase, detail in phases:
        write_cell(ws, r, 1, phase, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, detail)
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=6)
        r += 1

    # ── DAF Optimization ─────────────────────────────────────────────────────
    r += 2
    write_hdr(ws, r, 1, 'DAF OPTIMIZATION — Recommended Contribution Amount & Year', NAVY, WHITE, span=6); r+=1

    # Compute optimal DAF in the selected contribution year (highest income year before earn_end)
    # Strategy: contribute enough to DAF to fully itemize past standard deduction
    # in the high-income year. DAF deduction is limited to 60% of AGI.
    opt_year     = TAX_BASE_YEAR   # highest income year
    est_agi_base = c.get('earned', 290000) * 0.9   # rough net of SE deductions
    std_ded_base = 31500  # MFJ tax-reference-year standard deduction (approx)
    salt_base    = 40400  # SALT cap for the tax reference year
    marg_base    = 0.24   # likely marginal rate

    # To itemize: need itemized > standard_deduction
    # Itemized = salt + char_base + daf = salt_base + char_low + daf_contrib
    # Solve: daf_contrib = std_ded_base - salt_base - char_low + 1 (to exceed std)
    base_itemized = salt_base + c.get('char_low', 3000)
    min_daf_to_itemize = max(0, std_ded_base - base_itemized + 1)
    # DAF deduction limit = 60% of AGI
    max_daf_deductible = est_agi_base * 0.60
    # Optimal: itemize meaningfully but stay within 60% AGI limit
    # Recommend 3-5 years of charitable giving bundled into DAF in the selected year
    avg_annual_giving  = (c.get('char_low', 3000) + c.get('char_high', 5000)) / 2
    rec_daf_years      = 5   # bundle 5 years of giving
    rec_daf_amount     = min(avg_annual_giving * rec_daf_years, max_daf_deductible)
    rec_daf_amount     = max(rec_daf_amount, min_daf_to_itemize)
    rec_daf_tax_saving = min(rec_daf_amount, max_daf_deductible) * marg_base

    # Current CSV settings
    daf_on     = c.get('daf_enabled', False)
    daf_amount = c.get('daf_amount', 0)
    daf_year   = c.get('daf_year', c.get('plan_start', TAX_BASE_YEAR))
    daf_use    = c.get('daf_use_amount', 0)
    daf_start  = c.get('daf_use_start', 2027)
    daf_end    = c.get('daf_use_end', 2035)

    write_hdr(ws, r, 1, 'Parameter', DGRAY, WHITE, span=2)
    write_hdr(ws, r, 3, 'Recommended', DGRAY, WHITE)
    write_hdr(ws, r, 4, 'CSV Current', DGRAY, WHITE)
    write_hdr(ws, r, 5, 'Notes', DGRAY, WHITE, span=2); r+=1

    daf_table = [
        ('Toggle',             'TRUE',                str(daf_on),    'Set enabled:TRUE in [DAF][Settings] of CSV'),
        ('Contribution Year',  str(c.get('daf_year', c.get('plan_start', TAX_BASE_YEAR))),                str(daf_year),  'Highest income year; max SALT headroom'),
        ('Contribution Amount', f'${rec_daf_amount:,.0f}', f'${daf_amount:,.0f}',
         f'{rec_daf_years} yrs × ${avg_annual_giving:,.0f}/yr avg; ≤ 60% AGI limit ${max_daf_deductible:,.0f}'),
        ('Est. Tax Savings',   f'${rec_daf_tax_saving:,.0f}', 'N/A',
         f'At {marg_base:.0%} marginal rate; actual depends on final AGI'),
        ('Annual Grant Amount', f'${avg_annual_giving:,.0f}/yr', f'${daf_use:,.0f}/yr',
         'Replace ongoing charitable cash spending from DAF'),
        ('Grant Start Year',   '2027',                str(daf_start), 'Begin distributing year after contribution'),
        ('Grant End Year',     str(int(daf_start + rec_daf_years - 1)), str(daf_end),
         f'Spread over {rec_daf_years} years'),
    ]

    for label, rec_val, csv_val, note in daf_table:
        bg = 'E2EFDA' if rec_val != csv_val and not daf_on else None
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        write_cell(ws, r, 3, rec_val,  bg='C6EFCE')
        write_cell(ws, r, 4, csv_val,  bg=bg or 'F4F5F7')
        write_cell(ws, r, 5, note, align='left')
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        r += 1

    if not daf_on:
        r += 1
        write_cell(ws, r, 1,
                   f'ACTION: To activate DAF, add these rows to client_assets.csv under section=DAF, subsection=Settings: '
                   f'enabled=TRUE, contribution_amount={rec_daf_amount:,.0f}, contribution_year=<selected_year>, '
                   f'annual_grant_amount={avg_annual_giving:,.0f}, grant_start_year=2027, grant_end_year={int(daf_start+rec_daf_years-1)}',
                   bg='FFEB9C', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1


    qc('12. Charitable Giving', 'Three vehicles documented; SALT phases shown', True, '')


def build_sheet_tlh(ws, c, rows):
    """Tax-Loss Harvesting — current opportunities and lifetime value/cost."""
    from .. import tlh as _tlh
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'TAX-LOSS HARVESTING', 8)

    policy = str(c.get('tlh_policy', 'off') or 'off')
    r = 3
    write_hdr(ws, r, 1, 'POLICY', NAVY, WHITE, span=6); r += 1
    policy_rows = [
        ('Policy', policy.replace('_', ' ').title()),
        ('Minimum Loss ($)', f"${c.get('tlh_min_loss_dollars', 500):,.0f}"),
        ('Minimum Loss (% of basis)', f"{c.get('tlh_min_loss_pct', 0.05):.1%}"),
        ('Annual Ceiling', 'Unlimited' if not c.get('tlh_annual_ceiling') else f"${c.get('tlh_annual_ceiling', 0):,.0f}"),
        ('Transaction Cost', f"{c.get('tlh_transaction_cost_bps', 2):.0f} bps"),
        ('Fraction Sold Before Step-Up', f"{c.get('tlh_fraction_sold_before_death', 0.5):.0%}"),
    ]
    for label, val in policy_rows:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, val)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1
    if policy == 'off':
        r += 1
        write_cell(ws, r, 1,
                   'Harvesting is OFF — the opportunities below are for reference only and do not change '
                   'the projection. Set Withdrawal Policy / Tax-Loss Harvesting / tlh_policy to analyze_only '
                   'or apply to activate.', bg='FFEB9C')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1

    plan_start = int(c.get('plan_start', rows[0]['year'] if rows else 2026))
    first_row = rows[0] if rows else {}
    scan = _tlh.scan_harvest_opportunities(
        c, plan_start,
        ordinary_income=float(first_row.get('taxable_inc', 0) or 0),
        existing_lt_gain=float(first_row.get('ltcg_gain', 0) or 0),
        carryforward_in=0.0,
        annual_return=float(c.get('ret', 0.06) or 0.06),
        years_to_step_up=max(1, int(c.get('h_death_yr', plan_start + 20)) - plan_start),
        fraction_sold_before_death=float(c.get('tlh_fraction_sold_before_death', 0.5) or 0.5),
        ordinary_offset_rate=0.24,
        transaction_cost_bps=float(c.get('tlh_transaction_cost_bps', 2.0) or 0.0),
        min_loss_dollars=float(c.get('tlh_min_loss_dollars', 500.0) or 0.0),
        min_loss_pct=float(c.get('tlh_min_loss_pct', 0.05) or 0.0),
        annual_ceiling=float(c.get('tlh_annual_ceiling', 0.0) or 0.0),
    )

    r += 1
    write_hdr(ws, r, 1, f'CURRENT OPPORTUNITIES ({plan_start})', BLUE, WHITE, span=9); r += 1
    hdrs = ['Account', 'Symbol', 'Term', 'Basis', 'Market Value', 'Loss',
            'Gross Benefit', 'Future Give-Back', 'Net Value', 'Suggested Replacement']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    opps = scan['opportunities']
    if not opps:
        write_cell(ws, r, 1, 'No loss lots currently meet the minimum-loss threshold.', bg=None)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    else:
        for o in opps:
            write_cell(ws, r, 1, _display_accounts_in_text(o['account'], c))
            write_cell(ws, r, 2, o['symbol'], bold=True)
            write_cell(ws, r, 3, 'LT' if o['long_term'] else 'ST', align='center')
            write_cell(ws, r, 4, o['basis'], fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 5, o['market_value'], fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 6, o['loss'], fmt=FMT_DOLLAR, align='right', fg=RED)
            write_cell(ws, r, 7, o['gross_benefit'], fmt=FMT_DOLLAR, align='right', fg=GREEN)
            write_cell(ws, r, 8, o['future_give_back'], fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 9, o['net_value'], fmt=FMT_DOLLAR, align='right', bold=True)
            write_cell(ws, r, 10, o['replacement'] or '—')
            r += 1
        write_cell(ws, r, 1, 'TOTAL', bold=True, bg=LGRAY)
        for col, key in ((6, 'loss'), (7, 'gross_benefit'), (8, 'future_give_back'), (9, 'net_value')):
            write_cell(ws, r, col, scan['totals'][key], fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
        r += 1

    r += 1
    write_cell(ws, r, 1,
               f"Marginal LTCG+NIIT rate applied: {scan['marginal_ltcg_rate']:.1%}. "
               f"Values are lifetime-net-of-cost: Gross Benefit is this year's tax saved (offsetting gains, "
               f"then up to $3,000 of ordinary income, then carryforward); Future Give-Back is the "
               f"present-value tax cost of the replacement's lower basis, reduced for the share of the "
               f"position expected to receive a basis step-up at death instead of being sold.")
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    # ── Lifetime value realized (apply mode only — driven by actual harvests) ──
    write_hdr(ws, r, 1, 'LIFETIME VALUE REALIZED (Apply Mode)', BLUE, WHITE, span=6); r += 1
    hdrs2 = ['Year', 'Harvested Loss', 'Loss Used', 'Carryforward', 'Tax Value', 'Transaction Cost']
    for i, h in enumerate(hdrs2, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    total_tax_value = total_txn_cost = total_harvested = 0.0
    shown_years = 0
    for row in rows:
        harvested = float(row.get('tlh_harvested_loss', 0) or 0)
        if harvested <= 0 and float(row.get('cap_loss_carryforward', 0) or 0) <= 0:
            continue
        write_cell(ws, r, 1, row['year'], align='center')
        write_cell(ws, r, 2, harvested, fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 3, row.get('cap_loss_used', 0), fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 4, row.get('cap_loss_carryforward', 0), fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 5, row.get('tlh_tax_value', 0), fmt=FMT_DOLLAR, align='right', fg=GREEN)
        write_cell(ws, r, 6, row.get('tlh_transaction_cost', 0), fmt=FMT_DOLLAR, align='right')
        total_tax_value += float(row.get('tlh_tax_value', 0) or 0)
        total_txn_cost += float(row.get('tlh_transaction_cost', 0) or 0)
        total_harvested += harvested
        shown_years += 1
        r += 1
    if not shown_years:
        write_cell(ws, r, 1, 'No harvesting activity in the projection (policy is off or no qualifying losses arose).')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1
    else:
        write_cell(ws, r, 1, 'LIFETIME TOTAL', bold=True, bg=LGRAY)
        write_cell(ws, r, 2, total_harvested, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
        write_cell(ws, r, 3, '', bg=LGRAY)
        write_cell(ws, r, 4, '', bg=LGRAY)
        write_cell(ws, r, 5, total_tax_value, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
        write_cell(ws, r, 6, total_txn_cost, fmt=FMT_DOLLAR, align='right', bold=True, bg=LGRAY)
        r += 1
        write_cell(ws, r, 1, f'Net lifetime value: ${total_tax_value - total_txn_cost:,.0f} (Tax Value less Transaction Cost)', bold=True)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        r += 1

    ws.column_dimensions['A'].width = 22
    for col in range(2, 11):
        ws.column_dimensions[get_column_letter(col)].width = 16

    qc('2I. Tax-Loss Harvesting', 'Opportunities scanned and lifetime ledger rendered', True,
       f'policy={policy}; opportunities={len(opps)}; years_with_activity={shown_years}')


def build_sheet13(ws, c, rows):
    """State Residency Analysis — retirement-income-aware comparison."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'STATE RESIDENCY ANALYSIS', 10)

    r = 3
    # ── Aggregate income components over plan horizon ────────────────────────
    total_earned = sum(row.get('state_earned_net', 0) for row in rows)
    total_retirement = sum(row.get('state_retirement', 0) for row in rows)
    total_nonqual = sum(row.get('state_nonqual_ann', 0) for row in rows)
    total_ss = sum(row.get('state_ss_taxable', 0) for row in rows)
    total_invest = sum(row.get('state_investment', 0) for row in rows)
    total_roth_conv = sum(row.get('state_roth_conv', 0) for row in rows)
    total_agi = sum(row.get('agi', 0) for row in rows)
    yrs = max(1, c['plan_end'] - c['plan_start'])

    # ── Section A: Income component breakdown ────────────────────────────────
    write_hdr(ws, r, 1, 'Lifetime Income Components (State Tax Basis)', NAVY, WHITE, span=3); r += 1
    components = [
        ('Earned Income (W-2/S-Corp)', total_earned, 'Taxable in all states with income tax'),
        ('Qualified Retirement Distributions', total_retirement, 'IRA/401k/pension/qualified annuity — exempt in IL'),
        ('Non-Qualified Annuity Income', total_nonqual, 'Personal market annuities — taxable in IL'),
        ('Social Security (fed taxable)', total_ss, 'Exempt in most states'),
        ('Investment Income', total_invest, 'Note interest, capital gains'),
        ('Roth Conversions', total_roth_conv, 'Exempt in IL (retirement distribution)'),
        ('Total AGI', total_agi, ''),
    ]
    for lbl, val, note in components:
        write_cell(ws, r, 1, lbl, bold=(lbl=='Total AGI'))
        write_cell(ws, r, 2, val, fmt=FMT_DOLLAR, bold=(lbl=='Total AGI'))
        if note:
            write_cell(ws, r, 3, note, fg='888888')
        r += 1
    r += 1

    # ── Section B: State comparison ──────────────────────────────────────────
    write_hdr(ws, r, 1, 'Lifetime Tax Burden by State', NAVY, WHITE, span=10); r += 1
    hdrs = ['State', 'Income Rate', 'Income Tax',
            'Property Tax', 'Sales Tax', 'Estate Tax', 'Total Tax', 'Delta vs IL',
            'Retirement Income Taxed']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    home_val_avg = c['home_val'] * (1 + c['home_appr']) ** (yrs // 2)
    taxable_spend = sum(row.get('spend_base_yr', 0) for row in rows) * 0.4

    il_total = None
    over_65 = True  # most of plan horizon is post-65
    state_rows = []  # collect all rows, then sort
    for state_name, rules in STATE_TAX_RULES.items():
        # Compute state income tax year-by-year using actual components
        inc_tax = 0
        retirement_taxed = 0
        for row in rows:
            yr_tax = state_income_tax(
                state_name,
                row.get('state_earned_net', 0),
                row.get('state_retirement', 0),
                row.get('state_ss_taxable', 0),
                row.get('state_investment', 0),
                row.get('state_nonqual_ann', 0),
                row.get('state_roth_conv', 0),
                row['year'], over_65)
            inc_tax += yr_tax
            # Track how much retirement income is taxed in this state
            if not rules.get('exempt_retirement'):
                ret_this_yr = row.get('state_retirement', 0) + row.get('state_roth_conv', 0)
                if state_name == 'Colorado' and over_65:
                    ret_this_yr = max(0, ret_this_yr - rules.get('retirement_exempt_over_65', 0))
                retirement_taxed += ret_this_yr

        prop_tax = home_val_avg * rules.get('prop_rate', 0) * yrs
        sales_tax = taxable_spend * rules.get('sales_rate', 0)
        is_current = c.get('state', 'Illinois') in state_name
        est_tax = 0
        # For current state, use the CST-adjusted exemption from the plan
        _estate_exempt = c['il_exempt'] if is_current else rules.get('estate_exempt', 0)
        if rules.get('estate') and rows[-1]['total_nw'] > _estate_exempt:
            excess = rows[-1]['total_nw'] - _estate_exempt
            est_tax = excess * 0.08
        total = inc_tax + prop_tax + sales_tax + est_tax
        if il_total is None:
            il_total = total
        delta = total - il_total

        state_rows.append({
            'state_name': state_name, 'rules': rules, 'is_current': is_current,
            'inc_tax': inc_tax, 'prop_tax': prop_tax, 'sales_tax': sales_tax,
            'est_tax': est_tax, 'total': total, 'delta': delta,
            'retirement_taxed': retirement_taxed,
        })

    # Sort by delta descending (biggest savings first, current state at top)
    state_rows.sort(key=lambda x: (0 if x['is_current'] else 1, -x['delta']))

    for sr in state_rows:
        rules = sr['rules']
        is_current = sr['is_current']
        bg = 'E2EFDA' if sr['delta'] < -50000 else ('FCE4D6' if sr['delta'] > 50000 else None)

        vals = [
            (sr['state_name'] + (' (Current)' if is_current else ''), None),
            (f'{rules["rate"]*100:.1f}%' if rules['rate'] > 0 else 'None', None),
            (sr['inc_tax'], FMT_DOLLAR), (sr['prop_tax'], FMT_DOLLAR), (sr['sales_tax'], FMT_DOLLAR),
            (sr['est_tax'], FMT_DOLLAR), (sr['total'], FMT_DOLLAR),
            (sr['delta'] if not is_current else 'Baseline', FMT_DOLLAR if not is_current else None),
            (sr['retirement_taxed'] if sr['retirement_taxed'] > 0 else 'Exempt', FMT_DOLLAR if sr['retirement_taxed'] else None),
        ]
        for i, (val, fmt) in enumerate(vals, 1):
            write_cell(ws, r, i, val, fmt=fmt, bg=bg if i >= 7 else None,
                       bold=is_current,
                       fg='C00000' if i==9 and isinstance(val,(int,float)) and val>0 else '000000')
        r += 1

    r += 2
    # ── Key insight callout ──────────────────────────────────────────────────
    ret_pct = total_retirement / total_agi * 100 if total_agi > 0 else 0
    write_cell(ws, r, 1,
        f'Illinois exempts ${total_retirement:,.0f} of retirement income '
        f'({ret_pct:.0f}% of AGI) from state tax. '
        f'Moving to a state that taxes retirement income (e.g. North Carolina) '
        f'would add ~${total_retirement * 0.045:,.0f} in lifetime state income tax.',
        bold=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 1
    write_cell(ws, r, 1,
        'Qualified retirement income includes IRA/401k RMDs, pension, qualified annuity '
        'distributions, and Roth conversions. Non-qualified (Personal market) annuity income '
        'is taxable even in Illinois.', fg='888888')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 3

    # ── Section C: Geographic cost-of-living delta ───────────────────────────
    # The household's actual budgeted amounts in the *current* state are the
    # baseline.  We then estimate the annual delta for four geographically
    # sensitive categories (auto insurance, homeowners insurance, utilities,
    # home maintenance) if the household relocated to the target state, using
    # relative cost-of-living factors.  This is an approximation the user can
    # override with real quotes.
    current_state = c.get('state', 'Illinois')
    target_state = (c.get('residency_target_state') or '').strip()
    # Map an abbreviation or partial name to a known state key.
    _abbr = {
        'IL': 'Illinois', 'IN': 'Indiana', 'FL': 'Florida', 'TX': 'Texas',
        'TN': 'Tennessee', 'NC': 'North Carolina', 'AZ': 'Arizona',
        'CO': 'Colorado', 'NV': 'Nevada', 'CA': 'California', 'NY': 'New York',
    }
    def _resolve_state(name):
        if not name:
            return None
        for key in STATE_TAX_RULES:
            if name.lower() == key.lower() or key.lower() in name.lower():
                return key
        return _abbr.get(name.strip().upper())
    cur_key = _resolve_state(current_state) or 'Illinois'
    tgt_key = _resolve_state(target_state)

    write_hdr(ws, r, 1, 'Geographic Cost-of-Living Delta (Estimated)', NAVY, WHITE, span=6); r += 1
    write_cell(ws, r, 1,
        f'Baseline = current budgeted amounts in {cur_key}. Delta = estimated annual change '
        f'if relocating to {tgt_key or "the target state"}, from relative cost-of-living '
        f'factors. ESTIMATE ONLY — replace with real quotes when available.', fg='888888')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6); r += 1

    cost_hdrs = ['Category', f'Baseline ({cur_key})',
                 f'Estimated ({tgt_key or "target"})', 'Annual Delta', 'Lifetime Delta', 'Basis']
    for i, h in enumerate(cost_hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    cur_col = col_factors(cur_key, STATE_TAX_RULES.get(cur_key))
    tgt_col = col_factors(tgt_key, STATE_TAX_RULES.get(tgt_key)) if tgt_key else cur_col
    cost_cats = [
        ('Auto Insurance', c.get('current_auto_insurance_annual', 0), 'auto'),
        ('Homeowners Insurance', c.get('current_homeowners_insurance_annual', 0), 'home_ins'),
        ('Utilities', c.get('current_home_utilities_annual', 0), 'utilities'),
        ('Home Maintenance', c.get('current_home_maintenance_annual', 0), 'maintenance'),
    ]
    total_annual_delta = 0.0
    for lbl, baseline, key in cost_cats:
        factor = (tgt_col[key] / cur_col[key]) if cur_col[key] else 1.0
        est = baseline * factor
        annual_delta = est - baseline
        lifetime_delta = annual_delta * yrs
        total_annual_delta += annual_delta
        bg = 'FCE4D6' if annual_delta > 0 else ('E2EFDA' if annual_delta < 0 else None)
        write_cell(ws, r, 1, lbl)
        write_cell(ws, r, 2, baseline, fmt=FMT_DOLLAR)
        write_cell(ws, r, 3, est, fmt=FMT_DOLLAR)
        write_cell(ws, r, 4, annual_delta, fmt=FMT_DOLLAR, bg=bg,
                   fg='C00000' if annual_delta > 0 else '000000')
        write_cell(ws, r, 5, lifetime_delta, fmt=FMT_DOLLAR, bg=bg)
        write_cell(ws, r, 6, f'x{tgt_col[key]:.2f} vs x{cur_col[key]:.2f}', fg='888888')
        r += 1
    write_cell(ws, r, 1, 'Total (4 categories)', bold=True)
    write_cell(ws, r, 4, total_annual_delta, fmt=FMT_DOLLAR, bold=True,
               fg='C00000' if total_annual_delta > 0 else '000000')
    write_cell(ws, r, 5, total_annual_delta * yrs, fmt=FMT_DOLLAR, bold=True)
    r += 2
    write_cell(ws, r, 1,
        'Cost-of-living factors are illustrative approximations from public regional '
        'cost and insurance-premium indices. Homeowners insurance, utilities, and '
        'maintenance baselines come from the Housing current-home budget; the auto '
        'insurance baseline comes from the State Residency inputs. Override factors '
        'via reference_data/state_tax.csv (col_auto, col_home_ins, col_utilities, '
        'col_maintenance).', fg='888888')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)

    qc('13. State Residency', f'{len(STATE_TAX_RULES)} states compared with retirement-income treatment', True,
       f'retirement={ret_pct:.0f}% of AGI')


def build_sheet14(ws, c, rows):
    """Estate & Legacy Plan"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'ESTATE & LEGACY PLAN', 8)

    yr_first  = next((row for row in rows if row['year']==c['first_death_yr']), rows[-1])
    yr_second = rows[-1]

    r = 3
    write_hdr(ws, r, 1, 'Projected Gross Estate', NAVY, WHITE, span=4); r+=1
    items = [
        (f'At First Death ({c["first_death_yr"]})', yr_first['total_nw']),
        (f'At Second Death ({c["plan_end"]})',       yr_second['total_nw']),
    ]
    for label, val in items:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, val, fmt=FMT_DOLLAR, bold=True)
        r += 1

    # Federal estate tax
    r += 1
    write_hdr(ws, r, 1, 'Federal Estate Tax', BLUE, WHITE, span=4); r+=1
    fed_exempt = c['fed_exempt']
    est2 = yr_second['total_nw']
    fed_estate_tax = max(0, est2 - fed_exempt) * 0.40
    write_cell(ws, r, 1, 'Federal Exemption (MFJ, OBBBA)')
    write_cell(ws, r, 2, fed_exempt, fmt=FMT_DOLLAR); r+=1
    write_cell(ws, r, 1, 'Projected Estate at Second Death')
    write_cell(ws, r, 2, est2, fmt=FMT_DOLLAR); r+=1
    write_cell(ws, r, 1, 'Est. Federal Estate Tax', bold=True)
    write_cell(ws, r, 2, fed_estate_tax, fmt=FMT_DOLLAR, bold=True); r+=1
    write_cell(ws, r, 1, 'Note'); write_cell(ws, r, 2, 'Estate well below $30M exemption — no federal tax likely'); r+=2

    # Illinois estate tax
    if c['model_state_est']:
        write_hdr(ws, r, 1, 'Illinois Estate Tax (At Second Death)', ORANGE, WHITE, span=4); r+=1
        il_exempt = c['il_exempt']
        il_excess = max(0, est2 - il_exempt)
        il_tax = illinois_estate_tax(est2, il_exempt)
        write_cell(ws, r, 1, 'IL Exemption'); write_cell(ws, r, 2, il_exempt, fmt=FMT_DOLLAR); r+=1
        write_cell(ws, r, 1, 'Estate over IL Exemption'); write_cell(ws, r, 2, il_excess, fmt=FMT_DOLLAR); r+=1
        write_cell(ws, r, 1, 'Est. IL Estate Tax (cliff/interrelated calc)', bold=True)
        write_cell(ws, r, 2, il_tax, fmt=FMT_DOLLAR, bold=True,
                   bg='FCE4D6' if il_tax>0 else 'E2EFDA'); r+=1
        if il_tax > 0:
            write_cell(ws, r, 1, '⚠ ACTION REQUIRED', bold=True, bg='FCE4D6', fg=RED)
            write_cell(ws, r, 2,
                       f'Estate may exceed ${c["il_exempt"]/1e6:.0f}M IL exemption. Consider: annual gifting, ILIT, '
                       'charitable bequest, or credit-shelter/QTIP trust. Calculation uses the IL cliff/interrelated structure, not a tax-on-excess shortcut.',
                       bg='FCE4D6'); r+=2

    # Gifting
    write_hdr(ws, r, 1, 'Gifting Strategy', NAVY, WHITE, span=4); r+=1
    gift_items = [
        ('Annual Exclusion per Donee', f'${c["gift_excl"]:,} per recipient (tax reference year, indexed)'),
        ('Trust Type', c['trust_type'].title()),
        ('Step-Up in Basis', 'Non-retirement assets (Trust, home, autos) receive step-up at death; '
                             'IRAs/401k do NOT — heirs pay ordinary income'),
        ('Recommended Actions', 'Max annual gifts; consider Roth conversions to reduce taxable IRA '
                                'inherited by heirs; review beneficiary designations annually'),
    ]
    for label, detail in gift_items:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, detail); ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=4)
        r += 1

    # ── QTIP Trust ────────────────────────────────────────────────────────────
    r += 1
    qtip_on = c.get('qtip_enabled', False)
    qtip_bg = 'E2EFDA' if qtip_on else 'F4F5F7'
    write_hdr(ws, r, 1, f'QTIP Trust  [{"ENABLED" if qtip_on else "DISABLED — add enabled:TRUE to CSV"}]',
              bg='2D6A4F' if qtip_on else DGRAY, span=4); r += 1
    qtip_rows = [
        ('Status',         'ENABLED — QTIP trust in place' if qtip_on else 'DISABLED — consider enabling'),
        ('Funding Amount', f'${c.get("qtip_amount",0):,.0f}' if c.get("qtip_amount",0) else 'All remaining marital assets'),
        ('Purpose',        'Qualifies for unlimited marital deduction; surviving spouse receives all income; '
                           'executor controls remainder beneficiaries'),
        ('Manages Annuity','YES — annuity income flows to QTIP trustee after first death'
                           if c.get("qtip_manages_annuity", True) else 'NO'),
        ('Tax Effect',     "Defers estate tax on marital share to second death; QTIP assets included in survivor's gross estate"),
        ('Key Requirement','Executor must file QTIP election on Form 706 by estate tax return due date'),
        ('Cost',           '$3,000–$5,000 drafting; $1,000–$2,000/yr admin'),
    ]
    for label, detail in qtip_rows:
        write_cell(ws, r, 1, label, bold=True, bg=qtip_bg)
        write_cell(ws, r, 2, detail, bg=qtip_bg)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        r += 1

    # ── Credit Shelter Trust ──────────────────────────────────────────────────
    r += 1
    cs_on  = c.get('cs_enabled', True)
    cs_bg  = 'E2EFDA' if cs_on else 'F4F5F7'
    cs_amt = c.get('cs_amount', c.get('il_exempt', 4000000))
    il_exempt = c['il_exempt']
    cs_tax_saved = min(cs_amt, il_exempt) * 0.08
    write_hdr(ws, r, 1, f'Credit Shelter Trust (Bypass Trust)  [{"ENABLED" if cs_on else "DISABLED"}]',
              bg='375623' if cs_on else DGRAY, span=4); r += 1
    cs_rows = [
        ('Status',                  'ENABLED — Credit Shelter Trust in place' if cs_on else 'DISABLED'),
        ('Funding Amount',          f'${cs_amt:,.0f} (= IL exemption amount)'),
        ('Purpose',                 f'Assets bypass survivor estate for IL purposes. Preserves the ${il_exempt:,.0f} IL exemption.'),
        ('Projected IL Tax Saved',  f'~${cs_tax_saved:,.0f} (approx 8% avg rate on ${cs_amt:,.0f} bypass amount)'),
        ('Mechanism',               'First-to-die funds trust up to IL exemption; survivor has limited access (income, HEMS); '
                                    'remainder passes to heirs free of IL estate tax'),
        ('Federal Effect',          'No federal benefit (OBBBA $30M exemption covers this estate); pure IL tax play'),
        ('Portability',             'Illinois has NO portability — unused exemption at first death is LOST without this trust'),
        ('Cost',                    '$3,000–$5,000 drafting; trustee fees ~0.5%/yr on trust assets'),
        ('Recommendation',          f'STRONGLY RECOMMENDED — potential ${cs_tax_saved:,.0f} IL estate tax savings'),
    ]
    for label, detail in cs_rows:
        is_rec = 'STRONGLY' in detail
        bg = 'C6EFCE' if is_rec else cs_bg
        write_cell(ws, r, 1, label, bold=True, bg=bg)
        write_cell(ws, r, 2, detail, bg=bg, bold=is_rec)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        r += 1

    qc('14. Estate Plan', 'Federal/IL tax, QTIP, Credit Shelter documented', True,
       f"IL est. tax: ${il_tax if c['model_state_est'] else 0:,.0f}, CS saves ~${cs_tax_saved:,.0f}")




__all__ = ['build_sheet9', 'build_sheet10', 'build_sheet11', 'build_sheet12', 'build_sheet13', 'build_sheet14']
