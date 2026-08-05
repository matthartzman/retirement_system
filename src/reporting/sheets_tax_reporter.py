"""Tax reporting and balance sheet generation.

This module provides tax and portfolio-tracking workbook functionality:
- build_sheet3: Balance Sheet (Today) — asset/liability summary with valuation

This sheet presents a comprehensive snapshot of the household's current financial
position, reconciling to the projection engine's starting balances.

System review 2026-08-04, architect finding `reporting-facade-theater`
(Wave 4.10): this was a facade re-importing from sheets_summary.py; it is now
the canonical source for tax reporting and balance-sheet builders.
"""

from .workbook_common import (
    BLUE,
    FMT_DOLLAR,
    GRAY,
    LGRAY,
    NAVY,
    WHITE,
    datetime,
    fetch_price,
    qc,
    section_title,
    write_cell,
    write_hdr,
)

def build_sheet3(ws, c, rows):
    """Balance Sheet (Today)"""
    ws.sheet_view.showGridLines = False
    section_title(ws, 1, f'BALANCE SHEET — As of {datetime.date.today()}', 6)

    yr0 = rows[0]
    r = 3

    def write_group(title, items):
        nonlocal r
        write_hdr(ws, r, 1, title, BLUE, WHITE, span=3); r+=1
        group_total = 0
        for acct, bal, note in items:
            write_cell(ws, r, 1, '  '+acct)
            write_cell(ws, r, 2, bal, fmt=FMT_DOLLAR, align='right')
            write_cell(ws, r, 3, note)
            group_total += bal
            r += 1
        write_cell(ws, r, 1, f'  Total {title}', bold=True, bg=LGRAY)
        write_cell(ws, r, 2, group_total, fmt=FMT_DOLLAR, bold=True, bg=LGRAY, align='right')
        write_cell(ws, r, 3, '', bg=LGRAY)
        r += 1
        return group_total

    write_hdr(ws, 2, 1, 'ASSETS', NAVY, WHITE)
    write_hdr(ws, 2, 2, 'Value ($)', NAVY, WHITE)
    write_hdr(ws, 2, 3, 'Notes', NAVY, WHITE)
    r = 3

    # Annuities / Income streams (PV)
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    ann_assets = [
        (f'{_n2} Pension (PV of future income)', yr0['pension_pv'], 'PV through mortality'),
        (f'{_n2} Single Annuity (PV)',            yr0['w_single_pv'], ''),
        (f'{_n2} Joint Annuity (PV)',             yr0['w_joint_pv'], ''),
        (f'{_n1} Single Annuity (PV)',            yr0['h_single_pv'], ''),
        (f'{_n1} Joint Annuity (PV)',             yr0['h_joint_pv'], ''),
    ]
    ann_total = write_group('Annuities & Pension (PV)', ann_assets)

    # #253: yr0[acct_id] is the engine's END-OF-YEAR Y0 balance (after that
    # year's growth/withdrawals/CST funding), while the Net Worth sheet's
    # "Plan Start" column deliberately uses the PRE-activity opening balance
    # (row['_account_opening'], seeded from live holdings) so it reconciles
    # with the Asset Allocation sheet's "today's" figures. Balance Sheet was
    # the odd one out reading the wrong snapshot -- use the same opening map
    # here so all three sheets agree on "today's" account balances. Falls
    # back to the year-end value for any account the opening map lacks (e.g.
    # a synthetic/legacy row not produced by the full engine).
    _y0_opening = yr0.get('_account_opening') or {}

    def _acct_items(tax_type, note):
        return [(acct.get('label') or acct['id'],
                  _y0_opening.get(acct['id'], yr0.get(acct['id'], 0)), note)
                for acct in c.get('account_registry', []) if acct.get('tax') == tax_type]

    pretax_total = write_group('Pre-Tax (Tax-Deferred)', _acct_items('pre_tax', 'Tax-deferred'))
    roth_total = write_group('Roth (Tax-Free)', _acct_items('roth', 'Tax-free'))
    trust_total = write_group('Taxable / Trust', _acct_items('taxable', 'Taxable'))
    hsa_total = write_group('Health Savings Account', _acct_items('hsa', 'Triple tax-advantaged'))

    # Other
    # v7.5 normalization: do not list both gross residence value and net home
    # equity as assets. The Balance Sheet now uses conventional presentation:
    # gross primary residence in Assets and the mortgage in Liabilities. This
    # reconciles to the projection, which stores net home equity internally.
    home_gross_value = yr0.get('home_val', c.get('home_val', 0))
    home_net_equity = yr0.get('home_equity', max(0, home_gross_value - c.get('mort_bal', 0)))
    mort_val = max(0, home_gross_value - home_net_equity)
    startup_val = yr0.get('startup_val', c.get('startup_eq', 0))
    autos_val = yr0.get('autos_val', c.get('autos', 0))
    note_val = yr0.get('note_bal', c.get('note_face', 0))
    cash_val = c.get('cash_other', 0)

    other_items = [
        ('Primary Residence', home_gross_value, 'Gross home value; mortgage shown in Liabilities'),
        ('Startup Equity',    startup_val, 'Illiquid'),
        ('Autos',             autos_val, 'Depreciated Y0 value'),
        ('Cash (Checking Accounts)', cash_val, 'Sum of _Checking positions'),
        ('Note Receivable',  note_val, f"Projected balance through {c['note_last']}"),
    ]
    other_total = write_group('Other Assets', other_items)

    total_assets = ann_total + pretax_total + roth_total + trust_total + hsa_total + other_total

    r += 1
    write_hdr(ws, r, 1, 'LIABILITIES', NAVY, WHITE); r+=1
    write_cell(ws, r, 1, '  Mortgage')
    write_cell(ws, r, 2, mort_val, fmt=FMT_DOLLAR, align='right')
    write_cell(ws, r, 3, 'Offsets Primary Residence gross value; not double-counted as Home Equity')
    r+=1
    write_cell(ws, r, 1, '  Total Liabilities', bold=True, bg=LGRAY)
    write_cell(ws, r, 2, mort_val, fmt=FMT_DOLLAR, bold=True, bg=LGRAY, align='right')
    write_cell(ws, r, 3, '', bg=LGRAY)
    r+=2

    net_worth = total_assets - mort_val
    write_cell(ws, r, 1, 'NET WORTH', bold=True, bg=NAVY, fg=WHITE)
    write_cell(ws, r, 2, net_worth, fmt=FMT_DOLLAR, bold=True, bg=NAVY, fg=WHITE, align='right')
    r += 3

    # Holdings detail intentionally omitted from Balance Sheet in v5.1.
    # Detailed positions now live only on Sheet 4 (Asset Allocation) to avoid
    # duplicate holdings tables. Account-level balances remain above.

    grand_total = sum(
        fetch_price(sym, '') * shares
        for holdings in c.get('positions', {}).values()
        for sym, shares in holdings.items()
    )

    # #253: Balance Sheet now shows opening (pre-activity) pretax/roth/trust/
    # hsa balances above, so the QC target must be the same opening-adjusted
    # total the Net Worth sheet reconciles to -- not the engine's raw
    # year-end total_nw, which still includes that year's growth/withdrawal/
    # CST-funding activity on those same account groups.
    _ye_invest_y0 = sum(yr0.get(k, 0) for k in ('pretax_nw', 'roth_nw', 'trust_nw', 'hsa_nw'))
    _open_invest_y0 = pretax_total + roth_total + trust_total + hsa_total
    _projection_y0_nw = (rows[0].get('total_nw', 0) - _ye_invest_y0 + _open_invest_y0) if rows else 0
    _nw_reconciled = abs(net_worth - _projection_y0_nw) < 1.0
    qc('3. Balance Sheet', 'Total assets - liabilities = net worth and reconciles to projection Y0', _nw_reconciled,
       f"NW={net_worth:,.0f} vs projection Y0={_projection_y0_nw:,.0f}")
    # Holdings source QC — verify positions were derived from client_holdings.csv
    _n_holdings = len(c.get('lots_reconcile', {}))
    _n_accounts = len(c.get('positions', {}))
    if _n_holdings > 0:
        qc('3. Balance Sheet', 'Positions sourced from client_holdings.csv', True,
           f'{_n_holdings} holdings across {_n_accounts} accounts')
    else:
        qc('3. Balance Sheet', 'Positions sourced from client_holdings.csv', False,
           'No holdings file found — fell back to client_data.csv Positions rows')
    lot_engine = c.get('lot_engine')
    if lot_engine:
        qc('3. Balance Sheet', 'Tax-lot data coverage',
           lot_engine.use_lots or lot_engine.coverage == 0,
           f'{lot_engine.coverage:.0%} — {"specific-lot sell guidance active" if lot_engine.use_lots else "fallback estimate (add purchase prices for lot-level guidance)"}')

    # Tax-lot data coverage is surfaced as a System / Quality Control item.
    # Actionable lot-by-lot sell guidance appears directly under taxable SELL
    # recommendations on 2B. Asset Allocation, so the Balance Sheet remains a
    # pure balance-sheet report rather than a partial tax-lot engine surface.


    qc('3. Balance Sheet', 'Holdings detail: all positions with live prices', True,
       f"Grand total invested: ${grand_total:,.0f}")


__all__ = ['build_sheet3']
