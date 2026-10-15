from __future__ import annotations

"""Account reconciliation: the app's account numbers against Monarch's.

``build_rows`` pairs each app number with the Monarch account(s) that match it and reports the
difference; ``preview`` / ``apply`` / ``undo`` copy Monarch's number into the app, with every change
logged (``reconcile_log``) so it can be undone.

What each app number is, and what an update writes:

* **Accounts & Sources rows** (``ytd_account_setup``): cash, cards, loans and manual accounts (offline
  assets, annuities with no income stream, ...) write the row's ``Current Value`` / ``Current Balance``.
  Liabilities are stored positive in the app and negative in Monarch, so the compared Monarch value is
  sign-flipped.
* **Plan inputs**: home (``Other Assets / Home / value_as_of_plan_start``), autos (``Other Assets / Autos /
  value``) and mortgage (``Cashflow / Mortgage / balance_as_of_plan_start``). These are the plan's
  stored (plan-start) figures, compared as stored.
* **Report only**: investment accounts (valued from holdings lots x prices) and annuities/pensions whose
  value comes from an income stream's base value. The page shows the difference; nothing is written.

Several Monarch accounts can map to one app number (their balances are summed): two vehicles to "Autos".
Matches are automatic when the Monarch account name equals an Accounts & Sources account name, otherwise
saved by hand in ``monarch_account_map``.
"""

import functools
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import active_plan, platform_runtime
from . import ytd_tracking as ytd

DEFAULT_TOLERANCE = 1.0

LIABILITY_ROLES = frozenset({"Credit card", "Mortgage", "HELOC", "Loan", "Other liability"})
INVESTMENT_ROLE = "Investment"
ANNUITY_ROLES = frozenset({"Annuity/Pension", "Annuity", "Pension"})
CASH_ROLE = "Cash / spending"

GROUP_CASH = "Cash, cards and loans"
GROUP_MANUAL = "Manual accounts"
GROUP_PLAN = "Plan inputs"
GROUP_INVEST = "Investments (report only)"
GROUP_ORDER = (GROUP_CASH, GROUP_MANUAL, GROUP_PLAN, GROUP_INVEST)

# Plan-input targets: id -> (label, (section, subsection, label), is_liability)
PLAN_TARGETS: dict[str, tuple[str, tuple[str, str, str], bool]] = {
    "plan:home": ("Home value (plan input)", ("Other Assets", "Home", "value_as_of_plan_start"), False),
    "plan:autos": ("Autos value (plan input)", ("Other Assets", "Autos", "value"), False),
    "plan:mortgage": ("Mortgage balance (plan input)", ("Cashflow", "Mortgage", "balance_as_of_plan_start"), True),
}
MAP_SETUP = "setup_account"
MAP_IGNORE = "ignore"
MAP_KINDS = (MAP_SETUP, *PLAN_TARGETS, MAP_IGNORE)

REPORT_ONLY_INVEST = "Investment accounts are valued from holdings lots x prices. Change lots on the Holdings page."
REPORT_ONLY_STREAM = "This annuity's value comes from its income stream's base value. Change it where the income stream is set up."


class ReconcileError(ValueError):
    """A request the page cannot honor (bad id, stale preview, a value that changed since, no such plan)."""


def _store_errors(fn):
    """Report the plan store's own errors (missing plan, not found, invalid value) as ReconcileError, so the
    routes catch one type and real programming errors are not mistaken for a bad request."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except active_plan.StoreError as exc:
            raise ReconcileError(str(exc)) from exc
    return wrapper


def _money_text(value: float) -> str:
    return f"{round(float(value), 2):.2f}"


def _parse_as_of(as_of: str | None, default: str | None) -> str | None:
    if not as_of:
        return default
    try:
        return date.fromisoformat(as_of).isoformat()
    except ValueError:
        raise ReconcileError(f"as-of date must be YYYY-MM-DD, got {as_of!r}") from None


SETUP_VALUE_FIELD = "Current Value"  # canonical: ``normalize_account_setup`` mirrors it into ``Current Balance``


def _set_setup_value(row: dict[str, str], text: str) -> None:
    row[SETUP_VALUE_FIELD] = text
    row["Current Balance"] = text


def _same_amount(a: str, b: str) -> bool:
    """Equal as written, or as numbers: the setup normalizer may reformat ``10021.20`` as ``10021.2``."""
    if a == b:
        return True
    try:
        return abs(ytd.parse_money(a) - ytd.parse_money(b)) < 0.005 and bool(a.strip()) == bool(b.strip())
    except (TypeError, ValueError):
        return False


def _group_for(role: str) -> str:
    if role == INVESTMENT_ROLE:
        return GROUP_INVEST
    if role in LIABILITY_ROLES or role == CASH_ROLE:
        return GROUP_CASH
    return GROUP_MANUAL


def _read_plan_values(input_dir: Path) -> dict[tuple[str, str, str], str]:
    out: dict[tuple[str, str, str], str] = {}
    for section, subs in active_plan.peek_plan_data_for_input_dir(input_dir).items():
        for sub, labels in subs.items():
            for label, value in labels.items():
                out[(section.strip(), sub.strip(), label.strip())] = str(value).strip()
    return out


def _monarch_side(monarch: list[dict[str, Any]], liability: bool) -> dict[str, Any]:
    total = sum(a["balance"] for a in monarch)
    return {
        "monarch_value": round(-total if liability else total, 2),
        "monarch_accounts": [{"account_key": a["account_key"], "account": a["account"], "balance": a["balance"],
                              "closed": a["closed"], "balance_date": a["balance_date"], "auto": bool(a.get("auto"))} for a in monarch],
    }


@_store_errors
def build_rows(input_dir: str | Path, as_of: str | None = None, *, tolerance: float = DEFAULT_TOLERANCE,
               today: date | None = None) -> dict[str, Any]:
    """Every comparison row for the plan behind ``input_dir`` as of a Monarch date (default: the latest)."""
    input_dir = Path(input_dir)
    base = input_dir.parent
    with active_plan.workspace_store(base) as store:
        repo = store.monarch
        latest = repo.latest_date()
        as_of_date = _parse_as_of(as_of, latest)
        if latest is None or as_of_date is None:
            return {"has_balances": False, "rows": [], "unmatched": [], "ignored": 0, "tolerance": tolerance,
                    "import": repo.last_import(), "dates": []}
        monarch_accounts = repo.accounts_as_of(as_of_date)
        mapping = repo.mapping()
        dates = repo.dates()
        last_import = repo.last_import()
        last_ok = repo.last_import(ok_only=True)

    setup = ytd.read_account_setup(input_dir)
    summary = ytd.ytd_summary(input_dir, today=today)
    growth = {str(r.get("account") or "").strip().casefold(): r
              for r in (summary.get("investment_balance") or {}).get("account_growth_rows", [])}
    plan_values = _read_plan_values(input_dir)

    setup_rows = {}
    for r in setup:
        name = str(r.get("Account") or "").strip()
        role = str(r.get("Role") or "").strip() or CASH_ROLE
        if name and role != "Ignore":
            setup_rows[name.casefold()] = (name, role, r)

    # ---- resolve each Monarch account to an app target
    by_target: dict[str, list[dict[str, Any]]] = {}
    unmatched: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    for acct in monarch_accounts:
        saved = mapping.get(acct["account_key"])
        target = None
        auto = False
        if saved:
            if saved["kind"] == MAP_IGNORE:
                ignored.append({"account_key": acct["account_key"], "label": acct["account"]})
                continue
            if saved["kind"] == MAP_SETUP and saved["ref"].casefold() in setup_rows:
                target = "setup:" + setup_rows[saved["ref"].casefold()][0]
            elif saved["kind"] in PLAN_TARGETS:
                target = saved["kind"]
        elif acct["account"].strip().casefold() in setup_rows:
            target = "setup:" + setup_rows[acct["account"].strip().casefold()][0]
            auto = True
        if target is None:
            if abs(acct["balance"]) >= 0.005:
                unmatched.append({
                    "id": "monarch:" + acct["account_key"], "account_key": acct["account_key"], "label": acct["account"],
                    "status": "not_in_app", "monarch_value": acct["balance"], "closed": acct["closed"],
                    "saved_mapping": saved or None,
                })
            continue
        by_target.setdefault(target, []).append({**acct, "auto": auto})

    rows: list[dict[str, Any]] = []

    def finish(row: dict[str, Any]) -> None:
        if row["monarch_value"] is None:
            row["difference"] = None
        else:
            row["difference"] = round(row["monarch_value"] - row["app_value"], 2)
            if row["status"] in ("match", "differs"):
                row["status"] = "differs" if abs(row["difference"]) >= tolerance else "match"
        row["updatable"] = row["status"] == "differs" and row.get("write") is not None
        rows.append(row)

    # ---- Accounts & Sources rows
    for key, (name, role, raw) in setup_rows.items():
        rid = "setup:" + name
        mapped = by_target.get(rid, [])
        liability = role in LIABILITY_ROLES
        g = growth.get(key)
        app_value = float(g["current_value"]) if g is not None else ytd._account_current_value(raw)
        if not mapped and abs(app_value) < 0.005:
            continue  # a blank, unmatched row is noise
        row = {"id": rid, "kind": MAP_SETUP, "label": name, "role": role, "group": _group_for(role),
               "app_value": round(app_value, 2), "write": None, "report_reason": None,
               "auto_matched": bool(mapped) and all(m["auto"] for m in mapped), **_monarch_side(mapped, liability)}
        if not mapped:
            row.update(status="not_in_monarch", monarch_value=None, monarch_accounts=[])
        elif role == INVESTMENT_ROLE:
            row.update(status="report_only", report_reason=REPORT_ONLY_INVEST)
        elif role in ANNUITY_ROLES and g is not None and str(g.get("source", "")).startswith("income_stream_base"):
            row.update(status="report_only", report_reason=REPORT_ONLY_STREAM)
        else:
            row.update(status="differs", write={"kind": MAP_SETUP, "ref": name, "field": SETUP_VALUE_FIELD,
                                                "old": str(raw.get(SETUP_VALUE_FIELD) or "").strip(), "new": _money_text(row["monarch_value"])})
        finish(row)

    # ---- plan inputs
    for rid, (label, key, liability) in PLAN_TARGETS.items():
        mapped = by_target.get(rid, [])
        present = key in plan_values
        if not present and not mapped:
            continue
        stored = plan_values.get(key, "")
        app_value = ytd.parse_money(stored)
        row = {"id": rid, "kind": rid, "label": label, "role": "", "group": GROUP_PLAN, "app_value": round(app_value, 2),
               "report_reason": None, "auto_matched": False, **_monarch_side(mapped, liability),
               "write": {"kind": rid, "ref": "|".join(key), "field": key[2], "old": stored, "new": ""}}
        if not mapped:
            row.update(status="not_in_monarch", monarch_value=None, monarch_accounts=[], write=None)
        else:
            row["status"] = "differs"
            row["write"]["new"] = _money_text(row["monarch_value"])
        finish(row)

    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: (order.get(r["group"], 99), r["label"].casefold()))
    return {
        "has_balances": True, "as_of": as_of_date, "latest": latest, "tolerance": tolerance, "dates": dates,
        "rows": rows, "unmatched": sorted(unmatched, key=lambda u: u["label"].casefold()), "ignored": len(ignored),
        "ignored_accounts": sorted(ignored, key=lambda u: u["label"].casefold()),
        "import": last_import, "last_ok_import": last_ok,
        "app_targets": [{"id": f"setup:{n}", "label": n, "role": ro} for n, ro, _ in sorted(setup_rows.values(), key=lambda t: t[0].casefold())]
                       + [{"id": rid, "label": v[0], "role": ""} for rid, v in PLAN_TARGETS.items()],
    }


# ------------------------------------------------------------------------------ mapping
@_store_errors
def set_mapping(input_dir: str | Path, account_key: str, target: str | None) -> dict[str, Any]:
    """Save (or with ``target`` None/'' clear) the match for a Monarch account. ``target`` is a row id
    (``setup:<account>``, ``plan:home`` ...) or ``ignore``."""
    base = Path(input_dir).parent
    with active_plan.workspace_store(base, write=True) as store:
        repo = store.monarch
        known = {a["account_key"] for a in repo.accounts_as_of(repo.latest_date() or "9999-12-31")}
        if account_key not in known:
            raise ReconcileError(f"unknown Monarch account {account_key!r}")
        if not target:
            repo.clear_mapping(account_key)
            return {"account_key": account_key, "mapping": None}
        if target == MAP_IGNORE:
            repo.set_mapping(account_key, MAP_IGNORE, "")
        elif target in PLAN_TARGETS:
            repo.set_mapping(account_key, target, "")
        elif target.startswith("setup:"):
            names = {str(r.get("Account") or "").strip().casefold(): str(r.get("Account") or "").strip()
                     for r in store.dataset("ytd_account_setup").rows()}
            ref = names.get(target[len("setup:"):].strip().casefold())
            if ref is None:
                raise ReconcileError(f"no Accounts & Sources account named {target[len('setup:'):]!r}")
            repo.set_mapping(account_key, MAP_SETUP, ref)
        else:
            raise ReconcileError(f"unknown match target {target!r}")
        return {"account_key": account_key, "mapping": repo.mapping()[account_key]}


# ------------------------------------------------------------------------------ preview / apply / undo
def _select(rows: list[dict[str, Any]], items: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_id = {r["id"]: r for r in rows}
    chosen, rejected, seen = [], [], set()
    for item in items:
        rid = str(item.get("id") or "")
        if rid in seen:
            continue
        seen.add(rid)
        row = by_id.get(rid)
        if row is None:
            rejected.append({"id": rid, "reason": "no such row"})
        elif not row["updatable"]:
            rejected.append({"id": rid, "reason": row.get("report_reason") or "nothing to update"})
        elif item.get("expected_new") not in (None, "") and str(item["expected_new"]) != row["write"]["new"]:
            rejected.append({"id": rid, "reason": "Monarch's number changed since the preview; preview again"})
        else:
            chosen.append(row)
    return chosen, rejected


def _change(row: dict[str, Any]) -> dict[str, Any]:
    w = row["write"]
    return {"id": row["id"], "label": row["label"], "kind": w["kind"], "ref": w["ref"], "field": w["field"],
            "old": w["old"], "new": w["new"], "app_value": row["app_value"], "monarch_value": row["monarch_value"]}


@_store_errors
def preview(input_dir: str | Path, items: list[dict[str, Any]], as_of: str | None = None, *,
            tolerance: float = DEFAULT_TOLERANCE, today: date | None = None) -> dict[str, Any]:
    data = build_rows(input_dir, as_of, tolerance=tolerance, today=today)
    chosen, rejected = _select(data["rows"], items)
    return {"as_of": data.get("as_of"), "changes": [_change(r) for r in chosen], "rejected": rejected}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@_store_errors
def apply(input_dir: str | Path, items: list[dict[str, Any]], as_of: str | None = None, *,
          tolerance: float = DEFAULT_TOLERANCE, today: date | None = None) -> dict[str, Any]:
    """Write the chosen rows' Monarch numbers into the app and log each change.

    The rows are recomputed here (never trusted from the page); an item whose ``expected_new`` no longer
    matches is rejected so a stale preview cannot write a different number than the one shown.
    """
    input_dir = Path(input_dir)
    data = build_rows(input_dir, as_of, tolerance=tolerance, today=today)
    chosen, rejected = _select(data["rows"], items)
    if not chosen:
        return {"as_of": data.get("as_of"), "applied": [], "rejected": rejected}
    base = input_dir.parent
    applied = []
    with active_plan.workspace_store(base, write=True) as store:
        with store.transaction():
            setup_changes = [r for r in chosen if r["write"]["kind"] == MAP_SETUP]
            if setup_changes:
                rows = [ytd.normalize_account_setup(r) for r in ytd.read_account_setup(input_dir)]
                for r in setup_changes:
                    w = r["write"]
                    for row in rows:
                        if row["Account"].strip().casefold() == w["ref"].casefold():
                            _set_setup_value(row, w["new"])
                store.dataset("ytd_account_setup").replace_all(rows)
            for r in chosen:
                w = r["write"]
                if w["kind"] in PLAN_TARGETS:
                    section, sub, label = w["ref"].split("|")
                    store.set_value(section, sub, label, w["new"])
                entry_id = store.monarch.log_change(_now(), w["kind"], w["ref"], w["field"], r["label"], w["old"], w["new"], data["as_of"])
                applied.append({**_change(r), "change_id": entry_id})
    return {"as_of": data["as_of"], "applied": applied, "rejected": rejected}


def _current_text(store: Any, input_dir: Path, kind: str, ref: str, field: str) -> str:
    if kind == MAP_SETUP:
        for row in ytd.read_account_setup(input_dir):
            if str(row.get("Account") or "").strip().casefold() == ref.casefold():
                return str(row.get(field) or "").strip()
        raise ReconcileError(f"account {ref!r} is no longer in Accounts & Sources")
    section, sub, label = ref.split("|")
    found = store.find_rows(section, sub, label)
    return str(found[-1]["value"]).strip() if found else ""


@_store_errors
def undo(input_dir: str | Path, change_id: int) -> dict[str, Any]:
    """Restore the value a logged change replaced, but only while the app still holds the number that change
    wrote; otherwise someone has edited it since and Undo refuses rather than overwrite that edit."""
    input_dir = Path(input_dir)
    with active_plan.workspace_store(input_dir.parent, write=True) as store:
        entry = store.monarch.log_entry(int(change_id))
        if entry["undone_at"]:
            raise ReconcileError("that change was already undone")
        current = _current_text(store, input_dir, entry["kind"], entry["ref"], entry["field"])
        if not _same_amount(current, entry["new_value"]):
            raise ReconcileError(f"{entry['label']} is now {current or 'blank'}, not the {entry['new_value']} this change wrote, so it was not undone")
        with store.transaction():
            if entry["kind"] == MAP_SETUP:
                rows = [ytd.normalize_account_setup(r) for r in ytd.read_account_setup(input_dir)]
                for row in rows:
                    if row["Account"].strip().casefold() == entry["ref"].casefold():
                        _set_setup_value(row, entry["old_value"])
                store.dataset("ytd_account_setup").replace_all(rows)
            else:
                section, sub, label = entry["ref"].split("|")
                store.set_value(section, sub, label, entry["old_value"])
            store.monarch.mark_undone(entry["id"], _now())
        return {"change_id": entry["id"], "label": entry["label"], "restored": entry["old_value"]}


@_store_errors
def change_log(input_dir: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        return store.monarch.log_entries(limit)
