"""Shared computed figures for the Executive Summary and the detail sheets it cites.

Every figure here is read by at least two sheets. They live in one module so the
flagship page and the sheet it points at can never show two different numbers for
the same quantity -- the failure mode ``src/glossary.py``'s docstring records this
codebase already shipped once, when two copies of the same definition drifted.

Each helper returns ``None`` when the underlying analysis is unavailable, rather
than a placeholder or an approximation. Callers are expected to omit the row in
that case. Printing an invented figure on a client-facing page is the defect this
module exists to remove -- see documentation/reports/SYSTEM_REVIEW_2026-08-04.md
findings C1 and C2.
"""


def _f(value):
    """Coerce to float, returning None for missing/non-numeric values."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None  # drop NaN


def roth_strategy_candidates(c):
    """Return the Sheet 11 candidate list, newest contract shape first."""
    contract = c.get('roth_strategy_result') or (c.get('plan_result') or {}).get('roth_strategy_result') or {}
    ropt = c.get('roth_optimization', {}) or {}
    return contract.get('candidates') or ropt.get('candidates') or []


def roth_strategy_benefit(c):
    """Selected-versus-next-best Roth strategy deltas, or None.

    The Executive Summary previously published ``sum(roth_conv) * 0.22`` as
    "Estimated Tax Saved -- Roth Strategy". That figure was 22% of *gross
    conversions* labelled as tax *saved*, and it contradicted the candidate
    comparison on Sheet 11 that this function reads instead.

    Returns a dict with ``lifetime_tax_delta`` (positive = the selected strategy
    pays less lifetime tax than the runner-up) and ``terminal_nw_delta``
    (positive = the selected strategy ends with more after-tax wealth), plus the
    two candidate labels. Returns None when fewer than two candidates were
    scored, since a "versus next best" figure is meaningless without a next best.
    """
    candidates = roth_strategy_candidates(c)
    if len(candidates) < 2:
        return None

    def _tax(cand):
        return _f(cand.get('lifetime_tax'))

    def _nw(cand):
        return _f(cand.get('after_tax_terminal_net_worth', cand.get('after_tax_terminal_nw')))

    selected, runner_up = candidates[0], candidates[1]
    sel_tax, next_tax = _tax(selected), _tax(runner_up)
    sel_nw, next_nw = _nw(selected), _nw(runner_up)
    if sel_tax is None or next_tax is None or sel_nw is None or next_nw is None:
        return None

    return {
        'selected_label': selected.get('label') or selected.get('selected_strategy_name') or 'Selected strategy',
        'runner_up_label': runner_up.get('label') or runner_up.get('selected_strategy_name') or 'Next-best strategy',
        'lifetime_tax_delta': next_tax - sel_tax,
        'terminal_nw_delta': sel_nw - next_nw,
    }


def credit_shelter_trust_savings(c):
    """Projected state estate tax sheltered by the CST, or None when disabled.

    Sheet 1 and Sheet 14 both report this. Sheet 1 previously hardcoded
    '~$320K IL estate tax avoided on $4M (8% avg rate)' -- correct only when
    ``il_exempt`` happens to equal its $4,000,000 default, which is a
    user-editable field.
    """
    if not c.get('cs_enabled', True):
        return None
    # Item 291: the CST-shelter math below (the flat 0.08 average-rate
    # assumption) is specific to the il_credit_table mechanism's typical
    # effective rate, not a generic "any state with an estate tax" figure --
    # so this must gate on the resolved state's estate_calc mechanism, not
    # merely on whether an estate tax exists at all.
    try:
        from ..core import STATE_TAX_RULES
    except ImportError:  # pragma: no cover - direct execution fallback
        from src.core import STATE_TAX_RULES
    _rules = STATE_TAX_RULES.get(str(c.get('state', '') or ''), {})
    if _rules.get('estate_calc') != 'il_credit_table':
        return None
    il_exempt = _f(c.get('il_exempt'))
    if il_exempt is None:
        return None
    cst_cap = _f(c.get('il_cst_shelter_cap')) or il_exempt
    cs_amt = _f(c.get('cs_amount'))
    if cs_amt is None:
        cs_amt = cst_cap
    sheltered = min(cs_amt, cst_cap)
    return {
        'funding_amount': cs_amt,
        'shelter_cap': cst_cap,
        'state_exemption': il_exempt,
        'tax_saved': sheltered * 0.08,
        'avg_rate': 0.08,
    }
