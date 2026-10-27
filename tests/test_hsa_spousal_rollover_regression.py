"""A spouse who inherits an HSA owns it as an HSA, whether or not they already hold one.

Regression: at the first death the decedent's HSA rolled to the survivor's HSA only
when the survivor already had one. Otherwise it was swept into the survivor's TAXABLE
account, so on a plan with a single HSA the HSA bucket fell to $0 in the death year
with no withdrawal recorded, and its dollars were treated as ordinary taxable money
(growth taxed, no qualified-medical tax-free draws) for the rest of the plan.
"""
import pytest

from src.planning_engines import apply_death_transition


def _config(registry, **kw):
    c = {
        "household_size": 2,
        "members": [{"name": "Alex"}, {"name": "Blair"}],
        "h_nick": "Alex", "w_nick": "Blair",
        "h_death_yr": 2040, "w_death_yr": 2050,
        "basis_step_up_at_death": True,
        "basis_step_up_property_regime": "COMMON_LAW",
        "account_registry": registry,
        "account_titling": {},
    }
    c.update(kw)
    return c


_SINGLE_HSA = [
    {"id": "A_HSA", "owner_idx": 0, "tax": "hsa", "acct_type": "hsa"},
    {"id": "B_Taxable", "owner_idx": 1, "tax": "taxable", "acct_type": "trust"},
]


def test_a_sole_hsa_stays_an_hsa_when_its_owner_dies_first():
    c = _config(_SINGLE_HSA)
    balance = {"A_HSA": 12_922.0, "B_Taxable": 500.0}
    result = apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free={})
    assert balance["A_HSA"] == pytest.approx(12_922.0)
    assert balance["B_Taxable"] == pytest.approx(500.0)
    assert not any(t.src == "A_HSA" for t in result.transfers)


def test_it_stays_put_in_either_death_order():
    c = _config(_SINGLE_HSA, h_death_yr=2050, w_death_yr=2040)
    balance = {"A_HSA": 12_922.0, "B_Taxable": 500.0}
    apply_death_transition(c, balance, 2040, h_alive=True, w_alive=False, basis_free={})
    assert balance["A_HSA"] == pytest.approx(12_922.0)
    assert balance["B_Taxable"] == pytest.approx(500.0)


def test_an_hsa_still_rolls_into_the_survivors_own_hsa_when_there_is_one():
    registry = _SINGLE_HSA + [{"id": "B_HSA", "owner_idx": 1, "tax": "hsa", "acct_type": "hsa"}]
    c = _config(registry)
    balance = {"A_HSA": 12_922.0, "B_HSA": 3_000.0, "B_Taxable": 500.0}
    apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free={})
    assert balance["A_HSA"] == pytest.approx(0.0)
    assert balance["B_HSA"] == pytest.approx(15_922.0)
    assert balance["B_Taxable"] == pytest.approx(500.0)


def test_the_second_death_is_unchanged_and_still_consolidates_the_hsa_to_the_estate():
    c = _config(_SINGLE_HSA)
    balance = {"A_HSA": 12_922.0, "B_Taxable": 500.0}
    apply_death_transition(c, balance, 2050, h_alive=False, w_alive=False, basis_free={})
    assert balance["A_HSA"] == pytest.approx(0.0)
    assert balance["B_Taxable"] == pytest.approx(13_422.0)
