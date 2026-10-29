"""Difference report and official-number apportioning for a matched 1099-B import (plan 5.4, step 5.2). Pure."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..csv_exchange import text_csv

NONCOVERED_NOTE = "broker did not report basis; ledger value kept"
_MONEY = ("proceeds", "basis", "gain")
_EPS = 0.005
CSV_COLUMNS = ("status", "symbol", "date_sold", "quantity", "kind", "sale_ids", "changed",
               "proceeds_ledger", "proceeds_official", "proceeds_delta", "basis_ledger", "basis_official", "basis_delta",
               "gain_ledger", "gain_official", "gain_delta", "holding_period_ledger", "holding_period_official", "note")


def _r(x: float) -> float:
    return round(float(x) + 0.0, 2)


def official_gain(line: Mapping[str, Any], kept_basis: float | None) -> float:
    """Covered lines: the gain as printed (it already includes any wash-sale add-back). Noncovered lines: the broker's
    basis is not reliable, so proceeds - the ledger basis kept + wash-sale disallowed + accrued market discount."""
    if line["covered"] or kept_basis is None:
        return _r(line["gain"])
    return _r(line["proceeds"] - kept_basis + (line.get("wash_disallowed") or 0.0) + (line.get("market_discount") or 0.0))


def apportion(line: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The ledger fields to write for each matched row. One row (lot line): the line's numbers, trade and acquisition
    date. Several rows (aggregate line): proceeds, basis and gain split in proportion to shares (the last row takes the
    rounding remainder); dates are left alone because the line has no acquisition date."""
    rows = sorted(rows, key=lambda r: r["sale_id"])
    term = line["term"]
    out: list[dict[str, Any]] = []
    if len(rows) == 1:
        r = rows[0]
        basis = _r(line["basis"]) if line["covered"] else _r(r["basis"])
        gain = official_gain(line, None if line["covered"] else r["basis"])
        part = {"sale_id": r["sale_id"], "sale_date": line["date_sold"],
                "purchase_date": line.get("date_acquired") or r.get("purchase_date"),
                "proceeds": _r(line["proceeds"]), "basis": basis, "gain": gain, "holding_period": term,
                "official_proceeds": _r(line["proceeds"]), "official_basis": _r(line["basis"]) if line["covered"] else None,
                "official_gain": gain if line["covered"] else None, "official_holding_period": term}
        return [part]
    total_shares = sum(r["shares"] for r in rows)
    left = {"proceeds": _r(line["proceeds"]), "basis": _r(line["basis"]) if line["covered"] else None, "gain": None}
    kept_basis_total = None if line["covered"] else sum(r["basis"] for r in rows)
    agg_gain = official_gain(line, kept_basis_total)
    left["gain"] = agg_gain
    for n, r in enumerate(rows):
        last = n == len(rows) - 1
        share = r["shares"] / total_shares
        proceeds = left["proceeds"] if last else _r(line["proceeds"] * share)
        left["proceeds"] = _r(left["proceeds"] - proceeds)
        if line["covered"]:
            basis = left["basis"] if last else _r(line["basis"] * share)
            left["basis"] = _r(left["basis"] - basis)
        else:
            basis = _r(r["basis"])
        gain = left["gain"] if last else _r(agg_gain * share)
        left["gain"] = _r(left["gain"] - gain)
        out.append({"sale_id": r["sale_id"], "sale_date": line["date_sold"], "proceeds": proceeds, "basis": basis,
                    "gain": gain, "holding_period": term, "official_proceeds": proceeds,
                    "official_basis": basis if line["covered"] else None,
                    "official_gain": gain if line["covered"] else None, "official_holding_period": term})
    for part in out:  # an aggregate line gives no acquisition date: do not overwrite the ledger's
        part.pop("purchase_date", None)
    return out


def _field(ledger: Any, official: Any, *, money: bool = True, note: str | None = None) -> dict[str, Any]:
    f: dict[str, Any] = {"ledger": ledger, "official": official}
    if money:
        f["delta"] = 0.0 if official is None else _r(official - ledger)
    if note:
        f["note"] = note
    return f


def build_report(lines: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]], result: Mapping[str, Any], *,
                 tax_year: int) -> dict[str, Any]:
    """Every matched line with what changed, lines with no ledger row, and ledger rows of the year with no line."""
    by_id = {r["sale_id"]: r for r in ledger}
    rows: list[dict[str, Any]] = []
    for m in result["matches"]:
        ln = lines[m["line_index"]]
        sales = [by_id[i] for i in m["sale_ids"]]
        parts = apportion(ln, sales)
        led = {k: _r(sum(s[k] for s in sales)) for k in ("proceeds", "basis")}
        led["gain"] = _r(sum((s["gain"] or 0.0) for s in sales))
        new = {k: _r(sum(p[k] for p in parts)) for k in _MONEY}
        fields = {
            "proceeds": _field(led["proceeds"], new["proceeds"]),
            "basis": _field(led["basis"], new["basis"] if ln["covered"] else None,
                            note=None if ln["covered"] else NONCOVERED_NOTE),
            "gain": _field(led["gain"], new["gain"]),
            "holding_period": _field(sales[0]["holding_period"], ln["term"], money=False),
        }
        changed = [k for k in _MONEY if abs(fields[k]["delta"]) > _EPS]
        if len({s["holding_period"] for s in sales}) > 1 or sales[0]["holding_period"] != ln["term"]:
            changed.append("holding_period")
        if m["kind"] == "lot":
            fields["purchase_date"] = _field(sales[0].get("purchase_date"), ln.get("date_acquired"), money=False)
            if ln.get("date_acquired") and sales[0].get("purchase_date") != ln["date_acquired"]:
                changed.append("purchase_date")
            fields["sale_date"] = _field(sales[0]["sale_date"], ln["date_sold"], money=False)
            if sales[0]["sale_date"] != ln["date_sold"]:
                changed.append("sale_date")
        rows.append(_row("changed" if changed else "unchanged", ln, m["sale_ids"], m["kind"], fields, changed))
    for i in result["unmatched_lines"]:
        ln = lines[i]
        fields = {"proceeds": _field(0.0, _r(ln["proceeds"])), "basis": _field(0.0, _r(ln["basis"])),
                  "gain": _field(0.0, _r(ln["gain"])), "holding_period": _field(None, ln["term"], money=False)}
        rows.append(_row("not_previously_entered", ln, [], "line", fields, [], "no ledger row; will be added as source 1099b"))
    year = str(int(tax_year))
    for sid in result["unmatched_ledger"]:
        s = by_id[sid]
        if not str(s["sale_date"]).startswith(year):
            continue
        fields = {"proceeds": _field(_r(s["proceeds"]), None), "basis": _field(_r(s["basis"]), None),
                  "gain": _field(_r(s["gain"] or 0.0), None), "holding_period": _field(s["holding_period"], None, money=False)}
        rows.append({"status": "no_1099b_line", "symbol": s["symbol"], "date_sold": s["sale_date"], "quantity": s["shares"],
                     "kind": "ledger", "sale_ids": [sid], "changed": [], "fields": fields,
                     "note": "no 1099-B line: wrong lot, wrong account, or an account the broker does not report"})
    totals = {k: sum(1 for r in rows if r["status"] == k) for k in ("changed", "unchanged", "not_previously_entered", "no_1099b_line")}
    for k in _MONEY:
        totals[f"{k}_delta"] = _r(sum(r["fields"][k]["delta"] for r in rows if r["status"] in ("changed", "unchanged")))
    return {"tax_year": int(tax_year), "rows": rows, "totals": totals}


def _row(status, ln, sale_ids, kind, fields, changed, note=""):
    return {"status": status, "symbol": ln.get("symbol"), "date_sold": ln["date_sold"], "quantity": ln["quantity"],
            "kind": kind, "sale_ids": list(sale_ids), "changed": changed, "fields": fields, "note": note}


def report_csv(report: Mapping[str, Any]) -> str:
    out: list[list[object]] = [list(CSV_COLUMNS)]
    for r in report["rows"]:
        f = r["fields"]
        note = r.get("note") or "; ".join(x["note"] for x in f.values() if x.get("note"))
        out.append([r["status"], r["symbol"] or "", r["date_sold"], r["quantity"], r["kind"],
                    " ".join(str(i) for i in r["sale_ids"]), " ".join(r["changed"]),
                    f["proceeds"]["ledger"], _blank(f["proceeds"]["official"]), f["proceeds"]["delta"],
                    f["basis"]["ledger"], _blank(f["basis"]["official"]), f["basis"]["delta"],
                    f["gain"]["ledger"], _blank(f["gain"]["official"]), f["gain"]["delta"],
                    _blank(f["holding_period"]["ledger"]), _blank(f["holding_period"]["official"]), note])
    return text_csv.rows_to_text(out)


def _blank(v: Any) -> Any:
    return "" if v is None else v


def _key(ln: Mapping[str, Any]) -> tuple:
    return (ln.get("symbol") or ln.get("cusip") or "", ln["date_sold"], ln.get("date_acquired") or "", round(float(ln["quantity"]), 3))


def compare_statements(old: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """What a corrected statement changed against the one it replaces: lines added, removed, or with other numbers."""
    def index(lines):
        d: dict[tuple, list[Mapping[str, Any]]] = {}
        for ln in lines:
            d.setdefault(_key(ln), []).append(ln)
        return d
    a, b = index(old), index(new)
    out: list[dict[str, Any]] = []
    for key in sorted(set(a) | set(b)):
        olds, news = a.get(key, []), b.get(key, [])
        for o, n in zip(olds, news):
            fields = {k: {"old": _r(o[k]), "new": _r(n[k]), "delta": _r(n[k] - o[k])}
                      for k in _MONEY if abs(n[k] - o[k]) > _EPS}
            if o["term"] != n["term"]:
                fields["term"] = {"old": o["term"], "new": n["term"]}
            if fields:
                out.append({"change": "changed", "symbol": key[0], "date_sold": key[1], "fields": fields})
        for o in olds[len(news):]:
            out.append({"change": "removed", "symbol": key[0], "date_sold": key[1], "fields": {}})
        for n in news[len(olds):]:
            out.append({"change": "added", "symbol": key[0], "date_sold": key[1], "fields": {}})
    return out
