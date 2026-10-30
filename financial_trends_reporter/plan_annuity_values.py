from __future__ import annotations

"""Annuity and pension accounts valued at the plan's figure, not Monarch's hand-typed balance.

Design: documentation/future/superpowers/plans/2026-10-29-annuity-plan-values-design.md.

The match is the one the user already configured: Monarch account -> plan account (Trends registry
``app_account`` or the Planner reconcile page, see ``live_snapshot.saved_setup_aliases``) -> that Accounts &
Sources row's ``Mapped Investment Account`` (an Income Streams subsection) -> the engine's PV column. The value is
the plan-start row of the latest build's projection tables: what Recent Projections shows.
"""

from pathlib import Path
from typing import Any

# Income Streams subsection -> the engine's net-worth PV column (projection_tables.json key).
STREAM_COLUMNS = {
    "Member 1 Joint Annuity": "H Joint PV",
    "Member 2 Joint Annuity": "W Joint PV",
    "Member 1 Single Annuity": "H Single PV",
    "Member 2 Single Annuity": "W Single PV",
    "Member 2 Pension": "Pension PV",
}


def first_row_pv(doc: dict[str, Any] | None) -> dict[str, float]:
    """{PV column: value} from the plan-start (earliest) row of a projection_tables doc; {} when none."""
    rows = (((doc or {}).get("tables") or {}).get("net_worth") or {}).get("rows") or []
    rows = [r for r in rows if isinstance(r.get("year"), int)]
    if not rows:
        return {}
    values = min(rows, key=lambda r: r["year"]).get("values") or {}
    return {col: float(values[col]) for col in STREAM_COLUMNS.values()
            if isinstance(values.get(col), (int, float)) and not isinstance(values.get(col), bool)}


def match_values(accounts: list[dict[str, Any]], aliases: dict[str, str], stream_of: dict[str, str],
                 pv: dict[str, float]) -> dict[str, float]:
    """{account_key: plan value} for each Monarch account that resolves to exactly one PV column.

    Two accounts resolving to the same column are both left on Monarch rather than guessing a split.
    """
    by_column: dict[str, list[str]] = {}
    for a in accounts:
        column = STREAM_COLUMNS.get(stream_of.get(aliases.get(a["display_name"], ""), ""))
        if column in pv:
            by_column.setdefault(column, []).append(a["account_key"])
    return {keys[0]: pv[column] for column, keys in by_column.items() if len(keys) == 1}


def account_values(base_dir: Path, balances_db: Path) -> dict[str, float]:
    """The live lookup for ``balance_series``'s ``plan_values``. Never raises: no plan, no build, no store -> {}."""
    try:
        from src import ytd_tracking
        from . import account_registry, projections
        from .live_snapshot import saved_setup_aliases

        pv = first_row_pv(projections.load(Path(base_dir)))
        if not pv:
            return {}
        stream_of = {str(r.get("Account") or "").strip(): str(r.get("Mapped Investment Account") or "").strip()
                     for r in ytd_tracking.read_account_setup(Path(base_dir) / "input")}
        return match_values(account_registry.list_accounts(balances_db), saved_setup_aliases(Path(base_dir), balances_db),
                            stream_of, pv)
    except Exception:  # noqa: BLE001 - a missing plan or store keeps Monarch's balances
        return {}
