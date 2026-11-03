"""Vanguard Brokerage tax information statement: 1099-B detail from extracted text (plan step 5.1a).

Layout (plan section 14, structure only): a summary by term and Form 8949 box, then detail under section headings
(Short / Long / Undetermined term x box), each security introduced by ``DESCRIPTION / CUSIP: <cusip> / Symbol:
<symbol>`` (explicit separators; the symbol can be blank for bonds and CDs). Two line shapes under a security:

* a "Various" line (an aggregate of N sales): ``date sold, quantity, proceeds [G|N], Various, basis, [amount D|W],
  gain, ... Total of N transactions``;
* a lot line with an explicit acquisition date (a wash-sale or basis-adjusted lot), same columns.

``D`` after an amount marks accrued market discount and ``W`` a wash-sale loss disallowed (they share one column); ``X`` / ``Z``
mark losses not allowed; "Sale" or "Redemption" (plus a number) is the additional information; a trailing single letter
is a form-legend code that is kept but not decoded. Losses carry a leading minus. A CORRECTED statement says so on every
page and carries a statement date, both read into ``meta``. ``Security total:`` / ``Totals:`` lines are skipped, and a
long column header repeats at page breaks.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .normalized import ParsedStatement, check_control_totals, is_money, parse_money, two_digit_year

BROKER = "vanguard"

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
_HEADER = re.compile(r"^(?P<desc>.*?)\s*/\s*CUSIP:\s*(?P<cusip>\S+)\s*/\s*Symbol:\s*(?P<symbol>.*)$", re.I)
_ACCOUNT = re.compile(r"Account\s*(?:Number|No\.?|#)\s*:?\s*([A-Za-z0-9*Xx\-]+)", re.I)
_YEAR = re.compile(r"\b(20\d{2})\s+Tax\s+Information\s+Statement", re.I)
_STATEMENT_DATE = re.compile(r"statement\s+date\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.I)
_TERM = re.compile(r"\b(short|long|undetermined|unknown)[\s-]*term\b", re.I)
_BOX_RE = re.compile(r"\b(?:Box|form)\s+([A-F])\b", re.I)
# Form 8949 box -> (term, covered). C and F are not reported on a 1099-B at all; G-I (undetermined term) are unverified.
_BOX = {"a": ("short", True), "b": ("short", False), "c": ("short", False),
        "d": ("long", True), "e": ("long", False), "f": ("long", False)}
_NOT_REPORTED = re.compile(r"\bnot\s+(?:been\s+)?reported\b|\bnoncovered\b", re.I)
_COVERED = re.compile(r"\bcovered\b|\breported\b", re.I)
_TOTAL_OF = re.compile(r"^Total\s+of\s+(\d+)\s+transactions?$", re.I)
_SKIP = ("security total", "totals", "total ")
_GAP_TOL = 0.01


def _norm(line: str) -> str:
    return " ".join(line.split())


def _iso(token: str, *, not_after: int | None = None) -> str | None:
    m = _DATE.match(token)
    if not m:
        return None
    mm, dd, yy = (int(g) for g in m.groups())
    return f"{two_digit_year(yy, not_after=not_after):04d}-{mm:02d}-{dd:02d}"


def _section(line: str) -> tuple[str, bool] | None:
    t = _TERM.search(line)
    if not t:
        return None
    word = t.group(1).lower()
    term = "unknown" if word in ("undetermined", "unknown") else word
    b = _BOX_RE.search(line)
    if b and term != "unknown" and b.group(1).lower() in _BOX:
        return _BOX[b.group(1).lower()]
    if _NOT_REPORTED.search(line):
        return term, False
    if _COVERED.search(line):
        return term, True
    return None


def _tail_money(tokens: list[str], n: int) -> list[float] | None:
    if len(tokens) >= n and all(is_money(t) for t in tokens[-n:]):
        return [parse_money(t) for t in tokens[-n:]]
    return None


def _split_adjustment(tok: str) -> tuple[str, str] | None:
    """``60.00W`` -> ("60.00", "W"); a bare amount -> None."""
    if len(tok) > 1 and tok[-1] in "DWdw" and is_money(tok[:-1]):
        return tok[:-1], tok[-1].upper()
    return None


def parse(text: str, *, known_symbols: Iterable[str] | None = None, account: str | None = None) -> ParsedStatement:
    st = ParsedStatement(broker=BROKER)
    acct_text = None
    section: tuple[str, bool] | None = None
    cusip = symbol = None
    description = ""
    in_detail = False
    st.meta["corrected"] = False
    blank: dict[str, int] = {}

    for no, raw in enumerate((text or "").splitlines(), start=1):
        line = _norm(raw)
        if not line:
            continue
        if "corrected" in line.lower() and re.search(r"\bCORRECTED\b", line):
            st.meta["corrected"] = True
        if "statement_date" not in st.meta and (m := _STATEMENT_DATE.search(line)):
            mm, dd, yyyy = (int(g) for g in m.groups())
            st.meta["statement_date"] = f"{yyyy:04d}-{mm:02d}-{dd:02d}"
        if acct_text is None and (m := _ACCOUNT.search(line)):
            acct_text = m.group(1)
        if "tax_year" not in st.meta and (m := _YEAR.search(line)):
            st.meta["tax_year"] = int(m.group(1))
        low = line.lower()
        if low.startswith(_SKIP) or low.startswith("original basis"):
            continue
        if m := _HEADER.match(line):
            in_detail = True
            cusip = m.group("cusip")
            symbol = (m.group("symbol").strip().split() or [""])[0].upper() or None
            description = re.sub(r"\(?cont[’']?d\.?\)?", "", m.group("desc"), flags=re.I).strip()
            if symbol is None:
                blank[description or cusip] = blank.get(description or cusip, 0) + 1
            continue
        tokens = line.split()
        if _DATE.match(tokens[0]):
            _line(st, no, line, tokens, section, cusip, symbol, description)
            continue
        sec = _section(line)
        if sec and not _tail_money(tokens, 5):
            section = sec
            continue
        if not in_detail and sec and (vals := _tail_money(tokens, 5)):
            st.summary[sec] = dict(zip(("proceeds", "basis", "market_discount", "wash_disallowed", "gain"), vals))

    acct = account or acct_text
    for r in st.rows:
        r["account"] = acct
        r["corrected"] = st.meta["corrected"]
        r["statement_date"] = st.meta.get("statement_date")
    st.meta["account"] = acct
    for name, n in sorted(blank.items()):
        st.warnings.append(f"{name}: no symbol on the statement (bond, CD or similar); kept by CUSIP and will not match a "
                           f"holdings symbol ({n} header(s)).")
    if not st.rows and not st.errors:
        st.errors.append({"line": 0, "error": "No 1099-B lines were found in the statement text."})
    st.control = check_control_totals(st.rows, st.summary)
    return st


def _line(st: ParsedStatement, no: int, line: str, tokens: list[str], section, cusip, symbol, description) -> None:
    def bad(why: str) -> None:
        st.errors.append({"line": no, "error": f"line {no}: {why}: {line[:80]}"})

    if section is None:
        return bad("sale line appears before any term / box heading")
    tok = list(tokens)
    pos = 0

    def take() -> str | None:
        nonlocal pos
        if pos >= len(tok):
            return None
        pos += 1
        return tok[pos - 1]

    def peek() -> str | None:
        return tok[pos] if pos < len(tok) else None

    sold = _iso(take() or "")
    qty, proceeds = take(), take()
    if not sold or not (qty and is_money(qty)) or not (proceeds and is_money(proceeds)):
        return bad("cannot read this line (expected date sold, quantity, proceeds)")
    if (peek() or "").strip("()").upper() in ("G", "N"):
        take()
    acq_tok = take() or ""
    various = acq_tok.lower() == "various"
    acquired = None if various else _iso(acq_tok, not_after=int(sold[:4]))
    if not various and acquired is None:
        return bad("cannot read the acquisition date (expected a date or 'Various')")
    basis_tok = take()
    if not (basis_tok and is_money(basis_tok)):
        return bad("cannot read this line (non-numeric cost basis)")
    market_discount = wash = 0.0
    nxt = peek() or ""
    amount = letter = None
    if adj := _split_adjustment(nxt):  # "60.00W"
        take()
        amount, letter = parse_money(adj[0]), adj[1]
    elif is_money(nxt) and len(tok) > pos + 1 and tok[pos + 1].upper() in ("D", "W"):  # "60.00 W"
        amount, letter = parse_money(take()), (take() or "").upper()
    if amount is not None:
        if letter == "D":
            market_discount = amount
        else:
            wash = amount
    gain_tok = take()
    if not (gain_tok and is_money(gain_tok)):
        return bad("cannot read this line (non-numeric gain or loss)")
    rest = tok[pos:]
    loss_not_allowed = None
    while rest and rest[0].upper() in ("X", "Z"):
        loss_not_allowed = rest.pop(0).upper()
    info = " ".join(rest)
    count = 1
    if m := re.search(r"Total\s+of\s+(\d+)\s+transactions?", info, re.I):
        count = int(m.group(1))
        info = (info[:m.start()] + info[m.end():]).strip()
    kind = "redemption" if re.search(r"\bredemption\b", info, re.I) else "sale"
    code = None
    if (cm := re.search(r"(?:^|\s)([A-Za-z])$", info)) and not re.search(r"\b(?:sale|redemption)$", info, re.I):
        code = cm.group(1).upper()
    row: dict[str, Any] = {
        "broker": BROKER, "source": "1099b", "line": no, "account": None, "symbol": symbol, "cusip": cusip,
        "description": description, "date_acquired": acquired, "date_sold": sold,
        "proceeds": parse_money(proceeds), "basis": parse_money(basis_tok), "market_discount": market_discount,
        "wash_disallowed": wash, "gain": parse_money(gain_tok), "fed_withheld": 0.0,
        "term": section[0], "covered": section[1], "quantity": parse_money(qty),
        "aggregated": various, "transaction_count": count, "kind": kind,
        "loss_not_allowed": loss_not_allowed, "legend_code": code,
    }
    footed = round(row["proceeds"] - row["basis"] + wash + market_discount, 2)
    if abs(footed - row["gain"]) > _GAP_TOL:
        st.warnings.append(f"line {no}: gain {row['gain']:,.2f} does not foot to proceeds - basis + wash + discount "
                           f"({footed:,.2f}); kept as printed.")
    st.rows.append(row)
