"""Response security headers shared by the planner server, the Financial Insights listeners and the gateway proxy (SEC-07 / F-10 / S-02).

Two content-security policies:

* ``PLANNER_CSP``: the planner page is built with inline ``onclick=`` handlers and inline styles, so scripts need
  ``'unsafe-inline'``; everything else is pinned to the same origin, with no framing, no ``<base>``, no plugins.
* ``csp_for_html``: pages that carry only inline ``<script>`` blocks (Financial Insights) get exactly those blocks'
  SHA-256 hashes instead of ``'unsafe-inline'``, so an injected script does not run.

``apply`` uses ``setdefault`` semantics, so a policy a downstream service already set is never overridden.
"""
from __future__ import annotations

import base64
import hashlib
import re

_COMMON = "frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"
_FETCH = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'"

PLANNER_CSP = f"{_FETCH}; script-src 'self' 'unsafe-inline'; {_COMMON}"
BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>", re.I | re.S)


def inline_script_hashes(html: str) -> list[str]:
    """CSP source tokens for every inline ``<script>`` body in ``html``."""
    out = []
    for body in _INLINE_SCRIPT.findall(html):
        if body.strip():
            out.append("'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii") + "'")
    return out


def csp_for_html(html: str) -> str:
    """Narrow policy for a page with only inline script blocks: same-origin files plus those blocks by hash."""
    scripts = " ".join(["'self'", *inline_script_hashes(html)])
    return f"{_FETCH}; script-src {scripts}; {_COMMON}"


def apply(headers, csp: str, *, no_store: bool = False) -> None:
    """Add the headers to ``headers`` (a mapping) without overriding any already set."""
    for key, value in BASE_HEADERS.items():
        headers.setdefault(key, value)
    headers.setdefault("Content-Security-Policy", csp)
    if no_store:
        headers.setdefault("Cache-Control", "no-store")
