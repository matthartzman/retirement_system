"""Pure helpers of the realized-sales ledger: holding period, sale-row validation, lot allocation.

No I/O. ``holding_period`` is the one place the ledger decides short vs long term (calendar rule: long only
when the sale is after the first anniversary of the purchase); do not use ``tlh._is_long_term``, which
compares calendar years and is for planning only. Column values and status names match ``stores.sales_repo``.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

# Mirrors of the ``stores.sales_repo`` column values (product code reaches ``stores`` only through
# ``active_plan``); ``tests/test_sales_ledger_unit.py`` pins them equal.
TAX_CLASSES = ("taxable", "pre_tax", "roth", "hsa")
SALE_SOURCES = ("holdings_diff", "monarch", "manual", "1099b", "broker")
SALE_STATUSES = ("confirmed", "voided")


class ValidationError(ValueError):
    """A ledger row or lot allocation that must not be saved."""


TAXABLE_CLASS = "taxable"
_SHARE_EPS = 1e-6


def _to_date(name: str, value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValidationError(f"{name} must be an ISO date (YYYY-MM-DD), got {value!r}")


def _anniversary(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # Feb 29 -> Feb 28 in a non-leap year
        return date(d.year + 1, 2, 28)


def holding_period(purchase: date | str | None, sale: date | str) -> str:
    """``'long'`` if the sale is strictly after the first anniversary of ``purchase``, ``'short'`` if not,
    ``'unknown'`` when the purchase date is missing."""
    sale_d = _to_date("sale", sale)
    if purchase is None or (isinstance(purchase, str) and not purchase.strip()):
        return "unknown"
    return "long" if sale_d > _anniversary(_to_date("purchase", purchase)) else "short"


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a number, got {value!r}")
    return float(value)


def _text(name: str, value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"a sale needs {name}")
    return text


def validate_sale_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Check one ledger row and return it with the derived fields filled in.

    ``holding_period`` and ``gain`` (proceeds - fees - basis; ``None`` for non-taxable ``tax_class``) are always
    recomputed, never trusted from the caller. A taxable sale with no purchase date is rejected (confirm is
    blocked until the date is supplied). Other fields pass through for ``SalesRepo.insert_sale``.
    """
    out = dict(row)
    sale_d = _to_date("sale_date", row.get("sale_date"))
    out["sale_date"] = sale_d.isoformat()
    out["account"] = _text("an account", row.get("account"))
    out["symbol"] = _text("a symbol", row.get("symbol")).upper()
    tax_class = row.get("tax_class")
    if tax_class not in TAX_CLASSES:
        raise ValidationError(f"tax_class must be one of {', '.join(TAX_CLASSES)}; got {tax_class!r}")
    source = row.get("source")
    if source not in SALE_SOURCES:
        raise ValidationError(f"source must be one of {', '.join(SALE_SOURCES)}; got {source!r}")
    status = row.get("status", "confirmed")
    if status not in SALE_STATUSES:
        raise ValidationError(f"status must be one of {', '.join(SALE_STATUSES)}; got {status!r}")
    out["status"] = status
    shares = _number("shares", row.get("shares"))
    if shares <= 0:
        raise ValidationError("shares must be > 0")
    proceeds = _number("proceeds", row.get("proceeds"))
    basis = _number("basis", row.get("basis"))
    fees = _number("fees", row.get("fees", 0.0))
    if fees < 0:
        raise ValidationError("fees must be >= 0")
    out.update(shares=shares, proceeds=proceeds, basis=basis, fees=fees)

    purchase = row.get("purchase_date")
    if purchase is not None and str(purchase).strip():
        purchase_d = _to_date("purchase_date", purchase)
        if purchase_d > sale_d:
            raise ValidationError("purchase_date is after sale_date")
        out["purchase_date"] = purchase_d.isoformat()
    else:
        out["purchase_date"] = None
    out["holding_period"] = holding_period(out["purchase_date"], sale_d)
    if tax_class == TAXABLE_CLASS:
        if out["holding_period"] == "unknown":
            raise ValidationError("purchase_date is required for a taxable sale (holding period unknown)")
        out["gain"] = proceeds - fees - basis
    else:
        out["gain"] = None
    return out


def allocate_lots(shares_sold: float, lots: Iterable[Mapping[str, Any]],
                  allocation: Mapping[str, float]) -> dict[str, float]:
    """Validate a user's per-lot split of a sale and return it without zero entries.

    ``lots`` are ``{'lot_key', 'remaining'}``; ``allocation`` maps ``lot_key`` to shares. No lot is ever chosen
    for the user: an empty allocation fails the total check. Each lot is capped at its remaining shares and the
    total must equal ``shares_sold`` (to within float dust).
    """
    target = _number("shares_sold", shares_sold)
    if target <= 0:
        raise ValidationError("shares sold must be > 0")
    remaining = {str(lot["lot_key"]): float(lot["remaining"]) for lot in lots}
    cleaned: dict[str, float] = {}
    for key, raw in allocation.items():
        qty = _number(f"shares for lot {key}", raw)
        if key not in remaining:
            raise ValidationError(f"unknown lot {key!r}")
        if qty < 0:
            raise ValidationError(f"shares for lot {key} must not be negative")
        if qty > remaining[key] + _SHARE_EPS:
            raise ValidationError(f"lot {key}: {qty:g} shares exceeds the {remaining[key]:g} remaining")
        if qty > _SHARE_EPS:
            cleaned[key] = qty
    total = sum(cleaned.values())
    if abs(total - target) > _SHARE_EPS:
        raise ValidationError(f"allocated total {total:g} must equal the {target:g} shares sold")
    return cleaned
