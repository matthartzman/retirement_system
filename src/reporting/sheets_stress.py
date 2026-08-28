from .workbook_common import (
    Alignment,
    BLUE,
    DGRAY,
    FMT_DOLLAR,
    FMT_PCT,
    FMT_YEAR,
    Font,
    GRAY,
    GREEN,
    LGRAY,
    NAVY,
    ORANGE,
    WHITE,
    _aa,
    annuity_cash_income,
    deflate_to_present,
    essential_discretionary_floor_check,
    fill,
    ltcg_tax_on_gain,
    project,
    qc,
    run_scenario as _run_scenario,
    section_title,
    thin_border,
    write_cell,
    write_hdr,
)
from ..person_labels import display_accounts_in_text as _display_accounts_in_text
from . import summary_figures
def build_sheet15(ws, c, rows, mc_data):
    """Market-Luck Stress Test — 8 sections:
    A. Methodology  B. Headline Results  B3. Required Spending Cut on Failing
    Paths  C. Ending NW Distribution  D. Year-by-Year Percentile Bands
    E. Sequence-of-Returns Quintiles  F. Sensitivity Grid
    G. Interpretation & Adjustments
    """
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A4'

    # ── unpack mc_data ────────────────────────────────────────────────────────
    total_pct = mc_data['pct_by_year']
    pct  = mc_data.get('liquid_pct_by_year', total_pct)
    qnts = mc_data['quintiles']
    sens = mc_data['sensitivity']
    yrs  = mc_data['years']
    mus  = mc_data['mus']
    sigs = mc_data['sigs']
    mu   = mc_data['mu']
    sig  = mc_data['sig']
    N    = mc_data['n_sims']
    seed = mc_data['seed']
    suc  = mc_data['success_rate']
    nw0  = mc_data['nw0']
    end_yr = c['plan_end']

    section_title(ws, 1, f'MARKET-LUCK STRESS TEST — Monte Carlo  ·  {N:,} Simulations', 10)

    def hdr2(r, c_, text, bg=NAVY, span=1):
        write_hdr(ws, r, c_, text, bg, WHITE, span=span)

    def dat(r, c_, val, fmt=None, bg=None, bold=False, align='right'):
        write_cell(ws, r, c_, val, fmt=fmt, bold=bold, bg=bg, align=align)

    r = 3

    # ══════════════════════════════════════════════════════════════════════════
    # A. METHODOLOGY
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'A.  Methodology', bg=BLUE, span=10); r += 1

    params = [
        ('Simulations',           f'{N:,}'),
        ('Random Seed',           str(seed)),
        ('Configured Portfolio Return μ', f'{mc_data.get("configured_mu", mu):.1%}  (deterministic reference return)'),
        ('MC Portfolio Return Model', str(mc_data.get('portfolio_return_model', 'single_blended_mu_sigma')).replace('_', ' ')),
        ('MC Expected Return μ', f'{mu:.1%}  (arithmetic expected return used in simulations)'),
        ('Sampled Arithmetic Mean Return',    f'{mc_data.get("sampled_mean_return", mu):.1%} across simulated years'),
        ('Sampled Geometric Mean Return',     f'{mc_data.get("sampled_geometric_return", mc_data.get("sampled_mean_return", mu)):.1%} compounded across simulated years'),
        ('Annual Return Std Dev σ', f'{sig:.1%}'),
        ('Sampled Mean Inflation', f'{mc_data.get("sampled_mean_inflation", c.get("inf", 0.025)):.1%} across simulated years'),
        ('Return Distribution',    'Asset-class covariance or blended μ/σ, with regime/fat-tail annual draws and AR(1) serial dependence when enabled'),
        ('Regime Recentered?',     'YES' if mc_data.get('return_recentered', True) else 'NO'),
        ('Wellness Shock Events', f'{mc_data.get("sampled_wellness_shock_count", 0):,}; mean event cost ${mc_data.get("sampled_wellness_shock_mean_cost", 0):,.0f}'),
        ('Starting Liquid Assets', f'${nw0:,.0f}'),
        ('Net Portfolio Draw',     'Spending + taxes minus non-portfolio income streams; stochastic inflation and wellness shocks apply inside MC'),
        ('Plan Horizon',           f'{c["plan_start"]}–{c["plan_end"]}  ({len(yrs)} years)'),
        ('Success Definition',     mc_data.get('success_definition', 'Liquid assets remain positive and no annual spending gap is unfunded')),
        ('Success Rate 95% CI',    f'{mc_data.get("success_rate_ci_low", suc):.1%}–{mc_data.get("success_rate_ci_high", suc):.1%} (SE {mc_data.get("success_rate_standard_error", 0):.1%})'),
        ('Sequence-of-Returns',    'Sims sorted by first-5-year average return, split into quintiles'),
        ('Asset Location',         'Per-account holdings differences enter as a constant return offset per tax bucket, '
                                   'renormalized each year so they redistribute return between buckets without changing '
                                   'the portfolio total. Cash accounts are modeled separately on a short-rate path.'),
        ('Asset Location — Limits', 'Within the taxable / pretax / Roth / HSA buckets, every account takes the SAME annual '
                                   'market shock and differs only by that constant offset — sleeves are not simulated with '
                                   'their own volatility. This model therefore cannot credit a bond tent or de-risking '
                                   'glidepath held inside retirement accounts with reducing failure risk, and the success '
                                   'rate should not be read as evidence for or against those strategies. Cash reserves held '
                                   'in cash accounts ARE modeled with their own low-volatility path.'),
        ('Sensitivity Grid',       f'{mc_data.get("sensitivity_sims", 200):,} full re-simulations per cell; μ ∈ {{4%–8%}}, σ ∈ {{8%–16%}}'),
        ('Note',                   'Deterministic projection is a no-volatility reference path; MC median is the probabilistic planning number.'),
    ]
    hdr2(r, 1, 'Parameter', bg=DGRAY, span=3)
    hdr2(r, 4, 'Value / Description', bg=DGRAY, span=7); r += 1
    for label, val in params:
        dat(r, 1, label, bold=True, bg=LGRAY, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        dat(r, 4, val, align='left')
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=10)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # B. HEADLINE RESULTS
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'B.  Headline Results', bg=BLUE, span=10); r += 1

    end_pct = pct[end_yr]
    total_end_pct = total_pct[end_yr]
    n10_end = end_pct[10];  n50_end = end_pct[50];  n90_end = end_pct[90]
    n25_end = end_pct[25];  n75_end = end_pct[75]
    mean_end = end_pct['mean']
    total_n50_end = total_end_pct[50]
    deterministic_terminal_total = rows[-1].get('total_nw', 0)
    deterministic_terminal_liquid = (rows[-1].get('pretax_nw', 0) + rows[-1].get('roth_nw', 0) +
                                     rows[-1].get('trust_nw', 0) + rows[-1].get('hsa_nw', 0))

    headline_items = [
        ('Plan Funding Success Rate',            suc,      FMT_PCT,    suc >= 0.85),
        ('Success Rate CI Low (95%)',            mc_data.get('success_rate_ci_low', suc), FMT_PCT, mc_data.get('success_rate_ci_low', suc) >= 0.80),
        ('Success Rate CI High (95%)',           mc_data.get('success_rate_ci_high', suc), FMT_PCT, True),
        ('Median Terminal Liquid Assets (P50)',  n50_end,  FMT_DOLLAR, n50_end > 0),
        ('P10 Terminal Liquid Assets',           n10_end,  FMT_DOLLAR, n10_end > 0),
        ('P25 Terminal Liquid Assets',           n25_end,  FMT_DOLLAR, n25_end > 0),
        ('P75 Terminal Liquid Assets',           n75_end,  FMT_DOLLAR, True),
        ('P90 Terminal Liquid Assets',           n90_end,  FMT_DOLLAR, True),
        ('Mean Terminal Liquid Assets',          mean_end, FMT_DOLLAR, True),
        ('Median Terminal Total Net Worth',      total_n50_end, FMT_DOLLAR, True),
    ]
    hdr2(r, 1, 'Metric',  bg=DGRAY, span=5)
    hdr2(r, 6, 'Value',   bg=DGRAY, span=2)
    hdr2(r, 8, 'Status',  bg=DGRAY, span=3); r += 1
    for label, val, fmt, ok in headline_items:
        bg_s = 'E2EFDA' if ok else 'FCE4D6'
        dat(r, 1, label, bold=True, bg=LGRAY, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        dat(r, 6, val, fmt=fmt, bold=True)
        ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=7)
        dat(r, 8, 'On Track' if ok else 'Review', bg=bg_s, bold=True, align='center')
        ws.merge_cells(start_row=r, start_column=8, end_row=r, end_column=10)
        r += 1
    r += 1

    # B2. Deterministic vs Monte Carlo comparison — keeps total NW and liquid funding distinct.
    section_title(ws, r, 'B2.  Deterministic vs Monte Carlo Comparison', bg=GREEN, span=10); r += 1
    compare_hdrs = ['Measure', 'No-Volatility Deterministic Reference', 'MC P10', 'MC P50', 'MC P90', 'Purpose']
    spans = [(1,2), (3,4), (5,5), (6,6), (7,7), (8,10)]
    for (start, end), h in zip(spans, compare_hdrs):
        hdr2(r, start, h, bg=DGRAY, span=(end-start+1))
    r += 1
    # C5 / Wave 3.4: the terminal-year figures above are nominal, and a
    # plan-end dollar buys less than a plan-start dollar -- add the same row
    # in today's purchasing power immediately below so the two are directly
    # comparable, not just readable side by side.
    _terminal_pv = lambda v: deflate_to_present(v, c['plan_end'], c)
    comp_rows = [
        ('Terminal Total Net Worth', deterministic_terminal_total, total_end_pct[10], total_end_pct[50], total_end_pct[90],
         'Broad estate/net-worth measure including illiquid assets. Deterministic line is a reference path, not the MC median.'),
        ("Terminal Total Net Worth (Today's $)", _terminal_pv(deterministic_terminal_total),
         _terminal_pv(total_end_pct[10]), _terminal_pv(total_end_pct[50]), _terminal_pv(total_end_pct[90]),
         'Same measure, deflated to plan-start purchasing power.'),
        ('Terminal Liquid Retirement Assets', deterministic_terminal_liquid, end_pct[10], end_pct[50], end_pct[90],
         'Spendable funding measure used for MC success.'),
        ("Terminal Liquid Retirement Assets (Today's $)", _terminal_pv(deterministic_terminal_liquid),
         _terminal_pv(end_pct[10]), _terminal_pv(end_pct[50]), _terminal_pv(end_pct[90]),
         'Same measure, deflated to plan-start purchasing power.'),
        ('Success Liquidity Floor', mc_data.get('success_liquid_floor', 0), '', '', '',
         f"Success requires no unfunded gaps and liquid assets above {mc_data.get('success_liquid_floor_source','configured floor')} every year."),
    ]
    for label, det, p10, p50, p90, purpose in comp_rows:
        dat(r, 1, label, bold=True, bg=LGRAY, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        dat(r, 3, det, fmt=FMT_DOLLAR, bold=True)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        if p10 != '': dat(r, 5, p10, fmt=FMT_DOLLAR)
        if p50 != '': dat(r, 6, p50, fmt=FMT_DOLLAR, bold=True)
        if p90 != '': dat(r, 7, p90, fmt=FMT_DOLLAR)
        dat(r, 8, purpose, align='left')
        ws.merge_cells(start_row=r, start_column=8, end_row=r, end_column=10)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # B3. REQUIRED SPENDING CUT ON FAILING PATHS (P13 phase 1 — additive
    # diagnostic; does not change the success rate reported above)
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'B3.  Required Spending Cut to Rescue Failing Paths', bg=GREEN, span=10); r += 1
    rc = mc_data.get('required_cut_distribution') or {}
    n_failing = rc.get('n_failing', 0)
    if n_failing:
        # Wave 5.5: does the median/P90 required cut fit entirely inside
        # discretionary (Travel / Large Discretionary) spending, or would it
        # have to reach into essentials (housing, wellness, core spend_base)?
        median_floor = essential_discretionary_floor_check(rows, rc.get('required_cut_median'))
        p90_floor = essential_discretionary_floor_check(rows, rc.get('required_cut_p90'))

        def _floor_label(floor):
            if floor.get('essential_protected') is None:
                return 'n/a'
            if floor.get('essential_protected'):
                return 'Discretionary-only'
            return (f"Reaches essentials in {floor.get('worst_year')} "
                    f"(~${floor.get('worst_year_essential_shortfall', 0.0):,.0f})")

        rc_rows = [
            ('Failing Paths Analyzed', n_failing, None, None),
            ('Median Required Spending Cut', rc.get('required_cut_median'), FMT_PCT, _floor_label(median_floor)),
            ('Worst-Decile (P90) Required Spending Cut', rc.get('required_cut_p90'), FMT_PCT, _floor_label(p90_floor)),
            ('Failing Paths With No Feasible Uniform Cut', rc.get('n_infeasible', 0), None, None),
        ]
        for label, val, fmt, floor_label in rc_rows:
            dat(r, 1, label, bold=True, bg=LGRAY, align='left')
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
            dat(r, 6, val if val is not None else 'n/a', fmt=fmt, bold=True)
            ws.merge_cells(start_row=r, start_column=6, end_row=r, end_column=7)
            dat(r, 8, floor_label or '', align='left')
            ws.merge_cells(start_row=r, start_column=8, end_row=r, end_column=10)
            r += 1
        dat(r, 1, 'The uniform, whole-plan spending cut (taxable/pretax/Roth/cash withdrawals — HSA draws for '
                  'wellness shocks excluded) that would have kept each failing simulation funded, holding that '
                  'simulation\'s own sampled returns, inflation and death year fixed. Diagnostic only: does not '
                  'change the success rate above and is not a recommended policy. "Discretionary-only" means the '
                  'cut fits entirely within Travel/Large Discretionary spending every year without touching '
                  'housing, wellness, or core spending.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    else:
        dat(r, 1, 'No failing paths in this run — every simulation stayed funded, so there is no required-cut '
                  'distribution to report.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # B4. SUSTAINABLE SPENDING (system review 5.1: "what's the most I can
    # sustainably spend?" -- the planner's most common client question. Reuses
    # B3's per-path binary-search machinery, bisecting a uniform whole-plan
    # cut against the OVERALL success rate for each target confidence level
    # instead of a per-path rescue cut.)
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'B4.  Sustainable Spending — What Can This Plan Support?', bg=GREEN, span=10); r += 1
    sustainable = mc_data.get('sustainable_spending_solve') or []
    if sustainable:
        hdr2(r, 1, 'Target Success Rate', bg=DGRAY, span=2)
        hdr2(r, 3, 'Sustainable Annual Spending', bg=DGRAY, span=2)
        hdr2(r, 5, 'Spending Cut vs. Current Plan', bg=DGRAY, span=2)
        hdr2(r, 7, 'Achieved Success Rate', bg=DGRAY, span=2)
        hdr2(r, 9, 'Note', bg=DGRAY, span=2); r += 1
        for row in sustainable:
            cut = row.get('required_cut', 0.0) or 0.0
            note = '' if row.get('feasible', True) else 'Even the largest modeled cut cannot reach this target.'
            # Wave 5.5: does this cut fit entirely inside discretionary
            # (Travel / Large Discretionary) spending, or would it reach
            # into essentials (housing, wellness, core spend_base)?
            if row.get('essential_protected') is True:
                note = (note + ' ' if note else '') + 'Discretionary-only — essentials untouched.'
            elif row.get('essential_protected') is False:
                note = (note + ' ' if note else '') + (
                    f"Reaches essential spending in {row.get('essential_shortfall_worst_year')} "
                    f"(~${row.get('essential_shortfall_worst_year_amount', 0.0):,.0f}).")
            dat(r, 1, row.get('target_success_rate'), fmt=FMT_PCT, bold=True); ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
            dat(r, 3, row.get('sustainable_spend_base'), fmt=FMT_DOLLAR, bold=True); ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
            dat(r, 5, cut, fmt=FMT_PCT); ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
            dat(r, 7, row.get('achieved_success_rate'), fmt=FMT_PCT); ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=8)
            dat(r, 9, note, align='left'); ws.merge_cells(start_row=r, start_column=9, end_row=r, end_column=10)
            r += 1
        dat(r, 1, 'Sustainable Annual Spending is this plan\'s current spend_base uniformly scaled by the smallest '
                  'whole-plan cut (taxable/pretax/Roth/cash withdrawals; HSA draws for wellness shocks excluded) '
                  'that reaches each target success rate, holding every other plan input fixed. A 0% cut means the '
                  'current spending level already clears that target. "Discretionary-only" means the cut can come '
                  'entirely from Travel/Large Discretionary spending every year, protecting housing, wellness, and '
                  'core spending as a floor.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    else:
        dat(r, 1, 'Sustainable spending solve not available for this run.', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # C. ENDING LIQUID ASSET PERCENTILE DISTRIBUTION
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'C.  Ending Liquid Asset Percentile Distribution', bg=BLUE, span=10); r += 1

    pct_bands = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    hdr2(r, 1, 'Percentile', bg=DGRAY)
    hdr2(r, 2, f'Terminal Liquid Assets ({end_yr})', bg=DGRAY, span=3)
    hdr2(r, 5, 'vs Median', bg=DGRAY, span=2)
    hdr2(r, 7, 'Interpretation', bg=DGRAY, span=4); r += 1

    interps = {
        1:  'Catastrophic — total portfolio loss',
        5:  'Very bad luck — significant shortfall',
        10: 'Poor sequence — stress-test floor',
        25: '1-in-4 downside scenario',
        50: 'Base case — median outcome',
        75: '3-in-4 scenarios end above this',
        90: 'Good sequence — upside scenario',
        95: 'Very good luck',
        99: 'Exceptional returns',
    }
    p50v = end_pct[50]
    for p in pct_bands:
        v = end_pct[p]
        vs_med = v - p50v
        bg = GRAY if p == 50 else (LGRAY if p in (25,75) else None)
        bold = (p == 50)
        dat(r, 1, f'P{p}', bold=bold, bg=bg, align='center')
        dat(r, 2, v, fmt=FMT_DOLLAR, bold=bold, bg=bg)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        dat(r, 5, vs_med, fmt=FMT_DOLLAR, bg=bg)
        ws.merge_cells(start_row=r, start_column=5, end_row=r, end_column=6)
        dat(r, 7, interps.get(p,''), bg=bg, align='left')
        ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=10)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # D. YEAR-BY-YEAR LIQUID ASSET PERCENTILE BANDS
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'D.  Year-by-Year Liquid Asset Percentile Bands', bg=BLUE, span=10); r += 1

    band_hdrs = ['Year', 'Age H', 'Age W', 'P10', 'P25', 'P50 Median', 'P75', 'P90', 'Mean', 'Success %']
    for i, h in enumerate(band_hdrs, 1):
        hdr2(r, i, h, bg=DGRAY)
    r += 1

    D_DATA_FIRST = r  # save for chart reference later

    for row in rows:
        yr   = row['year']
        d    = pct[yr]
        hage = row['h_age']
        wage = row['w_age']
        suc_yr = d['success']
        bg = 'FCE4D6' if suc_yr < 0.70 else (LGRAY if suc_yr < 0.90 else None)
        for i, v in enumerate([yr, hage, wage, d[10], d[25], d[50],
                                d[75], d[90], d['mean'], suc_yr], 1):
            fmt = FMT_YEAR if i==1 else ('0' if i in (2,3) else
                  (FMT_PCT if i==10 else FMT_DOLLAR))
            write_cell(ws, r, i, v, fmt=fmt, bg=bg, bold=(i==6))
        r += 1

    D_DATA_LAST = r - 1  # last data row

    r = D_DATA_LAST + 2

    # ══════════════════════════════════════════════════════════════════════════
    # E. SEQUENCE-OF-RETURNS RISK — QUINTILES
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'E.  Sequence-of-Returns Risk — Quintiles by First-5-Year Avg Return', bg=BLUE, span=10); r += 1

    sq_hdrs = ['Quintile', 'Avg First-5-Yr Return', 'P10 End Liquid', 'Median End Liquid',
               'P90 End Liquid', 'Avg End Liquid', 'Funding Success', 'Key Insight']
    for i, h in enumerate(sq_hdrs, 1):
        hdr2(r, i, h, bg=DGRAY)
    r += 1

    insights = [
        'Retire into a bear market: portfolio may not recover',
        'Below-avg early returns: monitor spending levels',
        'Middle outcome: plan as modeled',
        'Above-avg early returns: strong buffer builds fast',
        'Bull market at retirement: large bequest potential',
    ]
    q_colors = ['FCE4D6','FFF2CC','F4F5F7','E2EFDA','C6EFCE']
    for qi, q in enumerate(qnts):
        bg = q_colors[qi]
        dat(r, 1, q['label'],  bold=True, bg=bg, align='left')
        dat(r, 2, q['avg_r5'], fmt=FMT_PCT, bg=bg)
        dat(r, 3, q['p10_end'],fmt=FMT_DOLLAR, bg=bg)
        dat(r, 4, q['med_end'],fmt=FMT_DOLLAR, bold=True, bg=bg)
        dat(r, 5, q['p90_end'],fmt=FMT_DOLLAR, bg=bg)
        dat(r, 6, q['avg_end'],fmt=FMT_DOLLAR, bg=bg)
        dat(r, 7, q['success'],fmt=FMT_PCT, bold=True, bg=bg)
        dat(r, 8, insights[qi], bg=bg, align='left')
        ws.merge_cells(start_row=r, start_column=8, end_row=r, end_column=10)
        r += 1

    # key note
    r += 1
    note = ('Sequence-of-Returns Risk is the dominant tail risk in this plan. '
            'The spread between Q1 and Q5 success rates measures it: identical average '
            'returns in a different order produce these different outcomes. Roth conversions '
            'move these numbers, because the conversion and the tax it triggers are simulated '
            'on every path. The Reserve requirement does not — reserved taxable/Trust dollars '
            'take the same annual market shock as the rest of the bucket. See section G.')
    dat(r, 1, note, align='left', bg=LGRAY)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
    r += 2

    # ══════════════════════════════════════════════════════════════════════════
    # F. SENSITIVITY ANALYSIS — FULL RE-SIMULATIONS, μ × σ GRID
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, f'F.  Sensitivity Analysis — {mc_data.get("sensitivity_sims", 100):,} Sims per Cell  ·  Varying μ (Return) × σ (Volatility)', bg=BLUE, span=10); r += 1

    # Header: σ across, μ down
    dat(r, 1, 'Return (mu) / Vol (sigma)', bold=True, bg=DGRAY, align='center')
    for j, sig_v in enumerate(sigs):
        hdr2(r, 2 + j, f'σ={sig_v:.0%}', bg=DGRAY)
    hdr2(r, 2 + len(sigs), 'Best σ', bg=NAVY); r += 1

    BASE_MU  = c['ret']
    BASE_SIG = 0.12
    for mu_v in mus:
        row_best = max(sens[(mu_v, s)] for s in sigs)
        dat(r, 1, f'μ={mu_v:.0%}', bold=(mu_v == BASE_MU), bg=LGRAY, align='center')
        for j, sig_v in enumerate(sigs):
            rate = sens[(mu_v, sig_v)]
            # Colour: green ≥90%, yellow 70-90%, red <70%
            is_base = (abs(mu_v - BASE_MU) < 0.001 and abs(sig_v - BASE_SIG) < 0.001)
            bg = ('C6EFCE' if rate >= 0.90 else
                  ('FFEB9C' if rate >= 0.70 else 'FFC7CE'))
            if is_base:
                bg = 'BDD7EE'  # highlight base case in blue
            dat(r, 2 + j, rate, fmt=FMT_PCT, bold=is_base, bg=bg)
        dat(r, 2 + len(sigs), row_best, fmt=FMT_PCT, bold=True, bg='E2EFDA')
        r += 1

    # Legend
    r += 1
    legend_items = [
        ('BDD7EE', f'Base case (μ={BASE_MU:.0%}, σ={BASE_SIG:.0%})'),
        ('C6EFCE', 'Success ≥ 90%  — plan highly resilient'),
        ('FFEB9C', 'Success 70–89%  — monitor; consider adjustments'),
        ('FFC7CE', 'Success < 70%  — stress zone; action likely needed'),
    ]
    for bg, lbl in legend_items:
        dat(r, 1, '', bg=bg)
        dat(r, 2, lbl, align='left', bg='F4F5F7')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1
    r += 1

    # ══════════════════════════════════════════════════════════════════════════
    # G. INTERPRETATION, IMPLICATIONS & ADJUSTMENTS
    # ══════════════════════════════════════════════════════════════════════════
    section_title(ws, r, 'G.  Interpretation, Implications & Adjustments', bg=BLUE, span=10); r += 1

    items = [
        ('Overall Plan Assessment',
         f'At configured μ={BASE_MU:.0%}/σ={BASE_SIG:.0%}, the plan has a {suc:.0%} liquid-funding success rate — '
         f'{"strong" if suc >= 0.85 else "moderate" if suc >= 0.70 else "marginal"} by '
         'institutional planning standards. Median terminal liquid assets of '
         f'${pct[end_yr][50]:,.0f} and median total net worth of ${total_pct[end_yr][50]:,.0f} '
         'are shown separately so illiquid wealth does not mask spending shortfalls. '
         f'The sampled arithmetic/geometric returns were {mc_data.get("sampled_mean_return", BASE_MU):.1%}/'
         f'{mc_data.get("sampled_geometric_return", mc_data.get("sampled_mean_return", BASE_MU)):.1%}; '
         f'success requires maintaining the liquidity floor of ${mc_data.get("success_liquid_floor", 0):,.0f}.'),
        ('Primary Risk: Sequence-of-Returns',
         'The first 5–10 years of retirement carry the highest risk. A sustained bear '
         'market early in the distribution phase, before Social Security and annuity income '
         'fully offset spending, can permanently impair the portfolio. The mitigation this model '
         'credits is withdrawal ORDER: the cascade spends cash-type accounts first, and cash grows '
         'on a short-rate path rather than the equity draw, so reserves held in a cash account are '
         'insulated from an early bear market. The configured liquidity buffer is not that: it '
         'sets a floor under the taxable/Trust draw, redirecting spending to other buckets while '
         'every reserved dollar still takes the full taxable-bucket market shock. That floor is '
         'applied only in the deterministic cascade, not re-enforced against each simulated path.'),
        ('Annuity Income as a Floor',
         f'{str(c.get("w_nick") or c.get("w_name") or "Member 2")} pension + joint annuities provide deterministic income starting in the configured income year. '
         'This income floor reduces spending pressure, but it does not by itself guarantee liquid funding success. '
         f'In Q1 (worst first-5-year return paths), funded-plan success is {qnts[0]["success"]:.0%}, '
         'so early-market losses remain an important risk-control trigger.'),
        ('When to Take Action',
         'Monitor the actual first-5-year portfolio return vs the Q1/Q2 threshold. '
         'If cumulative return through the configured checkpoint year is below +10% total, consider: '
         '(1) Reduce discretionary spending (vacations, home projects); '
         '(2) Accelerate Roth conversions to reduce future RMD tax drag; '
         '(3) Delay Social Security claim if not yet claimed; '
         '(4) Consider a partial annuity purchase to increase income floor.'),
        ('Return Assumption Stress',
         f'At μ=7%, success ranges from {min(sens[(0.07,s)] for s in sigs):.0%}–{max(sens[(0.07,s)] for s in sigs):.0%} '
         f'across the tested volatility levels. At μ=5%, success ranges from '
         f'{min(sens[(0.05,s)] for s in sigs):.0%}–{max(sens[(0.05,s)] for s in sigs):.0%}. '
         'These cells are full re-simulations, not a shortcut based on terminal net worth.'),
        ('Recommended Annual Review',
         'Compare actual portfolio return to the base-case assumption each December. '
         'If 3-year trailing return is below 3% annualised, trigger a plan review '
         'and spending adjustment discussion. Re-run this Monte Carlo annually.'),
    ]

    hdr2(r, 1, 'Topic', bg=DGRAY, span=2)
    hdr2(r, 3, 'Interpretation', bg=DGRAY, span=8); r += 1
    for topic, body in items:
        dat(r, 1, topic, bold=True, bg=LGRAY, align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        dat(r, 3, body, align='left')
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=10)
        ws.row_dimensions[r].height = 45
        r += 1

    # ── Column widths ─────────────────────────────────────────────────────────
    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 16
    ws.column_dimensions['C'].width = 16
    ws.column_dimensions['D'].width = 16
    ws.column_dimensions['E'].width = 16
    ws.column_dimensions['F'].width = 16
    ws.column_dimensions['G'].width = 16
    ws.column_dimensions['H'].width = 16
    ws.column_dimensions['I'].width = 16
    ws.column_dimensions['J'].width = 16

    qc('15. Market-Luck Stress Test',
       f'7-section MC report: {N} sims, {len(qnts)} quintiles, {len(mus)*len(sigs)}-cell sensitivity',
       True, f'Funding success={suc:.1%}, P50 liquid end=${pct[end_yr][50]:,.0f}')


def build_sheet16(ws, c, rows):
    """Scenario Analysis"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'WHAT-IF SCENARIO ANALYSIS', 8)

    r = 3
    write_hdr(ws, r, 1, 'Deterministic Scenarios', NAVY, WHITE, span=6); r+=1
    hdrs = ['Scenario','Assumption Change','Ending NW','Lifetime Tax',
            'Plan Survives?','Delta vs Base']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    base_nw   = rows[-1]['total_nw']
    base_tax  = sum(row['total_tax'] for row in rows)

    # ── Run actual re-projections for each scenario ───────────────────────────
    def run_scenario(overrides):
        """Re-run project() with a modified copy of c and return (term_nw, lifetime_tax)."""
        _c2, rows2 = _run_scenario(c, overrides)
        return rows2[-1]['total_nw'], sum(row['total_tax'] for row in rows2)

    # Allocation scenarios: compare user-specified target_pct versus optimizer
    # recommendation as actual what-ifs.  Each scenario switches allocation mode
    # and uses that allocation's weighted expected return/volatility so it has a
    # cash-flow and terminal-net-worth impact rather than only changing display.
    from .. import allocation_policy as _ap
    from ..optimization import allocation_portfolio_stats

    def run_allocation_scenario(mode):
        stats = allocation_portfolio_stats(c, force_mode=mode)
        nw, tax = run_scenario({
            'allocation_selection_mode': stats['mode'],
            'ret': stats['expected_return'],
            'mc_sigma': stats['volatility'],
            'allocation_scenario_stats': stats,
        })
        return nw, tax, stats

    nw_alloc_user, tax_alloc_user, stats_alloc_user = run_allocation_scenario(_ap.ALLOCATION_MODE_USER)
    nw_alloc_opt, tax_alloc_opt, stats_alloc_opt = run_allocation_scenario(_ap.ALLOCATION_MODE_OPTIMIZER)

    # Retire later: extend earn_end to CSV value; mark original as base_earn_end
    # Extension years use scen_retire_inc_growth and scen_retire_salary from CSV.
    retire_later_yr = c['scen_retire_later_yr']
    nw_retire, tax_retire = run_scenario({
        'earn_end':      retire_later_yr,
        'base_earn_end': c['earn_end'],   # original earn_end → triggers extension logic
    })

    # Spend more: multiply spend_base by CSV multiplier
    nw_spend, tax_spend = run_scenario({'spend_base': c['spend_base'] * c['scen_spend_mult']})

    # Sell Home scenario — full model matching project() home sale logic
    sell_yr   = c['scen_sell_yr']
    sell_px   = c['scen_sell_px']
    sell_basis= c['scen_sell_basis']
    sell_acct = _display_accounts_in_text(c['scen_sell_acct'], c)
    # Projected home value at sale year
    home_at_sell = c['home_val'] * (1 + c['home_appr']) ** (sell_yr - c['plan_start'])
    gross_sell   = sell_px if sell_px > 0 else home_at_sell
    # Selling costs
    sell_costs   = gross_sell * c['home_sell_cost_pct']
    # Remaining mortgage at sale year (from amortization schedule)
    mort_at_sell = c['mort_schedule'].get(sell_yr, 0.0)
    if sell_yr > c['mort_end']:
        mort_at_sell = 0
    # Capital gain (net of selling costs), §121, bracketed LTCG tax
    cap_gain_sell   = max(0, gross_sell - sell_costs - sell_basis)
    taxable_sell    = max(0, cap_gain_sell - c['sec121'])
    ltcg_tax_sell   = ltcg_tax_on_gain(c, taxable_sell, 0, sell_yr)
    net_sell        = max(0, gross_sell - sell_costs - mort_at_sell - ltcg_tax_sell)
    # Run scenario: inject home sale parameters and zero out base home_sale_yr
    nw_sell, tax_sell = run_scenario({
        'home_sale_yr':   sell_yr,
        'home_sale_px':   gross_sell,
        'home_basis':     sell_basis,
        'home_sale_acct': sell_acct,
    })

    # High inflation: use CSV override rate
    nw_inf, tax_inf = run_scenario({'inf': c['scen_inf_override']})

    # Low return: use CSV override rate
    nw_ret, tax_ret = run_scenario({'ret': c['scen_ret_override']})

    # Optimization-refactor Phase 6: No SS Benefit Cut. The BASE plan already
    # models the trust-fund funding-discount haircut by default
    # (ss_funding_discount_year/pct, default 2032/22%) -- this scenario shows
    # the upside if that pessimistic default assumption does NOT materialize,
    # i.e. Congress fixes funding and full benefits are paid.
    nw_no_ss_cut, tax_no_ss_cut = run_scenario({'ss_funding_discount_pct': 0.0})

    # Optimization-refactor Phase 6: Divorce/QDRO asset split. A one-time,
    # tax-free division of every investment account at a configured year
    # (default 2029, 50/50) -- asset-split only, does not model ongoing
    # spousal support/alimony (see docs/superpowers/plans/2026-08-28-
    # phase6-scenario-implementation-design.md's Option D1).
    nw_divorce, tax_divorce = run_scenario({
        'divorce_split_yr': c['scen_divorce_yr'],
        'divorce_split_pct': c['scen_divorce_split_pct'],
    })

    # ── PDIA What-If: Lower Dividend (4.50%, same split) ─────────────────
    def run_pdia_scenario(div_override=None, cash_pct_override=None):
        """Re-run with modified annuity parameters across all streams."""
        def _mutate(c2):
            for stream_key in ['wife_pension','wife_single','wife_joint','h_single','h_joint']:
                s = c2[stream_key]
                if div_override is not None and s['base'] > 0:
                    s['div_rate'] = div_override
                if cash_pct_override is not None and s['base'] > 0:
                    s['add_pct'] = 1.0 - cash_pct_override
        _c2, rows2 = _run_scenario(c, mutate=_mutate)
        return rows2[-1]['total_nw'], sum(row['total_tax'] for row in rows2)

    nw_pdia_lo, tax_pdia_lo = run_pdia_scenario(div_override=c['scen_pdia_div_lo'])
    nw_pdia_5050, tax_pdia_5050 = run_pdia_scenario(cash_pct_override=c['scen_pdia_split_5050'])

    # ── Stackable combined scenario: apply ALL active overrides in one run ────
    def run_combined_scenario(toggles):
        """Apply multiple overrides simultaneously (sell home + low return + 4.5% div etc.).
        toggles is a dict of which overrides to activate."""
        def _mutate(c2):
            if toggles.get('sell_home'):
                c2['home_sale_yr']   = sell_yr
                c2['home_sale_px']   = gross_sell
                c2['home_basis']     = sell_basis
                c2['home_sale_acct'] = sell_acct
            if toggles.get('low_return'):
                c2['ret'] = c['scen_ret_override']
            if toggles.get('high_inflation'):
                c2['inf'] = c['scen_inf_override']
            if toggles.get('spend_more'):
                c2['spend_base'] = c['spend_base'] * c['scen_spend_mult']
            if toggles.get('retire_later'):
                c2['earn_end'] = retire_later_yr
                c2['base_earn_end'] = c['earn_end']
            for sk in ['wife_pension','wife_single','wife_joint','h_single','h_joint']:
                s = c2[sk]
                if toggles.get('pdia_low_div') and s['base'] > 0:
                    s['div_rate'] = c['scen_pdia_div_lo']
                if toggles.get('pdia_5050') and s['base'] > 0:
                    s['add_pct'] = 1.0 - c['scen_pdia_split_5050']
        _c2, rows2 = _run_scenario(c, mutate=_mutate)
        return rows2[-1]['total_nw'], sum(row['total_tax'] for row in rows2)

    # Read which toggles are active from CSV (Scenarios / Combined Stress Test)
    combo_toggles = {
        'sell_home':      c.get('combo_sell_home', True),
        'low_return':     c.get('combo_low_return', True),
        'high_inflation': c.get('combo_high_inflation', False),
        'spend_more':     c.get('combo_spend_more', False),
        'retire_later':   c.get('combo_retire_later', False),
        'pdia_low_div':   c.get('combo_pdia_low_div', True),
        'pdia_5050':      c.get('combo_pdia_5050', False),
    }
    nw_combo, tax_combo = run_combined_scenario(combo_toggles)
    active_labels = [k.replace('_',' ') for k,v in combo_toggles.items() if v]
    combo_desc = 'Stacked: ' + ', '.join(active_labels) if active_labels else 'No overrides active'

    # Also compute annuity income delta for reference
    def annuity_income_at_year(yr, div_override=None, cash_pct_override=None):
        """Total annuity income at a specific year with optional overrides."""
        # Not a project() scenario -- doesn't need run_scenario, just a copy to mutate.
        import copy
        c2 = copy.deepcopy(c)
        for sk in ['wife_pension','wife_single','wife_joint','h_single','h_joint']:
            s = c2[sk]
            if div_override is not None and s['base'] > 0:
                s['div_rate'] = div_override
            if cash_pct_override is not None and s['base'] > 0:
                s['add_pct'] = 1.0 - cash_pct_override
        total = 0
        for sk in ['wife_pension','wife_single','wife_joint','h_single','h_joint']:
            total += annuity_cash_income(c2[sk], yr)
        return total

    # Annuity income comparison at a sample year (age 80 for husband = 2042)
    sample_yr = c['h_dob_yr'] + 80
    ann_base   = annuity_income_at_year(sample_yr)
    ann_lo_div = annuity_income_at_year(sample_yr, div_override=c['scen_pdia_div_lo'])
    ann_5050   = annuity_income_at_year(sample_yr, cash_pct_override=c['scen_pdia_split_5050'])

    scenarios = [
        ('Base Case',
         'As modeled',
         base_nw, base_tax, True, 0),

        ('Allocation — User Defined',
         f"Use user-specified target_pct allocation; implied return {stats_alloc_user['expected_return']*100:.2f}%, "
         f"volatility {stats_alloc_user['volatility']*100:.2f}%, geometric approx {stats_alloc_user['geometric_return']*100:.2f}%, "
         f"Sharpe {stats_alloc_user.get('sharpe', 0.0):.2f}",
         nw_alloc_user, tax_alloc_user, nw_alloc_user > 0, nw_alloc_user - base_nw),

        ('Allocation — Optimizer Defined',
         f"Use optimizer allocation recommendation; implied return {stats_alloc_opt['expected_return']*100:.2f}%, "
         f"volatility {stats_alloc_opt['volatility']*100:.2f}%, geometric approx {stats_alloc_opt['geometric_return']*100:.2f}%, "
         f"Sharpe {stats_alloc_opt.get('sharpe', 0.0):.2f}",
         nw_alloc_opt, tax_alloc_opt, nw_alloc_opt > 0, nw_alloc_opt - base_nw),

        (f'Retire Later ({retire_later_yr})',
         f'earn_end {retire_later_yr} vs {c["h_ret_yr"]}; '
         f'+{retire_later_yr - c["h_ret_yr"]} yrs @ '
         f'{c["scen_retire_inc_growth"]*100:.1f}% growth, '
         f'${c["scen_retire_salary"]:,.0f} salary',
         nw_retire, tax_retire, True, nw_retire - base_nw),

        (f'Spend {int((c["scen_spend_mult"]-1)*100)}% More',
         f'${c["spend_base"]*c["scen_spend_mult"]:,.0f}/yr vs ${c["spend_base"]:,.0f} base',
         nw_spend, tax_spend, nw_spend > 0, nw_spend - base_nw),

        (f'Sell Home {sell_yr}',
         f'Gross ${gross_sell:,.0f} · basis ${sell_basis:,.0f} · '
         f'net ${net_sell:,.0f} → {sell_acct}',
         nw_sell, tax_sell, True, nw_sell - base_nw),

        (f'High Inflation {c["scen_inf_override"]*100:.1f}%',
         f'Inflation {c["scen_inf_override"]*100:.1f}% vs {c["inf"]*100:.1f}%',
         nw_inf, tax_inf, nw_inf > 0, nw_inf - base_nw),

        (f'Low Return {c["scen_ret_override"]*100:.1f}%',
         f'Portfolio return {c["scen_ret_override"]*100:.1f}% vs {c["ret"]*100:.1f}%',
         nw_ret, tax_ret, nw_ret > 0, nw_ret - base_nw),

        (f'PDIA Div {c["scen_pdia_div_lo"]*100:.1f}%',
         f'All annuity dividends at {c["scen_pdia_div_lo"]*100:.1f}% '
         f'(vs illustrated 5.50-5.75%). '
         f'Annuity income at age 80: ${ann_lo_div:,.0f} vs ${ann_base:,.0f} base',
         nw_pdia_lo, tax_pdia_lo, True, nw_pdia_lo - base_nw),

        ('PDIA 50/50 Split',
         f'50% cash / 50% reinvest (vs 80/20). '
         f'Less cash now, more income growth later. '
         f'Annuity income at age 80: ${ann_5050:,.0f} vs ${ann_base:,.0f} base',
         nw_pdia_5050, tax_pdia_5050, True, nw_pdia_5050 - base_nw),

        ('No Social Security Benefit Cut',
         f'Assumes Congress fixes trust-fund funding; full benefits paid '
         f'(vs base case, which already assumes a {c["ss_funding_discount_pct"]*100:.0f}% cut '
         f'from {int(c["ss_funding_discount_year"])} onward)',
         nw_no_ss_cut, tax_no_ss_cut, True, nw_no_ss_cut - base_nw),

        (f'Divorce/QDRO Asset Split ({c["scen_divorce_split_pct"]*100:.0f}%, {int(c["scen_divorce_yr"])})',
         f'One-time, tax-free division of all investment accounts in '
         f'{int(c["scen_divorce_yr"])} — asset split only, does not model '
         f'ongoing spousal support',
         nw_divorce, tax_divorce, nw_divorce > 0, nw_divorce - base_nw),

        ('COMBINED Stress Test',
         combo_desc,
         nw_combo, tax_combo, nw_combo > 0, nw_combo - base_nw),
    ]

    for scen in scenarios:
        bg = 'E2EFDA' if scen[4] else 'FCE4D6'
        for i, val in enumerate(scen, 1):
            fmt = FMT_DOLLAR if i in (3, 4, 6) else None
            write_cell(ws, r, i,
                       val if not isinstance(val, bool) else ('YES' if val else 'NO'),
                       fmt=fmt, bg=bg if i == 5 else None)
        r += 1

    r += 2
    write_hdr(ws, r, 1, f'Sell Home Scenario Detail — {sell_yr}', BLUE, WHITE, span=6); r+=1
    for lbl, val, fmt in [
        (f'Projected Home Value at {sell_yr}',   home_at_sell,   FMT_DOLLAR),
        ('Projected Sale Price',                  gross_sell,     FMT_DOLLAR),
        (f'Less: Selling Costs ({c["home_sell_cost_pct"]*100:.0f}%)', sell_costs, FMT_DOLLAR),
        ('Cost Basis (purchase + improvements)',  sell_basis,     FMT_DOLLAR),
        ('Capital Gain (net of selling costs)',  cap_gain_sell,  FMT_DOLLAR),
        ('§121 Exclusion (MFJ)',                 c['sec121'],    FMT_DOLLAR),
        ('Taxable Capital Gain',                 taxable_sell,   FMT_DOLLAR),
        ('LTCG Tax (bracketed 0/15/20% + NIIT)', ltcg_tax_sell,  FMT_DOLLAR),
        ('Remaining Mortgage at Sale',           mort_at_sell,   FMT_DOLLAR),
        ('Net Proceeds',                         net_sell,       FMT_DOLLAR),
        (f'Deposited to: {sell_acct} (basis-free)', '',          None),
    ]:
        write_cell(ws, r, 1, lbl)
        if val != '':
            write_cell(ws, r, 2, val, fmt=fmt, bold=(lbl.startswith('Net')))
        r += 1

    # ── Spend Reduction Recommendation (#13) ──────────────────────────────────
    r += 2
    write_hdr(ws, r, 1, 'Spending Reduction Analysis', GREEN, WHITE, span=6); r += 1
    _c_spend_lo, rows_lo = _run_scenario(c, {'spend_base': c['spend_base'] * 0.90})
    nw_lo   = rows_lo[-1]['total_nw']
    delta   = nw_lo - base_nw
    write_cell(ws, r, 1, 'Current Base Spending')
    write_cell(ws, r, 2, c['spend_base'], fmt=FMT_DOLLAR); r += 1
    write_cell(ws, r, 1, 'Reduced Spending (−10%)')
    write_cell(ws, r, 2, c['spend_base'] * 0.90, fmt=FMT_DOLLAR); r += 1
    write_cell(ws, r, 1, 'Terminal NW with Reduction')
    write_cell(ws, r, 2, nw_lo, fmt=FMT_DOLLAR); r += 1
    write_cell(ws, r, 1, 'Increase in Terminal NW', bold=True)
    write_cell(ws, r, 2, delta, fmt=FMT_DOLLAR, bold=True); r += 1
    write_cell(ws, r, 1, f'A 10% spending reduction (${c["spend_base"]*0.10:,.0f}/yr) adds ${delta:,.0f} to terminal net worth.',
               bold=False); r += 1

qc('16. Scenario Analysis', 'All CSV scenarios have result rows', True, '')


# Wave 5.6 (system review 2026-08-04, planner finding
# ltc-scenarios-fixed-and-incomplete): "State-adjusted, surviving-spouse,
# modeled funding." Illustrative regional cost-of-care index, NOT a
# survey-precise figure -- coastal/high-cost-of-living states run
# meaningfully above the national median for home care and facility care,
# lower-cost-of-living states run below it.
#
# Item 291 note (this is NOT the pattern that ticket removes elsewhere):
# 1.0 here means the NATIONAL baseline, and unlisted states already default
# to it (see _ltc_state_cost_index below) -- this table is looked up by the
# household's OWN state, never silently substituted with Illinois. Illinois
# happens to sit at 1.0 only because Sheet 19's existing "OPTIMAL" LTC
# illustration ($103K/yr IL median facility care) was already implicitly
# IL-anchored when this index was built; that is a historical coincidence
# of which dollar figure got pinned first, not a design assumption that the
# household lives in Illinois.
LTC_STATE_COST_INDEX = {
    # High cost of living
    'california': 1.35, 'new york': 1.30, 'massachusetts': 1.30, 'connecticut': 1.30,
    'new jersey': 1.25, 'alaska': 1.35, 'hawaii': 1.30, 'washington': 1.20,
    'oregon': 1.15, 'district of columbia': 1.30,
    # Above national average
    'illinois': 1.0, 'minnesota': 1.10, 'wisconsin': 1.05, 'maryland': 1.15,
    'virginia': 1.05, 'colorado': 1.10, 'arizona': 1.05, 'nevada': 1.05,
    'pennsylvania': 1.05, 'michigan': 1.0,
    # Below national average
    'texas': 0.90, 'missouri': 0.85, 'oklahoma': 0.80, 'arkansas': 0.80,
    'kansas': 0.85, 'mississippi': 0.75, 'alabama': 0.80, 'louisiana': 0.85,
    'georgia': 0.90, 'tennessee': 0.85, 'north carolina': 0.90, 'south carolina': 0.85,
    'indiana': 0.90, 'ohio': 0.90, 'iowa': 0.90, 'north dakota': 0.90, 'south dakota': 0.90,
    'nebraska': 0.90, 'west virginia': 0.80, 'kentucky': 0.85,
}


def _ltc_state_cost_index(c):
    state = str(c.get('state', '') or '').strip().lower()
    return LTC_STATE_COST_INDEX.get(state, 1.0)


def _ltc_modeled_funding_source(c, rows_base, rows2, shock_years):
    """Wave 5.6: which accounts ACTUALLY funded this scenario's added LTC
    cost, from the incremental per-account withdrawal (scenario minus
    baseline) over the shock years -- not a hand-picked label."""
    registry = {a.get('id'): str(a.get('tax') or '').lower() for a in c.get('account_registry') or []}

    def _bucket(aid):
        tax = registry.get(aid, '')
        if tax == 'pre_tax':
            return 'Pre-Tax/IRA'
        if tax == 'roth':
            return 'Roth'
        if tax == 'hsa':
            return 'HSA'
        if tax == 'cash':
            return 'Cash'
        return 'Taxable/Trust'

    base_by_year = {int(r['year']): (r.get('_account_withdrawals') or {}) for r in rows_base}
    totals = {}
    for r2 in rows2:
        yr = int(r2['year'])
        if yr not in shock_years:
            continue
        base_wd = base_by_year.get(yr, {})
        scen_wd = r2.get('_account_withdrawals') or {}
        for aid, amount in scen_wd.items():
            delta = float(amount or 0.0) - float(base_wd.get(aid, 0.0) or 0.0)
            if delta > 0:
                b = _bucket(str(aid))
                totals[b] = totals.get(b, 0.0) + delta
    total = sum(totals.values())
    if total <= 1.0:
        return 'No incremental draw (absorbed by existing cash flow)'
    parts = sorted(totals.items(), key=lambda kv: -kv[1])
    return ', '.join(f'{name} ({amount / total:.0%})' for name, amount in parts if amount / total >= 0.03)


def build_sheet17(ws, c, rows):
    """LTC Stress Test — 5 actual projection re-runs with the LTC cost stream
    added to spending (same wellness_shock_by_year hook the MC engine uses).
    """
    from ..planning_engines import _funding_success
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'LONG-TERM-CARE STRESS TEST', 9)

    base_nw = rows[-1]['total_nw']
    threshold = float(c.get('mc_success_liquid_floor', 0.0) or 0.0)
    ltc_inf = c['med_inf']
    # Onset age is measured against whichever spouse is older (lower DOB year),
    # since that spouse carries the nearer-term LTC risk in a household model.
    older_dob_yr = min(c['h_dob_yr'], c['w_dob_yr'])
    n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    state_idx = _ltc_state_cost_index(c)
    state_label = str(c.get('state', '') or '').strip() or 'National'

    r = 3
    hdrs = ['Scenario', 'Onset Age', 'Annual Cost Today', 'Duration (yrs)',
            'Total Cost (inflated)', 'Funding Source (modeled)', 'Terminal NW', 'Δ vs Base', 'Plan Survives?']
    write_hdr(ws, r, 1, 'LTC Scenarios (full projection re-runs)', NAVY, WHITE, span=9); r += 1
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    # onset_age is configured per scenario via input/client_policy.csv
    # (Scenarios / LTC Stress Test section) — editable through the same
    # settings UI that edits that CSV, defaulting here only if a row is missing.
    # Annual costs are national-median illustrative figures scaled by
    # LTC_STATE_COST_INDEX for the client's actual state of residence.
    scenario_defs = [
        ('Moderate Home Care', 40000 * state_idx, 3, c.get('ltc_onset_age_moderate_home_care', 80)),
        ('Severe Home Care', 75000 * state_idx, 5, c.get('ltc_onset_age_severe_home_care', 82)),
        ('Facility (Memory Care)', 110000 * state_idx, 5, c.get('ltc_onset_age_facility_memory_care', 85)),
        ('Catastrophic (Both)', 220000 * state_idx, 7, c.get('ltc_onset_age_catastrophic_both', 87)),
    ]
    for scen_name, annual_today, years, onset_age in scenario_defs:
        ltc_start_yr = older_dob_yr + onset_age
        cost_by_year = {ltc_start_yr + k: annual_today * (1 + ltc_inf) ** k
                         for k in range(years)}
        total_cost = sum(cost_by_year.values())

        def _mutate(c2, cost_by_year=cost_by_year):
            shocks = dict(c2.get('wellness_shock_by_year') or {})
            for yr, cost in cost_by_year.items():
                shocks[yr] = shocks.get(yr, 0.0) + cost
            c2['wellness_shock_by_year'] = shocks

        _c2, rows2 = _run_scenario(c, mutate=_mutate)
        if not rows2:
            continue
        scen_nw = rows2[-1]['total_nw']
        delta_nw = scen_nw - base_nw
        survives = _funding_success(rows2, threshold)
        funding = _ltc_modeled_funding_source(c, rows, rows2, set(cost_by_year.keys()))

        bg = 'E2EFDA' if survives else 'FCE4D6'
        vals = [scen_name, onset_age, annual_today, years, total_cost, funding, scen_nw, delta_nw,
                'YES' if survives else 'NO']
        for i, val in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (3, 5, 7, 8) else None
            write_cell(ws, r, i, val, fmt=fmt, bg=bg if i == 9 else None, align='left' if i == 6 else None)
        r += 1

    # ── Surviving-spouse LTC scenario ──────────────────────────────────────
    # None of the four scenarios above model the household's other major LTC
    # risk pattern: one spouse dies first, and the survivor -- now filing
    # Single, with reduced Social Security/pension/annuity income -- later
    # needs facility care alone. Whichever spouse the baseline plan already
    # projects to outlive the other (later of h_death_yr/w_death_yr) plays
    # the survivor role here.
    survivor_is_h = c['h_death_yr'] >= c['w_death_yr']
    if survivor_is_h:
        first_death_yr = c['w_dob_yr'] + 78
        death_overrides = {'w_death_yr': first_death_yr, 'first_death_yr': first_death_yr}
        survivor_dob = c['h_dob_yr']
        survivor_label = n1
    else:
        first_death_yr = c['h_dob_yr'] + 78
        death_overrides = {'h_death_yr': first_death_yr, 'first_death_yr': first_death_yr}
        survivor_dob = c['w_dob_yr']
        survivor_label = n2
    survivor_onset_age = c.get('ltc_onset_age_facility_memory_care', 85)
    survivor_ltc_start_yr = survivor_dob + survivor_onset_age
    survivor_annual_today = 110000 * state_idx
    survivor_years = 5
    survivor_cost_by_year = {survivor_ltc_start_yr + k: survivor_annual_today * (1 + ltc_inf) ** k
                              for k in range(survivor_years)}
    survivor_total_cost = sum(survivor_cost_by_year.values())

    def _mutate_survivor(c2, death_overrides=death_overrides, cost_by_year=survivor_cost_by_year):
        c2.update(death_overrides)
        shocks = dict(c2.get('wellness_shock_by_year') or {})
        for yr, cost in cost_by_year.items():
            shocks[yr] = shocks.get(yr, 0.0) + cost
        c2['wellness_shock_by_year'] = shocks

    _c2, rows_surv = _run_scenario(c, mutate=_mutate_survivor)
    if rows_surv:
        scen_nw = rows_surv[-1]['total_nw']
        delta_nw = scen_nw - base_nw
        survives = _funding_success(rows_surv, threshold)
        funding = _ltc_modeled_funding_source(c, rows, rows_surv, set(survivor_cost_by_year.keys()))
        bg = 'E2EFDA' if survives else 'FCE4D6'
        scen_name = f'Surviving-Spouse Facility Care ({survivor_label} alone, filing Single)'
        vals = [scen_name, survivor_onset_age, survivor_annual_today, survivor_years, survivor_total_cost,
                funding, scen_nw, delta_nw, 'YES' if survives else 'NO']
        for i, val in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (3, 5, 7, 8) else None
            write_cell(ws, r, i, val, fmt=fmt, bg=bg if i == 9 else None, align='left' if i == 6 else None)
        r += 1

    r += 1
    write_cell(ws, r, 1,
               f'Costs are scaled for {state_label} (regional cost index {state_idx:.2f}x national baseline; '
               'illustrative approximation, not a survey-precise figure). Funding Source is modeled from this '
               'household\'s own actual incremental account withdrawals during each scenario\'s care years, not '
               'a hand-picked label. The Surviving-Spouse scenario is this plan\'s own baseline mortality '
               'assumption (whichever spouse the plan already expects to outlive the other) facing facility '
               'care alone, filing Single with reduced survivor income.', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    r += 2
    write_cell(ws, r, 1,
               '⚠ Recommendation: Facility-care, catastrophic, and surviving-spouse scenarios stress the plan. '
               'Consider a Hybrid Life/LTC policy to cap open-ended risk.  '
               'No LTC policy is currently in force (see Sheet 19 — Life Insurance).', bold=True)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)

    qc('17. LTC Stress Test', 'Five scenarios (incl. surviving-spouse) re-run through project() with real, '
       'state-adjusted LTC cost stream and modeled funding source; '
       'Plan Survives = liquid assets stay above floor with no unfunded gap, every year', True, '')


def _survivor_early_death_scenarios(c, rows):
    """5 early-death full projection re-runs, shared by Sheet 18 (renders them)
    and Sheet 19 (derives the life-insurance need from this household's own
    modeled early-death impact instead of generic income-multiple rules of
    thumb)."""
    base_nw = rows[-1]['total_nw']
    base_tax = sum(row['total_tax'] for row in rows)
    h_dob = c['h_dob_yr']
    w_dob = c['w_dob_yr']
    n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    early_scenarios = [
        (f'{n1} dies at 65 (before SS & annuities)',
         h_dob + 65, c['w_death_yr'],
         f'{n1} dies {h_dob + 65}. No SS claimed yet. Joint annuity income continues to {n2} at 100%. '
         f'{n1} single annuity stops. {n2} files Single.'),

        (f'{n1} dies at 72 (early retirement)',
         h_dob + 72, c['w_death_yr'],
         f'{n1} dies {h_dob + 72}. SS claimed but only a few years of benefits. Joint annuities continue. '
         f'{n2} survives as Single filer.'),

        (f'{n2} dies at 65 (pension & annuities lost early)',
         c['h_death_yr'], w_dob + 65,
         f'{n2} dies {w_dob + 65}: pension/single-life income stops immediately. '
         f'Joint annuities continue to {n1}. {n1} files Single.'),

        (f'{n2} dies at 72 (early retirement)',
         c['h_death_yr'], w_dob + 72,
         f'{n2} dies {w_dob + 72}. Pension stops. {n2} single annuity stops. '
         f'Joint annuities continue. {n1} survives as Single filer.'),

        ('Both die at 75 (shortened plan)',
         h_dob + 75, w_dob + 75,
         f'Both die by {max(h_dob, w_dob) + 75}. Plan horizon is sharply shortened. '
         'Minimal RMDs, no late-retirement spending. Tests estate value.'),
    ]
    results = []
    for label, h_death, w_death, desc in early_scenarios:
        overrides = {
            'h_death_yr': h_death,
            'w_death_yr': w_death,
            'first_death_yr': min(h_death, w_death),
            'plan_end': max(h_death, w_death),
        }
        _c2, rows2 = _run_scenario(c, overrides)
        if not rows2:
            continue
        scen_nw = rows2[-1]['total_nw']
        scen_tax = sum(row2['total_tax'] for row2 in rows2)
        results.append({
            'label': label, 'h_death': h_death, 'w_death': w_death,
            'plan_end': max(h_death, w_death),
            'scen_nw': scen_nw, 'delta_nw': scen_nw - base_nw,
            'scen_tax': scen_tax, 'delta_tax': scen_tax - base_tax,
            'desc': desc,
        })
    return {'base_nw': base_nw, 'base_tax': base_tax, 'n1': n1, 'n2': n2, 'scenarios': results}


def build_sheet18(ws, c, rows):
    """Survivor / Early-Death Stress Test — 5 actual projection re-runs."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'SURVIVOR / EARLY-DEATH STRESS TEST', 9)

    r = 3
    survivor = _survivor_early_death_scenarios(c, rows)
    base_nw = survivor['base_nw']
    base_tax = survivor['base_tax']
    n1 = survivor['n1']
    n2 = survivor['n2']
    h_dob = c['h_dob_yr']
    w_dob = c['w_dob_yr']

    write_hdr(ws, r, 1, 'Early-Death Scenarios (full projection re-runs)', NAVY, WHITE, span=9); r += 1
    hdrs = ['Scenario', f'{n1} Death', f'{n2} Death', 'Plan End', 'Terminal NW',
            'Δ vs Base', 'Lifetime Tax', 'Δ Tax', 'Description']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1

    # Base row
    write_cell(ws, r, 1, 'BASE PLAN', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, c['h_death_yr'], fmt=FMT_YEAR, bg=LGRAY)
    write_cell(ws, r, 3, c['w_death_yr'], fmt=FMT_YEAR, bg=LGRAY)
    write_cell(ws, r, 4, c['plan_end'], fmt=FMT_YEAR, bg=LGRAY)
    write_cell(ws, r, 5, base_nw, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)
    write_cell(ws, r, 6, 'Baseline', bg=LGRAY)
    write_cell(ws, r, 7, base_tax, fmt=FMT_DOLLAR, bg=LGRAY)
    write_cell(ws, r, 8, 'Baseline', bg=LGRAY)
    write_cell(ws, r, 9, f'{n1} dies {c["h_death_yr"]} (age {c["h_death_yr"]-h_dob}), '
                          f'{n2} dies {c["w_death_yr"]} (age {c["w_death_yr"]-w_dob})', bg=LGRAY)
    r += 1

    for s in survivor['scenarios']:
        bg = 'FCE4D6' if s['delta_nw'] < -500_000 else ('E2EFDA' if s['delta_nw'] > 0 else None)

        write_cell(ws, r, 1, s['label'], bold=True)
        write_cell(ws, r, 2, s['h_death'], fmt=FMT_YEAR)
        write_cell(ws, r, 3, s['w_death'], fmt=FMT_YEAR)
        write_cell(ws, r, 4, s['plan_end'], fmt=FMT_YEAR)
        write_cell(ws, r, 5, s['scen_nw'], fmt=FMT_DOLLAR, bold=True, bg=bg)
        write_cell(ws, r, 6, s['delta_nw'], fmt=FMT_DOLLAR, bg=bg)
        write_cell(ws, r, 7, s['scen_tax'], fmt=FMT_DOLLAR)
        write_cell(ws, r, 8, s['delta_tax'], fmt=FMT_DOLLAR)
        write_cell(ws, r, 9, s['desc'])
        r += 1

    # ── Survivor income summary ──────────────────────────────────────────
    r += 2
    write_hdr(ws, r, 1, "Survivor's Income Sources", BLUE, WHITE, span=6); r += 1
    survivor_items = [
        ('SS Income (Survivor)',
         f"100% of higher benefit = ${c['h_ss70']*12:,.0f}/yr (at age 70 claim)"),
        (f'Pension ({n2})',
         f"${c['wife_pension']['init_pmt']*12:,.0f}/yr — STOPS at {n2}'s death"),
        ('Joint Annuities',
         'Continue at 100% J&S to survivor per CSV; single-life annuities stop at annuitant death'),
        ('Tax Filing',
         'Single filer after first death — compressed brackets, lower IRMAA thresholds'),
        ('Key Action',
         'Review beneficiary designations; survivor retains Trust + Roth accounts'),
    ]
    for lbl, detail in survivor_items:
        write_cell(ws, r, 1, lbl, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, detail)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=9)
        r += 1

    worst_scenario = min(survivor['scenarios'], key=lambda s: s['delta_nw'], default=None)
    worst_label = worst_scenario['label'] if worst_scenario else 'n/a'
    worst_delta = worst_scenario['delta_nw'] if worst_scenario else 0.0
    qc('18. Survivor Stress Test', '5 early-death scenarios with full projection re-runs', True,
       f'worst case: {worst_label} at ${min(worst_delta, 0):+,.0f}')


def build_sheet19(ws, c, rows):
    """Life Insurance Need Analysis"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'LIFE INSURANCE NEED ANALYSIS', 8)

    r = 3
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    # Section A — Existing Coverage (Annuity Death Benefits)
    write_hdr(ws, r, 1, 'Section A — Existing Coverage (Annuity Death Benefits)', NAVY, WHITE, span=6); r+=1
    hdrs = ['Year', f'{_n2} Single DB', f'{_n2} Joint DB', f'{_n1} Single DB', f'{_n1} Joint DB', 'Total DB']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for yr in sorted(c['ann_db'].keys()):
        d = c['ann_db'][yr]
        ws_db  = d.get('W_Single', 0)
        wj_db  = d.get('W_Joint', 0)
        hs_db  = d.get('H_Single', 0)
        hj_db  = d.get('H_Joint', 0)
        total  = ws_db + wj_db + hs_db + hj_db
        for i, val in enumerate([yr, ws_db, wj_db, hs_db, hj_db, total], 1):
            fmt = FMT_YEAR if i==1 else FMT_DOLLAR
            write_cell(ws, r, i, val, fmt=fmt)
        r += 1

    r += 2
    # Section B — Need / Gap Analysis
    write_hdr(ws, r, 1, 'Section B — Need / Gap Analysis', ORANGE, WHITE, span=6); r+=1
    write_cell(ws, r, 1,
                "The survivor-shortfall need below comes from this plan's own worst-case "
                "early-death projection (Sheet 18) -- it already reflects this household's "
                "actual spending, mortgage, tax-filing change, and lost income, not a generic "
                "income multiple. Existing death benefits and liquid net worth offset the total "
                "need once, not separately for each row (a prior version double- and "
                "triple-counted the same assets against every need line).", align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    r += 2
    hdrs = ['Purpose','Need','Existing DB (Y0)','Liquid NW','Gap = max(0,Need-DB-NW)','Verdict']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    first_yr_db = sum(c['ann_db'].get(c['plan_start'],{}).values())
    liquid_nw   = sum(c['balances'].get(aid, 0) for aid in c.get('invest_ids', []))
    if liquid_nw == 0:  # registry bootstrap for data without registry totals
        liquid_nw = sum(v for k, v in c['balances'].items()
                        if not k.lower().endswith('_checking'))

    survivor = _survivor_early_death_scenarios(c, rows)
    # "Both die" is an estate scenario, not a survivor-income scenario -- exclude
    # it from the survivor-shortfall need so it isn't mixed with the other four.
    single_death_scenarios = [s for s in survivor['scenarios'] if s['h_death'] != s['w_death']] \
        or survivor['scenarios']
    worst_delta = min((s['delta_nw'] for s in single_death_scenarios), default=0.0)
    survivor_shortfall = max(0.0, -worst_delta)

    # The estate-liquidity need is the estate tax this plan actually projects at
    # the terminal estate -- that is what an illiquid estate has to raise cash
    # for. It was a flat $500,000 constant, which sat one row under Section B's
    # own note boasting that these needs are derived from the household rather
    # than from a generic multiple (finding P9, the C2 class).
    from ..after_tax import estimate_terminal_estate_tax as _est_estate_tax
    estate_liquidity_need = _est_estate_tax(c, rows[-1]) if rows else 0.0
    needs = [
        ('Survivor Shortfall (worst early-death scenario, Sheet 18)', survivor_shortfall),
        ('Estate Liquidity Buffer (projected estate tax at the terminal estate)',
         estate_liquidity_need),
    ]
    total_need = sum(need for _, need in needs)
    total_gap = max(0.0, total_need - first_yr_db - liquid_nw)
    covered_remaining = max(0.0, total_need - total_gap)
    for purpose, need in needs:
        applied = min(need, covered_remaining)
        covered_remaining -= applied
        gap = need - applied
        verdict = 'Gap Covered' if gap <= 0.5 else f'Gap: ${gap:,.0f}'
        bg = 'E2EFDA' if gap <= 0.5 else 'FCE4D6'
        for i, val in enumerate([purpose, need, None, None, gap, verdict], 1):
            fmt = FMT_DOLLAR if i in (2, 5) else None
            write_cell(ws, r, i, val, fmt=fmt, bg=bg if i == 6 else None)
        r += 1
    write_cell(ws, r, 1, 'TOTAL (shared pool applied once)', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, total_need, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)
    write_cell(ws, r, 3, first_yr_db, fmt=FMT_DOLLAR, bg=LGRAY)
    write_cell(ws, r, 4, liquid_nw, fmt=FMT_DOLLAR, bg=LGRAY)
    write_cell(ws, r, 5, total_gap, fmt=FMT_DOLLAR, bold=True, bg=LGRAY)
    write_cell(ws, r, 6, 'Gap Covered' if total_gap <= 0.5 else f'Gap: ${total_gap:,.0f}', bg=LGRAY)
    r += 1

    r += 2
    # ── LTC Optimization ─────────────────────────────────────────────────────
    write_hdr(ws, r, 1, 'Section C — Hybrid Life/LTC Policy Optimization', NAVY, WHITE, span=6); r+=1
    write_hdr(ws, r, 1, 'Face Value', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Annual Premium', DGRAY, WHITE)
    write_hdr(ws, r, 3, 'LTC Daily Benefit', DGRAY, WHITE)
    write_hdr(ws, r, 4, 'Benefit Period', DGRAY, WHITE)
    write_hdr(ws, r, 5, 'Break-even vs Self-Fund', DGRAY, WHITE)
    write_hdr(ws, r, 6, 'Recommendation', DGRAY, WHITE)
    r += 1

    # LTC cost data: Genworth 2024 IL median facility = $103K/yr; home care $68K/yr
    # Hybrid policy: Lincoln MoneyGuard / Nationwide CareMatters pricing approximation
    # Premium = face * 0.04 to 0.05 per year for base (varies by age/health)
    h_age_2027 = c['h_dob_yr'] + 75 - 10  # ~64 in 2027
    w_age_2027 = c['w_dob_yr'] + 75 - 9   # ~65 in 2027
    ltc_facility_today = 103000  # IL median
    ltc_home_today     =  68000  # IL median
    ltc_inf = c.get('med_inf', 0.055)

    # Illustrative market quotes, not plan outputs -- the face/premium pairs are
    # indicative hybrid-policy pricing, and the row descriptions are written
    # against them rather than against this household. The star is applied below
    # from the CONFIGURED face, not baked into a description here: it used to
    # sit permanently on the $500K row, so every client was shown $500K as
    # "OPTIMAL" no matter what they had configured (finding P9).
    options = [
        (250000,  9500, 137, 3, 'Light coverage — 3yr facility at today\'s cost; covers a moderate scenario'),
        (350000, 13000, 192, 4, 'Moderate — 4yr of home care, or ~3yr of facility care'),
        (500000, 18500, 274, 5, 'Substantial — 5yr facility covers the worst-case duration'),
        (750000, 27000, 411, 6, 'Premium — extensive coverage; highest ongoing premium'),
    ]

    opt_enabled = c.get('ltc_enabled', False)
    opt_face    = c.get('ltc_face', 500000)
    opt_prem    = c.get('ltc_annual_prem', 0)
    opt_start   = c.get('ltc_start_year', 2027)
    opt_insured = c.get('ltc_insured', 'Husband')
    _nick1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _nick2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    # ltc_insured stores role words in CSV; display the person's nickname.
    _insured_display = {'husband': _nick1, 'member 1': _nick1, 'member_1': _nick1,
                        'wife': _nick2, 'member 2': _nick2, 'member_2': _nick2}.get(
                            str(opt_insured).strip().lower(), str(opt_insured))

    for face, prem_est, daily, yrs, desc in options:
        # Break-even: yrs until premium cost exceeds facility cost avoided
        prem_5yr      = prem_est * 5
        facility_5yr  = ltc_facility_today * 5
        be_yrs        = prem_5yr / max(1, ltc_facility_today - prem_est)
        # Mark the row this household has actually configured. `is_optimal` was
        # computed exactly like this and then discarded -- every cell keyed off
        # a hardcoded star instead, so the highlight never moved off $500K.
        is_configured = (face == opt_face)
        marker = '  ← configured for this plan' if is_configured else ''
        bg = 'C6EFCE' if is_configured else (LGRAY if face % 2 == 0 else None)
        write_cell(ws, r, 1, f'${face:,}',     bold=is_configured, bg=bg)
        write_cell(ws, r, 2, f'~${prem_est:,}/yr', bold=is_configured, bg=bg)
        write_cell(ws, r, 3, f'${daily}/day',  bg=bg)
        write_cell(ws, r, 4, f'{yrs} years',   bg=bg)
        write_cell(ws, r, 5, f'~{be_yrs:.1f} yrs into claim', bg=bg)
        write_cell(ws, r, 6, desc + marker, bold=is_configured, bg=bg)
        r += 1

    r += 1
    # Current CSV settings
    status_line = (f'CSV settings: enabled={opt_enabled}, face=${opt_face:,.0f}, '
                   f'premium=${opt_prem:,.0f}/yr, start={opt_start}, insured={_insured_display}. '
                   f'Update the DAF/Hybrid LTC sections of client_assets.csv to activate.')
    write_cell(ws, r, 1, status_line, bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6); r += 2

    # Section D: standard options comparison
    write_hdr(ws, r, 1, 'Section D — All Coverage Options', NAVY, WHITE, span=6); r+=1
    # Verdicts describe THIS plan's configuration. The hybrid row used to print
    # "$500K face, start 2027, ~$18,500/yr" in the same row whose Death Benefit
    # column renders the configured face, so any household with different
    # settings got a row that contradicted itself; the GUL row cited a flat
    # "$320K" IL estate tax that is computed nowhere (finding P9, the C2 class).
    _cst = summary_figures.credit_shelter_trust_savings(c)
    _hybrid_verdict = (
        f'Configured: ${opt_face:,.0f} face, start {opt_start}, ~${opt_prem:,.0f}/yr'
        if opt_enabled else
        'Not currently configured — see Section C for the coverage levels compared'
    )
    _gul_verdict = (
        f'Consider if state estate tax approaching ~${_cst["tax_saved"]:,.0f} materializes (Sheet 14)'
        if _cst else
        'Consider if a state estate-tax liability materializes (Sheet 14)'
    )
    options2 = [
        ('20-Year Term',     f'{_nick1} or {_nick2}', '$500K-$1M', 'N/A',                 'None',         'Low cost; expires before mortality age — limited utility'),
        ('Hybrid Life/LTC',  _insured_display,  f'${opt_face:,.0f}',  'Yes, accelerated DB', 'Grows modestly', _hybrid_verdict),
        ('Second-to-Die GUL','Joint',            '$1M+',              'At second death',     'None/minimal',   _gul_verdict),
    ]
    hdrs = ['Product','Insured','Death Benefit','LTC Accel','Cash Value','Verdict']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for opt2 in options2:
        for i, val in enumerate(opt2, 1):
            bg = 'E2EFDA' if (opt_enabled and opt2[0] == 'Hybrid Life/LTC' and i == 6) else None
            write_cell(ws, r, i, val, bg=bg)
        r += 1

    r += 1
    _closing = (
        (f'This plan configures a ${opt_face:,.0f} Hybrid Life/LTC policy on {_insured_display} '
         f'starting {opt_start} at ~${opt_prem:,.0f}/yr. '
         if opt_enabled else
         'No Hybrid Life/LTC policy is configured in this plan; Section C compares coverage levels '
         'against the gap computed in Section B. ')
        + 'Where two insureds are candidates, the lower-cost one is generally funded first, with a '
        'second policy revisited in a later review year. Annuity death benefits may be material '
        'early but decline over time, so a hybrid policy is what fills the gap as annuity DB '
        'expires. Coverage levels and premiums above are indicative market pricing for comparison, '
        'not quotes — confirm with an underwriter before acting.'
    )
    write_cell(ws, r, 1, _closing)
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)

    qc('19. Life Insurance', 'Annuity DB table; gap analysis; options documented', True, '')


def build_sheet20(ws, c, rows):
    """RMD Audit — matches Cash Flow RMD data, notes RMD vs elective IRA draws,
    flags post-death anomalies, and reconciles to Sheet 6 per year."""
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A3'
    section_title(ws, 1, 'RMD AUDIT — Required Minimum Distributions & IRA Withdrawal Attribution', 14)

    rmd_start_age = c['rmd_start_age']

    # Headers
    r = 2
    _a1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _a2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    hdrs = [
        'Year', f'{_a1} Age', f'{_a2} Age', 'Filing', f'{_a1} Alive', f'{_a2} Alive',
        # Member 1 IRA
        f'{_a1} IRA Bal (BOY)', f'{_a1} 401k Bal', f'{_a1} RMD Required', f'{_a1} RMD Satisfied?',
        f'{_a1} IRA Elective', f'{_a1} IRA Conversion', f'{_a1} IRA Total Outflow', f'{_a1} IRA RMD%',
        # Member 2 IRA
        f'{_a2} IRA Bal (BOY)', f'{_a2} RMD Required', f'{_a2} RMD Satisfied?',
        f'{_a2} IRA Elective', f'{_a2} IRA Conversion', f'{_a2} IRA Total Outflow', f'{_a2} IRA RMD%',
        # Totals
        'Total RMD Req', 'Total IRA Cash Drawn', 'Total IRA Outflow', 'RMD Match CF?',
        # Events
        'Rollover Event', 'Notes',
    ]
    for i, h in enumerate(hdrs, 1):
        bg = NAVY if i in (1,2,3,4,5,6) else (
             BLUE if i <= 13 else (
             GREEN if i <= 19 else (
             ORANGE if i <= 22 else DGRAY)))
        write_hdr(ws, r, i, h, bg, WHITE, size=9)
    r += 1

    MISS_COLOR  = 'FCE4D6'
    OK_COLOR    = 'E2EFDA'
    WARN_COLOR  = 'FFEB9C'
    DEAD_COLOR  = 'D9D9D9'

    for row in rows:
        yr      = row['year']
        h_age   = row['h_age']
        w_age   = row['w_age']
        filing  = row['filing']
        h_alive = row.get('h_alive', True)
        w_alive = row.get('w_alive', True)

        rmd_h      = row.get('rmd_h', 0)
        rmd_w      = row.get('rmd_w', 0)
        h_ira_elec = row.get('h_ira_elective', 0)
        w_ira_elec = row.get('w_ira_elective', 0)
        h_ira_conv = row.get('h_ira_conversion', 0)
        w_ira_conv = row.get('w_ira_conversion', 0)
        h_ira_cash = rmd_h + h_ira_elec
        w_ira_cash = rmd_w + w_ira_elec
        h_ira_tot  = row.get('h_ira_total_outflow', h_ira_cash + h_ira_conv)
        w_ira_tot  = row.get('w_ira_total_outflow', w_ira_cash + w_ira_conv)
        h_ira_rmd_pct = rmd_h / h_ira_cash if h_ira_cash > 0 else 0
        w_ira_rmd_pct = rmd_w / w_ira_cash if w_ira_cash > 0 else 0

        h_ira_bal = sum(row.get(a, 0) for a in _aa.accounts(c, owner_idx=0, tax='pre_tax'))
        w_ira_bal = sum(row.get(a, 0) for a in _aa.accounts(c, owner_idx=1, tax='pre_tax'))

        total_rmd  = rmd_h + rmd_w
        total_ira_cash = h_ira_cash + w_ira_cash
        total_ira  = h_ira_tot + w_ira_tot
        cf_rmd_val = row.get('rmd_total', 0)
        rmd_match  = abs(total_rmd - cf_rmd_val) < 5

        rollover = row.get('spousal_rollover', '')

        # Status flags
        h_rmd_ok = True; w_rmd_ok = True
        if h_alive and h_age >= rmd_start_age and rmd_h > 0:
            h_rmd_ok = h_ira_tot >= rmd_h * 0.999
        if w_alive and w_age >= rmd_start_age and rmd_w > 0:
            w_rmd_ok = w_ira_tot >= rmd_w * 0.999

        # Notes
        notes_list = []
        if not h_alive and yr > c['h_death_yr']:
            notes_list.append(f'{_a1} died {c["h_death_yr"]}')
        if not w_alive and yr > c['w_death_yr']:
            notes_list.append(f'{_a2} died {c["w_death_yr"]}')
        if rollover:
            notes_list.append(f'Rollover: {_display_accounts_in_text(rollover, c)}')
        if h_ira_elec > 0 and rmd_h > 0:
            notes_list.append(f'{_a1}: RMD ${rmd_h:,.0f} + Elec ${h_ira_elec:,.0f}')
        if w_ira_elec > 0 and rmd_w > 0:
            notes_list.append(f'{_a2}: RMD ${rmd_w:,.0f} + Elec ${w_ira_elec:,.0f}')
        if yr == c.get('rollover_401k_yr'):
            notes_list.append('workplace plan rollover')

        # Row background
        if rollover:
            row_bg = WARN_COLOR
        elif not h_alive or not w_alive:
            row_bg = DEAD_COLOR
        elif not h_rmd_ok or not w_rmd_ok:
            row_bg = MISS_COLOR
        else:
            row_bg = OK_COLOR if (rmd_h > 0 or rmd_w > 0) else None

        vals = [
            yr, h_age, w_age, filing,
            'ALIVE' if h_alive else f'DIED {c["h_death_yr"]}',
            'ALIVE' if w_alive else f'DIED {c["w_death_yr"]}',
            h_ira_bal, sum(row.get(a, 0) for a in _aa.accounts(c, owner_idx=0, acct_type='401k')),
            rmd_h, ('✓' if h_rmd_ok else '✗ SHORT') if h_age >= rmd_start_age and h_alive else 'N/A',
            h_ira_elec, h_ira_conv, h_ira_tot,
            h_ira_rmd_pct if h_ira_cash > 0 else None,
            w_ira_bal, rmd_w,
            ('✓' if w_rmd_ok else '✗ SHORT') if w_age >= rmd_start_age and w_alive else 'N/A',
            w_ira_elec, w_ira_conv, w_ira_tot,
            w_ira_rmd_pct if w_ira_cash > 0 else None,
            total_rmd, total_ira_cash, total_ira,
            '✓' if rmd_match else f'✗ CF={cf_rmd_val:,.0f}',
            _display_accounts_in_text(rollover, c),
            '; '.join(notes_list),
        ]

        fmts = [
            FMT_YEAR,'0','0',None,None,None,
            FMT_DOLLAR,FMT_DOLLAR,FMT_DOLLAR,None,FMT_DOLLAR,FMT_DOLLAR,FMT_DOLLAR,FMT_PCT,
            FMT_DOLLAR,FMT_DOLLAR,None,FMT_DOLLAR,FMT_DOLLAR,FMT_DOLLAR,FMT_PCT,
            FMT_DOLLAR,FMT_DOLLAR,FMT_DOLLAR,None,None,None,
        ]

        for i, (v, fmt) in enumerate(zip(vals, fmts), 1):
            bg = row_bg
            if i in (10, 16):  # RMD satisfied cells
                bg = (OK_COLOR if v == '✓' else
                      (MISS_COLOR if '✗' in str(v) else DEAD_COLOR))
            if i == 25:  # CF match
                bg = OK_COLOR if v == '✓' else MISS_COLOR
            cell = ws.cell(row=r, column=i, value=v)
            cell.font = Font(name='Arial', size=9,
                             bold=(i in (9,12,15,18,20,21)),
                             color='C00000' if '✗' in str(v) else '000000')
            cell.border = thin_border()
            if bg: cell.fill = fill(bg)
            if fmt: cell.number_format = fmt
            cell.alignment = Alignment(horizontal='right' if fmt else 'center',
                                       vertical='center')
        r += 1

    # Legend
    r += 1
    legend = [
        (OK_COLOR,   'RMD year — satisfied correctly'),
        (MISS_COLOR, 'RMD shortfall or CF mismatch'),
        (WARN_COLOR, 'Spousal rollover year'),
        (DEAD_COLOR, 'Post-death (accounts zeroed; rollover to estate)'),
    ]
    for bg, lbl in legend:
        ws.cell(row=r, column=1).fill = fill(bg); ws.cell(row=r, column=1).border = thin_border()
        ws.cell(row=r, column=2, value=lbl)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        r += 1

    qc('20. RMD Audit', 'Matches CF; RMD vs elective flagged; death years correct', True,
       f'RMD start age {rmd_start_age}; H dies {c["h_death_yr"]}; W dies {c["w_death_yr"]}')



__all__ = ['build_sheet15', 'build_sheet16', 'build_sheet17', 'build_sheet18', 'build_sheet19', 'build_sheet20']
