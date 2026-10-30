"""Percent view: divide every money number by one constant and strip dollar-level detail.

Fail-closed: a number is scaled unless its key is on ``NON_MONEY_KEYS`` (or is a ratio
by suffix). A wrongly allowlisted money key leaks a dollar amount; a wrongly scaled
count is only cosmetic, so when unsure a key stays off the list.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import balance_series

NON_MONEY_KEYS: frozenset[str] = frozenset({
    "id",                # row / account ids
    "days",              # window length and holding periods
    "year",              # calendar year (flows.ytd_summary, full_year_budget)
    "year_fraction",     # fraction of a year elapsed
    "count",             # item counts
    "share",             # live_snapshot group share of the total (a 0-1 ratio)
    "share_of_gain",     # live_snapshot group share of total gain (a ratio)
    "delayed_minutes",   # live_snapshot quote delay, minutes
    "tax_year",          # realized view / realized tax line: the tax year, not an amount
    "years",             # realized view: the tax years offered
    "basis_missing",     # realized view: how many waiting or estimated rows have no basis (a count)
    "not_estimated",     # realized view: how many waiting sales could not be estimated (a count)
    "ages",              # projections: the owners' ages in a projection year
    "plan_first_year",   # projections: first year of the plan's projection
    "plan_last_year",    # projections: last year of the plan's projection
})

_RATIO_SUFFIXES = ("_rate", "_pct", "_ratio", "_fraction")
_RATIO_KEYS = frozenset({"pct", "rate", "weight"})
_DOLLAR_TEXT = re.compile(r"\$\s?-?\d")
_HIDDEN = "(amount hidden)"
_ALL_MERCHANTS = "All merchants"
# A share count times a public ticker price, or a public index level against its scaled value, gives back
# the hidden scale and with it every dollar figure. A percent-only person never receives these.
_PUBLIC_QUANTITY_KEYS = frozenset({"shares", "quantity", "purchase_price", "price"})
# The realized view's per-sale rows: dates, share counts and amounts per sale would give the scale back. A percent-only
# person gets group-level scaled totals and returns only (sales ledger plan 10).
_REALIZED_DETAIL_KEYS = frozenset({"lots"})


def is_non_money(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return key in NON_MONEY_KEYS or key in _RATIO_KEYS or key.endswith(_RATIO_SUFFIXES)


def scale_basis(balances_db: Path, history: list[dict], plan_values: dict[str, float] | None = None) -> float | None:
    """Today's net worth: the balance store's latest, else the last history entry's. None if missing or <= 0."""
    net_worth = None
    try:
        summary = balance_series.snapshot_summary(balances_db, plan_values)
    except Exception:  # an unreadable store is "missing", not an error page
        summary = None
    if summary:
        net_worth = summary.get("net_worth")
    elif history:
        net_worth = ((history[-1] or {}).get("net_worth") or {}).get("total")
    if isinstance(net_worth, bool) or not isinstance(net_worth, (int, float)) or net_worth <= 0:
        return None
    return float(net_worth)


def scale_payload(obj: Any, k: float, key: str | None = None) -> Any:
    """A new structure with every money number divided by ``k``; ``obj`` is never mutated."""
    if not k or k <= 0:
        raise ValueError("scale constant must be positive")
    if isinstance(obj, dict):
        return {name: scale_payload(value, k, name) for name, value in obj.items()}
    if isinstance(obj, list):
        return [scale_payload(item, k, key) for item in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        # unrounded: rounding to 6 places breaks sums once K is in the millions
        return obj if is_non_money(key) else obj / k
    if isinstance(obj, str) and _DOLLAR_TEXT.search(obj):
        return _HIDDEN
    return obj


def _collapse_merchants(tree: Any) -> Any:
    """``{type: {group: {category: {merchant: amount}}}}`` -> merchants become ``{"All merchants": sum}``."""
    if not isinstance(tree, dict):
        return tree
    return {tt: {grp: {cat: ({_ALL_MERCHANTS: round(sum(v for v in merchants.values() if isinstance(v, (int, float))), 2)}
                             if isinstance(merchants, dict) else merchants)
                       for cat, merchants in cats.items()}
                 for grp, cats in groups.items()}
            for tt, groups in tree.items()}


def _drop_prior_merchants(detail: Any) -> Any:
    """``{type: {group: {category: {prior, merchants}}}}`` -> same without ``merchants``."""
    if not isinstance(detail, dict):
        return detail
    return {tt: {grp: {cat: ({k: v for k, v in row.items() if k != "merchants"} if isinstance(row, dict) else row)
                       for cat, row in cats.items()}
                 for grp, cats in groups.items()}
            for tt, groups in detail.items()}


def _strip_spending(payload: dict) -> dict:
    out = dict(payload)
    if "hierarchy" in out:
        out["hierarchy"] = _collapse_merchants(out["hierarchy"])
    prior = out.get("prior")
    if isinstance(prior, dict) and "detail" in prior:
        out["prior"] = {**prior, "detail": _drop_prior_merchants(prior["detail"])}
    return out


def _strip_history_entry(entry: Any) -> Any:
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if "ytd_expense_hierarchy" in out:
        out["ytd_expense_hierarchy"] = _collapse_merchants(out["ytd_expense_hierarchy"])
    if "ytd_expense_prior_detail" in out:
        out["ytd_expense_prior_detail"] = _drop_prior_merchants(out["ytd_expense_prior_detail"])
    return out


def _drop_keys(node: Any, names: frozenset[str]) -> Any:
    if isinstance(node, dict):
        return {k: _drop_keys(v, names) for k, v in node.items() if k not in names}
    if isinstance(node, list):
        return [_drop_keys(v, names) for v in node]
    return node


def strip_detail(route: str, payload: Any) -> Any:
    """Remove the detail a percent-only person never sees (merchants, reconciliation). Returns a new structure."""
    if route == "/api/spending" and isinstance(payload, dict):
        return _strip_spending(payload)
    if route == "/api/live-snapshot" and isinstance(payload, dict):
        kept = {k: v for k, v in payload.items() if k not in ("reconciliation", "unmapped_monarch", "unmapped_holdings")}
        return _drop_keys(kept, _PUBLIC_QUANTITY_KEYS)
    if route == "/api/realized" and isinstance(payload, dict):
        return _drop_keys(payload, _REALIZED_DETAIL_KEYS | _PUBLIC_QUANTITY_KEYS)
    if route == "/api/history":
        if isinstance(payload, list):
            return [_strip_history_entry(e) for e in payload]
        if isinstance(payload, dict):
            return {k: ([_strip_history_entry(e) for e in v] if isinstance(v, list) else v) for k, v in payload.items()}
    return payload


def find_money_leaks(obj: Any, threshold: float = 50.0) -> list[str]:
    """Paths of numbers outside the allowlist with ``abs(v) > threshold``, and of ``$`` strings."""
    leaks: list[str] = []

    def walk(node: Any, path: str, key: str | None) -> None:
        if isinstance(node, dict):
            for name, value in node.items():
                walk(value, f"{path}.{name}" if path else str(name), name)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]", key)
        elif isinstance(node, bool):
            return
        elif isinstance(node, (int, float)):
            if not is_non_money(key) and abs(node) > threshold:
                leaks.append(path)
        elif isinstance(node, str) and _DOLLAR_TEXT.search(node):
            leaks.append(path)

    walk(obj, "", None)
    return leaks
