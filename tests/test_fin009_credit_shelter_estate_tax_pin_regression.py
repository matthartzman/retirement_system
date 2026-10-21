"""FIN-009: pin the federal credit-shelter-trust (CST) estate-tax arithmetic.

``estimate_terminal_estate_tax`` subtracts the CST amount from the federal
taxable estate when portability is on, while still applying the full combined
exemption. The first decedent's exemption is then counted twice for the CST
dollars: once because the trust is removed from the survivor's estate, and
again inside the combined exemption.

Hand computation (federal rate 40%, plan_start == terminal year so no
indexing, no lifetime gifts, state estate tax off):

* Single, 15M exemption, 20M estate: (20M - 15M) * 40% = 2.0M.
* Couple, 30M combined exemption, 35M estate, 5M CST, portability ON. The
  trust consumes 5M of the first decedent's 15M exemption, so the survivor has
  10M of unused exemption (portability) plus their own 15M = 25M against a 30M
  estate: (30M - 25M) * 40% = 2.0M. The model returns 0.0.
* Same couple, portability OFF: the model does not subtract the CST and
  applies 30M: (35M - 30M) * 40% = 2.0M, which happens to equal the hand value.

The first test pins today's (wrong) output so any change is deliberate. The
strict xfail states the correct value and turns red the moment the arithmetic
is fixed, which is the cue to delete the pin and the xfail. Estate-attorney
review of the portability and CST treatment is still required (documented in
SYSTEM_REVIEW_2026-10-19_WAVE3_STATUS.md); until then credit-shelter outputs
are provisional.
"""
from __future__ import annotations

import pytest

from src.after_tax import estimate_terminal_estate_tax

M = 1_000_000.0


def _plan(**over):
    c = {"fed_exempt": 30 * M, "plan_start": 2026, "brk_inf": 0.02, "model_state_est": False}
    c.update(over)
    return c


def _terminal(total_nw, cst=0.0):
    return {"total_nw": total_nw, "year": 2026, "cst_excluded_from_survivor_estate": cst}


def test_single_household_estate_above_the_single_exemption():
    tax = estimate_terminal_estate_tax(_plan(fed_exempt=15 * M), _terminal(20 * M))
    assert tax == pytest.approx(2.0 * M)


def test_couple_without_a_credit_shelter_trust():
    tax = estimate_terminal_estate_tax(_plan(), _terminal(35 * M))
    assert tax == pytest.approx(2.0 * M)


def test_pin_cst_under_portability_currently_shows_zero_tax():
    """Known defect (FIN-009): returns 0.0 where the hand value is 2.0M."""
    tax = estimate_terminal_estate_tax(_plan(federal_portability_enabled=True), _terminal(35 * M, cst=5 * M))
    assert tax == 0.0


@pytest.mark.xfail(strict=True, reason="FIN-009: the CST is counted twice under portability; hand value is 2.0M")
def test_cst_under_portability_should_equal_the_hand_computed_tax():
    tax = estimate_terminal_estate_tax(_plan(federal_portability_enabled=True), _terminal(35 * M, cst=5 * M))
    assert tax == pytest.approx(2.0 * M)


def test_cst_without_portability_is_not_subtracted():
    tax = estimate_terminal_estate_tax(_plan(federal_portability_enabled=False), _terminal(35 * M, cst=5 * M))
    assert tax == pytest.approx(2.0 * M)


def test_understatement_is_forty_percent_of_the_cst_amount():
    on = estimate_terminal_estate_tax(_plan(federal_portability_enabled=True), _terminal(35 * M, cst=5 * M))
    off = estimate_terminal_estate_tax(_plan(federal_portability_enabled=False), _terminal(35 * M, cst=5 * M))
    assert off - on == pytest.approx(0.40 * 5 * M)
