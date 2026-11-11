"""FIN-005: in-force life insurance pays its death benefit in the projection when the module is on."""
import os

import pytest

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")


def _run(mutate=None):
    from src.planning_engines import project
    from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config

    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        c = _frozen_config()
        if mutate:
            mutate(c)
        return c, project(c)


def _policy(c, **kw):
    p = {"name": "T1", "owner": c["h_name"], "insured": c["h_name"], "beneficiary": c["w_name"],
         "policy_type": "Term", "face_amount": 1_000_000.0, "cash_value_today": 0.0, "annual_premium": 1500.0,
         "term_end_year": 0, "premium_end_year": 0, "cash_value_growth_rate": 0.0, "owned_by_ilit": False,
         "notes": ""}
    p.update(kw)
    return p


def _with_policy(module_on=True, **kw):
    def mutate(c):
        c.setdefault("opt", {})["existing_life_insurance"] = module_on
        c["life_policies"] = [_policy(c, **kw)]
    return mutate


@pytest.fixture(scope="module")
def baseline():
    return _run()


def _death_year_row(c, rows, idx=0):
    year = c["h_death_yr"] if idx == 0 else c["w_death_yr"]
    return next(r for r in rows if r["year"] == year)


def test_first_death_adds_face_amount_to_survivor_balance(baseline):
    c0, rows0 = baseline
    c1, rows1 = _run(_with_policy())
    first = min(c0["h_death_yr"], c0["w_death_yr"])
    assert c0["h_name"] == c1["h_name"]
    assert first == c0["h_death_yr"]   # the frozen plan's first death is member 1's (survivor-factor test)
    r0 = next(r for r in rows0 if r["year"] == first)
    r1 = next(r for r in rows1 if r["year"] == first)
    # +$1M at the death, plus that money's own growth through the rest of the death year (observed ~4.8%)
    assert 1_000_000.0 <= r1["total_nw"] - r0["total_nw"] <= 1_100_000.0


def test_module_off_leaves_projection_unchanged(baseline):
    _c0, rows0 = baseline
    _c1, rows1 = _run(_with_policy(module_on=False))
    assert [r["total_nw"] for r in rows1] == [r["total_nw"] for r in rows0]


def test_ilit_policy_does_not_enter_the_estate(baseline):
    _c0, rows0 = baseline
    _c1, rows1 = _run(_with_policy(owned_by_ilit=True))
    assert [r["total_nw"] for r in rows1] == [r["total_nw"] for r in rows0]


def test_expired_term_policy_pays_nothing(baseline):
    c0, rows0 = baseline
    _c1, rows1 = _run(_with_policy(term_end_year=c0["plan_start"] + 1))
    assert [r["total_nw"] for r in rows1] == [r["total_nw"] for r in rows0]


def test_estate_tax_base_includes_non_ilit_proceeds(baseline):
    from src.after_tax import estimate_terminal_estate_tax

    _c0, rows0 = baseline
    c1, rows1 = _run(_with_policy())
    assert rows1[-1]["total_nw"] > rows0[-1]["total_nw"]
    t = {"year": rows1[-1]["year"], "total_nw": rows1[-1]["total_nw"]}
    t0 = {"year": rows0[-1]["year"], "total_nw": rows0[-1]["total_nw"]}
    assert estimate_terminal_estate_tax(c1, t) >= estimate_terminal_estate_tax(c1, t0)
