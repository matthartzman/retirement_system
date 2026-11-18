"""Worker mode's deny-by-default route allow-list (multi-user Financial Insight).

In worker mode (Financial Insight served by a user's own planner worker) a request is served only when its
``(method, rule)`` pair is in :data:`ALLOWED`; every other registered route answers 403, and an unknown path 404.
:data:`REFUSED` names each registered route that is not allowed, with the reason, so the contract test can check
that every route the app registers is classified exactly once. A new route is therefore refused for remote users
until someone adds it to one of the two tables.

``rule`` is the decorator's rule string exactly (``/api/spending/transactions``), as in
``src/server/remote_allowlist.py``.
"""
from __future__ import annotations

_PEOPLE = "people and sign-in belong to the gateway in worker mode"
_PROCESS = "stops the process; the worker's lifetime belongs to the gateway"

ALLOWED: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/"),
    ("GET", "/charts.js"),
    ("GET", "/live_snapshot.js"),
    ("GET", "/projections.js"),
    ("GET", "/projection_groups.js"),
    ("GET", "/live_groups.js"),
    ("GET", "/realized.js"),
    ("GET", "/spending_dock.js"),
    ("GET", "/money_view.js"),
    ("GET", "/insights_client.js"),
    ("GET", "/shared/runtime_history.js"),
    ("GET", "/api/history"),
    ("GET", "/api/accounts"),
    ("GET", "/api/balances"),
    ("GET", "/api/flows"),
    ("GET", "/api/liquid-change"),
    ("GET", "/api/spending"),
    ("GET", "/api/spending/transactions"),
    ("GET", "/api/live-snapshot"),
    ("GET", "/api/projections"),
    ("GET", "/api/realized"),
    ("GET", "/api/app-accounts"),
    ("GET", "/api/run-status"),
    ("GET", "/api/whoami"),
    # Display preferences and the update job: Financial Insight's own per-plan store, never the plan.
    ("POST", "/api/account"),
    ("POST", "/api/account-prefs"),
    ("POST", "/api/passthrough-decision"),
    ("POST", "/api/run-now"),
    ("POST", "/api/run-cancel"),
    ("POST", "/api/ping"),
    ("POST", "/api/view"),
})

REFUSED: dict[tuple[str, str], str] = {
    ("POST", "/api/exit"): _PROCESS,
}


def route_allowed(method: str, rule: str) -> bool:
    method = method.upper()
    return ((method, rule) in ALLOWED) or (method == "HEAD" and ("GET", rule) in ALLOWED)
