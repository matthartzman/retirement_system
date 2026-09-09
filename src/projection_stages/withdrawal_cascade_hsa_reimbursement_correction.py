from __future__ import annotations

from typing import Any, Callable, NamedTuple


class HsaReimbursementCorrectionResult(NamedTuple):
    """Everything this sub-stage produces that code outside it still needs.

    ``gap`` is the cascade's central threading variable, read by every
    sub-stage from here on (Priority 3 next). ``fed_tax``/``taxable_inc``/
    ``total_tax_pre_niit``/``item_ded``/``ded`` are all read again by the
    still-inline sub-stages that follow (Priority 3's IRA true-up reads
    ``fed_tax``/``taxable_inc``/``total_tax_pre_niit`` directly; the DAF
    carryforward make-up pass later reads ``item_ded``/``ded``) -- all five
    are accepted as inputs too and simply passed back through unchanged
    when this correction's gate does not fire, exactly like the original
    inline code left them untouched. ``total_tax`` is rebuilt from scratch
    by the LTCG/NIIT recombination further down the cascade
    (``total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit``) and so
    is not actually consumed before being overwritten, but is returned
    anyway to keep this function's local state and ``row``'s state in
    agreement at every call boundary, matching the DAF make-up module's
    same pattern. ``medical_ded`` is not read again this year but is
    returned for the same reason. Python scalar reassignment inside this
    function does not propagate to the caller, so every one of these must
    come back explicitly.
    """
    gap: float
    fed_tax: float
    taxable_inc: float
    total_tax_pre_niit: float
    total_tax: float
    item_ded: float
    ded: float
    medical_ded: float


def apply_hsa_reimbursement_correction(
    row: dict[str, Any],
    *,
    year: int,
    filing: str,
    hsa_wd: float,
    medical_expense_yr: float,
    medical_ded: float,
    agi: float,
    item_ded: float,
    ded: float,
    std_ded: float,
    qbi_ded: float,
    qbi_elig: bool,
    fed_tax: float,
    state_tax: float,
    payroll_tax: float,
    irmaa_yr: float,
    home_sale_ltcg_tax: float,
    taxable_inc: float,
    total_tax_pre_niit: float,
    total_tax: float,
    gap: float,
    total_spend_need: float,
    other_cash_need_yr: float,
    brk_inf: Any,
    compute_fed_tax_fn: Callable[[float, int, str, Any], float],
) -> HsaReimbursementCorrectionResult:
    """Withdrawal Cascade sub-stage #3 (design doc addendum): the
    HSA-reimbursement medical-deduction correction (lines ~1005-1099).

    **Positional precondition, load-bearing -- do not relocate.** This
    must run after Priority 2 (the HSA priority draws, which finalize
    ``hsa_wd`` for the dollars known by this point) and before Priority 3
    (the pre-tax elective withdrawal). This correction only ever INCREASES
    tax, which grows ``gap`` -- the rest of the cascade (Priority 3 onward)
    must still run afterward so it can fund that growth in order. An
    earlier version placed this after Priority 4c instead, on the
    reasoning that ``hsa_wd`` is not final until 4c's gap-fill has run;
    that left only Roth to fund the extra tax demand and caused 10 years
    of Roth-ordering-invariant violations, caught by
    ``test_recommendations_functional.py::
    test_fixed_point_taxable_withdrawal_solver_runs_before_roth``. That
    test is this function's acceptance gate -- treat it as the primary
    correctness oracle for any future change here, not just one more test
    in a batch. See that regression's full writeup, plus a second,
    independent regression from writing ``total_tax`` directly here instead
    of updating ``total_tax_pre_niit`` (a $178.21 residual caught by
    ``test_cashflow_breakdown_single_source_of_truth.py``), in the design
    doc's "Addendum (2026-09-09): Stage 10 (Withdrawal Cascade) design
    pass".

    Only the draws known by this point are netted -- Priority 1b's
    contingent-liability draw and Priority 2's scheduled window draw
    (both folded into ``hsa_wd`` by the time this runs). Priority 4c's
    later gap-fill is deliberately excluded: it is a last-resort liquidity
    draw against a general cash shortfall, not a reimbursement of this
    year's medical spend, so excluding it errs conservative (nets less,
    never more than the evidence supports).

    A qualified medical expense cannot both be reimbursed tax-free from
    the HSA and deducted on Schedule A. ``medical_expense_yr`` was
    computed from the full medical spend with no reduction for HSA
    dollars, so every HSA withdrawal was silently taking both benefits
    before this correction existed.

    ``row`` is mutated in place, as elsewhere in this stage decomposition.
    """
    _hsa_reimbursed = min(max(0.0, hsa_wd), max(0.0, medical_expense_yr))
    if _hsa_reimbursed > 1e-6 and medical_ded > 1e-6:
        # Net the reimbursed dollars out of the DEDUCTION directly rather
        # than re-deriving `max(0, net_medical - 0.075*agi)` here.
        #
        # The two are algebraically identical while the deduction is above
        # the floor AND `agi` is the same at both points -- and on the
        # frozen fixture's own configuration they are: both forms produce
        # byte-identical pins, so no test here distinguishes them. They
        # diverge only where `agi` has been mutated between the deduction
        # (computed early, off first-pass agi) and this correction
        # (post-cascade); measured under a `roth_policy='none'`
        # configuration, re-deriving stripped 18,439 against a 10,168
        # reimbursement in one year.
        #
        # Netting directly is preferred anyway because it inherits
        # whatever floor the engine already applied instead of silently
        # re-basing it. Whether that floor should use first-pass or
        # converged AGI is a real question, and a separate one from the
        # double benefit this block exists to correct.
        _new_medical_ded = max(0.0, medical_ded - _hsa_reimbursed)
        _medical_ded_lost = medical_ded - _new_medical_ded
        if _medical_ded_lost > 1e-6:
            _cand_item_ded = item_ded - _medical_ded_lost
            # std-vs-itemized is re-evaluated: a household pushed below the
            # standard deduction by this correction takes the standard one,
            # which caps the damage at (item_ded - std_ded) rather than the
            # full lost medical deduction.
            _new_ded = max(std_ded, _cand_item_ded + (qbi_ded if qbi_elig else 0.0))
            _new_taxable_inc = max(0.0, agi - _new_ded)
            _new_fed_tax = compute_fed_tax_fn(_new_taxable_inc, year, filing, brk_inf)
            _fed_tax_extra = max(0.0, _new_fed_tax - fed_tax)
            fed_tax = _new_fed_tax
            taxable_inc = _new_taxable_inc
            # Update the PRE-NIIT subtotal, not `total_tax` directly.
            # `total_tax` is rebuilt from scratch further down
            # (`total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit`),
            # so a direct `total_tax += ...` here is silently discarded
            # while the `fed_tax` change survives -- leaving the two
            # disagreeing. That showed up as a 178.21 cash-flow
            # reconciliation residual in
            # test_cashflow_breakdown_single_source_of_truth.py, with the
            # breakdown's `other` remainder absorbing exactly the gap.
            # Recomputing the subtotal from its own components is the
            # idiom the engine already uses at its other two update sites.
            total_tax_pre_niit = fed_tax + state_tax + payroll_tax + irmaa_yr
            total_tax = total_tax_pre_niit + home_sale_ltcg_tax
            gap += _fed_tax_extra
            item_ded = _cand_item_ded
            ded = _new_ded
            medical_ded = _new_medical_ded
            row['medical_expense_deduction'] = medical_ded
            row['medical_expense_hsa_reimbursed'] = _hsa_reimbursed
            row['taxable_inc'] = taxable_inc
            row['fed_tax'] = fed_tax
            row['total_tax'] = total_tax
            row['net_income'] = row.get('gross_income', agi) - total_tax
            row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr

    return HsaReimbursementCorrectionResult(
        gap=gap,
        fed_tax=fed_tax,
        taxable_inc=taxable_inc,
        total_tax_pre_niit=total_tax_pre_niit,
        total_tax=total_tax,
        item_ded=item_ded,
        ded=ded,
        medical_ded=medical_ded,
    )
