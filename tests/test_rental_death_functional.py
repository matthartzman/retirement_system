"""H5: death handling (RENTAL_TAX_RULES.md section 12): step-up, depreciation restart, 469(g)(2) release."""
from __future__ import annotations

import pytest

from src.projection_stages import rental_property as rp
from tests import rental_fixtures as rf

DEATHS = {"h_death_yr": 2034, "w_death_yr": 2040, "household_size": 2}
PROP = dict(rf.PROFITABLE, loan_balance=0, owner="joint")  # no loan: keeps the cash side simple


def _book(owner="joint", plan=None, **extra):
    row = dict(PROP, owner=owner, **extra)
    c = rf.rental_config(rf.RentalCase([row], plan={**DEATHS, **(plan or {})}))
    book = rp.rental_book_for(c)
    return c, book, book.specs[0]


def test_first_death_steps_up_the_decedents_half_and_restarts_its_depreciation():
    _c, book, s = _book()
    (e1, e2), segs = book._walk(s)
    assert (e1.year, e1.fraction) == (2034, 0.5) and (e2.year, e2.fraction) == (2040, 1.0)
    assert e1.delta_basis == pytest.approx(0.5 * (e1.fmv - e1.adjusted_basis))
    improvements = sum(a for y, _m, a in s.improvements if y <= 2034)
    assert e1.basis_after == pytest.approx(0.5 * (s.cost_basis + improvements) + 0.5 * e1.fmv)
    # the decedent's half of the original building leaves in 2034; its stepped-up half starts in 2034 (land excluded)
    assert any(g.placed_year == s.placed_year and g.off_year == 2034 for g in segs)
    stepped = [g for g in segs if g.placed_year == 2034 and g.placed_month == 7 and g.off_year == 2040]
    assert [g.basis for g in stepped] == [pytest.approx(0.5 * e1.fmv * (1 - s.land_share))]
    # between the deaths: survivor half + stepped half depreciate; the decedent half does not
    recovery = book.constants(2036, "MFJ").recovery_years
    live = [g for g in segs if g.placed_year <= 2036 and (g.off_year is None or g.off_year >= 2036)]
    dep = book._depreciation(s, 2036, recovery, None)
    assert dep == pytest.approx(sum(rp.annual_depreciation(g.basis, g.placed_year, g.placed_month, 2036, recovery)
                                    for g in live))
    assert dep != pytest.approx(rp.property_depreciation(s.assets(), 2036, recovery))
    # a later sale sees the stepped basis and only the depreciation still on the books
    assert book._sale_basis(s, 2036)[0] == pytest.approx(e1.basis_after)
    assert book._accumulated(s, 2036, recovery, None) < rp.property_accumulated_depreciation(s.assets(), 2036, recovery)


def test_no_owner_no_death_handling():
    c = rf.rental_config(rf.RentalCase([dict(rf.PROFITABLE, loan_balance=0)], plan=DEATHS))
    book = rp.rental_book_for(c)
    assert book._walk(book.specs[0])[0] == ()


@pytest.mark.parametrize("suspended_over_step, expect_allowed", [(-1.0, 0.0), (0.0, 0.0)])
def test_losses_below_the_step_up_are_lost(suspended_over_step, expect_allowed):  # D2
    _c, book, s = _book()
    st = book._state[s.name]
    delta = book._walk(s)[0][0].delta_basis
    assert delta > 0
    st.suspended = (delta / 0.5 * 0.5) * 2 + suspended_over_step  # decedent share (x0.5) = delta + something <= delta
    out = book._death_in(s, st, 2034)
    assert out["death_suspended_removed"] == pytest.approx(st.suspended * 0.5)
    assert out["death_loss_released"] == pytest.approx(max(0.0, st.suspended * 0.5 - delta))


def test_losses_above_the_step_up_are_released_on_the_final_return():  # D3 / D5
    _c, book, s = _book(owner="member_1")  # sole owner who dies first: fraction 1.0
    delta = book._walk(s)[0][0].delta_basis
    st = book._state[s.name]
    st.suspended = max(0.0, delta) + 70_000
    out = book._death_in(s, st, 2034)
    assert out["death_suspended_removed"] == pytest.approx(st.suspended)
    assert out["death_loss_released"] == pytest.approx(70_000)
    assert out["death_loss_lost"] == pytest.approx(max(0.0, delta))


def test_step_down_releases_the_whole_decedent_share():  # D6
    _c, book, s = _book(plan={}, current_value=100_000, appreciation=0.0)
    e1 = book._walk(s)[0][0]
    assert e1.delta_basis < 0
    st = book._state[s.name]
    st.suspended = 30_000
    out = book._death_in(s, st, 2034)
    assert out["death_loss_released"] == pytest.approx(15_000) and out["death_loss_lost"] == pytest.approx(0)


def test_community_property_steps_up_both_halves():  # D7
    _c, book, s = _book(plan={"basis_step_up_property_regime": "COMMUNITY_PROPERTY"})
    assert book._walk(s)[0][0].fraction == 1.0


def test_sole_owner_who_survives_has_no_first_death_event():
    _c, book, s = _book(owner="member_2")  # member 1 dies first
    assert [e.year for e in book._walk(s)[0]] == [2040]


def test_death_year_row_fields_and_unset_owner_unchanged_in_the_engine():
    rows = rf.by_year(rf.project(rf.rental_config(rf.RentalCase(
        [dict(PROP, owner="member_1", prior_suspended_loss=200_000, active_participation=False)], plan=DEATHS))))
    base = rf.by_year(rf.project(rf.rental_config(rf.RentalCase(
        [dict(rf.PROFITABLE, loan_balance=0, prior_suspended_loss=200_000, active_participation=False)], plan=DEATHS))))
    p = rows[2034]["rental_by_property"][0]
    assert p["death_suspended_removed"] > 0
    assert p.get("death_loss_released", 0.0) == pytest.approx(max(0.0, p["death_suspended_removed"] - max(0.0, p["death_basis_change"])))
    assert rows[2034].get("rental_death_loss_released", 0.0) == pytest.approx(p.get("death_loss_released", 0.0))
    assert "rental_death_basis_change" not in base[2034]
    assert "rental_death_basis_change" not in rows[2033]


def test_converted_home_estate_year_releases_the_excess_over_the_step_up():
    conv = dict(rf.CONVERTED_HOME, owner="joint", prior_suspended_loss=400_000, active_participation=False)
    rows = rf.by_year(rf.project(rf.rental_config(rf.RentalCase([conv], plan={**DEATHS, "home_sale_yr": 0}))))
    p = rows[2040]["rental_by_property"][0]
    assert p["death_suspended_removed"] > 0
    assert p.get("death_loss_released", 0.0) == pytest.approx(
        max(0.0, p["death_suspended_removed"] - max(0.0, p["death_basis_change"])))
    off = rf.by_year(rf.project(rf.rental_config(rf.RentalCase(
        [dict(conv, owner="")], plan={**DEATHS, "home_sale_yr": 0}))))
    assert "rental_death_basis_change" not in off[2040]
