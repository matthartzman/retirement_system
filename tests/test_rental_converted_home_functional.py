"""WP12.3: converted home, fixture cases and the Roth-conversion interaction.

Design 2026-10-05 sections 4.5 (carrying-cost shift), 4.7-4.8 (recapture, dual basis,
section 121 two-of-five test for converted homes only) and 4 "Roth conversion
interaction". The cases are the in-code fixtures of ``tests/rental_fixtures.py`` run
through the parse boundary on the frozen sample plan (home 1,313,000, basis 800,000,
mortgage 36,000 a year to 2034, planned sale price 1,750,000).
"""
from __future__ import annotations

import pytest

from src.projection_stages import rental_property as rp
from src.rental_tax import macrs_mid_month_percentages, special_allowance
from tests import rental_fixtures as rf


@pytest.fixture(scope="module")
def runs():
    out = {name: rf.project(rf.rental_config(name)) for name in rf.CASES}
    out["base_2029"] = rf.project(rf.base_config({"home_sale_yr": 2029}))
    out["base_2033"] = rf.project(rf.base_config({"home_sale_yr": 2033}))
    out["converted_off"] = rf.project(rf.rental_config("converted_passes", on=False))
    # Sold July 2027, the conversion month: the conversion never happens.
    early = rf.RentalCase(rf.CASES["converted_passes"].rows, plan={"home_sale_yr": 2027})
    out["sold_before_conversion"] = rf.project(rf.rental_config(early))
    out["base_2027"] = rf.project(rf.base_config({"home_sale_yr": 2027}))
    # No planned sale: rented until the estate sale at the second death.
    out["kept"] = rf.project(rf.rental_config(rf.RentalCase(rf.CASES["converted_passes"].rows)))
    return out


def _y(rows):
    return rf.by_year(rows)


def test_feature_off_is_a_no_op_with_a_converted_home(runs):
    assert runs["converted_off"] == runs["base_2029"]
    assert not any(k.startswith(("rental_", "converted_home")) for r in runs["converted_off"] for k in r)


def test_carrying_costs_move_from_spending_to_schedule_e(runs):
    conv, base = _y(runs["converted_passes"]), _y(runs["base_2029"])
    c = rf.rental_config("converted_passes")
    assert "converted_home_share" not in conv[2026]
    for year, share in ((2027, 0.5), (2028, 1.0)):  # converted 1 July 2027
        r, b = conv[year], base[year]
        assert r["converted_home_share"] == pytest.approx(share)
        shifted = r["converted_home_carrying_costs"]
        # Nothing counts twice: spending drops by exactly what moved.
        assert b["total_spend"] - r["total_spend"] == pytest.approx(shifted)
        assert r["mortgage_payment_yr"] == pytest.approx(b["mortgage_payment_yr"] * (1 - share))
        assert r["real_estate_tax_yr"] == pytest.approx(b["real_estate_tax_yr"] * (1 - share))
        # The whole payment is rental debt service; only the interest is on Schedule E.
        interest = c["mort_interest_schedule"][year] * share
        assert r["rental_mortgage_interest"] == pytest.approx(interest)
        assert r["rental_mortgage_interest"] + r["rental_mortgage_principal"] == pytest.approx(
            b["mortgage_payment_yr"] * share)
        assert r["mortgage_interest_deduction"] == pytest.approx(b["mortgage_interest_deduction"] * (1 - share))
        own_opex = r["rental_operating_expenses"] - (shifted - b["mortgage_payment_yr"] * share)
        assert own_opex == pytest.approx(r["rental_gross_rent"] * 0.96 * 0.08 + 1200 * 1.025 ** (year - 2026) * share)
        assert r["rental_net_cash_flow"] == pytest.approx(
            r["rental_gross_rent"] - r["rental_vacancy_loss"] - r["rental_operating_expenses"]
            - r["rental_mortgage_interest"] - r["rental_mortgage_principal"])
        # The home stays on the home lines: no rental value or loan (no double count).
        assert r["rental_property_value"] == 0 and r["rental_mortgage_balance"] == 0
        assert r["home_val"] == pytest.approx(b["home_val"])


def test_depreciation_uses_the_lesser_basis_from_the_conversion_month(runs):
    r = _y(runs["converted_passes"])[2027]
    value = 1_313_000 * 1.03 ** 1.5  # projected to 1 July 2027
    basis = min(value, 800_000) * (1 - 0.25)  # adjusted basis is lower; land 25%
    assert r["rental_depreciation"] == pytest.approx(basis * macrs_mid_month_percentages(7, 27.5)[0] / 100)
    assert r["rental_gross_rent"] == pytest.approx(5500 * 12 * 1.025 * 6 / 12)


def test_converted_home_passing_two_of_five_excludes_all_but_depreciation(runs):
    conv, base = _y(runs["converted_passes"]), _y(runs["base_2029"])
    sale, b = conv[2029], base[2029]
    dep = sum(conv[y]["rental_depreciation"] for y in (2027, 2028, 2029))
    assert sale["home_sale_converted_home"] is True and sale["home_sale_sec121_two_of_five"] is True
    assert sale["home_sale_accumulated_depreciation"] == pytest.approx(dep)
    # Recapture: gain equal to the depreciation is never excluded.
    assert sale["home_sale_unrecaptured_1250_gain"] == pytest.approx(dep)
    assert sale["rental_sale_unrecaptured_1250_gain"] == pytest.approx(dep)
    assert sale["home_sale_gain"] == pytest.approx(b["home_sale_gain"] + dep)
    assert sale["home_sale_sec121_excluded"] == pytest.approx(500_000)
    # The rest is taxed exactly like the unconverted sale.
    assert sale["home_sale_taxable"] == pytest.approx(b["home_sale_taxable"])
    assert sale["ltcg_gain"] >= sale["home_sale_taxable"]
    prop = sale["rental_by_property"][0]
    assert prop["sold"] and prop["sec121_qualifies"] is True and prop["capital_gain"] == 0
    assert prop["home_sale_capital_gain"] == pytest.approx(sale["home_sale_taxable"])
    assert sale["home_sale_net"] == pytest.approx(b["home_sale_net"])
    after = conv[2030]
    assert after["rental_gross_rent"] == 0 and "converted_home_share" not in after
    assert after["mortgage_payment_yr"] == pytest.approx(base[2030]["mortgage_payment_yr"])
    assert "home_sale_converted_home" not in b  # every other home sale is unchanged


def test_converted_home_failing_two_of_five_taxes_the_whole_gain(runs):
    conv, base = _y(runs["converted_fails"]), _y(runs["base_2033"])
    sale, b = conv[2033], base[2033]
    dep = sum(conv[y]["rental_depreciation"] for y in range(2027, 2034))
    assert sale["home_sale_sec121_two_of_five"] is False
    assert sale["home_sale_sec121_excluded"] == 0 and sale["home_sale_sec121_exclusion"] == 0
    assert sale["home_sale_unrecaptured_1250_gain"] == pytest.approx(dep)
    assert sale["home_sale_taxable"] == pytest.approx(sale["home_sale_gain"] - dep)
    assert sale["home_sale_taxable"] == pytest.approx(b["home_sale_gain"])
    assert sale["home_sale_tax"] > b["home_sale_tax"]


def test_cash_flow_breakdown_reconciles_with_a_converted_home(runs):
    for name in ("converted_passes", "converted_fails", "kept"):
        for row in runs[name]:
            cb = row["cashflow_breakdown"]
            lhs = (sum(cb["income"].values()) + sum(cb["draws"].values())
                   - sum(cb["expense"].values()) - sum(cb["tax"].values()))
            assert lhs == pytest.approx(cb["surplus"] - cb["unfunded_gap"], abs=0.01), (name, row["year"])
            assert sum(cb["tax"].values()) == pytest.approx(row["total_tax"], abs=0.01), (name, row["year"])


def test_sale_before_the_conversion_leaves_the_plan_unchanged(runs):
    early, base = runs["sold_before_conversion"], runs["base_2027"]
    for r, b in zip(early, base):
        assert r["rental_gross_rent"] == 0 and "converted_home_share" not in r
        assert "home_sale_converted_home" not in r
        assert r["total_tax"] == pytest.approx(b["total_tax"]) and r["total_spend"] == pytest.approx(b["total_spend"])


def test_kept_converted_home_is_rented_to_the_end_without_a_converted_sale(runs):
    rows = runs["kept"]
    assert not any(r.get("home_sale_converted_home") for r in rows)
    rented = [r for r in rows if r["rental_gross_rent"] > 0]
    assert rented[0]["year"] == 2027 and len(rented) >= len(rows) - 2


def test_fixture_cases_standalone(runs):
    loss, prof = runs["standalone_loss"], runs["profitable"]
    assert all(r["rental_schedule_e_net"] < 0 for r in loss if r["year"] < 2040)
    assert all(r["rental_schedule_e_net"] > 0 for r in prof[:5])
    sale = _y(runs["sale_with_recapture"])[2035]
    prop = sale["rental_by_property"][0]
    assert prop["sold"] and sale["rental_sale_unrecaptured_1250_gain"] == pytest.approx(prop["accumulated_depreciation"])
    assert sale["rental_sale_capital_gain"] == pytest.approx(sale["rental_sale_gain"] - prop["accumulated_depreciation"])
    # Sale month 3: depreciation for 2.5 months of the sale year.
    full = _y(runs["sale_with_recapture"])[2034]["rental_depreciation"]
    assert sale["rental_depreciation"] == pytest.approx(full * 2.5 / 12, rel=1e-3)


def test_fixture_cases_filing_status(runs):
    for name, status in (("single", "Single"), ("mfs", "MFS")):
        rows = runs[name]
        assert any(r["filing"] == status for r in rows), name
        for r in rows:
            if r["year"] >= 2040:
                break
            # Loss ledger holds for every filing status.
            assert r["rental_suspended_loss_carryforward"] >= 0
    c = rf.rental_config("mfs")
    book = rp.rental_book_for(c)
    assert book.mfs_lived_apart_all_year is True
    ry = rp.RentalYear(2026, (), (rp.PassiveActivity("Condo", net_income=-20000.0),))
    assert book.passive_result(ry, 60000, "MFS").net_to_agi == pytest.approx(-7500)  # lived apart: 12,500 phased


def test_roth_conversion_under_a_loss_making_rental(runs):
    """Design section 4: the conversion is sized with the passive-loss allowance at the
    MAGI before the conversion; the final tax uses the actual MAGI (with the
    conversion); the difference is logged on the row and bounded by phase-out rate x
    conversion (the conversion can only shrink the allowance)."""
    rows = runs["standalone_loss"]
    book = rp.rental_book_for(rf.rental_config("standalone_loss"))
    carried_in, moved = 0.0, False
    for r in rows:
        if r["year"] >= 2040:  # sale year: the full disposition releases everything
            break
        k = book.constants(r["year"], r["filing"])
        loss = carried_in - r["rental_schedule_e_net"]
        actual, sizing = r["rental_passive_magi"], r.get("rental_passive_magi_for_conversion_sizing")
        assert -r["rental_schedule_e_to_agi"] == pytest.approx(min(loss, special_allowance(actual, k)))
        if sizing is not None:
            conv = r["roth_conv"]
            assert actual - sizing == pytest.approx(conv)
            assert -r["rental_schedule_e_to_agi_for_conversion_sizing"] == pytest.approx(
                min(loss, special_allowance(sizing, k)))
            diff = r["rental_conversion_sizing_difference"]
            assert -1e-6 <= diff <= k.phaseout_rate * conv + 1e-6, r["year"]
            moved = moved or diff > 1.0
        carried_in = r["rental_suspended_loss_carryforward"]
    assert moved, "expected a conversion year inside the allowance phase-out band"
