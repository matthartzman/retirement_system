from __future__ import annotations

"""Daily balance series and chart totals from the Monarch balance store.

Pure functions over plain data (``dense_series`` and below take no database), so the
rules are easy to test:

* An account's value is carried forward across gaps inside [first row, last row] (and on to the newest
  date when its last row is within CLOSED_GRACE_DAYS of it, a late sync) and is 0 outside that, so a closed or replaced account never inflates later history and a
  not-yet-opened one never inflates earlier history.
* A chart total is the sum over the accounts enabled for that chart. Liabilities are
  already negative in Monarch's export, so net worth is a plain sum.
* Hover detail omits accounts whose value on that date is zero.
* Where Monarch has no balance for a date, the log's plan-derived figure is used and the
  point is tagged ``source: "plan"``.
"""

from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from . import account_registry
from .balance_store import connect

ZERO_EPSILON = 0.005
# An account whose last row is within this many days of the newest date is a late sync, not a closed account.
CLOSED_GRACE_DAYS = 3
MONARCH_CHARTS = ("networth", "holdings")


def _daterange(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def dense_series(rows: Iterable[tuple[str, str, float]]) -> tuple[list[str], dict[str, list[float]]]:
    """``(date, account_key, balance)`` rows -> (ISO dates, {account_key: value per date}).

    Dates run daily from the earliest to the latest row across all accounts.
    """
    per_account: dict[str, dict[str, float]] = {}
    lo: str | None = None
    hi: str | None = None
    for d, key, balance in rows:
        per_account.setdefault(key, {})[d] = float(balance)
        lo = d if lo is None or d < lo else lo
        hi = d if hi is None or d > hi else hi
    if lo is None or hi is None:
        return [], {}
    days = _daterange(date.fromisoformat(lo), date.fromisoformat(hi))
    iso = [d.isoformat() for d in days]
    live_from = (date.fromisoformat(hi) - timedelta(days=CLOSED_GRACE_DAYS)).isoformat()
    series: dict[str, list[float]] = {}
    for key, by_date in per_account.items():
        first, last = min(by_date), max(by_date)
        if last >= live_from:
            last = hi  # still live: a late sync carries its last balance forward
        values: list[float] = []
        current = 0.0
        for d in iso:
            if d < first or d > last:
                values.append(0.0)
                continue
            current = by_date.get(d, current)
            values.append(current)
        series[key] = values
    return iso, series


def chart_totals(series: dict[str, list[float]], enabled_keys: Iterable[str], length: int) -> list[float]:
    """Per-date sum over ``enabled_keys`` (unknown keys are ignored)."""
    totals = [0.0] * length
    for key in enabled_keys:
        values = series.get(key)
        if values is None:
            continue
        for i, v in enumerate(values):
            totals[i] += v
    return [round(t, 2) for t in totals]


def enabled_keys(accounts: list[dict[str, Any]], chart: str) -> list[str]:
    return [a["account_key"] for a in accounts if a["enabled"].get(chart)]


def account_detail(
    accounts: list[dict[str, Any]], series: dict[str, list[float]], index: int, chart: str,
) -> list[dict[str, Any]]:
    """Accounts contributing to ``chart`` at date ``index``, omitting zero values, largest first."""
    out = []
    for a in accounts:
        if not a["enabled"].get(chart):
            continue
        value = series.get(a["account_key"], [0.0])[index]
        if abs(value) < ZERO_EPSILON:
            continue
        out.append({"account_key": a["account_key"], "display_name": a["display_name"], "type": a["type"], "value": round(value, 2)})
    out.sort(key=lambda r: abs(r["value"]), reverse=True)
    return out


def merge_with_log(dates: list[str], monarch_values: list[float], history: list[dict[str, Any]], plan_value) -> list[dict[str, Any]]:
    """Monarch points for every Monarch date, plus plan-derived log points for other dates.

    ``plan_value(entry)`` returns the log entry's figure for the chart (or None).
    """
    points = [{"date": d, "value": v, "source": "monarch"} for d, v in zip(dates, monarch_values)]
    covered = set(dates)
    for entry in history:
        d = str(entry.get("as_of_date") or "")
        value = plan_value(entry)
        if d and d not in covered and isinstance(value, (int, float)):
            points.append({"date": d, "value": round(float(value), 2), "source": "plan"})
    points.sort(key=lambda p: p["date"])
    return points


def _plan_networth(entry: dict[str, Any]):
    # Same rule as _plan_holdings: the entry's own Monarch figure beats the plan total.
    monarch = (entry.get("monarch_balances") or {}).get("net_worth")
    if isinstance(monarch, (int, float)):
        return monarch
    return (entry.get("net_worth") or {}).get("total")


def _plan_holdings(entry: dict[str, Any]):
    # The plan's figure counts annuities and pensions, which the holdings chart leaves out by default; the
    # entry's own toggle-aware Monarch figure (latest synced day carried forward) honours the toggles.
    monarch = (entry.get("monarch_balances") or {}).get("holdings")
    if isinstance(monarch, (int, float)):
        return monarch
    return (entry.get("holdings") or {}).get("current_value")


def load_rows(db_path: str | Path) -> list[tuple[str, str, float]]:
    with closing(connect(db_path)) as conn:
        return [(r["date"], r["account_key"], r["balance"]) for r in conn.execute("SELECT date, account_key, balance FROM balances")]


def balances_payload(db_path: str | Path, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Everything the charts need: dates, per-account series, registry rows and merged points.

    ``points`` uses the saved toggles; the client re-sums ``series`` when a toggle changes.
    """
    accounts = account_registry.list_accounts(db_path)
    dates, series = dense_series(load_rows(db_path))
    history = history or []
    points = {
        "networth": merge_with_log(dates, chart_totals(series, enabled_keys(accounts, "networth"), len(dates)), history, _plan_networth),
        "holdings": merge_with_log(dates, chart_totals(series, enabled_keys(accounts, "holdings"), len(dates)), history, _plan_holdings),
    }
    return {
        "dates": dates,
        "accounts": accounts,
        "series": {k: [round(v, 2) for v in vals] for k, vals in series.items()},
        "points": points,
    }


def snapshot_summary(db_path: str | Path) -> dict[str, Any] | None:
    """Latest-day figures for the daily log entry, or None when the store has no data."""
    db_path = Path(db_path)
    if not db_path.exists():
        return None
    accounts = account_registry.list_accounts(db_path)
    rows = load_rows(db_path)
    dates, series = dense_series(rows)
    if not dates:
        return None
    last = len(dates) - 1
    synced: dict[str, str] = {}   # each account's own last balance date (a late sync is carried forward)
    for d, key, _ in rows:
        if d > synced.get(key, ""):
            synced[key] = d
    return {
        "latest_date": dates[last],
        "net_worth": chart_totals(series, enabled_keys(accounts, "networth"), len(dates))[last],
        "holdings": chart_totals(series, enabled_keys(accounts, "holdings"), len(dates))[last],
        "by_account": [
            {"account": d["display_name"], "type": d["type"], "value": d["value"], "as_of": synced.get(d["account_key"])}
            for d in account_detail(accounts, series, last, "networth")
        ],
    }
