from __future__ import annotations

from typing import Any, Callable, NamedTuple

from .. import core as _aa  # consolidated from account_access
from .. import core as _ar  # consolidated from account_registry
from .. import planning_engines as _legacy_pe
from ..planning_engines import EvDeath, EvTransfer


class Stage1Result(NamedTuple):
    """Every value this stage updates, returned as one typed bundle.

    ``h_alive``/``w_alive``/``n_alive`` are this-iteration-only: every stage
    later in the *same* year reads them (as Stage 3's own ``h_alive``/
    ``w_alive`` parameters already show), so the caller must capture them
    from the return value even though they are not carried into the next
    loop iteration.

    ``filing`` and ``first_death_done`` are different in kind, not just in
    lifetime: they are seeded ONCE before the year loop (from
    ``year_state.filing_status`` / ``year_state.first_death_done``) and then
    carried across *every* iteration, reassigned here as plain locals. As
    with Stage 3's ``cst_balance``/``startup``/``autos_val``, Python does
    not propagate a reassigned parameter back to the caller -- the caller
    MUST reassign its own ``filing``/``first_death_done`` locals from this
    return value on every call, or every subsequent year silently keeps
    computing tax under the wrong (pre-death) filing status for the rest of
    the plan. A dropped reassignment here would misprice federal/state tax
    brackets, IRMAA tiers, and the standard deduction for every year after
    the miss -- see the module docstring for how this was verified safe.

    A plain tuple would invite exactly that kind of silent, hard-to-detect
    bug (a dropped or swapped field among five same-shaped values); a named
    tuple keeps the call site's reassignment explicit and self-documenting,
    matching Stage 3's ``Stage3Result`` precedent.
    """
    h_alive: bool
    w_alive: bool
    n_alive: int
    filing: str
    first_death_done: bool


def apply_deaths_and_filing_status(
    c: dict[str, Any],
    *,
    year: int,
    filing: str,
    first_death_done: bool,
) -> Stage1Result:
    """Determine who is alive this year and update the household's tax
    filing status, including the multi-year QSS (Qualifying Surviving
    Spouse) window.

    In original order:

    1. **Alive flags** -- a member is alive through (and including) their
       configured death year; the year of death itself is still reported
       alive.
    2. **Filing status transition** -- ``filing`` stays ``'MFJ'`` through
       the year of the first death. The year *after* the first death:
       - if the plan marks a dependent survivor (``qss_dependent``), filing
         stays ``'MFJ'`` for up to two more years (the IRC S2(a) Qualifying
         Surviving Spouse window), then drops to ``survivor_filing``
         (normally ``'Single'``);
       - otherwise filing drops to ``survivor_filing`` immediately.
       ``first_death_done`` latches ``True`` the first time either death
       branch fires and is never reset -- it exists purely to make the
       transition a one-time event (so a plan that later re-enters one of
       these year-equality conditions, e.g. via a second member's death
       year, does not re-trigger the *first*-death transition).

    Nothing here mutates ``bal`` or emits events -- this stage only decides
    who is alive and what filing status applies, both purely from ``c`` and
    the two carried-forward scalars. The spousal-rollover/CST-funding stage
    that follows depends on this stage's ``h_alive``/``w_alive`` output and
    is deliberately kept as a separate function (see
    :func:`apply_spousal_rollover_and_cst_funding`) rather than merged in,
    since it does something categorically different (dollar-moving account
    mutation vs. bookkeeping of two flags and a status string) even though
    both are conventionally grouped under one "Deaths" header in the legacy
    engine and are always called back-to-back at the same call site.
    """
    h_alive = year <= c['h_death_yr']
    w_alive = year <= c['w_death_yr']
    n_alive = (1 if h_alive else 0) + (1 if w_alive else 0)

    # Filing status change year after first death.  Year of death remains
    # MFJ where applicable.  QSS is available for the next two years when
    # the plan marks a dependent survivor; tax brackets use MFJ during QSS.
    _survivor_filing = c.get('survivor_filing', 'Single')
    _first_death_year = int(c.get('first_death_yr', 0) or 0)
    if _first_death_year and c.get('qss_dependent', False) and _first_death_year < year <= _first_death_year + 2:
        filing = 'MFJ'
    elif not h_alive and not first_death_done and year == c['h_death_yr'] + 1:
        filing = _survivor_filing
        first_death_done = True
    elif not w_alive and not first_death_done and year == c['w_death_yr'] + 1:
        filing = _survivor_filing
        first_death_done = True
    elif _first_death_year and year > _first_death_year + 2 and c.get('qss_dependent', False):
        filing = _survivor_filing
        first_death_done = True

    return Stage1Result(
        h_alive=h_alive,
        w_alive=w_alive,
        n_alive=n_alive,
        filing=filing,
        first_death_done=first_death_done,
    )


class Stage2Result(NamedTuple):
    """Every value this stage updates, returned as one typed bundle.

    ``cst_balance`` and ``cst_funded_total`` are the same category of risk
    as Stage 1's ``filing``/``first_death_done``: both are seeded once
    before the year loop (from ``year_state.cst_balance`` /
    ``year_state.cst_funded_total``) and carried, reassigned, across every
    iteration -- the caller must reassign its own locals from this return
    value on every call. ``spousal_rollover``, ``estate_trust``, and
    ``cst_funded_yr`` are this-year-only reporting values the caller
    assigns onto ``row`` (mirroring ``row['cst_excluded_from_survivor_estate']
    = cst_funded_total`` after reassignment, since that field is the
    running total, not a per-year amount).
    """
    cst_balance: float
    cst_funded_total: float
    spousal_rollover: str
    estate_trust: str
    cst_funded_yr: float


def apply_spousal_rollover_and_cst_funding(
    c: dict[str, Any],
    *,
    year: int,
    h_alive: bool,
    w_alive: bool,
    bal: dict[str, float],
    bal_basis_free: dict[str, float],
    cst_balance: float,
    cst_funded_total: float,
    account_transfers_in: dict[str, float],
    account_transfers_out: dict[str, float],
    emit: Callable[[Any], None],
) -> Stage2Result:
    """Apply the year's spousal asset rollover at a death, and -- when a
    Credit Shelter (bypass) Trust is enabled -- fund it from the decedent's
    transferred assets.

    In original order:

    1. **Spousal rollover / terminal estate consolidation** -- delegates to
       the existing (already-extracted) ``planning_engines.apply_death_transition``
       for the actual balance-sheet mechanics of a death year, then emits an
       ``EvDeath`` plus one ``EvTransfer`` per moved account and records each
       transfer on the year's account-flow dicts.
    2. **CST funding** -- when a rollover happened, a bypass trust is
       enabled, and the survivor is identifiable, funds the trust (capped by
       the smaller of the plan's configured CST amount and its Illinois
       exemption-derived shelter cap) by pulling first from the survivor's
       taxable accounts, then cash accounts, tracking both the year's actual
       funded amount (``cst_funded_yr``, capped by what was actually
       available -- may be less than the nominal ``cap`` if the decedent's
       transferred assets or the survivor's taxable/cash balances run out)
       and the running lifetime total (``cst_funded_total``).

    ``bal`` and ``bal_basis_free`` are mutated in place by
    ``apply_death_transition`` itself (dict mutation crosses the function
    boundary naturally); this stage additionally mutates ``bal`` directly
    for the CST-funding draw. ``account_transfers_in``/``account_transfers_out``
    (normally the year's ``row['_account_transfers_in']``/
    ``row['_account_transfers_out']``) are mutated in place the same way.
    ``cst_balance`` and ``cst_funded_total`` do NOT mutate through their
    parameters -- see :class:`Stage2Result` for why they come back via the
    return value instead.
    """
    inher = _legacy_pe.apply_death_transition(c, bal, year, h_alive, w_alive, bal_basis_free)
    spousal_rollover = inher.description
    estate_trust = inher.estate_account or _aa.first_taxable(c) or ''
    if spousal_rollover:
        emit(EvDeath(year, 'member', spousal_rollover))
        for tr in inher.transfers:
            emit(EvTransfer(year, tr.from_acct, tr.to_acct, tr.amount, tr.reason))
            _add_account_flow(account_transfers_out, tr.from_acct, tr.amount)
            _add_account_flow(account_transfers_in, tr.to_acct, tr.amount)

    cst_funded_yr = 0.0
    if spousal_rollover and inher.survivor_owner_idx is not None and c.get('cs_enabled', False):
        available_from_decedent = sum(float(tr.amount or 0.0) for tr in inher.transfers)
        # #227: capped by the CST shelter cap (what a funded bypass trust can
        # remove from the survivor's estate), NOT il_exempt -- il_exempt is
        # the survivor's own separate exemption applied later; conflating the
        # two here would double-count the same dollars as both trust-sheltered
        # and separately exempt.
        _cst_cap = float(c.get('il_cst_shelter_cap', c.get('il_exempt', 0.0)) or 0.0)
        cap = max(0.0, min(float(c.get('cs_amount', _cst_cap) or 0.0), _cst_cap))
        cst_funded_yr = min(cap, max(0.0, available_from_decedent))
        # Actual CST funding: remove the funded amount from survivor-accessible
        # taxable/cash balances and track it as a separate estate-excluded trust
        # value. It remains part of household net worth but is not available to
        # the survivor withdrawal cascade or survivor estate base.
        _remaining_cst = cst_funded_yr
        _candidate_ids = []
        try:
            _candidate_ids.extend(_ar.ids_by_tax(c.get('account_registry', []), 'taxable', inher.survivor_owner_idx))
        except Exception:
            _candidate_ids.extend(c.get('taxable_ids', []))
        _candidate_ids.extend(c.get('cash_ids', []))
        for _aid in list(dict.fromkeys(_candidate_ids)):
            if _remaining_cst <= 0:
                break
            _take = min(_remaining_cst, float(bal.get(_aid, 0.0) or 0.0))
            if _take > 0:
                bal[_aid] = float(bal.get(_aid, 0.0) or 0.0) - _take
                _add_account_flow(account_transfers_out, _aid, _take)
                _remaining_cst -= _take
        _funded_actual = cst_funded_yr - max(0.0, _remaining_cst)
        cst_balance += _funded_actual
        cst_funded_total += _funded_actual
        cst_funded_yr = _funded_actual

    return Stage2Result(
        cst_balance=cst_balance,
        cst_funded_total=cst_funded_total,
        spousal_rollover=spousal_rollover,
        estate_trust=estate_trust,
        cst_funded_yr=cst_funded_yr,
    )


def _add_account_flow(target: dict[str, float], acct: str | None, amount: float) -> None:
    amount = float(amount or 0.0)
    if acct and abs(amount) > 1e-9:
        target[acct] = target.get(acct, 0.0) + amount
