"""Rental Properties sheet (WP12.7; design 2026-10-05 section 7).

Built only while the ``rental_property_income`` feature is on (the sheet is gated by its
SHEET_REGISTRY ``module_key``). Sections:

A summary by year · B by property and year (collapsible rows) · C depreciation schedule ·
D passive-loss ledger · E sale analysis · F metrics · G assumptions and warnings.

The figures come from ``rental_report_data`` (pure functions over the projection rows); this
module only writes them.
"""
from __future__ import annotations

import math

from .rental_report_data import (
    DepreciationLine,
    RentalReport,
    YearLine,
    build_report,
    last_active_year,
    rental_active,
)
from .workbook_common import (
    Alignment,
    BLUE,
    DGRAY,
    FMT_DOLLAR,
    FMT_PCT,
    FMT_YEAR,
    LGRAY,
    NAVY,
    RED,
    WHITE,
    get_column_letter,
    qc,
    section_title,
    write_cell,
    write_hdr,
)

SHEET = '40. Rental Properties'
SPAN = 15  # columns used by the widest table (section A)
TYPE_BG = 'D6E4F0'
GRP_BG = 'EAF2F8'

SUMMARY_HEADERS = (
    'Gross rent', 'Vacancy loss', 'Operating expenses', 'Mortgage interest', 'Depreciation',
    'Net Schedule E (before passive limit)', 'Passive loss allowed', 'Suspended loss (year end)',
    'Schedule E added to AGI', 'Estimated tax effect', 'Debt service (interest + principal)',
    'Improvements and purchase cash', 'Net cash flow', 'Sale proceeds deposited',
)


def _summary_values(y: YearLine) -> list[float]:
    return [y.gross_rent, y.vacancy, y.operating_expenses, y.interest, y.depreciation, y.schedule_e,
            y.loss_allowed, y.suspended, y.schedule_e_to_agi, y.tax_effect, y.debt_service,
            y.improvements_purchase, y.net_cash, y.sale_net_proceeds]


def _sum_values(lines) -> list[float]:
    vals = [sum(col) for col in zip(*[_summary_values(y) for y in lines])] if lines else [0.0] * len(SUMMARY_HEADERS)
    if lines:
        vals[7] = lines[-1].suspended
    return vals


def _note(ws, r: int, text: str, span: int = SPAN, lines: int | None = None, italic_fg: str = '595959') -> int:
    write_cell(ws, r, 1, text, fg=italic_fg, border=False, align='left')
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=span)
    ws.cell(row=r, column=1).alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    n = lines if lines is not None else max(1, math.ceil(len(text) / 170))
    ws.row_dimensions[r].height = 15 * n
    return r + 1


def _write_year_row(ws, r: int, label, values, *, bold=False, bg=None, year_fmt=False) -> None:
    write_cell(ws, r, 1, label, bold=bold, bg=bg, fmt=FMT_YEAR if year_fmt else None,
               align='center' if year_fmt else 'left')
    for i, v in enumerate(values):
        write_cell(ws, r, 2 + i, v, fmt=FMT_DOLLAR, bold=bold, bg=bg, align='right')


def _section_a(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'A. SUMMARY BY YEAR (all properties)', SPAN, bg=NAVY); r += 1
    r = _note(ws, r, 'Net cash flow = rent collected - operating expenses - debt service - improvements and purchase cash. '
                     'Taxes are produced by the plan\'s tax stages; "Estimated tax effect" is Schedule E added to AGI times the '
                     'year\'s effective marginal rate (federal, Social Security inclusion and NIIT; state tax not included). '
                     'Positive = more tax, negative = a tax saving.')
    write_hdr(ws, r, 1, 'Year', DGRAY, WHITE, size=9)
    for i, h in enumerate(SUMMARY_HEADERS):
        write_hdr(ws, r, 2 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 42
    r += 1
    last = last_active_year(rep.totals)
    for y in rep.totals:
        if last is not None and y.year > last:
            break
        _write_year_row(ws, r, y.year, _summary_values(y), year_fmt=True)
        r += 1
    _write_year_row(ws, r, 'Plan total', _sum_values(rep.totals), bold=True, bg=LGRAY)
    r += 1
    if last is not None and last < rep.totals[-1].year:
        r = _note(ws, r, f'No rental activity after {last}; later years are not listed.')
    return r + 1


def _section_b(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'B. BY PROPERTY AND YEAR (expand a property to see its years)', SPAN, bg=NAVY); r += 1
    r = _note(ws, r, 'Same columns as section A, one block per property. Schedule E added to AGI is the property\'s Schedule E net '
                     'less its opening suspended loss plus its closing suspended loss.')
    write_hdr(ws, r, 1, 'Property / Year', DGRAY, WHITE, size=9)
    for i, h in enumerate(SUMMARY_HEADERS):
        write_hdr(ws, r, 2 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 42
    r += 1
    for name, lines in rep.by_property.items():
        active = [y for y in lines if y.owned]
        _write_year_row(ws, r, name, _sum_values(active), bold=True, bg=TYPE_BG)
        r += 1
        for y in active:
            _write_year_row(ws, r, f'    {y.year}', _summary_values(y), bg=GRP_BG)
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1
    return r + 1


def _dep_header(ws, r: int, first: str) -> int:
    for i, h in enumerate((first, 'Depreciable basis (building + improvements)', 'Land (not depreciable)',
                           'Depreciation this year', 'Accumulated depreciation', 'Adjusted basis (year end)')):
        write_hdr(ws, r, 1 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 42
    return r + 1


def _section_c(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'C. DEPRECIATION SCHEDULE', SPAN, bg=NAVY); r += 1
    r = _note(ws, r, 'Straight line over the recovery period with the mid-month convention (IRS Publication 946 Table A-6). '
                     'Adjusted basis = purchase price and closing costs (for a converted home, the home\'s adjusted basis) + improvements - '
                     'accumulated depreciation; in a sale year it is the sale\'s adjusted basis. Depreciation accrues in loss years too.')
    r = _dep_header(ws, r, 'Property / Year')
    for name, lines in rep.depreciation.items():
        last: DepreciationLine = lines[-1]
        write_cell(ws, r, 1, name, bold=True, bg=TYPE_BG)
        for i, v in enumerate((last.depreciable_basis, last.land, sum(d.annual for d in lines),
                               last.accumulated, last.adjusted_basis)):
            write_cell(ws, r, 2 + i, v, fmt=FMT_DOLLAR, bold=True, bg=TYPE_BG, align='right')
        r += 1
        for d in lines:
            write_cell(ws, r, 1, f'    {d.year}' + (' (sale year)' if d.sold else ''), bg=GRP_BG)
            for i, v in enumerate((d.depreciable_basis, d.land, d.annual, d.accumulated, d.adjusted_basis)):
                write_cell(ws, r, 2 + i, v, fmt=FMT_DOLLAR, bg=GRP_BG, align='right')
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1
    return r + 1


def _section_d(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'D. PASSIVE-LOSS LEDGER', SPAN, bg=NAVY); r += 1
    r = _note(ws, r, 'A rental loss first offsets passive income; the rest is allowed up to the special allowance, which shrinks as income '
                     '(MAGI computed before passive losses) rises. Whatever is not allowed is suspended and carried forward by property, '
                     'and is released in full when the property is sold.')
    heads = ('Year', 'MAGI used for the limit', 'Special allowance available', 'Special allowance used',
             'Net Schedule E (before limit)', 'Schedule E added to AGI', 'Released at sale',
             'Suspended loss (year end)')
    for i, h in enumerate(heads):
        write_hdr(ws, r, 1 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 42
    r += 1
    last = last_active_year(rep.totals)
    for p in rep.passive_by_year:
        if last is not None and p['year'] > last:
            break
        write_cell(ws, r, 1, int(p['year']), fmt=FMT_YEAR, align='center')
        for i, k in enumerate(('magi', 'allowance_available', 'allowance_used', 'schedule_e_net',
                               'schedule_e_to_agi', 'released', 'suspended')):
            write_cell(ws, r, 2 + i, p[k], fmt=FMT_DOLLAR, align='right')
        r += 1
    r += 1
    for i, h in enumerate(('Property / Year', 'Opening carryforward', 'Current-year loss', 'Used within the limits',
                           'Released at sale', 'Closing carryforward')):
        write_hdr(ws, r, 1 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 30
    r += 1
    for name, lines in rep.ledger.items():
        if not lines:
            continue
        write_cell(ws, r, 1, name, bold=True, bg=TYPE_BG)
        vals = (lines[0].opening, sum(x.current_loss for x in lines), sum(x.used for x in lines),
                sum(x.released for x in lines), lines[-1].closing)
        for i, v in enumerate(vals):
            write_cell(ws, r, 2 + i, v, fmt=FMT_DOLLAR, bold=True, bg=TYPE_BG, align='right')
        r += 1
        for x in lines:
            write_cell(ws, r, 1, f'    {x.year}', bg=GRP_BG)
            for i, v in enumerate((x.opening, x.current_loss, x.used, x.released, x.closing)):
                write_cell(ws, r, 2 + i, v, fmt=FMT_DOLLAR, bg=GRP_BG, align='right')
            ws.row_dimensions[r].outlineLevel = 1
            ws.row_dimensions[r].hidden = True
            r += 1
    return r + 1


def _section_e(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'E. SALE ANALYSIS', SPAN, bg=NAVY); r += 1
    if not rep.sales:
        r = _note(ws, r, 'No rental property is sold inside the plan horizon.')
        return r + 1
    r = _note(ws, r, 'Gain = price - selling costs - adjusted basis. Unrecaptured section 1250 gain (up to the depreciation taken) is taxed at ordinary '
                     'rates capped at 25%; the rest is long-term capital gain. For a converted home the section 121 exclusion applies first, '
                     'only when the home passes the two-of-five-year test, and never to the depreciation. The tax lines are estimates: the '
                     'federal long-term tax and the state tax on the long-term part come from the plan\'s tax stages; the tax on the '
                     '1250 gain is the gain times the lesser of the year\'s marginal rate and 25%. When several sales fall in one year the '
                     'year\'s tax is shared by taxable gain.')
    write_hdr(ws, r, 1, 'Item', DGRAY, WHITE, size=9)
    for i, s in enumerate(rep.sales):
        write_hdr(ws, r, 2 + i, f'{s.name} ({s.year})', DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 30
    r += 1

    def line(label, fn, fmt=FMT_DOLLAR, bold=False, bg=None):
        nonlocal r
        write_cell(ws, r, 1, label, bold=bold, bg=bg)
        for i, s in enumerate(rep.sales):
            write_cell(ws, r, 2 + i, fn(s), fmt=fmt, bold=bold, bg=bg, align='right')
        r += 1

    line('Sale price', lambda s: s.price)
    line('Selling costs', lambda s: s.selling_costs)
    line('Mortgage paid off', lambda s: s.loan_payoff)
    line('Adjusted basis (cost + improvements - depreciation)', lambda s: s.adjusted_basis)
    line('   of which accumulated depreciation', lambda s: s.accumulated_depreciation)
    line('Gain or (loss)', lambda s: s.gain, bold=True)
    line('Unrecaptured section 1250 gain (taxed at ordinary rates, 25% cap)', lambda s: s.recapture_1250)
    line('Long-term capital gain taxed', lambda s: s.long_term_gain)
    line('Section 121 two-of-five-year test (converted home)',
         lambda s: 'n/a' if s.sec121_qualifies is None else ('Passes' if s.sec121_qualifies else 'Fails'), fmt=None)
    line('Section 121 exclusion applied', lambda s: s.sec121_excluded)
    line('Federal tax on the long-term gain', lambda s: s.tax_ltcg)
    line('State tax on the long-term gain', lambda s: s.tax_state)
    line('Estimated tax on the 1250 gain', lambda s: s.tax_1250_est)
    line('Estimated tax at sale', lambda s: s.tax_at_sale, bold=True, bg=LGRAY)
    line('Net proceeds before tax (price - costs - mortgage)', lambda s: s.net_proceeds)
    line('Net proceeds after estimated tax', lambda s: s.after_tax_proceeds, bold=True, bg=LGRAY)
    return r + 1


def _section_f(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'F. METRICS', SPAN, bg=NAVY); r += 1
    r = _note(ws, r, 'Measured in the first full year of rent. Cap rate = (rent collected - operating expenses) / property value. Net yield on value = '
                     '(rent collected - operating expenses - mortgage interest) / value. Cash-on-cash = (rent collected - operating expenses - debt service) / '
                     'equity (value - mortgage). After-tax hold-to-sale return = the yearly rate of return on the owner\'s cash: equity at the plan start, each '
                     'year\'s net cash flow after the estimated tax effect, and either the after-tax sale proceeds or, held to the plan end, the equity then '
                     '(no selling costs or tax). Not computed for a converted home (its mortgage belongs to the home).')
    for i, h in enumerate(('Property', 'Reference year', 'Property value', 'Net operating income', 'Cap rate',
                           'Net yield on value', 'Cash-on-cash', 'After-tax hold-to-sale return', 'Held until')):
        write_hdr(ws, r, 1 + i, h, DGRAY, WHITE, size=9)
    ws.row_dimensions[r].height = 30
    r += 1

    def pct(v):
        return 'n/a' if v is None else v

    for m in rep.metrics:
        write_cell(ws, r, 1, m.name, bold=True)
        write_cell(ws, r, 2, m.reference_year if m.reference_year else 'n/a', fmt=FMT_YEAR, align='center')
        write_cell(ws, r, 3, m.value if m.value is not None else 'n/a', fmt=FMT_DOLLAR, align='right')
        write_cell(ws, r, 4, m.noi if m.noi is not None else 'n/a', fmt=FMT_DOLLAR, align='right')
        for i, v in enumerate((m.cap_rate, m.net_yield, m.cash_on_cash, m.after_tax_return)):
            write_cell(ws, r, 5 + i, pct(v), fmt=FMT_PCT, align='right')
        write_cell(ws, r, 9, m.held_to)
        r += 1
    return r + 1


def assumption_lines(rep: RentalReport) -> list[tuple[str, list[str]]]:
    """Section G text in plain words: (heading, paragraphs). Dollar figures come from the
    reference data in force (``rep.constants``); nothing else is hard-coded here."""
    k = rep.constants
    allowance = (
        f"A rental loss first offsets passive income. Whatever is left is allowed up to a special allowance of ${k.special_allowance:,.0f} "
        f"(you must actively participate), which is cut by {k.phaseout_rate:.0%} of the amount your income (MAGI, computed before passive losses) "
        f"exceeds ${k.phaseout_start:,.0f} and is gone when it reaches the end of that range. The rest is suspended, carried forward by property, "
        f"and released when the property is sold in full."
        f" (Figures shown are for the first plan year and the first year's filing status, {rep.filing}.)")
    how = [
        "Schedule E: rent after vacancy, less operating expenses, mortgage interest and depreciation. A negative result is a loss.",
        f"Depreciation: straight line over {k.recovery_years:g} years with the mid-month convention (IRS Publication 946 Table A-6). "
        "Basis is (purchase price + closing costs) x (1 - land share); a converted home uses the lesser of its value and its adjusted basis at "
        "conversion. Capital improvements are depreciated separately from the month they are placed in service.",
        allowance,
        "Net rental income adds to AGI, to the MAGI used for IRMAA and the ACA credit, and to the net investment income base for NIIT "
        "(real-estate-professional status is not modelled).",
        f"Sale: amount realized = price - selling costs. Adjusted basis = cost basis + improvements - accumulated depreciation. "
        f"Unrecaptured section 1250 gain (up to the depreciation taken) is taxed at ordinary rates capped at {k.unrecaptured_1250_max_rate:.0%}; "
        "the rest is long-term capital gain. State tax treats the whole gain as ordinary income.",
        f"Converted homes only: the section 121 exclusion (${k.section_121_exclusion:,.0f} for the first-year filing status) applies when the home was owned and "
        f"used as the principal residence for at least {k.section_121_required_days} days in the {k.section_121_lookback_years} years before the sale, and never "
        "to depreciation taken. Failing the test, the whole gain is taxable. Every other home sale in the plan is computed as before.",
        "Converted homes: from the conversion, the rented share of the home's carrying costs (mortgage payment, real estate tax, utilities, "
        "maintenance and other housing budget lines) moves from spending to Schedule E, so nothing is counted twice; the principal part of the "
        "payment stays a financing flow.",
    ]
    defaults = [
        "Months: an improvement, a sale or a conversion entered without a month is placed in July (mid-year). Purchase and placed-in-service months default the same way.",
        "Married filing separately: if the spouses' living-apart status is not entered, they are assumed to have lived together all year, so the special allowance is $0 "
        "(a household input can change this).",
        "The MAGI for the passive-loss limit is the first-pass AGI before the withdrawal cascade, like the plan's other AGI-dependent deductions. Roth "
        "conversions are sized with the MAGI before the conversion; the final tax uses the actual MAGI and the difference is logged.",
        "A converted home uses one land share for both its value and its basis. Its residence start defaults to January five years before the conversion, "
        "conversion and sale dates are the 1st of the month, and its sale year and price are the plan's home sale year and price.",
        "At the first death the converted home's sale uses the stepped-up basis for gain; the loss basis is not stepped up. An estate sale after "
        "conversion keeps the step-up (no gain) and drops suspended losses.",
        "Depreciation uses the published Table A-6 percentages rounded to three decimals, straight line only (no section 1250 'additional depreciation' "
        "taxed as ordinary income). All depreciation is treated as taken after 6 May 1997.",
        "A section 1231 loss on a sale is treated as ordinary in the sale year; the five-year lookback and netting with other section 1231 gains are not modelled.",
        "Only a sale of the whole property, fully taxable and to an unrelated buyer, releases suspended losses.",
        "Other passive activities (such as K-1 income or losses) are not modelled. Amounts are not rounded to whole dollars.",
        "Property values, rents and expenses grow by the rates entered (default: the plan's inflation and home appreciation); a property bought in a plan year "
        "uses the purchase month for its first-year rent and expenses.",
        "The estimated tax effect and the estimated tax at sale are approximations built from the year's effective marginal rate; the exact tax is in the "
        "plan's tax stages (Lifetime Taxes). The state tax on the section 1250 part of a sale sits in that year's ordinary state tax and is not separated.",
    ]
    excluded = [
        "Like-kind (section 1031) exchanges, the qualified business income (QBI) deduction, real-estate-professional status, short-term rentals "
        "(average stay of 7 days or less) and personal use of a dwelling unit (section 280A).",
        "Refinancing events, entity (LLC or partnership) ownership, state-specific passive-loss rules, tenant-level detail.",
        "Splitting a property between the spouses, death handling beyond the step-up above, and turning a rental back into a personal home.",
        "Partial, installment and related-party sales, gifts, linking a loan to an existing liability row, and splitting sale proceeds across accounts.",
        "Section 121 refinements: the once-in-two-years rule, reduced exclusions for unforeseen circumstances, military or other suspensions of the five-year "
        "period, a check that both spouses used the home, and any non-qualified-use proration.",
    ]
    return [
        ("Tax preparer must verify before switch-on",
         ["The tax preparer must verify every constant and the Table A-6 percentages before the feature is switched on for anyone. "
          "They were entered from memory and have not been checked against IRS sources. Treat every number on this sheet as an estimate "
          "until they have been."]),
        ("How the numbers are built", how),
        ("Defaults and simplifications", defaults),
        ("Not modelled", excluded),
        ("Warnings for this plan", list(rep.warnings) or ["No warnings for this plan."]),
    ]


def _section_g(ws, r: int, rep: RentalReport) -> int:
    section_title(ws, r, 'G. ASSUMPTIONS AND WARNINGS', SPAN, bg=NAVY); r += 1
    for heading, paras in assumption_lines(rep):
        warn = heading.startswith(('Tax preparer', 'Warnings'))
        write_hdr(ws, r, 1, heading, RED if warn else BLUE, WHITE, span=SPAN)
        r += 1
        for p in paras:
            r = _note(ws, r, f'- {p}')
    return r + 1


def build_sheet_rental(ws, c, rows):
    """Rental Properties (sheet 40)."""
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.column_dimensions['A'].width = 44
    for col in range(2, SPAN + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16
    section_title(ws, 1, 'RENTAL PROPERTIES', SPAN, bg=BLUE)
    rep = build_report(c, rows) if rental_active(rows) else None
    if rep is None:
        write_cell(ws, 3, 1, 'No rental property is entered, so there is nothing to report. Add one on the Rental Properties page.',
                   border=False)
        ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=SPAN)
        qc(SHEET, 'Rental sheet built', True, 'no properties entered')
        return None
    r = _note(ws, 2, 'WARNING: the tax preparer must verify every constant and the Table A-6 percentages before this feature is switched on for anyone. '
                     'See section G for every simplification and exclusion.', italic_fg='C00000')
    r += 1
    for section in (_section_a, _section_b, _section_c, _section_d, _section_e, _section_f, _section_g):
        r = section(ws, r, rep)
    _checks(rep, rows)
    return rep


def _checks(rep: RentalReport, rows) -> None:
    total_cash = sum(y.net_cash for y in rep.totals)
    by_prop_cash = sum(sum(y.net_cash for y in lines) for lines in rep.by_property.values())
    qc(SHEET, 'Per-property net cash flow adds up to the plan total', abs(total_cash - by_prop_cash) < 1.0,
       f'total {total_cash:,.0f} vs properties {by_prop_cash:,.0f}')
    total_agi = sum(y.schedule_e_to_agi for y in rep.totals)
    by_prop_agi = sum(sum(y.schedule_e_to_agi for y in lines) for lines in rep.by_property.values())
    qc(SHEET, 'Per-property Schedule E added to AGI adds up to the plan total', abs(total_agi - by_prop_agi) < 1.0,
       f'total {total_agi:,.0f} vs properties {by_prop_agi:,.0f}')
