"""Broker 1099-B import against the realized-sales ledger (plan 5.4, step 5.2): preview with a difference report, and
apply the official numbers with an audit trail.

The parsers (``broker_1099b``) turn a statement into normalized lines and verify its control totals; this module matches
the lines to ledger rows, writes the official proceeds / basis / gain / holding period (keeping every pre-correction value
in ``realized_sale_audit``), adds lines the ledger never had as ``source=1099b`` rows, and lets a corrected statement
supersede the earlier import of the same broker, account and tax year by reverting it first. ``preview`` never writes;
``apply`` is one plan-file transaction. Every function takes the workspace ``input`` folder like ``sales_confirm``.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from . import active_plan, broker_1099b
from .broker_1099b import matching, report as _report
from .sales_ledger import ValidationError


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _store_errors(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except active_plan.StoreError as exc:
            raise ValidationError(str(exc)) from exc
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


def _tax_year(parsed: dict[str, Any], override: int | None) -> int:
    lines = parsed["parsed"]
    if override is not None:
        year = int(override)
    elif parsed.get("meta", {}).get("tax_year"):
        year = int(parsed["meta"]["tax_year"])
    elif lines:
        year = int(Counter(r["date_sold"][:4] for r in lines).most_common(1)[0][0])
    else:
        raise ValidationError("no 1099-B lines were read, so there is no tax year")
    stray = sorted({r["date_sold"] for r in lines if not r["date_sold"].startswith(str(year))})
    if stray:
        raise ValidationError(f"tax year {year} does not match the statement: lines were sold on {', '.join(stray[:3])}")
    return year


def _ledger_before(store, statement_id: int | None) -> list[dict[str, Any]]:
    """The ledger rows as they stood before ``statement_id`` was applied (its corrections undone, rows it added left
    out). With no statement, the ledger as it is. Read-only; mirrors ``SalesRepo.revert_statement``."""
    rows = {r["sale_id"]: dict(r) for r in store.sales.list_sales()}
    if statement_id is None:
        return list(rows.values())
    for a in reversed(store.sales.audit(statement_id=statement_id)):
        if a["action"] == "correct" and a["sale_id"] in rows:
            rows[a["sale_id"]].update(a["before"])
        elif a["action"] == "add":
            rows.pop(a["sale_id"], None)
    return list(rows.values())


@_store_errors
def preview(input_dir: str | Path, *, broker: str, account: str, text: str | None = None, pdf_bytes: bytes | None = None,
            known_symbols: Iterable[str] | None = None, tax_year: int | None = None) -> dict[str, Any]:
    """Side-effect-free ``import_preview_v1``-style report: the parsed lines and control totals (``broker_1099b``), how
    each line matches the ledger, the difference report (and its CSV), and what an earlier import of the same statement
    would be replaced and how the new one differs from it."""
    account = str(account or "").strip()
    if not account:
        raise ValidationError("choose the Planner account this statement belongs to (account)")
    pv = broker_1099b.preview_statement(broker, text=text, pdf_bytes=pdf_bytes, known_symbols=known_symbols, account=account)
    if pv["received"] == 0 and pv["errors"] and not pv["parsed"]:
        raise ValidationError(pv["errors"][0]["error"])
    year = _tax_year(pv, tax_year)
    lines = pv["parsed"]
    with active_plan.workspace_store(_base(input_dir)) as store:
        active = store.sales.active_statement(broker, account, year)
        ledger = _ledger_before(store, active["statement_id"] if active else None)
        previous = store.sales.statement_lines(active["statement_id"]) if active else []
    result = matching.match_lines(lines, ledger, account=account)
    rep = _report.build_report(lines, ledger, result, tax_year=year)
    placed = {m["line_index"]: m["sale_ids"] for m in result["matches"]}
    washes = _report.wash_adjustments(lines, [placed.get(i, []) for i in range(len(lines))])
    out = {**pv, "wash_adjustments": washes, "account": account, "tax_year": year, "match": result, "report": rep, "report_csv": _report.report_csv(rep),
           "supersedes": None, "changes_since_previous": []}
    if active:
        out["supersedes"] = {"statement_id": active["statement_id"], "applied_at": active["applied_at"],
                             "corrected": bool(active["corrected"]), "line_count": len(previous)}
        out["changes_since_previous"] = _report.compare_statements([p["line"] for p in previous], lines)
    return out


@_store_errors
def apply(input_dir: str | Path, *, broker: str, account: str, text: str | None = None, pdf_bytes: bytes | None = None,
          known_symbols: Iterable[str] | None = None, tax_year: int | None = None, replace: bool = False) -> dict[str, Any]:
    """Write the official numbers. Refused unless the control totals tie. A statement for the same broker, account and
    tax year that is already applied is refused unless ``replace`` is true, in which case it is reverted first (its
    corrections undone, its added rows voided) and marked superseded; an identical file is always refused."""
    pv = preview(input_dir, broker=broker, account=account, text=text, pdf_bytes=pdf_bytes,
                 known_symbols=known_symbols, tax_year=tax_year)
    if not pv["can_apply"]:
        problems = "; ".join(e["error"] for e in pv["errors"]) or "the statement could not be verified"
        raise ValidationError(f"refusing to apply: control totals / parse check failed: {problems}")
    account, year, lines = pv["account"], pv["tax_year"], pv["parsed"]
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        active = store.sales.active_statement(broker, account, year)
        superseded = None
        if active:
            if [p["line"] for p in store.sales.statement_lines(active["statement_id"])] == [dict(r) for r in lines]:
                raise ValidationError("this statement is identical to the one already imported")
            if not replace:
                raise ValidationError(f"a {year} {broker} statement for {account} was already imported "
                                      f"(statement {active['statement_id']}); confirm replacing it")
            store.sales.revert_statement(active["statement_id"])
            superseded = active["statement_id"]
        ledger = store.sales.list_sales()
        result = matching.match_lines(lines, ledger, account=account)
        by_id = {r["sale_id"]: r for r in ledger}
        meta = pv.get("meta", {})
        sid = store.sales.add_statement(broker=broker, account=account, tax_year=year, corrected=bool(meta.get("corrected")),
                                        statement_date=meta.get("statement_date"), control=pv["control_totals"])
        corrected = added = 0
        placed: dict[int, list[int]] = {}
        for m in result["matches"]:
            parts = _report.apportion(lines[m["line_index"]], [by_id[i] for i in m["sale_ids"]])
            for part in parts:
                store.sales.correct_sale(part["sale_id"], sid, {k: v for k, v in part.items() if k != "sale_id"})
                corrected += 1
            placed[m["line_index"]] = list(m["sale_ids"])
        for i in result["unmatched_lines"]:
            new_id = store.sales.insert_sale(**_new_row(lines[i], account, sid, i))
            store.sales.record_added(new_id, sid)
            placed[i] = [new_id]
            added += 1
        for i, ln in enumerate(lines):
            store.sales.add_line(sid, i, dict(ln), placed.get(i, []))
    return {"statement_id": sid, "corrected": corrected, "added": added, "superseded": superseded,
            "unmatched_ledger": result["unmatched_ledger"]}


def _new_row(ln: dict[str, Any], account: str, statement_id: int, line_no: int) -> dict[str, Any]:
    covered = bool(ln["covered"])
    return {
        "sale_date": ln["date_sold"], "account": account, "tax_class": "taxable",
        "symbol": ln.get("symbol") or f"CUSIP-{ln.get('cusip') or 'UNKNOWN'}", "shares": ln["quantity"],
        "proceeds": ln["proceeds"], "fees": 0.0, "basis": ln["basis"], "purchase_date": ln.get("date_acquired"),
        "holding_period": ln["term"], "gain": ln["gain"], "source": "1099b", "statement_id": statement_id,
        "wash_note": "not previously entered (added from the 1099-B)" + ("" if covered else "; broker did not report basis"),
        "lot_key": json.dumps({"statement_id": statement_id, "line": line_no}),
        "official_proceeds": ln["proceeds"], "official_basis": ln["basis"] if covered else None,
        "official_gain": ln["gain"] if covered else None, "official_holding_period": ln["term"],
    }


@_store_errors
def wash_adjustments(input_dir: str | Path, tax_year: int) -> dict[str, Any]:
    """Wash-sale losses disallowed (1099-B column 1g) from the applied statements of ``tax_year``, for display. A
    superseded statement is not counted. Read-only; it never changes a gain, a wash flag or a tax figure."""
    items: list[dict[str, Any]] = []
    with active_plan.workspace_store(_base(input_dir)) as store:
        for st in store.sales.list_statements():
            if st["status"] != "applied" or st["tax_year"] != int(tax_year):
                continue
            stored = store.sales.statement_lines(st["statement_id"])
            found = _report.wash_adjustments([s["line"] for s in stored], [s["sale_ids"] for s in stored])
            items += [{**w, "account": st["account"], "broker": st["broker"], "statement_id": st["statement_id"]} for w in found]
    return {"tax_year": int(tax_year), "adjustments": items, "total": round(sum(w["wash_disallowed"] for w in items), 2)}
