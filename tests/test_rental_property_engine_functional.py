"""WP12.2: Rental Properties in the deterministic engine (design 2026-10-05 sections 4, 5, 8).

Runs the frozen sample plan with rental properties added to ``c['rental_properties']``
(the parse boundary is WP12.3) and checks: off is a no-op; a profitable rental reaches
AGI and cash; a loss-making rental's loss is suspended, carried and released at the sale;
the sale splits unrecaptured 1250 gain and LTCG; married filing separately (lived
together) gets no allowance; the Roth-conversion sizing difference stays bounded.
"""
from __future__ import annotations

import copy

import pytest

import src.module_catalog as mc
from src.data_io import parse_client
from src.projection_stages import rental_property as rp
from src.rental_tax import PassiveActivity, property_accumulated_depreciation
from tests.golden_pricing import frozen_holdings_prices
from tests.plan_fixture import plan_data
from tests.test_deterministic_engine_full_row_snapshot_regression import empty_workspace

PROFITABLE = dict(
    name="Duplex", purchase_year=2018, purchase_month=6, purchase_price=350000, closing_costs=10000,
    current_value=450000, monthly_rent=2500, vacancy_rate=0.05, property_tax=5000, insurance=1500,
    maintenance_pct=0.08, loan_balance=200000, loan_rate=0.04, loan_term_years=22, sale_year=2035,
    improvements=[{"year": 2028, "amount": 27500}])
LOSS_MAKING = dict(
    name="Condo", purchase_year=2024, purchase_month=3, purchase_price=500000, closing_costs=10000,
    current_value=520000, monthly_rent=2000, property_tax=8000, insurance=2000, management_pct=0.08,
    loan_balance=400000, loan_rate=0.07, loan_term_years=28, sale_year=2040)


def _project(c):
    from src.planning_engines import project
    with empty_workspace(), frozen_holdings_prices():
        return project(copy.deepcopy(c))


def _config(properties=None, on=True, filing=None):
    c = parse_client(plan_data("sample_frozen"), "")
    if properties is not None:
        c["rental_properties"] = [dict(p) for p in properties]
    mc.set_feature(c, "rental_property_income", on)
    if filing:
        c["filing_status"] = filing
    return c


@pytest.fixture(scope="module")
def runs():
    base = parse_client(plan_data("sample_frozen"), "")
    return {
        "base": _project(base),
        "off": _project(_config([PROFITABLE, LOSS_MAKING], on=False)),
        "on_empty": _project(_config([], on=True)),
        "profit": _project(_config([PROFITABLE])),
        "loss": _project(_config([LOSS_MAKING])),
        "loss_mfs": _project(_config([LOSS_MAKING], filing="MFS")),
        "loss_sale": _project(_config([dict(LOSS_MAKING, sale_price=250000)])),
        "future": _project(_config([dict(name="Later", purchase_year=2030, purchase_month=4,
                                         purchase_price=300000, closing_costs=5000, loan_balance=240000,
                                         loan_rate=0.06, monthly_rent=2200, property_tax=3000)])),
    }


def _by_year(rows):
    return {r["year"]: r for r in rows}


def test_feature_defaults_off_and_is_registered():
    m = mc.CATALOG["rental_property_income"]
    assert (m.kind, m.domain, m.demand, m.tier) == (mc.PROJECTION, mc.HOUSING_PROPERTY, mc.MEDIUM, mc.ADVANCED)
    assert m.optional and m.engine_participation and m.default_on is False
    c = parse_client(plan_data("sample_frozen"), "")
    assert mc.feature_enabled(c, "rental_property_income") is False


def test_off_or_empty_is_a_no_op(runs):
    assert runs["off"] == runs["base"]
    assert runs["on_empty"] == runs["base"]
    assert not any(k.startswith("rental_") for r in runs["base"] for k in r)
    assert "rental" not in runs["base"][0]["cashflow_breakdown"]["income"]


def test_profitable_rental_reaches_agi_cash_and_net_worth(runs):
    on, off = runs["profit"], runs["base"]
    r, b = on[0], off[0]
    assert r["rental_schedule_e_net"] > 0
    # Net income passes the passive limit untouched and lands in AGI.
    assert r["rental_schedule_e_to_agi"] == pytest.approx(r["rental_schedule_e_net"])
    assert r["rental_suspended_loss_carryforward"] == 0
    # First year: the other income streams are identical, so income funding moves by the rental cash.
    assert r["income_funding"] - b["income_funding"] == pytest.approx(r["rental_net_cash_flow"])
    assert r["rental_net_cash_flow"] > 0
    assert r["rental_equity"] == pytest.approx(r["rental_property_value"] - r["rental_mortgage_balance"])
    assert r["total_liabilities"] - b["total_liabilities"] == pytest.approx(r["rental_mortgage_balance"])
    for row in on:  # the canonical cash-flow breakdown still reconciles exactly
        cb = row["cashflow_breakdown"]
        lhs = (sum(cb["income"].values()) + sum(cb["draws"].values())
               - sum(cb["expense"].values()) - sum(cb["tax"].values()))
        assert lhs == pytest.approx(cb["surplus"] - cb["unfunded_gap"], abs=0.01), row["year"]
        assert sum(cb["tax"].values()) == pytest.approx(row["total_tax"], abs=0.01), row["year"]


def test_row_fields_match_the_result_contract(runs):
    from src.result_contract import RENTAL_ROW_FIELDS, rental_summary
    keys = {k for r in runs["loss"] for k in r if k.startswith("rental_")}
    assert keys == set(RENTAL_ROW_FIELDS)
    assert rental_summary(runs["base"]) is None
    assert rental_summary(runs["profit"])["lifetime_depreciation"] > 0


def test_future_purchase_pays_the_down_payment_in_its_year(runs):
    rows = _by_year(runs["future"])
    assert rows[2029]["rental_property_value"] == 0 and rows[2029]["rental_net_cash_flow"] == 0
    buy = rows[2030]
    assert buy["rental_purchase_cash"] == pytest.approx(300000 + 5000 - 240000)
    assert buy["rental_property_value"] > 0 and 0 < buy["rental_mortgage_balance"] < 240000
    # Rented from the purchase month (April): 9 months of rent.
    assert buy["rental_gross_rent"] == pytest.approx(2200 * 12 * 1.025 ** 4 * 9 / 12)
    assert buy["rental_net_cash_flow"] < -50000


def test_sale_splits_recapture_and_ltcg_and_deposits_proceeds(runs):
    rows = _by_year(runs["profit"])
    sale = rows[2035]
    prop = sale["rental_by_property"][0]
    assert prop["sold"]
    spec = rp.parse_rental_spec(PROFITABLE, 0, {"plan_start": 2026, "inf": 0.025, "home_appr": 0.03,
                                                "home_sell_cost_pct": 0.06})
    accumulated = property_accumulated_depreciation(spec.assets(), 2035, 27.5, disposed_month=7)
    assert prop["accumulated_depreciation"] == pytest.approx(accumulated)
    gain = sale["rental_sale_gain"]
    assert gain > accumulated > 0
    assert sale["rental_sale_unrecaptured_1250_gain"] == pytest.approx(accumulated)
    assert sale["rental_sale_capital_gain"] == pytest.approx(gain - accumulated)
    assert sale["ltcg_gain"] >= sale["rental_sale_capital_gain"]
    assert sale["rental_sale_ltcg_tax"] > 0
    assert sale["rental_sale_net_proceeds"] == pytest.approx(
        sale["rental_sale_price"] - sale["rental_sale_selling_costs"] - sale["rental_sale_loan_payoff"])
    sources = [s for v in sale["_account_deposit_sources"].values() for s in v]
    assert any(s["source"] == "Rental Sale Proceeds (Duplex)" for s in sources)
    after = rows[2036]
    assert after["rental_property_value"] == 0 and after["rental_gross_rent"] == 0
    assert after["rental_suspended_loss_carryforward"] == 0


def test_loss_making_rental_is_suspended_carried_and_released(runs):
    rows = runs["loss"]
    prior = 0.0
    for r in rows:
        if r["year"] > 2040:
            break
        assert r["rental_schedule_e_net"] < 0, r["year"]
        if r["year"] < 2040:
            # Ledger: carried = carried in - this year's loss not allowed.
            assert r["rental_suspended_loss_carryforward"] == pytest.approx(
                prior - r["rental_schedule_e_net"] + r["rental_schedule_e_to_agi"]), r["year"]
        prior = r["rental_suspended_loss_carryforward"]
    first = rows[0]  # MAGI far above 150,000: nothing allowed
    assert first["rental_passive_magi"] > 150000
    assert first["rental_schedule_e_to_agi"] == 0
    assert first["rental_suspended_loss_carryforward"] == pytest.approx(-first["rental_schedule_e_net"])
    sale = _by_year(rows)[2040]
    carried_in = _by_year(rows)[2039]["rental_suspended_loss_carryforward"]
    assert carried_in > 0
    assert sale["rental_sale_gain"] > 0
    assert sale["rental_suspended_loss_carryforward"] == 0
    # A sale with a gain: the property's own losses are all allowed.
    assert sale["rental_schedule_e_to_agi"] == pytest.approx(sale["rental_schedule_e_net"] - carried_in)


def test_sale_at_a_loss_releases_suspended_losses_and_deducts_1231_loss(runs):
    rows = _by_year(runs["loss_sale"])
    carried_in = rows[2039]["rental_suspended_loss_carryforward"]
    sale = rows[2040]
    assert sale["rental_sale_gain"] < 0
    assert sale["rental_sale_ordinary_loss"] == pytest.approx(-sale["rental_sale_gain"])
    assert sale["rental_sale_unrecaptured_1250_gain"] == 0 and sale["rental_sale_capital_gain"] == 0
    assert sale["rental_passive_loss_released"] == pytest.approx(carried_in - sale["rental_schedule_e_net"])
    assert sale["rental_schedule_e_to_agi"] == pytest.approx(sale["rental_schedule_e_net"] - carried_in)
    # Underwater (loan above the net price): the shortfall is a cash need, nothing deposited.
    assert sale["rental_sale_net_proceeds"] == 0
    assert sale["rental_net_cash_flow"] < rows[2039]["rental_net_cash_flow"]


def test_roth_conversion_sizing_difference_is_bounded(runs):
    rows = runs["loss"]
    moved = False
    for r in rows:
        if "rental_conversion_sizing_difference" not in r:
            continue
        diff = r["rental_conversion_sizing_difference"]
        assert r["rental_passive_magi"] - r["rental_passive_magi_for_conversion_sizing"] == pytest.approx(r["roth_conv"])
        assert abs(diff) <= 0.5 * r["roth_conv"] + 1e-6, r["year"]
        moved = moved or abs(diff) > 1.0
    assert moved, "expected a year where the conversion moves MAGI through the phase-out"


def test_mfs_lived_together_gets_no_allowance(runs):
    for r in runs["loss_mfs"]:
        if r["year"] >= 2040:
            break
        assert r["filing"] != "MFS" or r["rental_schedule_e_to_agi"] == 0, r["year"]
    rows = _by_year(runs["loss_mfs"])
    carried_in = rows[2039]["rental_suspended_loss_carryforward"]
    assert carried_in > 0  # freed only by the full sale
    assert rows[2040]["rental_schedule_e_to_agi"] == pytest.approx(rows[2040]["rental_schedule_e_net"] - carried_in)


@pytest.mark.parametrize("filing,magi,allowed", [
    ("MFJ", 125000, 12500), ("Single", 125000, 12500), ("Single", 90000, 20000),
    ("MFS", 40000, 0), ("MFJ", 150000, 0)])
def test_passive_allowance_by_filing_status(filing, magi, allowed):
    c = {"plan_start": 2026, "inf": 0.0, "home_appr": 0.0, "home_sell_cost_pct": 0.06}
    book = rp.RentalBook(specs=(rp.parse_rental_spec({"name": "A"}, 0, c),), plan_start=2026)
    ry = rp.RentalYear(2026, (), (PassiveActivity("A", net_income=-20000.0),))
    res = book.passive_result(ry, magi, filing)
    assert res.net_to_agi == pytest.approx(-allowed)
    assert res.total_suspended == pytest.approx(20000 - allowed)
