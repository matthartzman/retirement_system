"""WI-024 phase 2: the Social Security and ACA steps run end to end through the cascade.

The frozen sample plan shows no effect from either step (documented in the impact doc,
section 8: its gain years before Social Security starts have no benefit to tax, and its
gain years after have the benefit already at the 85% inclusion cap; the one bridge year
has MAGI far above the credit range). These tests use small synthetic, plan-like
households where each step demonstrably bites, comparing the real engine with the step
switched off.
"""
import copy

import pytest

from src.data_io import build_plan_from_json
from src.plan_config import ensure_engine_config
from src.planning_engines import project
from src.projection_stages import deterministic_engine as de
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices
from tests.synthetic_plans import base_plan


def _plan(trust, spend, claim, dobs):
    p = copy.deepcopy(base_plan())
    p["accounts"] = [
        {"id": "Member_1_Roth", "acct_type": "roth_ira", "owner_idx": 0, "balance": 200_000.0, "label": "Roth"},
        {"id": "Joint_Trust", "acct_type": "trust", "owner_idx": 0, "balance": trust, "label": "Trust"},
        {"id": "Family_Checking", "acct_type": "checking", "owner_idx": 0, "balance": 100_000.0, "label": "Checking"},
    ]
    p["members"][0].update(dob_year=dobs[0], retirement_year=2026)
    p["members"][1].update(dob_year=dobs[1], retirement_year=2026)
    p["income"].update(earned_income=0.0, h_ss_pia=1800.0, w_ss_pia=1000.0, ss_claim_age=claim)
    p["assumptions"]["roth_policy"] = "none"
    p["spending"]["annual_base"] = spend
    return p


def _run(plan, tweak=None, drop=None, monkeypatch=None):
    c = ensure_engine_config(build_plan_from_json(plan, ""), source="synthetic")
    if tweak:
        tweak(c)
    if drop:
        orig = de._apply_investment_tax_cascade
        monkeypatch.setattr(de, "_apply_investment_tax_cascade",
                            lambda *a, **k: orig(*a, **{**k, drop: None}))
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        return {r["year"]: r for r in project(c)}


def test_social_security_step_bites_end_to_end(monkeypatch):
    plan = _plan(2_000_000.0, 90_000.0, 67, (1960, 1962))
    on = _run(plan)
    with monkeypatch.context() as m:
        off = _run(plan, drop="ss_extra_fn", monkeypatch=m)
    y = 2028
    extra = on[y]["ss_extra_taxable_from_brokerage_gain"]
    tax = on[y]["ss_extra_tax_from_brokerage_gain"]
    assert on[y]["ltcg_gain"] > 30_000.0 and extra > 5_000.0
    # The benefit counted taxable moved by exactly the extra, and never past 85% of benefits.
    assert on[y]["ss_taxable"] - off[y]["ss_taxable"] == pytest.approx(extra)
    # Taxed as ordinary income in the 10-24% brackets, and kept in total tax.
    assert 0.10 * extra - 1.0 <= tax <= 0.24 * extra
    assert on[y]["total_tax"] - off[y]["total_tax"] >= tax - 1.0
    # AGI and IRMAA MAGI carry the extra benefit; net worth is lower.
    assert on[y]["agi"] - off[y]["agi"] == pytest.approx(extra, abs=1.0)
    assert on[y]["irmaa_magi_current"] - off[y]["irmaa_magi_current"] >= extra - 1.0
    assert on[2040]["total_nw"] < off[2040]["total_nw"]


def test_aca_step_bites_end_to_end_in_bridge_years(monkeypatch):
    plan = _plan(1_200_000.0, 60_000.0, 70, (1963, 1964))

    def tweak(c):
        c.update(aca_ptc_enabled=True, aca_benchmark_silver_premium=20_000.0, aca_fpl_base=21_150.0,
                 aca_household_size=2, aca_enhanced_subsidies_through_year=2026)

    on = _run(plan, tweak)
    with monkeypatch.context() as m:
        off = _run(plan, tweak, drop="aca_ptc_fn", monkeypatch=m)
    y = 2027  # both members under 65 (ages 64 and 63): bridge people = 2
    loss = on[y]["aca_ptc_loss_from_brokerage_gain"]
    assert on[y]["ltcg_gain"] > 30_000.0 and loss > 500.0
    assert off[y]["aca_premium_tax_credit"] == pytest.approx(20_000.0)
    assert on[y]["aca_premium_tax_credit"] == pytest.approx(off[y]["aca_premium_tax_credit"] - loss)
    assert on[y]["total_nw"] < off[y]["total_nw"]
    # 2029: nobody on the bridge any more (ages 66, 65): no credit, no loss.
    assert on[2029].get("aca_ptc_loss_from_brokerage_gain") is None


def test_frozen_plan_zeros_are_explained():
    """Frozen plan: no benefit to tax in gain years before Social Security starts, benefit at
    the 85% cap after; the credit is zero in every year (bridge year 2026 has MAGI ~455k)."""
    from tests.test_frozen_sample_plan_golden_master_regression import _frozen_config
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        rows = project(_frozen_config())
    gain_years = [r for r in rows if float(r.get("ltcg_gain") or 0) > 0]
    assert gain_years
    for r in gain_years:
        pct = float(r.get("ss_taxable_pct_actual") or 0.0)
        assert pct == 0.0 or pct == pytest.approx(0.85), r["year"]
        assert not r.get("ss_extra_taxable_from_brokerage_gain"), r["year"]
    assert all(float(r.get("aca_premium_tax_credit") or 0.0) == 0.0 for r in rows)
    assert float(rows[0]["irmaa_magi_current"]) > 400_000.0
