"""rental_properties.py — the Rental Properties parse boundary (WP12.3).

Design ``docs/superpowers/specs/2026-10-05-rental-property-module-design.md``
sections 3 and 8: one function turns source rows into ``c['rental_properties']``,
the only rental input the engine reads (``src/projection_stages/rental_property.py``
documents every key and its engine-side default).

Source-agnostic: the rows are plain dicts (one per property; ``improvements`` and
``overrides`` nested), whatever produced them: the typed plan tables of the storage
work, an import, a test fixture. Nothing here reads a file or a database.

Validation raises :class:`RentalPropertyInputError` naming the property and the
field. Blank values (``None`` or ``""``) count as missing; unknown keys are ignored.
Defaults filled here: kind ``standalone``, land share 20%, vacancy 0, active
participation yes, and month 7 (mid-year) for a purchase, sale, conversion or
improvement without a month (owner decision 2026-10-13). Defaults that depend on
the rest of the plan (growth rates, selling costs, the home's value and basis) are
left to the engine.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

STANDALONE = "standalone"
CONVERTED_HOME = "converted_home"
DEFAULT_LAND_SHARE = 0.20
DEFAULT_MONTH = 7
MAX_PROPERTIES = 20  # design section 3: the practical UI limit

_KINDS = {"standalone": STANDALONE, "converted_home": CONVERTED_HOME, "converted": CONVERTED_HOME}
_MONEY = ("purchase_price", "closing_costs", "current_value", "monthly_rent", "property_tax", "insurance",
          "hoa", "utilities", "other_expenses", "loan_balance", "loan_monthly_payment",
          "prior_suspended_loss", "sale_price", "value_at_conversion", "adjusted_basis_at_conversion")
_SHARES = ("land_share", "vacancy_rate", "maintenance_pct", "management_pct", "selling_cost_pct")
_GROWTH = ("appreciation", "rent_growth", "expense_growth", "property_tax_growth")
_YEARS = ("purchase_year", "value_as_of_year", "rental_start_year", "rental_end_year", "loan_balance_year",
          "placed_in_service_year", "sale_year", "conversion_year")
_MONTHS = ("purchase_month", "placed_in_service_month", "sale_month", "conversion_month")
# A converted home is the plan's own home: these come from the home (value, mortgage,
# sale year and price, selling costs), so setting them on the property is an error.
_NOT_FOR_CONVERTED = ("purchase_price", "closing_costs", "current_value", "value_as_of_year", "appreciation",
                      "loan_balance", "loan_balance_year", "loan_rate", "loan_monthly_payment", "loan_term_years",
                      "sale_year", "sale_price", "selling_cost_pct", "placed_in_service_year",
                      "placed_in_service_month", "rental_start_year")


class RentalPropertyInputError(ValueError):
    """A rental property row the engine cannot use; the message names the property and field."""


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _number(v: Any, where: str, field: str) -> float:
    if isinstance(v, bool):
        raise RentalPropertyInputError(f"{where}: {field} must be a number, got {v!r}")
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).strip().replace(",", "").replace("$", "")
    pct = text.endswith("%")
    try:
        x = float(text.rstrip("%").strip())
    except ValueError:
        raise RentalPropertyInputError(f"{where}: {field} must be a number, got {v!r}") from None
    return x / 100.0 if pct else x


def _int(v: Any, where: str, field: str, lo: int, hi: int) -> int:
    x = _number(v, where, field)
    if x != int(x) or not lo <= x <= hi:
        raise RentalPropertyInputError(f"{where}: {field} must be a whole number from {lo} to {hi}, got {v!r}")
    return int(x)


def _bool(v: Any, where: str, field: str) -> bool:
    if isinstance(v, bool):
        return v
    text = str(v).strip().lower()
    if text in ("true", "yes", "y", "1", "1.0"):
        return True
    if text in ("false", "no", "n", "0", "0.0"):
        return False
    raise RentalPropertyInputError(f"{where}: {field} must be yes or no, got {v!r}")


def _improvements(rows: Any, where: str) -> list[dict[str, Any]]:
    if _blank(rows):
        return []
    if not isinstance(rows, (list, tuple)):
        raise RentalPropertyInputError(f"{where}: improvements must be a list of rows")
    out = []
    for j, imp in enumerate(rows):
        at = f"{where}, improvement {j + 1}"
        if not isinstance(imp, Mapping):
            raise RentalPropertyInputError(f"{at}: must be a row with year and amount")
        if _blank(imp.get("year")) or _blank(imp.get("amount")):
            raise RentalPropertyInputError(f"{at}: year and amount are required")
        amount = _number(imp["amount"], at, "amount")
        if amount <= 0:
            raise RentalPropertyInputError(f"{at}: amount must be more than 0, got {imp['amount']!r}")
        month = DEFAULT_MONTH if _blank(imp.get("month")) else _int(imp["month"], at, "month", 1, 12)
        out.append({"year": _int(imp["year"], at, "year", 1900, 2200), "amount": amount, "month": month})
    return out


def _overrides(raw: Any, where: str) -> dict[int, dict[str, float]]:
    """``{year: {gross_rent, operating_expenses}}``, from that mapping or from rows with a ``year``."""
    if _blank(raw):
        return {}
    if isinstance(raw, Mapping):
        items = [(y, ov) for y, ov in raw.items()]
    elif isinstance(raw, (list, tuple)):
        items = []
        for j, ov in enumerate(raw):
            if not isinstance(ov, Mapping) or _blank(ov.get("year")):
                raise RentalPropertyInputError(f"{where}, override {j + 1}: must be a row with a year")
            items.append((ov["year"], ov))
    else:
        raise RentalPropertyInputError(f"{where}: overrides must be rows by year")
    out: dict[int, dict[str, float]] = {}
    for y, ov in items:
        year = _int(y, where, "override year", 1900, 2200)
        if not isinstance(ov, Mapping):
            raise RentalPropertyInputError(f"{where}, override {year}: must be a row")
        vals = {}
        for k in ("gross_rent", "operating_expenses"):
            if not _blank(ov.get(k)):
                vals[k] = _number(ov[k], f"{where}, override {year}", k)
                if vals[k] < 0:
                    raise RentalPropertyInputError(f"{where}, override {year}: {k} must not be negative")
        if year in out:
            raise RentalPropertyInputError(f"{where}: two overrides for {year}")
        if vals:
            out[year] = vals
    return out


def _parse_one(raw: Any, index: int, home_value: float | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise RentalPropertyInputError(f"Rental property {index + 1}: must be a row of fields, got {type(raw).__name__}")
    name = "" if _blank(raw.get("name")) else str(raw["name"]).strip()
    name = name or f"Rental {index + 1}"
    where = f"Rental property {index + 1} ({name!r})"
    kind_raw = "standalone" if _blank(raw.get("kind")) else str(raw["kind"]).strip().lower().replace(" ", "_")
    if kind_raw not in _KINDS:
        raise RentalPropertyInputError(f"{where}: kind must be 'Standalone' or 'Converted home', got {raw['kind']!r}")
    kind = _KINDS[kind_raw]
    out: dict[str, Any] = {"name": name, "kind": kind}
    if not _blank(raw.get("loan_liability_id")):
        out["loan_liability_id"] = str(raw["loan_liability_id"]).strip()
    for k in _MONEY:
        if not _blank(raw.get(k)):
            out[k] = _number(raw[k], where, k)
            if out[k] < 0:
                raise RentalPropertyInputError(f"{where}: {k} must not be negative, got {raw[k]!r}")
    for k in _SHARES:
        if not _blank(raw.get(k)):
            out[k] = _number(raw[k], where, k)
            if not 0.0 <= out[k] <= 1.0:
                raise RentalPropertyInputError(f"{where}: {k} must be between 0 and 1 (0% and 100%), got {raw[k]!r}")
    for k in _GROWTH:
        if not _blank(raw.get(k)):
            out[k] = _number(raw[k], where, k)
            if not -0.5 <= out[k] <= 0.5:
                raise RentalPropertyInputError(f"{where}: {k} must be an annual rate between -50% and 50%, got {raw[k]!r}")
    if not _blank(raw.get("loan_rate")):
        out["loan_rate"] = _number(raw["loan_rate"], where, "loan_rate")
        if not 0.0 <= out["loan_rate"] <= 0.5:
            raise RentalPropertyInputError(f"{where}: loan_rate must be between 0% and 50%, got {raw['loan_rate']!r}")
    for k in _YEARS:
        if not _blank(raw.get(k)):
            out[k] = _int(raw[k], where, k, 1900, 2200)
    for k in _MONTHS:
        if not _blank(raw.get(k)):
            out[k] = _int(raw[k], where, k, 1, 12)
    if not _blank(raw.get("loan_term_years")):
        out["loan_term_years"] = _int(raw["loan_term_years"], where, "loan_term_years", 1, 50)
    out["active_participation"] = (True if _blank(raw.get("active_participation"))
                                   else _bool(raw["active_participation"], where, "active_participation"))
    out["improvements"] = _improvements(raw.get("improvements"), where)
    out["overrides"] = _overrides(raw.get("overrides"), where)
    out.setdefault("land_share", DEFAULT_LAND_SHARE)
    out.setdefault("vacancy_rate", 0.0)
    out.setdefault("sale_month", DEFAULT_MONTH)

    if kind == CONVERTED_HOME:
        wrong = [k for k in _NOT_FOR_CONVERTED if k in out]
        if wrong:
            raise RentalPropertyInputError(
                f"{where}: a converted home takes {', '.join(wrong)} from the plan's home; remove "
                f"{'it' if len(wrong) == 1 else 'them'} from the property")
        if "conversion_year" not in out:
            raise RentalPropertyInputError(f"{where}: conversion_year is required for a converted home")
        if home_value is not None and home_value <= 0:
            raise RentalPropertyInputError(f"{where}: the plan has no home to convert (home value is 0)")
        out.setdefault("conversion_month", DEFAULT_MONTH)
        if "purchase_year" in out:
            out.setdefault("purchase_month", DEFAULT_MONTH)
            if (out["purchase_year"], out["purchase_month"]) > (out["conversion_year"], out["conversion_month"]):
                raise RentalPropertyInputError(f"{where}: purchase_year is after the conversion")
        if out.get("rental_end_year") is not None and out["rental_end_year"] < out["conversion_year"]:
            raise RentalPropertyInputError(f"{where}: rental_end_year is before conversion_year")
        return out

    if "conversion_year" in out or "conversion_month" in out:
        raise RentalPropertyInputError(f"{where}: conversion_year applies only to kind 'Converted home'")
    if out.get("purchase_price", 0.0) <= 0:
        raise RentalPropertyInputError(f"{where}: purchase_price is required and must be more than 0")
    out.setdefault("purchase_month", DEFAULT_MONTH)
    start = out.get("rental_start_year", out.get("purchase_year"))
    if start is not None and out.get("purchase_year") is not None and start < out["purchase_year"]:
        raise RentalPropertyInputError(f"{where}: rental_start_year is before purchase_year")
    if out.get("rental_end_year") is not None and start is not None and out["rental_end_year"] < start:
        raise RentalPropertyInputError(f"{where}: rental_end_year is before the rental starts")
    if out.get("sale_year") is not None and out.get("purchase_year") is not None and out["sale_year"] < out["purchase_year"]:
        raise RentalPropertyInputError(f"{where}: sale_year is before purchase_year")
    if out.get("loan_balance", 0.0) > 0 and "loan_rate" not in out and "loan_monthly_payment" not in out:
        raise RentalPropertyInputError(f"{where}: a loan_balance needs loan_rate or loan_monthly_payment")
    return out


def parse_rental_properties(c: dict[str, Any], rows: Any, *, mfs_lived_apart: Any = None) -> list[dict[str, Any]]:
    """Validate ``rows`` (one dict per property), fill the defaults and set
    ``c['rental_properties']``; returns that list.

    ``mfs_lived_apart`` (household input, optional): the spouses filing separately
    lived apart all year, which gives them the MFS passive-loss allowance (IRC
    469(i)(5)); stored as ``c['mfs_lived_apart']``. Left unset, the engine assumes
    they lived together (owner decision 2026-10-13).
    """
    if _blank(rows):
        rows = []
    if not isinstance(rows, (list, tuple)):
        raise RentalPropertyInputError("Rental properties must be a list of rows, one per property")
    if len(rows) > MAX_PROPERTIES:
        raise RentalPropertyInputError(f"At most {MAX_PROPERTIES} rental properties are supported, got {len(rows)}")
    home_value = c.get("home_val")
    home_value = None if home_value is None else float(home_value or 0.0)
    props = [_parse_one(r, i, home_value) for i, r in enumerate(rows)]
    seen: dict[str, int] = {}
    for i, p in enumerate(props):
        key = p["name"].casefold()
        if key in seen:
            raise RentalPropertyInputError(
                f"Rental properties {seen[key] + 1} and {i + 1} are both named {p['name']!r}; names must differ")
        seen[key] = i
    if sum(p["kind"] == CONVERTED_HOME for p in props) > 1:
        raise RentalPropertyInputError("Only one property can be the converted home (the plan has one home)")
    c["rental_properties"] = props
    if not _blank(mfs_lived_apart):
        c["mfs_lived_apart"] = _bool(mfs_lived_apart, "Household", "mfs_lived_apart")
    return props
