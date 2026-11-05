"""Match normalized 1099-B lines to ledger rows (plan 5.4, step 5.2). Pure: no database, no I/O.

Exact-match first, in passes, so the closest matches claim their rows before looser ones can:
  1. ``exact``      same symbol, same trade date, same shares, same acquisition date
  2. ``shares``     same symbol, same trade date, same shares (acquisition date differs)
  3. ``date``       same symbol and shares, trade date within ``date_tolerance_days`` (a Monarch-sourced row carries a
                    suggested trade date that the broker's can differ from)
  4. ``aggregate``  a line with no acquisition date ("Various"): two or more unclaimed rows of the symbol and trade
                    date whose shares add up to the line's quantity (many-to-one)
``suggest`` ranks candidate rows for the lines left unmatched; it is advisory only and never changes ``match_lines``.
Only confirmed taxable rows of the account are eligible.
"""
from __future__ import annotations

from datetime import date
from itertools import combinations
from typing import Any, Iterable, Mapping

SHARE_TOLERANCE = 0.001
DATE_TOLERANCE_DAYS = 3
_MAX_AGGREGATE_ROWS = 12


def _same_shares(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= SHARE_TOLERANCE


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def eligible(ledger: Iterable[Mapping[str, Any]], account: str, *, any_tax_class: bool = False) -> list[Mapping[str, Any]]:
    """Confirmed ledger rows of the account; a 1099-B covers taxable rows only, a Gains & Losses report any account."""
    return [r for r in ledger if r["account"] == account and r["status"] == "confirmed" and (any_tax_class or r["tax_class"] == "taxable")]


def match_lines(lines: list[Mapping[str, Any]], ledger: Iterable[Mapping[str, Any]], *, account: str,
                date_tolerance_days: int = DATE_TOLERANCE_DAYS, any_tax_class: bool = False) -> dict[str, Any]:
    """``{matches: [{line_index, kind, how, sale_ids}], unmatched_lines: [index], unmatched_ledger: [sale_id]}``."""
    rows = sorted(eligible(ledger, account, any_tax_class=any_tax_class), key=lambda r: r["sale_id"])
    free = {r["sale_id"]: r for r in rows}
    matches: dict[int, dict[str, Any]] = {}

    def sym(x: Mapping[str, Any]) -> str:
        return str(x.get("symbol") or "").upper()

    def claim(i: int, ids: list[int], kind: str, how: str) -> None:
        for s in ids:
            free.pop(s)
        matches[i] = {"line_index": i, "kind": kind, "how": how, "sale_ids": ids}

    def lot_pass(how: str, ok) -> None:
        for i, ln in enumerate(lines):
            if i in matches or not ln.get("symbol"):
                continue
            cands = [r for r in free.values() if sym(r) == sym(ln) and _same_shares(r["shares"], ln["quantity"]) and ok(ln, r)]
            if how == "date":
                cands.sort(key=lambda r: (_days(r["sale_date"], ln["date_sold"]),
                                          r.get("purchase_date") != ln.get("date_acquired"), r["sale_id"]))
            if cands:
                claim(i, [cands[0]["sale_id"]], "lot", how)

    has_acq = lambda ln: ln.get("date_acquired") is not None  # noqa: E731
    lot_pass("exact", lambda ln, r: r["sale_date"] == ln["date_sold"] and has_acq(ln) and r.get("purchase_date") == ln["date_acquired"])
    lot_pass("shares", lambda ln, r: r["sale_date"] == ln["date_sold"] and has_acq(ln))
    lot_pass("date", lambda ln, r: has_acq(ln) and _days(r["sale_date"], ln["date_sold"]) <= date_tolerance_days)

    for i, ln in enumerate(lines):
        if i in matches or not ln.get("symbol") or has_acq(ln):
            continue
        for window in (0, date_tolerance_days):
            pool = [r for r in free.values() if sym(r) == sym(ln) and _days(r["sale_date"], ln["date_sold"]) <= window]
            pick = _subset_summing_to(pool, ln["quantity"])
            if pick:
                claim(i, pick, "aggregate", "aggregate")
                break

    return {"matches": [matches[i] for i in sorted(matches)],
            "unmatched_lines": [i for i in range(len(lines)) if i not in matches],
            "unmatched_ledger": sorted(free)}


def _subset_summing_to(pool: list[Mapping[str, Any]], quantity: float) -> list[int] | None:
    """Ids of two or more rows whose shares sum to ``quantity`` (smallest ids first), else None."""
    pool = sorted(pool, key=lambda r: r["sale_id"])[:_MAX_AGGREGATE_ROWS]
    for size in range(2, len(pool) + 1):
        for combo in combinations(pool, size):
            if _same_shares(sum(r["shares"] for r in combo), quantity):
                return [r["sale_id"] for r in combo]
    return None


SUGGESTION_LIMIT = 3
SUGGESTION_MIN_SCORE = 50
_SUGGEST_DATE_DAYS = 30  # trade dates further apart than this earn no date points
# Points (total 100): symbol or CUSIP 40, shares 25, trade date 20, proceeds 15. A symbol match alone (40) never
# reaches SUGGESTION_MIN_SCORE; the candidate must also be close on at least one of shares, date or proceeds.


def _closeness(a: float, b: float) -> float:
    """1.0 when equal, falling linearly to 0.0 when they differ by 100 percent of the larger (never negative)."""
    top = max(abs(float(a)), abs(float(b)))
    return 1.0 if top == 0 else max(0.0, 1.0 - abs(float(a) - float(b)) / top)


def suggest(lines: list[Mapping[str, Any]], ledger: Iterable[Mapping[str, Any]], result: Mapping[str, Any], *,
            account: str, limit: int = SUGGESTION_LIMIT, any_tax_class: bool = False) -> dict[int, list[dict[str, Any]]]:
    """Advisory ranking for each unmatched line: up to ``limit`` unclaimed confirmed taxable rows of ``account`` with the
    same symbol (or CUSIP, for a line with no symbol), best first. ``{line_index: [{sale_id, score, reason, reasons}]}``;
    lines with no candidate over ``SUGGESTION_MIN_SCORE`` are omitted. Nothing here is applied or affects the match."""
    free = set(result["unmatched_ledger"])
    pool = [r for r in eligible(ledger, account, any_tax_class=any_tax_class) if r["sale_id"] in free]
    out: dict[int, list[dict[str, Any]]] = {}
    for i in result["unmatched_lines"]:
        ln = lines[i]
        want = str(ln.get("symbol") or "").upper() or (f"CUSIP-{ln['cusip']}".upper() if ln.get("cusip") else "")
        if not want:
            continue
        scored = []
        for r in pool:
            if str(r.get("symbol") or "").upper() != want:
                continue
            reasons = ["same symbol" if ln.get("symbol") else "same CUSIP"]
            pts = 40.0
            c = _closeness(r["shares"], ln["quantity"])
            pts += 25 * c
            reasons.append("same shares" if _same_shares(r["shares"], ln["quantity"]) else f"shares {r['shares']:g} vs {ln['quantity']:g}")
            d = _days(r["sale_date"], ln["date_sold"])
            pts += 20 * max(0.0, 1.0 - d / _SUGGEST_DATE_DAYS)
            reasons.append("same trade date" if d == 0 else f"trade date {d} day{'s' if d != 1 else ''} apart")
            pc = _closeness(r["proceeds"], ln["proceeds"])
            pts += 15 * pc
            reasons.append(f"proceeds within {round((1 - pc) * 100)}%" if pc < 1 else "same proceeds")
            scored.append({"sale_id": r["sale_id"], "score": round(pts), "reasons": reasons})
        scored = [c for c in scored if c["score"] >= SUGGESTION_MIN_SCORE]
        scored.sort(key=lambda c: (-c["score"], c["sale_id"]))
        for c in scored:
            c["reason"] = "; ".join(c["reasons"])
        if scored:
            out[i] = scored[:limit]
    return out
