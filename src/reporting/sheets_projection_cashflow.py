"""Cash Flow Projection sheet builder (Sheet 6).

Displays year-by-year cash flow analysis including:
- Income streams (earned, Social Security, pension, annuities, RMDs, note P+I)
- Tax & RMD columns (Roth conversions, AGI, taxable income, federal/state taxes, NIIT, IRMAA,
  payroll tax, LTCG tax)
- Spending breakdown (base, housing detail, wellness detail, travel, other, HELOC P&I)
- Account-level withdrawals (trust, HSA, Roth, IRA by type with collapsible detail)
- Cash bridge (income vs. expense gap analysis)

Includes collapsible column groups for detail/subtotal toggling and
home sale event callouts when applicable.
"""

from .workbook_common import *


def build_sheet6(ws, c, rows):
    """Cash Flow Projection — account-level withdrawals, collapsible groups, auto-fit."""
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'D3'
    ws.sheet_properties.outlinePr.summaryBelow = False  # summary row above detail

    # Column layout:
    # 1-3: Identifiers (Year, H Age, W Age)
    # 4-14: INCOME (Earned, H SS, W SS, Pension, W Sgl, W Jnt, H Sgl, H Jnt, Note, RMD, Σ)
    # 15-23: TAX (Roth Conv, AGI, Taxable, Fed, State, NIIT, IRMAA, Payroll, LTCG)
    # 24-38: SPENDING (Base, Housing detail, Wellness detail, Travel, Other, HELOC P&I, Σ)
    # 37-52: WITHDRAWALS — account level
    #   37: H Trust WD   38: W Trust WD   39: Σ Trust
    #   40: HSA WD
    #   41: H Roth WD   42: W Roth WD   43: Σ Roth
    #   44: H IRA RMD   45: H IRA Elec  46: H IRA Conv  47: H IRA Outflow
    #   48: W IRA RMD   49: W IRA Elec  50: W IRA Conv  51: W IRA Outflow
    #   52: HELOC Draw  53: HELOC Bal   54: Σ Cash Draws
    # 54: Total NW (balance check) — signed surplus/shortfall is Cash Bridge Gap, above

    def _pos(v):
        try:
            return float(v or 0) > 0
        except Exception:
            return False

    include_rent = bool(any(_pos(r.get('rent_yr')) for r in rows))
    ltc_configured = bool(c.get('ltc_enabled', False) and _pos(c.get('ltc_annual_prem')))
    include_ltc = bool(ltc_configured or any(_pos(r.get('ltc_prem_yr')) for r in rows))

    COL = {
        'Year': 1, 'H_Age': 2, 'W_Age': 3,
        'Earned': 4, 'H_SS': 5, 'W_SS': 6, 'Pension': 7,
        'W_Sgl': 8, 'W_Jnt': 9, 'H_Sgl': 10, 'H_Jnt': 11, 'Note': 12, 'RMD': 13, 'Σ_Inc': 14,
        'Roth_Conv': 15, 'AGI': 16, 'Taxable': 17, 'Fed': 18, 'State': 19, 'NIIT': 20, 'IRMAA': 21,
        'Payroll': 22, 'LTCG': 23,
    }
    col = 24
    for key in [
        'Spend_Base', 'Housing', 'Mort_PI', 'Prop_Tax', 'Housing_Utilities',
        'Home_Imp', 'Housing_Maintenance', 'Housing_Other'
    ]:
        COL[key] = col; col += 1
    if include_rent:
        COL['Rent_Det'] = col; col += 1
    for key in [
        'Wellness', 'Wellness_Premiums', 'Wellness_Medical', 'Wellness_Dental',
        'Wellness_Vision', 'Wellness_Rx_Otc', 'Wellness_Other'
    ]:
        COL[key] = col; col += 1
    if include_ltc:
        COL['HC_LTC'] = col; col += 1
    for key in ['Travel', 'Other', 'HELOC_PAI', 'Σ_Spend']:
        COL[key] = col; col += 1
    for key in ['Total_Tax', 'Total_Cash_Need', 'Income_Funding', 'Portfolio_Income',
                'Other_Funding', 'Req_Portfolio_Draws', 'Cash_Bridge_Gap']:
        COL[key] = col; col += 1
    for key in [
        'H_Trust_WD', 'W_Trust_WD', 'Σ_Trust', 'HSA_WD', 'H_Roth_WD', 'W_Roth_WD', 'Σ_Roth',
        'H_IRA_RMD', 'H_IRA_Elec', 'H_IRA_Conv', 'H_IRA_Tot',
        'W_IRA_RMD', 'W_IRA_Elec', 'W_IRA_Conv', 'W_IRA_Tot',
        'HELOC_Draw', 'HELOC_Bal', 'Σ_WD', 'NW_Check'
    ]:
        COL[key] = col; col += 1
    spending_span = COL['Σ_Spend'] - COL['Spend_Base'] + 1
    cash_bridge_span = COL['Cash_Bridge_Gap'] - COL['Total_Tax'] + 1
    withdrawal_span = COL['Σ_WD'] - COL['H_Trust_WD'] + 1

    # ── Group header row 1 ────────────────────────────────────────────────────
    write_hdr(ws, 1, COL['Year'],     'Identifiers', DGRAY, WHITE, span=3)
    write_hdr(ws, 1, COL['Earned'],   'INCOME',       BLUE,  WHITE, span=11)
    write_hdr(ws, 1, COL['Roth_Conv'],'TAX & RMD',   ORANGE,WHITE, span=9)
    write_hdr(ws, 1, COL['Spend_Base'],'SPENDING',   RED,   WHITE, span=spending_span)
    write_hdr(ws, 1, COL['Total_Tax'], 'CASH BRIDGE', NAVY, WHITE, span=cash_bridge_span)
    write_hdr(ws, 1, COL['H_Trust_WD'],'ACCOUNT OUTFLOWS — CASH DRAWS & IRA CONVERSIONS', GREEN, WHITE, span=withdrawal_span)
    # Roth conversions are account outflows/taxable, but are intentionally not
    # included in the cash-draw subtotal used by the cash bridge.
    write_hdr(ws, 1, COL['NW_Check'], 'NET WORTH',    NAVY,  WHITE, span=1)

    # ── Column headers row 2 ─────────────────────────────────────────────────
    SUBTOTAL_COLS = {COL['Σ_Inc'], COL['Σ_Spend'], COL['Σ_Trust'],
                     COL['Σ_Roth'], COL['H_IRA_Tot'], COL['W_IRA_Tot'],
                     COL['Σ_WD'], COL['AGI'], COL['HELOC_Bal'], COL['HELOC_PAI'],
                     COL['Total_Cash_Need'], COL['Req_Portfolio_Draws'], COL['Cash_Bridge_Gap']}
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    hdr2 = [
        (COL['Year'],       'Year'),         (COL['H_Age'],      f'{_n1} Age'),
        (COL['W_Age'],      f'{_n2} Age'),   (COL['Earned'],     'Earned'),
        (COL['H_SS'],       f'{_n1} SS'),    (COL['W_SS'],       f'{_n2} SS'),
        (COL['Pension'],    'Pension'),      (COL['W_Sgl'],      f'{_n2} Single Ann'),
        (COL['W_Jnt'],      f'{_n2} Joint Ann'),  (COL['H_Sgl'],  f'{_n1} Single Ann'),
        (COL['H_Jnt'],      f'{_n1} Joint Ann'),  (COL['Note'],   'Note P+I'),
        (COL['RMD'],        'RMD Dist'),     (COL['Σ_Inc'],      'Σ Income'),
        (COL['Roth_Conv'],  'Roth Conv'),    (COL['AGI'],        'AGI'),
        (COL['Taxable'],    'Taxable Inc'),  (COL['Fed'],        'Fed Tax'),
        (COL['State'],      'State Tax'),    (COL['NIIT'],       'NIIT'),
        (COL['IRMAA'],      'IRMAA'),
        (COL['Payroll'],    'Payroll Tax'), (COL['LTCG'],       'LTCG Tax'),
        (COL['Spend_Base'], 'Spend Base'),   (COL['Housing'],    'Housing'),
        (COL['Mort_PI'],    'Mortgage P&I'), (COL['Prop_Tax'],   'Property Tax'),
        (COL['Housing_Utilities'], 'Utilities'), (COL['Home_Imp'], 'Home Impr'),
        (COL['Housing_Maintenance'], 'Maintenance'), (COL['Housing_Other'], 'Other'),
        *(([(COL['Rent_Det'], 'Rent')] if include_rent else [])),
        (COL['Wellness'], 'Wellness'), (COL['Wellness_Premiums'], 'Healthcare Premiums'),
        (COL['Wellness_Medical'], 'Medical'), (COL['Wellness_Dental'], 'Dental'),
        (COL['Wellness_Vision'], 'Vision'), (COL['Wellness_Rx_Otc'], 'Rx/OTC'),
        (COL['Wellness_Other'], 'Other Wellness'),
        *(([(COL['HC_LTC'], 'LTC Prem')] if include_ltc else [])),
        (COL['Travel'],     'Travel'),
        (COL['Other'],      'Other'),        (COL['HELOC_PAI'],  'HELOC P&I'),
        (COL['Σ_Spend'],    'Σ Spend'),
        (COL['Total_Tax'], 'Total Taxes'),
        (COL['Total_Cash_Need'], 'Total Cash Need'), (COL['Income_Funding'], 'Income Funding'),
        (COL['Portfolio_Income'], 'Portfolio Income'), (COL['Other_Funding'], 'Other Funding'),
        (COL['Req_Portfolio_Draws'], 'Required Portfolio Cash Draws'),
        (COL['Cash_Bridge_Gap'], 'Cash Bridge Gap / (Surplus)'),
        (COL['H_Trust_WD'], f'{_n1} Trust WD'),   (COL['W_Trust_WD'], f'{_n2} Trust WD'),
        (COL['Σ_Trust'],    'Σ Trust'),      (COL['HSA_WD'],     'HSA WD'),
        (COL['H_Roth_WD'],  f'{_n1} Roth WD'),    (COL['W_Roth_WD'],  f'{_n2} Roth WD'),
        (COL['Σ_Roth'],     'Σ Roth'),
        (COL['H_IRA_RMD'],  f'{_n1} IRA RMD'),    (COL['H_IRA_Elec'], f'{_n1} IRA Elec'),
        (COL['H_IRA_Conv'], f'{_n1} IRA Conv'),   (COL['H_IRA_Tot'],  f'{_n1} IRA Outflow'),
        (COL['W_IRA_RMD'],  f'{_n2} IRA RMD'),    (COL['W_IRA_Elec'], f'{_n2} IRA Elec'),
        (COL['W_IRA_Conv'], f'{_n2} IRA Conv'),   (COL['W_IRA_Tot'],  f'{_n2} IRA Outflow'),
        (COL['HELOC_Draw'], 'HELOC Draw'),
        (COL['HELOC_Bal'],  'HELOC Bal'),    (COL['Σ_WD'],       'Σ Cash Draws'),
        (COL['NW_Check'],   'NW Check'),
    ]
    for col, hdr in hdr2:
        is_sub = col in SUBTOTAL_COLS
        bg = LGRAY if is_sub else DGRAY
        fg = '000000' if is_sub else WHITE
        write_hdr(ws, 2, col, hdr, bg, fg, size=9)

    # Add comment to Total Taxes header explaining its composition
    total_tax_cell = ws.cell(row=2, column=COL['Total_Tax'])
    total_tax_cell.comment = Comment(
        "Equals the sum of Fed Tax, State Tax, NIIT, IRMAA, Payroll Tax, and LTCG Tax shown in the Tax & RMD section.",
        "Report Generator"
    )

    # ── Collapsible column groups ─────────────────────────────────────────────
    # summaryRight=False: summary col appears LEFT of its detail cols
    ws.sheet_properties.outlinePr.summaryRight = False
    # Group the detail columns within each section (hide detail, show subtotal)
    # Housing detail includes every Housing spending group; Rent only appears when configured.
    housing_detail_cols = [
        COL['Mort_PI'], COL['Prop_Tax'], COL['Housing_Utilities'], COL['Home_Imp'],
        COL['Housing_Maintenance'], COL['Housing_Other']
    ]
    if include_rent:
        housing_detail_cols.append(COL['Rent_Det'])
    for col in housing_detail_cols:
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # Wellness detail uses the Wellness Budget Detail expansion. Healthcare Premiums combines
    # Pre-65 Healthcare Premium plus Medicare Part B, Part D, and Part G; LTC only appears when nonzero/configured.
    wellness_detail_cols = [
        COL['Wellness_Premiums'], COL['Wellness_Medical'], COL['Wellness_Dental'],
        COL['Wellness_Vision'], COL['Wellness_Rx_Otc'], COL['Wellness_Other']
    ]
    if include_ltc:
        wellness_detail_cols.append(COL['HC_LTC'])
    for col in wellness_detail_cols:
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # Trust detail (summary=Σ_Trust)
    for col in range(COL['H_Trust_WD'], COL['Σ_Trust']):
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # Roth detail (summary=Σ_Roth)
    for col in range(COL['H_Roth_WD'], COL['Σ_Roth']):
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # H/W IRA detail (summary=*_IRA_Tot). Conversion is an account outflow
    # but not a cash draw; it is shown here so IRA depletion reconciles to
    # starting balances plus growth instead of looking artificially low.
    for col in range(COL['H_IRA_RMD'], COL['H_IRA_Tot']):
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    for col in range(COL['W_IRA_RMD'], COL['W_IRA_Tot']):
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # Income detail (summary=Σ_Inc)
    for col in range(COL['Earned'], COL['Σ_Inc']):
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # Tax detail (summary=Total Taxes, in the Cash Bridge section) — Fed, State,
    # NIIT, IRMAA, Payroll, and LTCG are the components that sum to Total Taxes.
    for col in [COL['Fed'], COL['State'], COL['NIIT'], COL['IRMAA'], COL['Payroll'], COL['LTCG']]:
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    # HELOC Draw collapses under HELOC Bal
    ws.column_dimensions[get_column_letter(COL['HELOC_Draw'])].outlineLevel = 1

    # ── Data rows ─────────────────────────────────────────────────────────────
    for ri, row in enumerate(rows):
        r = ri + 3
        inc_total = (row['earned'] + row['h_ss'] + row['w_ss'] + row['pension'] +
                     row['wife_single_ann'] + row['wife_joint_ann'] +
                     row['h_single_ann'] + row['h_joint_ann'] +
                     row['note_princ'] + row['note_int'] + row['rmd_total'])
        heloc_pai       = row.get('heloc_interest', 0) + row.get('heloc_repayment_principal', 0)
        other_cash_need = row.get('other_cash_need_yr', 0)
        spend_total = (row['spend_base_yr']
                       + row.get('housing_total_yr', row.get('mortgage', 0) + row.get('rent_yr', 0))
                       + row.get('wellness_base_yr', 0) + row.get('ltc_prem_yr', 0)
                       + row['rec_extra'] + row['lump'] + other_cash_need + heloc_pai)
        trust_total = row.get('h_trust_wd', 0) + row.get('w_trust_wd', 0)
        roth_total  = row.get('h_roth_wd', 0)  + row.get('w_roth_wd', 0)
        h_ira_cash  = row.get('rmd_h', 0)       + row.get('h_ira_elective', 0)
        w_ira_cash  = row.get('rmd_w', 0)       + row.get('w_ira_elective', 0)
        h_ira_tot   = row.get('h_ira_total_outflow', h_ira_cash + row.get('h_ira_conversion', 0))
        w_ira_tot   = row.get('w_ira_total_outflow', w_ira_cash + row.get('w_ira_conversion', 0))
        # Cash bridge: RMDs are counted as income (inc_total includes rmd_total) so
        # only elective IRA draws appear in required_portfolio_draws.  Portfolio income
        # (dividends/interest) is a separate funding column.  Other cash needs (e.g.
        # home-purchase down payments) are folded into Σ Spend.
        required_portfolio_draws = (trust_total + row.get('hsa_wd', 0) + roth_total +
                                    row.get('h_ira_elective', 0) + row.get('w_ira_elective', 0))
        wd_total        = required_portfolio_draws + row.get('rmd_h', 0) + row.get('rmd_w', 0)
        total_tax       = row.get('total_tax', row.get('fed_tax', 0) + row.get('state_tax', 0) + row.get('niit', 0) + row.get('irmaa', 0) + row.get('payroll_tax', 0) + row.get('ltcg_tax', 0))
        total_cash_need = row.get('total_cash_need', spend_total + total_tax)
        income_funding  = inc_total
        portfolio_income = row.get('portfolio_income_cash', row.get('portfolio_income_total', 0))
        other_funding   = row.get('heloc_draw', 0)
        cash_bridge_gap = total_cash_need - income_funding - portfolio_income - other_funding - required_portfolio_draws

        vals = {
            COL['Year']:      row['year'],
            COL['H_Age']:     row['h_age'],
            COL['W_Age']:     row['w_age'],
            COL['Earned']:    row['earned'],
            COL['H_SS']:      row['h_ss'],
            COL['W_SS']:      row['w_ss'],
            COL['Pension']:   row['pension'],
            COL['W_Sgl']:     row['wife_single_ann'],
            COL['W_Jnt']:     row['wife_joint_ann'],
            COL['H_Sgl']:     row['h_single_ann'],
            COL['H_Jnt']:     row['h_joint_ann'],
            COL['Note']:      row['note_princ'] + row['note_int'],
            COL['RMD']:       row['rmd_total'],
            COL['Σ_Inc']:     inc_total,
            COL['Roth_Conv']: row['roth_conv'],
            COL['AGI']:       row['agi'],
            COL['Taxable']:   row['taxable_inc'],
            COL['Fed']:       row['fed_tax'],
            COL['State']:     row['state_tax'],
            COL['NIIT']:      row['niit'],
            COL['IRMAA']:     row.get('irmaa', 0),
            COL['Payroll']:   row.get('payroll_tax', 0),
            COL['LTCG']:      row.get('ltcg_tax', 0),
            COL['Spend_Base']:  row['spend_base_yr'],
            COL['Housing']:     row.get('housing_total_yr', row.get('mortgage', 0) + row.get('rent_yr', 0)),
            COL['Mort_PI']:     row.get('mortgage_payment_yr', 0),
            COL['Prop_Tax']:    row.get('real_estate_tax_yr', 0),
            COL['Housing_Utilities']: row.get('housing_utilities_yr', 0),
            COL['Home_Imp']:    row.get('home_improvement_yr', 0),
            COL['Housing_Maintenance']: row.get('housing_maintenance_yr', 0),
            COL['Housing_Other']: row.get('housing_other_yr', 0),
            **({COL['Rent_Det']: row.get('rent_yr', 0)} if include_rent else {}),
            COL['Wellness']:  row.get('wellness_base_yr', 0) + row.get('ltc_prem_yr', 0),
            COL['Wellness_Premiums']: row.get('wellness_premiums_yr', row.get('wellness_bridge_premium', 0) + row.get('medicare_base_premium', 0)),
            COL['Wellness_Medical']: row.get('wellness_medical_yr', 0),
            COL['Wellness_Dental']: row.get('wellness_dental_yr', 0),
            COL['Wellness_Vision']: row.get('wellness_vision_yr', 0),
            COL['Wellness_Rx_Otc']: row.get('wellness_rx_otc_yr', 0),
            COL['Wellness_Other']: row.get('wellness_other_yr', 0),
            **({COL['HC_LTC']: row.get('ltc_prem_yr', 0)} if include_ltc else {}),
            COL['Travel']:      row['rec_extra'],
            COL['Other']:       row['lump'] + other_cash_need,
            COL['HELOC_PAI']:   heloc_pai,
            COL['Σ_Spend']:     spend_total,
            COL['Total_Tax']: total_tax,
            COL['Total_Cash_Need']: total_cash_need,
            COL['Income_Funding']: income_funding,
            COL['Portfolio_Income']: portfolio_income,
            COL['Other_Funding']: other_funding,
            COL['Req_Portfolio_Draws']: required_portfolio_draws,
            COL['Cash_Bridge_Gap']: cash_bridge_gap,
            COL['H_Trust_WD']:row.get('h_trust_wd', 0),
            COL['W_Trust_WD']:row.get('w_trust_wd', 0),
            COL['Σ_Trust']:   trust_total,
            COL['HSA_WD']:    row.get('hsa_wd', 0),
            COL['H_Roth_WD']: row.get('h_roth_wd', 0),
            COL['W_Roth_WD']: row.get('w_roth_wd', 0),
            COL['Σ_Roth']:    roth_total,
            COL['H_IRA_RMD']: row.get('rmd_h', 0),
            COL['H_IRA_Elec']:row.get('h_ira_elective', 0),
            COL['H_IRA_Conv']:row.get('h_ira_conversion', 0),
            COL['H_IRA_Tot']: h_ira_tot,
            COL['W_IRA_RMD']: row.get('rmd_w', 0),
            COL['W_IRA_Elec']:row.get('w_ira_elective', 0),
            COL['W_IRA_Conv']:row.get('w_ira_conversion', 0),
            COL['W_IRA_Tot']: w_ira_tot,
            COL['HELOC_Draw']:row.get('heloc_draw', 0),
            COL['HELOC_Bal']: row.get('heloc_balance', 0),
            COL['Σ_WD']:      wd_total,
            COL['NW_Check']:  row['total_nw'],
        }
        for col_idx, val in vals.items():
            fmt = FMT_YEAR if col_idx == COL['Year'] else (
                  '0' if col_idx in (COL['H_Age'], COL['W_Age']) else FMT_DOLLAR)
            is_sub = col_idx in SUBTOTAL_COLS
            bg = LGRAY if is_sub else None
            write_cell(ws, r, col_idx, val, fmt=fmt, bold=is_sub, bg=bg,
                       align='right' if col_idx > 3 else 'center')


    # ── Home Sale Event Callout ───────────────────────────────────────────────
    if c.get('home_sale_yr') and c['home_sale_yr'] > 0:
        sale_row = next((rw for rw in rows if rw['year'] == c['home_sale_yr']), None)
        if sale_row and sale_row.get('home_sale_gross', 0) > 0:
            below = len(rows) + 5
            write_hdr(ws, below, 1, f"Home Sale — {c['home_sale_yr']}", BLUE, WHITE, span=6)
            below += 1
            for lbl, val, fmt in [
                ('Gross Sale Price',                  sale_row['home_sale_gross'],           FMT_DOLLAR),
                (f"Less: Selling Costs ({c['home_sell_cost_pct']*100:.0f}%)", sale_row.get('home_sale_costs',0), FMT_DOLLAR),
                ('Less: Mortgage Payoff',             sale_row['home_sale_mort_off'],        FMT_DOLLAR),
                ('Capital Gain (net of costs)',       sale_row['home_sale_gain'],            FMT_DOLLAR),
                ('Less: §121 Exclusion (MFJ)',        c['sec121'],                           FMT_DOLLAR),
                ('Taxable Gain',                      sale_row['home_sale_taxable'],         FMT_DOLLAR),
                ('LTCG Tax (bracketed 0/15/20%+NIIT)',sale_row['home_sale_tax'],             FMT_DOLLAR),
                ('Net Proceeds (basis-free in trust)',sale_row['home_sale_net'],             FMT_DOLLAR),
                (f"Deposited to: {c['home_sale_acct']}", '', None),
            ]:
                write_cell(ws, below, 1, lbl)
                if val != '':
                    write_cell(ws, below, 2, val, fmt=fmt,
                               bold=(lbl.startswith('Net')))
                below += 1

    qc('6. Cash Flow Projection', f'{len(rows)} rows, account-level WDs, collapsible groups',
       True, '')
