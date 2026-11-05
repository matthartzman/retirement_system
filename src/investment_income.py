"""Investment income of the taxable accounts for one tax year, by type: what the owner hands the accountant.

A derived view over the imported broker activity (``store.broker.activity``); nothing is stored except the owner's
per-symbol type choices (``plan_meta``). Only taxable accounts are included (a dividend inside an IRA, 401k, Roth or HSA is
not reported). Types:

- ``interest_ordinary`` bank and sweep interest; ``interest_treasury`` Treasury interest, which is exempt from state tax
  (a matured Treasury bill's discount is computed from its buys: redemption minus cost);
- ``dividend_ordinary`` fund and stock dividends; ``dividend_treasury_fund`` a fund of Treasuries, whose state-exempt share
  is fixed by the fund's year-end report, not by the broker rows; ``dividend_muni_fund`` a municipal fund, exempt from
  federal tax (state tax depends on the state);
- ``cap_gain_distribution`` (short or long), ``return_of_capital`` and ``foreign_tax``.

A broker row cannot say whether a dividend is qualified or what share of a fund is state-exempt: those come from the 1099-DIV
and the fund supplements, so the view reports gross amounts by type and says so. It is a cross-check and a hand-off, not a
return.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import active_plan
from .csv_exchange import text_csv
from .history_sales import is_taxable_account, is_treasury_bill_maturity
from .sales_ledger import ValidationError

SYMBOL_TYPES_KEY = "investment_income.symbol_types"
TYPES = ("interest_ordinary", "interest_treasury", "dividend_ordinary", "dividend_treasury_fund", "dividend_muni_fund",
         "cap_gain_distribution_short", "cap_gain_distribution_long", "return_of_capital", "foreign_tax")
LABELS = {
    "interest_ordinary": "Interest (ordinary)", "interest_treasury": "Interest: U.S. Treasury (state-exempt)",
    "dividend_ordinary": "Dividends (ordinary)", "dividend_treasury_fund": "Dividends: Treasury funds (state-exempt share per fund report)",
    "dividend_muni_fund": "Dividends: municipal funds (federal-exempt)",
    "cap_gain_distribution_short": "Capital gain distributions (short-term)", "cap_gain_distribution_long": "Capital gain distributions (long-term)",
    "return_of_capital": "Return of capital", "foreign_tax": "Foreign tax paid",
}
# Funds whose income is Treasury or municipal. A starting list the owner can change per symbol on the page.
_TREASURY_FUNDS = frozenset({"SHV", "BIL", "SGOV", "TFLO", "VGSH", "VGIT", "VGLT", "GOVT", "IEF", "SHY", "TLT", "IEI", "TIP",
                             "VTIP", "SCHO", "SCHR", "USFR", "FDRXX", "VMFXX", "SPAXX"})
_MUNI_FUNDS = frozenset({"MUB", "VTEB", "TFI", "SUB", "SHM", "ITM", "MUNI", "VWITX", "VWAHX", "VMLUX"})
_KIND_TYPE = {"dividend": "dividend_ordinary", "interest": "interest_ordinary", "cap_gain_short": "cap_gain_distribution_short",
              "cap_gain_long": "cap_gain_distribution_long", "return_of_capital": "return_of_capital", "foreign_tax": "foreign_tax"}


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def default_type(kind: str, symbol: str, description: str = "") -> str:
    sym = (symbol or "").strip().upper()
    text = (description or "").upper()
    base = _KIND_TYPE[kind]
    if base == "dividend_ordinary":
        if sym in _MUNI_FUNDS or "MUNI" in text or "TAX FREE" in text or "TAX-EXEMPT" in text:
            return "dividend_muni_fund"
        if sym in _TREASURY_FUNDS or "TREASURY" in text or "TREAS " in text:
            return "dividend_treasury_fund"
    if base == "interest_ordinary" and (sym.startswith(("9127", "9128", "912810")) or "TREAS" in text or "TSY" in text):
        return "interest_treasury"
    return base


def _symbol_types(store) -> dict[str, str]:
    try:
        raw = json.loads(store.get_meta(SYMBOL_TYPES_KEY) or "{}")
    except (TypeError, ValueError):
        return {}
    return {str(k).upper(): str(v) for k, v in raw.items() if v in TYPES}


def _maturity_interest(rows: list[dict[str, Any]], r: dict[str, Any]) -> float | None:
    """Redemption proceeds minus the cost of the units redeemed (first in, first out over the symbol's buys), ``None`` when
    the files do not hold the buy."""
    face = abs(r["quantity"] or 0.0)
    buys = sorted((b for b in rows if b["kind"] == "buy" and b["symbol"] == r["symbol"] and b["run_date"] <= r["run_date"]
                   and b["quantity"]), key=lambda b: (b["run_date"], b["activity_id"]))
    used = sum(abs(x["quantity"] or 0.0) for x in rows if is_treasury_bill_maturity(x) and x["symbol"] == r["symbol"]
               and (x["run_date"], x["activity_id"]) < (r["run_date"], r["activity_id"]))
    skip, need, cost = used, face, 0.0
    for b in buys:
        q = abs(b["quantity"])
        if skip >= q - 1e-9:
            skip -= q
            continue
        take = min(q - skip, need)
        cost += abs(b["amount"] or 0.0) * take / q
        need -= take
        skip = 0.0
        if need <= 1e-9:
            break
    return round(float(r["amount"] or 0.0) - cost, 2) if need <= 1e-9 else None


def build(input_dir: str | Path, year: int) -> dict[str, Any]:
    year = int(year)
    with active_plan.workspace_store(_base(input_dir)) as store:
        applied = {i["import_id"] for i in store.broker.list_imports() if i["status"] == "applied"}
        accounts = sorted({i["account"] for i in store.broker.list_imports() if i["status"] == "applied"})
        taxable = [a for a in accounts if is_taxable_account(a)]
        overrides = _symbol_types(store)
        rows_out: list[dict[str, Any]] = []
        notes: list[str] = []
        for account in taxable:
            rows = [r for r in store.broker.activity(account=account) if r["import_id"] in applied]
            for r in rows:
                if not r["run_date"].startswith(str(year)):
                    continue
                if r["kind"] in _KIND_TYPE and not r["sweep"]:
                    sym = (r["symbol"] or "").upper()
                    typ = overrides.get(sym) or default_type(r["kind"], sym, r["description"])
                    rows_out.append({"date": r["run_date"], "account": account, "symbol": sym, "type": typ,
                                     "amount": round(float(r["amount"] or 0.0), 2), "description": r["description"] or "",
                                     "source": "broker"})
                elif r["kind"] in ("sell", "other") and is_treasury_bill_maturity(r):
                    interest = _maturity_interest(rows, r)
                    if interest is None:
                        notes.append(f"{r['run_date']} {r['symbol']}: a Treasury bill matured but its purchase is not in the broker files, "
                                     "so the interest could not be worked out.")
                        continue
                    rows_out.append({"date": r["run_date"], "account": account, "symbol": (r["symbol"] or "").upper(),
                                     "type": "interest_treasury", "amount": interest, "source": "maturity",
                                     "description": "Treasury bill maturity: redemption minus cost"})
    totals: dict[str, float] = {}
    by_account: dict[str, dict[str, float]] = {}
    for r in rows_out:
        totals[r["type"]] = round(totals.get(r["type"], 0.0) + r["amount"], 2)
        acct = by_account.setdefault(r["account"], {})
        acct[r["type"]] = round(acct.get(r["type"], 0.0) + r["amount"], 2)
    symbols = sorted({(r["symbol"], r["type"]) for r in rows_out if r["source"] == "broker"})
    notes.append("Gross amounts from your imported broker files, taxable accounts only. Qualified dividends and the state-exempt "
                 "share of Treasury funds come from your 1099-DIV and the fund reports; give those to your accountant.")
    return {"year": year, "rows": sorted(rows_out, key=lambda r: (r["date"], r["account"], r["symbol"])), "totals": totals,
            "by_account": by_account, "labels": LABELS, "symbols": [{"symbol": s, "type": t} for s, t in symbols], "notes": notes}


def set_symbol_type(input_dir: str | Path, symbol: str, type_: str | None) -> None:
    """Pin ``symbol`` to ``type_`` for every year; ``None`` returns it to the default rule."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValidationError("a symbol is needed")
    if type_ is not None and type_ not in TYPES:
        raise ValidationError(f"type must be one of {', '.join(TYPES)}")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        cur = _symbol_types(store)
        if type_ is None:
            cur.pop(sym, None)
        else:
            cur[sym] = type_
        store.set_meta(SYMBOL_TYPES_KEY, json.dumps(cur, sort_keys=True))


def to_csv(data: dict[str, Any]) -> str:
    rows = [["date", "account", "symbol", "type", "amount", "description"]]
    rows += [[r["date"], r["account"], r["symbol"], LABELS.get(r["type"], r["type"]), f"{r['amount']:.2f}", r["description"]]
             for r in data["rows"]]
    return text_csv.rows_to_text(rows)
