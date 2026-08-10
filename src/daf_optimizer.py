"""DAF (donor-advised fund) contribution recommendation engine (#270).

Recommends the largest DAF contribution the household can make in a given
year without exceeding the IRS AGI-based deduction ceiling -- 60% of AGI for
a cash contribution, 30% of AGI for appreciated-securities -- and surfaces
the federal bracket, IRMAA tier, and NIIT-threshold context around that
AGI so the advisor can judge whether "maximize the contribution" is actually
the right call this year (e.g. a contribution that only partially uses
carryforward in a low-income year may be worth deferring to a high-income
year instead).

This is a recommendation only: it never mutates the plan. The UI applies it
by writing to the existing daf_amount/daf_contribution_is_appreciated fields,
which the projection engine already reads (deterministic_engine.py).
"""
from __future__ import annotations

from typing import Any, Mapping

from . import core as _core
from . import taxes as _td


def _agi_for_year(c: Mapping[str, Any], rows: list[dict] | None, year: int) -> float:
    row = next((r for r in (rows or []) if r.get('year') == year), None)
    if row and float(row.get('agi', 0) or 0) > 0:
        return float(row['agi'])
    # No projection row available (e.g. called before a build) -- fall back to
    # a rough current-year estimate from top-level plan inputs.
    est = (
        float(c.get('earned', 0) or 0)
        + float(c.get('h_ss', 0) or 0) + float(c.get('w_ss', 0) or 0)
        + float(c.get('pension', 0) or 0)
    )
    return max(0.0, est)


def recommend_daf_contribution(c: Mapping[str, Any], rows: list[dict] | None = None,
                                *, year: int | None = None,
                                appreciated: bool = False) -> dict[str, Any]:
    """Return a recommended DAF contribution for ``year`` (default:
    c['daf_year'] or plan_start), maximizing within the IRS AGI ceiling.

    ``appreciated`` selects the 30%-of-AGI (appreciated holdings) limit
    instead of the 60%-of-AGI (cash) limit -- pass whichever funding method
    the user has selected in the UI.
    """
    plan_start = int(c.get('plan_start', 2024) or 2024)
    year = int(year or c.get('daf_year') or plan_start)
    filing = str(c.get('filing_status', 'MFJ') or 'MFJ')
    inflator = float(c.get('irmaa_inflator', 0.02) or 0.02)

    agi = _agi_for_year(c, rows, year)
    agi_limit_pct = 0.30 if appreciated else 0.60
    agi_limit = round(agi * agi_limit_pct, -2)  # nearest $100

    # Informational context -- these thresholds are on (M)AGI, which an
    # itemized charitable deduction does NOT reduce (the deduction lowers
    # taxable income, not AGI), so a bigger DAF gift does not itself change
    # IRMAA/NIIT exposure. They still matter to the "how much to give"
    # decision because a higher-AGI year has both a higher DAF ceiling AND a
    # higher IRMAA tier / more NIIT-taxed investment income -- useful
    # context for choosing WHICH year to bunch a large gift into.
    tier_now = _core.irmaa_tier(agi, year, plan_start, inflator=inflator, filing=filing)
    niit_threshold = float(_td.NIIT_THRESHOLD.get(filing, 250000) or 250000)
    over_niit_threshold = agi > niit_threshold

    fed_brackets = None
    fed_bracket_top_rate = None
    try:
        brk_inf = float(c.get('brk_inf', c.get('inf', 0.0)) or 0.0)
        fed_tax = _core.compute_fed_tax(max(0.0, agi), year, filing, brk_inf)
        fed_bracket_top_rate = round((fed_tax / agi) * 100, 1) if agi > 0 else 0.0
    except Exception:
        pass

    notes = [
        f"AGI ceiling: {agi_limit_pct:.0%} of estimated {year} AGI (${agi:,.0f}) = ${agi_limit:,.0f}.",
    ]
    if tier_now > 0:
        notes.append(f"Household is currently in IRMAA surcharge tier {tier_now} at this AGI -- a charitable deduction does not reduce IRMAA-relevant MAGI.")
    if over_niit_threshold:
        notes.append(f"AGI is above the {filing} NIIT threshold (${niit_threshold:,.0f}); the deduction does not reduce NIIT-taxed investment income either.")
    if fed_bracket_top_rate is not None:
        notes.append(f"Effective federal rate on this AGI is approximately {fed_bracket_top_rate:.1f}% -- higher-bracket years generally get more tax value per dollar donated.")
    notes.append("Amount that exceeds this year's usable deduction (this year's remaining AGI room after other giving) carries forward up to 5 years.")

    return {
        "year": year,
        "agi": round(agi, 2),
        "appreciated": bool(appreciated),
        "agi_limit_pct": agi_limit_pct,
        "recommended_amount": agi_limit,
        "irmaa_tier": tier_now,
        "over_niit_threshold": over_niit_threshold,
        "niit_threshold": niit_threshold,
        "federal_effective_rate_pct": fed_bracket_top_rate,
        "notes": notes,
    }


__all__ = ["recommend_daf_contribution"]
