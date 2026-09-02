"""Wave 3 item 3.6 (system review 2026-08-31, finding F5): New York's
estate tax was a deliberate ``estate_calc='not_modeled'`` hole -- NY has
``estate=True`` and a real $6.94M exemption but no computed mechanism,
returning 0.0 with an explicit disclosure contract rather than a silently
wrong number. This completes New York's mechanism: the graduated rate
table, the 105%-of-exemption cliff, and the three-year gift add-back
(NY Tax Law Β§954(a)(3) -- NY decoupled from the federal repeal of the
3-year rule).
"""
import pytest

from src.core import new_york_estate_tax, resolved_state_estate_exemption, state_estate_tax


EXEMPT = 6_940_000.0


def test_below_exemption_owes_nothing():
    assert new_york_estate_tax(5_000_000.0, EXEMPT) == 0.0


def test_at_exactly_the_exemption_owes_nothing():
    assert new_york_estate_tax(EXEMPT, EXEMPT) == 0.0


def test_just_over_the_exemption_owes_a_real_but_bounded_amount():
    # Inside the narrow 100%-105% phase-out band, tax rises very quickly
    # (the whole scaled-up taxable base, not just the raw excess) -- real,
    # by the cliff's own design -- but must stay well short of what the
    # SAME estate would owe once it actually reaches the cliff.
    tax = new_york_estate_tax(EXEMPT + 100_000.0, EXEMPT)
    at_cliff_tax = new_york_estate_tax(EXEMPT * 1.05, EXEMPT)
    assert 0.0 < tax < at_cliff_tax


def test_the_cliff_taxes_the_entire_estate_not_just_the_excess():
    # At/above 105% of the exemption, NY's cliff removes the exclusion
    # entirely -- the full estate is taxed from dollar one.
    cliff = EXEMPT * 1.05
    at_cliff = new_york_estate_tax(cliff, EXEMPT)
    # Full-table tax on the whole $7,287,000 estate, no exclusion at all.
    from src.core import new_york_estate_tax as _nyet
    full_table_tax_on_whole_estate = _nyet(cliff, 0.0)  # exemption=0 -> no exclusion, same table
    assert at_cliff == pytest.approx(full_table_tax_on_whole_estate)


def test_a_household_just_over_the_exemption_shows_the_discontinuity():
    # The review's own framing: "a household just over the exemption faces
    # a discontinuity the tool currently reports as zero." Two estates a
    # small dollar amount apart, one just under/at the exemption (zero tax)
    # and one just past the 105% cliff, must show a large, non-linear jump
    # -- not a smooth, proportional increase.
    just_under = new_york_estate_tax(EXEMPT, EXEMPT)
    cliff = EXEMPT * 1.05
    just_over_cliff = new_york_estate_tax(cliff + 1000.0, EXEMPT)
    assert just_under == 0.0
    assert just_over_cliff > 500_000.0  # a five-figure estate difference, six-figure tax jump


def test_tax_rises_monotonically_with_estate_size():
    values = [new_york_estate_tax(v, EXEMPT) for v in
              (EXEMPT, EXEMPT * 1.02, EXEMPT * 1.05, 10_000_000.0, 15_000_000.0, 25_000_000.0)]
    assert values == sorted(values)


def test_three_year_gift_addback_can_push_an_under_exemption_estate_into_tax():
    base_estate = EXEMPT - 200_000.0
    without_addback = new_york_estate_tax(base_estate, EXEMPT)
    with_addback = new_york_estate_tax(base_estate, EXEMPT, gift_addback=500_000.0)
    assert without_addback == 0.0
    assert with_addback > 0.0


def test_zero_exemption_taxes_from_dollar_one_via_the_table_directly():
    assert new_york_estate_tax(500_000.0, 0.0) == pytest.approx(500_000.0 * 0.0306)


def test_dispatch_through_state_estate_tax_returns_computed_status():
    tax, status = state_estate_tax('New York', 20_000_000.0, EXEMPT)
    assert status == 'computed'
    assert tax > 0.0


def test_dispatch_passes_the_gift_addback_through():
    base_estate = EXEMPT - 200_000.0
    tax_none, _ = state_estate_tax('New York', base_estate, EXEMPT)
    tax_with, _ = state_estate_tax('New York', base_estate, EXEMPT, gift_addback=500_000.0)
    assert tax_none == 0.0
    assert tax_with > 0.0


def test_illinois_is_unaffected_by_the_ny_calc_addition():
    tax, status = state_estate_tax('Illinois', 20_000_000.0, 4_000_000.0)
    assert status == 'computed'
    # Must still use the credit-table mechanism (a materially different
    # figure from what the NY graduated table would produce for the same
    # inputs) -- confirms the two states' calcs did not collide.
    ny_tax, _ = state_estate_tax('New York', 20_000_000.0, 4_000_000.0)
    assert tax != ny_tax


# ── resolved_state_estate_exemption ─────────────────────────────────────

def test_ny_at_the_shipped_default_falls_back_to_nys_own_exemption():
    assert resolved_state_estate_exemption('New York', 4_000_000.0) == EXEMPT


def test_ny_with_an_explicit_non_default_value_is_honored():
    assert resolved_state_estate_exemption('New York', 3_000_000.0) == 3_000_000.0


def test_illinois_at_the_shipped_default_is_unaffected():
    # Illinois's own real exemption IS $4M -- the shipped default already
    # matches, and must never fall back to trying to "correct" it.
    assert resolved_state_estate_exemption('Illinois', 4_000_000.0) == 4_000_000.0


def test_an_unrecognized_state_at_the_default_just_keeps_the_configured_value():
    assert resolved_state_estate_exemption('Nowhereland', 4_000_000.0) == 4_000_000.0
