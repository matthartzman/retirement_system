"""One place for the operator's "CSV writes disabled" switch (PR-07).

``RuntimeConfig.allow_csv_write`` was checked by hand inside some routes and forgotten in others: the sales,
transactions, cash, reconcile, YTD, spending, housing/wellness seed and plan-registry routes wrote the plan with the
switch off. Rather than add a guard to each of ~75 handlers (every one a chance to forget the next), this module
classifies a request by method and path and a single ``before_request`` hook (:func:`install`) answers 403 before any
handler runs. Routes that already check it keep doing so; the message is the same.

A write is a POST, PUT, PATCH or DELETE under one of :data:`GATED_PREFIXES`, except the previews and validations in
:data:`READ_ONLY_POSTS`, which only read. Reads (GET) are never gated. :func:`csv_write_gate` is the same check as a
decorator for a single route added later.
"""
from __future__ import annotations

import functools
from typing import Callable

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

GATED_PREFIXES: tuple[str, ...] = (
    "/api/sales",
    "/api/transactions",
    "/api/cash",             # /api/cash/* and /api/cash-accounts*
    "/api/year-end",
    "/api/reconcile",
    "/api/ytd",
    "/api/spending",
    "/api/housing/seed",
    "/api/wellness/seed",
    "/api/plans",            # the plan registry: switch, rename, create, duplicate, delete, forget
    "/api/investment-income/symbol-type",
)

# POST endpoints inside those prefixes that only compute and return a result.
READ_ONLY_POSTS: frozenset[str] = frozenset({
    "/api/ytd/transactions/preview",
    "/api/sales/1099b/preview",
    "/api/sales/broker/preview",
    "/api/sales/candidates/bulk/review",
    "/api/sales/candidates/bulk/validate",
    "/api/reconcile/preview",
})

MESSAGE = "CSV writes are disabled"


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/") or (prefix == "/api/cash" and path.startswith("/api/cash-"))


def is_csv_write_request(method: str, path: str) -> bool:
    """True when this request changes plan data through a route the switch must cover."""
    if method.upper() not in WRITE_METHODS:
        return False
    clean = path.rstrip("/") or "/"
    if clean in READ_ONLY_POSTS:
        return False
    return any(_under(clean, p) for p in GATED_PREFIXES)


def writes_allowed(get_config: Callable[[], object]) -> bool:
    """The switch, read fresh on every request. An unreadable config fails closed (writes refused)."""
    try:
        return bool(getattr(get_config(), "allow_csv_write", False))
    except Exception:  # noqa: BLE001
        return False


def install(app, get_config: Callable[[], object]) -> None:
    """Register the gate on ``app``. Call once, after the security gate so permission checks keep their order."""
    from src.http_runtime.wsgi_facade import jsonify, request  # noqa: PLC0415

    @app.before_request
    def _csv_write_gate():
        if is_csv_write_request(request.method, request.path) and not writes_allowed(get_config):
            return jsonify({"success": False, "error": MESSAGE}), 403
        return None


def csv_write_gate(get_config: Callable[[], object]):
    """Decorator for one route: refuse with the standard 403 while the switch is off."""
    def decorate(view):
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            from src.http_runtime.wsgi_facade import jsonify  # noqa: PLC0415

            if not writes_allowed(get_config):
                return jsonify({"success": False, "error": MESSAGE}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorate
