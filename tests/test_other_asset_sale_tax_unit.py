"""Tax on the gain when the plan sells its Other Assets (projection_stages/other_asset_sale_tax.py).

Before 2026-11 the start-up equity / art sale was deposited untaxed. Now each item's share of the proceeds minus its
basis is taxed by its treatment: long-term gains at LTCG rates (through the engine's LTCG line), collectible
long-term gains at ordinary rates capped at 28%, short-term gains as ordinary income, and "Not taxed" not at all."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

from src.projection_stages import other_asset_sale_tax as oas


def _item(name, value, basis, treatment, purchase="2020-01-01", sell="2030-06-30"):
    return {"name": name, "type": "Other", "value": value, "basis": basis, "basis_entered": basis > 0,
            "tax_treatment": treatment, "purchase_date": purchase, "sell_date": sell, "in_startup": True}


def test_proceeds_split_by_value_and_sorted_by_treatment():
    c = {"other_asset_items": [
        _item("hucu.ai", 60_000, 10_000, "gains"),
        _item("Masterworks", 30_000, 5_000, "collectible_gains"),
        _item("Recent", 10_000, 0, "gains", purchase="2030-01-01"),  # held under a year at the 2030-06-30 sale
        {"name": "Car", "type": "Auto", "value": 40_000, "tax_treatment": "none"},  # not in the sale
    ]}
    g = oas.sale_gains(c, 2030, 200_000)  # proceeds 2x the start values
    assert g.ltcg_gain == pytest.approx(120_000 - 10_000)
    assert g.collectible_gain == pytest.approx(60_000 - 5_000)
    assert g.ordinary_gain == pytest.approx(20_000)  # blank basis: the whole share
    assert [i["kind"] for i in g.items] == ["ltcg", "collectible", "ordinary"]


def test_not_taxed_items_and_losses_add_no_gain():
    c = {"other_asset_items": [_item("Art", 10_000, 50_000, "collectible_gains"), _item("Gift", 10_000, 0, "none")]}
    g = oas.sale_gains(c, 2030, 20_000)
    assert (g.total_gain, [i["gain"] for i in g.items]) == (0.0, [0.0, 0.0])
    assert oas.sale_gains(c, 2030, 0.0) is oas.NO_GAINS


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
