"""Hard filters applied to a candidate before it is ever run (§3.1.2/
§3.2.2), plus the informational §121 flag. Pure functions over a candidate
-- no engine, no config.
"""
from __future__ import annotations

from .models import FamilyPresence, HousingCandidate

def _location_timeline(base_state: str, cand: HousingCandidate) -> list[tuple[int, int, str, bool]]:
    """Ordered ``(start_year, end_year_inclusive, state, is_rental)`` legs
    covering the whole plan horizon for this candidate."""
    move1_start = cand.sale_year if cand.purchase_year is None else cand.purchase_year
    move1_is_rental = cand.purchase_year is None
    legs = [(1, move1_start - 1, base_state, False)]
    if cand.is_two_move:
        move2_start = cand.sale_year_2 if cand.purchase_year_2 is None else cand.purchase_year_2
        move2_is_rental = cand.purchase_year_2 is None
        legs.append((move1_start, move2_start - 1, cand.location_1.state, move1_is_rental))
        legs.append((move2_start, 9999, cand.location_2.state, move2_is_rental))
    else:
        legs.append((move1_start, 9999, cand.location_1.state, move1_is_rental))
    return legs


def family_presence_ok(base_state: str, cand: HousingCandidate, presence: FamilyPresence | None) -> tuple[bool, bool]:
    """Hard filter (§3.1.2/§3.2.2): returns ``(covered, via_rental)``.
    ``covered`` is False if any year in the presence window lacks an
    owned-or-rented residence in ``presence.region``. ``via_rental`` is True
    when a rent leg (rather than the current home or an owned purchase) is
    what satisfies coverage for at least one of those years.
    """
    if presence is None:
        return True, False
    legs = _location_timeline(base_state, cand)
    via_rental = False
    for year in range(presence.start_year, presence.end_year + 1):
        leg = next((l for l in legs if l[0] <= year <= l[1]), None)
        if leg is None or leg[2] != presence.region:
            return False, False
        if leg[3]:
            via_rental = True
    return True, via_rental


def sec121_exclusion_flag(purchase_year: int | None, sale_year: int) -> bool:
    """Informational-only two-of-five-year ownership/use flag (see module
    docstring): True means the exclusion would likely NOT survive the real
    IRS test, even though the engine's (and this package's) computed dollar
    figures still assume it applies in full. ``purchase_year is None`` means
    there is nothing to flag (nothing was purchased under this leg).
    """
    if purchase_year is None:
        return False
    return (sale_year - purchase_year) < 2
