"""WI-025 / FIN-010: a joint taxable account gets the same step-up in both death orders.

Closed form: Joint_Trust holds 200,000 (default joint titling = JTWROS, assigned to
member 1). Half is the decedent's, so basis_free after the first death is
0.5 x 200,000 = 100,000 whichever spouse dies first. The second death steps up the
whole account once (max with the existing basis_free), never twice.
"""
import pytest

from src.planning_engines import _survivor_bonus_step_fraction, apply_death_transition


def _config(**kw):
    c = {
        "household_size": 2,
        "members": [{"name": "Alex"}, {"name": "Blair"}],
        "h_nick": "Alex", "w_nick": "Blair",
        "h_death_yr": 2040, "w_death_yr": 2050,
        "basis_step_up_at_death": True,
        "basis_step_up_property_regime": "COMMON_LAW",
        "account_registry": [
            {"id": "Joint_Trust", "owner_idx": 0, "tax": "taxable", "acct_type": "trust"},
            {"id": "W_Taxable", "owner_idx": 1, "tax": "taxable", "acct_type": "trust"},
        ],
        "account_titling": {},
    }
    c.update(kw)
    return c


def _first_death(order):
    c = _config()
    balance = {"Joint_Trust": 200_000.0, "W_Taxable": 0.0}
    basis_free = {}
    if order == "member1_first":
        c.update(h_death_yr=2040, w_death_yr=2050)
        apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free=basis_free)
    else:
        c.update(h_death_yr=2050, w_death_yr=2040)
        apply_death_transition(c, balance, 2040, h_alive=True, w_alive=False, basis_free=basis_free)
    return sum(basis_free.values())


def test_default_joint_titling_gives_half_step_up_in_both_death_orders():
    assert _first_death("member1_first") == pytest.approx(100_000.0)
    assert _first_death("member2_first") == pytest.approx(100_000.0)


def test_survivor_bonus_fraction_for_joint_titling_and_unchanged_cases():
    c = _config()
    assert _survivor_bonus_step_fraction(c, "Joint_Trust") == 0.5          # default joint titling
    assert _survivor_bonus_step_fraction(c, "W_Taxable") == 0.0            # individually owned, common law
    c2 = _config(account_titling={"W_Taxable": {"titling": "JTWROS"}})
    assert _survivor_bonus_step_fraction(c2, "W_Taxable") == 0.5
    c3 = _config(account_titling={"Joint_Trust": {"titling": "COMMUNITY_PROPERTY"}})
    assert _survivor_bonus_step_fraction(c3, "Joint_Trust") == 1.0
    c4 = _config(account_titling={"Joint_Trust": {"titling": "SEPARATE_PROPERTY"}},
                 basis_step_up_property_regime="COMMUNITY_PROPERTY")
    assert _survivor_bonus_step_fraction(c4, "Joint_Trust") == 0.0


def test_second_death_consolidation_does_not_double_apply():
    c = _config()
    balance = {"Joint_Trust": 200_000.0, "W_Taxable": 0.0}
    basis_free = {}
    apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free=basis_free)
    first = sum(basis_free.values())
    assert first == pytest.approx(100_000.0)
    # Balance grows to 300,000 before the second death; the whole account is stepped up
    # once: basis_free = max(existing, balance), never existing + balance.
    for k in list(balance):
        balance[k] = balance[k] * 1.5
    apply_death_transition(c, balance, 2050, h_alive=False, w_alive=False, basis_free=basis_free)
    total_balance = sum(balance.values())
    assert sum(basis_free.values()) <= total_balance + 1e-6
    assert sum(basis_free.values()) >= first
