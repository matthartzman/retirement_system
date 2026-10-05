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

from src import spending_tracker, ytd_tracking as ytd  # noqa: E402
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


def _net_worth_from_account_setup(
    accounts: list[dict[str, Any]], growth_rows: list[dict[str, Any]] | None = None
) -> dict[str, float]:
    # Investment/annuity/pension accounts carry their live value in the
    # holdings-/income-stream-derived ``growth_rows`` (the same figures the
    # Holdings chart sums); the account-setup "Current Value" field is blank or
    # stale for them, which previously left net worth far below holdings value.
    live_values = {
        str(r.get("account") or "").strip(): ytd.parse_money(r.get("current_value"))
        for r in (growth_rows or [])
    }
    assets = 0.0
    account_liabilities = 0.0
    for row in accounts:
        role = str(row.get("Role") or "").strip()
        if role == "Ignore":
            continue
        name = str(row.get("Account") or "").strip()
        if role in ytd.GROWTH_ROLES and name in live_values:
            value = live_values[name]
        else:
            value = ytd.parse_money(row.get("Current Value") or row.get("Current Balance"))
        if role in LIABILITY_ROLES:
            account_liabilities += value
        else:
            assets += value
    return {"assets": assets, "account_liabilities": account_liabilities}


def _plan_rows(base_dir: Path, db_path: Path, filename: str) -> dict[tuple[str, str, str], str]:
    """{(section, subsection, label): value} for a section/subsection/label/value plan CSV."""
    content = read_plan_data_file(filename, base_dir, db_path)
    out: dict[tuple[str, str, str], str] = {}
    if not content:
        return out
    for row in csv.reader(io.StringIO(content)):
        if len(row) >= 4 and row[0] and not row[0].startswith("#"):
            out[(row[0].strip(), row[1].strip(), row[2].strip())] = row[3].strip()
    return out


def _amortized_balance(balance: float, annual_rate: float, payment: float, months: int) -> float:
    monthly_rate = annual_rate / 12.0
    for _ in range(max(0, months)):
        balance = max(0.0, balance * (1 + monthly_rate) - payment)
    return balance


def _plan_assets_and_mortgage(base_dir: Path, db_path: Path, as_of: date) -> dict[str, float]:
    """Non-account assets (home, startup equity, cash, autos) and the mortgage.

    Account setup only knows investment/annuity/pension balances; the plan
    inputs hold the rest, as the main app's Balance Sheet does. Values are the
    plan's own "as of plan start" figures; the mortgage is amortized from its
    plan-start balance (4/1/2026 in the spending inputs) to ``as_of``.
    """
    assets = _plan_rows(base_dir, db_path, "client_assets.csv")
    spending = _plan_rows(base_dir, db_path, "client_spending.csv")

    def money(rows, key):
        return ytd.parse_money(rows.get(key))

    other = {
        "home": money(assets, ("Other Assets", "Home", "value_as_of_plan_start")),
        "startup_equity": money(assets, ("Other Assets", "Startup Equity", "value")),
        "cash": money(assets, ("Other Assets", "Cash", "value")),
        "autos": money(assets, ("Other Assets", "Autos", "value")),
    }
    mortgage = money(spending, ("Cashflow", "Mortgage", "balance_as_of_plan_start"))
    if mortgage:
        rate = ytd.parse_money(str(spending.get(("Cashflow", "Mortgage", "interest_rate"), "0")).rstrip("%")) / 100.0
        payment = money(spending, ("Cashflow", "Mortgage", "monthly_payment"))
        start = date(2026, 4, 1)  # "Outstanding balance 4/1/2026" per the input's note
        months = (as_of.year - start.year) * 12 + (as_of.month - start.month) - (1 if as_of.day < start.day else 0)
        mortgage = _amortized_balance(mortgage, rate, payment, months)
    other["mortgage"] = mortgage
    return other


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

    # Tracking Type -> Group -> Category -> Merchant, for the expenses chart:
    # level 1 is displayed, levels 2-4 appear in the hover popup.
    ytd_expense_hierarchy = spending_tracker.ytd_spending_hierarchy(
        base_dir, (today or date.today()).year
    )

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
    from_accounts = _net_worth_from_account_setup(
        summary.get("accounts", []), inv.get("account_growth_rows", [])
    )
    plan = _plan_assets_and_mortgage(base_dir, db_path, today or date.today())
    plan_assets = plan["home"] + plan["startup_equity"] + plan["cash"] + plan["autos"]
    assets = from_accounts["assets"] + plan_assets
    liabilities = from_accounts["account_liabilities"] + liabilities_csv_total + plan["mortgage"]
    net_worth = {
        "home": round(plan["home"], 2),
        "other_assets": round(plan["startup_equity"] + plan["cash"] + plan["autos"], 2),
        "mortgage": round(plan["mortgage"], 2),
        "assets": round(assets, 2),
        "liabilities": round(liabilities, 2),
        "total": round(assets - liabilities, 2),
    }

    actual = summary.get("actual", {})
    cashflow = {
        "income": actual.get("income"),
        "expenses": actual.get("spending"),
        "taxes": actual.get("taxes"),
        # ytd_summary's "spending" already includes taxes paid, so net is
        # income - expenses (subtracting taxes again double-counted them).
        "net": (
            None
            if actual.get("income") is None or actual.get("spending") is None
            else round(actual["income"] - actual["spending"], 2)
        ),
    }

    # as_of_date is the log's dedup/sort key (trends_log.append_or_replace_entry
    # overwrites same-date entries) and must be the calendar day this snapshot
    # was taken -- NOT the latest transaction date. Those two routinely
    # diverge (bank transactions post with a lag, some days have none at
    # all), and keying on the transaction date caused any day without a
    # freshly-posted transaction to silently overwrite the prior day's whole
    # snapshot -- holdings/net-worth included, even though those change daily
    # independent of transaction activity. data_through_date keeps the
    # transaction-coverage info (what the YTD expense/income figures actually
    # reflect) available separately, for anything that wants it.
    as_of_date = (today or date.today()).isoformat()
    data_through_date = summary.get("through_date") or summary.get("ytd_end") or as_of_date

    return {
        "as_of_date": as_of_date,
        "data_through_date": data_through_date,
        "ytd_expenses_by_category": ytd_expenses_by_category,
        "ytd_expense_hierarchy": ytd_expense_hierarchy,
        "holdings": holdings,
        "net_worth": net_worth,
        "cashflow": cashflow,
    }
