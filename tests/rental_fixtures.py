"""In-code Rental Properties fixtures (WP12.3; design 2026-10-05 section 9).

Source rows for the parse boundary (``src.data_io.parse_rental_properties``) on top of
the frozen sample plan, one case per scenario the design asks for: standalone
loss-making, profitable, converted home that passes and that fails the section 121
two-of-five-year test, sale with recapture, married filing separately and single.
Values are deliberately given in mixed source forms ("350,000", "20%", "yes") because
the boundary is source-agnostic. Nothing here reads or writes a file of its own; the
sample plan comes from ``tests.plan_fixture``.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import src.module_catalog as mc
from src.data_io import parse_client, parse_rental_properties
from tests.golden_pricing import frozen_holdings_prices
from tests.plan_fixture import plan_data
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace

LOSS_MAKING = {
    "name": "Condo", "kind": "Standalone", "purchase_year": 2024, "purchase_month": 3,
    "purchase_price": "500,000", "closing_costs": 10000, "current_value": 520000, "monthly_rent": 2000,
    "property_tax": 8000, "insurance": 2000, "management_pct": "8%", "loan_balance": 400000,
    "loan_rate": 0.07, "loan_term_years": 28, "sale_year": 2040, "active_participation": "yes",
    "notes": "unknown keys are ignored",
}
PROFITABLE = {
    "name": "Duplex", "purchase_year": 2018, "purchase_month": 6, "purchase_price": 350000,
    "closing_costs": 10000, "land_share": "20%", "current_value": 450000, "monthly_rent": 2500,
    "vacancy_rate": 0.05, "property_tax": 5000, "insurance": 1500, "maintenance_pct": 0.08,
    "loan_balance": 200000, "loan_rate": 0.04, "loan_term_years": 22,
    "improvements": [{"year": 2028, "amount": 27500}],
}
SALE_WITH_RECAPTURE = dict(PROFITABLE, name="Duplex for sale", sale_year=2035, sale_month=3)
CONVERTED_HOME = {
    "name": "Our house", "kind": "Converted home", "conversion_year": 2027, "monthly_rent": 5500,
    "vacancy_rate": 0.04, "management_pct": 0.08, "insurance": 1200, "land_share": 0.25,
}


@dataclass(frozen=True)
class RentalCase:
    rows: list[dict[str, Any]]
    plan: dict[str, Any] = field(default_factory=dict)  # engine-config overrides (the household side)
    mfs_lived_apart: Any = None


CASES: dict[str, RentalCase] = {
    "standalone_loss": RentalCase([LOSS_MAKING]),
    "profitable": RentalCase([PROFITABLE]),
    # Converted 1 July 2027 (month 7 default); sold 1 July 2029 (sale month 7): lived
    # in through the conversion, so 730+ days of use in the five years -> passes.
    "converted_passes": RentalCase([CONVERTED_HOME], plan={"home_sale_yr": 2029}),
    # Sold July 2033: the five-year window starts after the move-out -> fails.
    "converted_fails": RentalCase([CONVERTED_HOME], plan={"home_sale_yr": 2033}),
    "sale_with_recapture": RentalCase([SALE_WITH_RECAPTURE]),
    "mfs": RentalCase([LOSS_MAKING], plan={"filing_status": "MFS"}, mfs_lived_apart="yes"),
    "single": RentalCase([LOSS_MAKING], plan={"filing_status": "Single"}),
}


def base_config(plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """The frozen sample plan's engine config with ``plan`` overrides applied."""
    c = parse_client(plan_data("sample_frozen"), "")
    c.update(plan or {})
    return c


def rental_config(case: str | RentalCase, *, on: bool = True) -> dict[str, Any]:
    """Engine config for a case: rows through the parse boundary, feature switched."""
    rc = CASES[case] if isinstance(case, str) else case
    c = base_config(rc.plan)
    parse_rental_properties(c, copy.deepcopy(rc.rows), mfs_lived_apart=rc.mfs_lived_apart)
    mc.set_feature(c, "rental_property_income", on)
    return c


def project(c: dict[str, Any]) -> list[dict[str, Any]]:
    from src.planning_engines import project as _project
    with empty_workspace(), frozen_holdings_prices():
        return _project(copy.deepcopy(c))


def by_year(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {r["year"]: r for r in rows}
