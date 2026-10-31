"""Interest and dividend reconciliation: imported broker income rows vs Monarch's investment-income rows (read-only).

For one plan account and tax year, broker rows of the income kinds (dividends including money-market sweep dividends,
interest, capital-gain distributions) are matched one-to-one to the Monarch YTD rows whose Account maps to that plan
account in the YTD account setup and whose Category is "Dividends & Capital Gains" or "Interest": amount within one
cent, date within 3 days, nearest date first. Design section 3.5. Foreign tax and return of capital are listed with the
broker rows but are not expected in Monarch, so they are reported separately and never counted as differences.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import active_plan
from .ytd_tracking import parse_date, parse_money

MATCH_KINDS = ("dividend", "interest", "cap_gain_short", "cap_gain_long")
INFO_KINDS = ("foreign_tax", "return_of_capital")
MONARCH_CATEGORIES = ("dividends & capital gains", "interest")
DAY_TOLERANCE = 3
CENT = 0.005


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _norm(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def monarch_income_rows(ytd_rows: Iterable[Mapping[str, Any]], accounts: set[str], year: int) -> list[dict[str, Any]]:
    out = []
    for r in ytd_rows:
        if _norm(r.get("Account")) not in accounts or _norm(r.get("Category")) not in MONARCH_CATEGORIES:
            continue
        d = parse_date(r.get("Date"))
        if d is None or d.year != year:
            continue
        out.append({"date": d.isoformat(), "amount": round(parse_money(r.get("Amount")), 2), "category": r.get("Category"),
                    "merchant": r.get("Merchant") or "", "account": r.get("Account") or "",
                    "monarch_id": r.get("Monarch Id") or ""})
    return sorted(out, key=lambda r: (r["date"], r["amount"]))


def match_income(broker_rows: list[Mapping[str, Any]], monarch_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Pure. ``{matched: [{broker, monarch}], broker_only, monarch_only, months, totals}``."""
    free = list(range(len(monarch_rows)))
    matched, broker_only = [], []
    for b in sorted(broker_rows, key=lambda r: (r["run_date"], r["amount"])):
        bd = date.fromisoformat(b["run_date"])
        fits = [i for i in free if abs(monarch_rows[i]["amount"] - b["amount"]) < CENT
                and abs((date.fromisoformat(monarch_rows[i]["date"]) - bd).days) <= DAY_TOLERANCE]
        if fits:
            i = min(fits, key=lambda i: (abs((date.fromisoformat(monarch_rows[i]["date"]) - bd).days), i))
            free.remove(i)
            matched.append({"broker": dict(b), "monarch": dict(monarch_rows[i])})
        else:
            broker_only.append(dict(b))
    monarch_only = [dict(monarch_rows[i]) for i in free]
    twins = [m["monarch"] for m in matched]  # an unmatched account-import row that repeats a matched one is a duplicate feed row
    for m in monarch_only:
        m["duplicate"] = any(abs(t["amount"] - m["amount"]) < CENT and abs((date.fromisoformat(t["date"]) - date.fromisoformat(m["date"])).days) <= DAY_TOLERANCE
                             for t in twins)
    dup_total = round(sum(m["amount"] for m in monarch_only if m["duplicate"]), 2)
    months: dict[str, dict[str, float]] = {}
    for b in broker_rows:
        months.setdefault(b["run_date"][:7], {"broker": 0.0, "monarch": 0.0})["broker"] += b["amount"]
    for m in monarch_rows:
        months.setdefault(m["date"][:7], {"broker": 0.0, "monarch": 0.0})["monarch"] += m["amount"]
    month_rows = [{"month": k, "broker": round(v["broker"], 2), "monarch": round(v["monarch"], 2),
                   "difference": round(v["broker"] - v["monarch"], 2)} for k, v in sorted(months.items())]
    tb, tm = round(sum(b["amount"] for b in broker_rows), 2), round(sum(m["amount"] for m in monarch_rows), 2)
    return {"matched": matched, "broker_only": broker_only, "monarch_only": monarch_only, "months": month_rows,
            "totals": {"broker": tb, "monarch": tm, "difference": round(tb - tm, 2),
                       "matched": len(matched), "broker_only": len(broker_only), "monarch_only": len(monarch_only),
                       "monarch_duplicates": sum(1 for m in monarch_only if m["duplicate"]),
                       "difference_without_duplicates": round(tb - (tm - dup_total), 2)}}


def _by_kind(rows: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        out[r["kind"]] = round(out.get(r["kind"], 0.0) + r["amount"], 2)
    return out


def reconcile(input_dir: str | Path, *, account: str, year: int) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        rows = store.broker.activity(account=account, year=int(year), kinds=MATCH_KINDS + INFO_KINDS)
        setup = [r for r in store.dataset("ytd_account_setup").rows() if _norm(r.get("Mapped Investment Account")) == _norm(account)]
        names = {_norm(r.get("Account")) for r in setup}
        monarch_off = bool(setup) and all(r.get("Role") == "Investment" for r in setup)  # Monarch rows are not kept for Investment accounts
        monarch = monarch_income_rows(store.dataset("ytd_transactions").rows(), names, int(year))
        imports = [i for i in store.broker.list_imports(account=account) if i["status"] == "applied"]
        reinvests = store.broker.activity(account=account, year=int(year), kinds=["reinvest"])
    keep = ("run_date", "kind", "symbol", "action", "amount", "sweep", "row_key")
    income = [{k: r[k] for k in keep} for r in rows if r["kind"] in MATCH_KINDS]
    info = [{k: r[k] for k in keep} for r in rows if r["kind"] in INFO_KINDS]
    reinvested = {(r["symbol"], r["run_date"], round(-r["amount"], 2)) for r in reinvests}
    for r in income:
        r["reinvested"] = (r["symbol"], r["run_date"], round(r["amount"], 2)) in reinvested
    out = match_income(income, monarch)
    return {"account": account, "year": int(year), "monarch_accounts": sorted(names), "monarch_disabled": monarch_off, "by_kind": _by_kind(income),
            "other_rows": info, "coverage": [{"date_from": i["date_from"], "date_to": i["date_to"],
                                              "file_name": i["file_name"]} for i in imports], **out}


def income_totals(input_dir: str | Path, *, account: str, year: int) -> dict[str, float]:
    """The year's broker income by kind: the figures the 1099-DIV / 1099-INT check (design 3.6) compares against."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        return _by_kind(store.broker.activity(account=account, year=int(year), kinds=MATCH_KINDS + INFO_KINDS))
