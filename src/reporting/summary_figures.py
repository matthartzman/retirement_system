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


# How far *below* the state exemption a projected estate may sit and still make
# the credit-shelter trust a live planning question. Exemption planning is
# forward-looking -- an estate at 92% of the exemption crosses it on ordinary
# growth -- but an estate at a third of the exemption is not a CST conversation,
# and printing the recommendation anyway is finding F2
# (documentation/reports/SYSTEM_REVIEW_2026-08-31.md).
CST_MATERIALITY_MARGIN = 0.10


def projected_second_death_estate(c, rows=None):
    """``(gross estate at second death, terminal row)``, or ``(None, None)``.

    This is the same quantity Sheet 14 prints as "Projected Estate at Second
    Death" (``rows[-1]['total_nw']``), plus the business interest that
    ``src/after_tax.py:estimate_terminal_estate_tax`` adds to the taxable
    estate, so the Executive Summary and Sheet 14 test the same number.

    It is the estate *before* any CST bypass: a funded trust is tracked in
    ``cst_excluded_from_survivor_estate`` and subtracted when forming the
    state-taxable estate -- the assets never leave ``total_nw``.
    """
    terminal = None
    if rows:
        terminal = rows[-1]
    else:
        _rows = (c.get('plan_result') or {}).get('rows') or []
        if _rows:
            terminal = _rows[-1]
    if not terminal:
        return None, None
    total = _f(terminal.get('total_nw'))
    if total is None:
        return None, None
    from ..after_tax import business_taxable_estate_value
    try:
        biz = _f(business_taxable_estate_value(c)) or 0.0
    except Exception:  # pragma: no cover - defensive: partial succession config
        biz = 0.0
    return max(0.0, total + biz), terminal


def credit_shelter_trust_savings(c, rows=None, require_enabled=True):
    """Real state estate tax sheltered by the CST, or None when not material.

    Sheets 1, 14 and 19 all report this. Sheet 1 originally hardcoded
    '~$320K IL estate tax avoided on $4M (8% avg rate)'; the first repair
    replaced the hardcoding with ``sheltered * 0.08``, which was still a
    fabricated figure -- a flat 8% of the funding amount, with no reference
    anywhere to the household's projected estate or to whether that estate
    exceeds the exemption at all (SYSTEM_REVIEW_2026-08-31 finding F2).

    The saving is now the actual delta between the state estate tax on the
    projected second-death estate WITHOUT the trust and WITH it, computed
    through ``core.state_estate_tax`` -- the same cliff/interrelated
    calculation Sheet 14 prints -- so a hand-worked household reproduces it.

    Returns ``None`` -- meaning publish no figure, and render no row at all --
    when any of these hold:

    - the trust is configured off and ``require_enabled`` is set (Sheet 1's
      recommendation row passes ``require_enabled=False``: the point of that
      row is precisely that the trust is *not* yet in place);
    - the residence state's estate-tax mechanism is not modeled by this engine
      (``state_estate_tax`` returns 0.0 there, and that 0.0 must never be
      published as though it were computed);
    - state estate tax is switched off for this plan (``model_state_est``);
    - nothing would be sheltered, or no projection is available to measure the
      estate against;
    - the projected estate is more than ``CST_MATERIALITY_MARGIN`` below the
      state exemption -- the trust shelters nothing for this household.

    In the near-miss band (estate below the exemption but within the margin)
    the dict IS returned, with ``tax_saved`` and ``avg_rate`` set to ``None``:
    there is no dollar figure to publish, but the recommendation is still worth
    making. Callers must render the qualitative wording in that case rather
    than a "$0 saved" line.
    """
    if require_enabled and not c.get('cs_enabled', True):
        return None
    # Item 291: gate on the resolved state's estate_calc mechanism, not merely
    # on whether an estate tax exists at all.
    from ..core import STATE_TAX_RULES, state_estate_tax
    state = str(c.get('state', '') or '')
    _rules = STATE_TAX_RULES.get(state, {})
    if _rules.get('estate_calc') != 'il_credit_table':
        return None
    if not c.get('model_state_est', True):
        return None
    exemption = _f(c.get('il_exempt'))
    if exemption is None or exemption <= 0:
        return None

    cst_cap = _f(c.get('il_cst_shelter_cap')) or exemption
    cs_amt = _f(c.get('cs_amount'))
    if cs_amt is None:
        cs_amt = cst_cap

    estate, terminal = projected_second_death_estate(c, rows)
    if estate is None:
        return None

    # When the projection already ran with the trust funded, the engine's own
    # funded total is the honest shelter amount -- it is capped by what the
    # first decedent actually held, which the configured cs_amount is not.
    funded_actual = _f((terminal or {}).get('cst_excluded_from_survivor_estate'))
    sheltered = funded_actual if (funded_actual or 0.0) > 0 else min(cs_amt, cst_cap)
    sheltered = max(0.0, min(sheltered, estate))
    if sheltered <= 0:
        return None

    # Materiality gate (F2): well below the exemption, the trust shelters
    # nothing and there is no recommendation to make.
    if estate < exemption * (1.0 - CST_MATERIALITY_MARGIN):
        return None

    tax_without, status_without = state_estate_tax(state, estate, exemption)
    if status_without != 'computed':
        return None
    tax_with, _status_with = state_estate_tax(state, max(0.0, estate - sheltered), exemption)
    saved = max(0.0, tax_without - tax_with)
    # No dollar figure in the near-miss band: the estate does not clear the
    # exemption at current projections, so the honest delta is zero, and
    # printing "$0 saved" beside a recommendation is worse than saying why.
    publish_figure = saved > 0 and estate > exemption

    return {
        'funding_amount': sheltered,
        'configured_funding_amount': cs_amt,
        'shelter_cap': cst_cap,
        'state_exemption': exemption,
        'projected_estate': estate,
        'estate_tax_without_cst': tax_without,
        'estate_tax_with_cst': tax_with,
        'tax_saved': saved if publish_figure else None,
        'avg_rate': (saved / sheltered) if publish_figure else None,
        'below_exemption': estate <= exemption,
    }


def federal_estate_materiality(c, rows=None, margin=CST_MATERIALITY_MARGIN):
    """Whether FEDERAL estate tax planning is a live question for this
    household, independent of which (if any) state estate tax is modeled.

    Item 2.11: generalizes 1.10/F2's materiality gating -- previously only
    applied to the Illinois-specific Credit Shelter Trust row -- to
    recommendation rows whose relevance is driven by *federal* estate
    exposure rather than a specific state's mechanism (starting with QTIP,
    since a QTIP trust is a federal marital-deduction/estate-tax tool
    usable in any state, not an Illinois-only planning question the way
    ``credit_shelter_trust_savings`` is scoped). Nets out lifetime gift
    exemption already consumed (see ``after_tax.estimate_terminal_estate_tax``,
    item 2.6) so this agrees with the same terminal estate-tax figure the
    Executive Summary and Roth optimizer's estate penalty use.

    Returns ``(projected_estate, federal_exemption_net_of_gifts, exposed)``.
    ``exposed`` is True when the projected estate is at or within ``margin``
    below the net exemption -- the same "estate tax planning is a live
    question, even if not yet triggered" threshold ``credit_shelter_trust_savings``
    uses. Returns ``(None, None, False)`` when no projection is available.
    """
    estate, terminal = projected_second_death_estate(c, rows)
    if estate is None:
        return None, None, False
    from ..core import indexed_federal_estate_exemption
    target_year = int((terminal or {}).get('year', c.get('plan_end', c.get('plan_start', 0))) or 0)
    fed_exempt = indexed_federal_estate_exemption(
        c.get('fed_exempt'), c.get('plan_start', target_year), target_year, c.get('brk_inf', 0.02))
    lifetime_used = _f((terminal or {}).get('lifetime_exemption_used_cumulative')) or 0.0
    fed_exempt = max(0.0, fed_exempt - lifetime_used)
    if fed_exempt <= 0:
        return estate, fed_exempt, True
    exposed = estate >= fed_exempt * (1.0 - margin)
    return estate, fed_exempt, exposed
