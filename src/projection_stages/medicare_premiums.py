"""Medicare / pre-65 premium and SEHI-source helpers lifted out of run_deterministic_projection_stage (ARC-001).

Pure functions of the plan config ``c``; behaviour is identical to the former closures.
"""
from __future__ import annotations

from .index_paths import path_factor


def medicare_month_fraction(dob_yr, dob_month, year):
    """Fraction of `year` (0.0-1.0) a person is Medicare Part B/D enrolled.

    Convention: Medicare eligibility begins the first of the calendar
    month in which a person turns 65 (standard CMS enrollment rule). Age
    follows the engine's existing integer convention (year - dob_yr), so
    this only ever prorates the single transition year where that age
    first equals 65 — 0.0 in all earlier years, 1.0 in all later years,
    and (12 - (birth_month - 1)) / 12 in the turn-65 year itself.
    """
    try:
        age = int(year) - int(dob_yr)
    except Exception:
        return 0.0
    if age < 65:
        return 0.0
    if age > 65:
        return 1.0
    try:
        m = int(dob_month) if dob_month else 1
    except Exception:
        m = 1
    m = min(max(m, 1), 12)
    return (12 - (m - 1)) / 12.0

def wellness_premium_for_age(c, age, year, dob_month=1):
    """Return the annual per-person premium used for SEHI in this year.

    There is intentionally no standalone "health insurance premiums"
    input.  Before age 65, use Pre-65 Healthcare Premium; at 65+ use
    Medicare Part B + Part D + Part G costs. In the calendar year a
    person turns 65, both are prorated by month via
    `medicare_month_fraction` (Medicare starts the 1st of the birth
    month) instead of switching on a hard binary age gate.
    """
    try:
        age = float(age)
    except Exception:
        age = 0.0
    dob_yr = year - age
    medicare_frac = medicare_month_fraction(dob_yr, dob_month, year)
    pre65_frac = 1.0 - medicare_frac
    bridge = float(c.get('bridge_premium', 0.0) or 0.0) * path_factor(c, 'medical_index_by_year', c.get('med_inf', c['inf']), year) * pre65_frac
    part_b = float(c.get('partb', 0.0) or 0.0) * 12 * path_factor(c, 'medical_index_by_year', c.get('med_inf', c['inf']), year) * medicare_frac
    part_d = float(c.get('partd', 0.0) or 0.0) * 12 * path_factor(c, 'partd_index_by_year', c.get('partd_inf', c.get('med_inf', c['inf'])), year) * medicare_frac
    part_g = float(c.get('partg', 0.0) or 0.0) * 12 * path_factor(c, 'medical_index_by_year', c.get('med_inf', c['inf']), year) * medicare_frac
    return bridge + part_b + part_d + part_g

def sehi_deduction_source_amount(c, year, h_age, w_age, h_alive=True, w_alive=True):
    _sehi_override = c.get('sehi_user_override')
    if _sehi_override is not None:
        return max(0.0, float(_sehi_override))
    if c.get('sehi_derived_from_wellness', True):
        total = 0.0
        if h_alive:
            total += wellness_premium_for_age(c, h_age, year, c.get('h_dob_month'))
        if w_alive:
            total += wellness_premium_for_age(c, w_age, year, c.get('w_dob_month'))
        return max(0.0, total)
    return max(0.0, float(c.get('sehi', 0.0) or 0.0))
