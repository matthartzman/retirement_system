"""validation.py — registry-aware validation for retirement projections.

Extracted from src/data_io.py (formerly the inlined "validation_engine.py"
section) as part of system review 2026-08-31, finding A5 / Wave 3 item 3.13
("split parse_client into src/parsing/ siblings; move validation out").
src/data_io.py re-exports these names for backward compatibility with
existing callers (`from src.data_io import summarize_validation`, etc.).

Centralizes projection quality checks so workbook/API/reporting layers do not
need to embed validation rules. The functions return simple tuples for the
existing QC sheet:

    (year, severity, code, message)

Severity is either FAIL or WARN.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence, Tuple

ValidationFailure = Tuple[Any, str, str, str]


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return True  # non-numeric values are ignored by numeric validation


def _account_ids(c: Dict[str, Any]) -> List[str]:
    ids = list(c.get('all_acct_ids') or [])
    if ids:
        return ids
    registry = c.get('account_registry') or []
    ids = [a.get('id') for a in registry if a.get('id')]
    if ids:
        return ids
    # No hardcoded account fallback: validation must follow the active registry.
    return []


def validate_projection(rows: Sequence[Dict[str, Any]], c: Dict[str, Any]) -> List[ValidationFailure]:
    """Validate projection rows using registry-aware checks.

    The checks intentionally avoid asserting a precise financial-planning answer;
    they assert accounting integrity and presentation sanity.
    """
    failures: List[ValidationFailure] = []
    acct_ids = _account_ids(c)
    plan_end = c.get('plan_end')

    for row in rows:
        yr = row.get('year', '?')

        # NaN/Inf detection across numeric row values.
        for key, val in row.items():
            if isinstance(val, (int, float)) and not _finite(val):
                failures.append((yr, 'FAIL', 'NON_FINITE', f'{key} is {val!r}'))

        # Registry-driven account non-negativity and roll-forward footing.
        opening_map = row.get('_account_opening', {}) or {}
        deposits_map = row.get('_account_deposits', {}) or {}
        transfers_in_map = row.get('_account_transfers_in', {}) or {}
        transfers_out_map = row.get('_account_transfers_out', {}) or {}
        conv_in_map = row.get('_account_conversions_in', {}) or {}
        conv_out_map = row.get('_account_conversions_out', {}) or {}
        withdrawals_map = row.get('_account_withdrawals', {}) or {}
        growth_map = row.get('_account_growth', {}) or {}
        for acct in acct_ids:
            bal = row.get(acct, 0)
            if isinstance(bal, (int, float)) and bal < -0.01:
                failures.append((yr, 'FAIL', 'ACCOUNT_NEGATIVE', f'{acct} = ${bal:,.0f}'))
            if opening_map:
                calc_bal = (float(opening_map.get(acct, 0) or 0) +
                            float(deposits_map.get(acct, 0) or 0) +
                            float(transfers_in_map.get(acct, 0) or 0) -
                            float(transfers_out_map.get(acct, 0) or 0) +
                            float(conv_in_map.get(acct, 0) or 0) -
                            float(conv_out_map.get(acct, 0) or 0) -
                            float(withdrawals_map.get(acct, 0) or 0) +
                            float(growth_map.get(acct, 0) or 0))
                delta = float(bal or 0) - calc_bal
                if abs(delta) > 10:
                    failures.append((yr, 'FAIL', 'ACCOUNT_RECON',
                                     f'{acct} roll-forward delta = ${delta:,.2f}'))

        home_eq = row.get('home_equity', row.get('home_eq_nw', 0))
        if isinstance(home_eq, (int, float)) and home_eq < -0.01:
            failures.append((yr, 'FAIL', 'HOME_EQ_NEGATIVE', f'home equity = ${home_eq:,.0f}'))

        agi = max(1.0, float(row.get('agi', 0) or 0))
        total_tax = float(row.get('total_tax', 0) or 0)
        if total_tax > agi * 0.55 + 10_000:
            failures.append((yr, 'WARN', 'TAX_HIGH', f'tax/AGI = {total_tax / agi:.0%}'))

        if float(row.get('spend_base_yr', 0) or 0) < 0:
            failures.append((yr, 'FAIL', 'SPEND_NEGATIVE', 'Negative base spending'))
        if plan_end is None or (isinstance(yr, int) and yr <= plan_end):
            if float(row.get('total_spend', 0) or 0) <= 0:
                failures.append((yr, 'WARN', 'SPEND_ZERO', 'Total spending is zero or missing'))

        recon_delta = abs(float(row.get('cash_recon_delta', 0) or 0))
        tolerance = max(100.0, float(row.get('cash_uses', 0) or 0) * float(c.get('qc_cash_tolerance_pct', 0.01)))
        if recon_delta > tolerance:
            failures.append((yr, 'WARN', 'CASH_RECON_DRIFT', f'cash sources - uses = ${row.get("cash_recon_delta", 0):,.0f}'))

        unfunded_gap = float(row.get('unfunded_gap', 0) or 0)
        if unfunded_gap > tolerance:
            failures.append((yr, 'FAIL', 'UNFUNDED_GAP', f'unfunded cash need = ${unfunded_gap:,.0f}'))

        alloc_sum = row.get('allocation_sum')
        if isinstance(alloc_sum, (int, float)) and abs(alloc_sum - 1.0) > 0.01:
            failures.append((yr, 'WARN', 'ALLOCATION_SUM', f'allocation sum = {alloc_sum:.2%}'))

    return failures


def summarize_validation(rows: Sequence[Dict[str, Any]], c: Dict[str, Any]) -> Dict[str, Any]:
    failures = validate_projection(rows, c)
    return {
        'failures': failures,
        'fail_count': sum(1 for _y, sev, _code, _msg in failures if sev == 'FAIL'),
        'warn_count': sum(1 for _y, sev, _code, _msg in failures if sev == 'WARN'),
        'years': [_y for _y, _sev, _code, _msg in failures],
        'first_fail': next(((yr, code, msg) for yr, sev, code, msg in failures if sev == 'FAIL'), None),
    }
