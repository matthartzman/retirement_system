from __future__ import annotations

"""Monthly investment flows: aggregation, YTD summary and account toggles.

Input is a log entry's ``investment_flows_monthly`` (and, when logged, the same shape keyed by
``YYYY-MM-DD`` in ``investment_flows_daily``, which the client buckets by the selected scope):
``{account: {"YYYY-MM": {"to_checking", "from_checking"}}}`` where ``from_checking`` is money
contributed INTO the investment account and ``to_checking`` is money withdrawn OUT of it.

Definitions used by the chart (the reverse sign of the legacy ``net`` field, hence the label):
credits = contributions into investments, debits = withdrawals out of them,
net contributions = credits - debits.

Flow accounts are transaction account labels; they are tied to Monarch registry accounts
through the registry's ``app_account`` mapping (or an exact display-name match). A flow
account with no registry match cannot be toggled, so it stays included and is flagged
``mapped: false`` for the UI to surface.
"""

from typing import Any, Iterable


def _months_between(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def monthly_series(monthly: dict[str, dict[str, dict[str, float]]], accounts: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """One point per month, first to last with zero-filled gaps, summed over ``accounts`` (all if None)."""
    chosen = set(monthly) if accounts is None else set(accounts)
    months = sorted({m for a, ms in monthly.items() if a in chosen for m in ms})
    if not months:
        return []
    out = []
    for month in _months_between(months[0], months[-1]):
        credits = debits = 0.0
        for acct in chosen:
            cell = monthly.get(acct, {}).get(month)
            if cell:
                credits += cell.get("from_checking", 0.0)
                debits += cell.get("to_checking", 0.0)
        out.append({"month": month, "credits": round(credits, 2), "debits": round(debits, 2), "net": round(credits - debits, 2)})
    return out


def ytd_summary(series: list[dict[str, Any]], year: int) -> dict[str, Any]:
    """Credits, debits and total (net contributions) for ``year`` from a monthly series."""
    prefix = f"{year:04d}-"
    rows = [p for p in series if p["month"].startswith(prefix)]
    credits = round(sum(p["credits"] for p in rows), 2)
    debits = round(sum(p["debits"] for p in rows), 2)
    return {"year": year, "credits": credits, "debits": debits, "total": round(credits - debits, 2)}


def resolve_flow_accounts(flow_names: Iterable[str], registry: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tie each flow account to registry accounts and decide whether the Flows toggle includes it.

    Included when any matched registry account has Flows enabled; unmatched accounts stay included.
    """
    out = []
    for name in sorted(flow_names, key=str.casefold):
        folded = name.strip().casefold()
        matched = [a for a in registry if (a.get("app_account") or "").strip().casefold() == folded]
        if not matched:
            matched = [a for a in registry if a["display_name"].strip().casefold() == folded]
        out.append({
            "flow_account": name,
            "account_keys": [a["account_key"] for a in matched],
            "mapped": bool(matched),
            "enabled": any(a["enabled"].get("flows") for a in matched) if matched else True,
        })
    return out


def flows_payload(entry: dict[str, Any] | None, registry: list[dict[str, Any]], year: int | None = None) -> dict[str, Any]:
    """Everything the flows chart needs from the latest log entry and the registry toggles."""
    monthly = (entry or {}).get("investment_flows_monthly") or {}
    # Daily ledger (Trends Phase 4); older log entries lack it and the client falls back to monthly.
    daily = (entry or {}).get("investment_flows_daily")
    accounts = resolve_flow_accounts(set(monthly) | set(daily or {}), registry)
    included = [a["flow_account"] for a in accounts if a["enabled"]]
    series = monthly_series(monthly, included)
    if year is None:
        year = int(str((entry or {}).get("as_of_date") or "0000")[:4]) or None
    return {
        "as_of_date": (entry or {}).get("as_of_date"),
        "accounts": accounts,
        "monthly": monthly,
        "daily": daily,
        "series": series,
        "ytd": ytd_summary(series, year) if year else None,
    }
