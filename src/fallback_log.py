"""One-line, log-once reporting for deliberate engine fallbacks (WI-029 / QA-007).

The calculation core tolerates bad optional inputs by falling back to a default.
A fallback that is silent hides a defect as a changed number, so each site calls
``log_fallback`` with a stable site name; the first occurrence per site and
exception type is logged at WARNING and later ones are dropped, so a
per-year loop cannot flood the log.
"""
from __future__ import annotations

import logging
import threading

_log = logging.getLogger("retirement_system.engine_fallback")
_seen: set[tuple[str, str]] = set()
_lock = threading.Lock()


def log_fallback(site: str, exc: BaseException, **context: object) -> None:
    key = (site, type(exc).__name__)
    with _lock:
        if key in _seen:
            return
        _seen.add(key)
    detail = ", ".join(f"{k}={v!r}" for k, v in context.items())
    _log.warning("engine fallback at %s: %s: %s%s", site, type(exc).__name__, exc,
                 f" ({detail})" if detail else "")


def reset_fallback_log() -> None:
    """Forget what has been logged (tests only)."""
    with _lock:
        _seen.clear()
