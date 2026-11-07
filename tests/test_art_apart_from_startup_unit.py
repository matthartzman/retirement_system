"""Art & Collectibles are shown apart from Start-up Equity, and both stay inside Other Assets for net worth.

Before 2026-11 the net worth "Startup Equity" line summed every non-vehicle Other Asset: a plan's $66,600 start-up
plus its $9,000 art showed as one $74,700 line, and the art alone (no sale date) kept the line above zero after the
start-up was sold.

Design: documentation/future/superpowers/plans/2026-11-07-cash-balances-and-art-split-design-and-plan.md 3.4."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src import other_asset_tax as oat
from src.projection_stages import other_asset_sale_tax as oas

START, ART = 66_600.0, 9_000.0


@pytest.mark.parametrize("typ, want", [("Art", True), ("Collectible", True), ("Fine Art", True),
                                       ("Start-up Equity", False), ("Other", False), ("Auto", False), ("", False)])
def test_collectible_type(typ, want):
    assert oat.is_collectible_type(typ) is want


def _item(name, typ, value, rate, sell):
    return {"name": name, "type": typ, "value": value, "basis": 0.0, "annual_appreciation_pct": rate,
            "sell_date": sell, "in_startup": True, "tax_treatment": "", "purchase_date": "2020-01-01"}


def _c(art_type="Art"):
    return {"plan_start": 2026, "other_asset_items": [
        _item("Start-up Equity", "Start-up Equity", START, 0.0, "2030-12-31"),
        _item("Masterworks", art_type, ART, -0.10, "2035-12-31"),
        {"name": "Car", "type": "Auto", "value": 40_000.0, "annual_appreciation_pct": -0.1, "in_startup": None}]}


def test_held_value_split_by_year():
    c = _c()
    assert oas.held_value_split(c, 2026) == (pytest.approx(START), pytest.approx(ART * 0.9))
    assert oas.held_value_split(c, 2029) == (pytest.approx(START), pytest.approx(ART * 0.9 ** 4))
    assert oas.held_value_split(c, 2030) == (pytest.approx(0.0), pytest.approx(ART * 0.9 ** 5))  # start-up sold
    assert oas.held_value_split(c, 2035) == (pytest.approx(0.0), pytest.approx(0.0))  # art sold
    start, art = oas.held_value_split(c, 2027)
    assert start + art == pytest.approx(oas.held_value(c, 2027))


def _run(art_type):
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        items = _c(art_type)["other_asset_items"]
        c["other_asset_items"] = items
        c["startup_eq"] = START + ART
        c["startup_gr"] = 0.0
        c["startup_sale_year"] = 0
        return c, project(c)


@pytest.fixture(scope="module")
def runs():
    c_art, rows_art = _run("Art")
    _c_other, rows_other = _run("Other")  # same values, but no item is a collectible
    return c_art, {r["year"]: r for r in rows_art}, {r["year"]: r for r in rows_other}


def test_engine_splits_the_row_value_and_net_worth_is_unchanged(runs):
    _c, art, other = runs
    for year in (2026, 2029, 2030, 2034, 2035, 2036):
        assert art[year]["startup_val"] + art[year]["art_val"] == pytest.approx(other[year]["startup_val"])
        assert "art_val" not in other[year]
    # Same values, same tax until the art is sold (from 2035 it is taxed as a collectible, not as a regular gain).
    for year in (2026, 2029, 2030, 2034):
        assert art[year]["total_nw"] == pytest.approx(other[year]["total_nw"])


def test_engine_values_match_the_user_example(runs):
    _c, art, _other = runs
    assert art[2026]["startup_val"] == pytest.approx(66_600.0)
    assert art[2026]["art_val"] == pytest.approx(8_100.0)  # 74,700 together
    assert art[2030]["startup_val"] == pytest.approx(0.0)  # sold in 2030
    assert art[2030]["art_val"] == pytest.approx(ART * 0.9 ** 5, abs=0.01)  # 5,314: only the art is left
    assert art[2035]["art_val"] == pytest.approx(0.0)  # art sold in 2035


def test_net_worth_sheet_shows_the_art_column_and_foots(runs):
    from openpyxl import Workbook
    from src.reporting.sheets_projection_net_worth import build_sheet5

    c, art, _other = runs
    ws = Workbook().active
    cols = build_sheet5(ws, c, list(art.values()))
    assert "Art & Collectibles" in cols
    first = 3
    for i, (year, row) in enumerate(art.items()):
        r = first + i
        assert ws.cell(r, 1).value == year
        assert ws.cell(r, cols["Art & Collectibles"]).value == pytest.approx(row["art_val"])
        assert ws.cell(r, cols["Startup"]).value == pytest.approx(row["startup_val"])
        parts = sum(ws.cell(r, cols[k]).value or 0 for k in
                    ("Home Equity", "Next Housing Equity", "Startup", "Autos", "Note", "Cash", "Art & Collectibles"))
        parts += ws.cell(r, cols["Rental Equity"]).value or 0 if "Rental Equity" in cols else 0
        assert ws.cell(r, cols["Σ Other"]).value == pytest.approx(parts)


def test_no_art_no_new_column():
    from openpyxl import Workbook
    from src.planning_engines import project
    from src.reporting.sheets_projection_net_worth import build_sheet5
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        rows = project(c)
    assert "Art & Collectibles" not in build_sheet5(Workbook().active, c, rows)
