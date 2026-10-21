"""WI-039 (FIN-004): 10% additional tax on early pre-tax distributions, hand-computed (IRC 72(t))."""
from __future__ import annotations

import pytest

import src.data_io  # noqa: F401  (import order: avoids a parsing/data_io cycle)
from src.early_distribution import early_distribution_tax, early_fraction

REGISTRY = [
    {"id": "A_IRA", "owner_idx": 0, "acct_type": "traditional_ira"},
    {"id": "A_401k", "owner_idx": 0, "acct_type": "401k"},
    {"id": "B_IRA", "owner_idx": 1, "acct_type": "traditional_ira"},
    {"id": "A_Roth", "owner_idx": 0, "acct_type": "roth_ira"},
]
MEMBERS = [{"dob_yr": 1972, "dob_month": 6}, {"dob_yr": 1960, "dob_month": 1}]   # B is past 59 1/2 from 2019/2020


def _tax(year, draws, exceptions=None):
    return early_distribution_tax(0.10, year, draws, REGISTRY, MEMBERS, exceptions or {})


def test_early_fraction_by_year():
    # Born June 1972: 59 1/2 reached December 2031 (month index 11) -> 11 of 12 months count in 2031.
    assert early_fraction(2030, 1972, 6) == 1.0
    assert early_fraction(2031, 1972, 6) == pytest.approx(11 / 12)
    assert early_fraction(2032, 1972, 6) == 0.0


def test_plain_early_draw_and_exempt_owner_and_roth():
    tax, base = _tax(2028, {"A_IRA": 50_000.0, "B_IRA": 80_000.0, "A_Roth": 20_000.0})
    assert (tax, base) == pytest.approx((5_000.0, 50_000.0))   # B is past 59 1/2; Roth is not penalized here


def test_year_of_59_and_a_half_is_prorated():
    tax, base = _tax(2031, {"A_IRA": 120_000.0})
    assert base == pytest.approx(110_000.0) and tax == pytest.approx(11_000.0)


def test_rule_of_55_exempts_the_employer_plan_only():
    ex = {0: {"separation_year": 2028}}   # age 56 at separation (born 1972)
    assert _tax(2028, {"A_401k": 40_000.0, "A_IRA": 10_000.0}, ex) == pytest.approx((1_000.0, 10_000.0))
    assert _tax(2027, {"A_401k": 40_000.0}, ex) == pytest.approx((4_000.0, 40_000.0))   # before separation
    # Separation before 55 does not qualify.
    assert _tax(2025, {"A_401k": 40_000.0}, {0: {"separation_year": 2025}}) == pytest.approx((4_000.0, 40_000.0))


def test_disability_exempts_everything_from_the_start_year():
    ex = {0: {"disability_year": 2029}}
    assert _tax(2029, {"A_IRA": 90_000.0, "A_401k": 10_000.0}, ex) == (0.0, 0.0)
    assert _tax(2028, {"A_IRA": 90_000.0}, ex) == pytest.approx((9_000.0, 90_000.0))


def test_sepp_exempts_up_to_the_scheduled_amount():
    ex = {0: {"sepp_year": 2027, "sepp_amount": 30_000.0}}
    assert _tax(2028, {"A_IRA": 50_000.0}, ex) == pytest.approx((2_000.0, 20_000.0))
    assert _tax(2028, {"A_IRA": 20_000.0}, ex) == (0.0, 0.0)
    assert _tax(2026, {"A_IRA": 50_000.0}, ex) == pytest.approx((5_000.0, 50_000.0))   # before the schedule starts


# ── Through the projection ─────────────────────────────────────────────────

def _rows(**kw):
    from tests.rental_fixtures import base_config, project
    c = base_config()
    for who, yr in (("h", 1972), ("w", 1974)):
        c[f"{who}_dob_yr"] = yr
    c["members"][0]["dob_yr"] = 1972
    c["members"][1]["dob_yr"] = 1974
    c.update(earn_end=2025, h_ss_claim_age=70, w_ss_claim_age=70, h_ss_claim_age_precise=70.0,
             w_ss_claim_age_precise=70.0, h_ss_claim_year=2042, w_ss_claim_year=2044)
    c.update(kw)
    return {r["year"]: r for r in project(c)}


def test_projection_charges_funds_and_itemizes_the_additional_tax():
    rows = _rows()
    r = rows[2027]
    assert r["early_dist_tax"] == pytest.approx(0.10 * r["ira_wd"], rel=1e-9)   # both owners are under 59 1/2
    assert r["unfunded_gap"] == pytest.approx(0.0, abs=1e-6)                    # the tax is funded, not dropped
    tax = r["cashflow_breakdown"]["tax"]
    assert tax["early_distribution"] == pytest.approx(r["early_dist_tax"])
    assert sum(tax.values()) == pytest.approx(r["total_tax"])
    # Consistent with the kernel applied to the recorded draws.
    from tests.rental_fixtures import base_config
    c = base_config()
    expect, _ = early_distribution_tax(0.10, 2027, r["_pretax_elective_by_account"], c["account_registry"],
                                       [{"dob_yr": 1972, "dob_month": c["members"][0].get("dob_month")},
                                        {"dob_yr": 1974, "dob_month": c["members"][1].get("dob_month")}], {})
    assert r["early_dist_tax"] == pytest.approx(expect, rel=1e-9)


def test_disability_inputs_remove_the_tax_in_the_projection():
    exc = {0: {"disability_year": 2026}, 1: {"disability_year": 2026}}
    rows = _rows(early_dist_exceptions=exc)
    assert "early_dist_tax" not in rows[2027]


def test_no_exposure_means_no_field():
    from tests.rental_fixtures import base_config, project
    rows = project(base_config())
    assert all("early_dist_tax" not in r for r in rows)
