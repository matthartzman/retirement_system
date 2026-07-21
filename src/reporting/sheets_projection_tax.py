"""Lifetime Tax Projection sheet builder (Sheet 7).

Displays year-by-year tax analysis including:
- Filing status and age progression
- AGI, taxable income, and effective tax rates
- Federal, state, NIIT, payroll tax, and IRMAA components
- Lifetime tax totals and effective/marginal rate analysis
"""

from .workbook_common import (
    FMT_DOLLAR,
    FMT_INT,
    FMT_PCT,
    FMT_YEAR,
    NAVY,
    WHITE,
    get_column_letter,
    marginal_rate,
    qc,
    section_title,
    write_cell,
    write_hdr,
)


def build_sheet7(ws, c, rows):
    """Lifetime Tax Projection"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, 'LIFETIME TAX PROJECTION', 10)

    r = 2
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    hdrs = ['Year',f'{_n1} Age',f'{_n2} Age','Filing','AGI','Taxable Income',
            'Fed Tax','State Tax','NIIT','Payroll Tax','IRMAA',
            'Total Tax','Effective Rate','Marginal Rate']
    for i, h in enumerate(hdrs, 1):
        write_hdr(ws, r, i, h, NAVY, WHITE, size=9)
    r += 1

    lifetime_fed = 0; lifetime_state = 0; lifetime_niit = 0; lifetime_total = 0

    for row in rows:
        eff_rate = row['total_tax'] / row['agi'] if row['agi'] > 0 else 0
        marg = marginal_rate(row['taxable_inc'], row['year'], row['filing'], c['brk_inf'])
        vals = [row['year'], row['h_age'], row['w_age'], row['filing'],
                row['agi'], row['taxable_inc'],
                row['fed_tax'], row['state_tax'], row['niit'],
                row['payroll_tax'], row['irmaa'],
                row['total_tax'], eff_rate, marg]
        for col_idx, val in enumerate(vals, 1):
            if col_idx == 1:
                fmt = FMT_YEAR
            elif col_idx in (2, 3):  # ages
                fmt = FMT_INT
            elif col_idx in (4,): # filing
                fmt = None
            elif col_idx in (13, 14):
                fmt = FMT_PCT
            else:
                fmt = FMT_DOLLAR
            write_cell(ws, r, col_idx, val, fmt=fmt,
                       align='right' if col_idx>4 else 'center')
        lifetime_fed   += row['fed_tax']
        lifetime_state += row['state_tax']
        lifetime_niit  += row['niit']
        lifetime_total += row['total_tax']
        r += 1

    # Totals
    r += 1
    totals = [('Lifetime Federal Tax', lifetime_fed),
              (f'Lifetime State Tax ({c["state"][:2]})',   lifetime_state),
              ('Lifetime NIIT',        lifetime_niit),
              ('Lifetime Total Tax',   lifetime_total)]
    for label, val in totals:
        write_cell(ws, r, 1, label, bold=True, bg=NAVY, fg=WHITE)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        write_cell(ws, r, 7, val, fmt=FMT_DOLLAR, bold=True, bg=NAVY, fg=WHITE)
        r += 1

    for col in range(1, 15):
        ws.column_dimensions[get_column_letter(col)].width = 14

    qc('7. Lifetime Tax', 'Lifetime totals present', True,
       f"Total: ${lifetime_total:,.0f}")
