"""E*Trade (Morgan Stanley) consolidated tax statement: 1099-B detail from extracted text (plan step 5.1).

Layout (plan section 14, structure only): a 1099-B summary of totals by term and basis box, then detail under four
headings (Short/Long Term x basis reported or not), each security introduced by ``CUSIP: <cusip> Symbol:
<symbol><description>`` (symbol and description run together), then one line per lot sold: date acquired, date sold
(MM/DD/YY), proceeds, cost basis, accrued market discount, wash-sale loss disallowed, gain/(loss), federal tax
withheld, quantity. Page breaks repeat headers; ``Total`` lines are skipped. The summary is the control total.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .normalized import ParsedStatement, check_control_totals, is_money, parse_money, two_digit_year

BROKER = "etrade"

_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{2})$")
_CUSIP_LINE = re.compile(r"^CUSIP:\s*(\S+)\s+Symbol:\s*(.*)$", re.I)
_ACCOUNT = re.compile(r"Account\s*(?:Number|No\.?|#)\s*:?\s*([A-Za-z0-9*Xx\-]+)", re.I)
_YEAR = re.compile(r"\b(20\d{2})\s+Consolidated\s+Tax\s+Statement", re.I)
_TERM = re.compile(r"\b(short|long|unknown|undetermined)[\s-]*term\b", re.I)
_BOX = {"a": ("short", True), "b": ("short", False), "d": ("long", True), "e": ("long", False)}
_BOX_RE = re.compile(r"\bBox\s+([A-F])\b", re.I)
_NOT_REPORTED = re.compile(r"\bnot\s+(?:been\s+)?reported\b", re.I)
_REPORTED = re.compile(r"\breported\b", re.I)
_LOT_MONEY_COLUMNS = ("proceeds", "basis", "market_discount", "wash_disallowed", "gain", "fed_withheld")


def _norm(line: str) -> str:
    return " ".join(line.split())


def split_symbol(rest: str, known_symbols: Iterable[str] | None) -> tuple[str | None, str, str]:
    """Split ``<symbol><description>`` -> (symbol, description, source). ``source`` is ``master`` (matched the
    security master), ``guessed`` (leading capitals before a capitalised word) or ``blank``."""
    rest = rest.strip()
    if not rest:
        return None, "", "blank"
    known = {s.upper() for s in (known_symbols or ())}
    for n in range(min(len(rest), 10), 0, -1):  # longest known symbol first
        cand = rest[:n]
        if cand.upper() in known and _word_boundary(rest, n):
            return cand.upper(), rest[n:].strip(), "master"
    m = re.match(r"^([A-Z][A-Z.\-]*)", rest)
    if not m:
        return None, rest, "blank"
    run = m.group(1)
    after = rest[len(run):]
    if after[:1].islower() and len(run) > 1:      # "ZZZZZebra" -> the last capital starts the description
        run, after = run[:-1], rest[len(run) - 1:]
    return run, after.strip(), "guessed"


def _word_boundary(rest: str, n: int) -> bool:
    nxt = rest[n:n + 2]
    if not nxt or not nxt[0].isalpha():
        return True
    return nxt[0].isupper() and len(nxt) == 2 and nxt[1].islower()


def _iso(token: str, *, not_after: int | None = None) -> str | None:
    m = _DATE.match(token)
    if not m:
        return None
    mm, dd, yy = (int(g) for g in m.groups())
    return f"{two_digit_year(yy, not_after=not_after):04d}-{mm:02d}-{dd:02d}"


def _section(line: str) -> tuple[str, bool] | None:
    """(term, covered) for a section heading line, else None. Boxes beat the wording when both are present."""
    t = _TERM.search(line)
    if not t:
        return None
    term = "unknown" if t.group(1).lower() in ("unknown", "undetermined") else t.group(1).lower()
    b = _BOX_RE.search(line)
    if b and b.group(1).lower() in _BOX:
        return _BOX[b.group(1).lower()]
    if not _REPORTED.search(line):
        return None
    return term, not _NOT_REPORTED.search(line)


def _tail_money(tokens: list[str], n: int) -> list[float] | None:
    if len(tokens) >= n and all(is_money(t) for t in tokens[-n:]):
        return [parse_money(t) for t in tokens[-n:]]
    return None


def parse(text: str, *, known_symbols: Iterable[str] | None = None, account: str | None = None) -> ParsedStatement:
    st = ParsedStatement(broker=BROKER)
    lines = (text or "").splitlines()
    acct_text = None
    section: tuple[str, bool] | None = None
    sec_line = 0
    cusip = symbol = None
    description = ""
    guessed: dict[str, int] = {}
    in_detail = False

    for no, raw in enumerate(lines, start=1):
        line = _norm(raw)
        if not line:
            continue
        if acct_text is None and (m := _ACCOUNT.search(line)):
            acct_text = m.group(1)
        if "tax_year" not in st.meta and (m := _YEAR.search(line)):
            st.meta["tax_year"] = int(m.group(1))
        if line.lower().startswith("total"):
            continue
        if m := _CUSIP_LINE.match(line):
            in_detail = True
            cusip = m.group(1)
            symbol, description, source = split_symbol(m.group(2), known_symbols)
            if source == "guessed":
                guessed[symbol] = guessed.get(symbol, 0) + 1
            continue
        tokens = line.split()
        first_date = _DATE.match(tokens[0]) if tokens else None
        if first_date:
            _lot(st, no, line, tokens, section, cusip, symbol, description)
            continue
        sec = _section(line)
        if sec and not _tail_money(tokens, 5):
            section, sec_line = sec, no
            continue
        if not in_detail and sec and (vals := _tail_money(tokens, 5)):
            st.summary[sec] = dict(zip(("proceeds", "basis", "market_discount", "wash_disallowed", "gain"), vals))

    acct = account or acct_text
    for r in st.rows:
        r["account"] = acct
    st.meta["account"] = acct
    for sym, n in sorted(guessed.items()):
        st.warnings.append(f"Symbol {sym} was guessed from the header text (not in the security master); check it ({n} header(s)).")
    if not st.rows and not st.errors:
        st.errors.append({"line": 0, "error": "No 1099-B lot lines were found in the statement text."})
    st.control = check_control_totals(st.rows, st.summary)
    return st


def _lot(st: ParsedStatement, no: int, line: str, tokens: list[str], section, cusip, symbol, description) -> None:
    def bad(why: str) -> None:
        st.errors.append({"line": no, "error": f"line {no}: {why}: {line[:80]}"})

    if len(tokens) != 2 + len(_LOT_MONEY_COLUMNS) + 1 or not _DATE.match(tokens[1]):
        return bad("cannot read this lot line (expected 2 dates, 6 amounts, quantity)")
    if section is None:
        return bad("lot line appears before any term / basis-reported heading")
    money = tokens[2:-1]
    if not all(is_money(t) for t in money) or not is_money(tokens[-1]):
        return bad("cannot read this lot line (non-numeric amount)")
    sold = _iso(tokens[1])
    acquired = _iso(tokens[0], not_after=int(sold[:4]))
    vals = dict(zip(_LOT_MONEY_COLUMNS, (parse_money(t) for t in money)))
    row: dict[str, Any] = {
        "broker": BROKER, "source": "1099b", "line": no, "account": None, "symbol": symbol, "cusip": cusip,
        "description": description, "date_acquired": acquired, "date_sold": sold,
        "proceeds": vals["proceeds"], "basis": vals["basis"], "market_discount": vals["market_discount"],
        "wash_disallowed": vals["wash_disallowed"], "gain": vals["gain"], "fed_withheld": vals["fed_withheld"],
        "term": section[0], "covered": section[1], "quantity": parse_money(tokens[-1]),
    }
    footed = round(vals["proceeds"] - vals["basis"] + vals["wash_disallowed"] + vals["market_discount"], 2)
    if abs(footed - vals["gain"]) > 0.01:
        st.warnings.append(f"line {no}: gain {vals['gain']:,.2f} does not foot to proceeds - basis + wash + discount "
                           f"({footed:,.2f}); kept as printed.")
    st.rows.append(row)
