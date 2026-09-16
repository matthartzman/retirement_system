"""Family presence as ZIP proximity, not state residence (design §6.4)."""
import pytest

from src.housing.constraints import family_presence_ok
from src.housing.models import (
    FamilyPresence,
    HousingCandidate,
    Location,
    Move,
    OriginalHome,
)

pytestmark = pytest.mark.unit

# 60521 Hinsdale IL; 60540 Naperville ~9 mi west; 80014 Aurora CO ~1000 mi west.
COORDS = {
    '60521': (41.80, -87.93),
    '60540': (41.77, -88.15),
    '80014': (39.68, -104.83),
}


def _cand(zip1, year1=2030, action1='buy', zip2=None, year2=None,
          action2='buy', mode2='sequential'):
    moves = [Move(index=1, acquisition_year=year1, action=action1,
                  location=Location(state='IL', zip_code=zip1))]
    if zip2:
        moves.append(Move(index=2, acquisition_year=year2, action=action2,
                          location=Location(state='CO', zip_code=zip2), mode=mode2))
    return HousingCandidate(
        original_home=OriginalHome(disposition='sell', sale_year=2029),
        moves=tuple(moves),
    )


def _presence(radius=25, from_year=2030, through_year=2040):
    return FamilyPresence(zip_code='60521', radius_miles=radius,
                          from_year=from_year, through_year=through_year)


def test_a_nearby_zip_satisfies_presence():
    ok, _ = family_presence_ok(_cand('60540'), _presence(radius=25), COORDS)
    assert ok is True


def test_a_distant_zip_fails_presence():
    ok, _ = family_presence_ok(_cand('80014'), _presence(radius=25), COORDS)
    assert ok is False


def test_the_radius_is_what_decides_not_the_state():
    """60540 is in the same state as the family ZIP but must still be inside
    the radius -- the old state-level rule would have passed it at any
    distance."""
    ok, _ = family_presence_ok(_cand('60540'), _presence(radius=5), COORDS)
    assert ok is False


def test_presence_is_only_checked_inside_the_declared_years():
    cand = _cand('80014', year1=2045)
    ok, _ = family_presence_ok(cand, _presence(from_year=2030, through_year=2040), COORDS)
    assert ok is True, 'the household is still at its original home through 2040'


def test_moving_away_mid_window_fails():
    cand = _cand('60540', year1=2030, zip2='80014', year2=2035)
    ok, _ = family_presence_ok(cand, _presence(from_year=2030, through_year=2040), COORDS)
    assert ok is False


def test_a_concurrent_second_residence_satisfies_presence():
    cand = _cand('80014', year1=2030, zip2='60540', year2=2030, mode2='concurrent')
    ok, _ = family_presence_ok(cand, _presence(), COORDS)
    assert ok is True


def test_via_rental_is_reported_when_a_rental_is_what_covers_the_window():
    cand = _cand('60540', action1='rent')
    ok, via_rental = family_presence_ok(cand, _presence(), COORDS)
    assert ok is True
    assert via_rental is True


def test_no_presence_requirement_passes_everything():
    ok, via_rental = family_presence_ok(_cand('80014'), None, COORDS)
    assert (ok, via_rental) == (True, False)


def test_an_unknown_zip_fails_closed_rather_than_passing_silently():
    """A ZIP missing from the coordinate table cannot be shown to be near
    family, and passing it would let an unscreened candidate through a filter
    the user asked for."""
    ok, _ = family_presence_ok(_cand('99999'), _presence(), COORDS)
    assert ok is False
