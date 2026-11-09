"""Realized-sales ledger, server side of the Sales ledger page: manual entry (one row or a grid of sales) and the ledger list. Validation and derived fields come from ``sales_ledger``; storage is the plan
file's ``store.sales`` (``SalesRepo``). Every function takes the workspace ``input`` folder like ``reconcile``.

Manual rows are one lot (or part of a lot) each, with the lot's basis and purchase date typed in.
Nothing reads the ledger yet (Phase 1)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import active_plan, sales_tax_year
from .sales_ledger import ValidationError, holding_period, validate_sale_row

_ROW_FIELDS = ("sale_date", "account", "tax_class", "symbol", "shares", "proceeds", "basis", "fees", "purchase_date", "settle_date", "wash_note", "lot_key")


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _manual(row: dict[str, Any]) -> dict[str, Any]:
    return validate_sale_row({**{k: v for k, v in row.items() if k in _ROW_FIELDS}, "source": "manual"})


def _fresh(input_dir: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    """The stored row re-read after the automatic wash scan (which may have flagged it); ``row`` if that fails."""
    try:
        with active_plan.workspace_store(_base(input_dir)) as store:
            return store.sales.get_sale(row["sale_id"])
    except Exception:  # noqa: BLE001
        return row


def add_sale(input_dir: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    """Record one manual sale; returns the stored row. Raises ``ValidationError`` and writes nothing on a bad row."""
    clean = _manual(row)
    clean.pop("status", None)
    with active_plan.workspace_store(_base(input_dir), write=True) as store:
        row = store.sales.get_sale(store.sales.insert_sale(**clean))
    sales_tax_year.auto_refresh(input_dir)
    return _fresh(input_dir, row)


def list_sales(input_dir: str | Path, *, year: int | None = None, include_voided: bool = False) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales(year=year, include_voided=include_voided)
    live = [s for s in sales if s["status"] == "confirmed" and s["gain"] is not None]
    return {"sales": sales, "totals": {
        "count": len(sales),
        "short_gain": sum(s["gain"] for s in live if s["holding_period"] == "short"),
        "long_gain": sum(s["gain"] for s in live if s["holding_period"] == "long"),
    }}


def sales_summary(input_dir: str | Path, year: int | None, *, taxable_only: bool = True) -> dict[str, Any]:
    """The Sales tab's KPI strip. The filter is exactly the Tax year tab's (``sales_tax_year._live_sales``) so the two agree
    on the realized figures; ``year=None`` means all years and ``taxable_only=False`` lets IRA, Roth and HSA sales in.
    ``count`` is ledger rows (lots, as Tax year counts them), ``sales`` is whole sales (account + symbol + date)."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales()
    live = [s for s in sales if s["status"] == "confirmed" and s["gain"] is not None
            and (not taxable_only or s["tax_class"] == "taxable") and (year is None or s["sale_date"][:4] == str(int(year)))]
    return {"count": len(live), "sales": len({(s["account"], s["symbol"], s["sale_date"]) for s in live}),
            "st_gain": sum(s["gain"] for s in live if s["holding_period"] == "short") + 0.0,
            "lt_gain": sum(s["gain"] for s in live if s["holding_period"] == "long") + 0.0,
            "fees": round(sum(float(s.get("fees") or 0.0) for s in live), 2) + 0.0}


def sales_years(input_dir: str | Path) -> list[int]:
    """Years that have ledger or log rows, ascending, never in the future."""
    this_year = date.today().year
    with active_plan.workspace_store(_base(input_dir)) as store:
        found = {str(s["sale_date"])[:4] for s in store.sales.list_sales()}
        found |= {str(r["txn_date"])[:4] for r in store.transactions.list()}
    return sorted(int(y) for y in found if y.isdigit() and 1900 < int(y) <= this_year)


def open_lots(input_dir: str | Path, account: str, symbol: str, as_of: str | None) -> dict[str, Any]:
    """The lot chooser's data: the account's open lots of ``symbol`` on ``as_of`` (the sale date), from the transaction log.
    ``log_started`` is False when the account has no log rows at all (the chooser then offers blank lot rows)."""
    from . import transactions
    with active_plan.workspace_store(_base(input_dir)) as store:
        started = any(r["account"] == account for r in store.transactions.list())
        lots = []
        for l in transactions.open_lots(store, account=account, symbol=symbol, as_of=as_of or None):
            lots.append({"txn_id": l["lot_txn_id"], "purchase_date": l["purchase_date"], "open_shares": l["shares"],
                         "unit_cost": float(l["price"] or 0.0), "source": store.transactions.get(l["lot_txn_id"])["source"],
                         "term": holding_period(l["purchase_date"], as_of) if as_of and l["purchase_date"] else "unknown"})
        near = []
        if as_of:
            lo, hi = (date.fromisoformat(as_of) + timedelta(days=d) for d in (-30, 30))
            near = [{"txn_id": r["txn_id"], "txn_date": r["txn_date"]} for r in store.transactions.list(symbol=symbol)
                    if r["type"] in ("buy", "reinvest") and lo.isoformat() <= r["txn_date"] <= hi.isoformat()]
    return {"lots": lots, "log_started": started, "nearby_buys": near}


_ENTRY_FIELDS = ("sale_date", "account", "symbol", "shares", "proceeds", "fees", "basis", "purchase_date", "settle_date", "wash_note")


def add_sales(input_dir: str | Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Record several lot rows at once, all or none. A row that names ``txn_lot`` (a lot of the transaction log) is also
    written to the log as a sell of those shares, so holdings follow; its ``lot_key`` carries both ids so a later Void
    gives the shares back. The tax class comes from the account."""
    from . import transactions
    from .sales_confirm import default_tax_class
    if not rows:
        raise ValidationError("add at least one sale")
    ids: list[int] = []
    accounts: set[str] = set()
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
            for raw in rows:
                base = {k: raw[k] for k in _ENTRY_FIELDS if k in raw}
                account = str(base.get("account") or "").strip()
                lot_id = raw.get("txn_lot")
                key: dict[str, Any] = {}
                if lot_id not in (None, ""):
                    lot = store.transactions.get(int(lot_id))
                    if lot["account"] != account or str(lot["symbol"]).upper() != str(base.get("symbol") or "").strip().upper():
                        raise ValidationError("the chosen lot belongs to another account or symbol")
                    base.setdefault("purchase_date", transactions.lot_date(lot))
                    if not base.get("purchase_date"):
                        base["purchase_date"] = transactions.lot_date(lot)
                    key = {"txn_lot": int(lot_id)}
                clean = validate_sale_row({**base, "tax_class": default_tax_class(store, account) if account else "taxable", "source": "manual"})
                clean.pop("status", None)
                if key:
                    sell_id = transactions._add(store, {
                        "txn_date": clean["sale_date"], "account": account, "type": "sell", "symbol": clean["symbol"],
                        "shares": clean["shares"], "price": clean["proceeds"] / clean["shares"], "amount": clean["proceeds"],
                        "fees": clean["fees"], "source": "manual"}, {int(lot_id): clean["shares"]})
                    clean["lot_key"] = json.dumps({**key, "log_sell": sell_id}, sort_keys=True)
                    accounts.add(account)
                ids.append(store.sales.insert_sale(**clean))
            if accounts:
                transactions.materialize_managed(store, accounts)
    except active_plan.StoreError as exc:
        raise ValidationError(str(exc)) from exc
    sales_tax_year.auto_refresh(input_dir)
    return {"ids": ids}


def account_classes(input_dir: str | Path) -> dict[str, str]:
    """``{investment account: tax class}`` for the entry grid's account list (the class sets the gain rule; no form field)."""
    from .broker_import import investment_accounts
    from .sales_confirm import default_tax_class
    with active_plan.workspace_store(_base(input_dir)) as store:
        return {a: default_tax_class(store, a) for a in investment_accounts(store)}


def taxable_accounts(input_dir: str | Path) -> list[str]:
    """Investment accounts a sale in which is taxable (the Taxable-only switch covers these), by the account-name rule."""
    from .broker_import import investment_accounts
    from .history_sales import is_taxable_account
    return [a for a in investment_accounts(input_dir) if is_taxable_account(a)]


def replace_sale(input_dir: str | Path, sale_id: int, row: dict[str, Any]) -> dict[str, Any]:
    """Edit a manual sale: void the old row and record the corrected one in one transaction (the old row stays
    voided, so Show voided keeps the history). Sales confirmed from the queue carry lot links and are changed by
    sending them back to the queue instead (``sales_confirm.requeue_sale``)."""
    clean = _manual(row)
    clean.pop("status", None)
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
            old = store.sales.get_sale(int(sale_id))
            if old["status"] != "confirmed":
                raise ValidationError("only a confirmed sale can be edited")
            if "log_sell" in (old.get("lot_key") or ""):
                raise ValidationError("this lot is linked to the transaction log; void it and record the sale again")
            if old["source"] != "manual":
                raise ValidationError("this sale came from the queue or a statement; send it back to the queue "
                                      "(or correct it through the 1099-B import) instead of editing it")
            store.sales.void_sale(old["sale_id"])
            row = store.sales.get_sale(store.sales.insert_sale(**clean))
    except active_plan.StoreError as exc:
        raise ValidationError(str(exc)) from exc
    sales_tax_year.auto_refresh(input_dir)
    return _fresh(input_dir, row)


def _set_voided(input_dir: str | Path, sale_id: int, voided: bool) -> None:
    from . import transactions
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
            row = store.sales.get_sale(int(sale_id))
            sell_id = (json.loads(row["lot_key"]) if (row.get("lot_key") or "").startswith("{") else {}).get("log_sell")
            if sell_id is not None:
                sell = store.transactions.get(int(sell_id))
                if voided and sell["status"] == "active":
                    store.transactions.void(int(sell_id))            # the shares go back to their lot
                    transactions.materialize_managed(store, [row["account"]])
                elif not voided and sell["status"] != "active":
                    raise ValidationError("this lot's log sale was removed with the void; record the sale again")
            (store.sales.void_sale if voided else store.sales.unvoid_sale)(int(sale_id))
    except active_plan.StoreError as exc:
        raise ValidationError(str(exc)) from exc
    sales_tax_year.auto_refresh(input_dir)


def void_sale(input_dir: str | Path, sale_id: int) -> None:
    _set_voided(input_dir, sale_id, True)


def unvoid_sale(input_dir: str | Path, sale_id: int) -> None:
    _set_voided(input_dir, sale_id, False)
