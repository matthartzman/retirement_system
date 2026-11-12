"""Realized-sales ledger, server side of the Sales Ledger page's tax-year panel (plan step 3a.3): the year's
capital gain/loss netting, the carryforward entry and the possible-wash flags. Netting is ``realized_tax`` and
detection is ``wash_sales``; this module only reads and writes the plan file. Nothing here changes the
projection or the engine. Every function takes the workspace ``input`` folder like ``sales_service``."""
from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import active_plan
from .core import ACCOUNT_TYPES, _infer_type
from .realized_seed import terms_from_ledger_rows
from .realized_income_stack import plan_income_stack
from .realized_tax import net_realized_by_year, net_realized_year, realized_gain_tax
from .taxes import capital_loss_ordinary_limit
from .sales_ledger import ValidationError
from .sales_matching import buy_rows
from .wash_sales import buys_from_rows, dedupe_buys, detect_wash_sales, plan_flag_updates, sale_key

log = logging.getLogger("retirement_system.sales_tax_year")

_LEDGER_CLASSES = ("taxable", "pre_tax", "roth", "hsa")


def _base(input_dir: str | Path) -> Path:
    return Path(input_dir).parent


def _filing(input_dir: str | Path, filing: str | None) -> str:
    if filing is None:
        filing = active_plan.peek_plan_data_for_input_dir(input_dir).get("Household", {}).get("", {}).get("filing_status")
    return "MFS" if str(filing or "").strip().upper() == "MFS" else (str(filing or "MFJ").strip().upper() or "MFJ")


def _adjustments(store) -> dict[int, dict[str, Any]]:
    return {int(a["tax_year"]): a for a in store.sales.adjustments()}


def _plan_config(input_dir: str | Path) -> dict[str, Any] | None:
    """The Planner's built config (no live pricing, no projection run), or None when the plan cannot be built."""
    try:
        from .data_io import parse_client
        return parse_client(active_plan.peek_plan_data_for_input_dir(input_dir), "", skip_live_pricing=True)
    except Exception:  # noqa: BLE001 - a partial plan must not take the panel down
        return None


def realized_tax_estimate(cfg: dict[str, Any] | None, netting: dict[str, float], year: int, filing: str,
                          state_rate_override: float | None = None) -> dict[str, Any]:
    """Dollar tax on the year's netted gains (federal ordinary/LTCG, NIIT, state) from the engine's own functions.
    ``available`` is False, with no figures, when the plan config cannot be built or priced."""
    if not cfg:
        return {"available": False, "reason": "The plan is not complete enough to price tax."}
    try:
        c = dict(cfg)
        c["filing_status"] = filing
        stack = plan_income_stack(c, year, filing)
        income = stack["ordinary_income"]
        parts = realized_gain_tax(c, netting, year=year, ordinary_income=income, magi=income,
                                  state_rate_override=state_rate_override)
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "The plan is not complete enough to price tax."}
    return {"available": True, "method": "planner", "ordinary_income": round(income, 2), "magi": round(income, 2),
            "income_source": ", ".join(stack["included"]) or "none", "income_components": {
                k: stack[k] for k in ("earned", "pension", "annuity", "rental", "social_security", "social_security_taxable")},
            **{k: round(parts[k], 2) for k in ("ordinary_tax", "ltcg_tax", "niit", "state_tax", "total")},
            "note": stack["label"]}


def _live_sales(sales: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    return [s for s in sales if s["status"] == "confirmed" and s["tax_class"] == "taxable"
            and s["gain"] is not None and s["sale_date"][:4] == str(year)]


def wash_flagged(sales: list[dict[str, Any]], year: int | None = None, reviews: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Loss sales carrying a wash flag (of ``year``'s live taxable sales when a year is given); a sale reviewed as not a wash is skipped."""
    rows = sales if year is None else _live_sales(sales, year)
    skip = {k for k, v in (reviews or {}).items() if v.get("outcome") == "not_wash"}
    return [s for s in rows if s["wash_flag"] != "none" and s["gain"] < 0 and sale_key(s) not in skip]


def _detected(store, sales: list[dict[str, Any]], reviews: dict[str, Any]) -> dict[str, dict[str, Any]]:
    buys = _all_buys(store)
    return detect_wash_sales(sales, buys, accounts=_account_classes(sales, {b["account"] for b in buys}), reviews=reviews)


def _wash_offsets(sales: list[dict[str, Any]], detected: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Terms that lower the loss by what a wash sale disallows (a gain-signed record in the loss lots' own term, by loss share),
    so the netting, the carryforward and the estimated tax all use the loss net of it."""
    by_id = {s["sale_id"]: s for s in sales}
    out = []
    for d in detected.values():
        lots = [by_id[i] for i in d["sale_ids"] if i in by_id]
        total = sum(-float(l["gain"]) for l in lots) or 1.0
        for l in lots:
            if l["holding_period"] in ("short", "long"):
                out.append({"tax_year": int(l["sale_date"][:4]), "term": l["holding_period"], "status": "confirmed", "tax_class": "taxable",
                            "gain": d["disallowed"] * (-float(l["gain"])) / total})
    return out


def _wash_totals(detected: dict[str, dict[str, Any]], year: int) -> dict[str, Any]:
    mine = [d for k, d in detected.items() if k.rsplit("|", 1)[-1][:4] == str(year)]
    lost = sum(m["amount"] for d in mine for m in d["matches"] if not m["taxable"])
    total = sum(d["disallowed"] for d in mine)               # a sale the broker reported carries the broker's figure
    return {"disallowed": round(total, 2), "deferred": round(max(total - lost, 0.0), 2), "lost_permanently": round(lost, 2), "sales": len(mine)}


def wash_open_windows(input_dir: str | Path) -> dict[str, Any]:
    """The open-window warnings (see ``wash_sales.open_windows``) with friendly account names, as of today."""
    from . import platform_runtime
    from .person_labels import display_account
    from .wash_sales import open_windows
    cfg = _plan_config(input_dir) or {}
    with active_plan.workspace_store(_base(input_dir)) as store:
        return {"windows": open_windows(store, platform_runtime.today(), label=lambda a: display_account(a, cfg))}


def wash_cards(input_dir: str | Path, year: int) -> dict[str, Any]:
    """The To fix wash cards for ``year``: one per flagged sale that has no review yet, with friendly account names and where each
    replacement's share of the loss goes, plus the reviews already made (to undo)."""
    from .person_labels import display_account
    year = int(year)
    cfg = _plan_config(input_dir)
    label = lambda a: display_account(a, cfg or {})  # noqa: E731
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales()
        reviews = store.sales.reviews()
        detected = _detected(store, sales, reviews)
        run = wash_run_status(store, sales)
    by_id = {s["sale_id"]: s for s in sales}
    cards = []
    for key, d in sorted(detected.items(), key=lambda kv: kv[0].rsplit("|", 1)[-1]):
        if key.rsplit("|", 1)[-1][:4] != str(year) or key in reviews:
            continue
        lots = [by_id[i] for i in d["sale_ids"]]
        account, symbol, sale_date = key.split("|")
        cards.append({
            "sale_key": key, "account": label(account), "symbol": symbol, "sale_date": sale_date, "lots": len(lots),
            "shares": sum(float(l["shares"]) for l in lots), "proceeds": round(sum(float(l["proceeds"]) for l in lots), 2),
            "loss": d["loss"], "disallowed": d["disallowed"], "deductible": d["deductible"],
            "matches": [{"txn_id": m["txn_id"], "label": label(m["account"]), "account": m["account"], "date": m["date"], "shares": m["shares"],
                         "value": m["value"], "is_reinvest": m["is_reinvest"], "taxable": m["taxable"], "amount": m["amount"],
                         "where": f"adds ${m['amount']:,.2f} to the cost of this lot" if m["taxable"] else "lost permanently"} for m in d["matches"]]})
    done = [{"sale_key": k, "outcome": v["outcome"], "reason": v["reason"], "updated_at": v["updated_at"]}
            for k, v in sorted(reviews.items()) if k.rsplit("|", 1)[-1][:4] == str(year)]
    for r in done:
        a, sym, day = r["sale_key"].split("|")
        r["label"] = f"{sym} {day} in {label(a)}"          # the key holds the raw account id; the list shows the friendly name
    return {"cards": cards, "reviewed": done, "run": run}


def tax_year_summary(input_dir: str | Path, year: int, *, filing: str | None = None) -> dict[str, Any]:
    """Netting for ``year`` with the carryforward chained from earlier years (an entered figure for a year
    replaces the computed one), the raw short/long sums, and the wash-flagged losses."""
    year = int(year)
    filing = _filing(input_dir, filing)
    with active_plan.workspace_store(_base(input_dir)) as store:
        sales = store.sales.list_sales()
        reviews = store.sales.reviews()
        adjustments = _adjustments(store)
        try:
            detected_all = _detected(store, sales, reviews)
        except Exception:  # noqa: BLE001 - the replacement scan reads several sources; the summary still answers without it
            log.exception("wash detection failed; the loss is shown whole")
            detected_all = {}
        try:
            run = wash_run_status(store, sales)
        except Exception:  # noqa: BLE001 - the marker is advisory; it must not break the tax-year response
            log.exception("wash last-run status failed; showing it as unknown")
            run = {"last_run": None, "never_run": False, "stale": False}
    by_year = net_realized_by_year(terms_from_ledger_rows(sales) + _wash_offsets(sales, detected_all), adjustments, filing, through_year=year)
    prev = by_year.get(year - 1)
    entered = year in adjustments
    if entered:
        cf_in = (float(adjustments[year]["carryforward_short"]), float(adjustments[year]["carryforward_long"]))
    else:
        cf_in = (prev["carryforward_st"], prev["carryforward_lt"]) if prev else (0.0, 0.0)
    netting = by_year.get(year) or net_realized_year(0.0, 0.0, 0.0, 0.0, filing)
    live = _live_sales(sales, year)
    flagged = wash_flagged(live, reviews=reviews)
    all_flagged = wash_flagged([x for x in sales if x["status"] == "confirmed" and x["tax_class"] == "taxable"
                                and x["gain"] is not None], reviews=reviews)   # every year: the Sales Ledger strip counts across all years
    out = {
        "year": year, "filing": filing, "limit": capital_loss_ordinary_limit(filing), "netting": netting,
        "carryforward_in": {"short": cf_in[0] + 0.0, "long": cf_in[1] + 0.0, "entered": entered},
        "carryforward_out": {"short": netting["carryforward_st"], "long": netting["carryforward_lt"]},
        "totals": {"count": len(live),
                   "st_gain": sum(s["gain"] for s in live if s["holding_period"] == "short") + 0.0,
                   "lt_gain": sum(s["gain"] for s in live if s["holding_period"] == "long") + 0.0},
        "wash": {"count": len(flagged), "all_years_count": len(all_flagged), "flagged_loss": sum(-s["gain"] for s in flagged) + 0.0,
                 **_wash_totals(detected_all, year),
                 "rows": [{"sale_id": s["sale_id"], "symbol": s["symbol"], "sale_date": s["sale_date"],
                           "gain": s["gain"], "flag": s["wash_flag"], "note": s["wash_note"]} for s in flagged], **run},
    }
    if live or netting["ordinary_offset"] or any(netting[k] for k in ("net_st", "net_lt")):   # empty ledger: no line
        override = (adjustments.get(year) or {}).get("state_rate_override")
        out["realized_tax"] = realized_tax_estimate(_plan_config(input_dir), netting, year, filing, override)
    return out


def set_wash_review(input_dir: str | Path, sale_key: str, outcome: str, *, reason: str | None = None,
                    broker_amount: float | None = None) -> None:
    """Record the user's outcome for a wash flag (wash / broker_reported / not_wash with a reason); the flags are refreshed after."""
    try:
        with active_plan.workspace_store(_base(input_dir), write=True) as store:
            store.sales.set_review(sale_key, outcome, reason, broker_amount)
    except active_plan.StoreError as exc:
        raise ValidationError(str(exc)) from exc
    auto_refresh(input_dir)


def clear_wash_review(input_dir: str | Path, sale_key: str) -> None:
    with active_plan.workspace_store(_base(input_dir), write=True) as store:
        store.sales.clear_review(sale_key)
    auto_refresh(input_dir)


def _figure(name: str, value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{name} must be a number, got {value!r}") from None
    if not math.isfinite(out) or out < 0:
        raise ValidationError(f"{name} must be zero or more (enter the loss as a positive amount)")
    return out


def set_carryforward(input_dir: str | Path, year: int, *, short: Any, long: Any) -> dict[str, Any]:
    """Enter the capital-loss carryforward INTO ``year`` from the prior year's Schedule D (positive amounts)."""
    try:
        year = int(year)
    except (TypeError, ValueError):
        raise ValidationError(f"year must be a number, got {year!r}") from None
    if not 1990 <= year <= 2100:
        raise ValidationError("year must be between 1990 and 2100")
    short_f, long_f = _figure("short-term carryforward", short), _figure("long-term carryforward", long)
    with active_plan.workspace_store(_base(input_dir), write=True) as store:
        existing = store.sales.adjustment(year) or {}
        store.sales.set_adjustment(year, carryforward_short=short_f, carryforward_long=long_f,
                                   state_rate_override=existing.get("state_rate_override"))
    return {"year": year, "carryforward_short": short_f, "carryforward_long": long_f}


def _account_classes(sales: list[dict[str, Any]], accounts: set[str]) -> dict[str, dict[str, str]]:
    """Tax class per account for the IRA message: a class the user gave a ledger row wins, else the Planner's
    own naming rule (``core._infer_type`` suffixes); an account matching neither is left unclassified."""
    ledger = {s["account"]: s["tax_class"] for s in sales}
    out: dict[str, dict[str, str]] = {}
    for name in accounts:
        cls = ledger.get(name)
        if cls is None:
            try:
                cls = ACCOUNT_TYPES[_infer_type(name)]["tax"]
            except ValueError:
                cls = None
        if cls in _LEDGER_CLASSES:
            out[name] = {"label": name, "tax_class": cls}
    return out


def _all_buys(store) -> list[dict[str, Any]]:
    """Replacement-purchase candidates from every source: holdings lots, broker-activity buys and reinvestments,
    and Monarch ``Buy`` rows. A purchase present in more than one source counts once."""
    held = buys_from_rows(store.dataset("holdings").rows(), source="holdings")
    broker = buys_from_rows(({"date": a["run_date"], "symbol": a["symbol"], "quantity": abs(a["quantity"] or 0.0),
                              "account": a["account"], "price": a.get("price"), "is_reinvest": a["kind"] == "reinvest"}
                             for a in store.broker.activity(kinds=("buy", "reinvest")) if not a["sweep"]),
                            source="broker")
    monarch = buys_from_rows(buy_rows(store.dataset("ytd_transactions").rows()), source="monarch")
    return dedupe_buys(held, broker, monarch)


WASH_MARKER_KEY = "wash.last_run"
_SALE_INPUT_KEYS = ("sale_id", "account", "symbol", "sale_date", "purchase_date", "shares", "status", "tax_class", "gain")


def _wash_signature(sales: list[dict[str, Any]], buys: list[dict[str, Any]], reviews: dict[str, Any] | None = None) -> str:
    """Stable digest of what the wash scan reads: a SHA-256 over the sales' identity and scan-relevant fields
    (``_SALE_INPUT_KEYS``; the scan's own output, ``wash_flag``/``wash_note``, is left out so writing flags never
    changes it) and the de-duplicated replacement purchases (account, symbol, date, shares), both sorted. It costs the
    same reads as the scan but not the detection, and changes exactly when a rescan could give a different answer."""
    payload = {"sales": sorted([str(s.get(k)) for k in _SALE_INPUT_KEYS] for s in sales),
               "buys": sorted([str(b.get("account")), b["symbol"], b["date"], f"{float(b['shares']):.6f}"] for b in buys)}
    if reviews:                                       # a changed review changes what a scan would flag
        payload["reviews"] = sorted([k, str(v.get("outcome")), str(v.get("reason"))] for k, v in reviews.items())
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def wash_run_status(store, sales: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The last-run marker against the current inputs: ``last_run`` (ISO time or None), ``never_run`` and ``stale``
    (a marker exists but the inputs changed since, e.g. a hand-edited holding that triggers no rescan)."""
    try:
        mark = json.loads(store.get_meta(WASH_MARKER_KEY) or "null")
    except ValueError:
        mark = None
    if not isinstance(mark, dict):
        return {"last_run": None, "never_run": True, "stale": False}
    sales = store.sales.list_sales() if sales is None else sales
    return {"last_run": mark.get("at"), "never_run": False,
            "stale": mark.get("signature") != _wash_signature(sales, _all_buys(store), store.sales.reviews())}


def refresh_wash_flags_in(store) -> dict[str, int]:
    """``refresh_wash_flags`` inside the caller's open write store (and transaction). Records the last-run marker
    (``plan_meta`` key ``wash.last_run``: ``{at, signature}``, see ``_wash_signature``) every time it completes."""
    sales = store.sales.list_sales()
    buys = _all_buys(store)
    reviews = store.sales.reviews()
    detected = detect_wash_sales(sales, buys, accounts=_account_classes(sales, {b["account"] for b in buys}), reviews=reviews)
    updates = plan_flag_updates(sales, detected)
    for sale_id, flag, note in updates:
        store.sales.set_wash_flag(sale_id, flag, note)
    from . import transactions
    from .wash_adjustments import recompute_adjustments
    if recompute_adjustments(store) or store.transactions.managed_accounts():
        transactions.materialize_managed(store)           # holdings follow the add-backs
    store.set_meta(WASH_MARKER_KEY, json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                 "signature": _wash_signature(sales, buys, reviews)}))
    return {"flagged": len(detected), "updated": len(updates)}


def refresh_wash_flags(input_dir: str | Path) -> dict[str, int]:
    """Re-run the possible-wash scan against holdings lots, broker buys and Monarch Buy rows and write the flags to
    the ledger rows. Returns how many loss sales are flagged and how many rows changed."""
    with active_plan.workspace_store(_base(input_dir), write=True) as store, store.transaction():
        return refresh_wash_flags_in(store)


def auto_refresh(input_dir: str | Path) -> None:
    """Best-effort ``refresh_wash_flags`` for the ledger-changing operations (confirm, add, import, undo, 1099-B).
    Idempotent and cheap; it runs after the primary operation has committed and swallows every error, so a scan
    problem can never fail or roll back the operation that triggered it."""
    try:
        refresh_wash_flags(input_dir)
    except Exception:  # noqa: BLE001 - flags are advisory; the primary write already succeeded
        log.warning("automatic wash-sale scan failed", exc_info=True)
