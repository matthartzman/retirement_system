"""Insurance / protection report sheets.

Report-only builders (Phase 1) for the optional protection modules:

    * Existing Life Insurance (in-force policy inventory + cash-value projection)
    * Disability Income Insurance (benefit adequacy + gap)
    * Property & Casualty / Umbrella Liability (coverage inventory + umbrella adequacy)

Each builder consumes structured config parsed by
``data_io.parse_advanced_modules`` (keys ``life_policies``, ``disability``,
``pc_umbrella``) and the projection ``rows``. These sheets are the in-force
counterpart to the Life Insurance *need* analysis (Sheet 19); they do not feed
the projection engine.
"""

from .workbook_common import (
    DGRAY,
    FMT_DOLLAR,
    FMT_PCT,
    NAVY,
    ORANGE,
    WHITE,
    qc,
    section_title,
    write_cell,
    write_hdr,
)


def _nick1(c):
    return str(c.get('h_nick') or c.get('h_name') or 'Member 1')


def _nick2(c):
    return str(c.get('w_nick') or c.get('w_name') or 'Member 2')


def _household_net_worth(c, rows):
    """Current-year household net worth for adequacy ratios."""
    if rows:
        nw = rows[0].get('total_nw')
        if nw:
            return float(nw)
    # Fallback: sum of investable balances (registry-independent).
    balances = c.get('balances', {}) or {}
    return float(sum(v for k, v in balances.items() if not str(k).lower().endswith('_checking')))


# ─────────────────────────────────────────────────────────────────────────────
# Existing Life Insurance
# ─────────────────────────────────────────────────────────────────────────────

def build_existing_life(ws, c, rows):
    """Existing Life Insurance — in-force inventory, cash-value projection, premium timeline."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'EXISTING LIFE INSURANCE — IN-FORCE POLICIES', 8)
    base_year = int(c.get('plan_start', 2026))
    policies = c.get('life_policies', []) or []

    r = 3
    if not policies:
        write_cell(ws, r, 1,
                   'No in-force life-insurance policies on file. Add them under Insurance In Force in '
                   'client_insurance_estate.csv. (See Sheet 19 — Life Insurance for the coverage-need analysis.)',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('31. Existing Life Insurance', 'Module enabled; no in-force policies on file', True, '')
        return

    # ── Section A — Policy Inventory ─────────────────────────────────────────
    write_hdr(ws, r, 1, 'Section A — In-Force Policy Inventory', NAVY, WHITE, span=8); r += 1
    hdrs = ['Policy', 'Insured', 'Beneficiary', 'Type', 'Face Amount', 'Cash Value', 'Annual Premium', 'ILIT?']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    total_face = total_cv = total_prem = 0.0
    for p in policies:
        total_face += p['face_amount']
        total_cv += p['cash_value_today']
        total_prem += p['annual_premium']
        vals = [p['name'], p['insured'], p['beneficiary'], p['policy_type'],
                p['face_amount'], p['cash_value_today'], p['annual_premium'],
                'Yes' if p['owned_by_ilit'] else 'No']
        for i, v in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (5, 6, 7) else None
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    write_cell(ws, r, 4, 'Total', bold=True)
    write_cell(ws, r, 5, total_face, fmt=FMT_DOLLAR, bold=True, bg='E2EFDA')
    write_cell(ws, r, 6, total_cv, fmt=FMT_DOLLAR, bold=True)
    write_cell(ws, r, 7, total_prem, fmt=FMT_DOLLAR, bold=True)
    r += 3

    # ── Section B — Cash-Value Projection (permanent policies) ───────────────
    perm = [p for p in policies if p['cash_value_today'] > 0 or p['cash_value_growth_rate'] > 0]
    if perm:
        write_hdr(ws, r, 1, 'Section B — Cash-Value Projection (Permanent Policies)', ORANGE, WHITE, span=8); r += 1
        horizon = [base_year, base_year + 5, base_year + 10, base_year + 20]
        write_hdr(ws, r, 1, 'Policy', DGRAY, WHITE)
        for i, yr in enumerate(horizon, 2):
            write_hdr(ws, r, i, str(yr), DGRAY, WHITE)
        r += 1
        for p in perm:
            write_cell(ws, r, 1, p['name'])
            for i, yr in enumerate(horizon, 2):
                cv = p['cash_value_today'] * ((1 + p['cash_value_growth_rate']) ** max(0, yr - base_year))
                write_cell(ws, r, i, cv, fmt=FMT_DOLLAR)
            r += 1
        r += 2

    # ── Section C — Coverage-Need Reconciliation ─────────────────────────────
    write_hdr(ws, r, 1, 'Section C — Coverage vs Need (summary; see Sheet 19 for detail)', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(['Total In-Force Face', 'Income-Replacement Need (10× earned)',
                           'Mortgage Payoff', 'Total Need', 'Surplus / (Gap)', 'Verdict'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    income_need = float(c.get('earned', 0)) * 10
    mort_need = float(c.get('mort_bal', 0))
    total_need = income_need + mort_need
    surplus = total_face - total_need
    verdict = 'Coverage adequate' if surplus >= 0 else 'Coverage gap'
    bg = 'E2EFDA' if surplus >= 0 else 'FCE4D6'
    for i, v in enumerate([total_face, income_need, mort_need, total_need, surplus, verdict], 1):
        fmt = FMT_DOLLAR if i in (1, 2, 3, 4, 5) else None
        write_cell(ws, r, i, v, fmt=fmt, bg=bg if i == 6 else None)
    r += 3

    write_cell(ws, r, 1,
               'Note: term policies expire at their term-end year and provide no cash value; permanent '
               '(whole/universal) policies build cash value shown above. ILIT-owned policies sit outside '
               'the taxable estate. This inventory complements the need analysis on Sheet 19.',
               bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('31. Existing Life Insurance', 'Inventory, cash-value projection, and coverage reconciliation built', True,
       f'{len(policies)} policies; ${total_face:,.0f} face')


# ─────────────────────────────────────────────────────────────────────────────
# Disability Income Insurance
# ─────────────────────────────────────────────────────────────────────────────

def build_disability(ws, c, rows):
    """Disability Income — benefit adequacy, elimination-period gap, taxability."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'DISABILITY INCOME INSURANCE', 8)
    di = c.get('disability', {}) or {}
    policies = di.get('policies', [])

    r = 3
    if not policies:
        write_cell(ws, r, 1,
                   'No disability-income policies on file. Add them under Insurance In Force (DI_*) in '
                   'client_insurance_estate.csv. Disability coverage typically lapses at retirement.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('32. Disability Income', 'Module enabled; no policies on file', True, '')
        return

    earned = float(c.get('earned', 0))

    # ── Section A — Policy Inventory & Benefit Adequacy ──────────────────────
    write_hdr(ws, r, 1, 'Section A — Policy Inventory & Benefit Adequacy', NAVY, WHITE, span=8); r += 1
    hdrs = ['Policy', 'Insured', 'Type', 'Monthly Benefit', 'Annual Benefit',
            'Elim. Days', 'Benefit Period', 'Replacement %']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    total_annual_benefit = 0.0
    for p in policies:
        annual_benefit = p['monthly_benefit'] * 12
        total_annual_benefit += annual_benefit
        repl = (annual_benefit / earned) if earned else 0.0
        vals = [p['name'], p['insured'], p['coverage_type'], p['monthly_benefit'], annual_benefit,
                p['elimination_days'], f"{p['benefit_period_years']} yr" if p['benefit_period_years'] else '—', repl]
        for i, v in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (4, 5) else (FMT_PCT if i == 8 else None)
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    r += 2

    # ── Section B — Adequacy Verdict ─────────────────────────────────────────
    write_hdr(ws, r, 1, 'Section B — Income-Replacement Adequacy', ORANGE, WHITE, span=8); r += 1
    for i, h in enumerate(['Pre-Retirement Earned Income', 'Total Annual DI Benefit',
                           'Replacement Ratio', 'Target (60–70%)', 'Verdict'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    repl_ratio = (total_annual_benefit / earned) if earned else 0.0
    adequate = repl_ratio >= 0.60
    verdict = 'Adequate (≥60%)' if adequate else ('Below target' if earned else 'No earned income to replace')
    bg = 'E2EFDA' if adequate else 'FCE4D6'
    for i, v in enumerate([earned, total_annual_benefit, repl_ratio, '60–70%', verdict], 1):
        fmt = FMT_DOLLAR if i in (1, 2) else (FMT_PCT if i == 3 else None)
        write_cell(ws, r, i, v, fmt=fmt, bg=bg if i == 5 else None)
    r += 3

    # ── Notes ────────────────────────────────────────────────────────────────
    taxable_note = []
    for p in policies:
        if p['premium_pre_tax']:
            taxable_note.append(f"{p['name']}: employer/pre-tax premium → benefit is TAXABLE income.")
        else:
            taxable_note.append(f"{p['name']}: after-tax premium → benefit is TAX-FREE.")
    for n in taxable_note:
        write_cell(ws, r, 1, n, bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        r += 1
    write_cell(ws, r, 1,
               'Note: benefits begin only after the elimination period (an income gap the emergency fund '
               'must bridge) and end at the benefit-period limit or retirement. Set a disability year in the '
               'DI_Scenario row to re-project the plan: earned income stops and the (elimination-prorated) '
               'benefit replaces it, taxable when the premium was paid pre-tax.',
               bg='FFF2CC', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('32. Disability Income', 'Benefit adequacy, replacement ratio, and taxability documented', True,
       f'{len(policies)} policies')


# ─────────────────────────────────────────────────────────────────────────────
# Property & Casualty / Umbrella Liability
# ─────────────────────────────────────────────────────────────────────────────

def build_pc_umbrella(ws, c, rows):
    """Property & Casualty / Umbrella — coverage inventory and umbrella adequacy vs net worth."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'PROPERTY & CASUALTY / UMBRELLA LIABILITY', 8)
    pc = c.get('pc_umbrella', {}) or {}
    policies = pc.get('policies', [])

    r = 3
    if not policies:
        write_cell(ws, r, 1,
                   'No property/casualty or umbrella policies on file. Add them under Insurance In Force '
                   '(PC_*) in client_insurance_estate.csv.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('33. P&C Umbrella', 'Module enabled; no policies on file', True, '')
        return

    # ── Section A — Coverage Inventory ───────────────────────────────────────
    write_hdr(ws, r, 1, 'Section A — Coverage Inventory', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(['Policy', 'Type', 'Coverage Limit', 'Deductible', 'Annual Premium'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    umbrella_coverage = 0.0
    total_premium = 0.0
    for p in policies:
        total_premium += p['annual_premium']
        if str(p['policy_type']).strip().lower() == 'umbrella':
            umbrella_coverage += p['coverage_limit']
        vals = [p['name'], p['policy_type'], p['coverage_limit'], p['deductible'], p['annual_premium']]
        for i, v in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (3, 4, 5) else None
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    write_cell(ws, r, 4, 'Total premium', bold=True)
    write_cell(ws, r, 5, total_premium, fmt=FMT_DOLLAR, bold=True)
    r += 3

    # ── Section B — Umbrella Adequacy vs Net Worth ───────────────────────────
    write_hdr(ws, r, 1, 'Section B — Umbrella Liability Adequacy', ORANGE, WHITE, span=8); r += 1
    for i, h in enumerate(['Household Net Worth', 'Target Multiple', 'Recommended Umbrella',
                           'In-Force Umbrella', 'Gap', 'Verdict'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    nw = _household_net_worth(c, rows)
    mult = pc.get('umbrella_target_multiple', 0) or 1.0
    recommended = nw * mult
    gap = max(0.0, recommended - umbrella_coverage)
    verdict = 'Adequate' if gap == 0 else 'Increase umbrella limit'
    bg = 'E2EFDA' if gap == 0 else 'FCE4D6'
    for i, v in enumerate([nw, mult, recommended, umbrella_coverage, gap, verdict], 1):
        fmt = FMT_DOLLAR if i in (1, 3, 4, 5) else (('0.0"×"') if i == 2 else None)
        write_cell(ws, r, i, v, fmt=fmt, bg=bg if i == 6 else None)
    r += 3

    write_cell(ws, r, 1,
               'Note: umbrella liability should generally cover at least net worth (often 1.5× for HNW '
               'households), sitting above the underlying auto/homeowner limits. Verify the umbrella\'s '
               'required underlying limits are met by the P&C policies above.',
               bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('33. P&C Umbrella', 'Coverage inventory and umbrella adequacy vs net worth computed', True,
       f'{len(policies)} policies; ${umbrella_coverage:,.0f} umbrella')


__all__ = ['build_existing_life', 'build_disability', 'build_pc_umbrella']
