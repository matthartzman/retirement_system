"""The reported marginal rate must reflect what a dollar actually costs.

System review 2026-08-04, financial-planner finding `marginal-rate-statutory-only`:
sheets_projection_tax reported ``core.marginal_rate()``, which is a bare bracket
lookup. It omits every effect that makes retirement marginal rates differ from
the bracket -- most importantly the Social Security "torpedo", where each extra
dollar of ordinary income also drags up to $0.85 more benefit into taxable
income, so a household sitting in the 12% bracket really faces 22.2%.

The engine now computes an effective marginal rate by perturbing ordinary income
by +$1,000 and re-running SS inclusion, federal, state, NIIT and IRMAA through
the same functions the year itself used.
"""
from __future__ import annotations

import pytest

from conftest import TEST_INPUT_DIR
from src.core import marginal_rate, social_security_taxable_amount
from src.data_io import load_csv
from src.planning_engines import project
from src.report_compute import prepare_config_from_sectioned_data


@pytest.fixture(scope="module")
def projected():
    c = prepare_config_from_sectioned_data(load_csv(TEST_INPUT_DIR / "client_data.csv"))
    return c, project(c)


def test_every_year_reports_an_effective_marginal_rate(projected):
    _c, rows = projected
    missing = [r["year"] for r in rows if r.get("effective_marginal_rate") is None]
    assert not missing, f"effective_marginal_rate missing for years: {missing}"


def test_rate_is_never_absurd(projected):
    """Guards the failure mode this landed with in development.

    An early version compared a freshly recomputed 'bumped' stack against the
    engine's own fed_tax/state_tax, which carry true-up and settle-up passes the
    probe does not reproduce. The difference measured that mismatch rather than
    the marginal dollar and produced rates like -3487%. Both sides must come
    from the same code path.
    """
    _c, rows = projected
    bad = [(r["year"], r["effective_marginal_rate"]) for r in rows
           if not (-0.10 <= r["effective_marginal_rate"] <= 1.50)]
    assert not bad, f"implausible effective marginal rates: {bad}"


def test_effective_rate_is_at_least_the_statutory_bracket(projected):
    """Add-ons can only push the cost of a marginal dollar up, never down.

    A rate below the bracket means the probe is evaluating a different (poorer)
    household than the one the year actually ended as -- the second failure mode
    hit in development, when the baseline was taken from a mid-loop snapshot
    that predated elective IRA withdrawals.
    """
    c, rows = projected
    below = []
    for r in rows:
        statutory = marginal_rate(r["taxable_inc"], r["year"], r["filing"], c["brk_inf"])
        if r["effective_marginal_rate"] < statutory - 1e-6:
            below.append((r["year"], statutory, r["effective_marginal_rate"]))
    assert not below, (
        "effective marginal rate fell below the statutory bracket in "
        f"{len(below)} year(s): {below[:5]}"
    )


def test_social_security_torpedo_is_detected(projected):
    """The frozen household has years where SS inclusion is still phasing in.

    In those years the effective rate must exceed the bracket. This is the
    concrete case the finding cited: 12% statutory -> 22.2% effective, which is
    12% x 1.85 (each extra dollar also taxes $0.85 more of the benefit).
    """
    c, rows = projected
    torpedo = []
    for r in rows:
        statutory = marginal_rate(r["taxable_inc"], r["year"], r["filing"], c["brk_inf"])
        pct = r.get("ss_taxable_pct_actual") or 0.0
        # Inclusion strictly between 0 and the 85% cap => still phasing in.
        if 0.0 < pct < 0.85 - 1e-9 and r["effective_marginal_rate"] > statutory + 1e-6:
            torpedo.append((r["year"], statutory, r["effective_marginal_rate"]))
    assert torpedo, (
        "no year showed a Social Security torpedo, but the frozen plan has years "
        "with partial SS inclusion -- the effective rate is probably not "
        "re-running social_security_taxable_amount under the perturbation"
    )
    # At least one should land near the textbook 1.85x multiple of the bracket.
    assert any(abs(eff - stat * 1.85) < 0.02 for _yr, stat, eff in torpedo), (
        f"expected a ~1.85x bracket multiple somewhere in {torpedo[:5]}"
    )


def test_torpedo_multiple_matches_a_hand_calculation():
    """Independent check of the mechanism, no engine involved.

    At $40k of other income and $40k of benefits, MFJ, the taxability worksheet
    is in its 85% phase-in band, so $1,000 more ordinary income should add
    materially more than $1,000 to taxable income.
    """
    base = social_security_taxable_amount(40_000.0, 40_000.0, "MFJ")
    bumped = social_security_taxable_amount(40_000.0, 41_000.0, "MFJ")
    extra_taxable = (bumped - base) + 1_000.0
    assert extra_taxable > 1_000.0, "SS inclusion did not rise with other income"
    assert extra_taxable == pytest.approx(1_850.0, abs=1.0), (
        f"expected the 85% phase-in to make $1,000 behave like $1,850, got {extra_taxable}"
    )


def test_irmaa_cliff_flag_is_boolean_everywhere(projected):
    _c, rows = projected
    assert all(isinstance(r.get("effective_marginal_rate_irmaa_cliff"), bool) for r in rows)
