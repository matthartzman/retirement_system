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
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import active_plan, platform_runtime
from . import ytd_tracking as ytd

DEFAULT_TOLERANCE = 1.0

# Auto-update guard: a policy-"auto" difference is held for the inbox, not written overnight, when it is both
# over AUTO_MAX_PCT of the app's number and over AUTO_MAX_ABS dollars.
AUTO_MAX_PCT = 0.10
AUTO_MAX_ABS = 5000.0
AUTO_HOLD_BIG = "Change is over 10% and $5,000: confirm it here before it changes."

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
REPORT_ONLY_APP = "The app is the source for this account (policy: app is source). Change the policy to update it from Monarch."
REPORT_ONLY_STREAM = "This annuity's value comes from its income stream's base value. Change it where the income stream is set up."


# Dynamic targets (one per row the plan holds): saved match kind == the target id.
DYN_OTHER_ASSET, DYN_NOTE, DYN_LIABILITY = "other_asset:", "note:", "liability:"
DYN_PREFIXES = (DYN_OTHER_ASSET, DYN_NOTE, DYN_LIABILITY)
KIND_PENDING = "pending"  # seeded from the mapping CSV, resolved against the plan's rows here
_OTHER_ASSET_TYPES = ("auto", "boat", "start-up equity", "art", "collectible", "other")


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


DYN_CASH_LOT = "cash_lot:"
CASH_LOT_FIELD = "shares+purchase_date"  # a cash account's one CASH lot: balance and its date change together
OTHER_ASSET_FIELD = "value+as_of_date"  # one logged change writes both cells, so one Undo restores both


def _like_date(existing: str, iso: str) -> str:
    """``iso`` written in the style of ``existing`` (the plan keeps some dates as m/d/yyyy)."""
    if "/" in (existing or "") and re.match(r"\d{4}-\d{2}-\d{2}$", iso or ""):
        y, m, d = iso.split("-")
        return f"{int(m)}/{int(d)}/{y}"
    return iso


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


def _same_current(a: str, b: str) -> bool:
    """``_same_amount`` for one cell, or for a ``value|date`` pair (amount compared as a number, date as text)."""
    if "|" in a or "|" in b:
        (a1, _, a2), (b1, _, b2) = a.partition("|"), b.partition("|")
        return _same_amount(a1, b1) and a2.strip() == b2.strip()
    return _same_amount(a, b)


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


def _row_policy(monarch: list[dict[str, Any]]) -> str:
    """One policy for a row fed by several Monarch accounts: any ``app`` wins (never write), then ``ask``
    unless every account is ``auto``."""
    policies = {a.get("policy") or "ask" for a in monarch}
    if "app" in policies:
        return "app"
    return "auto" if policies == {"auto"} else "ask"


def _dynamic_context(plan_values: dict[tuple[str, str, str], str], liabilities: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Every row-level target the plan holds: Other Asset Items, Note Receivable notes, liabilities.
    ``id -> {label, name, app_text, liability, group}``."""
    out: dict[str, dict[str, Any]] = {}
    subs: dict[tuple[str, str], dict[str, str]] = {}
    for (section, sub, label), value in plan_values.items():
        if section in ("Other Assets", "Note Receivable") and sub:
            subs.setdefault((section, sub), {})[label] = value
    for (section, sub), vals in subs.items():
        name = vals.get("name") or sub
        if section == "Other Assets" and re.match(r"Other Asset\s+\d+$", sub, re.I):
            out[DYN_OTHER_ASSET + sub] = {"label": f"{name} (other asset)", "name": name, "app_text": vals.get("value", ""),
                                          "as_of": vals.get("as_of_date", ""), "liability": False}
        elif section == "Note Receivable" and re.match(r"Note\s+\d+$", sub, re.I):
            out[DYN_NOTE + sub] = {"label": f"{name} (note face value)", "name": name, "app_text": vals.get("face_value", ""), "liability": False}
    for r in liabilities:
        lid = str(r.get("liability_id") or "").strip()
        if lid:
            out[DYN_LIABILITY + lid] = {"label": f"{r.get('label') or lid} (liability)", "name": str(r.get("label") or lid),
                                        "app_text": str(r.get("balance") or ""), "liability": True,
                                        "type": str(r.get("type") or "")}
    return out


def _resolve_pending(ref: str, dyn: dict[str, dict[str, Any]]) -> str | None:
    """Resolve a seeded ``"<App Location>|<App Field>"`` to one dynamic target, or None when it matches
    none or several (the page then offers it for a hand match)."""
    _, _, field = ref.partition("|")
    core = field.strip()
    prefix, sep, rest = core.partition(" - ")
    if sep and prefix.strip().casefold() in _OTHER_ASSET_TYPES + ("liabilities", "redmane note"):
        core = rest if prefix.strip().casefold() in _OTHER_ASSET_TYPES + ("liabilities",) else core
    core = re.sub(r"\s*-?\s*(face value|balance)$", "", core.strip(), flags=re.I).strip().casefold()
    if not core:
        return None
    if field.casefold().startswith("liabilities"):
        wants: tuple[str, ...] = (DYN_LIABILITY,)
    elif "note" in field.casefold() and "face" in field.casefold():
        wants = (DYN_NOTE,)
    else:  # a bare name ("Amex") may be an other asset or a liability (credit card)
        wants = (DYN_OTHER_ASSET, DYN_LIABILITY)
    pool = {tid: d["name"].casefold() for tid, d in dyn.items() if tid.startswith(wants)}
    whole = lambda a, b: re.search(rf"(?<!\w){re.escape(a)}(?!\w)", b) is not None  # a is a whole word/phrase in b
    hits = [tid for tid, n in pool.items() if n == core] or [tid for tid, n in pool.items() if whole(core, n) or whole(n, core)]
    if not hits:  # "HELOC Balance" names the liability's type, not its label
        hits = [tid for tid in pool if tid.startswith(DYN_LIABILITY) and str(dyn[tid].get("type", "")).casefold() == core]
    return hits[0] if len(hits) == 1 else None


def _auto_hold(row: dict[str, Any]) -> str | None:
    diff = abs(row["difference"] or 0.0)
    if diff > AUTO_MAX_ABS and diff > AUTO_MAX_PCT * max(abs(row["app_value"]), 1.0):
        return AUTO_HOLD_BIG
    return None


def _monarch_side(monarch: list[dict[str, Any]], liability: bool) -> dict[str, Any]:
    total = sum(a["balance"] for a in monarch)
    return {"policy": _row_policy(monarch) if monarch else "ask",
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
        liabilities = store.liabilities.rows()
        holdings = store.holdings.rows()

    cash_lots = _cash_only_lots(holdings)
    setup = ytd.read_account_setup(input_dir)
    summary = ytd.ytd_summary(input_dir, today=today)
    growth = {str(r.get("account") or "").strip().casefold(): r
              for r in (summary.get("investment_balance") or {}).get("account_growth_rows", [])}
    plan_values = _read_plan_values(input_dir)
    dyn = _dynamic_context(plan_values, liabilities)

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
    closed_quiet: list[dict[str, str]] = []  # closed and empty: nothing to decide
    parked: list[dict[str, str]] = []  # matched to something the page cannot update (e.g. an annuity), policy app/ignore
    for acct in monarch_accounts:
        saved = mapping.get(acct["account_key"])
        target = None
        auto = False
        if saved:
            if saved["kind"] == MAP_IGNORE or saved.get("policy") == "ignore":
                ignored.append({"account_key": acct["account_key"], "label": acct["account"]})
                continue
            if saved["kind"] == MAP_SETUP and saved["ref"].casefold() in setup_rows:
                target = "setup:" + setup_rows[saved["ref"].casefold()][0]
            elif saved["kind"] in PLAN_TARGETS:
                target = saved["kind"]
            elif saved["kind"] in dyn:
                target = saved["kind"]
            elif saved["kind"] == KIND_PENDING:
                target = _resolve_pending(saved["ref"], dyn)
        elif acct["account"].strip().casefold() in setup_rows:
            target = "setup:" + setup_rows[acct["account"].strip().casefold()][0]
            auto = True
        if target is None and saved and saved["kind"] == KIND_PENDING and saved.get("policy") in ("app", "ignore"):
            parked.append({"account_key": acct["account_key"], "label": acct["account"], "ref": saved["ref"], "policy": saved["policy"]})
            continue
        if target is None and acct["closed"] and abs(acct["last_balance"]) < 0.005:
            closed_quiet.append({"account_key": acct["account_key"], "label": acct["account"], "last_date": acct["last_date"]})
            continue
        if target is None:
            if acct["closed"]:  # stopped syncing with money still on it: flag it
                unmatched.append({
                    "id": "monarch:" + acct["account_key"], "account_key": acct["account_key"], "label": acct["account"],
                    "status": "closed_with_balance", "monarch_value": acct["last_balance"], "closed": True,
                    "closed_since": acct["last_date"], "saved_mapping": saved or None,
                })
            elif abs(acct["balance"]) >= 0.005:
                unmatched.append({
                    "id": "monarch:" + acct["account_key"], "account_key": acct["account_key"], "label": acct["account"],
                    "status": "not_in_app", "monarch_value": acct["balance"], "closed": acct["closed"],
                    "saved_mapping": saved or None,
                })
            continue
        by_target.setdefault(target, []).append({**acct, "auto": auto, "policy": (saved or {}).get("policy") or "ask"})

    rows: list[dict[str, Any]] = []

    def finish(row: dict[str, Any]) -> None:
        if row["monarch_value"] is None:
            row["difference"] = None
        else:
            row["difference"] = round(row["monarch_value"] - row["app_value"], 2)
            if row["status"] in ("match", "differs"):
                row["status"] = "differs" if abs(row["difference"]) >= tolerance else "match"
        if row["status"] == "differs" and row.get("policy") == "app":
            row["status"], row["report_reason"] = "report_only", REPORT_ONLY_APP
        row["auto_hold"] = _auto_hold(row) if row["status"] == "differs" and row.get("policy") == "auto" else None
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
        elif role == INVESTMENT_ROLE and key in cash_lots:  # a cash-only account: its one CASH lot is the balance
            lot = cash_lots[key]
            new_date = _like_date(str(lot.get("purchase_date") or ""), max(a["balance_date"] for a in mapped))
            row.update(status="differs", write={
                "kind": DYN_CASH_LOT + name, "ref": name, "field": CASH_LOT_FIELD,
                "old": f"{str(lot.get('shares') or '').strip()}|{str(lot.get('purchase_date') or '').strip()}",
                "new": f"{_money_text(row['monarch_value'])}|{new_date}"})
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

    # ---- row-level targets: Other Asset Items (value + as-of date), notes, liabilities
    for tid, d in dyn.items():
        mapped = by_target.get(tid, [])
        if not mapped:
            continue  # no match: nothing to show (unmatched Monarch accounts are listed separately)
        stored = d["app_text"]
        app_value = ytd.parse_money(stored)
        row = {"id": tid, "kind": tid, "label": d["label"], "role": "", "group": GROUP_PLAN, "app_value": round(app_value, 2),
               "report_reason": None, "auto_matched": False, "status": "differs", **_monarch_side(mapped, d["liability"])}
        new_text = _money_text(row["monarch_value"])
        if tid.startswith(DYN_OTHER_ASSET):
            when = max(a["balance_date"] for a in mapped)
            new_date = _like_date(d["as_of"], when)
            row["write"] = {"kind": tid, "ref": tid[len(DYN_OTHER_ASSET):], "field": OTHER_ASSET_FIELD,
                            "old": f"{stored}|{d['as_of']}", "new": f"{new_text}|{new_date}"}
        elif tid.startswith(DYN_NOTE):
            row["write"] = {"kind": tid, "ref": "|".join(("Note Receivable", tid[len(DYN_NOTE):], "face_value")),
                            "field": "face_value", "old": stored, "new": new_text}
        else:
            row["write"] = {"kind": tid, "ref": tid[len(DYN_LIABILITY):], "field": "balance", "old": stored, "new": new_text}
        finish(row)

    order = {g: i for i, g in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda r: (order.get(r["group"], 99), r["label"].casefold()))
    return {
        "has_balances": True, "as_of": as_of_date, "latest": latest, "tolerance": tolerance, "dates": dates,
        "rows": rows, "unmatched": sorted(unmatched, key=lambda u: u["label"].casefold()), "ignored": len(ignored),
        "closed_accounts": sorted(closed_quiet, key=lambda u: u["label"].casefold()),
        "parked_accounts": sorted(parked, key=lambda u: u["label"].casefold()),
        "ignored_accounts": sorted(ignored, key=lambda u: u["label"].casefold()),
        "import": last_import, "last_ok_import": last_ok,
        "app_targets": [{"id": f"setup:{n}", "label": n, "role": ro} for n, ro, _ in sorted(setup_rows.values(), key=lambda t: t[0].casefold())]
                       + [{"id": rid, "label": v[0], "role": ""} for rid, v in PLAN_TARGETS.items()]
                       + [{"id": tid, "label": d["label"], "role": ""} for tid, d in dyn.items()],
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
        elif target.startswith(DYN_PREFIXES):
            known_dyn = _dynamic_context(_read_plan_values(Path(input_dir)), store.liabilities.rows())
            if target not in known_dyn:
                raise ReconcileError(f"no such plan row {target!r}")
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


@_store_errors
def set_policy(input_dir: str | Path, account_key: str, policy: str) -> dict[str, Any]:
    """Set what happens when a matched Monarch account differs: ask / auto / app / ignore. Store errors
    (unknown account, bad policy) surface as ReconcileError via ``_store_errors``."""
    with active_plan.workspace_store(Path(input_dir).parent, write=True) as store:
        repo = store.monarch
        if account_key in repo.mapping():
            repo.set_policy(account_key, policy)
        else:
            # Matched by name only so far: save that match (kind and ref) so the policy has a row to live on.
            names = {str(r.get("Account") or "").strip().casefold(): str(r.get("Account") or "").strip()
                     for r in store.dataset("ytd_account_setup").rows()}
            acct = next((a for a in repo.accounts_as_of(repo.latest_date() or "9999-12-31") if a["account_key"] == account_key), None)
            ref = names.get((acct or {}).get("account", "").strip().casefold())
            if ref is None:
                raise ReconcileError("match this Monarch account to an app account before choosing a policy")
            repo.set_mapping(account_key, MAP_SETUP, ref, policy)
        return {"account_key": account_key, "policy": policy}


@_store_errors
def seed_from_csv(input_dir: str | Path, csv_text: str, overwrite: bool = False) -> dict[str, Any]:
    """Save matches and policies from the mapping CSV (see ``monarch_mapping_seed``)."""
    from . import monarch_mapping_seed
    return {"seed": monarch_mapping_seed.seed_mapping(Path(input_dir).parent, csv_text=csv_text, overwrite=overwrite)}


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
          tolerance: float = DEFAULT_TOLERANCE, today: date | None = None, source: str = "manual") -> dict[str, Any]:
    """Write the chosen rows' Monarch numbers into the app and log each change.

    The rows are recomputed here (never trusted from the page); an item whose ``expected_new`` no longer
    matches is rejected so a stale preview cannot write a different number than the one shown.
    """
    if source not in ("manual", "auto"):
        raise ReconcileError(f"source must be 'manual' or 'auto', got {source!r}")
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
                if w["kind"] in PLAN_TARGETS or w["kind"].startswith(DYN_NOTE):
                    section, sub, label = w["ref"].split("|")
                    store.set_value(section, sub, label, w["new"])
                elif w["kind"].startswith(DYN_OTHER_ASSET):
                    _write_other_asset(store, w["ref"], *w["new"].split("|"))
                elif w["kind"].startswith(DYN_LIABILITY):
                    _write_liability_balance(store, w["ref"], w["new"])
                elif w["kind"].startswith(DYN_CASH_LOT):
                    _write_cash_lot(store, w["ref"], *w["new"].split("|"))
                entry_id = store.monarch.log_change(_now(), w["kind"], w["ref"], w["field"], r["label"], w["old"], w["new"], data["as_of"], source)
                applied.append({**_change(r), "change_id": entry_id})
    return {"as_of": data["as_of"], "applied": applied, "rejected": rejected}


@_store_errors
def auto_apply(input_dir: str | Path, *, tolerance: float = DEFAULT_TOLERANCE, today: date | None = None) -> dict[str, Any]:
    """Copy Monarch's number into every row whose policy is ``auto`` and whose change passes the guards
    (see ``_auto_hold``). Held rows stay in the page's inbox with their reason. Each write is logged with
    source ``auto`` so it can be undone (``undo_auto``)."""
    data = build_rows(input_dir, None, tolerance=tolerance, today=today)
    due = [r for r in data["rows"] if r.get("policy") == "auto" and r["updatable"]]
    held = [{"id": r["id"], "label": r["label"], "reason": r["auto_hold"]} for r in due if r["auto_hold"]]
    items = [{"id": r["id"], "expected_new": r["write"]["new"]} for r in due if not r["auto_hold"]]
    out = apply(input_dir, items, data.get("as_of"), tolerance=tolerance, today=today, source="auto") if items else {"applied": [], "rejected": []}
    return {"as_of": data.get("as_of"), "applied": out["applied"], "rejected": out["rejected"], "held": held}


@_store_errors
def undo_auto(input_dir: str | Path) -> dict[str, Any]:
    """Undo every automatic change not yet undone, newest first. A value edited since is left alone and listed."""
    undone, skipped = [], []
    for entry in change_log(input_dir, limit=10_000):
        if entry["source"] != "auto" or entry["undone_at"]:
            continue
        try:
            undo(input_dir, entry["id"])
            undone.append(entry["label"])
        except ReconcileError as exc:
            skipped.append({"label": entry["label"], "reason": str(exc)})
    return {"undone": undone, "skipped": skipped}


def _cash_only_lots(holdings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``account casefold -> its lot`` for accounts whose holdings are exactly one CASH lot (e.g. a checking account)."""
    by_acct: dict[str, list[dict[str, Any]]] = {}
    for r in holdings:
        by_acct.setdefault(str(r.get("account") or "").strip().casefold(), []).append(r)
    return {k: lots[0] for k, lots in by_acct.items()
            if k and len(lots) == 1 and str(lots[0].get("symbol") or "").strip().upper() == "CASH"}


def _find_cash_lot(rows: list[dict[str, Any]], account: str) -> dict[str, Any]:
    lots = _cash_only_lots([r for r in rows if str(r.get("account") or "").strip().casefold() == account.casefold()])
    if not lots:
        raise ReconcileError(f"{account!r} no longer has a single CASH holding")
    return next(iter(lots.values()))


def _write_cash_lot(store: Any, account: str, shares: str, when: str) -> None:
    ds = store.holdings
    rows = ds.rows()
    lot = _find_cash_lot(rows, account)
    lot["shares"], lot["purchase_date"] = shares, when
    ds.replace_all(rows, header=ds.extra_columns())


def _write_other_asset(store: Any, sub: str, value: str, as_of: str) -> None:
    store.set_value("Other Assets", sub, "value", value)
    store.set_value("Other Assets", sub, "as_of_date", as_of)


def _write_liability_balance(store: Any, liability_id: str, balance: str) -> None:
    ds = store.liabilities
    rows = ds.rows()
    hit = [r for r in rows if str(r.get("liability_id") or "").strip() == liability_id]
    if not hit:
        raise ReconcileError(f"liability {liability_id!r} is no longer in the plan")
    hit[0]["balance"] = balance
    ds.replace_all(rows, header=ds.extra_columns())


def _current_text(store: Any, input_dir: Path, kind: str, ref: str, field: str) -> str:
    if kind == MAP_SETUP:
        for row in ytd.read_account_setup(input_dir):
            if str(row.get("Account") or "").strip().casefold() == ref.casefold():
                return str(row.get(field) or "").strip()
        raise ReconcileError(f"account {ref!r} is no longer in Accounts & Sources")
    if kind.startswith(DYN_OTHER_ASSET):
        cell = lambda label: (store.find_rows("Other Assets", ref, label) or [{"value": ""}])[-1]["value"]
        return f"{str(cell('value')).strip()}|{str(cell('as_of_date')).strip()}"
    if kind.startswith(DYN_CASH_LOT):
        lot = _find_cash_lot(store.holdings.rows(), ref)
        return f"{str(lot.get('shares') or '').strip()}|{str(lot.get('purchase_date') or '').strip()}"
    if kind.startswith(DYN_LIABILITY):
        for row in store.liabilities.rows():
            if str(row.get("liability_id") or "").strip() == ref:
                return str(row.get("balance") or "").strip()
        raise ReconcileError(f"liability {ref!r} is no longer in the plan")
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
        if not _same_current(current, entry["new_value"]):
            raise ReconcileError(f"{entry['label']} is now {current or 'blank'}, not the {entry['new_value']} this change wrote, so it was not undone")
        with store.transaction():
            if entry["kind"] == MAP_SETUP:
                rows = [ytd.normalize_account_setup(r) for r in ytd.read_account_setup(input_dir)]
                for row in rows:
                    if row["Account"].strip().casefold() == entry["ref"].casefold():
                        _set_setup_value(row, entry["old_value"])
                store.dataset("ytd_account_setup").replace_all(rows)
            elif entry["kind"].startswith(DYN_OTHER_ASSET):
                _write_other_asset(store, entry["ref"], *entry["old_value"].split("|"))
            elif entry["kind"].startswith(DYN_LIABILITY):
                _write_liability_balance(store, entry["ref"], entry["old_value"])
            elif entry["kind"].startswith(DYN_CASH_LOT):
                _write_cash_lot(store, entry["ref"], *entry["old_value"].split("|"))
            else:
                section, sub, label = entry["ref"].split("|")
                store.set_value(section, sub, label, entry["old_value"])
            store.monarch.mark_undone(entry["id"], _now())
        return {"change_id": entry["id"], "label": entry["label"], "restored": entry["old_value"]}


@_store_errors
def change_log(input_dir: str | Path, limit: int = 100) -> list[dict[str, Any]]:
    with active_plan.workspace_store(Path(input_dir).parent) as store:
        return store.monarch.log_entries(limit)
