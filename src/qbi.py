"""Section 199A qualified business income (QBI) deduction with its statutory limits (FIN-001).

Pure function, one qualified trade or business. Layers, in the order Form 8995-A applies them:

1. tentative deduction = 20% of QBI;
2. above the taxable-income threshold the deduction is limited to the greater of 50% of W-2 wages
   or 25% of wages + 2.5% of UBIA, phased in over a range (150k joint / 75k other from 2026,
   100k / 50k before); a specified service trade or business (SSTB) instead has its QBI, wages
   and UBIA scaled by the applicable percentage and reaches zero at the top of the range;
3. the overall cap of 20% of (taxable income before QBI minus net capital gain, which includes
   qualified dividends);
4. OBBBA minimum deduction from 2026: at least ``min_deduction`` ($400) when active QBI is at least
   ``min_income`` ($1,000), never more than taxable income before the QBI deduction.

Rule values come from dated rows in reference_src/tax_law_v10.json (Rev. Proc. 2025-32 sec. 4.26).
"""
from __future__ import annotations


def qbi_deduction(
    qbi: float,
    w2_wages: float,
    ubia: float,
    sstb: bool,
    taxable_before_qbi: float,
    net_capital_gain: float,
    threshold: float,
    phase_in_width: float,
    min_deduction: float = 0.0,
    min_income: float = 0.0,
) -> float:
    qbi = max(0.0, float(qbi or 0.0))
    if qbi <= 0.0:
        return 0.0
    ti = max(0.0, float(taxable_before_qbi or 0.0))
    wages = max(0.0, float(w2_wages or 0.0))
    prop = max(0.0, float(ubia or 0.0))

    pct = 0.0 if ti <= threshold else (1.0 if phase_in_width <= 0 else min(1.0, (ti - threshold) / phase_in_width))
    if sstb and pct > 0.0:
        applicable = 1.0 - pct
        qbi, wages, prop = qbi * applicable, wages * applicable, prop * applicable
    active_qbi = qbi   # an SSTB's QBI counts only for its applicable (not phased-out) share
    tentative = 0.20 * qbi
    wage_limit = max(0.50 * wages, 0.25 * wages + 0.025 * prop)
    if pct <= 0.0 or tentative <= wage_limit:
        ded = tentative
    else:
        ded = tentative - pct * (tentative - wage_limit)
    overall_cap = 0.20 * max(0.0, ti - max(0.0, float(net_capital_gain or 0.0)))
    ded = min(ded, overall_cap)
    if min_deduction > 0.0 and active_qbi >= min_income:
        ded = max(ded, min(min_deduction, ti))
    return max(0.0, ded)
