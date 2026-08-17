"""Wave 3.3 (system review 2026-08-04, finding C5 second half):
the Roth-conversion objective's terminal-wealth component must be
present-valued to plan_start, like lifetime_tax and estate_tax_penalty
already are, so a plan-end dollar is not implicitly weighted the same as a
plan-start dollar in the optimizer's score.
"""
from __future__ import annotations

import pytest

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project, _roth_discount_rate, _roth_strategy_metrics

from conftest import TEST_INPUT_DIR


def sample_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return ensure_engine_config(c, source="test")


def test_terminal_component_is_discounted_below_nominal_after_tax_nw():
    """The OBJECTIVE's terminal component must be the present value.

    Rewritten 2026-08-17 (P6). The previous body computed the PV itself and
    asserted ``pv < nominal`` -- true by arithmetic for any positive discount
    over any positive horizon, and never once reading the objective. It passed
    with C5's defect fully restored (demonstrated by reverting
    ``after_tax_terminal_nw_pv`` to the nominal figure: both tests stayed
    green). The claim lived only in the test's name, which is finding S3's shape
    inside C5's own guard.

    This body asserts on ``terminal_wealth_score`` -- the component that
    actually enters the score -- and pins it to the PV while rejecting the
    nominal figure, which is the observable that separates the two
    implementations.
    """
    c = sample_config()
    # Pin the mode so the terminal weight is a known constant rather than
    # whichever branch the fixture happens to select.
    c["roth_objective_mode"] = "MAXIMIZE_PTI"  # terminal_component = 1.0 * pv
    rows = project(c)
    result = _roth_strategy_metrics(c, rows)

    after_tax_terminal_nw = result["after_tax_terminal_nw"]
    # after_tax_terminal_nw itself must stay the real, nominal dollar figure
    # (reported as PTI/Executive Summary) -- only the objective's internal
    # terminal_component is discounted.
    assert after_tax_terminal_nw > 0

    plan_start = int(c["plan_start"])
    terminal_year = int(rows[-1]["year"])
    assert terminal_year > plan_start
    discount = _roth_discount_rate(c)
    assert discount > 0, "fixture must carry a positive discount or nothing distinguishes the two"
    expected_pv = after_tax_terminal_nw / ((1.0 + discount) ** (terminal_year - plan_start))

    terminal_component = result["terminal_wealth_score"]
    assert terminal_component == pytest.approx(expected_pv, rel=1e-9), (
        "the Roth objective's terminal component is not the present value of "
        "after-tax terminal net worth (finding C5). Undiscounted plan-end "
        "wealth systematically over-rewards deferring wealth into the far "
        "future relative to the discounted taxes paid to get there."
    )
    # And explicitly reject the defect, so a change that makes the component
    # nominal again cannot pass by coincidence.
    assert terminal_component < after_tax_terminal_nw


def test_post_tax_inheritance_stays_nominal_not_discounted():
    # post_tax_inheritance is a reported figure (PTI), not an objective
    # component -- it must not be silently discounted by this change.
    c = sample_config()
    rows = project(c)
    result = _roth_strategy_metrics(c, rows)
    assert result["post_tax_inheritance"] == (
        result["after_tax_terminal_nw"] - result["terminal_estate_tax"]
    )
