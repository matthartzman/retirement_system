"""What made up the change in Liquid Investments and Cash between two chart points.

The Trends pop-up splits "Change since <date>" into three lines that add up to it:

* Deposits & withdrawals: money that crossed the edge of the accounts switched on for the chart (paychecks in,
  spending and transfers to other accounts out). It is the sum of each account's own transactions, so a transfer
  between two included accounts cancels (both legs are in the sum) and one to an excluded account counts.
* Income less fees: cash dividends, interest, fund capital-gain distributions and return of capital, less fees,
  commissions, margin interest and foreign tax withheld.
* Market gain/loss: the rest (price change of what is held), computed in the page so the three always add up.

This module builds the per-account daily ledger the page sums: ``{account name: {YYYY-MM-DD: {"flows": f,
"income": i}}}``, keyed by the imported (Monarch) account name the balances use. Income comes from the broker
activity files where an account has one (their rows are the record of its dividends, interest and fees; the
importer drops the Monarch copies), else from the Monarch transactions in the income and fee categories.
Design: documentation/future/superpowers/plans/2026-11-06-alt-asset-gain-tax-and-change-breakdown-design-and-plan.md
section 3.4.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# Monarch categories that are income or charges on the account itself, not money moved in or out.
INCOME_CATEGORIES = frozenset({"dividends & capital gains", "interest", "financial fees"})
# Trades: cash and securities swap inside the account; the balance does not move.
TRADE_CATEGORIES = frozenset({"buy", "sell"})
# Broker activity kinds that are income (amounts signed as in the file; foreign tax withheld is negative).
BROKER_INCOME_KINDS = frozenset({"dividend", "interest", "cap_gain_short", "cap_gain_long", "foreign_tax",
                                 "return_of_capital"})
# Broker "other" rows that are income or a charge rather than a transfer, contribution or distribution.
_BROKER_OTHER_INCOME = re.compile(r"\b(fee|fees|margin interest|misc income|partnership)\b", re.I)


def account_key(name: str) -> str:
    """Match key for an account name: case, spacing and punctuation ignored ("Trust  Under Agreement" and
    "Trust Under Agreement" are one account; so are the two spellings of a card with a stray symbol)."""
    return re.sub(r"[^a-z0-9]+", "", str(name or "").casefold())


def _num(value: Any) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", "")) if value not in (None, "") else 0.0
    except ValueError:
        return 0.0


def broker_income(row: Mapping[str, Any]) -> float:
    """Income less fees in one broker activity row (0 for trades, transfers, contributions, distributions)."""
    kind = str(row.get("kind") or "")
    amount = _num(row.get("amount"))
    income = 0.0
    if kind in BROKER_INCOME_KINDS:
        income = amount
    elif kind == "other" and _BROKER_OTHER_INCOME.search(str(row.get("action") or "")):
        income = amount
    # Fees and commissions on any row (a trade's amount nets them, but they leave the account all the same).
    income -= abs(_num(row.get("fees"))) + abs(_num(row.get("commission")))
    return income


def ledger(transactions: Iterable[Mapping[str, Any]], broker_rows: Iterable[Mapping[str, Any]],
           broker_to_account: Mapping[str, str]) -> dict[str, Any]:
    """``{"daily": {account name: {day: {"flows", "income"}}}, "broker_covered": [account names]}``.

    ``transactions`` are the imported rows (Date, Account, Category, Amount); ``broker_rows`` the broker activity
    rows (run_date, account = Planner account id, kind, action, amount, fees, commission); ``broker_to_account``
    maps a Planner account id to the imported account name."""
    daily: dict[str, dict[str, dict[str, float]]] = {}

    def add(account: str, day: str, field: str, value: float) -> None:
        if not account or not day or not value:
            return
        cell = daily.setdefault(account, {}).setdefault(day, {"flows": 0.0, "income": 0.0})
        cell[field] = round(cell[field] + value, 2)

    covered: dict[str, str] = {}
    for row in broker_rows:
        account = broker_to_account.get(str(row.get("account") or ""))
        if not account:
            continue
        covered[account_key(account)] = account
        add(account, str(row.get("run_date") or "")[:10], "income", broker_income(row))

    for t in transactions:
        account = str(t.get("Account") or "").strip()
        category = str(t.get("Category") or "").strip().casefold()
        if not account or category in TRADE_CATEGORIES:
            continue
        day, amount = str(t.get("Date") or "")[:10], _num(t.get("Amount"))
        if category in INCOME_CATEGORIES:
            # The broker file is this account's income record when there is one.
            if account_key(account) not in covered:
                add(account, day, "income", amount)
        else:
            add(account, day, "flows", amount)

    return {"daily": {a: dict(sorted(days.items())) for a, days in sorted(daily.items())},
            "broker_covered": sorted(covered.values())}


def broker_account_names(setup_rows: Iterable[Mapping[str, Any]], aliases: Mapping[str, str] | None = None) -> dict[str, str]:
    """{Planner account id: imported account name} from the Accounts & Sources rows (Account, Mapped Investment
    Account). ``aliases`` ({imported name: setup row name}, the reconcile matches) wins when the imported name
    differs from the setup row's."""
    by_setup = {str(k).casefold(): v for v, k in (aliases or {}).items()}
    out: dict[str, str] = {}
    for row in setup_rows:
        plan_id = str(row.get("Mapped Investment Account") or "").strip()
        name = str(row.get("Account") or "").strip()
        if plan_id and name and plan_id not in out:
            out[plan_id] = by_setup.get(name.casefold(), name)
    return out


def payload(input_dir, base_dir, balances_db) -> dict[str, Any]:
    """The /api/liquid-change body for the active plan: its transactions, broker activity and account matches."""
    from src import active_plan
    from src import ytd_tracking as ytd

    from .live_snapshot import saved_setup_aliases

    names = broker_account_names(ytd.read_account_setup(input_dir), saved_setup_aliases(base_dir, balances_db))
    try:
        with active_plan.workspace_store(base_dir) as store:
            broker_rows = store.broker.activity()
    except Exception:  # no plan store: Monarch transactions only
        broker_rows = []
    return ledger(ytd.read_transactions(input_dir), broker_rows, names)
