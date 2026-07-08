from .workbook_common import *
def validate_all(rows, c):
    """Run registry-aware validation. Returns list of (year, severity, name, msg)."""
    from ..data_io import validate_projection  # consolidated from validation_engine
    failures = validate_projection(rows, c)
    # validation_engine already returns (year, severity, code, message)
    return failures


def build_sheet21(ws, checks, rows=None, c=None):
    # Run validation framework if rows/c provided
    validation_failures = []
    if rows and c:
        validation_failures = validate_all(rows, c)
        if not validation_failures:
            checks.append(('Validation', 'All invariants passed', 'PASS', f'{len(rows)} rows checked'))
        else:
            for vf in validation_failures[:10]:
                # validation_engine returns (year, severity, code, message).
                # Older invariant code returned (idx, year, severity, code, message).
                if len(vf) == 4:
                    yr, severity, code, msg = vf
                else:
                    _idx, yr, severity, code, msg = vf
                checks.append(('Validation', f'{code}', severity, f'Year {yr}: {msg}'))

    """Quality Control Summary"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'QUALITY CONTROL SUMMARY', 5)

    r = 3
    write_hdr(ws, r, 1, 'Sheet', NAVY, WHITE)
    write_hdr(ws, r, 2, 'Check', NAVY, WHITE, span=2)
    write_hdr(ws, r, 4, 'Status', NAVY, WHITE)
    write_hdr(ws, r, 5, 'Detail', NAVY, WHITE)
    r += 1

    pass_count = 0; fail_count = 0
    for sheet, check, status, detail in checks:
        bg = 'E2EFDA' if status=='PASS' else 'FCE4D6'
        write_cell(ws, r, 1, sheet, bg=LGRAY)
        write_cell(ws, r, 2, check); ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=3)
        write_cell(ws, r, 4, status, bold=True, bg=bg, align='center')
        write_cell(ws, r, 5, detail)
        if status=='PASS': pass_count+=1
        else:              fail_count+=1
        r += 1

    total = pass_count + fail_count
    r += 1
    write_cell(ws, r, 1, f'TOTAL: {pass_count}/{total} PASS · {fail_count} FAIL',
               bold=True, bg=NAVY, fg=WHITE)
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=5)

    # Modeling Adjustments
    r += 2
    write_hdr(ws, r, 1, 'MODELING ADJUSTMENTS & NORMALIZATIONS', NAVY, WHITE, span=5); r+=1
    adjustments = [
        ('Annuity Net Worth Valuation',
         'Each annuity is valued at the PV of future cash income (guaranteed payment + '
         'cash dividend) through the relevant death. Base accumulation is NOT an estate asset.'),
        ('Annuity Dividend Model',
         'Base compounds at div_rate pre-distribution; at div_rate × additional_income_pct '
         'post-distribution. Guaranteed payment grows at add_pct × div_rate.'),
        ('CASH Placeholder Positions',
         'Every account includes a CASH position at $1/share. Drain logic: '
         'Account_Balance < max(500, Calculated_RMD).'),
        ('Mortgage Normalization',
         'Mortgage balance computed from configured starting balance; $0 after last_payment_year.'),
        ('RMD Timing',
         'RMDs computed at year-start balance; satisfied before year-end; '
         'SECURE 2.0 age-75 for those born 1960+.'),
        ('Roth Conversion Forced Actions',
         'Forced Roth conversion amounts are read from CSV Forced Actions.'),
        ('NIIT / State Estate Tax',
         'Modeled per Plan Settings toggles (both TRUE). IL estate tax: ~$4M exemption, '
         'graduated 0.8%–16% rates, no portability.'),
        ('Live Pricing',
         'ETF prices fetched at build time via FMP / Alpha Vantage / Stooq. CASH = $1.00/share.'),
        ('SS Survivor Benefit',
         '100% of higher benefit (at deceased\'s claim age per CSV policy rows).'),
        ('Spousal Rollover',
         'Decedent balances roll to survivor in year of death; RMDs recalculated under '
         'survivor\'s age starting the following year.'),
    ]
    for label, detail in adjustments:
        write_cell(ws, r, 1, label, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, detail)
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=5)
        r += 1

    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 80


def build_sheet22(ws):
    """Glossary"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'GLOSSARY OF TERMS', 4)

    terms = [
        ('AGI', 'Adjusted Gross Income — gross income minus above-the-line deductions'),
        ('Basis', 'The original cost of an asset used to determine capital gain or loss'),
        ('Credit-Shelter Trust', 'A trust designed to use a decedent\'s estate tax exemption'),
        ('DAF', 'Donor Advised Fund — charitable giving vehicle allowing immediate deduction with delayed grant-making'),
        ('ILIT', 'Irrevocable Life Insurance Trust — removes life insurance proceeds from the taxable estate'),
        ('IRMAA', 'Income-Related Monthly Adjustment Amount — Medicare premium surcharge for high earners'),
        ('J&S (Joint-and-Survivor)', 'Annuity feature paying a reduced benefit to a surviving spouse'),
        ('LTCG', 'Long-Term Capital Gain — gain on assets held more than one year, taxed at preferential rates'),
        ('MAGI', 'Modified Adjusted Gross Income — AGI with certain deductions added back'),
        ('Monte Carlo', 'Statistical simulation using random scenarios to model range of outcomes'),
        ('NIIT', 'Net Investment Income Tax — 3.8% surtax on investment income above MAGI thresholds'),
        ('Percentile Band', 'The value at or below which a given percentage of simulation results fall'),
        ('QCD', 'Qualified Charitable Distribution — IRA distribution sent directly to charity, excluded from AGI'),
        ('QTIP', 'Qualified Terminable Interest Property trust — provides income to surviving spouse'),
        ('RMD', 'Required Minimum Distribution — mandatory annual withdrawals from tax-deferred accounts starting at age 75'),
        ('Roth Conversion', 'Transfer from a pre-tax IRA to a Roth IRA, triggering tax in the conversion year'),
        ('SALT Cap', 'State and Local Tax deduction cap — schedule sourced from tax_data.py'),
        ('§121 Exclusion', 'Up to $500,000 (MFJ) of home sale gain excluded from federal income tax'),
        ('Sequence-of-Returns Risk', 'Risk that poor investment returns early in retirement permanently impair the portfolio'),
        ('Spousal Rollover', 'Surviving spouse inherits deceased spouse\'s IRA as their own, deferring RMDs to their own age'),
        ('Standard Deduction', 'Tax-reference-year MFJ base plus over-65 add-ons; inflated annually'),
        ('Step-Up in Basis', 'Reset of asset cost basis to fair market value at death for non-retirement assets'),
    ]

    r = 2
    write_hdr(ws, r, 1, 'Term', NAVY, WHITE)
    write_hdr(ws, r, 2, 'Definition', NAVY, WHITE, span=3)
    r += 1
    for term, defn in sorted(terms):
        write_cell(ws, r, 1, term, bold=True, bg=LGRAY)
        write_cell(ws, r, 2, defn)
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=4)
        r += 1

    ws.column_dimensions['A'].width = 28
    ws.column_dimensions['B'].width = 80

    qc('22. Glossary', 'All key terms defined', True, f'{len(terms)} terms')


def build_sheet23(ws, c):
    """Methodology & Re-Run"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'METHODOLOGY & RE-RUN PROCESS', 6)

    r = 3
    sections = [
        ('Projection Engine Logic', [
            'Year-by-year from plan_start to plan_end (later of husband/wife death year).',
            'Asset balances grow at portfolio_nominal_return; withdrawals reduce balances before growth.',
            'Income sources: earned income, Social Security (age 70), annuities, pension, Note Receivable, RMDs.',
            'Withdrawal cascade: RMDs → HSA window → tax-sensitive pre-tax → taxable/trust → final pre-tax/HSA → Roth last → Home Equity.',
            'Surplus reinvested into the first registry taxable account.',
        ]),
        ('Tax Computation Order', [
            '1. Gross income (earned + SS + annuities + RMDs + Roth conversion)',
            '2. AGI (minus SE deductions, half-SE-tax, SEHI)',
            '3. MAGI (add back for NIIT/SALT)',
            '4. SALT cap (phased down formula)',
            '5. Charitable deduction (AGI floor per OBBBA)',
            '6. Greater of standard or itemized deduction',
            '7. Federal tax, State tax, NIIT, Payroll tax, IRMAA',
            '8. Taxable-withdrawal LTCG/NIIT uses a bounded fixed-point solve before moving to pre-tax/Roth buckets.',
        ]),
        ('Annuity Dividend Model', [
            'Base compounds at div_rate pre-distribution year.',
            'From first_payment year: base grows at add_pct × div_rate (reinvested share).',
            'Cash income = guaranteed_payment (grows at add_pct × div_rate) + base × div_rate × cash_pct.',
            'Net worth value = PV of future cash income at portfolio discount rate.',
            'Annuity death benefits per CSV Annuity Death Benefits matrix; decline to $0 over time.',
        ]),
        ('Monte Carlo Setup', [
            'Regime/fat-tail simulations use configured arithmetic return and volatility; non-static glide paths reduce both expected return and volatility over time.',
            'Success = no unfunded annual spending gap and liquid retirement assets remain above the configured floor in every projected year.',
            'Sheet 15 reports both arithmetic and geometric sampled returns plus P5/P25/P50/P75/P95 bands.',
        ]),
        ('Re-Run Instructions', [
            '1. Edit the split client_*.csv files (UTF-8 encoding required — no CP1252 special chars).',
            '2. Ensure Python 3.9+, openpyxl, numpy, scipy, requests are installed.',
            '3. Run: python build_workbook.py',
            '4. Output file: retirement_plan.xlsx in same directory.',
            '5. Review Quality Control sheet (Sheet 21) — all checks should be PASS.',
            '6. Update ETF prices by re-running the script (live prices fetched at build time).',
            '7. Annual review cadence: rebuild each January; update DOB-based calculations auto-update.',
        ]),
        ('Key Editable Variables in CSV', [
            'Economic Assumptions: inflation, returns, bracket inflator',
            'Household: DOBs, mortality ages (extend or shorten plan horizon)',
            'Cashflow: spending, earned income, mortgage, lump events',
            'Optional Functions: toggle sheets ON/OFF as needed',
            'Forced Actions: hard-code any prior-year Roth conversions',
        ]),
    ]

    for section_hdr, items in sections:
        write_hdr(ws, r, 1, section_hdr, NAVY, WHITE, span=4); r+=1
        for item in items:
            write_cell(ws, r, 1, '• '+item)
            ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=4)
            r += 1
        r += 1

    ws.column_dimensions['A'].width = 100

    # ── Advisor Governance and Model Risk ─────────────────────────────────────
    r += 1
    write_hdr(ws, r, 1, 'Illustration vs Recommendation', ORANGE, WHITE, span=4); r += 1
    readiness = c.get('advisor_readiness', {}) or {}
    write_cell(ws, r, 1, readiness.get('illustration_notice', 'Outputs are illustrations until suitability, tax review, liquidity, risk tolerance, and signed assumptions are complete.'))
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4); r += 1
    write_cell(ws, r, 1, 'Advisor-ready status')
    write_cell(ws, r, 2, readiness.get('status', 'ILLUSTRATION_ONLY'))
    r += 1

    # ── Tax-Year Constants Provenance (9.6) ───────────────────────────────────
    r += 1
    write_hdr(ws, r, 1, 'Tax-Year Constants Provenance', NAVY, WHITE, span=4); r += 1
    write_hdr(ws, r, 1, 'Constant Group', BLUE, WHITE)
    write_hdr(ws, r, 2, 'Tax Year', BLUE, WHITE)
    write_hdr(ws, r, 3, 'Source', BLUE, WHITE)
    write_hdr(ws, r, 4, 'Last reviewed / status', BLUE, WHITE)
    r += 1
    provenance = c.get('tax_provenance', {})
    for grp, meta in sorted(provenance.items()):
        write_cell(ws, r, 1, grp.replace('_', ' ').title())
        write_cell(ws, r, 2, meta.get('tax_year', ''))
        write_cell(ws, r, 3, meta.get('source', ''))
        write_cell(ws, r, 4, meta.get('last_reviewed', 'See tax-law dashboard'))
        r += 1

    warnings = c.get('tax_table_currency_warnings', []) or []
    if warnings:
        r += 1
        write_hdr(ws, r, 1, 'Tax Table Currency Warnings', ORANGE, WHITE, span=4); r += 1
        for warning in warnings:
            write_cell(ws, r, 1, '• ' + str(warning))
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
            r += 1

    r += 1
    write_cell(ws, r, 1, f'Filing status: {c.get("filing_status","MFJ")}  |  '
               f'Survivor filing: {c.get("survivor_filing","Single")}  |  '
               f'Roth policy: {c.get("roth_policy","fill_to_bracket")}  |  '
               f'Cascade: {" → ".join(c.get("cascade_order_list", []))}')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)

    qc('23. Methodology', 'Re-run steps and methodology documented', True, '')


def build_sheet24(ws, c, rows):
    """Asset-Location Optimizer — quantifies tax savings from holding the right
    asset class in the right account (equities in Roth, bonds in IRA, etc.)."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'ASSET-LOCATION OPTIMIZER', 7)

    r = 3
    write_cell(ws, r, 1, 'Tax-efficient asset placement: same overall allocation, but assets '
               'held in their most tax-advantaged account. Equities (growth + qualified '
               'dividends/LTCG) favor Roth and taxable; bonds/REITs (ordinary income) favor IRA.')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7); r += 2

    # ── Current balances by account ──────────────────────────────────────────
    bal = c['balances']
    ira   = _aa.sum_bal(c, bal, tax='pre_tax')
    roth  = _aa.sum_bal(c, bal, tax='roth')
    trust = _aa.sum_bal(c, bal, tax='taxable')
    total_inv = ira + roth + trust
    if total_inv <= 0:
        total_inv = 1

    eq_pct  = c.get('alloc_equity', 0.85)
    bond_pct = c.get('alloc_commodity', 0.10) + c.get('alloc_cash', 0.05)

    # Asset-class assumptions
    EQ_RET   = ASSET_CLASS_RETURNS.get('equity', 0.08)
    BOND_RET = (c.get('alloc_commodity',0.10)*ASSET_CLASS_RETURNS.get('commodity',0.05) +
                c.get('alloc_cash',0.05)*ASSET_CLASS_RETURNS.get('cash',0.02)) / max(0.01, bond_pct)
    yrs = max(1, c['plan_end'] - c['plan_start'])
    # Ordinary rate (approx marginal) vs LTCG rate
    ord_rate  = 0.24
    ltcg_rate = 0.15

    write_hdr(ws, r, 1, 'Current Account Balances', NAVY, WHITE, span=3); r += 1
    for lbl, val in [('Tax-Deferred (IRA/401k)', ira), ('Tax-Free (Roth)', roth),
                     ('Taxable (Trust)', trust), ('Total Investable', ira+roth+trust)]:
        write_cell(ws, r, 1, lbl, bold=(lbl=='Total Investable'))
        write_cell(ws, r, 2, val, fmt=FMT_DOLLAR, bold=(lbl=='Total Investable'))
        write_cell(ws, r, 3, f'{val/total_inv*100:.0f}%', align='right')
        r += 1
    r += 1

    # ── Tax drag comparison ──────────────────────────────────────────────────
    # Naive: each account holds the blended 85/15 mix.
    # Bonds in taxable drag at ordinary rate each year; bonds in IRA defer.
    # Equities in Roth grow fully tax-free; in taxable, LTCG on growth.
    write_hdr(ws, r, 1, 'Annual Tax Drag by Placement', NAVY, WHITE, span=4); r += 1
    write_cell(ws, r, 1, 'Scenario', bold=True, bg=NAVY, fg=WHITE)
    write_cell(ws, r, 2, 'Bond Tax Drag/yr', bold=True, bg=NAVY, fg=WHITE)
    write_cell(ws, r, 3, 'Equity Tax Drag/yr', bold=True, bg=NAVY, fg=WHITE)
    write_cell(ws, r, 4, 'Total/yr', bold=True, bg=NAVY, fg=WHITE); r += 1

    # Naive placement: bonds spread across all accounts (taxable portion drags)
    bonds_total = total_inv * bond_pct
    eq_total    = total_inv * eq_pct
    # Fraction of each asset class sitting in taxable under naive (proportional)
    taxable_frac = trust / total_inv
    naive_bond_drag = bonds_total * taxable_frac * BOND_RET * ord_rate
    naive_eq_drag   = eq_total * taxable_frac * EQ_RET * 0.30 * ltcg_rate  # 30% of growth realized/yr
    write_cell(ws, r, 1, 'Naive (blended mix in every account)')
    write_cell(ws, r, 2, naive_bond_drag, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 3, naive_eq_drag, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 4, naive_bond_drag+naive_eq_drag, fmt=FMT_DOLLAR, align='right'); r += 1

    # Optimized: bonds first fill IRA (no annual drag), equities fill Roth then taxable
    bonds_in_taxable = max(0, bonds_total - ira)   # only overflow bonds land in taxable
    opt_bond_drag = bonds_in_taxable * BOND_RET * ord_rate
    # Equities: Roth portion tax-free; taxable portion gets LTCG but benefits from step-up at death
    eq_in_taxable = max(0, eq_total - roth - max(0, ira - bonds_total))
    opt_eq_drag = eq_in_taxable * EQ_RET * 0.30 * ltcg_rate
    write_cell(ws, r, 1, 'Optimized (bonds→IRA, equities→Roth/taxable)', bold=True)
    write_cell(ws, r, 2, opt_bond_drag, fmt=FMT_DOLLAR, align='right', bold=True)
    write_cell(ws, r, 3, opt_eq_drag, fmt=FMT_DOLLAR, align='right', bold=True)
    write_cell(ws, r, 4, opt_bond_drag+opt_eq_drag, fmt=FMT_DOLLAR, align='right', bold=True); r += 2

    # ── Lifetime savings ─────────────────────────────────────────────────────
    annual_savings = (naive_bond_drag + naive_eq_drag) - (opt_bond_drag + opt_eq_drag)
    # Compound the annual savings over the plan horizon at the portfolio return
    lifetime_savings = 0.0
    for y in range(yrs):
        lifetime_savings += annual_savings * ((1 + c['ret']) ** (yrs - y))

    write_hdr(ws, r, 1, 'Estimated Savings', GREEN, WHITE, span=3); r += 1
    write_cell(ws, r, 1, 'Annual tax drag reduction', bold=True)
    write_cell(ws, r, 2, annual_savings, fmt=FMT_DOLLAR, bold=True); r += 1
    write_cell(ws, r, 1, f'Compounded over {yrs} years (at {c["ret"]*100:.1f}%)', bold=True)
    write_cell(ws, r, 2, lifetime_savings, fmt=FMT_DOLLAR, bold=True, fg=GREEN); r += 2

    # ── Recommendations ──────────────────────────────────────────────────────
    write_hdr(ws, r, 1, 'Placement Recommendations', NAVY, WHITE, span=5); r += 1
    recs = [
        f'Hold all bond/income assets (${min(bonds_total,ira):,.0f}) inside the IRA — '
        'ordinary-income yield is sheltered from annual tax.',
        f'Hold the highest-growth equities (${min(eq_total,roth):,.0f}) in the Roth — '
        'all future appreciation is permanently tax-free.',
        'Hold remaining equities in the taxable Trust — qualified dividends and LTCG '
        'are taxed at preferential rates, and heirs receive a stepped-up basis at death.',
        'Avoid holding bonds in the taxable Trust — their ordinary-income yield is the '
        'least tax-efficient use of taxable space.',
        'Re-evaluate placement after large Roth conversions, which shift the IRA/Roth balance.',
    ]
    for rec in recs:
        write_cell(ws, r, 1, '• ' + rec)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)
        r += 1
    r += 1
    write_cell(ws, r, 1, 'Note: estimate uses marginal ordinary rate 24%% and LTCG 15%%; '
               'actual savings depend on realized turnover and bracket in each year.', fg='888888')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=7)

    ws.column_dimensions['A'].width = 60
    for col in ['B','C','D','E']:
        ws.column_dimensions[col].width = 18
    qc('24. Asset Location', 'Tax-location savings quantified', True,
       f'${lifetime_savings:,.0f} lifetime')



def _combine_account_maps(*maps):
    out = {}
    for mp in maps:
        for k, v in (mp or {}).items():
            try:
                amt = float(v or 0.0)
            except Exception:
                amt = 0.0
            if abs(amt) > 1e-9:
                out[k] = out.get(k, 0.0) + amt
    return out


def account_reconciliation_rows(c, rows):
    """Return per-account annual roll-forward rows.

    Formula: opening balance + deposits + transfers in - transfers out
    + conversions in - conversions out - withdrawals + growth = ending balance.
    """
    registry = {a.get('id'): a for a in c.get('account_registry', [])}
    recs = []
    max_abs_delta = 0.0
    for row in rows:
        opening_map = row.get('_account_opening', {}) or {}
        deposits_map = row.get('_account_deposits', {}) or {}
        deposit_sources_map = row.get('_account_deposit_sources', {}) or {}
        transfers_in_map = row.get('_account_transfers_in', {}) or {}
        transfers_out_map = row.get('_account_transfers_out', {}) or {}
        conv_in_map = row.get('_account_conversions_in', {}) or {}
        conv_out_map = row.get('_account_conversions_out', {}) or {}
        withdrawals_map = row.get('_account_withdrawals', {}) or {}
        growth_map = row.get('_account_growth', {}) or {}

        for acct in c.get('all_acct_ids', []):
            meta = registry.get(acct, {})
            opening = float(opening_map.get(acct, 0.0) or 0.0)
            deposits = float(deposits_map.get(acct, 0.0) or 0.0)
            transfers_in = float(transfers_in_map.get(acct, 0.0) or 0.0)
            transfers_out = float(transfers_out_map.get(acct, 0.0) or 0.0)
            conv_in = float(conv_in_map.get(acct, 0.0) or 0.0)
            conv_out = float(conv_out_map.get(acct, 0.0) or 0.0)
            withdrawals = float(withdrawals_map.get(acct, 0.0) or 0.0)
            growth = float(growth_map.get(acct, 0.0) or 0.0)
            ending = float(row.get(acct, 0.0) or 0.0)
            deposit_source_entries = deposit_sources_map.get(acct, []) or []
            deposit_sources_text = '; '.join(
                f"{entry.get('source', 'unknown')}: ${float(entry.get('amount', 0.0) or 0.0):,.0f}"
                for entry in deposit_source_entries
            )
            calc = opening + deposits + transfers_in - transfers_out + conv_in - conv_out - withdrawals + growth
            delta = ending - calc
            max_abs_delta = max(max_abs_delta, abs(delta))

            notes = []
            if transfers_in or transfers_out:
                notes.append('transfer/rollover')
            if conv_in or conv_out:
                notes.append('Roth conversion')
            if withdrawals:
                notes.append('withdrawal')
            if deposits:
                notes.append('deposit')

            recs.append({
                'year': row.get('year'),
                'account': acct,
                'owner': meta.get('owner_name', ''),
                'tax': meta.get('tax', ''),
                'type': meta.get('acct_type', ''),
                'opening': opening,
                'deposits': deposits,
                'transfers_in': transfers_in,
                'transfers_out': transfers_out,
                'conv_in': conv_in,
                'conv_out': conv_out,
                'withdrawals': withdrawals,
                'growth': growth,
                'ending': ending,
                'calc_ending': calc,
                'delta': delta,
                'notes': '; '.join(notes),
                'deposit_sources': deposit_sources_text,
            })
    return recs, max_abs_delta


def build_sheet25(ws, c, rows):
    """Account Reconciliation — foots every account from year to year."""
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'A5'
    section_title(ws, 1, 'Roll Forward by Account and Year', 16)
    write_cell(ws, 2, 1,
               'Formula: Opening + Deposits + Transfers In - Transfers Out + Roth Conversion In - Roth Conversion Out - Withdrawals + Growth = Ending. '
               'This sheet explains movements that do not appear as cash-flow withdrawals, such as Roth conversions and death-year rollovers.',
               bg=LGRAY)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=16)

    recs, max_abs_delta = account_reconciliation_rows(c, rows)

    hdrs = [
        'Year', 'Account', 'Owner', 'Tax', 'Type',
        'Opening', 'Deposits', 'Transfers In', 'Transfers Out',
        'Roth Conv In', 'Roth Conv Out', 'Withdrawals', 'Growth',
        'Calculated Ending', 'Reported Ending', 'Foot Delta', 'Notes',
        'Deposit Sources',
    ]
    r = 4
    for i, h in enumerate(hdrs, 1):
        bg = NAVY if i <= 5 else (GREEN if i in (6, 14, 15, 16) else DGRAY)
        write_hdr(ws, r, i, h, bg, WHITE, size=9)
    r += 1

    bad_fill = 'FCE4D6'
    warn_fill = 'FFF2CC'
    from ..person_labels import display_account
    for rec in recs:
        vals = [
            rec['year'], display_account(rec['account'], c), rec['owner'], rec['tax'], rec['type'],
            rec['opening'], rec['deposits'], rec['transfers_in'], rec['transfers_out'],
            rec['conv_in'], rec['conv_out'], rec['withdrawals'], rec['growth'],
            rec['calc_ending'], rec['ending'], rec['delta'], rec['notes'],
            rec['deposit_sources'],
        ]
        delta = abs(rec['delta'])
        row_bg = bad_fill if delta > 10 else (warn_fill if delta > 1 else None)
        for i, val in enumerate(vals, 1):
            fmt = FMT_YEAR if i == 1 else (FMT_DOLLAR if 6 <= i <= 16 else None)
            align = 'right' if 6 <= i <= 16 else ('center' if i in (1, 4) else 'left')
            write_cell(ws, r, i, val, fmt=fmt, bg=row_bg, align=align)
        r += 1

    ws.auto_filter.ref = f'A4:R{max(4, r-1)}'
    widths = {
        'A': 8, 'B': 20, 'C': 14, 'D': 12, 'E': 16,
        'F': 14, 'G': 14, 'H': 14, 'I': 14, 'J': 14, 'K': 14,
        'L': 14, 'M': 14, 'N': 15, 'O': 15, 'P': 12, 'Q': 28,
        'R': 40,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    qc('25. Account Reconciliation', 'Every account roll-forward foots', max_abs_delta < 10,
       f'max residual ${max_abs_delta:,.2f} across {len(recs)} account-years')

# ─────────────────────────────────────────────────────────────────────────────
# 10.  MAIN
# ─────────────────────────────────────────────────────────────────────────────

__all__ = ['validate_all', 'build_sheet21', 'build_sheet22', 'build_sheet23', 'build_sheet24', 'account_reconciliation_rows', 'build_sheet25']
