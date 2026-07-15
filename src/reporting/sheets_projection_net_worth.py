"""Net Worth Projection sheet builder (Sheet 5).

Displays year-by-year net worth accumulation across account types:
- Annuities & Pension products
- Pre-Tax accounts (401k, IRA, etc.)
- Roth accounts
- Trust/Taxable accounts
- HSA
- Other assets (home equity, startup value, autos, notes, cash)

Includes collapsible column groups for detail/subtotal toggling and
a summary block showing start vs. end values with change calculations.
"""

from .workbook_common import *


def build_sheet5(ws, c, rows):
    """Net Worth Projection"""
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = 'D3'

    # Headers
    COL_YEAR = 1; COL_HAGE = 2; COL_WAGE = 3
    # Groups: Annuities (4-8), Pre-Tax (10-12), Roth (14-15), Trust (17-18), HSA (20), Other (21-26), TOTAL (28)
    COLS = {
        'Year':1,'H Age':2,'W Age':3,
        'Pension PV':4,'W Single PV':5,'W Joint PV':6,'H Single PV':7,'H Joint PV':8,'Σ Ann':9,
        'PreTax_1':10,'PreTax_2':11,'PreTax_3':12,'Σ PreTax':13,
        'Roth_1':14,'Roth_2':15,'Σ Roth':16,
        'Trust_1':17,'Trust_2':18,'Σ Trust':19,
        'HSA_1':20,
        'Home Equity':21,'Next Housing Equity':22,'Startup':23,'Autos':24,'Note':25,'Cash':26,'Σ Other':27,
        'TOTAL NW':28,
    }

    def _account_slots(tax=None, acct_type=None, count=1):
        """Return workbook account slots in semantic owner/type order.

        Do not rely on c['*_ids'] ordering here. The registry is sorted for
        deterministic engine access, but that order can be alphabetical within a
        tax bucket (for example Husband_401k before Husband_IRA). Workbook detail
        columns need each label to travel with the exact account id/value.
        """
        registry = list(c.get('account_registry') or [])
        order = {'traditional_ira': 0, '401k': 1, '403b': 2, 'sep_ira': 3,
                 'roth_ira': 0, 'roth_401k': 1, 'trust': 0, 'taxable': 1, 'hsa': 0}
        candidates = []
        for acct in registry:
            if tax is not None and acct.get('tax') != tax:
                continue
            if acct_type is not None and acct.get('acct_type') != acct_type:
                continue
            candidates.append(acct)
        candidates.sort(key=lambda a: (a.get('owner_idx', 0), order.get(a.get('acct_type'), 99), str(a.get('id', ''))))

        def _owner_label(acct):
            owner = acct.get('owner_idx', 0)
            if owner == 0:
                return str(c.get('h_nick') or c.get('h_name') or 'Member 1')
            if owner == 1:
                return str(c.get('w_nick') or c.get('w_name') or 'Member 2')
            return str(acct.get('owner_name') or f'Owner {owner + 1}')

        def _kind_label(acct):
            typ = str(acct.get('acct_type') or '')
            if typ == 'traditional_ira':
                return 'IRA'
            if typ == '401k':
                return '401k'
            if typ == '403b':
                return '403b'
            if typ == 'sep_ira':
                return 'SEP IRA'
            if typ in ('roth_ira', 'roth_401k'):
                return 'Roth'
            if typ in ('trust', 'taxable'):
                return 'Trust'
            if typ == 'hsa':
                return 'HSA'
            return str(acct.get('label') or acct.get('id') or 'Account')

        slots = []
        for acct in candidates[:count]:
            aid = acct.get('id')
            slots.append((aid, f"{_owner_label(acct)} {_kind_label(acct)}"))
        while len(slots) < count:
            slots.append((None, ''))
        return slots

    def _opening_adjusted_group_values(row, _opening):
        """Return (pretax, roth, trust, hsa, total) net-worth group values for a row.

        For the plan-start row, when `_opening` current-holdings balances are
        available, this swaps the engine's year-end investment aggregates
        (pretax_nw/roth_nw/trust_nw/hsa_nw) out of total_nw and substitutes
        the opening current-holdings balances instead, so this row's figures
        reconcile with "today's" values shown on the Asset Allocation sheet.
        Used by both the main table's plan-start row and the summary block's
        "Plan Start" column so the two never disagree. Annuity PV, cash, and
        other assets are unaffected (no swap applies to them). Non-plan-start
        rows (including Plan End) pass `_opening=None` and get the engine's
        raw year-end values unchanged.
        """
        pretax = row.get('pretax_nw', 0)
        roth = row.get('roth_nw', 0)
        trust = row.get('trust_nw', 0)
        hsa = row.get('hsa_nw', 0)
        total = row.get('total_nw', 0)
        if _opening is not None:
            def _acct_bal(aid):
                if aid in _opening:
                    return _opening.get(aid, 0)
                return row.get(aid, 0)
            pretax_open = sum(_acct_bal(a) for a in c.get('pre_tax_ids', []))
            roth_open = sum(_acct_bal(a) for a in c.get('roth_ids', []))
            trust_open = sum(_acct_bal(a) for a in c.get('taxable_ids', []))
            hsa_open = sum(_acct_bal(a) for a in c.get('hsa_ids', []))
            _ye_invest = pretax + roth + trust + hsa
            _open_invest = pretax_open + roth_open + trust_open + hsa_open
            total = total - _ye_invest + _open_invest
            pretax, roth, trust, hsa = pretax_open, roth_open, trust_open, hsa_open
        return pretax, roth, trust, hsa, total

    pretax_slots = _account_slots(tax='pre_tax', count=3)
    roth_slots = _account_slots(tax='roth', count=2)
    trust_slots = _account_slots(tax='taxable', count=2)
    hsa_slots = _account_slots(tax='hsa', count=1)
    _n1 = str(c.get('h_nick') or c.get('h_name') or 'Member 1')
    _n2 = str(c.get('w_nick') or c.get('w_name') or 'Member 2')
    header_labels = {
        'H Age': f'{_n1} Age',
        'W Age': f'{_n2} Age',
        'W Single PV': f'{_n2} Single PV',
        'W Joint PV': f'{_n2} Joint PV',
        'H Single PV': f'{_n1} Single PV',
        'H Joint PV': f'{_n1} Joint PV',
        'PreTax_1': pretax_slots[0][1] or 'Pre-Tax 1',
        'PreTax_2': pretax_slots[1][1] or 'Pre-Tax 2',
        'PreTax_3': pretax_slots[2][1] or 'Pre-Tax 3',
        'Roth_1': roth_slots[0][1] or 'Roth 1',
        'Roth_2': roth_slots[1][1] or 'Roth 2',
        'Trust_1': trust_slots[0][1] or 'Trust 1',
        'Trust_2': trust_slots[1][1] or 'Trust 2',
        'HSA_1': hsa_slots[0][1] or 'HSA',
    }

    # Group header row
    r = 1
    write_hdr(ws, r, 1, 'Identifiers', DGRAY, WHITE, span=3)
    write_hdr(ws, r, 4, 'ANNUITIES & PENSION', BLUE, WHITE, span=6)
    write_hdr(ws, r, 10, 'PRE-TAX (IRA / 401k)', ORANGE, WHITE, span=4)
    write_hdr(ws, r, 14, 'ROTH', GREEN, WHITE, span=3)
    write_hdr(ws, r, 17, 'TRUSTS', '7030A0', WHITE, span=3)
    write_hdr(ws, r, 20, 'HSA', GOLD, '000000', span=1)
    write_hdr(ws, r, 21, 'OTHER ASSETS', DGRAY, WHITE, span=7)
    write_hdr(ws, r, 28, 'TOTAL', NAVY, WHITE, span=1)

    r = 2
    for name, col in COLS.items():
        label = header_labels.get(name, name)
        bg = LGRAY if 'Σ' in label or label=='TOTAL NW' else DGRAY
        fg = '000000' if bg==LGRAY else WHITE
        write_hdr(ws, r, col, label, bg, fg, size=9)

    # Data rows
    # Captured during the loop below for the plan-start row so the summary
    # block (Item 176) can reuse the exact same opening-adjusted values
    # instead of re-reading raw engine aggregates that skip the swap.
    plan_start_group_values = None
    for i, row in enumerate(rows):
        r = i + 3
        # Current-plan-year reconciliation with the Asset Allocation sheet.
        # `row[aid]` is the engine's *year-end* projected balance (after a full
        # year of growth/contributions/withdrawals). For the current plan year
        # that diverges from "Holdings Detail by Account" on sheet 4, which values
        # actual current share counts at live prices. The engine already captures
        # the plan-start balance in `row['_account_opening']`, seeded from the very
        # same positions x live-price basis (data_io c['balances']). So for the
        # current year only we display those opening balances for the individual
        # investment accounts, making both sheets agree on "today's" value.
        # Projected years (2027+) are untouched and keep their year-end balances.
        _opening = row.get('_account_opening') if row.get('year') == c.get('plan_start') else None

        def _acct_bal(aid, _row=row, _opening=_opening):
            if _opening is not None and aid in _opening:
                return _opening.get(aid, 0)
            return _row.get(aid, 0)

        ann_total  = (row['pension_pv']+row['w_single_pv']+row['w_joint_pv']+
                      row['h_single_pv']+row['h_joint_pv'])
        pretax_accounts = [aid for aid, _label in pretax_slots if aid]
        roth_accounts = [aid for aid, _label in roth_slots if aid]
        trust_accounts = [aid for aid, _label in trust_slots if aid]
        hsa_accounts = [aid for aid, _label in hsa_slots if aid]
        pretax_vals = [_acct_bal(a) for a in pretax_accounts] + [0, 0, 0]
        roth_vals = [_acct_bal(a) for a in roth_accounts] + [0, 0]
        trust_vals = [_acct_bal(a) for a in trust_accounts] + [0, 0]
        hsa_val = _acct_bal(hsa_accounts[0]) if hsa_accounts else 0
        pretax_tot = sum(_acct_bal(a) for a in c.get('pre_tax_ids', []))
        roth_tot = sum(_acct_bal(a) for a in c.get('roth_ids', []))
        trust_tot = sum(_acct_bal(a) for a in c.get('taxable_ids', []))
        cash_val = row.get('cash_other', c.get('cash_other', 0))
        other_tot  = (row.get('home_equity',0)+row.get('next_housing_equity',0)+
                      row.get('startup_val',0)+row.get('autos_val',0)+
                      row.get('note_bal',0)+cash_val)

        # Keep the TOTAL NW column footing to the values shown. When the current
        # year uses opening (current-holdings) balances for investment accounts,
        # swap the engine's year-end investment aggregates out of total_nw and the
        # opening aggregates in. Annuity PV, cash, and other assets are unchanged.
        # Shared with the summary block below via _opening_adjusted_group_values so
        # the "Plan Start" figures never disagree with this row.
        _adj_pretax, _adj_roth, _adj_trust, _adj_hsa, total_nw = _opening_adjusted_group_values(row, _opening)
        if row.get('year') == c.get('plan_start'):
            plan_start_group_values = (_adj_pretax, _adj_roth, _adj_trust, _adj_hsa, total_nw)

        vals = [row['year'], row['h_age'], row['w_age'],
                row['pension_pv'], row['w_single_pv'], row['w_joint_pv'],
                row['h_single_pv'], row['h_joint_pv'], ann_total,
                pretax_vals[0], pretax_vals[1], pretax_vals[2], pretax_tot,
                roth_vals[0], roth_vals[1], roth_tot,
                trust_vals[0], trust_vals[1], trust_tot,
                hsa_val,
                row.get('home_equity',0), row.get('next_housing_equity',0), row.get('startup_val',0),
                row.get('autos_val',0), row.get('note_bal',0), cash_val, other_tot,
                total_nw]

        for col_idx, val in enumerate(vals, 1):
            if col_idx in (1,2,3):
                fmt = FMT_YEAR if col_idx==1 else '0'
                align = 'center'
            else:
                fmt = FMT_DOLLAR_ZERO_BAND
                align = 'right'
            is_subtotal = col_idx in (9,13,16,19,27,28)
            bg = LGRAY if is_subtotal else (GRAY if col_idx==28 else None)
            bold = is_subtotal or col_idx==28
            write_cell(ws, r, col_idx, val, fmt=fmt, bold=bold, bg=bg, align=align)

    # Column widths
    ws.column_dimensions['A'].width = 7
    ws.column_dimensions['B'].width = 7
    ws.column_dimensions['C'].width = 7
    for col in range(4, 29):
        ws.column_dimensions[get_column_letter(col)].width = 13

    # Collapsible column groups for Sheet 5 (individual account detail vs subtotals)
    # Subtotal cols: Σ Ann=9, Σ PreTax=13, Σ Roth=16, Σ Trust=19
    # Group individual detail cols under each subtotal
    for col in range(2, 9):   # Ann detail under col 9
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    for col in range(10, 13): # PreTax detail under col 13
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    for col in range(14, 16): # Roth detail under col 16
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    for col in range(17, 19): # Trust detail under col 19
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1
    for col in range(21, 27): # Other detail under col 27
        ws.column_dimensions[get_column_letter(col)].outlineLevel = 1


    # Summary block
    r_data_end = len(rows) + 2
    r = r_data_end + 2
    write_hdr(ws, r, 1, 'Summary: Plan Start vs Plan End', NAVY, WHITE, span=5); r+=1
    write_hdr(ws, r, 1, 'Group', DGRAY, WHITE)
    write_hdr(ws, r, 2, f'Plan Start ({c["plan_start"]})', DGRAY, WHITE)
    write_hdr(ws, r, 3, f'Plan End ({c["plan_end"]})', DGRAY, WHITE)
    write_hdr(ws, r, 4, 'Change', DGRAY, WHITE)
    write_hdr(ws, r, 5, '% Change', DGRAY, WHITE)
    r += 1
    # Item 176: use the same opening-adjusted plan-start values shown in the
    # main table's plan-start row (not raw rows[0]['pretax_nw']/etc.), so the
    # summary's "Plan Start" column always reconciles with the top table for
    # Pre-Tax, Roth, Trust, HSA, and TOTAL. Falls back to raw engine values if
    # rows[0] somehow wasn't the plan-start row (e.g. `_opening` unavailable).
    if plan_start_group_values is not None:
        _start_pretax, _start_roth, _start_trust, _start_hsa, _start_total = plan_start_group_values
    else:
        _start_pretax, _start_roth, _start_trust, _start_hsa, _start_total = (
            rows[0]['pretax_nw'], rows[0]['roth_nw'], rows[0]['trust_nw'],
            rows[0]['hsa_nw'], rows[0]['total_nw'],
        )
    groups = [
        ('Annuities & Pension', rows[0]['ann_nw'],  rows[-1]['ann_nw']),
        ('Pre-Tax',             _start_pretax,      rows[-1]['pretax_nw']),
        ('Roth',                _start_roth,        rows[-1]['roth_nw']),
        ('Trusts',              _start_trust,       rows[-1]['trust_nw']),
        ('HSA',                 _start_hsa,         rows[-1]['hsa_nw']),
        ('Other Assets',        rows[0]['other_nw'],rows[-1]['other_nw']),
        ('TOTAL',               _start_total,       rows[-1]['total_nw']),
    ]
    for grp, start, end in groups:
        chg = end - start
        pct = chg/start if start else 0
        bold = (grp=='TOTAL')
        bg   = LGRAY if bold else None
        write_cell(ws, r, 1, grp, bold=bold, bg=bg)
        write_cell(ws, r, 2, start, fmt=FMT_DOLLAR_ZERO_BAND, bold=bold, bg=bg, align='right')
        write_cell(ws, r, 3, end,   fmt=FMT_DOLLAR_ZERO_BAND, bold=bold, bg=bg, align='right')
        write_cell(ws, r, 4, chg,   fmt=FMT_DOLLAR_ZERO_BAND, bold=bold, bg=bg, align='right')
        write_cell(ws, r, 5, pct,   fmt=FMT_PCT, bold=bold, bg=bg, align='right')
        r += 1

    qc('5. Net Worth Projection', f'Row count = {len(rows)} ({c["plan_start"]}-{c["plan_end"]})',
       len(rows)==c['plan_end']-c['plan_start']+1, '')
    qc('5. Net Worth Projection', 'All balances ≥ 0',
       all(r['total_nw']>=0 for r in rows), '')
