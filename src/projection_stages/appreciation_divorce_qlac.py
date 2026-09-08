from __future__ import annotations

from typing import Any, NamedTuple

from .. import core as _aa  # consolidated from account_access
from .. import core as _ar  # consolidated from account_registry
from ..core import qlac_premium_limit


class Stage3Result(NamedTuple):
    """Every value this stage updates, returned as one typed bundle.

    Three fields (``cst_balance``, ``startup``, ``autos_val``) are
    multi-year state: the caller must reassign its own locals from
    these on every call, or the update silently fails to propagate
    (Python floats are passed by value -- mutating a parameter inside
    this function does not change the caller's variable). The other
    three (``startup_sale_proceeds``, ``divorce_split_amount``,
    ``qlac_purchase_yr``) are this-year-only reporting values the
    caller assigns onto ``row``.

    A plain tuple would work but invites a positional mis-assignment
    (e.g. swapping ``cst_balance``/``startup``, both floats, both
    plausible in either slot) that a snapshot/golden-master test might
    not catch for years -- the account-balance and net-worth impact of
    such a swap can be small in a given scenario. NamedTuple gives the
    call site named, order-independent unpacking (``result.cst_balance``)
    at zero runtime cost, without pulling in the full engine-wide
    YearState this decomposition is deliberately deferring.
    """
    cst_balance: float
    startup: float
    autos_val: float
    startup_sale_proceeds: float
    divorce_split_amount: float
    qlac_purchase_yr: float


def apply_appreciation_divorce_qlac(
    c: dict[str, Any],
    *,
    year: int,
    h_alive: bool,
    w_alive: bool,
    bal: dict[str, float],
    cst_balance: float,
    startup: float,
    account_deposits: dict[str, float],
    account_deposit_sources: dict[str, list],
    account_transfers_out: dict[str, float],
    account_withdrawals: dict[str, float],
) -> Stage3Result:
    """Grow CST/startup equity, depreciate autos, and apply the year's
    one-time divorce split and QLAC premium withdrawal.

    Four independent, mostly self-contained one-time/ongoing events
    bundled under one header in the legacy engine, in original order:

    1. **CST appreciation** -- grows the already-funded bypass-trust
       balance (funding itself happens earlier, in the spousal-rollover
       stage) at the plan's ordinary return rate.
    2. **Auto depreciation** -- straight-line to zero over
       ``auto_dep_yrs``; a pure function of ``year``, carrying no state
       from prior years despite living next to two stateful events.
    3. **Startup equity** -- grows at ``startup_gr`` until the
       configured sale year, then liquidates in full to the first
       taxable account (a one-time, non-recurring deposit).
    4. **Divorce/QDRO split** -- in the configured year, removes a flat
       percentage from every investment account. Not a taxable event
       (IRC S1041): dollars leave the household balance sheet with no
       gain/basis/tax pass.
    5. **QLAC purchase** -- in each spouse's configured purchase year,
       moves the premium out of the configured pre-tax source account.
       A same-character exchange inside the tax-deferred wrapper, not a
       taxable distribution.

    ``bal`` (account balances) and the four ``account_*`` flow dicts are
    mutated in place -- dict mutation crosses the function boundary
    naturally in Python, so callers see the updates without any of them
    appearing in the return value. ``cst_balance``, ``startup``, and
    ``autos_val`` do NOT: they are plain floats, reassigned here as
    locals, which does nothing to the caller's own locals of the same
    name. Those three -- plus the year's one-time report-only amounts
    (``startup_sale_proceeds``, ``divorce_split_amount``,
    ``qlac_purchase_yr``, all normally written straight onto ``row``) --
    come back via the returned :class:`Stage3Result`; see its docstring
    for why a named tuple rather than a bare one.

    Home value appreciation is handled separately, inside the home-sale
    stage that follows this one in the legacy engine -- deliberately not
    duplicated here.
    """
    # ── Asset appreciation ───────────────────────────────────────────────
    if cst_balance > 0:
        cst_balance *= (1 + float(c.get('ret', 0.0) or 0.0))
    # Note: home_val appreciation is handled inside the home sale block below
    autos_val = max(0, c['autos'] - c['autos'] / max(1, c['auto_dep_yrs']) * (year - c['plan_start'] + 1))
    # Startup equity: grow until sale year, then sell and deposit proceeds to Trust
    sale_yr = c.get('startup_sale_year', 0)
    sale_px = c.get('startup_sale_price', 0)
    if sale_yr and year == sale_yr and startup > 0:
        # Sale proceeds deposit to the first available taxable account.
        proceeds = sale_px if sale_px > 0 else startup
        _startup_acct = _aa.first_taxable(c)
        _aa.deposit(bal, _startup_acct, proceeds)
        _add_account_flow(account_deposits, _startup_acct, proceeds)
        _tag_deposit_source(account_deposit_sources, _startup_acct, 'Startup Equity Sale', proceeds)
        startup = 0.0
        startup_sale_proceeds = proceeds
    elif startup > 0 and (not sale_yr or year < sale_yr):
        # Only appreciate if growth_rate > 0; stays flat when 0
        if c['startup_gr'] > 0:
            startup *= (1 + c['startup_gr'])
        startup_sale_proceeds = 0.0
    else:
        startup_sale_proceeds = 0.0

    # ── Divorce/QDRO asset split (optimization-refactor Phase 6) ─────────
    # A one-time reduction of every investment account at a configured
    # year, modeling a QDRO/marital-asset division. Unlike a home sale,
    # transfers incident to divorce are not a taxable event (IRC S1041):
    # the departing share simply leaves the household's balance sheet,
    # no capital gain, no basis adjustment, no tax pass needed.
    divorce_split_amount = 0.0
    if c.get('divorce_split_yr') and year == int(c['divorce_split_yr']):
        _divorce_pct = max(0.0, min(1.0, float(c.get('divorce_split_pct', 0.0) or 0.0)))
        if _divorce_pct > 0:
            _divorce_split_total = 0.0
            for _aid in _ar.all_investment_ids(c.get('account_registry', [])):
                _before = float(bal.get(_aid, 0.0) or 0.0)
                if _before > 0:
                    _taken = _before * _divorce_pct
                    bal[_aid] = _before - _taken
                    _add_account_flow(account_transfers_out, _aid, _taken)
                    _divorce_split_total += _taken
            divorce_split_amount = _divorce_split_total

    # ── QLAC purchase (#295) ──────────────────────────────────────────
    # A one-time withdrawal of the premium from the configured pre-tax
    # source account in the purchase year -- the dollars leave the IRA
    # balance sheet the same way any other qualified-plan distribution
    # would, becoming instead the deferred-income contract modeled via
    # annuity_cash_income() (folded into h_single_ann/wife_single_ann
    # above). Not a taxable distribution: a QLAC purchase inside a
    # traditional IRA/401k is a same-character exchange (still pre-tax
    # money, still taxed as ordinary income when the contract eventually
    # pays out), not a withdrawal from the tax-deferred wrapper.
    qlac_purchase_yr = 0.0
    for _qlac_stream, _qlac_alive in ((c['h_qlac'], h_alive), (c['wife_qlac'], w_alive)):
        if (_qlac_alive and _qlac_stream.get('enabled') and
                int(_qlac_stream.get('purchase_year', 0) or 0) == year):
            _qlac_acct = _qlac_stream.get('source_account', '')
            if _qlac_acct in bal and _qlac_acct in c.get('pre_tax_ids', []):
                _qlac_cap = qlac_premium_limit(year, c.get('brk_inf', 0.02))
                _qlac_amt = min(float(_qlac_stream.get('premium', 0.0) or 0.0), _qlac_cap,
                                 float(bal.get(_qlac_acct, 0.0) or 0.0))
                if _qlac_amt > 0:
                    bal[_qlac_acct] = float(bal.get(_qlac_acct, 0.0) or 0.0) - _qlac_amt
                    _add_account_flow(account_withdrawals, _qlac_acct, _qlac_amt)
                    qlac_purchase_yr += _qlac_amt

    return Stage3Result(
        cst_balance=cst_balance,
        startup=startup,
        autos_val=autos_val,
        startup_sale_proceeds=startup_sale_proceeds,
        divorce_split_amount=divorce_split_amount,
        qlac_purchase_yr=qlac_purchase_yr,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount


def _tag_deposit_source(target: dict[str, list], acct: str | None, source: str, amount: float) -> None:
    """Record a human-readable source label for a deposit, alongside the
    existing flat account-deposits total (which remains unchanged and is
    still the authoritative per-account aggregate for reconciliation).
    """
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        sources = target.setdefault(acct, [])
        sources.append({'source': source, 'amount': amount})
