"""Pull account type, match and ignore from the Retirement app into the reporter's balance store.

The Retirement app's Monarch Reconciliation page owns how each Monarch account maps to the plan (and whether
to ignore it). The reporter used to ask for the same thing in its own "Monarch accounts & mapping" table; it now
reads the app's answer once per import instead:

* a match to an Accounts & Sources row sets the account's ``app_account`` (used by the flows chart) and, when the
  user has not confirmed a type, the type from that row's Role;
* a match to a plan input (home, autos, mortgage) or a plan row (other asset, note, liability) sets the type the
  same way;
* policy ``ignore`` switches the account off in every chart.

Per-chart inclusion stays editable in the reporter's Accounts popovers; an ``ignore`` in the app wins at the next
sync. Never raises: a plan that cannot be read just leaves the store as it was.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
from typing import Any

from .account_registry import CHARTS, TYPES, connect

ROLE_TYPE = {
    "Investment": "Investment", "Cash / spending": "Cash", "Credit card": "Credit card", "Mortgage": "Loan",
    "HELOC": "Loan", "Loan": "Loan", "Other liability": "Loan", "Annuity/Pension": "Annuity/Pension",
    "Annuity": "Annuity/Pension", "Pension": "Annuity/Pension", "Offline asset": "Other",
}


def _type_for(kind: str, ref: str, roles: dict[str, str]) -> str | None:
    if kind == "setup_account":
        return ROLE_TYPE.get(roles.get(ref.casefold(), ""))
    if kind == "plan:home":
        return "Real estate"
    if kind == "plan:autos":
        return "Vehicle"
    if kind in ("plan:mortgage",) or kind.startswith("liability:"):
        return "Loan"
    if kind.startswith(("other_asset:", "note:")):
        return "Other"
    return None


def sync_from_app(db_path: str | Path, base_dir: str | Path) -> dict[str, Any]:
    try:
        from src import active_plan

        with active_plan.workspace_store(Path(base_dir)) as store:
            mapping = store.monarch.mapping()
            roles = {str(r.get("Account") or "").strip().casefold(): str(r.get("Role") or "").strip()
                     for r in store.dataset("ytd_account_setup").rows()}
    except Exception as exc:  # noqa: BLE001 - the plan may be missing, locked or older than the mapping tables
        return {"success": False, "error": f"{exc.__class__.__name__}: {exc}"}
    changed = {"app_account": 0, "type": 0, "ignored": 0}
    with closing(connect(db_path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS app_sync_ignored (account_key TEXT PRIMARY KEY)")
        was_ignored = {r[0] for r in conn.execute("SELECT account_key FROM app_sync_ignored")}
        known = {r["account_key"]: r for r in conn.execute("SELECT account_key, type, confirmed, app_account FROM accounts")}
        with conn:
            for key, m in mapping.items():
                row = known.get(key)
                if row is None:
                    continue
                kind, ref = m["kind"], m["ref"]
                if m.get("policy") == "ignore" or kind == "ignore":
                    for chart in CHARTS:
                        conn.execute("INSERT INTO account_prefs (chart, account_key, enabled) VALUES (?,?,0) "
                                     "ON CONFLICT(chart, account_key) DO UPDATE SET enabled=0", (chart, key))
                    conn.execute("INSERT OR IGNORE INTO app_sync_ignored (account_key) VALUES (?)", (key,))
                    changed["ignored"] += 1
                    continue
                if key in was_ignored:  # no longer ignored in the app: drop the override this sync set
                    conn.execute("DELETE FROM account_prefs WHERE account_key=?", (key,))
                    conn.execute("DELETE FROM app_sync_ignored WHERE account_key=?", (key,))
                    changed["un_ignored"] = changed.get("un_ignored", 0) + 1
                if kind == "setup_account" and (row["app_account"] or "") != ref:
                    conn.execute("UPDATE accounts SET app_account=? WHERE account_key=?", (ref, key))
                    changed["app_account"] += 1
                new_type = _type_for(kind, ref, roles)
                if new_type in TYPES and not row["confirmed"] and row["type"] != new_type:
                    conn.execute("UPDATE accounts SET type=?, confirmed=1 WHERE account_key=?", (new_type, key))
                    changed["type"] += 1
            for key in was_ignored - set(mapping):  # the match was removed in the app
                conn.execute("DELETE FROM account_prefs WHERE account_key=?", (key,))
                conn.execute("DELETE FROM app_sync_ignored WHERE account_key=?", (key,))
                changed["un_ignored"] = changed.get("un_ignored", 0) + 1
    return {"success": True, **changed}
