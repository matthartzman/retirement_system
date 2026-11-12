"""Social Security factor helpers lifted out of run_deterministic_projection_stage (ARC-001).

Pure functions (no plan config); behaviour is identical to the former closures.
"""
from __future__ import annotations


def ss_first_claim_year_month_fraction(year, claim_year, dob_month):
    """Fraction of `year` (0.0-1.0) Social Security is actually payable.

    Wave 5 item W5-3 (finding N3, 2026-09-08 explicit direction):
    Social Security pays in ARREARS -- the check for a given month's
    entitlement arrives the following month -- unlike Medicare coverage
    (a genuine coverage-period concept correctly modeled as starting the
    1st of the entitlement month by _medicare_month_fraction). Reusing
    that same in-advance formula here was the root cause N3 identified:
    an entitlement in month M pays (12-M) months that calendar year, not
    (12-(M-1)) -- e.g. an August claim pays September-December (4
    months), not August-December (5). A December claim pays zero SS
    cash that calendar year (first check arrives the following January).
    Only the claim YEAR itself is ever partial; every later year is a
    full 12 months.
    """
    if year != claim_year:
        return 1.0
    try:
        m = int(dob_month) if dob_month else 1
    except Exception:
        m = 1
    m = min(max(m, 1), 12)
    return (12 - m) / 12.0


def fra_for_birth_year(dob_year, fra_override=None):
    if fra_override and float(fra_override) > 0:
        return float(fra_override)
    dob_year = int(dob_year or 1960)
    if dob_year >= 1960:
        return 67.0
    if dob_year <= 1937:
        return 65.0
    if dob_year <= 1942:
        return 65.0 + (dob_year - 1937) * (2.0 / 12.0)
    if dob_year <= 1954:
        return 66.0
    return 66.0 + (dob_year - 1954) * (2.0 / 12.0)

def ss_claim_factor(claim_age, dob_year, fra_override=None):
    # SSA reduction/credit factors relative to PIA at FRA.
    fra = fra_for_birth_year(dob_year, fra_override)
    months = int(round((float(claim_age or fra) - fra) * 12))
    if months >= 0:
        return 1.0 + months * (0.08 / 12.0)
    early = abs(months)
    first36 = min(36, early) * (5.0 / 900.0)
    extra = max(0, early - 36) * (5.0 / 1200.0)
    return max(0.0, 1.0 - first36 - extra)

def ss_benefit_from_age70(monthly_at_70, claim_age, dob_year, fra_override=None):
    f70 = ss_claim_factor(70, dob_year, fra_override) or 1.0
    return float(monthly_at_70 or 0.0) * (ss_claim_factor(claim_age, dob_year, fra_override) / f70)

def ss_spousal_excess_factor(start_age, dob_year, fra_override=None):
    # Reduction schedule for the EXCESS SPOUSAL benefit, which differs from a
    # worker's own retirement reduction (ss_claim_factor).  Per SSA the
    # excess spousal amount is reduced 25/36 of 1% per month for the first 36
    # months claimed before FRA, then 5/12 of 1% per month for any months
    # beyond 36.  Delayed retirement credits do NOT apply to the spousal
    # excess: claiming after FRA never grows it past the FRA-level amount, so
    # the factor is capped at 1.0.  `start_age` is the claimant's age when the
    # spousal benefit first becomes payable (the later of their own filing and
    # the worker's filing), relative to the claimant's own FRA.
    fra = fra_for_birth_year(dob_year, fra_override)
    months = int(round((float(start_age or fra) - fra) * 12))
    if months >= 0:
        return 1.0
    early = abs(months)
    first36 = min(36, early) * (25.0 / 3600.0)
    extra = max(0, early - 36) * (5.0 / 1200.0)
    return max(0.0, 1.0 - first36 - extra)

def ss_survivor_reduction_factor(age_at_start, dob_year, fra_override=None):
    """Survivor-benefit early-claim reduction, FIN-001 (system review
    2026-09-25). Distinct from ss_claim_factor (a worker's own
    retirement reduction/delayed-credit schedule, which runs from age 62
    to beyond FRA and grants delayed credits) and from
    ss_spousal_excess_factor (the excess-spousal top-up schedule): SSA
    reduces a survivor benefit linearly from 71.5% of the full amount at
    exactly age 60 up to 100% at the survivor's own FRA, and -- unlike a
    worker's own benefit -- grants no delayed credit for waiting past
    FRA to start it (capped at 1.0). The true SSA table is not perfectly
    linear between 60 and FRA; this linear approximation is within a
    fraction of a percent of the published table across that span and is
    adopted here in the same spirit as fra_for_birth_year's own
    piecewise-linear FRA formula.
    """
    fra = fra_for_birth_year(dob_year, fra_override)
    age_at_start = float(age_at_start or fra)
    if age_at_start >= fra:
        return 1.0
    if age_at_start <= 60.0:
        return 0.715
    span = fra - 60.0
    if span <= 0:
        return 1.0
    frac_early = (fra - age_at_start) / span
    return max(0.715, 1.0 - 0.285 * frac_early)
