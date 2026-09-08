from __future__ import annotations

from typing import Any, Callable

from ..planning_engines import niit_tax, social_security_taxable_amount, state_income_tax
from ..core import state_for_year


def compute_effective_marginal_rate(
    c: dict[str, Any],
    *,
    year: int,
    filing: str,
    agi: float,
    ded: float,
    ss_taxable: float,
    ss_total: float,
    portfolio_tax_exempt: float,
    earned_net: float,
    retirement_dist: float,
    ira_wd: float,
    note_int_yr: float,
    portfolio_ordinary: float,
    portfolio_qualified: float,
    nonqual_ann: float,
    roth_conv: float,
    nii: float,
    n_medicare: int,
    irmaa_magi_current: float,
    h_over_65: bool,
    compute_fed_tax: Callable[[float, int, str, Any], float],
    irmaa_tier: Callable[[float, int, str], int],
) -> tuple[float | None, bool]:
    """Diagnostic-only effective marginal rate for this year's household.

    The reported marginal rate (sheets_projection_tax) is the statutory
    bracket alone -- core.marginal_rate() just looks up the bracket
    containing taxable income. That understates what another dollar
    actually costs, sometimes badly: a household in the 12% bracket with
    taxable Social Security faces ~22.2% because each extra dollar also
    drags more benefit into taxation ("the Social Security torpedo"), and
    a dollar that crosses an IRMAA threshold costs hundreds.

    Perturb ordinary income by +$1,000 and re-run the pieces of the stack
    that respond to it within THIS year: SS inclusion, federal, state,
    and NIIT. Every function below is the same one the main path used
    this year, so the delta reflects this household's real position, not
    a table lookup.

    IRMAA is deliberately NOT perturbed here. `irmaa_yr` (this year's
    actual surcharge) is charged on `irmaa_magi`, the LOOKBACK MAGI from
    `c['irmaa_lookback_years']` years ago -- already fixed by history, and
    structurally incapable of responding to a dollar earned this year. An
    earlier version bumped that locked value anyway, which could
    manufacture huge phantom "cliffs": a $1,000 probe crossing a tier
    boundary on a value the dollar cannot actually move produced a
    measured 350% effective rate in a year with no real IRMAA event,
    caught by this file's own test_rate_is_never_absurd.

    What IS real: this year's marginal dollar raises irmaa_magi_current
    (this year's MAGI), which becomes the LOOKBACK figure for year+2 --
    so it can trigger a real, just deferred, IRMAA cost. That is flagged
    via the returned irmaa_cliff bool without folding a dollar amount for
    it into the rate, since attributing a future year's cost to this
    year's rate would need that future year's household composition and
    threshold inflation, not available from a single forward pass. Sheet
    7's note explains the flag.

    Also deliberately NOT included: the ACA premium-tax-credit cliff (it
    is resolved earlier in the year's flow and is not re-runnable from
    here) and LTCG stacking (this probe adds ordinary income, not gain).
    The rate is therefore a lower bound in ACA-subsidised bridge years
    and near an IRMAA threshold -- documented rather than silently
    approximated.

    Both sides of the delta are recomputed through the SAME calls.
    Comparing a recomputed "bumped" stack against the engine's own
    fed_tax/state_tax would be wrong: those carry true-up passes, AMT
    and settle-up adjustments this probe does not reproduce, so the
    difference would measure that mismatch rather than the marginal
    dollar.

    Returns (effective_marginal_rate, irmaa_cliff_flag). On any failure
    in the diagnostic calculation, returns (None, False) -- a diagnostic
    must never break a projection.
    """
    EMR_BUMP = 1000.0
    # Anchor on the year's FINAL position, not a mid-loop `non_ss_income`
    # snapshot: elective IRA/trust withdrawals are added to agi/taxable_inc
    # after that variable is set, so probing from it evaluates a poorer
    # household than the one the plan actually ends the year as -- which
    # showed up as effective rates a full bracket BELOW statutory.
    emr_non_ss_base = max(0.0, agi - ss_taxable)

    def emr_stack(extra_ordinary):
        non_ss = emr_non_ss_base + extra_ordinary
        ss_tax = social_security_taxable_amount(
            ss_total, non_ss + portfolio_tax_exempt, filing)
        cur_agi = max(0.0, non_ss + ss_tax)
        # `ded` is this year's actual deduction (max of standard vs itemized,
        # incl. the senior bonus), so the probe inherits the same
        # standard/itemized posture the real calculation landed on.
        taxable = max(0.0, cur_agi - ded)
        fed = compute_fed_tax(taxable, year, filing, c['brk_inf'])
        state = state_income_tax(
            state_for_year(c, year), earned_net, retirement_dist + ira_wd + extra_ordinary, ss_tax,
            note_int_yr + portfolio_ordinary + portfolio_qualified, nonqual_ann, roth_conv,
            year, h_over_65, filing=filing, brk_inf=c['brk_inf'])
        niit_v = niit_tax(nii or 0.0, cur_agi, filing)
        return fed + state + niit_v

    try:
        base_stack = emr_stack(0.0)
        bumped_stack = emr_stack(EMR_BUMP)
        effective_marginal_rate = (bumped_stack - base_stack) / EMR_BUMP
        # A future (year+2) IRMAA event: does the marginal dollar push
        # THIS year's own MAGI (irmaa_magi_current, not the locked
        # lookback irmaa_magi) across a tier it would otherwise not cross?
        if n_medicare > 0:
            base_tier = irmaa_tier(irmaa_magi_current, year, filing)
            bump_tier = irmaa_tier(irmaa_magi_current + EMR_BUMP, year, filing)
            irmaa_cliff = bump_tier > base_tier
        else:
            irmaa_cliff = False
        return effective_marginal_rate, irmaa_cliff
    except Exception:
        # A diagnostic must never break a projection.
        return None, False
