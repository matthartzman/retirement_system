"""Sales that a history-only broker import left out of the realized-sales ledger.

A history-only import (``broker_import``, for accounts whose holdings already reflect the file) stores the activity rows
but queues no sale, so a sale in a taxable account never reached the ledger (the 2026-09-22 ITOT sale of Matt's Trust).
This module finds those sales again and records them, deriving each lot's basis and purchase date by replaying the
buys the broker files themselves contain (first in, first out). A sale the replay cannot fully cover (a lot bought
before the oldest file) is listed as ``complete: False`` and is recorded by hand on the Record a sale form.

Matured Treasury bills are not sales here: their gain is interest, so they are listed as ``interest`` items and never
recorded as a capital gain (the owner decision of 2026-11-04).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import active_plan, sales_tax_year
from .broker_activity.normalized import group_orders
from .sales_confirm import default_tax_class
from .sales_ledger import ValidationError, validate_sale_row

DISMISS_KEY = "history_sales.dismissed"
_EPS = 1e-6
FIRST_YEAR = 2026          # earlier years are filed; only the current plan year onward is offered
_CUSIP_LEN = 9


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _order_key(account: str, o: dict[str, Any]) -> str:
    return f"{account}|{o['symbol']}|{o['trade_date']}|{o['shares']:.6f}|{o['proceeds']:.2f}"


def is_treasury_bill_maturity(row: dict[str, Any]) -> bool:
    """A redemption of a matured bond or bill: the gain is interest, not a capital gain."""
    text = f"{row.get('action') or ''} {row.get('description') or ''}".upper()
    return "REDEMPTION" in text and ("MATURED" in text or "TSY BILL" in text or "TREAS" in text)


def is_taxable_account(account: str) -> bool:
    """By the Planner's account-name rule (``_hsa``, ``_ira``, ``_roth``, ``_401k``, ...); an unrecognised name counts as taxable.
    The owner's ledger history is not consulted: an HSA sale booked as taxable to report earnings must not make the account taxable."""
    from .core import ACCOUNT_TYPES, _infer_type
    try:
        return ACCOUNT_TYPES[_infer_type(account)]["tax"] == "taxable"
    except (ValueError, KeyError):
        return True


def _dismissed(store) -> set[str]:
    try:
        return {str(k) for k in json.loads(store.get_meta(DISMISS_KEY) or "[]")}
    except (TypeError, ValueError):
        return set()


def _replay(rows: list[dict[str, Any]]) -> dict[tuple, list[dict[str, Any]] | None]:
    """FIFO replay of one account's buys, reinvestments and sells. Returns ``{(symbol, trade_date, shares): pieces}``
    for every sell order, ``None`` when the buys on file do not cover it."""
    lots: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r["sweep"] or not r["symbol"] or not r["quantity"]:
            continue
        if r["kind"] in ("buy", "reinvest"):
            lots.setdefault(r["symbol"], []).append({"date": r["run_date"], "left": abs(r["quantity"]),
                                                      "price": float(r["price"] or 0.0)})
    out: dict[tuple, list[dict[str, Any]] | None] = {}
    events = sorted((r for r in rows if r["kind"] == "sell" and not r["sweep"] and r["symbol"]),
                    key=lambda r: (r["run_date"], r["activity_id"]))
    for o in group_orders(events):
        pieces, need = [], o["shares"]
        for lot in sorted(lots.get(o["symbol"], []), key=lambda l: l["date"]):
            if need <= _EPS:
                break
            if lot["date"] > o["trade_date"] or lot["left"] <= _EPS:
                continue
            take = min(lot["left"], need)
            lot["left"] -= take
            need -= take
            pieces.append({"purchase_date": lot["date"], "shares": round(take, 6), "price": lot["price"]})
        out[(o["symbol"], o["trade_date"], o["shares"])] = pieces if need <= _EPS else None
    return out


def _recorded(store) -> list[dict[str, Any]]:
    return [s for s in store.sales.list_sales() if s["status"] == "confirmed"]


def _already_in_ledger(sales: list[dict[str, Any]], account: str, o: dict[str, Any], key: str) -> bool:
    mine = [s for s in sales if s["account"] == account and s["symbol"] == o["symbol"] and s["sale_date"] == o["trade_date"]]
    if any(f'"history_key": "{key}"' in (s.get("lot_key") or "") or key in (s.get("lot_key") or "") for s in mine):
        return True
    return bool(mine) and abs(sum(s["proceeds"] for s in mine) - o["proceeds"]) <= 1.0


def _items(store, year: int | None) -> list[dict[str, Any]]:
    imports = [i for i in store.broker.list_imports() if i["status"] == "applied"
               and (i.get("summary") or {}).get("history_only")]
    accounts = sorted({i["account"] for i in imports})
    sales, dismissed = _recorded(store), _dismissed(store)
    out: list[dict[str, Any]] = []
    for account in accounts:
        if not is_taxable_account(account):
            continue               # a sale inside an IRA, 401k, Roth or HSA has no gain to report
        rows = [r for r in store.broker.activity(account=account)
                if r["import_id"] in {i["import_id"] for i in store.broker.list_imports(account=account) if i["status"] == "applied"}]
        history_ids = {i["import_id"] for i in imports if i["account"] == account}
        treasury = [r for r in rows if r["kind"] in ("sell", "other") and is_treasury_bill_maturity(r)]
        trades = [r for r in rows if r not in treasury]
        replay = _replay(trades)
        sell_rows = [r for r in trades if r["import_id"] in history_ids and r["kind"] == "sell"]
        for o in group_orders(sell_rows):
            y = int(o["trade_date"][:4])
            if (year is not None and y != year) or y < FIRST_YEAR:
                continue
            key = _order_key(account, o)
            if key in dismissed or _already_in_ledger(sales, account, o, key):
                continue
            pieces = replay.get((o["symbol"], o["trade_date"], o["shares"]))
            item = {"key": key, "account": account, "symbol": o["symbol"], "sale_date": o["trade_date"],
                    "shares": o["shares"], "proceeds": o["proceeds"], "fees": o["fees"], "kind": "sale",
                    "complete": pieces is not None, "pieces": pieces or []}
            if pieces:
                item["basis"] = round(sum(p["shares"] * p["price"] for p in pieces), 2)
                item["gain"] = round(o["proceeds"] - item["basis"], 2)
            out.append(item)
        for r in treasury:
            y = int(r["run_date"][:4])
            if (year is not None and y != year) or y < FIRST_YEAR:
                continue
            out.append({"key": f"{account}|{r['symbol']}|{r['run_date']}|interest", "account": account, "symbol": r["symbol"],
                        "sale_date": r["run_date"], "shares": abs(r["quantity"] or 0.0), "proceeds": float(r["amount"] or 0.0),
                        "kind": "interest", "complete": False, "pieces": []})
    return sorted(out, key=lambda x: (x["sale_date"], x["account"], x["symbol"]))


def list_unrecorded(input_dir: str | Path, *, year: int | None = None) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        items = _items(store, year)
    return {"items": items}


def record(input_dir: str | Path, key: str, *, tax_class: str | None = None) -> dict[str, Any]:
    """Write the ledger rows (one per replayed lot) for the history sale ``key`` as manual sales."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        item = next((i for i in _items(store, None) if i["key"] == key), None)
        if item is None:
            raise ValidationError("that sale is already recorded or dismissed")
        if item["kind"] != "sale":
            raise ValidationError("a matured Treasury bill is interest income, not a sale; it cannot be recorded here")
        if not item["complete"]:
            raise ValidationError("the broker files do not show every lot this sale came from; record it on the Record a sale form")
        tclass = tax_class or default_tax_class(store, item["account"])
        ids, left = [], item["proceeds"]
        for n, p in enumerate(item["pieces"]):
            part = left if n == len(item["pieces"]) - 1 else round(item["proceeds"] * p["shares"] / item["shares"], 2)
            left = round(left - part, 2)
            row = validate_sale_row({
                "sale_date": item["sale_date"], "account": item["account"], "tax_class": tclass, "symbol": item["symbol"],
                "shares": p["shares"], "proceeds": part, "fees": round(item["fees"] * p["shares"] / item["shares"], 2),
                "basis": round(p["shares"] * p["price"], 2), "purchase_date": p["purchase_date"], "source": "manual",
                "lot_key": json.dumps({"history_key": key, "purchase_date": p["purchase_date"]}, sort_keys=True)})
            row.pop("status", None)
            ids.append(store.sales.insert_sale(**row))
    sales_tax_year.auto_refresh(input_dir)
    return {"sale_ids": ids}


def dismiss(input_dir: str | Path, key: str) -> None:
    """Hide a listed item (a sale already recorded another way, or an interest item handled elsewhere)."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        keys = _dismissed(store) | {key}
        store.set_meta(DISMISS_KEY, json.dumps(sorted(keys)))
