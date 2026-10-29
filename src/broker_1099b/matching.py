"""Match normalized 1099-B lines to ledger rows (plan 5.4, step 5.2). Pure: no database, no I/O.

Exact-match first, in passes, so the closest matches claim their rows before looser ones can:
  1. ``exact``      same symbol, same trade date, same shares, same acquisition date
  2. ``shares``     same symbol, same trade date, same shares (acquisition date differs)
  3. ``date``       same symbol and shares, trade date within ``date_tolerance_days`` (a Monarch-sourced row carries a
                    suggested trade date that the broker's can differ from)
  4. ``aggregate``  a line with no acquisition date ("Various"): two or more unclaimed rows of the symbol and trade
                    date whose shares add up to the line's quantity (many-to-one)
Fuzzy suggestions beyond this are deliberately left for later. Only confirmed taxable rows of the account are eligible.
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


def eligible(ledger: Iterable[Mapping[str, Any]], account: str) -> list[Mapping[str, Any]]:
    return [r for r in ledger if r["account"] == account and r["status"] == "confirmed" and r["tax_class"] == "taxable"]


def match_lines(lines: list[Mapping[str, Any]], ledger: Iterable[Mapping[str, Any]], *, account: str,
                date_tolerance_days: int = DATE_TOLERANCE_DAYS) -> dict[str, Any]:
    """``{matches: [{line_index, kind, how, sale_ids}], unmatched_lines: [index], unmatched_ledger: [sale_id]}``."""
    rows = sorted(eligible(ledger, account), key=lambda r: r["sale_id"])
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
