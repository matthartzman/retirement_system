"""Synthetic Vanguard-shaped 1099-B statement text for tests. Every name, account and figure is invented.

Shape follows plan section 14 (structure only): CORRECTED on every page, a summary by term and box, then per-security
blocks (``DESCRIPTION / CUSIP: <cusip> / Symbol: <symbol>``) with "Various" aggregate lines and lot lines, a repeated
long column header, ``Security total:`` / ``Totals:`` lines, and a redemption of a bond with a blank symbol.
"""
from __future__ import annotations

HEADINGS = {
    ("short", True): "Short-term transactions for covered tax lots - Report on Form 8949, Part I, with Box A checked",
    ("long", True): "Long-term transactions for covered tax lots - Report on Form 8949, Part II, with Box D checked",
}
SUMMARY_LABELS = {("short", True): "Short-term Box A", ("long", True): "Long-term Box D"}
COLUMN_HEADER = ("1a- Description 1b- Date acquired 1c- Date sold 1d- Proceeds 1e- Cost basis 1f- Accrued market discount (D) "
                 "or wash sale loss disallowed (W) 1g- Gain or loss Additional information")
PAGE_HEADER = "CORRECTED 2025 Tax Information Statement Statement date: 03/14/2026 Account Number: 99990042 Page {page} of 16"

# (term, covered) -> securities: (description, cusip, symbol, [line text, ...], [(proceeds, basis, discount, wash, gain), ...])
DEFAULT = {
    ("short", True): [
        ("ALPHA BETA CORP CL A", "111111111", "ABCD", [
            "09/10/25 15.500 2,280.50 (G) Various 2,300.25 -19.75 Total of 3 transactions",
            "10/15/25 8.000 400.00 (N) 07/01/25 500.00 60.00 W -40.00 Sale 1",
        ], [(2280.50, 2300.25, 0, 0, -19.75), (400.00, 500.00, 0, 60.00, -40.00)]),
    ],
    ("long", True): [
        ("LEMON INDEX FD ADM", "444444444", "LMNO", [
            "06/02/25 131.250 15,100.10 (G) Various 12,500.00 2,600.10 Total of 12 transactions",
            "06/03/25 5.000 600.00 (N) 11/30/23 590.00 12.00 D 22.00 Sale 1",
        ], [(15100.10, 12500.00, 0, 0, 2600.10), (600.00, 590.00, 12.00, 0, 22.00)]),
        ("ACME MUNI BD 4.0% 2025", "555555555", "", [
            "12/03/25 5,000.000 5,000.00 (G) 01/15/20 4,800.00 200.00 Redemption 1 K",
        ], [(5000.00, 4800.00, 0, 0, 200.00)]),
    ],
}


def totals(sections=DEFAULT):
    out = {}
    for key, secs in sections.items():
        cols = [0.0] * 5
        for *_, vals in secs:
            for v in vals:
                for i in range(5):
                    cols[i] += v[i]
        out[key] = tuple(round(c, 2) for c in cols)
    return out


def _m(v: float) -> str:
    return f"{v:,.2f}" if v >= 0 else f"-{abs(v):,.2f}"


def build_statement(sections=DEFAULT, *, summary=None, corrected=True, include_summary=True) -> str:
    summ = {**totals(sections), **(summary or {})}
    head = PAGE_HEADER if corrected else PAGE_HEADER.replace("CORRECTED ", "")
    lines = [head.format(page=1), "Form 1099-DIV Dividends and Distributions Total ordinary dividends 12.34"]
    if include_summary:
        lines += ["Form 1099-B Summary", "Proceeds Cost basis Accrued market discount Wash sale loss disallowed Net gain or loss"]
        for key, label in SUMMARY_LABELS.items():
            if key in summ:
                lines.append(f"{label} " + " ".join(_m(v) for v in summ[key]))
    lines.append("Form 1099-B Detail")
    page = 2
    for key, heading in HEADINGS.items():
        if key not in sections:
            continue
        lines += [heading, COLUMN_HEADER]
        for desc, cusip, symbol, rows, vals in sections[key]:
            lines.append(f"{desc} / CUSIP: {cusip} / Symbol: {symbol}")
            for i, row in enumerate(rows):
                lines.append(row)
                if i == 0 and len(rows) > 1:  # a page break inside the security block
                    lines += [head.format(page=page), heading + " (continued)", COLUMN_HEADER,
                              f"{desc} (cont'd) / CUSIP: {cusip} / Symbol: {symbol}"]
                    page += 1
            if symbol == "ABCD":
                lines.append("Original basis 450.00")
            lines.append("Security total: " + " ".join(_m(sum(v[j] for v in vals)) for j in range(5)))
        lines.append("Totals: " + " ".join(_m(v) for v in totals(sections)[key]))
    lines.append("This information is being furnished to the IRS. Legend: K = example code.")
    return "\n".join(lines) + "\n"
