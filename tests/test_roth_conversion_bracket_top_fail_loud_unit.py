"""Wave 3 item 3.2 (system review 2026-08-31, finding F3, planner's review
pass addition): plan_roth_conversion's bracket-top lookup used to fall back
silently to a hardcoded $400,000 bracket top whenever the configured
roth_target_rate matched no bracket rate (a typo, or a bracket-table edit
that dropped a rate) -- a silent wrong conversion-sizing cap with nothing
in the output to flag it. Only the target-rate-based policies actually
consume this cap; fixed_dollar and fill_to_irmaa compute it as an unused
diagnostic field, so they must not be gated on it matching.
"""
import pytest

from src.data_io import load_csv, parse_client
from src.planning_engines import project

from conftest import TEST_INPUT_DIR


def _config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    c.update(overrides)
    return c


def test_fill_to_bracket_raises_when_target_rate_matches_no_bracket():
    c = _config(roth_policy="fill_to_bracket", roth_target_rate=0.23)
    with pytest.raises(ValueError, match="matches no bracket rate"):
        project(c)


def test_fixed_dollar_does_not_raise_for_the_same_unmatched_rate():
    c = _config(roth_policy="fixed_dollar", roth_fixed_amount=20000, roth_target_rate=0.23)
    project(c)  # must not raise -- target_rate is unused by this policy


def test_fill_to_irmaa_does_not_raise_for_the_same_unmatched_rate():
    c = _config(roth_policy="fill_to_irmaa", roth_target_rate=0.23)
    project(c)  # must not raise -- target_rate is unused by this policy


def test_a_real_bracket_rate_still_works_normally():
    c = _config(roth_policy="fill_to_bracket", roth_target_rate=0.24)
    rows = project(c)
    assert rows  # no exception, plan still projects
