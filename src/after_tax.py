"""After-tax terminal value helpers.

These helpers estimate embedded taxes that have not yet been paid by the end of
projection.  They are intentionally conservative and auditable: ordinary tax on
remaining pre-tax retirement accounts is modeled separately from deferred long-
term capital-gains tax on remaining taxable brokerage assets.
"""
from __future__ import annotations

from typing import Any, Mapping, Dict, Tuple

from .core import ltcg_tax_on_gain, niit_tax, state_income_tax, illinois_estate_tax


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _terminal_account_balance(terminal: Mapping[str, Any], account_id: str) -> float:
    return max(0.0, _f(terminal.get(account_id), 0.0))


# Historical flat ordinary-income assumption for inherited pre-tax balances.
# Item 4.3 replaces this constant as the *default* with a bracket-derived
# effective rate; an equal value in config is therefore treated as "use the
# derived default", while any other value is honored as a deliberate override.
FLAT_HEIR_ORDINARY_RATE = 0.24


def _normalize_rate(value: Any, default: float = 0.24) -> float:
    r = _f(value, default)
    if abs(r) > 1:
        r = r / 100.0
    return max(0.0, min(1.0, r))


def _heir_filing_status(c: Mapping[str, Any]) -> str:
    filing = str(c.get("roth_heir_filing_status", "Single") or "Single").strip()
    return filing if filing in ("Single", "MFJ", "HOH", "MFS") else "Single"


def _is_flat_default(value: Any) -> bool:
    """True when a configured rate is absent or equals the historical flat 24%.

    Only in that case is the bracket-derived effective rate substituted; a user
    who set any other value keeps it (an explicit override is honored).
    """
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return True
    return abs(_normalize_rate(value) - FLAT_HEIR_ORDINARY_RATE) < 1e-6


def effective_heir_ten_year_rate(c: Mapping[str, Any], pretax_balance: Any,
                                 terminal_year: Any = None) -> float:
    """Effective ordinary tax rate an heir pays on an inherited pre-tax balance.

    Item 4.3 (SECURE Act 10-year rule, level-distribution simplification): the
    terminal pre-tax balance is spread evenly over 10 years (no growth), each
    annual slice is taxed as the heir's only ordinary income at the assumed heir
    filing status, and the ten years of federal tax are summed and divided by
    the total balance. Bracket-filling makes this rate rise with the balance: a
    small IRA's slices stay in low brackets (effective rate below 24%) while a
    large IRA's slices push into higher brackets (effective rate above 24%) --
    exactly the sensitivity a flat constant cannot express. Brackets inflate to
    each distribution year via the plan's bracket inflator, so the rate is
    consistent with the nominal terminal balance it is applied to.
    """
    from .core import compute_fed_tax

    bal = max(0.0, _f(pretax_balance, 0.0))
    if bal <= 0:
        return 0.0
    filing = _heir_filing_status(c)
    brk_inf = _f(c.get("brk_inf", 0.0), 0.0)
    if terminal_year is None:
        terminal_year = c.get("plan_end", c.get("plan_start", 0))
    year0 = int(_f(terminal_year, 0.0))
    annual = bal / 10.0
    total_tax = sum(compute_fed_tax(annual, year0 + i, filing, brk_inf) for i in range(10))
    return max(0.0, min(1.0, total_tax / bal))


def resolve_terminal_pretax_rate(c: Mapping[str, Any], pretax_balance: Any,
                                 terminal_year: Any = None) -> float:
    """Rate for the terminal pre-tax deferred-tax haircut: user override else derived."""
    configured = c.get("roth_optimize_terminal_tax_rate", c.get("roth_target_rate"))
    if not _is_flat_default(configured):
        return _normalize_rate(configured)
    return effective_heir_ten_year_rate(c, pretax_balance, terminal_year)


def resolve_heir_ordinary_rate(c: Mapping[str, Any], pretax_balance: Any,
                               terminal_year: Any = None) -> float:
    """Heir ordinary-income rate for legacy scoring: user override else derived."""
    configured = c.get("roth_heir_ordinary_tax_rate_assumption")
    if not _is_flat_default(configured):
        return _normalize_rate(configured)
    return effective_heir_ten_year_rate(c, pretax_balance, terminal_year)


def estimate_terminal_pretax_deferred_tax(c: Mapping[str, Any], terminal: Mapping[str, Any]) -> Dict[str, float]:
    """Estimate deferred ordinary-income tax on remaining pre-tax retirement assets.

    The haircut rate is no longer a flat 24% constant: unless the user set an
    explicit ``roth_optimize_terminal_pretax_tax_rate``, it is derived from the
    terminal pre-tax balance via the SECURE Act 10-year-rule level distribution
    (see :func:`effective_heir_ten_year_rate`).
    """
    terminal_pretax = max(0.0, _f(terminal.get("pretax_nw"), 0.0))
    terminal_year = terminal.get("year", c.get("plan_end", c.get("plan_start", 0)))
    rate = resolve_terminal_pretax_rate(c, terminal_pretax, terminal_year)
    tax = terminal_pretax * rate
    return {
        "terminal_pretax_nw": terminal_pretax,
        "terminal_pretax_deferred_tax_rate": rate,
        "terminal_deferred_pretax_tax": tax,
    }


def _lot_mv_basis_for_account(c: Mapping[str, Any], account_id: str) -> Tuple[float, float]:
    """Return remaining lot market value and basis for an account.

    The projection's LotEngine mutates quantities and basis when taxable lots are
    sold.  Because account balances receive annual growth at the account level,
    terminal balances may not equal current-price lot market value.  We therefore
    use the residual lot basis ratio and apply that ratio to terminal balances.
    """
    lot_engine = c.get("lot_engine")
    if not lot_engine or not getattr(lot_engine, "lots", None):
        return 0.0, 0.0
    lots_by_symbol = (getattr(lot_engine, "lots", {}) or {}).get(account_id, {}) or {}
    prices = getattr(lot_engine, "prices", {}) or {}
    mv = 0.0
    basis = 0.0
    for sym, lots in lots_by_symbol.items():
        sym_u = str(sym or "").strip().upper()
        for lot in list(lots or []):
            qty = max(0.0, _f(getattr(lot, "qty", 0.0), 0.0))
            lot_basis = max(0.0, _f(getattr(lot, "cost_basis", 0.0), 0.0))
            price = _f(prices.get(sym_u, prices.get(sym, 0.0)), 0.0)
            if price <= 0 and qty > 0:
                price = lot_basis / qty if lot_basis > 0 else 0.0
            mv += qty * max(0.0, price)
            basis += lot_basis
    return mv, basis


def _step_up_regime(c: Mapping[str, Any]) -> str:
    return str(c.get("basis_step_up_property_regime", "COMMON_LAW") or "COMMON_LAW").strip().upper()


def _second_death_step_fraction(c: Mapping[str, Any]) -> float:
    """Fraction of household taxable gain stepped up when the *last* member dies.

    At the second death the entire estate belongs to the decedent, so §1014
    steps up the full basis under both common-law and community-property
    regimes.  A HALF_STEP_UP configuration only steps up half.  Mirrors
    planning_engines._basis_step_fraction_for_death(first_death=False).
    """
    return 0.5 if _step_up_regime(c) == "HALF_STEP_UP" else 1.0


def _first_death_step_fraction(c: Mapping[str, Any]) -> float:
    """Household-level taxable-gain fraction stepped up at the *first* death.

    Only the decedent's share steps up in common law (~50% of jointly-held
    assets), while community-property (and explicit FULL_STEP_UP) regimes step
    up both spouses' halves — the classic double step-up the projection already
    models at first death (see planning_engines.apply_death_transition, which
    steps up the survivor's taxable accounts in full under those regimes).
    """
    regime = _step_up_regime(c)
    if regime in {"COMMUNITY_PROPERTY", "FULL_STEP_UP"}:
        return 1.0
    if regime == "HALF_STEP_UP":
        return 0.25  # half of the decedent's ~50% share
    return 0.5  # common law: decedent's ~50% share only


def _terminal_step_up_case(c: Mapping[str, Any], terminal: Mapping[str, Any]):
    """Classify the terminal year against the household death timeline.

    Returns (case, stepped_fraction, note):
      - 'second_death' — both members are dead by the terminal year: the full
        estate receives a §1014 step-up (scaled by regime).
      - 'first_death'  — the terminal year is at/after the first death but a
        survivor is still alive (or the horizon ends before the second death):
        only the decedent's share steps up; the survivor's share retains its
        deferred gain.
      - 'both_alive'   — the horizon ends before any death: no step-up occurs,
        the deferred gain is retained in full.
    ``stepped_fraction`` is 0.0 whenever basis_step_up_at_death is disabled.
    """
    if not bool(c.get("basis_step_up_at_death", True)):
        return "both_alive", 0.0, "basis step-up at death disabled — deferred gain retained in full"

    h_death = int(_f(c.get("h_death_yr"), 0.0))
    w_death = int(_f(c.get("w_death_yr"), 0.0))
    members = c.get("members", []) or []
    hh_size = int(_f(c.get("household_size", len(members)), 0.0))
    term_year = int(_f(terminal.get("year", c.get("plan_end", c.get("plan_start", 0))), 0.0))

    deaths = [d for d in (h_death, w_death) if d > 0]
    second_death = max(deaths) if deaths else 0
    first_death = min(deaths) if deaths else 0
    # A single-member household carries a synthetic spouse whose "death year" is
    # in the past; that is not a real first death, so the member's own death is
    # both the first and the (terminal) second death.
    if hh_size <= 1:
        first_death = second_death

    if second_death and term_year >= second_death:
        return ("second_death", _second_death_step_fraction(c),
                "terminal year is the second death — full §1014 step-up on the whole estate")
    if first_death and term_year >= first_death:
        return ("first_death", _first_death_step_fraction(c),
                "one member survives the terminal year — only the decedent's share steps up; "
                "the survivor's share retains its deferred gain")
    return ("both_alive", 0.0,
            "horizon ends with both members alive — deferred gain retained (no step-up)")


def estimate_terminal_taxable_deferred_cap_gain_tax(c: Mapping[str, Any], terminal: Mapping[str, Any]) -> Dict[str, float]:
    """Estimate deferred tax on unrealized gains in taxable brokerage accounts.

    Uses residual lot basis when available.  If lot data is unavailable, falls
    back to the model's trust_gain_fraction, matching the projection's taxable
    withdrawal fallback.  The deferred tax estimate includes federal LTCG tax,
    NIIT when enabled, and incremental state tax on taxable investment gains.

    §1014 step-up in basis at death is applied to the *gross* embedded gain
    before any tax is computed, branching on whether the terminal year lands at
    the second death (full step-up), after the first death with a survivor still
    alive (decedent's share only), or before any death (no step-up).  Taxing the
    full gain as if there were no step-up — while the same codebase grants the
    step-up during life — over-states the terminal tax drag and, because this
    metric dominates the Roth-conversion objective, systematically inflates the
    recommended conversions.
    """
    taxable_ids = list(c.get("taxable_ids") or [])
    terminal_taxable = sum(_terminal_account_balance(terminal, aid) for aid in taxable_ids)
    if terminal_taxable <= 0:
        terminal_taxable = max(0.0, _f(terminal.get("trust_nw"), 0.0))
    fallback_gain_fraction = max(0.0, min(1.0, _f(c.get("trust_gain_fraction"), 0.50)))

    taxable_basis = 0.0
    unrealized_gain = 0.0
    lot_covered_balance = 0.0
    fallback_balance = 0.0

    for aid in taxable_ids:
        bal = _terminal_account_balance(terminal, aid)
        if bal <= 0:
            continue
        lot_mv, lot_basis = _lot_mv_basis_for_account(c, aid)
        if lot_mv > 0:
            # Apply the residual basis ratio to terminal balance.  This makes the
            # estimate compatible with account-level growth that is not reflected
            # as updated lot prices.
            basis_ratio = lot_basis / lot_mv if lot_mv > 0 else 0.0
            basis_est = max(0.0, bal * basis_ratio)
            taxable_basis += basis_est
            unrealized_gain += max(0.0, bal - basis_est)
            lot_covered_balance += bal
        else:
            fallback_balance += bal
            gain_est = bal * fallback_gain_fraction
            unrealized_gain += gain_est
            taxable_basis += max(0.0, bal - gain_est)

    # If terminal trust_nw was populated but account-level taxable IDs were not,
    # still make the deferred gain assumption explicit.
    if terminal_taxable > 0 and lot_covered_balance + fallback_balance <= 0:
        fallback_balance = terminal_taxable
        unrealized_gain = terminal_taxable * fallback_gain_fraction
        taxable_basis = max(0.0, terminal_taxable - unrealized_gain)

    # §1014 step-up: the gain accumulated above is the *gross* embedded gain.
    # Eliminate the stepped-up portion before computing any tax, so the terminal
    # metric is coherent with the step-up the projection grants during life.
    gross_unrealized_gain = unrealized_gain
    step_case, step_fraction, step_note = _terminal_step_up_case(c, terminal)
    step_fraction = max(0.0, min(1.0, step_fraction))
    stepped_up_gain = gross_unrealized_gain * step_fraction
    retained_gain = max(0.0, gross_unrealized_gain - stepped_up_gain)
    # Assumed basis a reader can audit: original cost basis plus the portion of
    # the embedded gain that the step-up lifts into basis.
    assumed_basis = taxable_basis + stepped_up_gain

    filing = str(c.get("filing_status", "MFJ") or "MFJ")
    year = int(_f(terminal.get("year", c.get("plan_end", c.get("plan_start", 0))), 0))
    ordinary_income_base = max(0.0, _f(terminal.get("taxable_inc"), 0.0))
    federal_ltcg_tax = ltcg_tax_on_gain(c, retained_gain, ordinary_income_base, year) if retained_gain > 0 else 0.0

    niit = 0.0
    if bool(c.get("model_niit", True)) and retained_gain > 0:
        terminal_agi = max(0.0, _f(terminal.get("agi", ordinary_income_base), ordinary_income_base))
        # Liquidating the terminal taxable portfolio would add the gain to both
        # NII and MAGI.  Existing terminal NII is not always stored, so this is a
        # conservative standalone liquidation estimate.
        niit = niit_tax(retained_gain, terminal_agi + retained_gain, filing)

    state_tax = 0.0
    if retained_gain > 0:
        state = str(c.get("state", "Illinois") or "Illinois")
        age_over_65 = True
        state_tax = state_income_tax(
            state,
            earned=0.0,
            retirement_dist=0.0,
            ss_taxable=0.0,
            investment_inc=retained_gain,
            nonqual_annuity=0.0,
            roth_conv=0.0,
            year=year,
            age_over_65=age_over_65,
            filing=filing,
        )

    total_tax = max(0.0, federal_ltcg_tax + niit + state_tax)
    return {
        "terminal_taxable_nw": terminal_taxable,
        "terminal_taxable_basis_est": assumed_basis,
        "terminal_taxable_unrealized_gain_est": retained_gain,
        "terminal_taxable_gross_unrealized_gain_est": gross_unrealized_gain,
        "terminal_taxable_stepped_up_gain_est": stepped_up_gain,
        "terminal_step_up_case": step_case,
        "terminal_step_up_fraction": step_fraction,
        "terminal_step_up_note": step_note,
        "terminal_taxable_lot_covered_balance": lot_covered_balance,
        "terminal_taxable_fallback_gain_balance": fallback_balance,
        "terminal_taxable_fallback_gain_fraction": fallback_gain_fraction,
        "terminal_deferred_ltcg_tax": federal_ltcg_tax,
        "terminal_deferred_niit_tax": niit,
        "terminal_deferred_state_cap_gain_tax": state_tax,
        "terminal_deferred_taxable_cap_gain_tax": total_tax,
    }


def business_taxable_estate_value(c: Mapping[str, Any]) -> float:
    """Owner's projected business-interest value added to the taxable estate.

    Returns 0.0 unless the business-succession module is enabled. An illiquid
    business interest (or the cash from its buy-sell) remains in the gross estate,
    so the owner's share — projected to plan-end at the entity growth rate — is
    added to the estate-tax base. Gated purely on the saved toggle so default
    plans are unaffected.
    """
    if not (c.get("opt") or {}).get("business_succession"):
        return 0.0
    base_year = int(_f(c.get("plan_start"), 0.0))
    plan_end = int(_f(c.get("plan_end"), base_year))
    total = 0.0
    for e in c.get("business_succession", []) or []:
        val_today = _f(e.get("valuation_today"), 0.0)
        growth = _f(e.get("valuation_growth_rate"), 0.0)
        own = _f(e.get("ownership_pct"), 0.0)
        # A buy-sell crystallizes the interest at the transfer year; the estate
        # then holds the (conservatively flat) proceeds, so growth stops there.
        transfer = int(_f(e.get("transfer_year"), 0.0))
        val_year = min(plan_end, transfer) if 0 < transfer < plan_end else plan_end
        total += val_today * ((1.0 + growth) ** max(0, val_year - base_year)) * own
    return max(0.0, total)


def estimate_terminal_estate_tax(c: Mapping[str, Any], terminal: Mapping[str, Any]) -> float:
    """Estimate federal + state estate tax on the terminal estate.

    Federal: 40% on the taxable estate above the federal exemption.  State:
    Illinois graduated estate tax above the state exemption (only when state
    estate tax is modeled).  Mirrors the optimizer's per-row estate-tax model.
    When the business-succession module is on, the owner's business interest is
    added to the taxable estate.
    """
    row_total = max(0.0, _f(terminal.get("total_nw"), 0.0))
    row_cst = max(0.0, _f(terminal.get("cst_excluded_from_survivor_estate"), 0.0))
    biz = business_taxable_estate_value(c)
    fed_exempt = max(0.0, _f(c.get("fed_exempt"), 0.0))
    state_exempt = max(0.0, _f(c.get("il_exempt"), 0.0))
    federal_taxable = max(0.0, row_total + biz - (row_cst if c.get("federal_portability_enabled", True) else 0.0))
    state_taxable = max(0.0, row_total + biz - row_cst)
    federal_tax = max(0.0, federal_taxable - fed_exempt) * 0.40 if fed_exempt else 0.0
    state_tax = illinois_estate_tax(state_taxable, state_exempt) if c.get("model_state_est", True) and state_exempt else 0.0
    return max(0.0, federal_tax + state_tax)


def estimate_after_tax_terminal_net_worth(c: Mapping[str, Any], terminal: Mapping[str, Any]) -> Dict[str, float]:
    """Return gross terminal NW, embedded tax components, after-tax NW, and PTI.

    Post-Tax Inheritance (PTI) = after-tax terminal net worth minus estimated
    estate tax = what beneficiaries actually keep.
    """
    terminal_nw = _f(terminal.get("total_nw"), 0.0)
    pretax = estimate_terminal_pretax_deferred_tax(c, terminal)
    taxable = estimate_terminal_taxable_deferred_cap_gain_tax(c, terminal)
    total_deferred = pretax["terminal_deferred_pretax_tax"] + taxable["terminal_deferred_taxable_cap_gain_tax"]
    after_tax = terminal_nw - total_deferred
    estate_tax = estimate_terminal_estate_tax(c, terminal)
    return {
        "terminal_nw": terminal_nw,
        **pretax,
        **taxable,
        "terminal_deferred_tax_total": total_deferred,
        "after_tax_terminal_nw": after_tax,
        "after_tax_terminal_net_worth": after_tax,
        "terminal_estate_tax": estate_tax,
        "post_tax_inheritance": after_tax - estate_tax,
    }
