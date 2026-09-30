"""One shared parser for plan-data dates (DOB, retirement dates, etc.).

System review 2026-09-25-2, QA-001 / WI-401: household dates used to go
through three different two-digit-year rules -- ``data_io._y`` returned the
raw 2-digit number (so a DOB of '8/3/62' became birth year 62 and the member
was modeled as dead in every plan year), ``data_io._date_parts`` added 2000,
and the UI/server grid-save normalizers pivoted at 40. This module is the one
rule every server-side reader now shares:

* A two-digit year ``yy`` is ``19yy`` when ``yy > TWO_DIGIT_YEAR_PIVOT``,
  otherwise ``20yy`` -- the same pivot ``frontend/js/dashboard_decomp_row_model.js``
  (``toIsoDateValue``) and ``src/server/app_core._normalize_date_for_csv``
  already apply on grid saves, so a value the UI would have stored as 1962
  is read as 1962 here too.
* A bare ``YYYY`` is returned as ``(YYYY, 12, 31)`` by :func:`parse_plan_date`
  (``bare_year_as``="end"), which is the engine's long-standing reading of a
  year-only retirement date (earned income continues through that year). This
  module does not change that meaning; it only makes it explicit.

Callers that need a date to be unambiguous (a date of birth) use
:func:`has_two_digit_year` to reject a 2-digit year outright instead of
guessing a century.
"""
from __future__ import annotations

import datetime as _dt
import math
import re

TWO_DIGIT_YEAR_PIVOT = 40

# M/D/YY or M/D/YYYY (also accepts '-' separators in that order).
_MDY_RE = re.compile(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{2}|\d{4})$')
# YYYY-MM-DD or YYYY/MM/DD, optionally followed by a time part.
_YMD_RE = re.compile(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:[T ].*)?$')
# MM/YYYY, M/YY, YYYY-MM (month precision: Social Security claim dates).
_MY_RE = re.compile(r'^(\d{1,2})/(\d{2}|\d{4})$')
_YM_RE = re.compile(r'^(\d{4})-(\d{1,2})$')
_YEAR_RE = re.compile(r'^(\d{4})(?:\.0+)?$')


def expand_two_digit_year(year: int) -> int:
    """Apply the single century-pivot rule to a 0..99 year; pass others through."""
    year = int(year)
    if 0 <= year < 100:
        return (1900 if year > TWO_DIGIT_YEAR_PIVOT else 2000) + year
    return year


def _valid(y: int, m: int, d: int) -> bool:
    try:
        _dt.date(y, m, d)
        return True
    except (ValueError, OverflowError):
        return False


def parse_plan_date(value, *, bare_year_as: str = 'end'):
    """Return ``(year, month, day)`` for a plan-data date string, else None.

    Accepts M/D/YYYY, M/D/YY (century pivot), YYYY-MM-DD[Thh:mm...], and a
    bare YYYY (``bare_year_as`` 'end' -> Dec 31, 'start' -> Jan 1). Returns
    None for blank or unparseable input, and for calendar-impossible dates
    such as 2/30/2027.
    """
    s = str(value if value is not None else '').strip()
    if not s:
        return None
    m = _MDY_RE.match(s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), expand_two_digit_year(int(m.group(3)))
        return (y, mo, d) if _valid(y, mo, d) else None
    m = _YMD_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return (y, mo, d) if _valid(y, mo, d) else None
    m = _YEAR_RE.match(s)
    if m:
        y = int(m.group(1))
        return (y, 1, 1) if bare_year_as == 'start' else (y, 12, 31)
    return None


def parse_plan_month(value):
    """Return ``(year, month)`` for a month-precision date (MM/YYYY, YYYY-MM)."""
    s = str(value if value is not None else '').strip()
    m = _MY_RE.match(s)
    if m:
        mo, y = int(m.group(1)), expand_two_digit_year(int(m.group(2)))
    else:
        m = _YM_RE.match(s)
        if not m:
            return None
        y, mo = int(m.group(1)), int(m.group(2))
    return (y, mo) if 1 <= mo <= 12 else None


def has_two_digit_year(value) -> bool:
    """True when ``value`` is a slash/dash date whose year has only two digits."""
    s = str(value if value is not None else '').strip()
    m = _MDY_RE.match(s)
    if m:
        return len(m.group(3)) == 2
    m = _MY_RE.match(s)
    return bool(m and len(m.group(2)) == 2)


def date_format_error(value) -> str | None:
    """Validation message for a plan-data date value, or None when it is fine.

    Blank is not an error here (required-ness is checked separately). Used by
    ``schema_registry.validate_value``'s 'date' branch.
    """
    s = str(value if value is not None else '').strip()
    if not s:
        return None
    try:
        if not math.isfinite(float(s)):
            return 'expected a date, got a non-finite number'
    except ValueError:
        pass
    if has_two_digit_year(s):
        return 'ambiguous 2-digit year; enter a 4-digit year (M/D/YYYY)'
    if parse_plan_date(s) is not None or parse_plan_month(s) is not None:
        return None
    return 'expected a date (M/D/YYYY, YYYY-MM-DD, MM/YYYY or YYYY)'
