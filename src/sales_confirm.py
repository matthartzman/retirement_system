"""Confirm, undo and dismiss a queued sale (ledger plan 6 and 6.1): the user picks specific holdings lots, the
service turns that allocation into ledger rows, reduces the lots and marks the candidate, all in one plan-file
transaction. Aids (FIFO, HIFO, loss-first) are pure and only fill a draft; nothing is saved until ``confirm``.

Every function takes the workspace ``input`` folder like ``sales_service``. A lot is addressed by ``lot_id`` (its row
index in the holdings dataset), valid only against the holdings the panel was read from.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

from . import active_plan, sales_tax_year, transactions
from .sales_ledger import ValidationError, allocate_lots, holding_period, validate_sale_row

AIDS = ("fifo", "hifo", "lowest_gain")
DISMISS_REASONS = {"before_ledger_start": "dismissed", "other": "dismissed", "not_a_sale": "not_a_sale"}
_EPS = 1e-6


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _fmt(x: float) -> str:
    return ("%.8f" % x).rstrip("0").rstrip(".") or "0"


def prior_business_day(iso: str) -> str:
    """The weekday before ``iso`` (weekends only; exchange holidays are not modelled)."""
    d = date.fromisoformat(iso) - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _num(text: Any) -> float:
    try:
        return float(str(text).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def suggest_allocation(method: str, shares_sold: float, lots: list[Mapping[str, Any]], price: float | None) -> dict[str, Any]:
    """A draft split of ``shares_sold`` over ``lots`` (``lot_id, remaining, basis_per_share, holding_period,
    purchase_date``) by one rule. Read-only; ``complete`` is false when the lots hold fewer shares than sold.

    ``fifo`` oldest first; ``hifo`` highest basis per share first; ``lowest_gain`` losses first (largest loss first),
    then gains with long-term before short-term and the smaller gain first."""
    if method not in AIDS:
        raise ValidationError(f"method must be one of {', '.join(AIDS)}")

    def gain(l):
        return (price - l["basis_per_share"]) if price is not None else 0.0

    keys = {
        "fifo": lambda l: (not l.get("purchase_date"), l.get("purchase_date") or ""),
        "hifo": lambda l: (-l["basis_per_share"],),
        "lowest_gain": lambda l: (gain(l) >= 0, gain(l) if gain(l) < 0 else 0.0,
                                  l["holding_period"] != "long" if gain(l) >= 0 else False, gain(l)),
    }
    left, alloc, total = float(shares_sold), {}, 0.0
    for l in sorted(lots, key=keys[method]):
        if left <= _EPS:
            break
        take = min(left, float(l["remaining"]))
        if take > _EPS:
            alloc[l["lot_id"]] = take
            total += take * (gain(l) if price is not None else 0.0)
            left -= take
    return {"allocation": alloc, "gain": total if price is not None else None, "complete": left <= _EPS}


def _holdings_lots(store, account: str, symbol: str, trade_date: str | None, price: float | None) -> list[dict[str, Any]]:
    out = []
    for i, r in enumerate(store.dataset("holdings").rows()):
        remaining = _num(r.get("shares"))
        if remaining <= _EPS or str(r.get("account", "")).strip().lower() != account.strip().lower() \
                or str(r.get("symbol", "")).strip().upper() != symbol.upper():
            continue
        basis = _num(r.get("purchase_price"))
        hp = holding_period(r.get("purchase_date") or None, trade_date) if trade_date else "unknown"
        out.append({"lot_id": str(i), "purchase_date": r.get("purchase_date") or "", "remaining": remaining,
                    "basis_per_share": basis, "holding_period": hp, "lot_type": r.get("lot_type", ""),
                    "implied_gain": None if price is None else remaining * (price - basis)})
    return out


MONARCH_MANAGED_REFUSAL = ("this account is managed by the transaction log; record the sale there and dismiss this one")


def _log_lots(store, account: str, symbol: str, trade_date: str | None, price: float | None) -> list[dict[str, Any]]:
    """A managed account's lots, from the log: ``lot_id`` is the lot's transaction id (not a holdings index)."""
    out = []
    for l in transactions.open_lots(store, account=account, symbol=symbol):
        pd = "" if l["purchase_date"] == transactions._NO_DATE else l["purchase_date"]
        if trade_date and pd and pd > trade_date:
            continue
        pd = l["tacked_date"] or pd
        basis = float(l["adjusted_unit_cost"] or 0.0)        # includes any wash-sale add-back
        out.append({"lot_id": str(l["lot_txn_id"]), "purchase_date": pd, "remaining": float(l["shares"]), "basis_per_share": basis,
                    "holding_period": holding_period(pd or None, trade_date) if trade_date else "unknown",
                    "lot_type": l["lot_type"], "implied_gain": None if price is None else float(l["shares"]) * (price - basis),
                    "_row": l})
    return out


def _lots_for(store, account: str, symbol: str, trade_date: str | None, price: float | None) -> list[dict[str, Any]]:
    """The lots a sale can draw on: the log's for a managed account, else the holdings'."""
    if transactions.is_managed(store, account):
        return [{k: v for k, v in l.items() if k != "_row"} for l in _log_lots(store, account, symbol, trade_date, price)]
    return _holdings_lots(store, account, symbol, trade_date, price)


def _candidate(store, candidate_id: int) -> dict[str, Any]:
    for c in store.sales.list_candidates():
        if c["candidate_id"] == int(candidate_id):
            return c
    raise ValidationError(f"no sale candidate {candidate_id}")


def _price(c: Mapping[str, Any], shares: float | None) -> float | None:
    if c.get("price") is not None:
        return float(c["price"])
    if c.get("amount") is not None and shares:
        return float(c["amount"]) / shares
    return None


def _settle_date(c: Mapping[str, Any]) -> str | None:
    """A broker file states the settlement date; a Monarch row's date is the settlement date; otherwise unknown."""
    return c.get("settle_date") or (c["sale_date"] if c["source"] == "monarch" else None)


def default_tax_class(store, account: str) -> str:
    """The class the user last gave a ledger row of ``account``, else the Planner's account-name suffix rule
    (``_hsa``, ``_ira``, ``_roth``, ...), else ``taxable``."""
    for r in reversed(store.sales.list_sales(include_voided=True)):
        if r["account"].strip().lower() == account.strip().lower():
            return r["tax_class"]
    from .core import ACCOUNT_TYPES, _infer_type
    try:
        cls = ACCOUNT_TYPES[_infer_type(account)]["tax"]
    except ValueError:
        return "taxable"
    return cls if cls in ("taxable", "pre_tax", "roth", "hsa") else "taxable"


def panel(input_dir: str | Path, candidate_id: int, *, symbol: str | None = None, shares: float | None = None) -> dict[str, Any]:
    """Everything the side panel shows for one candidate. ``symbol``/``shares`` supply a bare candidate's missing
    detail. No lot is selected (``allocation`` is empty); ``only_exact_fit`` names a lot equal to the sale, unselected."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        c = _candidate(store, candidate_id)
        sym = (symbol or c["symbol"] or "").strip().upper()
        qty = shares if shares is not None else c["shares"]
        monarch = c["source"] == "monarch"
        trade = prior_business_day(c["sale_date"]) if monarch else c["sale_date"]
        price = _price(c, qty)
        lots = _lots_for(store, c["account"], sym, trade, price) if sym else []
        tax_class = default_tax_class(store, c["account"])
        managed = transactions.is_managed(store, c["account"])
    exact = [l["lot_id"] for l in lots if qty and abs(l["remaining"] - qty) <= _EPS]
    refusal = "its lots were already removed by the holdings import; record it with manual entry, then dismiss it" \
        if c["source"] == "holdings_diff" else MONARCH_MANAGED_REFUSAL if managed and monarch else None
    return {
        "candidate": c, "symbol": sym, "shares": qty, "price": price, "lots": lots, "allocation": {},
        "suggested_trade_date": trade, "settle_date": c["sale_date"] if monarch else None,
        "year_end_case": monarch and trade[:4] != c["sale_date"][:4], "tax_class": tax_class,
        "only_exact_fit": exact[0] if len(exact) == 1 else None, "confirmable": refusal is None, "refusal": refusal, "managed": managed,
        "aids": {m: suggest_allocation(m, qty, lots, price) for m in AIDS} if qty and lots else {},
    }


def list_candidates(input_dir: str | Path, *, state: str | None = None) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        every = store.sales.list_candidates()
    counts = {s: 0 for s in ("unmatched", "confirmed", "dismissed", "not_a_sale")}
    for c in every:
        counts[c["state"]] += 1
    return {"candidates": [c for c in every if state in (None, c["state"])], "counts": counts}


def _store_errors(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except active_plan.StoreError as exc:
            raise ValidationError(str(exc)) from exc
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


@_store_errors
def confirm(input_dir: str | Path, candidate_id: int, *, allocation: Mapping[str, float], tax_class: str,
            trade_date: str, fees: float = 0.0, proceeds: float | None = None,
            symbol: str | None = None, shares: float | None = None) -> dict[str, Any]:
    """Turn ``allocation`` (``{lot_id: shares}``) into confirmed ledger rows, reduce the holdings lots and mark the
    candidate ``confirmed``, in one transaction. Raises ``ValidationError`` and changes nothing when the candidate is
    not ``unmatched``, the allocation does not equal the shares sold, a lot is over-allocated or a row is invalid."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        out = confirm_in(store, candidate_id, allocation=allocation, tax_class=tax_class, trade_date=trade_date,
                         fees=fees, proceeds=proceeds, symbol=symbol, shares=shares)
        transactions.sync_if_started(store)   # a broker sale writes its log row; a Monarch sale writes none
    sales_tax_year.auto_refresh(input_dir)
    return out


def confirm_in(store, candidate_id: int, *, allocation: Mapping[str, float], tax_class: str, trade_date: str,
               fees: float = 0.0, proceeds: float | None = None, symbol: str | None = None,
               shares: float | None = None) -> dict[str, Any]:
    """``confirm`` inside the caller's open write store and transaction (the broker bulk import confirms many)."""
    c = _candidate(store, candidate_id)
    if c["state"] != "unmatched":
        raise ValidationError(f"only an unmatched sale can be confirmed (this one is {c['state']})")
    if c["source"] == "holdings_diff":
        raise ValidationError("its lots were already removed by the holdings import; record it with manual entry, then dismiss it")
    sym = (symbol or c["symbol"] or "").strip().upper()
    qty = shares if shares is not None else c["shares"]
    if not sym or not qty:
        raise ValidationError("a bare sale needs a symbol and shares before it can be confirmed")
    total = proceeds if proceeds is not None else c["amount"]
    if total is None and c["price"] is not None:
        total = c["price"] * qty
    if total is None:
        raise ValidationError("proceeds are needed")
    managed = transactions.is_managed(store, c["account"])
    if managed and c["source"] == "monarch":
        raise ValidationError(MONARCH_MANAGED_REFUSAL)
    if managed:   # the log is the book: the sale is a log row naming lots by id, and the holdings are rewritten from it
        lots = _log_lots(store, c["account"], sym, trade_date, None)
        info = {l["lot_id"]: l["_row"] for l in lots}
    else:
        lots = _holdings_lots(store, c["account"], sym, trade_date, None)
    picked = allocate_lots(qty, [{"lot_key": l["lot_id"], "remaining": l["remaining"]} for l in lots],
                          {str(k): v for k, v in allocation.items()})
    repo = store.dataset("holdings")
    rows = repo.rows()
    removed: list[str] = []   # holdings rows this sale emptied (they leave the dataset, so later row indexes shift)
    sale_rows, remaining_total = [], float(total)
    order = sorted(picked, key=int)
    for n, lot_id in enumerate(order):
        q = picked[lot_id]
        if managed:
            lot = info[lot_id]
            pd = lot["tacked_date"] or ("" if lot["purchase_date"] == transactions._NO_DATE else lot["purchase_date"])
            r = {"account": c["account"], "symbol": sym, "purchase_date": pd, "purchase_price": _fmt(float(lot["adjusted_unit_cost"] or 0.0)),
                 "lot_type": lot["lot_type"], "note": "", "shares": ""}
            key = {"txn_lot": int(lot_id), "index": 0}
        else:
            r = rows[int(lot_id)]
            key = {"index": int(lot_id)}
        part = remaining_total if n == len(order) - 1 else round(float(total) * q / qty, 6)
        remaining_total -= part
        ident = {k: r.get(k, "") for k in ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")}
        sale_rows.append(validate_sale_row({
            "sale_date": trade_date, "settle_date": _settle_date(c),
            "account": c["account"], "tax_class": tax_class, "symbol": sym, "shares": q, "proceeds": part,
            "fees": fees * q / qty, "basis": q * _num(r.get("purchase_price")),
            "purchase_date": r.get("purchase_date") or None, "source": c["source"], "monarch_id": c["monarch_id"],
            "lot_key": json.dumps({**ident, **key, "orig_shares": r.get("shares", "")}, sort_keys=True)}))
    if managed:
        act = next((a for a in store.broker.activity(kinds=("sell",)) if a["candidate_id"] == c["candidate_id"] and not a["sweep"]), None)
        transactions._add(store, {
            "txn_date": trade_date, "settle_date": _settle_date(c), "account": c["account"], "type": "sell", "symbol": sym,
            "shares": qty, "price": c["price"] if c["price"] is not None else float(total) / qty, "amount": float(total),
            "fees": fees, "source": "broker" if act else "manual", "activity_id": act["activity_id"] if act else None,
            "candidate_id": c["candidate_id"]}, {int(k): v for k, v in picked.items()})
    else:
        for lot_id in order:
            left = _num(rows[int(lot_id)]["shares"]) - picked[lot_id]
            rows[int(lot_id)]["shares"] = _fmt(left) if left > _EPS else None
            if left <= _EPS:
                removed.append(lot_id)
        repo.replace_all([r for r in rows if r.get("shares") is not None])
    ids = []
    for row in sale_rows:
        row.pop("status", None)
        ids.append(store.sales.insert_sale(**row))
    store.sales.set_candidate_state(c["candidate_id"], "confirmed", confirmed_sale_ids=ids)
    if managed:
        transactions.materialize_managed(store, [c["account"]])
    return {"sale_ids": ids, "removed_lots": removed}


@_store_errors
def undo(input_dir: str | Path, candidate_id: int) -> None:
    """Void the candidate's rows, give the shares back to their lots and return it to ``unmatched``. Locked once any of
    its rows carries 1099-B (``official_*``) numbers."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        undo_in(store, candidate_id)
    sales_tax_year.auto_refresh(input_dir)


def undo_in(store, candidate_id: int) -> None:
    """``undo`` inside the caller's open write store and transaction (the bulk review undoes many)."""
    c = _candidate(store, candidate_id)
    if c["state"] != "confirmed":
        raise ValidationError(f"only a confirmed sale can be undone (this one is {c['state']})")
    sales = [store.sales.get_sale(i) for i in c["confirmed_sale_ids"]]
    if any(s["official_proceeds"] is not None or s["official_basis"] is not None or s["official_gain"] is not None
           for s in sales):
        raise ValidationError("a 1099-B was applied to this sale; edit it through the 1099-B import instead")
    repo = store.dataset("holdings")
    rows = repo.rows()
    keys = [json.loads(s["lot_key"]) for s in sales]
    # a sale the log wrote and still manages is undone in the log; the holdings are rewritten from it
    via_log = bool(sales) and all("txn_lot" in k for k in keys) and transactions.is_managed(store, c["account"])
    for s in sorted(sales, key=lambda s: json.loads(s["lot_key"])["index"]):
        lot = json.loads(s["lot_key"])
        same = ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")
        hit = next((r for r in rows if all(r.get(k, "") == lot[k] for k in same)), None)
        if via_log:
            pass
        elif hit is None:
            rows.insert(min(lot["index"], len(rows)), {**{k: lot[k] for k in same}, "shares": _fmt(s["shares"])})
            if abs(s["shares"] - _num(lot["orig_shares"])) <= _EPS:
                rows[min(lot["index"], len(rows) - 1)]["shares"] = lot["orig_shares"]
        else:
            back = _num(hit["shares"]) + s["shares"]
            hit["shares"] = lot["orig_shares"] if abs(back - _num(lot["orig_shares"])) <= _EPS else _fmt(back)
        store.sales.void_sale(s["sale_id"])
    if not via_log:
        repo.replace_all(rows)
    store.sales.set_candidate_state(c["candidate_id"], "unmatched")
    for r in store.transactions.list():
        if r["type"] == "sell" and r["candidate_id"] == c["candidate_id"]:
            store.transactions.release(r["txn_id"], "sale undone")
    transactions.materialize_managed(store, [c["account"]])
    transactions.sync_if_started(store)


@_store_errors
def requeue_sale(input_dir: str | Path, sale_id: int) -> dict[str, Any]:
    """Send a queue-confirmed sale back to the queue: ``undo`` the candidate whose confirm wrote ``sale_id`` (all of
    that order's lot rows go back together). Returns the candidate id for the panel."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        hit = next((c for c in store.sales.list_candidates(state="confirmed") if int(sale_id) in c["confirmed_sale_ids"]), None)
    if hit is None:
        raise ValidationError("this sale was not confirmed from the queue; void it instead")
    undo(input_dir, hit["candidate_id"])
    return {"candidate_id": hit["candidate_id"]}


def move_in(store, candidate_id: int, allowed: tuple[str, ...], new_state: str) -> None:
    """A state-only move inside the caller's open write store and transaction."""
    c = _candidate(store, candidate_id)
    if c["state"] not in allowed:
        raise ValidationError(f"expected a candidate that is {' or '.join(allowed)}; this one is {c['state']}")
    store.sales.set_candidate_state(c["candidate_id"], new_state)


def _move(input_dir: str | Path, candidate_id: int, allowed: tuple[str, ...], new_state: str) -> None:
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        move_in(store, candidate_id, allowed, new_state)


@_store_errors
def dismiss(input_dir: str | Path, candidate_id: int, *, reason: str) -> None:
    """``before_ledger_start`` / ``other`` -> ``dismissed``; ``not_a_sale`` -> ``not_a_sale``. State only."""
    if reason not in DISMISS_REASONS:
        raise ValidationError(f"reason must be one of {', '.join(DISMISS_REASONS)}")
    _move(input_dir, candidate_id, ("unmatched",), DISMISS_REASONS[reason])


@_store_errors
def restore(input_dir: str | Path, candidate_id: int) -> None:
    _move(input_dir, candidate_id, ("dismissed", "not_a_sale"), "unmatched")
