from __future__ import annotations

"""Compute the four financial trend metric groups for one snapshot (ticket
306): YTD expenses by category, holdings value/performance, net worth, and
cashflow.

This is a genuinely separate app from retirement_system (its own entry
point, own server, own data file), but it imports retirement_system's own
calculation modules as a library rather than re-deriving spending/holdings
math -- almost everything here is `src.ytd_tracking.ytd_summary()`, the same
engine the main app's YTD dashboard already calls, plus a liabilities-CSV
summation for net worth (a plain sum, not a computation worth re-deriving).
"""

import csv
import io
import sys
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src import ytd_tracking as ytd  # noqa: E402
from src.plan_data_read import read_plan_data_file  # noqa: E402

# Account-setup roles ytd_tracking.ROLE_OPTIONS marks as liabilities -- their
# "Current Value"/"Current Balance" subtracts from, rather than adds to,
# net worth. Everything else non-Ignore is treated as an asset.
LIABILITY_ROLES = frozenset({"Credit card", "Mortgage", "HELOC", "Loan", "Other liability"})


def _liabilities_csv_total(base_dir: Path, db_path: Path) -> float:
    content = read_plan_data_file("client_liabilities.csv", base_dir, db_path)
    if not content:
        return 0.0
    total = 0.0
    for row in csv.DictReader(io.StringIO(content)):
        total += ytd.parse_money(row.get("balance"))
    return total


def _net_worth_from_account_setup(accounts: list[dict[str, Any]]) -> dict[str, float]:
    assets = 0.0
    account_liabilities = 0.0
    for row in accounts:
        role = str(row.get("Role") or "").strip()
        if role == "Ignore":
            continue
        value = ytd.parse_money(row.get("Current Value") or row.get("Current Balance"))
        if role in LIABILITY_ROLES:
            account_liabilities += value
        else:
            assets += value
    return {"assets": assets, "account_liabilities": account_liabilities}


def compute_snapshot(base_dir: str | Path, *, today=None) -> dict[str, Any]:
    """Return one snapshot's worth of the four metric groups.

    ``base_dir`` is the retirement_system workspace root (contains input/,
    local_state/) -- this app reads that workspace's data but writes its own
    log elsewhere (financial_trends_reporter/data/), never into
    retirement_system's own output/ or input/.
    """
    base_dir = Path(base_dir)
    input_dir = base_dir / "input"
    db_path = base_dir / "local_state" / "retirement_system_v10.db"

    summary = ytd.ytd_summary(input_dir, today=today)

    ytd_expenses_by_category = {
        row["category"]: row["amount"] for row in summary.get("category_totals", [])
    }

    inv = summary.get("investment_balance", {})
    current_value = inv.get("current_balance")
    prior_value = inv.get("prior_year_end_balance")
    growth = summary.get("actual", {}).get("growth")
    growth_pct = (growth / prior_value) if (growth is not None and prior_value) else None
    holdings = {
        "current_value": current_value,
        "prior_year_end_balance": prior_value,
        "ytd_growth": growth,
        "ytd_growth_pct": growth_pct,
        "by_account": inv.get("account_growth_rows", []),
    }

    liabilities_csv_total = _liabilities_csv_total(base_dir, db_path)
    from_accounts = _net_worth_from_account_setup(summary.get("accounts", []))
    assets = from_accounts["assets"]
    liabilities = from_accounts["account_liabilities"] + liabilities_csv_total
    net_worth = {
        "assets": round(assets, 2),
        "liabilities": round(liabilities, 2),
        "total": round(assets - liabilities, 2),
    }

    actual = summary.get("actual", {})
    cashflow = {
        "income": actual.get("income"),
        "expenses": actual.get("spending"),
        "taxes": actual.get("taxes"),
        "net": (
            None
            if actual.get("income") is None or actual.get("spending") is None or actual.get("taxes") is None
            else round(actual["income"] - actual["spending"] - actual["taxes"], 2)
        ),
    }

    return {
        "as_of_date": summary.get("through_date") or summary.get("ytd_end") or (today or date.today()).isoformat(),
        "ytd_expenses_by_category": ytd_expenses_by_category,
        "holdings": holdings,
        "net_worth": net_worth,
        "cashflow": cashflow,
    }
