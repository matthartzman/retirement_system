from __future__ import annotations

"""Money-boundary helpers.

External/user-facing money is parsed as Decimal and stored as integer cents at
DB/domain boundaries.  The legacy numerical engine may still receive float
execution copies after validation, but boundary parsing no longer uses binary
floating point as the source of truth.
"""

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


def decimal_money(value: Any, default: Decimal = ZERO) -> Decimal:
    return decimal_from_user_value(value, default).quantize(CENT, rounding=ROUND_HALF_UP)


def execution_float(value: Any, default: float = 0.0) -> float:
    return float(decimal_from_user_value(value, Decimal(str(default))))
