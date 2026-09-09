from __future__ import annotations

from typing import Any, Callable, NamedTuple


class DafCarryforwardMakeupResult(NamedTuple):
    """Everything this sub-stage produces that code outside it still needs.

    ``daf_deduction_carryforward`` is cross-year state (seeded once in
    setup, threaded through every year) -- the caller must reassign its
    own local from it on every call, exactly like every other cross-year
    local in this decomposition (Stage 3's ``cst_balance``, Stage 9's own
    ``daf_deduction_carryforward`` before this pass ever touches it, ...).
    Every other field is this-year-only but is read again by the
    still-inline sub-stages that follow (#9, #10, #11) and, for
    ``fed_tax``/``taxable_inc``/``total_tax``/``gap``, potentially by
    sub-stage #6's already-executed recombination logic upstream -- so
    even though this pass runs *after* that recombination, its own
    updates must still come back explicitly rather than being assumed to
    persist via plain scalar reassignment (which does not propagate out
    of a function call in Python).
    """
    gap: float
    fed_tax: float
    taxable_inc: float
    total_tax: float
    char: float
    item_ded: float
    ded: float
    daf_deduction_yr: float
    daf_deduction_carryforward: list


def apply_daf_carryforward_makeup(
    row: dict[str, Any],
    *,
    year: int,
    agi: float,
    daf_agi_limit_pct: float,
    daf_agi_limit: float,
    daf_deduction_carryforward: list,
    item_ded: float,
    std_ded: float,
    qbi_ded: float,
    qbi_elig: bool,
    fed_tax: float,
    taxable_inc: float,
    total_tax: float,
    gap: float,
    char: float,
    ded: float,
    daf_deduction_yr: float,
    total_spend_need: float,
    other_cash_need_yr: float,
    filing: str,
    brk_inf: Any,
    compute_fed_tax_fn: Callable[[float, int, str, Any], float],
) -> DafCarryforwardMakeupResult:
    """Withdrawal Cascade sub-stage #8 (design doc addendum): the DAF
    carryforward make-up pass against converged AGI (lines ~1630-1699,
    Item 4.2 follow-up).

    Documented as the mirror image of the still-inline sub-stage #3
    (HSA-reimbursement medical-deduction correction) -- "same shape,
    opposite sign". It only ever LOWERS tax, which is why (unlike
    sub-stage #3) it is safe to sit wherever it does in the cascade: a
    shrinking gap needs no funding, so there is no ordering-invariant risk
    analogous to the one guarding sub-stage #3's position.

    `agi` above is a first-pass estimate computed before the elective-
    withdrawal sizing loop (Priority 3/4b) ran; by this point in the
    cascade it has converged. For a retiree with no guaranteed income yet
    (pre-SS claim, pre-RMD, living entirely off elective withdrawals),
    first-pass agi can read near zero while this converged agi is
    substantial, understating the DAF 60%/30%-of-AGI limit and risking
    real carryforward capacity lapsing unused after 5 years. salt/char/
    mortgage-interest absorb the same first-pass approximation harmlessly
    (one year of rounding, no lasting effect); DAF's multi-year
    carryforward is the one case that can cost a taxpayer a deduction
    permanently, so it alone gets a make-up pass here. Scoped narrowly to
    avoid touching salt/mortgage interest (both stay at their first-pass
    values) and to only ever recognize *more* deduction (agi only rises
    across the cascade, never falls), never less.

    ``row`` is mutated in place, as elsewhere in this stage decomposition.
    """
    # A household with a real no-guaranteed-income gap year -- the exact
    # case this exists for -- typically has first-pass salt near zero too
    # (salt is sized off the same first-pass agi), so first-pass item_ded
    # is often already below std_ded and the household appears not to be
    # itemizing at all. Gating this purely on "was already itemizing at
    # first pass" would silently exclude that case. Instead, re-evaluate
    # std-vs-itemized once against the corrected char figure: salt and
    # mort_interest_yr are not recomputed (still first-pass values, left
    # untouched as designed), but whether the now-larger item_ded clears
    # std_ded is allowed to flip as a direct, mechanical consequence of
    # the corrected DAF number -- that comparison can't be avoided without
    # discarding the correction itself.
    if daf_deduction_carryforward:
        _daf_final_limit = max(0.0, agi) * daf_agi_limit_pct
        _daf_extra_room = max(0.0, _daf_final_limit - daf_agi_limit)
        if _daf_extra_room > 1e-6:
            _daf_unused_pool = sum(amt for _yr, amt in daf_deduction_carryforward)
            _daf_extra_candidate = min(_daf_extra_room, _daf_unused_pool)
            _candidate_item_ded = item_ded + _daf_extra_candidate
            if _daf_extra_candidate > 1e-6 and _candidate_item_ded > std_ded:
                _daf_extra_used = _daf_extra_candidate
                _new_ded = _candidate_item_ded + (qbi_ded if qbi_elig else 0.0)
                _new_taxable_inc = max(0.0, agi - _new_ded)
                _new_fed_tax = compute_fed_tax_fn(_new_taxable_inc, year, filing, brk_inf)
                _fed_tax_savings = max(0.0, fed_tax - _new_fed_tax)
                fed_tax = _new_fed_tax
                taxable_inc = _new_taxable_inc
                total_tax -= _fed_tax_savings
                gap -= _fed_tax_savings
                char += _daf_extra_used
                row['charitable_deduction_yr'] = char
                item_ded = _candidate_item_ded
                ded = _new_ded
                daf_deduction_yr += _daf_extra_used
                _daf_remaining = _daf_extra_used
                _daf_new_cf = []
                for _daf_origin_year, _daf_amt in daf_deduction_carryforward:
                    _daf_used = min(_daf_amt, _daf_remaining)
                    _daf_remaining -= _daf_used
                    _daf_leftover = _daf_amt - _daf_used
                    if _daf_leftover > 1e-6:
                        _daf_new_cf.append([_daf_origin_year, _daf_leftover])
                daf_deduction_carryforward = _daf_new_cf
                row['daf_deduction_yr'] = daf_deduction_yr
                row['daf_deduction_carryforward'] = sum(amt for _yr, amt in daf_deduction_carryforward)
                row['taxable_inc'] = taxable_inc
                row['fed_tax'] = fed_tax
                row['total_tax'] = total_tax
                row['net_income'] = row.get('gross_income', agi) - total_tax
                row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

    return DafCarryforwardMakeupResult(
        gap=gap,
        fed_tax=fed_tax,
        taxable_inc=taxable_inc,
        total_tax=total_tax,
        char=char,
        item_ded=item_ded,
        ded=ded,
        daf_deduction_yr=daf_deduction_yr,
        daf_deduction_carryforward=daf_deduction_carryforward,
    )
