"""The Realized gains and losses view (sales ledger plan 9.2): confirmed ledger sales in a date window, grouped by
symbol or account with their lots, plus an optional display-only estimate for sales still waiting for lots.

``build`` is pure. The estimate (plan 14, answer 7) values an unmatched Monarch sale at its parsed amount with a
first-in-first-out basis from the account's current holdings lots. It is never written to the ledger, never feeds
tax, the projection or the daily log, and is reported apart from the confirmed totals."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from src.sales_confirm import prior_business_day
from src.sales_ledger import holding_period

from .live_snapshot import _num, account_tax_type

GROUPS = ("symbol", "account")
EPS = 1e-6
DIFFERS = 0.005


def load(base_dir: str | Path) -> dict[str, Any]:
    """Confirmed sales, unmatched candidates and holdings lots from the plan file (uncached: the page asks after
    the user confirms a sale). A plan that cannot be opened reads as empty."""
    try:
        from src import active_plan

        with active_plan.workspace_store(Path(base_dir)) as store:
            return {"sales": store.sales.list_sales(), "candidates": store.sales.list_candidates(state="unmatched"),
                    "lots": store.dataset("holdings").rows()}
    except Exception:  # noqa: BLE001 - older plan (no ledger tables), missing or locked
        return {"sales": [], "candidates": [], "lots": []}


def _window(today: date, start: str | None, tax_year: int | None) -> tuple[date, date]:
    if tax_year:
        return date(tax_year, 1, 1), min(date(tax_year, 12, 31), today)
    try:
        return date.fromisoformat(str(start or "").strip()[:10]), today
    except ValueError:
        return date(today.year, 1, 1), today


def _in(day: Any, lo: date, hi: date) -> bool:
    try:
        return lo <= date.fromisoformat(str(day)[:10]) <= hi
    except ValueError:
        return False


def _status_1099(sale: dict) -> str:
    if sale.get("official_gain") is None and sale.get("official_proceeds") is None:
        return "none"
    gain = sale["gain"] if sale.get("gain") is not None else _num(sale.get("proceeds")) - _num(sale.get("basis"))
    differs = (sale.get("official_gain") is not None and abs(_num(sale["official_gain"]) - gain) > DIFFERS) or \
              (sale.get("official_proceeds") is not None and abs(_num(sale["official_proceeds"]) - _num(sale.get("proceeds"))) > DIFFERS)
    return "differs" if differs else "matches"


def _row(sale: dict) -> dict[str, Any]:
    proceeds, basis = _num(sale.get("proceeds")), sale.get("basis")
    gain = sale.get("gain")
    if gain is None and basis is not None:
        gain = proceeds - _num(basis)
    return {"sale_id": sale.get("sale_id"), "symbol": str(sale.get("symbol") or "").upper(), "account": sale.get("account"),
            "sale_date": sale.get("sale_date"), "purchase_date": sale.get("purchase_date"), "shares": _num(sale.get("shares")),
            "proceeds": proceeds, "basis": None if basis is None else _num(basis), "gain": gain,
            "term": sale.get("holding_period") or "unknown", "source": sale.get("source"),
            "wash_flag": sale.get("wash_flag") or "none", "tax_class": sale.get("tax_class"),
            "status_1099": _status_1099(sale) if sale.get("sale_id") is not None else "none", "estimate": bool(sale.get("estimate"))}


def estimate_rows(candidates: list[dict], lots: list[dict], lo: date, hi: date) -> tuple[list[dict], int]:
    """(rows, how many waiting sales could not be estimated). One row per FIFO lot slice; a slice with no lot left
    has no basis and no gain. A candidate with no symbol, shares or amount cannot be valued."""
    rows, skipped = [], 0
    pool: dict[tuple[str, str], list[dict]] = {}
    for r in lots:
        shares = _num(r.get("shares"))
        if shares > EPS:
            pool.setdefault((str(r.get("account") or "").strip().lower(), str(r.get("symbol") or "").strip().upper()), []).append(
                {"date": str(r.get("purchase_date") or ""), "left": shares, "price": _num(r.get("purchase_price"))})
    for lot_list in pool.values():
        lot_list.sort(key=lambda x: (not x["date"], x["date"]))
    for c in sorted(candidates, key=lambda x: (x["sale_date"], x["candidate_id"])):
        if not _in(c["sale_date"], lo, hi):
            continue
        shares, price = c.get("shares"), c.get("price")
        amount = c.get("amount")
        if c.get("source") != "monarch" or not c.get("symbol") or not shares or (price is None and amount is None):
            skipped += 1
            continue
        proceeds_total = abs(float(amount)) if amount is not None else float(shares) * float(price)
        trade = prior_business_day(c["sale_date"])
        tax = account_tax_type(c["account"])
        left = float(shares)
        for lot in pool.get((str(c["account"]).strip().lower(), str(c["symbol"]).upper()), []):
            if left <= EPS:
                break
            take = min(left, lot["left"])
            if take <= EPS:
                continue
            lot["left"] -= take
            left -= take
            rows.append(_row({"symbol": c["symbol"], "account": c["account"], "sale_date": trade, "purchase_date": lot["date"] or None,
                              "shares": take, "proceeds": proceeds_total * take / float(shares), "basis": take * lot["price"],
                              "holding_period": holding_period(lot["date"] or None, trade), "source": "monarch",
                              "tax_class": tax, "estimate": True}))
        if left > EPS:  # more shares than lots on hand: that slice is valued but has no basis
            rows.append(_row({"symbol": c["symbol"], "account": c["account"], "sale_date": trade, "shares": left,
                              "proceeds": proceeds_total * left / float(shares), "basis": None, "holding_period": "unknown",
                              "source": "monarch", "tax_class": tax, "estimate": True}))
    return rows, skipped


def _totals(rows: list[dict]) -> dict[str, Any]:
    t = {"count": len(rows), "proceeds": 0.0, "basis": 0.0, "st_gain": 0.0, "lt_gain": 0.0, "unknown_gain": 0.0, "net": 0.0,
         "wash_flagged": 0.0, "basis_missing": 0}
    for r in rows:
        t["proceeds"] += r["proceeds"]
        if r["gain"] is None:
            t["basis_missing"] += 1
            continue
        t["basis"] += r["basis"] or 0.0
        t["net"] += r["gain"]
        t[{"short": "st_gain", "long": "lt_gain"}.get(r["term"], "unknown_gain")] += r["gain"]
        if r["wash_flag"] != "none":
            t["wash_flagged"] += r["gain"]
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()}


def _groups(rows: list[dict], by: str) -> list[dict]:
    keyed: dict[str, list[dict]] = {}
    for r in rows:
        keyed.setdefault(str(r[by] or ""), []).append(r)
    return [{"name": name, **_totals(ms), "lots": sorted(ms, key=lambda r: (str(r["sale_date"]), r["sale_id"] or 0))}
            for name, ms in sorted(keyed.items(), key=lambda kv: kv[0].casefold())]


def build(*, sales: list[dict], candidates: list[dict], lots: list[dict], today: date, start: str | None = None,
          tax_year: int | None = None, group: str = "symbol", taxable_only: bool = False, wash_only: bool = False,
          include_unconfirmed: bool = False) -> dict[str, Any]:
    lo, hi = _window(today, start, tax_year)
    group = group if group in GROUPS else "symbol"
    keep = lambda r: (not taxable_only or r["tax_class"] == "taxable") and (not wash_only or r["wash_flag"] != "none")
    confirmed = [r for r in (_row(s) for s in sales if s.get("status", "confirmed") == "confirmed" and _in(s.get("sale_date"), lo, hi)) if keep(r)]
    waiting = [c for c in candidates if _in(c["sale_date"], lo, hi)]
    est, skipped = estimate_rows(waiting, lots, lo, hi) if include_unconfirmed else ([], 0)
    est = [r for r in est if keep(r)]
    years = sorted({int(str(s["sale_date"])[:4]) for s in sales if str(s.get("sale_date") or "")[:4].isdigit()} | {today.year}, reverse=True)
    return {"window": {"from": lo.isoformat(), "to": hi.isoformat(), "tax_year": tax_year or None}, "group_by": group, "years": years,
            "filters": {"taxable_only": taxable_only, "wash_only": wash_only, "include_unconfirmed": include_unconfirmed},
            "summary": _totals(confirmed), "groups": _groups(confirmed, group),
            "unconfirmed": {"count": len(waiting), "not_estimated": skipped if include_unconfirmed else None},
            "estimate": {**_totals(est), "groups": _groups(est, group)} if include_unconfirmed else None}
