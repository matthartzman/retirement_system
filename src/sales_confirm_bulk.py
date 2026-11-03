"""Bulk review of queued sales (ledger plan 6 item 6 and 6.1): review many unmatched candidates at once, validate every
allocation, then confirm, dismiss or undo them in one call with a result per item.

Each bulk call is one plan-file transaction in which every item runs in its own savepoint: an item that fails is rolled
back and reported, and does not stop the others. Items run in order against the same holdings, so two sales drawing on
one lot see each other (the second only gets what the first left). ``validate`` runs the exact confirm path and rolls
everything back, so what it reports is what ``confirm`` will do. The batch Undo is ``undo`` over the confirmed ids,
newest first, which restores lots in the reverse order they were taken. Single-sale rules live in ``sales_confirm``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import active_plan, transactions
from .sales_confirm import DISMISS_REASONS, _base, _candidate, _store_errors, confirm_in, move_in, panel, undo_in
from .sales_ledger import ValidationError

MAX_ITEMS = 500


class _DryRun(Exception):
    """Raised after a validation pass so the outer transaction rolls everything back."""


def _ids(candidate_ids: Any) -> list[int]:
    if not isinstance(candidate_ids, (list, tuple)) or not candidate_ids:
        raise ValidationError("choose at least one sale")
    if len(candidate_ids) > MAX_ITEMS:
        raise ValidationError(f"at most {MAX_ITEMS} sales can be handled in one batch")
    try:
        out = [int(i) for i in candidate_ids]
    except (TypeError, ValueError):
        raise ValidationError("sale ids must be whole numbers") from None
    if len(set(out)) != len(out):
        raise ValidationError("a sale appears more than once in the batch")
    return out


def _float(v: Any, name: str) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number") from None


def _confirm_kwargs(item: Mapping[str, Any]) -> dict[str, Any]:
    alloc = item.get("allocation") or {}
    if not isinstance(alloc, Mapping):
        raise ValidationError("allocation must map lot ids to shares")
    kw: dict[str, Any] = {"allocation": {str(k): _float(v, "allocation") or 0.0 for k, v in alloc.items()},
                          "tax_class": str(item.get("tax_class") or ""), "trade_date": str(item.get("trade_date") or ""),
                          "symbol": item.get("symbol") or None}
    for name in ("fees", "proceeds", "shares"):
        v = _float(item.get(name), name)
        if v is not None:
            kw[name] = v
    return kw


def _run(input_dir: str | Path, ids: Sequence[int], step: Callable[[Any, int, _Lots], Any], *, dry: bool) -> list[dict[str, Any]]:
    """``step(store, candidate_id, lots)`` per id, each in its own savepoint; ``dry`` rolls the whole batch back."""
    results: list[dict[str, Any]] = []
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
            lots = _Lots(store)
            for cid in ids:
                try:
                    with store.transaction():
                        out = step(store, cid, lots)
                    results.append({"candidate_id": cid, "ok": True, **(out or {})})
                except (ValidationError, active_plan.StoreError) as exc:
                    results.append({"candidate_id": cid, "ok": False, "error": str(exc)})
            if dry:
                raise _DryRun
    except _DryRun:
        pass
    return results


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    ok = sum(1 for r in results if r["ok"])
    return {"results": results, "succeeded": ok, "failed": len(results) - ok}


@_store_errors
def review(input_dir: str | Path, candidate_ids: Sequence[int]) -> dict[str, Any]:
    """Read-only: per candidate the single-sale panel plus a draft allocation, FIFO when the lots cover the sale, else
    empty. The aids stay in each item so the UI can offer them as chips; nothing is saved."""
    items = []
    for cid in _ids(candidate_ids):
        try:
            p = panel(input_dir, cid)
            if p["candidate"]["state"] != "unmatched":
                raise ValidationError(f"only an unmatched sale can be reviewed (this one is {p['candidate']['state']})")
        except ValidationError as exc:
            items.append({"candidate_id": cid, "ok": False, "error": str(exc)})
            continue
        fifo = p["aids"].get("fifo")
        draft = dict(fifo["allocation"]) if fifo and fifo["complete"] and p["confirmable"] else {}
        items.append({**p, "candidate_id": cid, "ok": True, "method": "fifo" if draft else None, "allocation": draft})
    return {"items": items}


_IDENT = ("account", "symbol", "purchase_date", "purchase_price", "lot_type", "note")


def _idents(store) -> list[tuple]:
    return [tuple(str(r.get(k) or "") for k in _IDENT) for r in store.dataset("holdings").rows()]


class _Lots:
    """Holdings lot ids are row indexes, and a sale that empties a lot removes its row, shifting every later index. The
    ids in a batch are the ones the review showed (the holdings as they were when the batch began), so each is
    translated to the lot's current row by its identity before it is used. ``gone`` holds the emptied lots."""

    def __init__(self, store) -> None:
        self.snap = _idents(store)
        self.gone: set[int] = set()

    def current(self, cur: list[tuple], sid: int) -> int | None:
        key = self.snap[sid]
        rank = sum(1 for j in range(sid) if self.snap[j] == key and j not in self.gone)
        spots = [j for j, k in enumerate(cur) if k == key]
        return spots[rank] if sid not in self.gone and rank < len(spots) else None

    def translate(self, store, alloc: Mapping[str, float]) -> tuple[dict[str, float], dict[str, int]]:
        cur, out, back = _idents(store), {}, {}
        for lot_id, q in alloc.items():
            sid = int(lot_id) if str(lot_id).isdigit() else -1
            now = self.current(cur, sid) if 0 <= sid < len(self.snap) else None
            key = str(now) if now is not None else str(lot_id) if sid >= len(self.snap) else "-1"
            out[key] = q
            if now is not None:
                back[str(now)] = sid
        return out, back


def _confirm_step(store, cid: int, item: Mapping[str, Any], lots: _Lots) -> dict[str, Any]:
    kw = _confirm_kwargs(item)
    back: dict[str, int] = {}
    if not transactions.is_managed(store, _candidate(store, cid)["account"]):
        kw["allocation"], back = lots.translate(store, kw["allocation"])
    out = confirm_in(store, cid, **kw)
    transactions.sync_if_started(store)
    lots.gone.update(back[i] for i in out.pop("removed_lots", ()) if i in back)
    return out


def _items(items: Any) -> dict[int, Mapping[str, Any]]:
    if not isinstance(items, (list, tuple)):
        raise ValidationError("items must be a list")
    ids = _ids([i.get("candidate_id") if isinstance(i, Mapping) else None for i in items])
    return dict(zip(ids, items))


@_store_errors
def validate(input_dir: str | Path, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Check every item exactly as ``confirm`` would, in order, and change nothing."""
    by_id = _items(items)
    return _summary(_run(input_dir, list(by_id), lambda s, cid, lots: _confirm_step(s, cid, by_id[cid], lots), dry=True))


@_store_errors
def confirm(input_dir: str | Path, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Confirm each item (``candidate_id`` plus the single-sale ``confirm`` fields). Failing items are reported and
    skipped; ``confirmed`` lists the ids that went through, in order, which is what ``undo`` takes."""
    by_id = _items(items)
    out = _summary(_run(input_dir, list(by_id), lambda s, cid, lots: _confirm_step(s, cid, by_id[cid], lots), dry=False))
    out["confirmed"] = [r["candidate_id"] for r in out["results"] if r["ok"]]
    return out


@_store_errors
def undo(input_dir: str | Path, candidate_ids: Sequence[int]) -> dict[str, Any]:
    """Undo confirmed sales, last id in the list first, so the lots come back in the order they were taken. A sale
    locked by a 1099-B is reported and left confirmed."""
    ids = list(reversed(_ids(candidate_ids)))
    return _summary(_run(input_dir, ids, lambda s, cid, lots: undo_in(s, cid), dry=False))


@_store_errors
def dismiss(input_dir: str | Path, candidate_ids: Sequence[int], *, reason: str) -> dict[str, Any]:
    """``before_ledger_start`` / ``other`` -> ``dismissed``; ``not_a_sale`` -> ``not_a_sale``, for each unmatched id.
    ``dismissed`` lists the ids that moved, which is what ``restore`` takes."""
    if reason not in DISMISS_REASONS:
        raise ValidationError(f"reason must be one of {', '.join(DISMISS_REASONS)}")
    out = _summary(_run(input_dir, _ids(candidate_ids),
                        lambda s, cid, lots: move_in(s, cid, ("unmatched",), DISMISS_REASONS[reason]), dry=False))
    out["dismissed"] = [r["candidate_id"] for r in out["results"] if r["ok"]]
    return out


@_store_errors
def restore(input_dir: str | Path, candidate_ids: Sequence[int]) -> dict[str, Any]:
    """Undo for a bulk dismiss: dismissed / not_a_sale -> unmatched."""
    return _summary(_run(input_dir, _ids(candidate_ids),
                         lambda s, cid, lots: move_in(s, cid, ("dismissed", "not_a_sale"), "unmatched"), dry=False))
