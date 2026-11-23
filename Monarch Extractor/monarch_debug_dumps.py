"""Failure dumps of authenticated Monarch pages (F-11): off by default, redacted when on, deleted after 7 days.

A full-page HTML copy and screenshot of a signed-in Monarch page show every balance and account on screen. They used
to be written on every failure and never removed. Now:
  * nothing is written unless ``--debug-dumps`` (or ``MONARCH_DEBUG_DUMPS=1``) is given;
  * the HTML is run through :func:`redact_html` first (amounts, long digit runs and masked account numbers);
  * a screenshot cannot be redacted, so it needs the extra ``--debug-screenshot`` and is announced as sensitive;
  * every run starts by deleting dumps older than :data:`MAX_AGE_DAYS`.
Standard library only (the extractor runs in its own virtualenv).
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Mapping

MAX_AGE_DAYS = 7
ENV_FLAG = "MONARCH_DEBUG_DUMPS"
DUMP_GLOBS = ("monarch-debug-*.html", "monarch-debug-*.png")
REDACTED = "[redacted]"

_AMOUNT = re.compile(r"[-−(]?\s?[$£€]\s?\d[\d,]*(?:\.\d+)?\)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")
_MASKED_ACCOUNT = re.compile(r"(?:[*•·x]{2,}|\.{3})\s?\d{2,}", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\b\d{6,}\b")
_ATTR_VALUE = re.compile(r'(value|data-balance|data-amount|aria-label)="([^"]*\d[^"]*)"', re.IGNORECASE)


def dumps_enabled(flag: bool = False, env: Mapping[str, str] | None = None) -> bool:
    """True only when explicitly asked for (flag or environment variable)."""
    env = os.environ if env is None else env
    return bool(flag) or str(env.get(ENV_FLAG, "")).strip().lower() in {"1", "true", "yes", "on"}


def redact_html(html: str) -> str:
    """Remove obvious money amounts, account numbers and numeric attribute values from saved HTML. Best effort: it is
    why the dump is also short-lived and opt-in, not a guarantee that nothing sensitive remains."""
    out = _ATTR_VALUE.sub(lambda m: f'{m.group(1)}="{REDACTED}"', html)
    out = _MASKED_ACCOUNT.sub(REDACTED, out)
    out = _AMOUNT.sub(REDACTED, out)
    return _LONG_DIGITS.sub(REDACTED, out)


def purge_old_dumps(output_dir: Path | str, *, now: float | None = None, max_age_days: float = MAX_AGE_DAYS) -> list[Path]:
    """Delete failure dumps older than ``max_age_days``; returns what was removed. Never touches other files."""
    now = time.time() if now is None else now
    removed: list[Path] = []
    folder = Path(output_dir)
    if not folder.is_dir():
        return removed
    for pattern in DUMP_GLOBS:
        for path in folder.glob(pattern):
            try:
                if path.is_file() and now - path.stat().st_mtime > max_age_days * 86400:
                    path.unlink()
                    removed.append(path)
            except OSError:
                continue
    return removed
