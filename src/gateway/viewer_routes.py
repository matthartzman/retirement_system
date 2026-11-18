"""The guest route table (Phase 9, ``multi-user-shared-view-design.md`` section 5.6): deny by default.

A viewer session is answered only by the gateway and never reaches a worker. The gate in ``app.py`` lets a viewer's
request through only when its ``(method, rule)`` pair, matched after routing on the registered rule string, is in
:data:`VIEWER_ALLOWED`. Everything else gets :data:`NOT_AVAILABLE_BODY` (404) for an API path or a redirect to
:data:`VIEWER_HOME` for a page.

This table is a reviewed literal. It is written out in full and derived from nothing else: not from the planner's
allow-list (``src/server/remote_allowlist.py``), not from Financial Insight's worker allow-list and not from the
gateway's other route sets. ``tests/test_gateway_viewer_gate_contract.py`` holds a second copy and fails when the two
differ, so a change here is a reviewed change.
"""
from __future__ import annotations

import json

VIEWER_ALLOWED: frozenset[tuple[str, str]] = frozenset({
    # Sign-in, second factor, password and the account page: the same routes every account uses.
    ("GET", "/login"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/session"),
    ("POST", "/api/auth/totp/enrol/start"),
    ("POST", "/api/auth/totp/enrol/confirm"),
    ("POST", "/api/auth/totp/verify"),
    ("GET", "/gateway/enrol"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/password"),
    ("GET", "/gateway/account"),
    ("GET", "/gateway/static/<name>"),
    # The guest page, its exact static files, and the three record routes.
    ("GET", "/gateway/viewer"),
    ("GET", "/gateway/viewer/static/<name>"),
    ("GET", "/api/viewer/shares"),
    ("GET", "/api/viewer/shares/<share_id>"),
    ("GET", "/api/viewer/shares/<share_id>/status"),
})

# Where a viewer's browser is sent for any page outside the table (including "/").
VIEWER_HOME = "/gateway/viewer"
# One body for every refusal and every share a viewer may not see: unknown, malformed, revoked, expired or someone
# else's (C6). The viewer page shows its own plain message for it.
NOT_AVAILABLE_BODY = json.dumps({"success": False, "available": False, "error": "Not available."})
# The one viewer route that may be sent as a background poll (it must not keep the session alive, C27).
STATUS_RULE = "/api/viewer/shares/<share_id>/status"


def viewer_may(method: str, rule: str | None) -> bool:
    """True when a viewer may make this request; ``rule`` is the matched route's rule string (None: no route)."""
    if rule is None:
        return False
    return ("GET" if method == "HEAD" else method, rule) in VIEWER_ALLOWED
