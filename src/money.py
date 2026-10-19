from __future__ import annotations

"""Money-boundary helpers.

External/user-facing money is parsed as Decimal and stored as integer cents at
DB/domain boundaries.  The legacy numerical engine may still receive float
execution copies after validation, but boundary parsing no longer uses binary
floating point as the source of truth.
"""

import math
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_from_user_value(value: Any, default: Decimal = ZERO) -> Decimal:
    if value is None or value == "":
        return default
    text = str(value).strip()
    pct = text.endswith("%")
    text = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if not text:
        return default
    try:
        out = Decimal(text)
    except (InvalidOperation, ValueError):
        return default
    return out / Decimal("100") if pct else out


def cents_from_user_value(value: Any, default_cents: int = 0) -> int:
    d = decimal_from_user_value(value, Decimal(default_cents) / Decimal("100"))
    return int((d * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))




_MISSING: Any = object()
_CURRENCY_SYMBOLS = "$€£¥"


def parse_strict_number(value: Any, default: Any = _MISSING, *, percent_as_fraction: bool = True) -> Decimal:
    """The one strict number grammar for imported/user cells.

    Accepts optional surrounding whitespace, currency symbols (``$ € £ ¥``), thousands commas,
    a leading ``+``/``-`` or an accounting wrapper ``(5,000)`` (negative), and a trailing ``%``
    (divided by 100 unless ``percent_as_fraction`` is False).  Always finite: ``nan``, ``inf``,
    ``1e999`` and garbage raise ``ValueError``.  A blank/None cell returns ``default`` when one
    is given, else raises ``ValueError``.
    """
    if isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is _MISSING:
            raise ValueError("blank number")
        return default if isinstance(default, Decimal) or default is None else Decimal(str(default))
    text = str(value).strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    pct = text.endswith("%")
    if pct:
        text = text[:-1].strip()
    for sym in _CURRENCY_SYMBOLS:
        text = text.replace(sym, "")
    text = text.replace(",", "").replace(" ", "")
    if not text or text[0] not in "+-.0123456789" or "_" in text:
        raise ValueError(f"not a number: {value!r}")
    try:
        out = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"not a number: {value!r}") from None
    if not out.is_finite() or not math.isfinite(float(out)):  # also rejects 1e999 (overflows a float)
        raise ValueError(f"not a finite number: {value!r}")
    if negative:
        out = -out
    if pct and percent_as_fraction:
        out = out / Decimal("100")
    return out


def is_strict_number(value: Any) -> bool:
    """True when ``parse_strict_number`` accepts ``value`` (blank counts as not a number)."""
    try:
        parse_strict_number(value)
    except ValueError:
        return False
    return True


def strict_float(value: Any, default: Any = _MISSING, *, percent_as_fraction: bool = True) -> float:
    """``parse_strict_number`` as a float execution copy (raises ValueError like it)."""
    out = parse_strict_number(value, default, percent_as_fraction=percent_as_fraction)
    return out if out is None else float(out)
