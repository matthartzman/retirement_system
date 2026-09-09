from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .. import core as _aa  # consolidated from account_access
from .. import tax_kernel as _tk
from ..planning_engines import EvHomeSale


class HomeSaleResult(NamedTuple):
    """The three values this stage updates that persist across years.

    ``home_val``, ``home_equity``, and ``mort_bal_yr`` are plain floats:
    Python does not mutate a caller's local through a function parameter,
    so the caller must reassign its own locals from these fields on every
    call, or the update silently fails to propagate (``mort_bal_yr`` in
    particular is read again ~2,200 lines later, in the net-worth/
    liabilities rollup, so a dropped reassignment would surface there, not
    here).

    Everything else this stage produces is a this-year-only reporting
    value. Unlike the appreciation/divorce/QLAC stage, those report fields
    are NOT bundled into this return: the legacy engine sets a different
    *subset* of ``row`` keys depending on which branch runs (sale vs.
    no-sale, HELOC-enabled vs. not), and the full-row snapshot regression
    test pins the exact key set present in each year's row, not just their
    values. Reproducing that via a returned bundle would require the call
    site to re-derive which fields to conditionally assign -- the same
    branching this function already has to do internally. So this stage
    takes ``row`` directly and writes its report fields onto it in place,
    matching the legacy branch structure exactly; see the docstring below
    for the full list of keys each branch sets.
    """
    home_val: float
    home_equity: float
    mort_bal_yr: float


def apply_home_sale(
    c: dict[str, Any],
    row: dict[str, Any],
    *,
    year: int,
    home_val: float,
    filing: str,
    second_death_yr: int,
    bal: dict[str, float],
    bal_basis_free: dict[str, float],
    emit: Callable[[Any], None],
) -> HomeSaleResult:
    """Appreciate or sell the home for the year, pay off HELOC/mortgage at
    sale, and route sale proceeds.

    In the sale year (the configured ``home_sale_yr``, or an estate sale
    forced at the second death), this:

    1. Computes gross proceeds (estate sale uses market value; a planned
       sale uses the configured ``home_sale_px`` if set, else market
       value).
    2. Deducts selling costs and pays off the remaining mortgage from the
       amortization schedule.
    3. Computes the taxable capital gain (basis step-up at death means an
       estate sale realizes no gain) net of the S121 exclusion, and stashes
       it on ``row['_home_sale_taxable_gain_pending']`` -- the tax on this
       gain is NOT computed here. It is computed later in the same year's
       tax pass, once ordinary taxable income is known, by
       :func:`resolve_home_sale_gain_tax`. ``home_sale_tax`` is written
       as ``0.0`` here as a placeholder and overwritten there.
    4. Pays off any outstanding HELOC balance from the proceeds first.
    5. Deposits the remaining net proceeds -- split across
       ``home_sale_splits`` accounts if configured, else to one designated
       account -- and marks those dollars basis-free (already taxed / basis
       stepped-up, so future trust draws should not tax them again).
    6. Zeroes out ``home_val``/``home_equity`` -- the home is no longer
       owned.

    In a non-sale year, home value simply appreciates at ``home_appr`` (if
    still owned) and equity is mortgage/HELOC balance netted against value.

    Row keys written, by branch (this mirrors the legacy engine's exact
    conditional key set -- the full-row snapshot regression test pins keys
    present, not just values, so these are NOT normalized to "always
    present"):

    - **Sale year:** ``home_sale_gross``, ``home_sale_costs``,
      ``home_sale_mort_off``, ``home_sale_gain``,
      ``home_sale_sec121_exclusion``, ``home_sale_taxable``,
      ``home_sale_tax`` (``0.0`` placeholder), ``home_sale_net``,
      ``home_sale_acct``, ``home_sale_splits_applied``,
      ``_home_sale_taxable_gain_pending``, and -- only when
      ``heloc_enabled`` -- ``heloc_payoff``.
    - **Non-sale year:** ``home_sale_gross``, ``home_sale_mort_off``,
      ``home_sale_gain``, ``home_sale_taxable``, ``home_sale_tax``,
      ``home_sale_net``, ``home_sale_costs`` (all ``0``), and
      ``home_sale_acct`` (``''``). ``_home_sale_taxable_gain_pending``,
      ``heloc_payoff``, and ``home_sale_splits_applied`` are not set.

    ``bal`` and ``bal_basis_free`` are mutated in place. ``row`` is
    mutated in place (see above). ``emit`` is called with an
    :class:`EvHomeSale` in the sale year. ``home_val``, ``home_equity``,
    and the recomputed ``mort_bal_yr`` come back via the returned
    :class:`HomeSaleResult` -- see its docstring for why.
    """
    home_sold = home_val <= 0  # already sold in a prior year
    # Mortgage balance -- computed once here, used in both sale and non-sale branches
    mort_bal_yr = c['mort_schedule'].get(year, 0.0)
    if year > c['mort_end'] or home_sold:
        mort_bal_yr = 0.0
    # Estate disposition: the home is sold at the second death rather than
    # carried by a household that no longer exists. Reuses the existing sale
    # machinery below (mortgage payoff, selling costs, proceeds routing).
    _estate_sale = (not home_sold) and year == second_death_yr
    if not home_sold and ((c.get('home_sale_yr') and year == c['home_sale_yr'])
                          or _estate_sale):
        # ── Home sale year ────────────────────────────────────────────────
        # 1. Gross proceeds
        # An estate sale is at MARKET value. home_sale_px is the user's assumed
        # price for a specific planned downsizing; applying it to a later
        # estate disposition would value the home at a stale figure -- on the
        # frozen fixture that is 1,750,000 against a 3,282,605 market value,
        # destroying 1.53M of estate value.
        gross_proceeds = home_val if _estate_sale else (
            c['home_sale_px'] if c['home_sale_px'] > 0 else home_val)
        # 2. Selling costs (realtor commission + closing)
        selling_costs = gross_proceeds * c['home_sell_cost_pct']
        # 3. Pay off remaining mortgage (from amortization schedule)
        mort_payoff = mort_bal_yr
        mort_bal_yr = 0.0  # mortgage retired at sale
        proceeds_after = max(0, gross_proceeds - selling_costs - mort_payoff)
        # 4. Capital gain: (gross - selling costs) - basis  [selling costs reduce gain]
        # Assets receive a basis step-up at death, so an estate sale in the
        # year of the second death realizes no taxable gain.
        basis = gross_proceeds if _estate_sale else (c.get('home_basis', 0) or c['home_val'] * 0.5)
        cap_gain = max(0, gross_proceeds - selling_costs - basis)
        # 5. §121 exclusion: $500k for MFJ, $250k otherwise. The filing
        # status is already switched to survivor_filing after the configured
        # survivor window, so post-window survivor sales do not over-exclude.
        sec121_exclusion = 500000.0 if filing == 'MFJ' else 250000.0
        sec121_exclusion = min(float(c.get('sec121', sec121_exclusion) or sec121_exclusion), sec121_exclusion)
        taxable_gain = max(0, cap_gain - sec121_exclusion)
        # 6. LTCG tax is computed later in this same-year tax pass after
        # ordinary taxable income is known. Deposit gross-after-cost/mortgage
        # proceeds now; the withdrawal cascade funds the tax like every other
        # current-year liability.
        home_sale_tax = 0.0
        row['_home_sale_taxable_gain_pending'] = taxable_gain
        # 7. Proceeds deposited to designated account (basis-free)
        net_proceeds = max(0, proceeds_after)
        # Pay off HELOC from home sale proceeds before depositing
        if c.get('heloc_enabled', False):
            _heloc_bal_at_sale = float(bal.get('_heloc_balance', 0.0) or 0.0)
            heloc_payoff_yr = min(_heloc_bal_at_sale, net_proceeds)
            net_proceeds = max(0.0, net_proceeds - heloc_payoff_yr)
            bal['_heloc_balance'] = max(0.0, _heloc_bal_at_sale - heloc_payoff_yr)
            row['heloc_payoff'] = heloc_payoff_yr
        # #299: proceeds may be split across multiple accounts by
        # percentage (home_sale_splits) instead of one designated
        # account. Drop any split naming an account that doesn't exist
        # in this plan's balances and renormalize the remaining
        # percentages to 1.0, so the full net_proceeds is always
        # deposited somewhere even if a configured account was removed
        # after the split was set up.
        _configured_splits = [
            s for s in (c.get('home_sale_splits') or [])
            if str(s.get('account', '')) in bal and float(s.get('pct', 0) or 0) > 0
        ]
        _split_pct_total = sum(float(s.get('pct', 0) or 0) for s in _configured_splits)
        if _configured_splits and _split_pct_total > 0:
            deposits = [
                (str(s['account']), net_proceeds * (float(s['pct']) / _split_pct_total))
                for s in _configured_splits
            ]
            acct = deposits[0][0]
        else:
            acct = c.get('home_sale_acct') or _aa.first_taxable(c)
            if acct not in bal:
                acct = _aa.first_taxable(c)
            deposits = [(acct, net_proceeds)]
        for _dep_acct, _dep_amt in deposits:
            if _dep_amt <= 0:
                continue
            _aa.deposit(bal, _dep_acct, _dep_amt)
            _add_account_flow(row['_account_deposits'], _dep_acct, _dep_amt)
            _tag_deposit_source(row, _dep_acct, 'Home Sale Proceeds', _dep_amt)
            # These dollars already had their gain taxed -> stepped-up basis.
            # Track as basis-free so future trust draws don't tax them again.
            if _dep_acct in bal_basis_free:
                bal_basis_free[_dep_acct] += _dep_amt
        row['home_sale_splits_applied'] = [
            {'account': a, 'amount': amt} for a, amt in deposits if amt > 0
        ] if len(deposits) > 1 else []
        # 8. Zero out home value -- no longer owned
        home_val = 0.0
        home_equity = 0.0
        row['home_sale_gross']    = gross_proceeds
        row['home_sale_costs']    = selling_costs
        row['home_sale_mort_off'] = mort_payoff
        row['home_sale_gain']     = cap_gain
        row['home_sale_sec121_exclusion'] = sec121_exclusion
        row['home_sale_taxable']  = taxable_gain
        row['home_sale_tax']      = home_sale_tax
        row['home_sale_net']      = net_proceeds
        row['home_sale_acct']     = acct
        emit(EvHomeSale(year, gross_proceeds, selling_costs, mort_payoff,
                        home_sale_tax, net_proceeds, acct))
    else:
        # Normal year -- appreciate home if still owned
        if not home_sold:
            home_val *= (1 + c['home_appr'])
        home_equity = max(0, home_val - mort_bal_yr)
        # Reduce home equity by outstanding HELOC balance in non-sale years
        if c.get('heloc_enabled', False):
            home_equity = max(0.0, home_equity - float(bal.get('_heloc_balance', 0.0) or 0.0))
        row['home_sale_gross'] = row['home_sale_mort_off'] = 0
        row['home_sale_gain']  = row['home_sale_taxable']  = 0
        row['home_sale_tax']   = row['home_sale_net']      = 0
        row['home_sale_costs'] = 0
        row['home_sale_acct']  = ''

    return HomeSaleResult(home_val=home_val, home_equity=home_equity, mort_bal_yr=mort_bal_yr)


class HomeSaleGainTaxResult(NamedTuple):
    """Both values downstream code needs from the resolution step.

    ``gain`` is not merely an echo of ``row['_home_sale_taxable_gain_pending']``
    for convenience: the withdrawal-cascade stage (~400 lines further on,
    out of scope for this extraction) seeds its own LTCG/NIIT fixed-point
    loop from this same gain figure (as ``ltcg_gain``, alongside ``tax`` as
    ``ltcg_tax``), so the caller needs both values as locals, not just the
    tax.
    """
    gain: float
    tax: float


def resolve_home_sale_gain_tax(
    c: dict[str, Any],
    row: dict[str, Any],
    *,
    year: int,
    taxable_inc: float,
) -> HomeSaleGainTaxResult:
    """Compute the LTCG tax on a home sale's deferred taxable gain.

    :func:`apply_home_sale` computes the taxable gain from a home sale
    (if any) and stashes it on ``row['_home_sale_taxable_gain_pending']``,
    but cannot compute the tax on it at that point in the year: LTCG tax
    depends on ordinary taxable income (``taxable_inc``), which is not
    known until the AGI/tax stage runs, ~1,300 lines later in the legacy
    engine. This function is that resolution step -- called from within
    the AGI/tax stage once ``taxable_inc`` exists, using the same
    ``tax_kernel.ltcg_tax_on_gain`` primitive the rest of that stage's
    LTCG calculations use (the legacy engine's local ``_ltcg_tax_on_gain_path``
    closure was just a thin wrapper over it with ``c`` pre-bound).

    Sets ``row['home_sale_tax']`` -- overwriting the ``0.0`` placeholder
    :func:`apply_home_sale` wrote in the sale year -- only when there is a
    pending gain to tax, matching the legacy engine's conditional exactly
    (a no-sale year leaves ``home_sale_tax`` at the ``0`` value the
    no-sale branch of :func:`apply_home_sale` already set, and this
    function does not touch it). Returns gain and tax via
    :class:`HomeSaleGainTaxResult` so the caller can fold the tax into the
    year's ``total_tax`` and seed the later withdrawal-cascade fixed point
    with both, the same way the legacy engine did inline.
    """
    home_sale_ltcg_gain = float(row.get('_home_sale_taxable_gain_pending', 0.0) or 0.0)
    home_sale_ltcg_tax = (
        _tk.ltcg_tax_on_gain(c, home_sale_ltcg_gain, max(0.0, taxable_inc), year)
        if home_sale_ltcg_gain > 0 else 0.0
    )
    if home_sale_ltcg_gain > 0:
        row['home_sale_tax'] = home_sale_ltcg_tax
    return HomeSaleGainTaxResult(gain=home_sale_ltcg_gain, tax=home_sale_ltcg_tax)


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount


def _tag_deposit_source(row: dict[str, Any], acct: str | None, source: str, amount: float) -> None:
    """Record a human-readable source label for a deposit, alongside the
    existing flat ``_account_deposits`` total (which remains unchanged and
    is still the authoritative per-account aggregate for reconciliation).
    """
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        sources = row.setdefault('_account_deposit_sources', {})
        sources.setdefault(acct, []).append({'source': source, 'amount': amount})
