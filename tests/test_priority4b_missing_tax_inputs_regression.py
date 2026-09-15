"""Priority 4b must not crash when Priority 3 never ran.

Withdrawal-cascade sub-stage #4 (Priority 3, the bracket-capped pre-tax
elective draw) computes ``top_24_yr``/``irmaa_thr_yr``/``marg`` and the
true-up baselines only when it sees ``gap > 0``; sub-stage #7 (Priority 4b,
the final pre-tax draw before any Roth withdrawal) reuses them. But the
cascade between the two -- Priority 4's taxable/trust draw and the LTCG/NIIT
fixed-point loop -- can reopen a gap that was closed, or zero, when #4
looked at it. #7 then fired with all three still ``None`` and died inside
``planning_engines.withdraw_pretax_elective``'s
``min(bracket_top_24, irmaa_threshold)``::

    TypeError: '<' not supported between instances of 'NoneType' and 'NoneType'

...taking down the whole projection, in the observed case over a residual
gap of a fifth of a cent.

Found by running the housing optimizer against the committed demo plan
(every candidate it evaluates is a plan-config variant, and one of them put
that plan's 2027 into exactly this state). The reproduction is NOT pinned
here as a whole-plan projection on purpose: which year lands on this
knife-edge shifts with holdings prices, the pinned clock, and the YTD blend,
so such a test would keep passing while quietly no longer exercising the
bug -- observed directly while writing this. The sub-stage is called
straight instead, with the ``None`` inputs the engine really passed it.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.planning_engines import FEDERAL_BRACKETS_MFJ
from src.projection_stages.withdrawal_cascade_ira_true_up import (
    apply_priority_4b_final_pretax_draw,
)

pytestmark = pytest.mark.unit

_YEAR = 2027
_IRA_ID = "h_ira"
_START_BALANCE = 500_000.0


def _inflate_brackets(brackets, _inflator_unused, _years_from_plan_start):
    """Stand-in for the engine's own bracket-inflation path, with the
    inflation factor fixed at 1.0 -- this test is about ``None`` handling,
    not about bracket indexing."""
    return list(brackets)


def _no_further_tax(fed_tax, state_tax, *_args, **_kwargs):
    """``ira_elective_tax_delta_fn`` stand-in reporting no incremental tax,
    so the shared true-up loop settles on its first pass. The defect is in
    sizing the draw, ahead of any true-up."""
    return 0.0, fed_tax, state_tax


def _config() -> dict[str, Any]:
    return {
        "plan_start": 2026,
        "irmaa_base": 206_000.0,
        "brk_inf": 0.0,
        "account_registry": [{"id": _IRA_ID, "owner_idx": 0, "tax": "pre_tax"}],
        "pre_tax_ids": [_IRA_ID],
        "tax_withdrawal_fixed_point_iterations": 3,
    }


def _kwargs(**overrides) -> dict[str, Any]:
    """Sub-stage #7's arguments as the engine passes them when sub-stage #4
    was skipped: everything #4 would have produced arrives as ``None``."""
    kwargs: dict[str, Any] = dict(
        year=_YEAR, filing="MFJ", gap=40_000.0, agi=180_000.0, taxable_inc=150_000.0,
        fed_tax=25_000.0, state_tax=5_000.0, payroll_tax=0.0, irmaa_yr=0.0,
        total_tax_pre_niit=30_000.0, ltcg_tax=0.0, niit=0.0, tlh_ordinary_credit=0.0,
        total_spend_need=120_000.0, other_cash_need_yr=0.0, irmaa_magi_current=180_000.0,
        retirement_dist=0.0, rmd_h=0.0, rmd_w=0.0, spend=120_000.0,
        ss_taxable=0.0, earned_net=0.0, note_int_yr=0.0,
        portfolio_ordinary=0.0, portfolio_qualified=0.0, nonqual_ann=0.0,
        roth_conv=0.0, h_over_65=False,
        ira_wd=0.0, h_ira_elective=0.0, w_ira_elective=0.0,
        pretax_by_account={}, ira_tax_true_up_iterations=0,
        # The crux: sub-stage #4's `gap > 0` guard did not fire, so it
        # produced none of these.
        top_24_yr=None, irmaa_thr_yr=None, marg=None,
        ira_taxable_inc_orig=None, ira_retirement_dist_orig=None,
        brk_inf=None, inflate_brackets_fn=_inflate_brackets,
        ira_elective_tax_delta_fn=_no_further_tax,
    )
    kwargs.update(overrides)
    return kwargs


def _run(*, config=None, **overrides):
    bal = {_IRA_ID: _START_BALANCE}
    row: dict[str, Any] = {"_account_withdrawals": {}}
    result = apply_priority_4b_final_pretax_draw(
        config if config is not None else _config(), bal, row, **_kwargs(**overrides)
    )
    return result, bal, row


def test_residual_gap_is_funded_when_priority_3_left_its_tax_inputs_unset():
    # A sub-cent residual gap is what the real failure carried.
    result, bal, row = _run(gap=0.0023)

    assert result.ira_wd > 0.0, "Priority 4b drew nothing for a positive gap"
    assert result.gap <= 0.0023, "the residual gap was not reduced"
    assert bal[_IRA_ID] < _START_BALANCE, "the pre-tax balance was never touched"
    assert row["_account_withdrawals"].get(_IRA_ID, 0.0) > 0.0


def test_large_gap_is_funded_when_priority_3_left_its_tax_inputs_unset():
    # Not only a rounding residue: the same path has to work for a gap big
    # enough to matter, since it is the last stop before Roth.
    result, bal, _row = _run(gap=40_000.0)

    # Grossed up for the tax the withdrawal itself creates (the derived
    # marginal rate is 22% at this taxable income): 40,000 / (1 - 0.22).
    assert result.ira_wd == pytest.approx(40_000.0 / 0.78, rel=1e-6)
    assert bal[_IRA_ID] == pytest.approx(_START_BALANCE - result.ira_wd, rel=1e-6)
    # respect_tax_caps=False is this sub-stage's whole point: the draw is
    # sized by the gap and the available balance, never held back by the
    # bracket ceiling it just derived.
    assert result.gap <= 0.0, "the gap was not fully funded"


def test_priority_3_values_are_reused_untouched_when_it_did_run():
    # The normal path must not start recomputing anything. Passing
    # marg=0.0 -- a rate no derivation would arrive at -- makes the two
    # cases tell each other apart: the gross-up is 40,000 / (1 - 0.0)
    # exactly if the passed-in rate was used, and 40,000 / (1 - 0.22) if
    # this sub-stage derived its own.
    result, _bal, _row = _run(
        gap=40_000.0, top_24_yr=0.0, irmaa_thr_yr=0.0, marg=0.0,
        ira_taxable_inc_orig=150_000.0, ira_retirement_dist_orig=0.0,
    )

    assert result.ira_wd == pytest.approx(40_000.0, rel=1e-6)


def test_no_draw_and_no_derivation_when_the_gap_is_closed():
    # The guard still gates everything: no gap, no withdrawal, and the None
    # inputs are never needed.
    result, bal, row = _run(gap=0.0)

    assert result.ira_wd == 0.0
    assert bal[_IRA_ID] == _START_BALANCE
    assert row["_account_withdrawals"] == {}


def test_derivation_keeps_priority_3s_refusal_to_guess_a_bracket():
    # The derived values come from Priority 3's own computation, unchanged
    # -- including its refusal to silently fall back when
    # withdrawal_bracket_target_rate names a rate no federal bracket carries.
    config = _config()
    config["withdrawal_bracket_target_rate"] = 0.37123

    with pytest.raises(ValueError, match="matches no federal bracket rate"):
        _run(config=config, gap=40_000.0)

    # And the default 0.24 it falls back to is a rate the table really has.
    assert any(rate == 0.24 for _lo, _hi, rate in FEDERAL_BRACKETS_MFJ)
