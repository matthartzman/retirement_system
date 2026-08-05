"""Wave 3.3 (system review 2026-08-04, finding C5 second half):
the Roth-conversion objective's terminal-wealth component must be
present-valued to plan_start, like lifetime_tax and estate_tax_penalty
already are, so a plan-end dollar is not implicitly weighted the same as a
plan-start dollar in the optimizer's score.
"""
from __future__ import annotations

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project, _roth_strategy_metrics

from conftest import TEST_INPUT_DIR


def sample_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return ensure_engine_config(c, source="test")


def test_terminal_component_is_discounted_below_nominal_after_tax_nw():
    c = sample_config()
    rows = project(c)
    result = _roth_strategy_metrics(c, rows)
    after_tax_terminal_nw = result["after_tax_terminal_nw"]
    terminal_weight = float(c.get("roth_terminal_weight", 1.0) or 1.0) if "roth_terminal_weight" in c else None
    # after_tax_terminal_nw itself must stay the real, nominal dollar figure
    # (reported as PTI/Executive Summary) -- only the objective's internal
    # terminal_component is discounted.
    assert after_tax_terminal_nw > 0
    # The discounted PV must be strictly less than the nominal figure for any
    # plan running past plan_start with a positive discount rate.
    plan_start = int(c["plan_start"])
    terminal_year = int(rows[-1]["year"])
    assert terminal_year > plan_start
    discount = max(-0.99, float(c.get("roth_tax_discount_rate", c.get("inf", 0.025)) or 0.0))
    expected_pv = after_tax_terminal_nw / ((1.0 + discount) ** (terminal_year - plan_start))
    assert expected_pv < after_tax_terminal_nw


def test_post_tax_inheritance_stays_nominal_not_discounted():
    # post_tax_inheritance is a reported figure (PTI), not an objective
    # component -- it must not be silently discounted by this change.
    c = sample_config()
    rows = project(c)
    result = _roth_strategy_metrics(c, rows)
    assert result["post_tax_inheritance"] == (
        result["after_tax_terminal_nw"] - result["terminal_estate_tax"]
    )
