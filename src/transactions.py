"""Transaction log service (phase 2 of ``2026-10-31-transaction-log-design-and-plan.md``): open lots by replay, add,
revise (void and replace) and void. The replay is a pure function over lists so the negative-position rule is testable
on its own; writes happen only after the hypothetical log passes it.

Lots are created by ``buy``, ``reinvest``, ``transfer_in`` and ``opening`` rows; ``sell`` and ``transfer_out`` rows
consume them through ``transaction_lots``. Everything is judged by date, never by entry order, and on one day the
purchase counts before the sale.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from . import active_plan
from .sales_ledger import ValidationError

_EPS = 1e-6
LOT_TYPES_CREATING = ("buy", "reinvest", "transfer_in", "opening")   # rows that create a lot (see stores/transactions_repo)
DISPOSAL_TYPES = ("sell", "transfer_out")


def lot_date(row: Mapping[str, Any]) -> str:
    """The date a lot's holding period runs from: the origin purchase date on a transfer, else the row's own date."""
    return row.get("lot_date") or row["txn_date"]


def replay_errors(rows: Iterable[Mapping[str, Any]], disposals: Iterable[Mapping[str, Any]]) -> list[str]:
    """Problems in a hypothetical log. ``rows`` are active transaction rows; ``disposals`` are ``{txn_id, lot_txn_id,
    shares}``. A disposal must come from a lot of the same account and symbol that exists on the disposal date, and no
    lot may go negative."""
    rows = list(rows)
    by_id = {r["txn_id"]: r for r in rows}
    lots = {r["txn_id"]: r for r in rows if r["type"] in LOT_TYPES_CREATING}
    used: dict[int, float] = {}
    errors: list[str] = []
    for d in sorted(disposals, key=lambda d: (by_id[d["txn_id"]]["txn_date"], d["txn_id"])):
        sale = by_id.get(d["txn_id"])
        lot = lots.get(d["lot_txn_id"])
        if sale is None:
            continue
        label = f"the {sale['type'].replace('_', ' ')} of {sale['symbol']} on {sale['txn_date']}"
        if lot is None:
            errors.append(f"{label} uses a lot that is not in the log")
            continue
        if (lot["account"], lot["symbol"].upper()) != (sale["account"], sale["symbol"].upper()):
            errors.append(f"{label} uses a lot of a different account or symbol")
        elif lot["txn_date"] > sale["txn_date"]:
            errors.append(f"{label} comes before the purchase it uses ({lot['txn_date']})")
        used[lot["txn_id"]] = used.get(lot["txn_id"], 0.0) + float(d["shares"])
        if used[lot["txn_id"]] > float(lot["shares"]) + _EPS:
            errors.append(f"{label} would take more shares than the {lot['txn_date']} lot of {lot['symbol']} holds")
    for sale in rows:
        if sale["type"] in DISPOSAL_TYPES:
            got = sum(float(d["shares"]) for d in disposals if d["txn_id"] == sale["txn_id"])
            if abs(got - float(sale["shares"])) > _EPS:
                errors.append(f"the {sale['type'].replace('_', ' ')} of {sale['symbol']} on {sale['txn_date']} "
                              f"names lots for {got:g} of its {float(sale['shares']):g} shares")
    return errors


def _state(store: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = store.transactions.list()
    active = {r["txn_id"] for r in rows}
    return rows, [d for d in store.transactions.all_disposals() if d["txn_id"] in active]


def open_lots(store: Any, *, account: str | None = None, symbol: str | None = None,
              as_of: str | None = None) -> list[dict[str, Any]]:
    """Lots with shares left on ``as_of`` (default: after every active row), oldest first."""
    rows, disposals = _state(store)
    by_id = {r["txn_id"]: r for r in rows}
    left = {r["txn_id"]: float(r["shares"]) for r in rows if r["type"] in LOT_TYPES_CREATING
            and (as_of is None or r["txn_date"] <= as_of)}
    for d in disposals:
        if d["lot_txn_id"] in left and (as_of is None or by_id[d["txn_id"]]["txn_date"] <= as_of):
            left[d["lot_txn_id"]] -= float(d["shares"])
    from .wash_adjustments import by_lot
    adj = by_lot(store)
    out = []
    for lid, shares in left.items():
        r = by_id[lid]
        if shares <= _EPS or (account and r["account"] != account) or (symbol and r["symbol"].upper() != symbol.upper()):
            continue
        a = adj.get(lid)
        # the add-back is spread over the lot's shares (no share-level identification), so open shares carry their pro rata part
        per_share = (a["amount"] / float(r["shares"])) if a and float(r["shares"]) > _EPS else 0.0
        out.append({"lot_txn_id": lid, "account": r["account"], "symbol": r["symbol"], "purchase_date": lot_date(r),
                    "price": r["price"], "lot_type": r["lot_type"], "shares": round(shares, 6), "note": r["note"],
                    "date_not_on_file": r["source"] == "backfill" and r["type"] == "opening",   # the date came from the backfill, not a broker or the user
                    "wash_adjustment": round(per_share * shares, 2) if a else None,
                    "adjusted_unit_cost": float(r["price"] or 0.0) + per_share, "tacked_date": a["tacked"] if a else None})
    return sorted(out, key=lambda x: (x["account"], x["symbol"], x["purchase_date"], x["lot_txn_id"]))


def _fifo(store: Any, fields: Mapping[str, Any], *, exclude: int | None = None) -> dict[int, float]:
    """Oldest-first allocation of a sale from the lots open on its date, not counting the sale being replaced."""
    rows, disposals = _state(store)
    disposals = [d for d in disposals if d["txn_id"] != exclude]
    by_id = {r["txn_id"]: r for r in rows}
    left = {r["txn_id"]: float(r["shares"]) for r in rows if r["type"] in LOT_TYPES_CREATING
            and r["account"] == fields["account"] and r["symbol"].upper() == fields["symbol"].upper()
            and r["txn_date"] <= fields["txn_date"]}
    for d in disposals:
        if d["lot_txn_id"] in left:
            left[d["lot_txn_id"]] -= float(d["shares"])
    need, out = float(fields["shares"]), {}
    for lid in sorted(left, key=lambda i: (lot_date(by_id[i]), i)):
        take = min(need, max(left[lid], 0.0))
        if take > _EPS:
            out[lid] = take
            need -= take
    if need > _EPS:
        raise ValidationError(f"only {float(fields['shares']) - need:g} shares of {fields['symbol']} are open in "
                              f"{fields['account']} on {fields['txn_date']}")
    return out


def _check(rows: list[dict[str, Any]], disposals: list[dict[str, Any]]) -> None:
    errors = replay_errors(rows, disposals)
    if errors:
        raise ValidationError("; ".join(errors[:3]) + ("; undo the sale in the queue first" if "more shares" in " ".join(errors) else ""))


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def add(input_dir: str | Path, *, allocation: Mapping[int, float] | None = None, **fields: Any) -> int:
    """Add one row. A ``sell`` names its lots in ``allocation`` ({lot txn id: shares}); without it the oldest lots go first."""
    fields.setdefault("source", "manual")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        new_id = _add(store, fields, allocation)
        materialize_managed(store, [fields.get("account")])
        return new_id


def _add(store: Any, fields: dict[str, Any], allocation: Mapping[int, float] | None, *, revision_of: int | None = None) -> int:
    if fields.get("type") in DISPOSAL_TYPES and not allocation:
        allocation = _fifo(store, fields, exclude=revision_of)
    rows, disposals = _state(store)
    if revision_of is not None:
        rows = [r for r in rows if r["txn_id"] != revision_of]
        disposals = [d for d in disposals if d["txn_id"] != revision_of]
    probe = {**fields, "txn_id": -1, "shares": float(fields.get("shares") or 0), "lot_date": fields.get("lot_date")}
    if probe["shares"] <= 0:
        raise ValidationError("shares must be greater than zero")
    _check(rows + [probe], disposals + [{"txn_id": -1, "lot_txn_id": lid, "shares": s} for lid, s in (allocation or {}).items()])
    new_id = store.transactions.insert(**fields)
    for lid, shares in (allocation or {}).items():
        store.transactions.add_disposal(new_id, int(lid), float(shares))
    return new_id


def revise(input_dir: str | Path, txn_id: int, *, allocation: Mapping[int, float] | None = None, **changes: Any) -> int:
    """Void ``txn_id`` and add a corrected row that carries ``revision_ref``. A lot that later sales used keeps those
    sales; the change is refused if it would leave them short, naming the sale."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        old = store.transactions.get(txn_id)
        if old["status"] != "active":
            raise ValidationError("that transaction is already voided")
        fields = {k: old[k] for k in ("txn_date", "settle_date", "account", "type", "symbol", "shares", "price", "amount",
                                      "fees", "lot_type", "transfer_group", "lot_date", "origin_lot_txn_id", "source",
                                      "activity_id", "candidate_id", "note")}
        fields.update(changes)
        fields["revision_ref"] = txn_id
        if old["source"] == "broker" and not changes.get("note"):
            fields["note"] = (old["note"] + " " if old["note"] else "") + "revised from import"
        if old["type"] in LOT_TYPES_CREATING:   # sales that used this lot stay on it: validate with them pointed at a stand-in
            rows, disposals = _state(store)
            rows = [r for r in rows if r["txn_id"] != txn_id]
            stand_in = {**fields, "txn_id": -2, "shares": float(fields["shares"])}
            moved = [{**d, "lot_txn_id": -2} if d["lot_txn_id"] == txn_id else d for d in disposals]
            _check(rows + [stand_in], moved)
            store.transactions.void(txn_id)
            new_id = store.transactions.insert(**{**fields, "activity_id": None})
            store.transactions.repoint_disposals(txn_id, new_id)
            materialize_managed(store, [old["account"], fields["account"]])
            return new_id
        alloc = allocation
        if alloc is None and old["type"] in DISPOSAL_TYPES and all(fields[k] == old[k] for k in ("shares", "symbol", "account")) \
                and fields["txn_date"] == old["txn_date"]:
            alloc = {d["lot_txn_id"]: d["shares"] for d in store.transactions.disposals(txn_id)}
        new_id = _add(store, {**fields, "activity_id": None}, alloc, revision_of=txn_id)
        store.transactions.void(txn_id)
        materialize_managed(store, [old["account"], fields["account"]])
        return new_id


def transfer(input_dir: str | Path, *, from_account: str, to_account: str, symbol: str, allocation: Mapping[int, float],
             txn_date: str, note: str = "") -> dict[str, Any]:
    """Move shares in kind: a ``transfer_out`` in the source (consuming ``allocation`` = {lot txn id: shares}) and one
    ``transfer_in`` per lot in the destination that keeps the lot's purchase date, price and lot type. No sale, no
    ledger row. All of it is one transaction. ``flags`` lists anything to check (a change of tax class)."""
    from .broker_import import plan_accounts
    from .sales_confirm import default_tax_class
    allocation = {int(k): float(v) for k, v in (allocation or {}).items() if float(v) > 0}
    if not allocation:
        raise ValidationError("choose the lots to move")
    if from_account == to_account:
        raise ValidationError("the source and destination accounts are the same")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        if to_account not in plan_accounts(store):
            raise ValidationError(f"{to_account} is not an account in this plan")
        rows, disposals = _state(store)
        by_id = {r["txn_id"]: r for r in rows}
        missing = [lid for lid in allocation if lid not in by_id or by_id[lid]["type"] not in LOT_TYPES_CREATING]
        if missing:
            raise ValidationError("one of the chosen lots is not in the log")
        group = f"xfer-{txn_date}-{min(allocation)}-{len(rows)}"
        total = sum(allocation.values())
        out = {"txn_id": -1, "txn_date": txn_date, "account": from_account, "type": "transfer_out", "symbol": symbol, "shares": total}
        _check(rows + [out], disposals + [{"txn_id": -1, "lot_txn_id": lid, "shares": s} for lid, s in allocation.items()])
        out_id = store.transactions.insert(txn_date=txn_date, account=from_account, type="transfer_out", symbol=symbol,
                                           shares=total, source="manual", transfer_group=group, note=note)
        for lid, shares in allocation.items():
            store.transactions.add_disposal(out_id, lid, shares)
            lot = by_id[lid]
            store.transactions.insert(txn_date=txn_date, account=to_account, type="transfer_in", symbol=symbol, shares=shares,
                                      price=lot["price"], lot_type=lot["lot_type"], lot_date=lot_date(lot), source="manual",
                                      transfer_group=group, origin_lot_txn_id=lid, note=note)
        flags = []
        if default_tax_class(store, from_account) != default_tax_class(store, to_account):
            flags.append("The accounts have different tax treatment: check whether this is a conversion or a contribution; "
                         "the log does not model the tax.")
        materialize_managed(store, [from_account, to_account])
        return {"group": group, "transfer_out": out_id, "flags": flags}


def void(input_dir: str | Path, txn_id: int) -> None:
    """Void a row. A purchase that a later sale used is refused and the sale is named."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        row = store.transactions.get(txn_id)
        if row["status"] != "active":
            return
        rows, disposals = _state(store)
        rows = [r for r in rows if r["txn_id"] != txn_id]
        disposals = [d for d in disposals if d["txn_id"] != txn_id]
        if row["type"] in LOT_TYPES_CREATING and any(d["lot_txn_id"] == txn_id for d in disposals):
            sale = next(r for r in rows if r["txn_id"] in {d["txn_id"] for d in disposals if d["lot_txn_id"] == txn_id})
            raise ValidationError(f"the {sale['type'].replace('_', ' ')} of {sale['symbol']} on {sale['txn_date']} used this "
                                  f"lot; undo it in the queue first")
        store.transactions.void(txn_id)
        materialize_managed(store, [row["account"]])


# ------------------------------------------------------------------------------------------------ backfill, reconcile
_NO_DATE = "1900-01-01"
_OPENING_NOTE = "lot with no purchase on file"   # the log's own explanation; never copied into the holdings
_ZERO = 1e-6


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "") or 0)
    except ValueError:
        return 0.0


def _key(account: Any, symbol: Any, purchase_date: Any, price: Any, lot_type: Any = "") -> tuple:
    return (str(account).strip().lower(), str(symbol).strip().upper(), str(purchase_date or "") or _NO_DATE,
            round(_num(price), 6), str(lot_type or "").strip().lower())


def _holdings_by_key(store: Any) -> dict[tuple, dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    for h in store.dataset("holdings").rows():
        shares = _num(h.get("shares"))
        if shares <= _ZERO or not str(h.get("symbol", "")).strip() or not str(h.get("account", "")).strip():
            continue
        k = _key(h.get("account"), h.get("symbol"), h.get("purchase_date"), h.get("purchase_price"), h.get("lot_type"))
        slot = out.setdefault(k, {"account": h["account"], "symbol": h["symbol"], "purchase_date": h.get("purchase_date") or _NO_DATE,
                                  "price": round(_num(h.get("purchase_price")), 6), "lot_type": h.get("lot_type") or "", "shares": 0.0,
                                  "note": h.get("note") or ""})
        slot["shares"] += shares
    return out


def _log_by_key(store: Any) -> dict[tuple, dict[str, Any]]:
    out: dict[tuple, dict[str, Any]] = {}
    managed = {a.lower() for a in store.transactions.managed_accounts()}
    for lot in open_lots(store):
        adj = lot["account"].lower() in managed            # only a managed account's holdings carry the add-back and the tacked date
        k = _key(lot["account"], lot["symbol"], (lot["tacked_date"] if adj else None) or lot["purchase_date"],
                 lot["adjusted_unit_cost"] if adj else lot["price"], lot["lot_type"])
        slot = out.setdefault(k, {**lot, "shares": 0.0})
        slot["shares"] += lot["shares"]
    return out


def backfill(store: Any) -> dict[str, Any]:
    """Build the log from what exists, idempotently (call inside ``store.transaction()``). Broker buys and reinvestments
    whose lot reached the holdings, and broker sales that were confirmed, become rows; Monarch sales are skipped. Every
    open holdings lot the log cannot explain then gets an ``opening`` row, so ``open_lots`` equals the holdings."""
    from .broker_import import investment_accounts
    t = store.transactions
    investing = set(investment_accounts(store))      # a bank account never gets log rows
    done = {r["activity_id"] for r in t.list(include_voided=True) if r["activity_id"] is not None}
    added = {"buy": 0, "reinvest": 0, "sell": 0, "opening": 0}
    warnings: list[str] = []
    acts = store.broker.activity(kinds=("buy", "reinvest", "sell"))
    for a in acts:
        ref = a["lot_ref"]
        if a["kind"] in ("buy", "reinvest") and ref and not a["sweep"] and a["activity_id"] not in done:
            t.insert(txn_date=a["run_date"], settle_date=a["settle_date"], account=a["account"], type=a["kind"], symbol=a["symbol"],
                     shares=abs(a["quantity"] or 0.0) or 0.0, amount=a["amount"], lot_type=ref.get("lot_type") or "", note=ref.get("note") or "",
                     # the holdings lot's own price: a lot the import matched (not created) can differ by cents
                     price=_num(ref["purchase_price"]) if ref.get("purchase_price") not in (None, "") else a["price"],
                     lot_date=ref.get("purchase_date") if ref.get("purchase_date") not in (None, "", a["run_date"]) else None,
                     source="broker", activity_id=a["activity_id"])
            added[a["kind"]] += 1
    # confirmed broker orders: one sell row each, lots resolved from the ledger rows' lot keys
    cands = {c["candidate_id"]: c for c in store.sales.list_candidates()}
    by_cand: dict[int, list[dict[str, Any]]] = {}
    for a in acts:
        if a["kind"] == "sell" and not a["sweep"] and a["candidate_id"] in cands and cands[a["candidate_id"]]["state"] == "confirmed":
            by_cand.setdefault(a["candidate_id"], []).append(a)
    pending = {cid: group for cid, group in by_cand.items() if group[0]["activity_id"] not in done}
    sales_of = {cid: [s for s in (store.sales.get_sale(i) for i in cands[cid]["confirmed_sale_ids"]) if s["status"] == "confirmed"]
                for cid in pending}
    import json as _json
    lot_keys = {cid: [(_json.loads(s["lot_key"] or "{}"), s) for s in rows] for cid, rows in sales_of.items()}
    # holdings lots that sales consumed but the log does not know: open them with (shares now + shares sold)
    held, logged = _holdings_by_key(store), _log_by_key(store)
    def lot_k(lk: dict[str, Any], s: dict[str, Any]) -> tuple:
        return _key(s["account"], s["symbol"], lk.get("purchase_date") or s["purchase_date"],
                    lk.get("purchase_price", s["basis"] / s["shares"]), lk.get("lot_type"))
    need: dict[tuple, list] = {}
    for items in lot_keys.values():
        for lk, s in items:
            slot = need.setdefault(lot_k(lk, s), [0.0, s])
            slot[0] += float(s["shares"])
    for k, (sold, src) in need.items():
        missing = held.get(k, {}).get("shares", 0.0) + sold - logged.get(k, {}).get("shares", 0.0)
        if missing > _ZERO and src["account"] in investing:
            t.insert(txn_date=k[2], account=src["account"], type="opening", symbol=src["symbol"], shares=missing, price=k[3],
                     lot_type=k[4], source="backfill", note=_OPENING_NOTE)
            added["opening"] += 1
    for cid, group in pending.items():
        c = cands[cid]
        alloc: dict[int, float] = {}
        rows = store.transactions.list(account=c["account"], symbol=c["symbol"])
        for lk, s in lot_keys[cid]:
            k = lot_k(lk, s)
            need_sh = float(s["shares"])
            for r in sorted((r for r in rows if r["type"] in LOT_TYPES_CREATING
                             and _key(r["account"], r["symbol"], lot_date(r), r["price"], r["lot_type"]) == k), key=lambda r: r["txn_id"]):
                used = sum(d["shares"] for d in t.all_disposals() if d["lot_txn_id"] == r["txn_id"]) + alloc.get(r["txn_id"], 0.0)
                take = min(need_sh, float(r["shares"]) - used)
                if take > _ZERO:
                    alloc[r["txn_id"]] = alloc.get(r["txn_id"], 0.0) + take
                    need_sh -= take
            if need_sh > _ZERO:
                warnings.append(f"{c['symbol']} sale on {c['sale_date']}: {need_sh:g} shares could not be matched to a lot")
        total = sum(alloc.values())
        if total <= _ZERO:
            continue
        first = group[0]
        sid = t.insert(txn_date=first["run_date"], settle_date=first["settle_date"], account=c["account"], type="sell",
                       symbol=c["symbol"], shares=total, price=c["price"], amount=sum(g["amount"] for g in group),
                       source="broker", activity_id=first["activity_id"], candidate_id=cid)
        for lid, sh in alloc.items():
            t.add_disposal(sid, lid, sh)
        added["sell"] += 1
    # whatever the holdings still show that the log cannot explain
    held, logged = _holdings_by_key(store), _log_by_key(store)
    for k, h in held.items():
        short = h["shares"] - logged.get(k, {}).get("shares", 0.0)
        if short > _ZERO and h["account"] in investing:
            t.insert(txn_date=h["purchase_date"], account=h["account"], type="opening", symbol=h["symbol"], shares=short,
                     price=h["price"], lot_type=h["lot_type"], source="backfill", note=h["note"] or _OPENING_NOTE)
            added["opening"] += 1
    return {"added": added, "warnings": warnings}


def reconcile(store: Any, account: str | None = None) -> list[dict[str, Any]]:
    """Differences between the log's open lots and the holdings, with a plain reason. Empty means they agree. CASH lots are not compared."""
    held, logged = _holdings_by_key(store), _log_by_key(store)
    drift = []
    for k in sorted(set(held) | set(logged)):
        h, g = held.get(k), logged.get(k)
        if str((h or g)["symbol"]).strip().upper() == "CASH":
            continue                    # the CASH lot is the cash ledger's (imports and the owner write it); the log never owns it
        hs, gs = (h["shares"] if h else 0.0), (g["shares"] if g else 0.0)
        if abs(hs - gs) <= 1e-4:
            continue
        ref = h or g
        if account and ref["account"] != account:
            continue
        reason = ("the holdings have a lot the log does not (a hand-entered or edited lot)" if gs <= _ZERO else
                  "the log has a lot the holdings do not (it was sold or removed outside the log)" if hs <= _ZERO else
                  "the holdings have more shares than the log" if hs > gs else "the holdings have fewer shares than the log")
        drift.append({"account": ref["account"], "symbol": ref["symbol"], "purchase_date": ref.get("purchase_date"),
                      "price": ref.get("price"), "holdings_shares": round(hs, 6), "log_shares": round(gs, 6), "reason": reason})
    return drift


def started(store: Any) -> bool:
    """The log is in use once it has any row (after the first backfill or manual entry)."""
    return bool(store.transactions.list(include_voided=True))


def sync(store: Any) -> dict[str, Any]:
    """Bring the log in line with the importer and the queue (call inside the caller's transaction): void rows whose
    broker row is gone (import reverted) or whose sale was undone, then backfill what is new. Rows the user revised or
    voided by hand keep their activity link, so they are not logged again."""
    t = store.transactions
    acts = {a["activity_id"]: a for a in store.broker.activity()}
    cands = {c["candidate_id"]: c for c in store.sales.list_candidates()}
    for r in t.list():
        if r["source"] != "broker" or r["activity_id"] is None:
            continue
        a = acts.get(r["activity_id"])
        if a is None:
            t.release(r["txn_id"], "import reverted")
        elif r["type"] == "sell" and cands.get(a["candidate_id"], {}).get("state") != "confirmed":
            t.release(r["txn_id"], "sale undone")
    from .wash_adjustments import recompute_adjustments
    recompute_adjustments(store)                           # before the holdings are compared with the log
    out = backfill(store)
    materialize_managed(store)
    return out


def sync_if_started(store: Any) -> None:
    if started(store):
        sync(store)


def revised_rows(store: Any, activity_ids: Iterable[int]) -> list[dict[str, Any]]:
    """Log rows mirroring these broker rows that the user has since revised (voided and replaced)."""
    ids = set(activity_ids)
    rows = store.transactions.list(include_voided=True)
    replaced = {r["revision_ref"] for r in rows if r["revision_ref"] is not None}
    return [r for r in rows if r["activity_id"] in ids and r["txn_id"] in replaced]


# ------------------------------------------------------------------------------------------------ route helpers
def log_view(input_dir: str | Path, *, account: str | None = None, symbol: str | None = None, year: int | None = None) -> dict[str, Any]:
    """The log for the panel: whether it is in use, its rows (newest last), lots still open and any drift."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        managed = store.transactions.managed_accounts()
        if not started(store):
            return {"started": False, "rows": [], "open": [], "drift": [], "managed": managed}
        rows = store.transactions.list(account=account, symbol=symbol, year=year)
        sales = {r["txn_id"]: store.transactions.disposals(r["txn_id"]) for r in rows if r["type"] in DISPOSAL_TYPES}
        return {"started": True, "rows": [{**r, "lots": sales.get(r["txn_id"], [])} for r in rows],
                "open": open_lots(store, account=account, symbol=symbol), "drift": reconcile(store, account),
                "managed": managed}


def start_log(input_dir: str | Path) -> dict[str, Any]:
    """Run the backfill (idempotent) and return what it added."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        return backfill(store)


# ------------------------------------------------------------------------------------------------ materialize (phase 3)
def _fmt(x: float) -> str:
    return ("%.8f" % x).rstrip("0").rstrip(".") or "0"


def materialize(store: Any, account: str) -> int:
    """Rewrite ``account``'s rows in the holdings dataset from the log's open lots (call inside the caller's transaction).
    Every other account's rows and the account's own ``CASH`` lot (the cash ledger's) are untouched. The rewritten rows
    sit where the account's first old row was, ordered by symbol and purchase date. Returns the lot rows written."""
    repo = store.dataset("holdings")
    rows = repo.rows()
    mine = [i for i, r in enumerate(rows) if str(r.get("account", "")).strip().lower() == account.strip().lower()
            and str(r.get("symbol", "")).strip().upper() != "CASH"]
    new = [{"account": account, "symbol": l["symbol"], "purchase_date": "" if (l["tacked_date"] or l["purchase_date"]) == _NO_DATE else (l["tacked_date"] or l["purchase_date"]),
            "shares": _fmt(l["shares"]), "purchase_price": _fmt(float(l["adjusted_unit_cost"] or 0.0)), "lot_type": l["lot_type"], "note": "" if l["note"] == _OPENING_NOTE else l["note"] or ""}
           for l in open_lots(store, account=account) if l["symbol"].strip().upper() != "CASH"]
    at = mine[0] if mine else len(rows)
    kept_before = sum(1 for i in range(at) if i not in set(mine))
    rest = [r for i, r in enumerate(rows) if i not in set(mine)]
    repo.replace_all(rest[:kept_before] + new + rest[kept_before:])
    return len(new)


# ------------------------------------------------------------------------------------------------ managed accounts
def managed_accounts(store: Any) -> list[str]:
    return store.transactions.managed_accounts()


def is_managed(store: Any, account: str) -> bool:
    return store.transactions.is_managed(account)


def materialize_managed(store: Any, accounts: Iterable[Any] | None = None) -> int:
    """Rewrite the holdings of every managed account in ``accounts`` (default: all managed accounts); an unmanaged account
    is left alone. Call inside the transaction of the log write that changed the account."""
    from .wash_adjustments import recompute_adjustments
    recompute_adjustments(store)                      # W4: every log write, sale confirm or void, and review change lands here or in the wash refresh
    managed = store.transactions.managed_accounts()
    if not managed:
        return 0
    want = None if accounts is None else {str(a or "").strip().lower() for a in accounts}
    return sum(materialize(store, a) for a in managed if want is None or a.strip().lower() in want)


def set_managed(input_dir: str | Path, account: str, on: bool) -> dict[str, Any]:
    """Make the log the author of ``account``'s holdings (``on``) or stop (``off``: the last rows stay as they are).
    Turning on is refused while the log is not started or differs from the account's holdings, then rewrites the
    account's holdings once so a later write needs no first step."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        if not on:
            store.transactions.set_managed(account, False)
            return {"account": account, "managed": False, "rows": 0}
        from .broker_import import plan_accounts
        names = {a.lower(): a for a in plan_accounts(store)}
        if account.strip().lower() not in names:
            raise ValidationError(f"{account} is not an account in this plan")
        account = names[account.strip().lower()]
        if not started(store):
            raise ValidationError("start the transaction log before managing an account")
        drift = reconcile(store, account)
        if drift:
            raise ValidationError(f"the log and the holdings differ for {account} ({len(drift)} lot(s), first: {drift[0]['symbol']}); "
                                  "resolve the differences before managing it")
        store.transactions.set_managed(account, True)
        return {"account": account, "managed": True, "rows": materialize(store, account)}


def _bank_opening_rows(store: Any) -> dict[str, list[int]]:
    """``{account: [active opening txn_ids]}`` for log accounts that are not investment accounts (a bank account's CASH balance)."""
    from .broker_import import investment_accounts
    investing = set(investment_accounts(store))
    out: dict[str, list[int]] = {}
    for r in store.transactions.list():
        if r["account"] not in investing and r["type"] == "opening":
            out.setdefault(r["account"], []).append(r["txn_id"])
    return out


def bank_account_cleanup_preview(input_dir: str | Path) -> dict[str, Any]:
    """What the one-time cleanup would void: the opening rows of accounts that are not investment accounts."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        managed = {a.lower() for a in store.transactions.managed_accounts()}
        return {"accounts": [{"account": a, "managed": a.lower() in managed, "opening_rows": ids}
                             for a, ids in sorted(_bank_opening_rows(store).items())]}


def bank_account_cleanup_apply(input_dir: str | Path, accounts: list[str]) -> dict[str, Any]:
    """Void the opening rows of the named bank accounts. Order is fixed: stop managing the account first, then void, and
    never rewrite its holdings, so the account's CASH holding survives. Investment accounts are never touched."""
    wanted = {str(a).strip().lower() for a in (accounts or []) if str(a).strip()}
    if not wanted:
        raise ValidationError("name the accounts to clean up")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        found = {a: ids for a, ids in _bank_opening_rows(store).items() if a.lower() in wanted}
        managed = {a.lower() for a in store.transactions.managed_accounts()}
        unmanaged = []
        for account in sorted(found):
            if account.lower() in managed:
                store.transactions.set_managed(account, False)
                unmanaged.append(account)
        voided = 0
        for ids in found.values():
            for txn_id in ids:
                store.transactions.void(txn_id)
                voided += 1
    return {"voided": voided, "unmanaged": unmanaged}


def managed_view(input_dir: str | Path) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        return {"managed": store.transactions.managed_accounts()}
