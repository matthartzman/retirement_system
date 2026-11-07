"""Tax on the gain when the plan sells its Other Assets (projection_stages/other_asset_sale_tax.py).

Before 2026-11 the start-up equity / art sale was deposited untaxed, and every item was sold in one lump in the
earliest sell year. Now each item grows (or shrinks) at its own rate, sells in its own year, and its own proceeds minus
its basis is taxed by its treatment: long-term gains at LTCG rates (through the engine's LTCG line), collectible
long-term gains at ordinary rates capped at 28%, short-term gains as ordinary income, and "Not taxed" not at all."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.projection_stages import other_asset_sale_tax as oas


def _item(name, value, basis, treatment, purchase="2020-01-01", sell="2030-06-30", rate=0.0):
    return {"name": name, "type": "Other", "value": value, "basis": basis, "basis_entered": basis > 0,
            "tax_treatment": treatment, "purchase_date": purchase, "sell_date": sell, "in_startup": True,
            "annual_appreciation_pct": rate}


def test_each_item_taxed_on_its_own_proceeds_and_sorted_by_treatment():
    c = {"plan_start": 2026, "other_asset_items": [
        _item("hucu.ai", 60_000, 10_000, "gains"),
        _item("Masterworks", 30_000, 5_000, "collectible_gains"),
        _item("Recent", 10_000, 0, "gains", purchase="2030-01-01"),  # held under a year at the 2030-06-30 sale
        {"name": "Car", "type": "Auto", "value": 40_000, "tax_treatment": "none"},  # not in the sale
    ]}
    g = oas.sale_gains(c, 2030)  # rate 0: each sells for its plan-start value
    assert g.ltcg_gain == pytest.approx(60_000 - 10_000)
    assert g.collectible_gain == pytest.approx(30_000 - 5_000)
    assert g.ordinary_gain == pytest.approx(10_000)  # blank basis: the whole proceeds
    assert [i["kind"] for i in g.items] == ["ltcg", "collectible", "ordinary"]


def test_not_taxed_items_and_losses_add_no_gain():
    c = {"plan_start": 2026,
         "other_asset_items": [_item("Art", 10_000, 50_000, "collectible_gains"), _item("Gift", 10_000, 0, "none")]}
    g = oas.sale_gains(c, 2030)
    assert (g.total_gain, [i["gain"] for i in g.items]) == (0.0, [0.0, 0.0])
    assert oas.sale_gains(c, 2029) is oas.NO_GAINS  # nothing sells that year


# ---- per-item value and sale year ----

def _plan():
    return {"plan_start": 2026, "other_asset_items": [
        _item("Start-up", 66_600, 15_000, "gains", sell="2030-12-31", rate=0.10),
        _item("Art", 6_750, 15_000, "collectible_gains", sell="", rate=-0.10),  # no sell date: held
        _item("Coins", 20_000, 5_000, "collectible_gains", sell="2033-03-01"),
    ]}


def test_each_item_sells_in_its_own_year():
    c = _plan()
    assert [(i["name"], round(p, 2)) for i, p in oas.year_sales(c, 2030)] == [("Start-up", round(66_600 * 1.1 ** 4, 2))]
    assert [i["name"] for i, _p in oas.year_sales(c, 2033)] == ["Coins"]
    assert all(not oas.year_sales(c, y) for y in (2026, 2029, 2031, 2032, 2034))


def test_an_item_with_no_sell_date_is_never_sold():
    c = _plan()
    art = c["other_asset_items"][1]
    assert all(art not in [i for i, _p in oas.year_sales(c, y)] for y in range(2026, 2080))
    assert oas.item_value(c, art, 2079) > 0


def test_a_negative_rate_depreciates_the_item():
    c = _plan()
    art = c["other_asset_items"][1]
    assert oas.item_value(c, art, 2026) == pytest.approx(6_750 * 0.9)
    assert oas.item_value(c, art, 2035) == pytest.approx(6_750 * 0.9 ** 10)
    # Held value: the unsold items only, each at its own rate.
    assert oas.held_value(c, 2031) == pytest.approx(6_750 * 0.9 ** 6 + 20_000)
    assert oas.held_value(c, 2033) == pytest.approx(6_750 * 0.9 ** 8)


def test_two_items_sold_in_different_years_each_taxed_in_its_own_year():
    c = _plan()
    g30 = oas.sale_gains(c, 2030)
    assert g30.ltcg_gain == pytest.approx(66_600 * 1.1 ** 4 - 15_000) and g30.collectible_gain == 0.0
    g33 = oas.sale_gains(c, 2033)
    assert g33.collectible_gain == pytest.approx(20_000 - 5_000) and g33.ltcg_gain == 0.0
    assert [i["name"] for i in g33.items] == ["Coins"]


def _flat(rate):
    return lambda t: max(0.0, t) * rate


def test_collectible_gain_is_capped_at_28_percent_and_short_term_is_ordinary():
    gains = oas.OtherAssetSaleGains(0.0, 100_000.0, 10_000.0, [])
    tax = oas.stacked_gain_tax(gains, taxable_inc=500_000, fed_tax_fn=_flat(0.37), state_tax_fn=_flat(0.05),
                               base_nii=0.0, magi=500_000, filing="MFJ", model_niit=True)
    assert tax.federal == pytest.approx(0.37 * 10_000 + 0.28 * 100_000)
    assert tax.state == pytest.approx(0.05 * 110_000)
    assert tax.niit == pytest.approx(0.038 * 110_000)  # MAGI is well over the threshold
    low = oas.stacked_gain_tax(gains, taxable_inc=0, fed_tax_fn=_flat(0.12), state_tax_fn=_flat(0.0),
                               base_nii=0.0, magi=0, filing="MFJ", model_niit=False)
    assert low.federal == pytest.approx(0.12 * 110_000) and low.niit == 0.0  # below 28%: the ordinary rate


# ---- through the engine ----

def _run(items, proceeds, sale_year):
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        c["other_asset_items"] = items
        c["startup_eq"] = sum(i["value"] for i in items)
        c["startup_gr"] = 0.0
        c["startup_sale_year"] = sale_year
        c["startup_sale_price"] = proceeds
        return {r["year"]: r for r in project(c)}


@pytest.fixture(scope="module")
def runs():
    year = 2028
    untaxed = _run([_item("hucu.ai", 100_000, 100_000, "gains", sell=f"{year}-06-30")], 100_000, year)
    gains = _run([_item("hucu.ai", 100_000, 20_000, "gains", sell=f"{year}-06-30")], 100_000, year)
    art = _run([_item("Masterworks", 100_000, 20_000, "collectible_gains", sell=f"{year}-06-30")], 100_000, year)
    return year, untaxed, gains, art


def test_engine_taxes_a_long_term_gain_at_ltcg_rates(runs):
    year, untaxed, gains, _art = runs
    row = gains[year]
    assert row["other_asset_sale_ltcg_gain"] == pytest.approx(80_000)
    assert row["sale_cap_gain_in_agi"] >= 80_000 - 1  # in AGI / IRMAA MAGI like a home-sale gain
    extra = row["total_tax"] - untaxed[year]["total_tax"]
    assert 0.15 * 80_000 - 1 <= extra <= (0.20 + 0.038 + 0.0495) * 80_000 + 1


def test_engine_taxes_a_collectible_gain_above_regular_ltcg(runs):
    year, untaxed, gains, art = runs
    row = art[year]
    assert row["other_asset_sale_collectible_gain"] == pytest.approx(80_000)
    assert row["other_asset_sale_stacked_tax"] > 0
    assert row["agi"] >= untaxed[year]["agi"] + 80_000 - 1  # the gain is in reported AGI
    assert row["cashflow_breakdown"]["tax"]["other_asset_sale"] == pytest.approx(row["other_asset_sale_stacked_tax"])
    assert sum(row["cashflow_breakdown"]["tax"].values()) == pytest.approx(row["total_tax"], abs=0.01)
    # A collectible pays at least as much as the same gain on regular LTCG rates, and no more than 28% + NIIT + state.
    collectible_extra = row["total_tax"] - untaxed[year]["total_tax"]
    assert collectible_extra >= gains[year]["total_tax"] - untaxed[year]["total_tax"] - 1
    assert collectible_extra <= (0.28 + 0.038 + 0.0495) * 80_000 + 1


def test_no_sale_year_no_change(runs):
    year, untaxed, gains, _art = runs
    assert gains[year - 1]["total_tax"] == pytest.approx(untaxed[year - 1]["total_tax"])
    assert "other_asset_sale_ltcg_gain" not in gains[year - 1]


def test_engine_sells_each_item_in_its_own_year_and_holds_the_rest():
    from src.planning_engines import project
    from tests import synthetic_plans as sp
    from tests.test_synthetic_golden_master import empty_workspace

    with empty_workspace():
        c = sp.SCENARIOS["baseline_balanced_couple"].build(optimize=False)
        start = int(c["plan_start"])
        items = [_item("Start-up", 100_000, 20_000, "gains", sell=f"{start + 2}-06-30"),
                 _item("Coins", 50_000, 10_000, "collectible_gains", sell=f"{start + 4}-06-30"),
                 _item("Art", 10_000, 15_000, "collectible_gains", sell="", rate=-0.10)]
        c["other_asset_items"] = items
        c["startup_eq"] = sum(i["value"] for i in items)
        rows = {r["year"]: r for r in project(c)}
    assert rows[start + 2]["startup_sale_proceeds"] == pytest.approx(100_000)
    assert rows[start + 2]["other_asset_sale_ltcg_gain"] == pytest.approx(80_000)
    assert rows[start + 2].get("other_asset_sale_collectible_gain", 0.0) == 0.0
    assert rows[start + 4]["startup_sale_proceeds"] == pytest.approx(50_000)
    assert rows[start + 4]["other_asset_sale_collectible_gain"] == pytest.approx(40_000)
    assert rows[start + 3]["startup_sale_proceeds"] == 0.0
    # Art is never sold and loses 10% a year; startup_val is the unsold items only.
    assert rows[start + 3]["startup_val"] == pytest.approx(50_000 + 10_000 * 0.9 ** 4)
    last = max(rows)
    assert rows[last]["startup_val"] == pytest.approx(10_000 * 0.9 ** (last - start + 1))
    assert all(r["startup_sale_proceeds"] == 0.0 for y, r in rows.items() if y not in (start + 2, start + 4))
