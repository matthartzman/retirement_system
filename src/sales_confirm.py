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

from . import active_plan
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


def _default_tax_class(store, account: str) -> str:
    for r in reversed(store.sales.list_sales(include_voided=True)):
        if r["account"].strip().lower() == account.strip().lower():
            return r["tax_class"]
    return "taxable"


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
        lots = _holdings_lots(store, c["account"], sym, trade, price) if sym else []
        tax_class = _default_tax_class(store, c["account"])
    exact = [l["lot_id"] for l in lots if qty and abs(l["remaining"] - qty) <= _EPS]
    refusal = "its lots were already removed by the holdings import; record it with manual entry, then dismiss it" \
        if c["source"] == "holdings_diff" else None
    return {
        "candidate": c, "symbol": sym, "shares": qty, "price": price, "lots": lots, "allocation": {},
        "suggested_trade_date": trade, "settle_date": c["sale_date"] if monarch else None,
        "year_end_case": monarch and trade[:4] != c["sale_date"][:4], "tax_class": tax_class,
        "only_exact_fit": exact[0] if len(exact) == 1 else None, "confirmable": refusal is None, "refusal": refusal,
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
        lots = _holdings_lots(store, c["account"], sym, trade_date, None)
        picked = allocate_lots(qty, [{"lot_key": l["lot_id"], "remaining": l["remaining"]} for l in lots],
                              {str(k): v for k, v in allocation.items()})
        repo = store.dataset("holdings")
        rows = repo.rows()
        sale_rows, remaining_total = [], float(total)
        order = sorted(picked, key=int)
        for n, lot_id in enumerate(order):
            r = rows[int(lot_id)]
            q = picked[lot_id]
            part = remaining_total if n == len(order) - 1 else round(float(total) * q / qty, 6)
            remaining_total -= part
            ident = {k: r.get(k, "") for k in ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")}
            sale_rows.append(validate_sale_row({
                "sale_date": trade_date, "settle_date": c["sale_date"] if c["source"] == "monarch" else None,
                "account": c["account"], "tax_class": tax_class, "symbol": sym, "shares": q, "proceeds": part,
                "fees": fees * q / qty, "basis": q * _num(r.get("purchase_price")),
                "purchase_date": r.get("purchase_date") or None, "source": c["source"], "monarch_id": c["monarch_id"],
                "lot_key": json.dumps({**ident, "index": int(lot_id), "orig_shares": r.get("shares", "")}, sort_keys=True)}))
        for lot_id in order:
            left = _num(rows[int(lot_id)]["shares"]) - picked[lot_id]
            rows[int(lot_id)]["shares"] = _fmt(left) if left > _EPS else None
        repo.replace_all([r for r in rows if r.get("shares") is not None])
        ids = []
        for row in sale_rows:
            row.pop("status", None)
            ids.append(store.sales.insert_sale(**row))
        store.sales.set_candidate_state(c["candidate_id"], "confirmed", confirmed_sale_ids=ids)
    return {"sale_ids": ids}


@_store_errors
def undo(input_dir: str | Path, candidate_id: int) -> None:
    """Void the candidate's rows, give the shares back to their lots and return it to ``unmatched``. Locked once any of
    its rows carries 1099-B (``official_*``) numbers."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        c = _candidate(store, candidate_id)
        if c["state"] != "confirmed":
            raise ValidationError(f"only a confirmed sale can be undone (this one is {c['state']})")
        sales = [store.sales.get_sale(i) for i in c["confirmed_sale_ids"]]
        if any(s["official_proceeds"] is not None or s["official_basis"] is not None or s["official_gain"] is not None
               for s in sales):
            raise ValidationError("a 1099-B was applied to this sale; edit it through the 1099-B import instead")
        repo = store.dataset("holdings")
        rows = repo.rows()
        for s in sorted(sales, key=lambda s: json.loads(s["lot_key"])["index"]):
            lot = json.loads(s["lot_key"])
            same = ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")
            hit = next((r for r in rows if all(r.get(k, "") == lot[k] for k in same)), None)
            if hit is None:
                rows.insert(min(lot["index"], len(rows)), {**{k: lot[k] for k in same}, "shares": _fmt(s["shares"])})
                if abs(s["shares"] - _num(lot["orig_shares"])) <= _EPS:
                    rows[min(lot["index"], len(rows) - 1)]["shares"] = lot["orig_shares"]
            else:
                back = _num(hit["shares"]) + s["shares"]
                hit["shares"] = lot["orig_shares"] if abs(back - _num(lot["orig_shares"])) <= _EPS else _fmt(back)
            store.sales.void_sale(s["sale_id"])
        repo.replace_all(rows)
        store.sales.set_candidate_state(c["candidate_id"], "unmatched")


def _move(input_dir: str | Path, candidate_id: int, allowed: tuple[str, ...], new_state: str) -> None:
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        c = _candidate(store, candidate_id)
        if c["state"] not in allowed:
            raise ValidationError(f"expected a candidate that is {' or '.join(allowed)}; this one is {c['state']}")
        store.sales.set_candidate_state(c["candidate_id"], new_state)


@_store_errors
def dismiss(input_dir: str | Path, candidate_id: int, *, reason: str) -> None:
    """``before_ledger_start`` / ``other`` -> ``dismissed``; ``not_a_sale`` -> ``not_a_sale``. State only."""
    if reason not in DISMISS_REASONS:
        raise ValidationError(f"reason must be one of {', '.join(DISMISS_REASONS)}")
    _move(input_dir, candidate_id, ("unmatched",), DISMISS_REASONS[reason])


@_store_errors
def restore(input_dir: str | Path, candidate_id: int) -> None:
    _move(input_dir, candidate_id, ("dismissed", "not_a_sale"), "unmatched")
