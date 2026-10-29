"""Synthetic E*Trade-shaped 1099-B statement text for tests. Every name, account and figure is invented.

The shape follows the structural notes in the realized-sales ledger plan (section 14): a summary of totals by term and
basis box, then per-security blocks (``CUSIP: <cusip> Symbol: <symbol><description>``) under four section headings, with
column headers repeated at page breaks and ``Total`` lines after each security.
"""
from __future__ import annotations

SECTION_HEADINGS = {
    ("short", True): "SHORT TERM TRANSACTIONS FOR WHICH BASIS IS REPORTED TO THE IRS - Report on Form 8949, Part I with Box A checked",
    ("short", False): "SHORT TERM TRANSACTIONS FOR WHICH BASIS IS NOT REPORTED TO THE IRS - Report on Form 8949, Part I with Box B checked",
    ("long", True): "LONG TERM TRANSACTIONS FOR WHICH BASIS IS REPORTED TO THE IRS - Report on Form 8949, Part II with Box D checked",
    ("long", False): "LONG TERM TRANSACTIONS FOR WHICH BASIS IS NOT REPORTED TO THE IRS - Report on Form 8949, Part II with Box E checked",
}
SUMMARY_LABELS = {
    ("short", True): "Short Term - Basis reported to the IRS (Box A)",
    ("short", False): "Short Term - Basis not reported to the IRS (Box B)",
    ("long", True): "Long Term - Basis reported to the IRS (Box D)",
    ("long", False): "Long Term - Basis not reported to the IRS (Box E)",
}
COLUMN_HEADER = ("Date Acquired Date Sold Proceeds Cost or Other Basis Accrued Market Discount "
                 "Wash Sale Loss Disallowed Gain/(Loss) Federal Tax Withheld Quantity")
PAGE_HEADER = "ACME SYNTHETIC SECURITIES 2025 Consolidated Tax Statement Account Number: XXXX-0042 Page {page} of 12"

# (term, covered) -> list of securities: (cusip, symbol, description, [lot, ...])
# lot = (acquired MM/DD/YY, sold MM/DD/YY, proceeds, basis, discount, wash, gain, withheld, quantity)
DEFAULT_SECTIONS = {
    ("short", True): [
        ("111111111", "ABCD", "Alpha Beta Corp Class A", [
            ("03/04/25", "09/10/25", 1500.00, 1400.00, 0.00, 0.00, 100.00, 0.00, 10.000),
            ("05/20/25", "09/10/25", 780.50, 900.25, 0.00, 0.00, -119.75, 0.00, 5.500),
        ]),
        ("222222222", "WXYZ", "Wexyz Holdings Inc", [
            ("07/01/25", "10/15/25", 400.00, 500.00, 0.00, 60.00, -40.00, 0.00, 8.000),
        ]),
    ],
    ("short", False): [
        ("333333333", "QRST", "Quest Rest Trust Units", [
            ("08/08/25", "11/12/25", 250.00, 200.00, 0.00, 0.00, 50.00, 0.00, 2.000),
        ]),
    ],
    ("long", True): [
        ("444444444", "LMNO", "Lemon Index Fund", [
            ("01/15/22", "06/02/25", 12000.00, 9000.00, 0.00, 0.00, 3000.00, 0.00, 100.000),
            ("11/30/23", "06/02/25", 3100.10, 3500.00, 12.00, 0.00, -387.90, 0.00, 31.250),
        ]),
    ],
    ("long", False): [
        ("555555555", "PQRS", "Pearls Quarters Co", [
            ("02/14/20", "12/03/25", 900.00, 1000.00, 0.00, 0.00, -100.00, 0.00, 3.000),
        ]),
    ],
}


def _money(v: float) -> str:
    s = f"{abs(v):,.2f}"
    return f"({s})" if v < 0 else s


def lot_line(lot) -> str:
    acq, sold, proceeds, basis, disc, wash, gain, withheld, qty = lot
    return f"{acq} {sold} {_money(proceeds)} {_money(basis)} {_money(disc)} {_money(wash)} {_money(gain)} {_money(withheld)} {qty:,.3f}"


def totals(sections=DEFAULT_SECTIONS):
    """(term, covered) -> (proceeds, basis, discount, wash, gain) summed from the lots, in dollars."""
    out = {}
    for key, secs in sections.items():
        cols = [0.0] * 5
        for _, _, _, lots in secs:
            for lot in lots:
                for i, idx in enumerate((2, 3, 4, 5, 6)):
                    cols[i] += lot[idx]
        out[key] = tuple(round(c, 2) for c in cols)
    return out


def summary_line(label: str, vals) -> str:
    return f"{label} " + " ".join(_money(v) for v in vals)


def build_statement(sections=DEFAULT_SECTIONS, *, summary=None, header_override=None, page_break_every=3,
                    include_summary=True, account_line=True) -> str:
    """Return statement text. ``summary`` overrides the control totals (dict key -> 5-tuple) for gap tests."""
    summ = totals(sections)
    if summary:
        summ = {**summ, **summary}
    lines = []
    if account_line:
        lines.append(PAGE_HEADER.format(page=1))
    lines.append("Form 1099-DIV Dividends and Distributions   Total ordinary dividends 123.45")
    lines.append("Form 1099-INT Interest Income  Interest income 6.78")
    if include_summary:
        lines.append("Form 1099-B Summary of proceeds, basis and gain/(loss)")
        lines.append("Description Proceeds Cost or Other Basis Accrued Market Discount Wash Sale Loss Disallowed Realized Gain/(Loss)")
        for key in SUMMARY_LABELS:
            if key in summ:
                lines.append(summary_line(SUMMARY_LABELS[key], summ[key]))
        lines.append(summary_line("Total Realized", [sum(v[i] for v in summ.values()) for i in range(5)]))
    lines.append("Form 1099-B Detail")
    page = 2
    n = 0
    for key, heading in SECTION_HEADINGS.items():
        if key not in sections:
            continue
        lines.append(heading)
        lines.append(COLUMN_HEADER)
        for cusip, symbol, desc, lots in sections[key]:
            lines.append(header_override or f"CUSIP: {cusip} Symbol: {symbol}{desc}")
            for lot in lots:
                n += 1
                if page_break_every and n % page_break_every == 0:
                    lines.append(PAGE_HEADER.format(page=page))
                    page += 1
                    lines.append(heading + " (continued)")
                    lines.append(COLUMN_HEADER)
                lines.append(lot_line(lot))
            tp = sum(l[2] for l in lots)
            lines.append(f"Total for {symbol} {_money(tp)}")
        lines.append(f"Total {key[0].title()} Term {_money(sum(v for v in [totals(sections)[key][0]]))}")
    lines.append("This information is being furnished to the Internal Revenue Service. Not a tax advice disclaimer.")
    return "\n".join(lines) + "\n"
