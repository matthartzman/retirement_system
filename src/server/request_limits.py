"""Per-route input limits (PR-11, PR-13, PR-14), kept out of ``plan_routes.py`` so the route edits stay one-liners.

* Upload caps below the global 64 MiB body cap, per kind of upload, and a page limit for a PDF statement.
* ``finite_float``: ``float()`` accepts ``nan`` and ``inf``; money and share counts must be finite.
* Forced local backups: a bounded ``trigger`` label and a minimum gap between forced runs (a forced run skips the
  plan-quota/interval checks, so unthrottled it is a disk-fill tool for any member).
"""
from __future__ import annotations

import math
import re
import threading
import time

MAX_PLAN_UPLOAD_B64 = 40 * 1024 * 1024       # a plan file is a few MB; 40 MiB of base64 is about 30 MiB of file
MAX_PDF_B64 = 12 * 1024 * 1024               # a broker PDF statement
MAX_STATEMENT_TEXT = 4 * 1024 * 1024         # pasted 1099-B / broker text
MAX_PDF_PAGES = 150
MIN_FORCED_BACKUP_SECONDS = 300.0
MAX_TRIGGER_CHARS = 32

_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")


def finite_float(value) -> float:
    """``float(value)``, refusing NaN and infinity. Raises ValueError (callers already map it to a 400)."""
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("number must be finite")
    return number


def too_large(value, limit: int) -> bool:
    """True when a JSON string field exceeds ``limit`` characters (checked before it is decoded)."""
    return isinstance(value, str) and len(value) > limit


def pdf_page_count(data: bytes) -> int:
    """Pages counted from the page objects, without parsing the PDF. An over-count only refuses a big file earlier."""
    return len(_PAGE.findall(data))


def pdf_problem(data: bytes) -> tuple[int, str] | None:
    """(HTTP status, message) when the bytes should not reach the PDF parser, else None."""
    if not data.lstrip()[:5] == b"%PDF-":
        return 400, "pdf_base64 is not a PDF file"
    if pdf_page_count(data) > MAX_PDF_PAGES:
        return 413, f"the PDF has more than {MAX_PDF_PAGES} pages; split it and import the parts"
    return None


def clean_trigger(value, default: str = "manual") -> str:
    """A short label of letters, digits, ``_``, ``-`` and ``.`` (it is written to the audit log and the status file)."""
    text = re.sub(r"[^A-Za-z0-9_.-]", "", str(value or ""))[:MAX_TRIGGER_CHARS]
    return text or default


class ForcedRunLimiter:
    """Allow a forced run at most once per ``min_seconds``; ``retry_after`` is the wait left (0 when allowed)."""

    def __init__(self, min_seconds: float = MIN_FORCED_BACKUP_SECONDS, clock=time.monotonic) -> None:
        self._min, self._clock, self._last, self._lock = float(min_seconds), clock, None, threading.Lock()

    def acquire(self) -> float:
        with self._lock:
            now = self._clock()
            if self._last is not None and now - self._last < self._min:
                return self._min - (now - self._last)
            self._last = now
            return 0.0
