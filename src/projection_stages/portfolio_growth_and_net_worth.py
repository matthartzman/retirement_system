from __future__ import annotations

from typing import Any, Callable

from .. import planning_engines as _legacy_pe
from ..planning_engines import EvGrowth, EvWarning, annuity_cash_income


def apply_portfolio_growth_and_net_worth(
    c: dict[str, Any],
    *,
    year: int,
    h_alive: bool,
    w_alive: bool,
    bal: dict[str, float],
    row: dict[str, Any],
    emit: Callable[[Any], None],
    home_equity: float,
    home_val: float,
    autos_val: float,
    startup: float,
    note_bal: float,
    cst_balance: float,
    mort_bal_yr: float,
) -> None:
    """Apply end-of-year portfolio growth, value the annuity streams for net
    worth, and assemble the year's total net worth + liability breakdown.

    This is the LAST stage inside the per-year loop -- ``rows.append(row)``
    is the caller's very next statement after this returns. In original
    order:

    1. **Portfolio growth (EOY)** -- delegates to the existing
       ``planning_engines.apply_end_of_year_growth`` to grow every
       investable account in ``bal`` at ``c['ret']``, emitting one
       ``EvGrowth`` per account (via ``emit``) plus any ``EvWarning``s it
       raises. Snapshots every account balance onto ``row`` afterward so
       downstream validators/reports can read ``row[acct_id]`` directly.
    2. **Annuity PV for net worth** -- for each of the household's annuity/
       pension streams (single-life, joint-life, QLAC-folded, pension),
       present-values the remaining income payments through the relevant
       death year at ``c['ret']``, adding the year's Cash Refund death
       benefit in the death year itself if it hasn't yet eroded to $0.
    3. **Net worth assembly** -- sums the annuity PVs with every account
       bucket (pre-tax/Roth/taxable/HSA/cash), the CST balance, and
       "other" net worth (home equity, next-housing equity, depreciating
       autos, startup equity, note receivable, cash), then subtracts
       outstanding liabilities (mortgage, next-housing mortgage, HELOC,
       additional liability line items) to get ``total_nw``. Also computes
       the inflation-adjusted real net worth and a separate liability
       decomposition for the net-worth chart/table.
    4. **Death/final-year balance snapshot** -- at either death year or the
       plan's final year, copies the full ``bal`` dict onto
       ``row['_account_balances']`` (used later, in a different projection
       pass, for per-beneficiary drawdown at the second death) -- captured
       only at those years, not every year, to avoid bloating every row's
       serialized output.

    Nothing this stage computes is read again later in the *same* year
    (there is no code after this stage in the loop body besides
    ``rows.append(row)``) or carried into the *next* year via a bare local
    -- unlike other extracted stages' ``cst_balance``/``startup`` or
    ``filing``/``first_death_done``, none of this stage's outputs need a
    NamedTuple return to propagate back to the caller. Every output is
    either a mutation of ``bal`` (dict, mutates via reference) or of
    ``row`` (also mutated in place here, matching the canonical
    cash-flow-breakdown stage's precedent, and for the same reason: this
    stage's job is "reflect everything computed so far plus this year's
    terminal growth/valuation," not to hand back a small set of named
    scalars), so this function returns ``None``.

    ``home_equity``, ``home_val``, ``autos_val``, ``startup``, ``note_bal``,
    ``cst_balance``, and ``mort_bal_yr`` are read-only inputs here -- all
    are set by earlier stages this same year (or carried from setup) and
    none are reassigned by this stage, so they are accepted as plain
    parameters rather than through a result type.
    """
    # ── Portfolio growth (end-of-year) ───────────────────────────────────
    port_ret = c['ret']

    def _growth_event(acct, before, rate, growth):
        return EvGrowth(year, acct, before, rate, growth)

    growth_res = _legacy_pe.apply_end_of_year_growth(c, bal, port_ret, emit, _growth_event, year=year)
    row['_account_growth'] = dict(growth_res.by_account or {})
    for _msg in growth_res.warnings:
        emit(EvWarning(year, 'GROWTH_WARNING', _msg))

    # Snapshot end-of-year account balances so validators can use row[acct_id].
    for _acct_id in c['all_acct_ids']:
        row[_acct_id] = float(bal.get(_acct_id, 0.0) or 0.0)

    # ── Annuity value for net worth ──────────────────────────────────────
    # Value = PV of remaining income payments through the relevant death.
    #   - Single-life: PV of payments from this year through annuitant's death
    #   - Joint-life: PV through the second death (continues to survivor)
    # PLUS, in the death year only, if the Cash Refund death benefit hasn't
    # yet eroded to $0, add that year's death benefit (heirs receive the
    # unrecovered contribution as a lump sum).
    def ann_pv_to_death(stream, death_yr):
        """PV of annuity payments from current year through death_yr."""
        if year > death_yr:
            return 0.0
        pv = 0.0
        for y in range(year, death_yr + 1):
            pmt = annuity_cash_income(stream, y)
            pv += pmt / ((1 + c['ret']) ** (y - year))
        return pv

    second_death = max(c['h_death_yr'], c['w_death_yr'])
    db = c['ann_db'].get(year, {})

    # Single-life: value through that annuitant's death. #295: QLAC
    # income was folded into wife_single_ann/h_single_ann above, so its
    # remaining PV is folded into this same terminal-value bucket too --
    # a QLAC's own return-of-premium death benefit (if any) is not yet
    # modeled here (only the guaranteed-payment PV), matching how a
    # non-annuitized QLAC balance is otherwise absent from net worth.
    w_single_val = (ann_pv_to_death(c['wife_single'], c['w_death_yr']) +
                    (ann_pv_to_death(c['wife_qlac'], c['w_death_yr']) if c['wife_qlac'].get('enabled') else 0)) if w_alive else 0
    h_single_val = (ann_pv_to_death(c['h_single'], c['h_death_yr']) +
                    (ann_pv_to_death(c['h_qlac'], c['h_death_yr']) if c['h_qlac'].get('enabled') else 0)) if h_alive else 0
    # Joint-life: value through second death
    w_joint_val  = ann_pv_to_death(c['wife_joint'], second_death) if (w_alive or h_alive)  else 0
    h_joint_val  = ann_pv_to_death(c['h_joint'], second_death) if (h_alive or w_alive) else 0
    # Pension: PV through wife's death (no death benefit)
    pension_val  = ann_pv_to_death(c['wife_pension'], c['w_death_yr']) if w_alive else 0

    # Death benefit in the death year only (if DB still positive)
    if year == c['w_death_yr']:
        w_single_val += db.get('W_Single', 0)
    if year == c['h_death_yr']:
        h_single_val += db.get('H_Single', 0)
    if year == second_death:
        w_joint_val += db.get('W_Joint', 0)
        h_joint_val += db.get('H_Joint', 0)

    row.update({'pension_pv': pension_val,
                'w_single_pv': w_single_val, 'w_joint_pv': w_joint_val,
                'h_single_pv': h_single_val, 'h_joint_pv': h_joint_val})

    # ── Net Worth ────────────────────────────────────────────────
    ann_nw = pension_val + w_single_val + w_joint_val + h_single_val + h_joint_val
    pretax_nw = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('pre_tax_ids', []))
    roth_nw   = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('roth_ids', []))
    trust_nw  = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('taxable_ids', []))
    hsa_nw    = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('hsa_ids', []))
    cash_nw   = sum(max(0.0, float(bal.get(_id, 0.0) or 0.0)) for _id in c.get('cash_ids', []))
    cst_nw    = max(0.0, float(cst_balance or 0.0))

    # other_nw = current home equity + next-housing equity + depreciating assets + note receivable + cash
    next_housing_equity = float(row.get('next_housing_equity', 0.0) or 0.0)
    other_nw = home_equity + next_housing_equity + autos_val + float(startup or 0.0) + float(note_bal or 0.0) + cash_nw

    # Outstanding balances on additional liabilities (auto/student/other/heloc
    # line items) directly reduce net worth. Empty for a liability-free plan.
    additional_liabilities = float(sum((bal.get('_liability_balances', {}) or {}).values()))

    total_nw = ann_nw + pretax_nw + roth_nw + trust_nw + cst_nw + hsa_nw + other_nw - additional_liabilities

    # Inflation-adjusted real NW (for trend analysis)
    inflation_cumu = float(row.get('inflation_cumu') or 1.0) or 1.0
    total_nw_real = total_nw / inflation_cumu

    # Liability decomposition (for NW chart and table)
    heloc_liability = float(bal.get('_heloc_balance', 0.0) or 0.0)
    next_housing_mortgage_balance = float(row.get('next_housing_mortgage_balance', 0.0) or 0.0)
    total_liabilities = mort_bal_yr + next_housing_mortgage_balance + heloc_liability + additional_liabilities

    row.update({
        'ann_nw': ann_nw,
        'pretax_nw': pretax_nw,
        'roth_nw': roth_nw,
        'trust_nw': trust_nw,
        'hsa_nw': hsa_nw,
        'cash_nw': cash_nw,
        'cst_nw': cst_nw,
        'other_nw': other_nw,
        'total_nw': total_nw,
        'total_nw_real': total_nw_real,
        'home_equity': home_equity,
        'home_val': home_val,
        'next_housing_equity': next_housing_equity,
        'next_housing_home_value': float(row.get('next_housing_home_value', 0.0) or 0.0),
        'next_housing_mortgage_balance': next_housing_mortgage_balance,
        'startup_val': float(startup or 0.0),
        'autos_val': float(autos_val or 0.0),
        'note_bal': float(note_bal or 0.0),
        'mort_bal_yr': mort_bal_yr,
        'heloc_liability': heloc_liability,
        'additional_liabilities': additional_liabilities,
        'total_liabilities': total_liabilities,
    })
    # Item 4.9 (P5 phase 2): a per-account balance snapshot, needed to
    # inherit each retirement account individually at the second death
    # (per-beneficiary drawdown reads whichever account the decedent's
    # accounts actually held, not just the household pretax_nw/roth_nw
    # aggregate). Captured only at the two possible death years and the
    # final row -- not every year -- to avoid bloating every row's JSON/
    # workbook serialization with a full account-balance copy.
    if year in {int(c.get('h_death_yr', 0) or 0), int(c.get('w_death_yr', 0) or 0), int(c.get('plan_end', 0) or 0)}:
        row['_account_balances'] = dict(bal)
