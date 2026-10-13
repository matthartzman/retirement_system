from __future__ import annotations

"""Rental Properties page service (WP12.6, design 2026-10-05 sections 3 and 6).

The route layer owns permissions and request parsing; this service owns the reads and writes
of the plan's rental properties through ``store.rental`` (``RentalRepo``): list, get, save,
duplicate, delete, and the improvements and year overrides of one property. A write keeps only
the keys ``RentalRepo`` knows (unknown keys are dropped), is checked by the parse boundary
``parse_rental_properties`` (the same check the build applies; a bad property is refused with
the parser's message and nothing is written), and goes through the context's ``edit_plan``
(one transaction on the plan file).

The page's summary strip, warnings and table are an ESTIMATE computed here from the stored
properties with the projection's own rental stage (``RentalBook``: the same tax core the
engine uses) over the plan's horizon. It is not the last build's result: it does not move the
home's carrying costs, the household's real MAGI is replaced by an assumed figure the caller
passes, and the Roth, sale-tax and housing interactions are not run. The payload says so
(``estimate``), and the page labels the numbers.
"""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable

from ..parsing.rental_properties import (
    CONVERTED_HOME,
    MAX_PROPERTIES,
    STANDALONE,
    RentalPropertyInputError,
    parse_rental_properties,
)
from ..projection_stages.rental_property import (
    RentalBook,
    net_cash_flow,
    ordinary_income,
    parse_rental_spec,
)
from ..rental_tax import converted_home_depreciable_basis, property_accumulated_depreciation

JsonDict = dict[str, Any]


def _liability_options(c: dict[str, Any] | None) -> list[JsonDict]:
    """Liabilities rows a property can use as its loan (H2): everything with an id but student loans."""
    return [{"id": li["liability_id"], "label": li.get("label") or li["liability_id"], "type": li.get("type"),
             "balance": li.get("balance", 0.0), "rate": li.get("interest_rate", 0.0)}
            for li in ((c or {}).get("liabilities") or [])
            if li.get("liability_id") and li.get("type") != "student_loan"]
AuditFn = Callable[[str, dict[str, Any] | None], None]

# The keys ``RentalRepo`` stores (src/stores/rental_repo.py; product code reaches the stores
# package only through active_plan, so they are named here and a test pins them to the repo's).
IMPROVEMENT_KEYS = ("year", "month", "amount", "description")
OVERRIDE_KEYS = ("year", "gross_rent", "operating_expenses", "notes")
PROPERTY_COLUMNS = (
    "kind", "owner", "notes", "loan_liability_id",
    "purchase_price", "closing_costs", "current_value", "monthly_rent", "property_tax", "insurance", "hoa",
    "utilities", "other_expenses", "loan_balance", "loan_monthly_payment", "prior_suspended_loss", "sale_price",
    "value_at_conversion", "adjusted_basis_at_conversion",
    "land_share", "vacancy_rate", "maintenance_pct", "management_pct", "selling_cost_pct",
    "appreciation", "rent_growth", "expense_growth", "property_tax_growth", "loan_rate",
    "purchase_year", "value_as_of_year", "rental_start_year", "rental_end_year", "loan_balance_year",
    "placed_in_service_year", "sale_year", "conversion_year",
    "purchase_month", "placed_in_service_month", "sale_month", "conversion_month", "loan_term_years",
    "reversion_month", "active_participation", "moves_back_in",
)
_PROPERTY_KEYS = frozenset(("name", "improvements", "overrides", *PROPERTY_COLUMNS))
DOUBLE_COUNT_TOLERANCE = 0.05  # owner decision 2026-10-13: same name OR value within 5%
MAX_YEARS = 60


# --------------------------------------------------------------------------- input cleaning
def _num(v: Any, default: float = 0.0) -> float:
    try:
        return default if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return default


def clean_property(raw: Any) -> JsonDict:
    """The property row with only the keys ``RentalRepo`` stores (unknown keys dropped, also
    inside improvements and overrides) and a canonical ``kind``."""
    if not isinstance(raw, dict):
        raise ValueError("property must be an object")
    out = {k: v for k, v in raw.items() if k in _PROPERTY_KEYS}
    kind = str(out.get("kind") or STANDALONE).strip().lower().replace(" ", "_")
    out["kind"] = CONVERTED_HOME if kind in ("converted_home", "converted") else kind
    imps = out.get("improvements")
    if isinstance(imps, (list, tuple)):
        out["improvements"] = [{k: v for k, v in i.items() if k in IMPROVEMENT_KEYS} for i in imps if isinstance(i, dict)]
    ovs = out.get("overrides")
    if isinstance(ovs, (list, tuple)):
        out["overrides"] = [{k: v for k, v in o.items() if k in OVERRIDE_KEYS} for o in ovs if isinstance(o, dict)]
    return out


def _index(rows: list[JsonDict], name: Any) -> int | None:
    key = str(name or "").strip().casefold()
    return next((i for i, p in enumerate(rows) if p["name"].casefold() == key), None)


def _copy_name(rows: list[JsonDict], name: str) -> str:
    taken = {p["name"].casefold() for p in rows}
    n, label = 1, f"{name} (copy)"
    while label.casefold() in taken:
        n += 1
        label = f"{name} (copy {n})"
    return label


# ------------------------------------------------------------------------------ the estimate
def _book(c: JsonDict, rows: list[JsonDict]) -> tuple[RentalBook | None, list[JsonDict]]:
    """A ``RentalBook`` over the stored properties, ``rental_book_for`` without its feature
    switch (the page previews a switched-off module). Raises ``RentalPropertyInputError``."""
    cc = dict(c)
    parsed = parse_rental_properties(cc, [dict(r) for r in rows])
    specs = [s for i, p in enumerate(parsed) if (s := parse_rental_spec(p, i, cc)) is not None]
    converted = [s for s in specs if s.kind == CONVERTED_HOME]
    if len(converted) > 1:
        specs = [s for s in specs if s.kind != CONVERTED_HOME or s is converted[0]]
    if not specs:
        return None, parsed
    lived_apart = c.get("mfs_lived_apart")
    return RentalBook(specs=tuple(specs), plan_start=int(c["plan_start"]), mfs_lived_apart_all_year=bool(lived_apart)), parsed


def _series(book: RentalBook, c: JsonDict, magi: float) -> list[JsonDict]:
    start = int(c["plan_start"])
    end = max(start, min(int(_num(c.get("plan_end"), start + 30)), start + MAX_YEARS))
    filing = str(c.get("filing_status") or "MFJ")
    out = []
    prior = sum(s.prior_suspended_loss for s in book.specs)
    for y in range(start, end + 1):
        ry = book.year_flows(y)
        res = book.settle_passive(ry, magi, filing)
        k = book.constants(y, filing)
        rental_rows = [p for p in ry.properties if p.owned or p.sold]
        recovery = book.constants(y, "MFJ").recovery_years
        susp = {a.name: a.suspended for a in res.activities}
        accumulated = {}
        for sp in book.specs:
            through = y if sp.rental_end_year is None else min(y, sp.rental_end_year)
            sold_before = sp.sale_year is not None and y > sp.sale_year
            accumulated[sp.name] = 0.0 if sold_before else property_accumulated_depreciation(sp.assets(), through, recovery)
        out.append({
            "year": y,
            "net_cash_flow": net_cash_flow(ry),
            "schedule_e": ry.total("schedule_e"),
            "taxable_rental_income": ordinary_income(ry, res),
            "suspended_loss": res.total_suspended,
            "suspended_added": max(0.0, res.total_suspended - prior),
            "allowance_available": res.special_allowance_available,
            "allowance": k.special_allowance,
            "phaseout_start": k.phaseout_start,
            "equity": sum(p.value - p.loan_balance for p in ry.properties),
            "losses": {p.name: p.schedule_e for p in rental_rows if p.schedule_e < 0},
            "suspended_by_property": {n: v for n, v in susp.items() if v > 0},
            "by_property": {p.name: {"depreciation": p.depreciation, "schedule_e": p.schedule_e,
                                     "accumulated_depreciation": accumulated.get(p.name, 0.0),
                                     "suspended_loss": susp.get(p.name, 0.0)} for p in ry.properties},
        })
        prior = res.total_suspended
    return out


def _annual(p: JsonDict, key: str) -> float:
    return _num(p.get(key))


def table_row(p: JsonDict, spec_value: float | None = None) -> JsonDict:
    """One property's table figures from its stored fields: value, gross annual rent and net
    yield = (rent - operating expenses) / value (owner decision 2026-10-13)."""
    converted = p.get("kind") == CONVERTED_HOME
    value = _num(spec_value) if converted else _annual(p, "current_value") or _annual(p, "purchase_price")
    rent = _annual(p, "monthly_rent") * 12.0
    collected = rent * (1.0 - min(1.0, max(0.0, _annual(p, "vacancy_rate"))))
    opex = (_annual(p, "property_tax") + _annual(p, "insurance") + _annual(p, "hoa") + _annual(p, "utilities")
            + _annual(p, "other_expenses") + (_annual(p, "maintenance_pct") + _annual(p, "management_pct")) * collected)
    return {
        "name": p["name"], "kind": p.get("kind") or STANDALONE, "value": value, "annual_rent": rent,
        "operating_expenses": opex, "net_yield": ((rent - opex) / value) if value > 0 else None,
        "sale_year": p.get("sale_year"),
    }


def _double_counts(rows: list[JsonDict], c: JsonDict) -> list[JsonDict]:
    out = []
    for a in c.get("other_asset_items") or []:
        name, value = str(a.get("name") or "").strip(), _num(a.get("value"))
        for p in rows:
            pv = _num(p.get("current_value"))
            same_name = bool(name) and name.casefold() == p["name"].casefold()
            close = value > 0 and pv > 0 and abs(value - pv) / max(value, pv) <= DOUBLE_COUNT_TOLERANCE
            if same_name or close:
                how = "name and value" if same_name and close else "name" if same_name else "value"
                out.append({
                    "id": f"double_count:{p['name']}:{name}", "kind": "double_count", "level": "warn",
                    "title": "Possible double count.",
                    "text": f"\"{name}\" in Other Assets (${value:,.0f}) matches the rental property \"{p['name']}\" by {how}. "
                            "Enter a property once: here or in Other Assets.",
                    "property": p["name"], "action": "other_assets",
                })
    return out


def _passive_warning(series: list[JsonDict], magi: float) -> JsonDict | None:
    hit = next((s for s in series if s["suspended_added"] > 0.5), None)
    if hit is None:
        return None
    name = max(hit["suspended_by_property"], key=hit["suspended_by_property"].get, default="")
    loss = abs(hit["losses"].get(name, 0.0)) if name else 0.0
    cut = ""
    if magi > hit["phaseout_start"]:
        cut = f" (assumed other income ${magi:,.0f} cuts the ${hit['allowance']:,.0f} allowance to ${hit['allowance_available']:,.0f})"
    which = f" of the {name} loss" if name and loss else ""
    return {
        "id": f"passive_limit:{hit['year']}", "kind": "passive_limit", "level": "warn",
        "title": "Loss limited by passive rule.",
        "text": f"{hit['year']}: ${hit['suspended_added']:,.0f}{which} is suspended{cut}. Carried forward.",
        "property": name or None, "action": "why",
        "detail": (f"A rental loss offsets other rental income first. With active participation up to "
                   f"${hit['allowance']:,.0f} more can offset other income; that allowance shrinks by 50 cents per "
                   f"dollar of income over ${hit['phaseout_start']:,.0f}. The rest is carried forward and released "
                   "when you sell the property."),
    }


def _section_121_warning(book: RentalBook, c: JsonDict) -> JsonDict | None:
    spec = book.converted_spec()
    sale_year = int(_num(c.get("home_sale_yr")))
    if spec is None or sale_year <= 0:
        return None
    filing = str(c.get("filing_status") or "MFJ")
    terms = book.converted_home_sale_terms(sale_year, filing)
    if terms is None or terms.qualifies:
        return None
    k = book.constants(sale_year, filing)
    return {
        "id": f"section_121:{spec.name}", "kind": "section_121", "level": "bad",
        "title": "Section 121 test fails.",
        "text": (f"{spec.name} converted {spec.placed_year}, sold {sale_year}: it was not your main home for 2 of the "
                 f"5 years before the sale, so the gain is fully taxable instead of excluding up to "
                 f"${k.section_121_exclusion:,.0f}. This is a warning only; nothing is blocked."),
        "property": spec.name, "action": "open_property",
    }


def _home_info(c: JsonDict | None) -> JsonDict:
    """The plan's home, for Convert my home (no suggested rent: the owner types it)."""
    home_val = _num((c or {}).get("home_val"))
    if c is None or home_val <= 0:
        return {"available": False}
    start = int(c["plan_start"])
    steps = [int(s["start_year"]) for s in c.get("next_housing_steps") or [] if s.get("start_year")]
    year = min(steps) if steps else start
    appr = _num(c.get("home_appr"))
    value = home_val * (1.0 + appr) ** max(0.0, year - start + 0.5)
    basis = _num(c.get("home_basis")) or home_val * 0.5
    return {
        "available": True, "label": "Primary residence", "value_today": home_val, "adjusted_basis": basis,
        "appreciation": appr, "conversion_year": year, "value_at_conversion": round(value),
        "depreciable_basis": round(converted_home_depreciable_basis(value, basis, 0.20)),
        "home_sale_year": int(_num(c.get("home_sale_yr"))) or None,
        "section_121_exclusion": _num(c.get("sec121")),
    }


@dataclass(frozen=True)
class RentalServiceContext:
    edit_plan: Callable[[], AbstractContextManager[Any]]
    read_plan: Callable[[], AbstractContextManager[Any]]
    load_config: Callable[[], JsonDict]  # the engine config (parse_client) of the active plan
    field_tiers: Callable[[], dict[tuple[str, str, str], str]]
    audit: AuditFn | None = None


class RentalService:
    """Framework-neutral owner of the Rental Properties page's reads and writes."""

    def __init__(self, context: RentalServiceContext):
        self.context = context

    def _audit(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.context.audit:
            self.context.audit(event, details or {})

    def _config(self) -> tuple[JsonDict | None, str]:
        try:
            return self.context.load_config(), ""
        except Exception as exc:  # a plan the engine cannot read yet: the page still lists and edits
            return None, str(exc)

    def _stored(self) -> list[JsonDict]:
        with self.context.read_plan() as store:
            return store.rental.properties()

    def _feature_on(self) -> bool:
        from .. import module_catalog as mc
        with self.context.read_plan() as store:
            return bool(mc.feature_enabled(store, "rental_property_income"))

    def _tiers(self) -> JsonDict:
        out: JsonDict = {"property": {}, "improvement": {}, "override": {}}
        sub = {"Property": "property", "Improvement": "improvement", "Year Override": "override"}
        for (section, subsection, label), tier in self.context.field_tiers().items():
            if section == "Rental Properties" and subsection in sub:
                out[sub[subsection]][label] = tier
        return out

    # ------------------------------------------------------------------------------ reads
    def list_payload(self, year: Any = None, magi: Any = None) -> tuple[JsonDict, int]:
        """The page: stored properties, feature state, and the estimate (summary strip, warnings,
        table figures) for ``year`` (default the first projection year) at an assumed ``magi``."""
        rows = self._stored()
        c, config_error = self._config()
        magi_value = max(0.0, _num(magi))
        payload: JsonDict = {
            "success": True, "enabled": self._feature_on(), "count": len(rows), "max_properties": MAX_PROPERTIES,
            "properties": rows, "field_tiers": self._tiers(), "home": _home_info(c),
            "estimate": {
                "available": False, "label": "Estimate from your property entries, not from the last build",
                "magi": magi_value, "notes": [
                    "Rent, expenses, debt service, depreciation and Schedule E come from the same rental rules the projection uses.",
                    "The passive-loss limit assumes the other income (MAGI) shown, not your plan's real income.",
                    "A converted home's carrying costs and the sale tax are not included.",
                ],
            },
            "summary": None, "warnings": [], "table": [t for t in (table_row(p) for p in rows)],
            "liability_options": _liability_options(c),
        }
        if c is None:
            payload["estimate"]["error"] = config_error
            return payload, 200
        start = int(c["plan_start"])
        payload["estimate"]["years"] = {"first": start, "last": max(start, min(int(_num(c.get("plan_end"), start + 30)), start + MAX_YEARS))}
        try:
            book, parsed = _book(c, rows)
        except RentalPropertyInputError as exc:
            payload["estimate"]["error"] = str(exc)
            return payload, 200
        payload["warnings"] = _double_counts(rows, c)
        if book is not None:
            payload["warnings"] += list(book.link_warnings)
        if book is None:
            return payload, 200
        series = _series(book, c, magi_value)
        want = int(_num(year, start))
        row = next((s for s in series if s["year"] == want), series[0])
        for t in payload["table"]:
            spec = next((s for s in book.specs if s.name == t["name"]), None)
            if spec is not None and spec.kind == CONVERTED_HOME:
                t["value"] = spec.value_at_conversion
                t["net_yield"] = ((t["annual_rent"] - t["operating_expenses"]) / t["value"]) if t["value"] > 0 else None
        passive = _passive_warning(series, magi_value)
        s121 = _section_121_warning(book, c)
        payload["warnings"] += [w for w in (passive, s121) if w]
        payload["estimate"]["available"] = True
        payload["summary"] = {
            "year": row["year"], "net_cash_flow": row["net_cash_flow"],
            "taxable_rental_income": row["taxable_rental_income"], "suspended_loss": row["suspended_loss"],
            "equity": row["equity"], "by_property": row["by_property"],
        }
        return payload, 200

    def get_payload(self, name: Any) -> tuple[JsonDict, int]:
        with self.context.read_plan() as store:
            prop = store.rental.get(str(name or ""))
        if prop is None:
            return {"success": False, "error": f"no rental property named {str(name or '')!r}"}, 404
        return {"success": True, "property": prop}, 200

    def home_payload(self) -> tuple[JsonDict, int]:
        c, _err = self._config()
        return {"success": True, "home": _home_info(c)}, 200

    # ----------------------------------------------------------------------------- writes
    def _commit(self, rows: list[JsonDict], event: str, details: JsonDict) -> tuple[JsonDict, int]:
        """Validate the whole set with the build's parse boundary, then replace it atomically."""
        c, _err = self._config()
        try:
            parse_rental_properties(dict(c or {}), [dict(r) for r in rows])
            with self.context.edit_plan() as edit:
                edit.store.rental.replace_all(rows)
            revision = edit.revision
        except ValueError as exc:  # parse boundary (RentalPropertyInputError) or the repo's ValidationError
            return {"success": False, "error": str(exc)}, 400
        except Exception as exc:
            self._audit(event + "_failed", {**details, "error": str(exc)})
            return {"success": False, "error": f"Rental properties could not be saved: {exc}"}, 500
        self._audit(event, {**details, "revision": revision})
        return {"success": True, "count": len(rows), "revision": revision}, 200

    def save_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """``{property, original_name?}``: add the property, or replace the one named
        ``original_name`` (default: its own name), keeping its place in the order."""
        try:
            prop = clean_property(body.get("property"))
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        if not str(prop.get("name") or "").strip():
            return {"success": False, "error": "name is required"}, 400
        prop["name"] = str(prop["name"]).strip()
        rows = self._stored()
        at = _index(rows, body.get("original_name") or prop["name"])
        if at is None:
            rows.append(prop)
        else:
            rows[at] = prop
        out, status = self._commit(rows, "rental_property_saved", {"name": prop["name"], "new": at is None})
        if status == 200:
            out["property"] = prop
        return out, status

    def duplicate_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        rows = self._stored()
        at = _index(rows, body.get("name"))
        if at is None:
            return {"success": False, "error": f"no rental property named {str(body.get('name') or '')!r}"}, 404
        src = rows[at]
        if src.get("kind") == CONVERTED_HOME:
            return {"success": False, "error": "Only one property can be the converted home (the plan has one home), so it cannot be duplicated."}, 400
        copy = {**src, "name": _copy_name(rows, src["name"]),
                "improvements": [dict(i) for i in src.get("improvements", [])],
                "overrides": [dict(o) for o in src.get("overrides", [])]}
        rows.insert(at + 1, copy)
        out, status = self._commit(rows, "rental_property_duplicated", {"name": src["name"], "copy": copy["name"]})
        if status == 200:
            out["property"] = copy
        return out, status

    def delete_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        rows = self._stored()
        at = _index(rows, body.get("name"))
        if at is None:
            return {"success": False, "error": f"no rental property named {str(body.get('name') or '')!r}"}, 404
        name = rows.pop(at)["name"]
        return self._commit(rows, "rental_property_deleted", {"name": name})

    def _replace_child(self, body: dict[str, Any], field: str) -> tuple[JsonDict, int]:
        rows = self._stored()
        at = _index(rows, body.get("name"))
        if at is None:
            return {"success": False, "error": f"no rental property named {str(body.get('name') or '')!r}"}, 404
        items = body.get(field)
        if items is not None and not isinstance(items, (list, tuple)):
            return {"success": False, "error": f"{field} must be a list of rows"}, 400
        try:
            rows[at] = clean_property({**rows[at], field: list(items or [])})
        except ValueError as exc:
            return {"success": False, "error": str(exc)}, 400
        out, status = self._commit(rows, f"rental_{field}_saved", {"name": rows[at]["name"], "rows": len(items or [])})
        if status == 200:
            out[field] = rows[at][field]
        return out, status

    def improvements_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """``{name, improvements}``: replace the capital improvements of one property."""
        return self._replace_child(body, "improvements")

    def overrides_payload(self, body: dict[str, Any]) -> tuple[JsonDict, int]:
        """``{name, overrides}``: replace the per-year rent and expense overrides of one property."""
        return self._replace_child(body, "overrides")
