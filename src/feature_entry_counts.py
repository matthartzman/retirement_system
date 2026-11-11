"""How much data the plan holds behind a feature switch (ARC-002 / W2-07).

Pure rules over a plan store, moved out of ``server_services.plan_tier_service`` so the one-time
legacy converter (``legacy_conversion.steps.t8_tier_mapping``) no longer imports a server service.
``plan_tier_service`` re-exports both names.
"""
from __future__ import annotations

from typing import Any

from . import module_catalog as mc


def entered_value(value: Any) -> bool:
    """A plan value that counts as entered data: non-blank and not a bare off switch.
    The rule the Plan Features page's ``enteredRowCount`` applies."""
    v = str(value if value is not None else "").strip()
    return bool(v) and v.upper() not in ("NO", "FALSE", "0")


def entered_rows(store: Any, key: str) -> int | None:
    """Rows of entered data behind feature ``key``, or None when the catalog declares no data
    location for it (only modules that gate input sections, ``csv_sections``, have one, plus
    Rental Properties, whose rows are its typed tables; a module owning a whole page is counted
    by the page from its own rows)."""
    if key == "rental_property_income":  # typed rental tables (WP12.4), not plan rows
        return store.rental.count()
    sections = mc.CATALOG[key].csv_sections
    if not sections:
        return None
    return sum(1 for s in sections for r in store.rows(s) if entered_value(r["value"]))
