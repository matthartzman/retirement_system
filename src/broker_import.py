"""Bulk import of a broker activity (all-transactions history) file: preview, commit, revert.

Buys and reinvestments become holdings lots (unless the lot is already there), sells become ``broker`` sale candidates
with same-day fills combined, and every row is stored for the income reconciliation (``broker_income``) and the
year-end 1099 checks. Commit can confirm the fully covered sales in bulk with a lot method the user picked in the
preview, through the same ``sales_confirm.confirm_in`` path as the queue panel. Design:
``documentation/future/superpowers/plans/2026-10-30-broker-activity-bulk-import-design-and-plan.md`` section 3.4.

Ledger convention: proceeds are the broker Amount (net of fees) with ``fees`` 0 on the ledger row, so the gain is
amount - basis; the fees stay on the candidate and the activity rows.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import active_plan, broker_activity
from .broker_activity.normalized import INCOME_KINDS, date_range, group_orders
from .sales_confirm import AIDS, _fmt, _holdings_lots, _num, confirm_in, default_tax_class, suggest_allocation
from .sales_ledger import ValidationError

LOT_DAY_TOLERANCE = 3
LOT_SHARE_TOLERANCE = 0.001
MONARCH_DAY_TOLERANCE = 3
MONARCH_AMOUNT_TOLERANCE = 1.0
_EPS = 1e-6


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _same(a: str, b: str) -> bool:
    return str(a or "").strip().lower() == str(b or "").strip().lower()


# ---------------------------------------------------------------------------------------------------- pure planning
def _match_existing_lot(row: Mapping[str, Any], lots: list[dict[str, Any]], claimed: set[int]) -> dict[str, Any] | None:
    """The holdings lot (unclaimed, same symbol, shares within 0.001, date within 3 days, nearest date first) that
    already records this buy/reinvest, else ``None``."""
    qty = abs(row["quantity"])
    cands = [l for l in lots if l["origin"] == "holdings" and l["index"] not in claimed and l["symbol"] == row["symbol"]
             and l["purchase_date"] and abs(l["orig_shares"] - qty) <= LOT_SHARE_TOLERANCE
             and _days(l["purchase_date"], row["run_date"]) <= LOT_DAY_TOLERANCE]
    cands.sort(key=lambda l: (_days(l["purchase_date"], row["run_date"]), l["index"]))
    return cands[0] if cands else None


def _allocation(method: str, shares: float, price: float | None, trade_date: str,
                lots: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """``suggest_allocation`` over the lots bought on or before ``trade_date`` (lots with no date are allowed)."""
    usable = [l for l in lots if l["remaining"] > _EPS and (not l.get("purchase_date") or l["purchase_date"] <= trade_date)]
    return suggest_allocation(method, shares, usable, price)


def plan_import(rows: list[dict[str, Any]], holdings: list[Mapping[str, Any]], *, account: str,
                method: str = "fifo") -> dict[str, Any]:
    """What committing ``rows`` (the new, not yet imported rows of one account) would do, replayed in date order over
    ``holdings`` (the plan's holdings rows). Pure. Buys on a date are applied before that date's sales."""
    if method not in AIDS:
        raise ValidationError(f"method must be one of {', '.join(AIDS)}")
    sim: list[dict[str, Any]] = []
    for i, r in enumerate(holdings):
        shares = _num(r.get("shares"))
        if not _same(r.get("account"), account) or shares <= _EPS:
            continue
        sim.append({"lot_id": str(i), "index": i, "origin": "holdings", "symbol": str(r.get("symbol", "")).strip().upper(),
                    "purchase_date": r.get("purchase_date") or "", "remaining": shares, "orig_shares": shares,
                    "basis_per_share": _num(r.get("purchase_price")), "holding_period": "unknown"})
    claimed: set[int] = set()
    lots_out: list[dict[str, Any]] = []
    for r in rows:
        if r["kind"] not in ("buy", "reinvest") or r["sweep"]:
            continue
        hit = _match_existing_lot(r, sim, claimed)
        entry = {"row_key": r["row_key"], "kind": r["kind"], "symbol": r["symbol"], "run_date": r["run_date"],
                 "shares": abs(r["quantity"]), "price": r["price"]}
        if hit is not None:
            claimed.add(hit["index"])
            entry.update(action="present", lot_index=hit["index"], lot_date=hit["purchase_date"],
                         lot_price=hit["basis_per_share"],
                         price_diff=round((r["price"] or 0.0) - hit["basis_per_share"], 4))
        else:
            entry.update(action="add")
            sim.append({"lot_id": f"new:{len(lots_out)}", "index": None, "origin": "import", "symbol": r["symbol"],
                        "purchase_date": r["run_date"], "remaining": abs(r["quantity"]), "orig_shares": abs(r["quantity"]),
                        "basis_per_share": r["price"] or 0.0, "holding_period": "unknown"})
        lots_out.append(entry)

    orders = group_orders(rows)
    for o in orders:
        lots = [l for l in sim if l["symbol"] == o["symbol"]]
        if not any(l["remaining"] > _EPS for l in lots):
            o.update(status="no_lots", allocation={}, lots_short=o["shares"])
            continue
        draft = _allocation(method, o["shares"], o["price"], o["trade_date"], lots)
        o.update(status="ready" if draft["complete"] else "short", allocation=draft["allocation"],
                 lots_short=round(o["shares"] - sum(draft["allocation"].values()), 6))
        if draft["complete"]:
            by_id = {l["lot_id"]: l for l in lots}
            o["lots"] = [{"lot_id": k, "shares": v, "purchase_date": by_id[k]["purchase_date"],
                          "basis_per_share": by_id[k]["basis_per_share"], "origin": by_id[k]["origin"]}
                         for k, v in draft["allocation"].items()]
            for k, v in draft["allocation"].items():
                by_id[k]["remaining"] -= v

    position: dict[str, dict[str, float]] = {}
    for l in sim:
        if l["origin"] == "holdings":
            position.setdefault(l["symbol"], {"now": 0.0, "bought": 0.0, "sold": 0.0})["now"] += l["orig_shares"]
    for e in lots_out:
        if e["action"] == "add":
            position.setdefault(e["symbol"], {"now": 0.0, "bought": 0.0, "sold": 0.0})["bought"] += e["shares"]
    for o in orders:
        position.setdefault(o["symbol"], {"now": 0.0, "bought": 0.0, "sold": 0.0})["sold"] += o["shares"]
    checks = []
    for sym in sorted(position):
        p = position[sym]
        after = round(p["now"] + p["bought"] - p["sold"], 6)
        checks.append({"symbol": sym, "holdings_now": round(p["now"], 6), "bought": round(p["bought"], 6),
                       "sold": round(p["sold"], 6), "after": after, "negative": after < -LOT_SHARE_TOLERANCE})

    income = [r for r in rows if r["kind"] in INCOME_KINDS]
    totals: dict[str, float] = {}
    for r in income:
        totals[r["kind"]] = round(totals.get(r["kind"], 0.0) + r["amount"], 2)
    other = [r for r in rows if r["kind"] == "other" or (r["sweep"] and r["kind"] in ("buy", "sell", "reinvest"))]
    return {"lots": lots_out, "orders": orders, "position": checks, "income": income, "income_totals": totals,
            "ignored": [{"run_date": r["run_date"], "action": r["action"], "amount": r["amount"]} for r in other]}


# ---------------------------------------------------------------------------------------------------- service helpers
def _monarch_accounts(store, account: str) -> set[str]:
    """Monarch account names that the YTD account setup maps to plan ``account`` (lower case)."""
    out = set()
    for r in store.dataset("ytd_account_setup").rows():
        if _same(r.get("Mapped Investment Account"), account):
            out.add(str(r.get("Account") or "").strip().lower())
    return out


def _covered_monarch(store, account: str, orders: list[Mapping[str, Any]]) -> list[dict[str, int]]:
    """Unmatched Monarch sell candidates that a broker order covers (mapped account, same symbol or a bare row,
    proceeds within $1, date within 3 days), one-to-one, nearest date first."""
    names = _monarch_accounts(store, account) | {account.strip().lower()}
    free = [c for c in store.sales.list_candidates(state="unmatched")
            if c["source"] == "monarch" and str(c["account"]).strip().lower() in names]
    out = []
    for i, o in enumerate(orders):
        fits = [c for c in free if (not c["symbol"] or c["symbol"] == o["symbol"]) and c["amount"] is not None
                and abs(float(c["amount"]) - o["proceeds"]) <= MONARCH_AMOUNT_TOLERANCE
                and _days(c["sale_date"], o["trade_date"]) <= MONARCH_DAY_TOLERANCE]
        if fits:
            best = min(fits, key=lambda c: (_days(c["sale_date"], o["trade_date"]), c["candidate_id"]))
            free.remove(best)
            out.append({"order": i, "candidate_id": best["candidate_id"]})
    return out


def plan_accounts(store) -> list[str]:
    names = {str(r.get("account") or "").strip() for r in store.dataset("holdings").rows()}
    names |= {str(r.get("Mapped Investment Account") or "").strip() for r in store.dataset("ytd_account_setup").rows()}
    return sorted(n for n in names if n and "_" in n)


def _coverage(store, account: str, broker: str, first: str | None, last: str | None) -> list[str]:
    prior = [i for i in store.broker.list_imports(account=account) if i["status"] == "applied" and i["broker"] == broker]
    if not prior or not first:
        return []
    latest = max(i["date_to"] or "" for i in prior)
    earliest = min(i["date_from"] or "9999" for i in prior)
    warnings = []
    if latest and first > latest and _days(first, latest) > 7:
        warnings.append(f"Gap: earlier imports of this account end {latest}; this file starts {first}.")
    if earliest and last and last < earliest and _days(earliest, last) > 7:
        warnings.append(f"Gap: this file ends {last}; earlier imports of this account start {earliest}.")
    return warnings


def _part(store, broker: str, hint: str, account: str, rows: list[dict[str, Any]], method: str) -> dict[str, Any]:
    """The plan for one plan account: ``rows`` are that account's parsed rows (not yet keyed)."""
    broker_activity.assign_row_keys(rows, broker=broker, account=account)
    have = store.broker.existing_keys([r["row_key"] for r in rows])
    new = [r for r in rows if r["row_key"] not in have]
    plan = plan_import(new, store.dataset("holdings").rows(), account=account, method=method)
    first, last = date_range(rows)
    warnings = _coverage(store, account, broker, first, last)
    warnings += [f"{p['symbol']}: the holdings would end at {p['after']:g} shares. They may already reflect some of "
                 "these sales; check before confirming." for p in plan["position"] if p["negative"]]
    return {"hint": hint, "account": account, "tax_class": default_tax_class(store, account), "received": len(rows),
            "already_imported": len(have), "will_write": new, "date_from": first, "date_to": last, "warnings": warnings,
            "monarch_covered": _covered_monarch(store, account, plan["orders"]), **plan,
            "counts": {"lots_add": sum(1 for l in plan["lots"] if l["action"] == "add"),
                       "lots_present": sum(1 for l in plan["lots"] if l["action"] == "present"),
                       "orders": len(plan["orders"]),
                       "orders_ready": sum(1 for o in plan["orders"] if o["status"] == "ready"),
                       "income_rows": len(plan["income"])}}


def _tag(items: Iterable[Mapping[str, Any]], account: str) -> list[dict[str, Any]]:
    return [{**i, "account": account} for i in items]


def _report(store, broker: str, text: str, file_name: str | None, account: str | None,
            accounts: Mapping[str, str] | None, method: str, history_only: Iterable[str] = ()) -> dict[str, Any]:
    """Preview of a file. A file holds one or several accounts (``hint`` per row); each distinct hint is mapped to a
    plan account: ``accounts[hint]``, else ``account`` when the file has a single hint, else the remembered mapping."""
    broker = (broker or "").strip().lower()
    if broker in ("", "auto"):
        broker = broker_activity.detect_broker(text, file_name) or ""
    base = {"schema": "import_preview_v1", "kind": "broker_activity", "broker": broker, "file_name": file_name or "",
            "brokers": [{"id": b, "label": broker_activity.BROKER_LABELS.get(b, b)} for b in broker_activity.available_brokers()],
            "accounts": plan_accounts(store), "methods": list(AIDS), "method": method}
    if not broker:
        return {**base, "account": None, "account_hint": None, "hints": [], "needs_account": False, "received": 0,
                "will_write": [], "warnings": [], "parts": [],
                "errors": [{"line": 0, "error": "This file's layout is not recognized; choose the broker."}]}
    parsed = broker_activity.parse_raw(broker, text, file_name=file_name)
    file_hint = parsed.meta.get("account_hint") or broker_activity.account_hint(broker, file_name)

    def hint_of(r: Mapping[str, Any]) -> str:
        return r.get("account_hint") or file_hint or ""

    hints = broker_activity.row_hints(parsed.rows, file_hint) or [file_hint or ""]
    chosen = {}
    for h in hints:
        chosen[h] = (((accounts or {}).get(h) or "").strip() or ((account or "").strip() if len(hints) == 1 else "")
                     or store.broker.account_for(h) or "")
    hint_rows = [{"hint": h, "account": chosen[h] or None, "rows": sum(1 for r in parsed.rows if hint_of(r) == h)}
                 for h in hints]
    base.update(account_hint=hints[0] or None, hints=hint_rows)
    if parsed.errors and not parsed.rows:
        return {**base, "account": None, "needs_account": False, "received": 0, "will_write": [],
                "warnings": list(parsed.warnings), "errors": list(parsed.errors), "parts": []}
    if not all(chosen.values()):
        msg = ("Choose the plan account this file belongs to." if len(hints) == 1
               else "Choose a plan account for each account in this file.")
        return {**base, "account": None, "needs_account": True, "received": len(parsed.rows), "will_write": [],
                "warnings": [], "errors": [{"line": 0, "error": msg}], "parts": []}
    parts = [_part(store, broker, h, chosen[h], [r for r in parsed.rows if hint_of(r) == h], method) for h in hints]
    first, last = date_range(parsed.rows)
    only = {str(a).strip().lower() for a in history_only or ()}
    for p in parts:
        p["history_only"] = p["account"].strip().lower() in only
        if p["history_only"]:
            p["warnings"] = [f"History only: lots are not added or reduced and no sales are queued for {p['account']}; "
                             "its sales are kept as activity rows."]
    totals: dict[str, float] = {}
    for p in parts:
        for k, v in p["income_totals"].items():
            totals[k] = round(totals.get(k, 0.0) + v, 2)
        for m in p["monarch_covered"]:
            m["account"] = p["account"]
    many = len(parts) > 1
    return {**base, "account": ", ".join(p["account"] for p in parts), "needs_account": False,
            "tax_class": None if many else parts[0]["tax_class"], "parts": parts,
            "received": len(parsed.rows), "already_imported": sum(p["already_imported"] for p in parts),
            "will_write": [r for p in parts for r in p["will_write"]], "date_from": first, "date_to": last,
            "errors": list(parsed.errors),
            "warnings": list(parsed.warnings) + [f"{p['account']}: {w}" if many else w for p in parts for w in p["warnings"]],
            "monarch_covered": [m for p in parts for m in p["monarch_covered"]],
            "lots": [l for p in parts for l in _tag(p["lots"], p["account"])],
            "orders": [o for p in parts for o in _tag(p["orders"], p["account"])],
            "position": [c for p in parts for c in _tag(p["position"], p["account"])],
            "income": [i for p in parts for i in _tag(p["income"], p["account"])], "income_totals": totals,
            "ignored": [i for p in parts for i in _tag(p["ignored"], p["account"])],
            "counts": {k: sum(p["counts"][k] for p in parts) for k in parts[0]["counts"]}}


# ---------------------------------------------------------------------------------------------------- service
def preview(input_dir: str | Path, *, broker: str = "", text: str, file_name: str | None = None,
            account: str | None = None, accounts: Mapping[str, str] | None = None, method: str = "fifo",
            history_only: Iterable[str] = ()) -> dict[str, Any]:
    """Side-effect-free report of what ``commit`` would do (``import_preview_v1`` style). An empty ``broker`` is
    recognized from the file's header."""
    with active_plan.workspace_store(_base(input_dir)) as store:
        return _report(store, broker, text, file_name, account, accounts, method, history_only)


def commit(input_dir: str | Path, *, broker: str = "", text: str, file_name: str | None = None, account: str = "",
           accounts: Mapping[str, str] | None = None, confirm_method: str | None = None,
           history_only: Iterable[str] = ()) -> dict[str, Any]:
    """Store the file's new rows, add the new lots, queue the sale orders, supersede covered Monarch candidates and,
    when ``confirm_method`` is given, confirm every fully covered order with that method. Each account in the file gets
    its own import record; all of it is one transaction: any failure changes nothing. A file with error rows is
    refused whole. Accounts named in ``history_only`` are for holdings that already reflect the file: their rows (income,
    trades) are stored for the income check and the record, but no lot is added or reduced and no sale is queued."""
    if confirm_method is not None and confirm_method not in AIDS:
        raise ValidationError(f"confirm_method must be one of {', '.join(AIDS)}")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        rep = _report(store, broker, text, file_name, account, accounts, confirm_method or "fifo", history_only)
        if rep["needs_account"]:
            raise ValidationError(rep["errors"][0]["error"])
        if rep["errors"]:
            raise ValidationError("; ".join(f"line {e['line']}: {e['error']}" for e in rep["errors"]))
        broker = rep["broker"]
        label = broker_activity.BROKER_LABELS.get(broker, broker)
        out = {"import_ids": [], "rows_new": 0, "lots_added": 0, "lots_present": 0, "candidates": [], "confirmed": [],
               "queued": [], "superseded_monarch": []}
        for part in rep["parts"]:
            res = _commit_part(store, broker, label, part, file_name, confirm_method)
            out["import_ids"].append(res["import_id"])
            for k in ("rows_new", "lots_added", "lots_present"):
                out[k] += res[k]
            for k in ("candidates", "confirmed", "queued", "superseded_monarch"):
                out[k] += res[k]
    return {"import_id": out["import_ids"][0], "account": rep["account"], **out}


def _commit_part(store, broker: str, label: str, rep: dict[str, Any], file_name: str | None,
                 confirm_method: str | None) -> dict[str, Any]:
    """Apply one account's part of a report (lots, sale candidates, rows) inside the caller's transaction."""
    account = rep["account"]
    new = rep["will_write"]
    holdings = store.dataset("holdings")
    hrows = holdings.rows()
    by_key = {r["row_key"]: {**r, "broker": broker, "account": account} for r in new}
    history = bool(rep.get("history_only"))
    for lot in ([] if history else rep["lots"]):
        row = by_key[lot["row_key"]]
        if lot["action"] == "add":
            ident = {"account": account, "symbol": lot["symbol"], "purchase_date": lot["run_date"],
                     "purchase_price": _fmt(lot["price"] or 0.0),
                     "lot_type": "reinvestment" if lot["kind"] == "reinvest" else "buy",
                     "note": f"{label} {lot['kind']} {lot['run_date']}"}
            hrows.append({**ident, "shares": _fmt(lot["shares"])})
            row["lot_ref"] = {"created": True, **ident, "shares": _fmt(lot["shares"])}
        else:
            h = hrows[lot["lot_index"]]
            row["lot_ref"] = {"created": False, **{k: h.get(k, "") for k in
                              ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")}}
    if not history:
        holdings.replace_all(hrows)

    candidate_ids = []
    for o in ([] if history else rep["orders"]):
        cid, _ = store.sales.add_candidate(source="broker", sale_date=o["trade_date"], account=account,
                                           symbol=o["symbol"], shares=o["shares"], price=o["price"],
                                           amount=o["proceeds"], fees=o["fees"], settle_date=o["settle_date"],
                                           broker_key=o["row_keys"][0])
        candidate_ids.append(cid)
        for k in o["row_keys"]:
            by_key[k]["candidate_id"] = cid
    for m in ([] if history else rep["monarch_covered"]):
        store.sales.set_candidate_state(m["candidate_id"], "superseded")

    import_id = store.broker.add_import(
        broker=broker, account=account, file_name=file_name or "", date_from=rep["date_from"], date_to=rep["date_to"],
        rows_total=rep["received"], rows_new=len(new),
        summary={**rep["counts"], "income_totals": rep["income_totals"], "history_only": history,
                 "history_sales": [{"date": o["trade_date"], "symbol": o["symbol"], "shares": o["shares"],
                                    "proceeds": o["proceeds"]} for o in rep["orders"]] if history else [],
                 "superseded_monarch": [] if history else [m["candidate_id"] for m in rep["monarch_covered"]]})
    store.broker.add_rows(import_id, [by_key[r["row_key"]] for r in new])
    store.broker.remember_account(rep["hint"], account)

    confirmed, left = [], []
    if confirm_method is not None:
        for o, cid in sorted(zip(rep["orders"], candidate_ids), key=lambda x: x[0]["trade_date"]):
            if o["status"] != "ready":
                left.append(cid)
                continue
            lots = _holdings_lots(store, account, o["symbol"], o["trade_date"], o["price"])
            draft = _allocation(confirm_method, o["shares"], o["price"], o["trade_date"], lots)
            if not draft["complete"]:
                left.append(cid)
                continue
            confirm_in(store, cid, allocation=draft["allocation"], tax_class=rep["tax_class"], trade_date=o["trade_date"],
                       proceeds=o["proceeds"])
            confirmed.append(cid)
    else:
        left = candidate_ids
    return {"import_id": import_id, "rows_new": len(new), "lots_added": 0 if history else rep["counts"]["lots_add"],
            "lots_present": 0 if history else rep["counts"]["lots_present"], "candidates": candidate_ids,
            "confirmed": confirmed, "queued": left,
            "superseded_monarch": [] if history else [m["candidate_id"] for m in rep["monarch_covered"]]}


def revert(input_dir: str | Path, import_id: int) -> dict[str, Any]:
    """Undo an import while none of its sales is confirmed and each lot it created still has its original shares."""
    keys = ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        imp = store.broker.get_import(int(import_id))
        if imp["status"] != "applied":
            raise ValidationError("this import is already reverted")
        rows = store.broker.activity(import_id=imp["import_id"])
        cands = {c["candidate_id"]: c for c in store.sales.list_candidates()}
        cids = sorted({r["candidate_id"] for r in rows if r["candidate_id"] is not None})
        if any(cands.get(c, {}).get("state") == "confirmed" for c in cids):
            raise ValidationError("some sales from this import are confirmed; undo them in the queue first")
        holdings = store.dataset("holdings")
        hrows = holdings.rows()
        for r in rows:
            ref = r["lot_ref"]
            if not ref or not ref.get("created"):
                continue
            hit = next((i for i, h in enumerate(hrows) if all(h.get(k, "") == ref[k] for k in keys)
                        and abs(_num(h.get("shares")) - _num(ref["shares"])) <= _EPS), None)
            if hit is None:
                raise ValidationError(f"the {ref['symbol']} lot of {ref['purchase_date']} added by this import has "
                                      "changed since; fix it in the holdings first")
            hrows.pop(hit)
        holdings.replace_all(hrows)
        for c in cids:
            if c in cands:
                store.sales.delete_candidate(c)
        for c in imp["summary"].get("superseded_monarch", []):
            if cands.get(c, {}).get("state") == "superseded":
                store.sales.set_candidate_state(c, "unmatched")
        store.broker.delete_import_rows(imp["import_id"])
        store.broker.set_import_status(imp["import_id"], "reverted")
    return {"import_id": imp["import_id"], "reverted": True}


def list_imports(input_dir: str | Path, *, account: str | None = None) -> dict[str, Any]:
    with active_plan.workspace_store(_base(input_dir)) as store:
        return {"imports": store.broker.list_imports(account=account), "brokers": broker_activity.available_brokers(),
                "accounts": plan_accounts(store)}
