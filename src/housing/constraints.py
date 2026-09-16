"""Hard filters applied to a candidate before it is ever run, plus the
informational §121 flag. Pure functions over a candidate -- no engine, no
config.

Family presence became ZIP proximity on 2026-09-16 (design §6.4). The previous
state-level rule passed any candidate in the right state regardless of
distance, which is not what "near family" means in a state the size of Texas.
"""
from __future__ import annotations

from .models import FamilyPresence, HousingCandidate, Location
from .zip_screen.geo import haversine_miles


def residence_timeline(cand: HousingCandidate):
    """Ordered ``(start_year, end_year_inclusive, location, is_rental)`` legs
    covering the plan horizon for the PRIMARY residence.

    ``location`` is ``None`` for the opening leg: the household is still at its
    current home, whose ZIP the optimizer does not model. A concurrent move 2
    is excluded here and checked separately -- it is a second simultaneous
    residence, not a relocation.
    """
    m1 = cand.move1
    legs = [(1, m1.acquisition_year - 1, None, False)]
    m2 = cand.move2
    if m2 is not None and m2.mode != 'concurrent':
        legs.append((m1.acquisition_year, m2.acquisition_year - 1,
                     m1.location, m1.action == 'rent'))
        legs.append((m2.acquisition_year, 9999, m2.location, m2.action == 'rent'))
    else:
        legs.append((m1.acquisition_year, 9999, m1.location, m1.action == 'rent'))
    return legs


def _within(loc: Location | None, presence: FamilyPresence,
            coords: dict[str, tuple[float, float]]) -> bool:
    if loc is None:
        # Still at the current home. The plan's existing residence is taken to
        # satisfy presence: the user is asking where they should MOVE to stay
        # near family, not whether they live there now.
        return True
    family = coords.get(presence.zip_code)
    here = coords.get(loc.zip_code or '')
    if family is None or here is None:
        return False
    return haversine_miles(family[0], family[1], here[0], here[1]) <= presence.radius_miles


def family_presence_ok(
    cand: HousingCandidate, presence: FamilyPresence | None,
    coords: dict[str, tuple[float, float]],
) -> tuple[bool, bool]:
    """Returns ``(covered, via_rental)``.

    ``covered`` is False if, in any year of the presence window, the household's
    residence is farther from the family ZIP than the radius. A concurrent
    second residence satisfies a year on its own -- representing presence in
    two places at once is the point of concurrent mode.
    """
    if presence is None:
        return True, False
    legs = residence_timeline(cand)
    m2 = cand.move2
    concurrent = m2 is not None and m2.mode == 'concurrent'
    via_rental = False
    for year in range(presence.from_year, presence.through_year + 1):
        leg = next((l for l in legs if l[0] <= year <= l[1]), None)
        primary_match = leg is not None and _within(leg[2], presence, coords)
        primary_rental = bool(leg and leg[3])
        concurrent_match = (
            concurrent and year >= m2.acquisition_year
            and _within(m2.location, presence, coords)
        )
        if not (primary_match or concurrent_match):
            return False, False
        if (primary_match and primary_rental) or (concurrent_match and m2.action == 'rent'):
            via_rental = True
    return True, via_rental


def sec121_exclusion_flag(acquisition_year: int | None, sale_year: int | None) -> bool:
    """Informational-only two-of-five-year ownership/use flag: True means the
    exclusion would likely NOT survive the real IRS test, even though the
    engine's computed dollar figures still assume it applies in full.
    ``acquisition_year is None`` (nothing purchased) or ``sale_year is None``
    (the home is kept, never sold) both mean there is nothing to flag.
    """
    if acquisition_year is None or sale_year is None:
        return False
    return (sale_year - acquisition_year) < 2
