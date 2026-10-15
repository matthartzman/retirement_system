from __future__ import annotations

"""Monarch account registry: type classification, app-account mapping, per-chart toggles.

The Monarch balances export carries no account type, so a type is guessed from the
name (``classify``) and then confirmed or corrected by the user. Chart membership
(``networth`` / ``holdings`` / ``flows``) defaults from the type and can be overridden
per account and chart; an override is stored in ``account_prefs`` and ``enabled=None``
removes it, restoring the type default.
"""

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .balance_store import connect

TYPES = (
    "Cash", "Investment", "Retirement", "HSA", "Annuity/Pension",
    "Real estate", "Vehicle", "Loan", "Credit card", "Other",
)
CHARTS = ("networth", "holdings", "flows")

# Holdings: liquid investments + cash (checking, Venmo). Annuity/pension and "Other" are off by default.
_HOLDINGS_TYPES = {"Cash", "Investment", "Retirement", "HSA"}
# Flows: money moving between checking and investment accounts.
_FLOWS_TYPES = {"Investment", "Retirement", "HSA"}

# First match wins. Order matters: HSA before "savings" (Cash); Loan before Vehicle ("BMW Loan").
_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Loan", re.compile(r"\b(mortgage|heloc|home equity|loan)\b")),
    ("Credit card", re.compile(r"\b(visa|mastercar\w*|credit card|platinum card|amex|american express|discover)\b")),
    ("Annuity/Pension", re.compile(r"\b(annuity|pension)\b")),
    ("HSA", re.compile(r"\b(hsa|health savings)\b")),
    ("Retirement", re.compile(r"\b(ira|roth|401\s?\(?k\)?|403\s?\(?b\)?)\b")),
    ("Investment", re.compile(r"\b(brokerage|trust|ibond|i bond|treasury)\b")),
    ("Cash", re.compile(r"\b(checking|savings|venmo|paypal|money market)\b")),
    ("Vehicle", re.compile(r"^(19|20)\d\d\s+\S+")),
    ("Real estate", re.compile(r"^\d+\s+\S+.*\b\d{5}\b")),
)


def classify(name: str) -> str:
    text = " ".join((name or "").casefold().split())
    for type_name, pattern in _RULES:
        if pattern.search(text):
            return type_name
    return "Other"


def default_enabled(chart: str, type_name: str) -> bool:
    if chart == "networth":
        return True
    if chart == "holdings":
        return type_name in _HOLDINGS_TYPES
    if chart == "flows":
        return type_name in _FLOWS_TYPES
    raise ValueError(f"unknown chart {chart!r}")


def _classify_new(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT account_key, display_name FROM accounts WHERE type IS NULL").fetchall()
    if rows:
        with conn:
            conn.executemany(
                "UPDATE accounts SET type=? WHERE account_key=?",
                [(classify(r["display_name"]), r["account_key"]) for r in rows],
            )


def list_accounts(db_path: str | Path) -> list[dict[str, Any]]:
    """Every account with its type, mapping, latest balance and resolved chart toggles."""
    with closing(connect(db_path)) as conn:
        _classify_new(conn)
        prefs: dict[tuple[str, str], bool] = {
            (r["chart"], r["account_key"]): bool(r["enabled"])
            for r in conn.execute("SELECT chart, account_key, enabled FROM account_prefs")
        }
        out = []
        for r in conn.execute(
            "SELECT a.*, (SELECT balance FROM balances b WHERE b.account_key=a.account_key "
            "ORDER BY b.date DESC LIMIT 1) AS latest_balance FROM accounts a "
            "ORDER BY a.active DESC, a.display_name COLLATE NOCASE"
        ):
            enabled = {
                chart: prefs.get((chart, r["account_key"]), default_enabled(chart, r["type"]))
                for chart in CHARTS
            }
            out.append({
                "account_key": r["account_key"],
                "display_name": r["display_name"],
                "type": r["type"],
                "confirmed": bool(r["confirmed"]),
                "app_account": r["app_account"] or "",
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "active": bool(r["active"]),
                "latest_balance": r["latest_balance"],
                "enabled": enabled,
                "overridden": {chart: (chart, r["account_key"]) in prefs for chart in CHARTS},
            })
        return out


def set_account(db_path: str | Path, account_key: str, *, type: str | None = None, app_account: str | None = None) -> dict[str, Any]:
    """Update an account's type and/or app-account mapping. Raises ValueError on bad input."""
    if type is not None and type not in TYPES:
        raise ValueError(f"unknown account type {type!r}")
    with closing(connect(db_path)) as conn:
        if conn.execute("SELECT 1 FROM accounts WHERE account_key=?", (account_key,)).fetchone() is None:
            raise ValueError(f"unknown account {account_key!r}")
        with conn:
            if type is not None:
                conn.execute("UPDATE accounts SET type=?, confirmed=1 WHERE account_key=?", (type, account_key))
            if app_account is not None:
                conn.execute("UPDATE accounts SET app_account=?, confirmed=1 WHERE account_key=?", (app_account.strip() or None, account_key))
    return next(a for a in list_accounts(db_path) if a["account_key"] == account_key)


def set_prefs(db_path: str | Path, items: list[dict[str, Any]]) -> int:
    """Apply ``{chart, account_key, enabled}`` overrides atomically; ``enabled: null`` clears one.

    All-or-nothing: any invalid item raises ValueError and nothing is written.
    """
    with closing(connect(db_path)) as conn:
        known = {r["account_key"] for r in conn.execute("SELECT account_key FROM accounts")}
        for item in items:
            if item.get("chart") not in CHARTS:
                raise ValueError(f"unknown chart {item.get('chart')!r}")
            if item.get("account_key") not in known:
                raise ValueError(f"unknown account {item.get('account_key')!r}")
            if item.get("enabled") is not None and not isinstance(item["enabled"], bool):
                raise ValueError("enabled must be true, false or null")
        with conn:
            for item in items:
                if item["enabled"] is None:
                    conn.execute("DELETE FROM account_prefs WHERE chart=? AND account_key=?", (item["chart"], item["account_key"]))
                else:
                    conn.execute(
                        "INSERT INTO account_prefs (chart, account_key, enabled) VALUES (?,?,?) "
                        "ON CONFLICT(chart, account_key) DO UPDATE SET enabled=excluded.enabled",
                        (item["chart"], item["account_key"], int(item["enabled"])),
                    )
    return len(items)


def list_app_accounts(base_dir: str | Path) -> list[str]:
    """Account names from the plan's account setup, for the mapping dropdown. Never raises."""
    try:
        from src import ytd_tracking as ytd

        summary = ytd.ytd_summary(Path(base_dir) / "input")
        names = {
            str(row.get("Account") or "").strip()
            for row in summary.get("accounts", [])
            if str(row.get("Role") or "").strip() != "Ignore"
        }
        return sorted(n for n in names if n)
    except Exception:
        return []
