

"""
enterprise_build_pdf.py

Institutional-quality PDF report generator for the Retirement Plan System.

Features
--------
- Landscape orientation
- Minimal side margins
- One narrative section per workbook tab
- Automatic page fitting / adaptive font sizing
- Charts + data tables
- Institutional typography
- Executive summary
- Projection storytelling
- Integrated automatically into workbook builds

Integration
-----------
At the end of build_workbook.py:

    pass  # consolidated: from enterprise_build_pdf import build_enterprise_pdf
    build_enterprise_pdf(c, rows, mc_data)

Requirements
------------
pip install reportlab matplotlib openpyxl pillow
"""

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, Image, KeepTogether
)
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.units import inch

import matplotlib.pyplot as plt
from pathlib import Path
import tempfile
import math


PAGE_W, PAGE_H = landscape(letter)

LEFT = 0.32 * inch
RIGHT = 0.32 * inch
TOP = 0.42 * inch
BOTTOM = 0.38 * inch

CONTENT_W = PAGE_W - LEFT - RIGHT


def _styles():
    s = getSampleStyleSheet()

    s['Title'].fontName = 'Helvetica-Bold'
    s['Title'].fontSize = 22
    s['Title'].leading = 28

    s['Heading1'].fontName = 'Helvetica-Bold'
    s['Heading1'].fontSize = 16
    s['Heading1'].leading = 20

    s['BodyText'].fontName = 'Helvetica'
    s['BodyText'].fontSize = 9.5
    s['BodyText'].leading = 12

    return s


def _fmt(v):
    if isinstance(v, (int, float)):
        if abs(v) >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:,.0f}"
    return str(v)


def _chart_networth(rows, outpath):
    yrs = [r['year'] for r in rows]
    nw = [r.get('total_nw', 0) for r in rows]

    plt.figure(figsize=(10, 3.8))
    plt.plot(yrs, nw, linewidth=2)
    plt.title("Projected Net Worth")
    plt.xlabel("Year")
    plt.ylabel("Net Worth")
    plt.tight_layout()
    plt.savefig(outpath, dpi=180)
    plt.close()


def _adaptive_table(data, width):
    cols = len(data[0])
    colw = width / cols

    t = Table(data, repeatRows=1, colWidths=[colw] * cols)

    fs = 8
    if cols >= 8:
        fs = 7
    if cols >= 11:
        fs = 6.5

    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F2937')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), fs),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor('#F9FAFB')
        ]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return t


def _section_header(story, styles, title, subtitle=None):
    story.append(Paragraph(title, styles['Heading1']))
    if subtitle:
        story.append(Paragraph(subtitle, styles['BodyText']))
    story.append(Spacer(1, 0.08 * inch))
    story.append(HRFlowable(width="100%"))
    story.append(Spacer(1, 0.12 * inch))


def build_enterprise_pdf(c, rows, mc_data, out_path='output/retirement_plan.pdf'):

    styles = _styles()

    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title='Retirement Plan',
        author='Retirement Plan System'
    )

    story = []

    # COVER PAGE
    story.append(Paragraph("Institutional Retirement Plan", styles['Title']))
    story.append(Spacer(1, 0.18 * inch))

    intro = """
    This report summarizes retirement sustainability, tax strategy,
    portfolio structure, lifetime cash flow, estate outcomes, and
    Monte Carlo simulation results across the full planning horizon.
    """

    story.append(Paragraph(intro, styles['BodyText']))
    story.append(Spacer(1, 0.25 * inch))

    # EXECUTIVE KPI TABLE
    final_nw = rows[-1].get('total_nw', 0)
    lifetime_tax = sum(r.get('total_tax', 0) for r in rows)

    kpi_data = [
        ['Metric', 'Value'],
        ['Terminal Net Worth', _fmt(final_nw)],
        ['Lifetime Taxes', _fmt(lifetime_tax)],
        ['Monte Carlo Success', f"{mc_data.get('success_rate', 0)*100:.1f}% (95% CI {mc_data.get('success_rate_ci_low', 0)*100:.1f}%–{mc_data.get('success_rate_ci_high', 0)*100:.1f}%)"],
        ['Plan Horizon', f"{len(rows)} years"],
    ]

    story.append(_adaptive_table(kpi_data, CONTENT_W * 0.45))

    story.append(PageBreak())

    # NET WORTH SECTION
    _section_header(
        story,
        styles,
        "1. Net Worth Projection",
        "Long-term balance sheet evolution under baseline assumptions."
    )

    tmp_chart = Path(tempfile.gettempdir()) / "nw_chart.png"
    _chart_networth(rows, tmp_chart)

    story.append(Image(str(tmp_chart), width=9.5 * inch, height=3.6 * inch))
    story.append(Spacer(1, 0.14 * inch))

    table_rows = [['Year', 'Pre-Tax', 'Roth', 'Taxable', 'Net Worth']]

    for r in rows[:20]:
        table_rows.append([
            r.get('year'),
            _fmt(r.get('pretax_nw', 0)),
            _fmt(r.get('roth_nw', 0)),
            _fmt(r.get('trust_nw', 0)),
            _fmt(r.get('total_nw', 0)),
        ])

    story.append(_adaptive_table(table_rows, CONTENT_W))

    story.append(PageBreak())

    # CASH FLOW SECTION
    _section_header(
        story,
        styles,
        "2. Cash Flow & Spending",
        "Income, taxes, and retirement spending sustainability."
    )

    cf_rows = [[
        'Year', 'Earned', 'SS', 'Taxes',
        'Spending', 'Ending NW'
    ]]

    for r in rows[:20]:
        cf_rows.append([
            r.get('year'),
            _fmt(r.get('earned', 0)),
            _fmt(r.get('ss_income', 0)),
            _fmt(r.get('total_tax', 0)),
            _fmt(r.get('total_spend', 0)),
            _fmt(r.get('total_nw', 0)),
        ])

    story.append(_adaptive_table(cf_rows, CONTENT_W))

    story.append(PageBreak())

    # MONTE CARLO
    _section_header(
        story,
        styles,
        "3. Monte Carlo & Risk",
        "Probability-based sustainability analysis."
    )

    mc_text = f"""
    The plan achieved a Monte Carlo success rate of
    <b>{mc_data.get('success_rate',0)*100:.1f}%</b>
    (95% CI {mc_data.get('success_rate_ci_low',0)*100:.1f}%–{mc_data.get('success_rate_ci_high',0)*100:.1f}%).
    Simulations incorporate stochastic market paths, asset-class covariance where available,
    inflation variability, wellness shocks, and portfolio volatility assumptions.
    """

    story.append(Paragraph(mc_text, styles['BodyText']))
    story.append(Spacer(1, 0.12 * inch))

    # ASSET ALLOCATION
    story.append(PageBreak())

    _section_header(
        story,
        styles,
        "4. Asset Allocation & Rebalancing",
        "Strategic portfolio structure and optimization diagnostics."
    )

    alloc_rows = [
        ['Asset Class', 'Target'],
        ['US Equity', '55%'],
        ['International Equity', '15%'],
        ['Fixed Income', '20%'],
        ['Real Assets', '5%'],
        ['Cash', '5%'],
    ]

    story.append(_adaptive_table(alloc_rows, CONTENT_W * 0.55))

    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(
        """
        Rebalancing policy prioritizes tax-advantaged accounts,
        minimizes unnecessary capital gains realization,
        and supports withdrawal sustainability throughout retirement.
        """,
        styles['BodyText']
    ))

    # TAX STRATEGY
    story.append(PageBreak())

    _section_header(
        story,
        styles,
        "5. Tax Strategy",
        "Lifetime tax minimization and Roth conversion analysis."
    )

    story.append(Paragraph(
        """
        The engine evaluates federal taxation, state taxation,
        IRMAA thresholds, capital gains treatment,
        and dynamic Roth conversion opportunities.
        """,
        styles['BodyText']
    ))

    # ESTATE
    story.append(PageBreak())

    _section_header(
        story,
        styles,
        "6. Estate & Legacy Planning",
        "Projected wealth transfer and beneficiary analysis."
    )

    story.append(Paragraph(
        """
        Estate projections incorporate beneficiary transitions,
        inherited retirement accounts, trust structures,
        and long-term wealth preservation scenarios.
        """,
        styles['BodyText']
    ))

    # APPENDIX
    story.append(PageBreak())

    _section_header(
        story,
        styles,
        "Appendix",
        "Methodology, assumptions, and audit metadata."
    )

    appendix = [
        ['Item', 'Value'],
        ['Projection Rows', len(rows)],
        ['MC Simulations', mc_data.get('simulations', 'N/A')],
        ['Engine Version', c.get('version', 'Institutional')],
    ]

    story.append(_adaptive_table(appendix, CONTENT_W * 0.6))

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.drawRightString(
            PAGE_W - RIGHT,
            0.18 * inch,
            f"Page {doc.page}"
        )
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=_footer,
        onLaterPages=_footer
    )

    print(f"PDF created: {out_path}")

