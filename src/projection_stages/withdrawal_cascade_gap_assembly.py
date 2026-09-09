from __future__ import annotations

from typing import Any


def apply_gap_assembly(
    c: dict[str, Any],
    bal: dict[str, float],
    row: dict[str, Any],
    *,
    year: int,
    h_ss: float,
    w_ss: float,
    pension: float,
    wife_single_ann: float,
    wife_joint_ann: float,
    h_single_ann: float,
    h_joint_ann: float,
    note_princ_yr: float,
    note_int_yr: float,
    rmd_taxable_total: float,
    earned_base: float,
    equity_events: dict[str, Any],
    di_cash: float,
    total_spend_need: float,
    total_tax: float,
    other_cash_need_yr: float,
    rec_extra: float,
    lump_yr: float,
    heloc_draw_yr: float,
    heloc_interest_yr: float,
    heloc_repayment_principal_yr: float,
) -> float:
    """Withdrawal Cascade sub-stage #0 (design doc addendum): assemble this
    year's cash ``gap`` (design doc Stage 10, lines ~959-1050), apply new
    HELOC draws/repayment against it, and amortize any additional
    liabilities into it.

    This is the cascade's central threading variable -- everything from
    here through Priority 5 (Roth, sub-stage #10) reads and reduces
    ``gap`` in sequence, so this sub-stage must run first and its
    returned ``gap`` must be the one every later sub-stage call receives.

    ``bal`` and ``row`` are mutated in place, as elsewhere in this stage
    decomposition. ``gap`` is a plain this-year float -- Python
    reassignment inside this function would not propagate to the caller
    on its own, so it comes back as the return value and the caller must
    reassign its own ``gap`` local from it before calling the next
    sub-stage.
    """
    income_from_streams = (h_ss + w_ss + pension + wife_single_ann +
                           wife_joint_ann + h_single_ann + h_joint_ann +
                           note_princ_yr + note_int_yr + rmd_taxable_total + earned_base +
                           equity_events['cash_proceeds'] + di_cash)
    row['income_funding'] = income_from_streams
    row['other_cash_need_yr'] = other_cash_need_yr
    row['total_cash_need'] = total_spend_need + total_tax + other_cash_need_yr
    gap = row['total_cash_need'] - income_from_streams

    # ── HELOC draw: new borrowing offsets gap (P&I already in spending above) ─
    # Interest and repayment principal were added to total_spend_need before
    # the gap calculation, so gap already includes those costs. Here we only
    # handle new draws (which reduce the gap) and balance updates.
    if c.get('heloc_enabled', False) and c.get('heloc_credit_limit', 0) > 0:
        _heloc_bal_now = float(bal.get('_heloc_balance', 0.0) or 0.0)
        if year <= c.get('heloc_draw_end_year', 0):
            _remaining_credit = max(0.0, float(c['heloc_credit_limit']) - _heloc_bal_now)
            _disc_spend = float(rec_extra or 0.0) + float(lump_yr or 0.0)
            heloc_draw_yr = min(_disc_spend, _remaining_credit, max(0.0, gap))
            if heloc_draw_yr > 1e-6:
                gap -= heloc_draw_yr
                bal['_heloc_balance'] = _heloc_bal_now + heloc_draw_yr
        elif _heloc_bal_now > 1.0:
            # Repayment period: reduce balance by principal already counted in spending
            bal['_heloc_balance'] = max(0.0, _heloc_bal_now - heloc_repayment_principal_yr)
    row['heloc_draw'] = heloc_draw_yr
    row['heloc_interest'] = heloc_interest_yr
    row['heloc_repayment_principal'] = heloc_repayment_principal_yr
    row['heloc_balance'] = float(bal.get('_heloc_balance', 0.0) or 0.0)
    row['heloc_payoff'] = 0.0  # set to nonzero in home sale year below

    # ── Additional liabilities: amortize into yearly cash outflow ──────────
    # auto / student_loan / other / heloc line items use standard fixed
    # amortization. Interest + principal for the year is added to `gap` (the
    # cash need funded by income/withdrawals), mirroring how HELOC interest
    # and repayment principal feed `gap` above. Outstanding balances reduce
    # net worth below. A plan with no liabilities skips this loop entirely.
    liability_payment_yr = 0.0
    liability_interest_yr = 0.0
    liability_principal_yr = 0.0
    student_loan_interest_yr = 0.0
    _liab_balances = bal.get('_liability_balances', {})
    if c.get('liabilities'):
        for _li_idx, _li in enumerate(c.get('liabilities', []) or []):
            _li_key = _li.get('liability_id') or f'liability_{_li_idx}'
            _li_bal = float(_liab_balances.get(_li_key, 0.0) or 0.0)
            if _li_bal <= 1e-6:
                continue
            _li_start = int(_li.get('start_year', 0) or 0)
            _li_payoff = int(_li.get('payoff_year', 0) or 0)
            # Not yet originated, or already past the scheduled payoff year.
            if _li_start and year < _li_start:
                continue
            if _li_payoff and year > _li_payoff:
                # Forgiven/assumed-settled after payoff year: drop the balance.
                _liab_balances[_li_key] = 0.0
                continue
            _li_rate = float(_li.get('interest_rate', 0.0) or 0.0)
            _li_annual_interest = _li_bal * _li_rate
            _li_monthly_pmt = float(_li.get('monthly_payment', 0.0) or 0.0)
            _li_annual_pmt = _li_monthly_pmt * 12.0
            if _li_annual_pmt <= 0.0:
                # No payment specified: if a payoff year is given, level-amortize
                # the remaining balance over the years left; else interest-only.
                if _li_payoff and _li_payoff >= year:
                    _yrs_left = max(1, _li_payoff - year + 1)
                    _mrate = _li_rate / 12.0
                    _n = _yrs_left * 12
                    if _mrate > 1e-9:
                        _li_annual_pmt = (_li_bal * _mrate / (1 - (1 + _mrate) ** (-_n))) * 12.0
                    else:
                        _li_annual_pmt = (_li_bal / max(1, _n)) * 12.0
                else:
                    _li_annual_pmt = _li_annual_interest  # interest-only
            # Cap the payment so it never overpays the balance + interest.
            _li_annual_pmt = min(_li_annual_pmt, _li_bal + _li_annual_interest)
            _li_principal = max(0.0, _li_annual_pmt - _li_annual_interest)
            _li_principal = min(_li_principal, _li_bal)
            _liab_balances[_li_key] = max(0.0, _li_bal - _li_principal)
            liability_payment_yr += _li_annual_pmt
            liability_interest_yr += _li_annual_interest
            liability_principal_yr += _li_principal
            if _li.get('type') == 'student_loan':
                student_loan_interest_yr += _li_annual_interest
        gap += liability_payment_yr
    row['liability_payment'] = liability_payment_yr
    row['liability_interest'] = liability_interest_yr
    row['liability_principal'] = liability_principal_yr
    row['liability_student_loan_interest'] = student_loan_interest_yr

    return gap
