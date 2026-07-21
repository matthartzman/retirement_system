"""Wealth-transfer / goal-funding report sheets.

Report-only builders (Phase 1) for the optional planning modules:

    * Education Funding (529 plans + education goals)
    * Equity Compensation (RSU / ISO / NSO / ESPP)
    * Special-Needs Planning (SNT / ABLE)

Each builder consumes structured config parsed by
``data_io.parse_advanced_modules`` (keys ``edu_funding``, ``equity_comp``,
``special_needs``) and the projection ``rows``. None of these feed the
projection engine — cross-module engine integration (equity-comp AMT into the
lifetime-tax sheet, etc.) is deferred to a later phase.
"""

from .workbook_common import (
    DGRAY,
    FMT_DOLLAR,
    FMT_INT,
    FMT_PCT,
    FMT_YEAR,
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


def _role_display(c, value):
    """Translate a role value (husband/wife/member_1/member_2) to the
    household's actual nickname; pass through anything else (e.g. a
    grandchild's name) unchanged."""
    key = str(value or '').strip().lower().replace(' ', '_')
    return {'husband': _nick1(c), 'member_1': _nick1(c),
            'wife': _nick2(c), 'member_2': _nick2(c)}.get(key, value)


def _birth_year(date_str):
    """Best-effort birth year from a m/d/yyyy or yyyy-mm-dd string."""
    s = str(date_str or '').strip()
    if not s:
        return 0
    try:
        if '/' in s:
            parts = s.split('/')
            return int(parts[-1]) if len(parts[-1]) == 4 else 0
        if '-' in s:
            return int(s.split('-')[0])
        return int(s)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Education Funding (529 plans + goals)
# ─────────────────────────────────────────────────────────────────────────────

def _project_529_balance(acct, target_year, base_year):
    """Grow a 529 balance to ``target_year``, applying annual contributions
    within the account's contribution window (contributions credited at the
    start of each year, then grown)."""
    bal = acct['balance_today']
    g = acct['growth_rate']
    start = acct['contribution_start_year'] or base_year
    end = acct['contribution_end_year'] or 0
    for yr in range(base_year, max(base_year, target_year)):
        if end and start <= yr <= end:
            bal += acct['annual_contribution']
        bal *= (1 + g)
    return bal


def build_education_funding(ws, c, rows):
    """Education Funding — 529 account inventory, goal costs, and funded-ratio gap."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'EDUCATION FUNDING — 529 PLANS & GOALS', 8)
    base_year = int(c.get('plan_start', 2026))
    edu = c.get('edu_funding', {}) or {}
    accounts = edu.get('accounts', [])
    goals = edu.get('goals', [])
    policy = edu.get('policy', {})

    r = 3
    if not accounts and not goals:
        write_cell(ws, r, 1,
                   'No 529 accounts or education goals on file. Add them under '
                   'Education Funding in client_insurance_estate.csv to activate this analysis.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('30. Education Funding', 'Education module enabled; no data on file', True, '')
        return

    # ── Section A — 529 Account Inventory & Projection ───────────────────────
    write_hdr(ws, r, 1, 'Section A — 529 Account Inventory & Projected Value', NAVY, WHITE, span=8); r += 1
    hdrs = ['Account', 'Owner', 'Beneficiary', 'Balance Today', 'Annual Contribution',
            'Contrib. End', 'Growth', 'Proj. @ First Use']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    # First-use year defaults to the earliest goal start (or 18y horizon).
    default_use_year = min([g['start_year'] for g in goals if g['start_year']], default=base_year + 18)
    total_proj = 0.0
    for a in accounts:
        proj = _project_529_balance(a, default_use_year, base_year)
        total_proj += proj
        vals = [a['name'], _role_display(c, a['owner']), a['beneficiary'], a['balance_today'],
                a['annual_contribution'], a['contribution_end_year'] or '—',
                a['growth_rate'], proj]
        for i, v in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (4, 5, 8) else (FMT_PCT if i == 7 else (FMT_YEAR if i == 6 and isinstance(v, int) else None))
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    write_cell(ws, r, 3, 'Total projected at first use', bold=True)
    write_cell(ws, r, 8, total_proj, fmt=FMT_DOLLAR, bold=True, bg='E2EFDA')
    r += 3

    # ── Section B — Education Goals (inflated cost) ──────────────────────────
    total_need = 0.0
    if goals:
        write_hdr(ws, r, 1, 'Section B — Education Goals (Inflation-Adjusted Cost)', ORANGE, WHITE, span=8); r += 1
        hdrs = ['Goal', 'Beneficiary', 'Start', 'End', 'Annual Cost (today)', 'Inflation', 'Total Cost (inflated)', '']
        for i, h in enumerate(hdrs, 1):
            write_hdr(ws, r, i, h, DGRAY, WHITE)
        r += 1
        for g in goals:
            years = list(range(g['start_year'], (g['end_year'] or g['start_year']) + 1)) if g['start_year'] else []
            total_cost = sum(g['annual_cost_today'] * ((1 + g['cost_inflation_rate']) ** (yr - base_year)) for yr in years)
            total_need += total_cost
            vals = [g['name'], g['beneficiary'], g['start_year'] or '—', g['end_year'] or '—',
                    g['annual_cost_today'], g['cost_inflation_rate'], total_cost, '']
            for i, v in enumerate(vals, 1):
                fmt = FMT_DOLLAR if i in (5, 7) else (FMT_PCT if i == 6 else (FMT_YEAR if i in (3, 4) and isinstance(v, int) else None))
                write_cell(ws, r, i, v, fmt=fmt)
            r += 1
        r += 2

    # ── Section C — Funded-Ratio Gap ────────────────────────────────────────
    write_hdr(ws, r, 1, 'Section C — Funded-Ratio Gap', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(['Projected 529 (all accounts)', 'Total Inflated Need', 'Funded Ratio', 'Gap', 'Verdict'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    ratio = (total_proj / total_need) if total_need else 0.0
    gap = max(0.0, total_need - total_proj)
    verdict = 'Fully funded' if gap == 0 and total_need else (f'Underfunded' if total_need else 'No goals on file')
    bg = 'E2EFDA' if gap == 0 and total_need else 'FCE4D6'
    write_cell(ws, r, 1, total_proj, fmt=FMT_DOLLAR)
    write_cell(ws, r, 2, total_need, fmt=FMT_DOLLAR)
    write_cell(ws, r, 3, ratio, fmt=FMT_PCT)
    write_cell(ws, r, 4, gap, fmt=FMT_DOLLAR)
    write_cell(ws, r, 5, verdict, bg=bg)
    r += 3

    # ── Notes ────────────────────────────────────────────────────────────────
    notes = []
    if policy.get('allow_secure_2_roth_rollover'):
        notes.append('SECURE 2.0: up to $35,000 of unused 529 funds may be rolled to the '
                     "beneficiary's Roth IRA (15-year account age and annual-limit rules apply).")
    ded_limit = policy.get('state_deduction_limit_annual', 0)
    notes.append(f'State income-tax deduction on contributions: '
                 f'{"$%s/yr limit" % format(int(ded_limit), ",") if ded_limit else "none (per plan settings)"}.')
    for n in notes:
        write_cell(ws, r, 1, n, bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        r += 1

    qc('30. Education Funding', 'Account projection, goal costs, and funded-ratio gap computed', True,
       f'{len(accounts)} accounts, {len(goals)} goals')


# ─────────────────────────────────────────────────────────────────────────────
# Equity Compensation (RSU / ISO / NSO / ESPP)
# ─────────────────────────────────────────────────────────────────────────────

_EQUITY_TAX_TREATMENT = {
    'RSU': 'Ordinary income at vest (FMV × shares); LTCG/STCG on later sale gain.',
    'ISO': 'AMT preference = (FMV − strike) at exercise; qualifying sale → LTCG on full gain.',
    'NSO': 'Ordinary income on (FMV − strike) spread at exercise; LTCG/STCG on later sale.',
    'NQSO': 'Ordinary income on (FMV − strike) spread at exercise; LTCG/STCG on later sale.',
    'ESPP': 'Discount taxed as ordinary income; qualifying disposition → LTCG on remainder.',
}


def build_equity_comp(ws, c, rows):
    """Equity Compensation — grant inventory, projected proceeds, and tax treatment."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'EQUITY COMPENSATION — RSU / ISO / NSO / ESPP', 8)
    base_year = int(c.get('plan_start', 2026))
    grants = c.get('equity_comp', []) or []

    r = 3
    if not grants:
        write_cell(ws, r, 1,
                   'No equity-compensation grants on file. Add them under Equity Compensation '
                   'in client_insurance_estate.csv to activate this analysis.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('35. Equity Compensation', 'Equity module enabled; no data on file', True, '')
        return

    # ── Section A — Grant Inventory & Projected Proceeds ─────────────────────
    write_hdr(ws, r, 1, 'Section A — Grant Inventory & Projected Proceeds', NAVY, WHITE, span=8); r += 1
    hdrs = ['Grant', 'Recipient', 'Type', 'Shares', 'FMV Today', 'Strike', 'Sale Year', 'Proj. Proceeds']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    total_proceeds = 0.0
    for g in grants:
        sale_year = g['planned_sale_year'] or base_year
        fmv_at_sale = g['fmv_today'] * ((1 + g['fmv_growth_rate']) ** max(0, sale_year - base_year))
        strike = g['strike'] if g['grant_type'] in ('ISO', 'NSO', 'NQSO', 'ESPP') else 0.0
        proceeds = max(0.0, (fmv_at_sale - strike)) * g['shares']
        total_proceeds += proceeds
        vals = [g['name'], _role_display(c, g['recipient']), g['grant_type'], g['shares'], g['fmv_today'],
                (strike if strike else '—'), sale_year, proceeds]
        for i, v in enumerate(vals, 1):
            fmt = (FMT_DOLLAR if i in (5, 6, 8) and isinstance(v, (int, float)) else
                   (FMT_INT if i == 4 else (FMT_YEAR if i == 7 else None)))
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    write_cell(ws, r, 7, 'Total', bold=True)
    write_cell(ws, r, 8, total_proceeds, fmt=FMT_DOLLAR, bold=True, bg='E2EFDA')
    r += 3

    # ── Section B — Tax Treatment by Grant Type ──────────────────────────────
    write_hdr(ws, r, 1, 'Section B — Tax Treatment by Grant Type', ORANGE, WHITE, span=8); r += 1
    write_hdr(ws, r, 1, 'Type', DGRAY, WHITE)
    write_hdr(ws, r, 2, 'Federal / AMT Treatment', DGRAY, WHITE, span=7)
    r += 1
    for typ in sorted({g['grant_type'] for g in grants}):
        write_cell(ws, r, 1, typ, bold=True)
        write_cell(ws, r, 2, _EQUITY_TAX_TREATMENT.get(typ, 'Consult grant agreement / tax advisor.'), align='left')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=8)
        r += 1
    r += 1
    write_cell(ws, r, 1,
               'Note: projected proceeds are pre-tax estimates at planned-sale FMV. When the Equity '
               'Compensation module is enabled, RSU/NSO ordinary income, the ISO AMT preference (with '
               'minimum-tax credit carryforward), and sale-year capital gains flow through the projection '
               'into the Lifetime Tax and Net Worth results.',
               bg='FFF2CC', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('35. Equity Compensation', 'Grant inventory, projected proceeds, and tax treatment documented', True,
       f'{len(grants)} grants')


# ─────────────────────────────────────────────────────────────────────────────
# Special-Needs Planning (SNT / ABLE)
# ─────────────────────────────────────────────────────────────────────────────

def build_special_needs(ws, c, rows):
    """Special-Needs Planning — lifetime support need, SNT funding, ABLE guardrails."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'SPECIAL-NEEDS PLANNING — SNT / ABLE', 8)
    base_year = int(c.get('plan_start', 2026))
    sn = c.get('special_needs', {}) or {}

    r = 3
    if not sn:
        write_cell(ws, r, 1,
                   'No special-needs beneficiary on file. Populate the Estate Planning → SN_* rows in '
                   'client_insurance_estate.csv to activate this analysis.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('36. Special-Needs Planning', 'Module enabled; no beneficiary on file', True, '')
        return

    b = sn.get('beneficiary', {})
    t = sn.get('snt', {})
    a = sn.get('able', {})
    g = sn.get('gov_benefits', {})

    birth_year = _birth_year(b.get('dob'))
    current_age = (base_year - birth_year) if birth_year else 0
    lifetime_to_age = b.get('lifetime_to_age', 0)
    support_years = max(0, lifetime_to_age - current_age) if (lifetime_to_age and current_age) else 0

    # ── Section A — Lifetime Support Need ────────────────────────────────────
    write_hdr(ws, r, 1, 'Section A — Lifetime Support Need', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(['Beneficiary', 'Current Age', 'Support To Age', 'Annual Support (today)',
                           'Inflation', 'Years', 'Total Lifetime Need'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    infl = b.get('inflation_rate', 0.025)
    annual = b.get('annual_support_today', 0)
    total_need = sum(annual * ((1 + infl) ** yr) for yr in range(support_years))
    vals = [b.get('name') or '(unnamed)', current_age or '—', lifetime_to_age or '—',
            annual, infl, support_years, total_need]
    for i, v in enumerate(vals, 1):
        fmt = FMT_DOLLAR if i in (4, 7) else (FMT_PCT if i == 5 else None)
        write_cell(ws, r, i, v, fmt=fmt)
    r += 3

    # ── Section B — Special Needs Trust Funding ──────────────────────────────
    write_hdr(ws, r, 1, 'Section B — Special-Needs Trust (SNT) Funding vs Need', ORANGE, WHITE, span=8); r += 1
    for i, h in enumerate(['Balance Today', 'Annual Funding', 'Growth', 'Third-Party',
                           'Proj. Value @ Support End', 'Lifetime Need', 'Funding Verdict'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    snt_bal = t.get('balance_today', 0)
    for _yr in range(support_years):
        snt_bal += t.get('funding_schedule', 0)
        snt_bal *= (1 + t.get('growth_rate', 0.05))
    gap = max(0.0, total_need - snt_bal)
    verdict = 'Adequately funded' if gap == 0 else f'Shortfall vs projected support'
    bg = 'E2EFDA' if gap == 0 else 'FCE4D6'
    vals = [t.get('balance_today', 0), t.get('funding_schedule', 0), t.get('growth_rate', 0.05),
            'Yes (no payback)' if t.get('is_third_party') else 'No (Medicaid payback)',
            snt_bal, total_need, verdict]
    for i, v in enumerate(vals, 1):
        fmt = FMT_DOLLAR if i in (1, 2, 5, 6) else (FMT_PCT if i == 3 else None)
        write_cell(ws, r, i, v, fmt=fmt, bg=bg if i == 7 else None)
    r += 3

    # ── Section C — ABLE Account & Eligibility Guardrails ────────────────────
    write_hdr(ws, r, 1, 'Section C — ABLE Account & Benefit-Eligibility Guardrails', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(['ABLE Balance', 'Monthly Contribution', 'Annual Limit',
                           'SSI Monthly', 'SSDI Monthly', 'Medicaid', 'Guardrail'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    able_bal = a.get('balance_today', 0)
    # SSI is suspended when countable ABLE assets exceed $100,000.
    guardrail = 'ABLE < $100K — SSI preserved' if able_bal < 100000 else 'ABLE ≥ $100K — SSI suspended'
    g_bg = 'E2EFDA' if able_bal < 100000 else 'FCE4D6'
    vals = [able_bal, a.get('monthly_contribution', 0), a.get('annual_contribution_limit', 0),
            g.get('ssi_monthly', 0), g.get('ssdi_monthly', 0),
            'Enrolled' if g.get('medicaid_enrolled') else 'Not enrolled', guardrail]
    for i, v in enumerate(vals, 1):
        fmt = FMT_DOLLAR if i in (1, 2, 3, 4, 5) else None
        write_cell(ws, r, i, v, fmt=fmt, bg=g_bg if i == 7 else None)
    r += 3

    write_cell(ws, r, 1,
               'Note: a properly drafted first-party (d4A) or third-party SNT holds assets outside the '
               "beneficiary's countable resources, preserving SSI/Medicaid. ABLE contributions above the "
               'annual gift-exclusion limit and balances above $100K can affect SSI. Coordinate with a '
               'special-needs attorney.',
               bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('36. Special-Needs Planning', 'Lifetime need, SNT funding gap, and ABLE guardrails computed', True, '')


# ─────────────────────────────────────────────────────────────────────────────
# Business Succession
# ─────────────────────────────────────────────────────────────────────────────

def build_business_succession(ws, c, rows):
    """Business Succession — entity valuation, buy-sell funding gap, estate liquidity."""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'BUSINESS SUCCESSION PLANNING', 8)
    base_year = int(c.get('plan_start', 2026))
    entities = c.get('business_succession', []) or []

    r = 3
    if not entities:
        write_cell(ws, r, 1,
                   'No business interests on file. Add them under Business Succession in '
                   'client_business.csv to activate this analysis.',
                   bg='F4F5F7', align='left')
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        qc('34. Business Succession', 'Module enabled; no business interests on file', True, '')
        return

    # ── Section A — Entity Inventory & Projected Valuation ───────────────────
    write_hdr(ws, r, 1, 'Section A — Business Interests & Projected Valuation', NAVY, WHITE, span=8); r += 1
    hdrs = ['Entity', 'Owner', 'Ownership %', 'Valuation Today', 'Growth',
            'Transfer Year', 'Proj. Valuation', "Owner's Share"]
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    per_entity = []
    for e in entities:
        transfer_year = e['transfer_year'] or base_year
        proj_val = e['valuation_today'] * ((1 + e['valuation_growth_rate']) ** max(0, transfer_year - base_year))
        owner_share = proj_val * e['ownership_pct']
        per_entity.append((e, transfer_year, proj_val, owner_share))
        vals = [e['entity_name'], _role_display(c, e['owner']), e['ownership_pct'], e['valuation_today'],
                e['valuation_growth_rate'], transfer_year, proj_val, owner_share]
        for i, v in enumerate(vals, 1):
            fmt = (FMT_DOLLAR if i in (4, 7, 8) else (FMT_PCT if i in (3, 5) else
                   (FMT_YEAR if i == 6 else None)))
            write_cell(ws, r, i, v, fmt=fmt)
        r += 1
    total_owner_share = sum(x[3] for x in per_entity)
    write_cell(ws, r, 7, 'Total owner share', bold=True)
    write_cell(ws, r, 8, total_owner_share, fmt=FMT_DOLLAR, bold=True, bg='E2EFDA')
    r += 3

    # ── Section B — Buy-Sell Funding Adequacy ────────────────────────────────
    write_hdr(ws, r, 1, 'Section B — Buy-Sell Funding Adequacy (at transfer)', ORANGE, WHITE, span=8); r += 1
    hdrs = ['Entity', 'Buy-Sell Type', 'Funding Vehicle', "Owner's Share",
            'Funding + Key-Person', 'Gap', 'Verdict']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    for e, transfer_year, proj_val, owner_share in per_entity:
        funded = e['funding_amount'] + e['key_person_coverage']
        gap = max(0.0, owner_share - funded)
        verdict = 'Fully funded' if gap == 0 else 'Underfunded buy-sell'
        bg = 'E2EFDA' if gap == 0 else 'FCE4D6'
        vals = [e['entity_name'], e['buy_sell_type'], e['funding_vehicle'],
                owner_share, funded, gap, verdict]
        for i, v in enumerate(vals, 1):
            fmt = FMT_DOLLAR if i in (4, 5, 6) else None
            write_cell(ws, r, i, v, fmt=fmt, bg=bg if i == 7 else None)
        r += 1
    r += 2

    # ── Section C — Estate-Liquidity Interaction ─────────────────────────────
    write_hdr(ws, r, 1, 'Section C — Estate-Liquidity Interaction (see 2G. Estate & Legacy Planning)', NAVY, WHITE, span=8); r += 1
    for i, h in enumerate(["Owner's Business Value", 'Federal Exemption (MFJ)',
                           'IL Estate Exemption', 'Over IL Exemption?', 'Illiquid Estate Flag'], 1):
        write_hdr(ws, r, i, h, DGRAY, WHITE)
    r += 1
    fed_exempt = float(c.get('fed_exempt', 30000000))
    il_exempt = float(c.get('il_exempt', 4000000))
    over_il = total_owner_share > il_exempt
    # Illiquid concentration: business share is a large fraction of terminal net worth.
    terminal_nw = float(rows[-1].get('total_nw', 0)) if rows else 0.0
    concentration = (total_owner_share / terminal_nw) if terminal_nw else 0.0
    illiquid_flag = 'Concentrated (>25% of estate)' if concentration > 0.25 else 'Manageable'
    flag_bg = 'FCE4D6' if concentration > 0.25 else 'E2EFDA'
    vals = [total_owner_share, fed_exempt, il_exempt,
            'Yes' if over_il else 'No', illiquid_flag]
    for i, v in enumerate(vals, 1):
        fmt = FMT_DOLLAR if i in (1, 2, 3) else None
        write_cell(ws, r, i, v, fmt=fmt, bg=(('FCE4D6' if over_il else 'E2EFDA') if i == 4 else (flag_bg if i == 5 else None)))
    r += 3

    write_cell(ws, r, 1,
               'Note: a funded buy-sell agreement (cross-purchase or entity-redemption) converts an '
               'illiquid business interest into cash for heirs and sets the estate valuation. Key-person '
               'coverage protects operating value during a transition. Where the owner\'s share is a large '
               'share of the estate, life insurance in an ILIT can supply estate liquidity without '
               'inflating the taxable estate. Estate-tax modeling lives on 2G. Estate & Legacy Planning.',
               bg='F4F5F7', align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)

    qc('34. Business Succession', 'Valuation projection, buy-sell funding gap, and estate liquidity computed', True,
       f'{len(entities)} entities; ${total_owner_share:,.0f} owner share')


__all__ = ['build_education_funding', 'build_equity_comp', 'build_special_needs',
           'build_business_succession']
