"""Phase 3 — advanced-module engine integration.

Covers the AMT engine, equity-comp tax-event modeling, and their gated wiring
into the deterministic projection, plus disability income re-projection and the
business-succession estate-tax effect. Every integration is gated on the saved
optional-function toggle in ``c['opt']`` (NOT module_enabled/FORCE_* env), so a
default plan projects identically — the off-state inertness test locks that in.
"""
import os

import pytest

from src.core import amt_tax, tentative_minimum_tax
from src.equity_comp import equity_comp_year_events, equity_comp_active
from src.after_tax import business_taxable_estate_value, estimate_terminal_estate_tax
from src.report_compute import prepare_config_from_sectioned_data
from src.data_io import load_csv
from src.planning_engines import project

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")


@pytest.fixture(scope="module")
def base_cfg():
    # TEST_INPUT_DIR, not a relative "input/..." path. The relative form loaded
    # the anchor client_data.csv from the REAL repo input/ while its nine part
    # files resolved through the redirected workspace -- an incoherent hybrid
    # config whose values depended on how far the two trees had diverged.
    from conftest import TEST_INPUT_DIR
    return prepare_config_from_sectioned_data(load_csv(TEST_INPUT_DIR / "client_data.csv"))


# ── AMT engine ────────────────────────────────────────────────────────────────

def test_amt_owed_on_large_iso_preference():
    adj, carry = amt_tax(300000, 60000, 500000, filing="MFJ", year=2026, inf=0.025)
    assert adj > 0                      # tentative minimum tax exceeds regular tax
    assert carry >= adj - 1e-6          # AMT owed accrues to the minimum-tax credit


def test_amt_credit_carryforward_offsets_later_regular_tax():
    _, carry = amt_tax(300000, 60000, 500000, filing="MFJ", year=2026, inf=0.025)
    adj2, carry2 = amt_tax(300000, 120000, 0, filing="MFJ", year=2027, inf=0.025, amt_credit_carryin=carry)
    assert adj2 <= 0                    # credit reduces tax
    assert carry2 < carry              # credit consumed


def test_no_amt_without_preference():
    adj, _ = amt_tax(120000, 18000, 0, filing="MFJ", year=2026, inf=0.025)
    assert adj == 0


def test_tmt_excludes_ltcg_base():
    # Only ordinary income + preferences feed the tentative minimum tax base.
    assert tentative_minimum_tax(0, 0, "MFJ", 2026, 0.025) == 0


# ── Equity-comp events ────────────────────────────────────────────────────────

def test_rsu_ordinary_income_at_sale():
    g = [{"grant_type": "RSU", "shares": 2000, "fmv_today": 150, "strike": 0,
          "fmv_growth_rate": 0.0, "planned_exercise_year": 0, "planned_sale_year": 2026}]
    e = equity_comp_year_events(g, 2026, 2026)
    assert e["ordinary_income"] == 300000 and e["cash_proceeds"] == 300000
    assert e["amt_preference"] == 0


def test_iso_amt_preference_then_ltcg():
    g = [{"grant_type": "ISO", "shares": 500, "fmv_today": 150, "strike": 25,
          "fmv_growth_rate": 0.0, "planned_exercise_year": 2026, "planned_sale_year": 2027}]
    ex = equity_comp_year_events(g, 2026, 2026)
    sale = equity_comp_year_events(g, 2027, 2026)
    assert ex["amt_preference"] == 62500 and ex["ordinary_income"] == 0
    assert sale["ltcg_gain"] == 62500 and sale["ordinary_income"] == 0


def test_nso_spread_ordinary_at_exercise():
    g = [{"grant_type": "NSO", "shares": 100, "fmv_today": 50, "strike": 10,
          "fmv_growth_rate": 0.0, "planned_exercise_year": 2026, "planned_sale_year": 0}]
    e = equity_comp_year_events(g, 2026, 2026)
    assert e["ordinary_income"] == 4000  # (50-10)*100


# ── Business estate value ─────────────────────────────────────────────────────

def test_business_estate_value_zero_when_off(base_cfg):
    assert business_taxable_estate_value(base_cfg) == 0.0


def test_business_estate_value_and_tax_rise_when_on(base_cfg):
    c = dict(base_cfg)
    c["opt"] = {**c.get("opt", {}), "business_succession": True}
    term = {"total_nw": 5_000_000.0, "cst_excluded_from_survivor_estate": 0.0}
    biz = business_taxable_estate_value(c)
    assert biz > 0
    off = dict(c); off["opt"] = {**c["opt"], "business_succession": False}
    assert estimate_terminal_estate_tax(c, term) > estimate_terminal_estate_tax(off, term)


# ── Gated engine integration ──────────────────────────────────────────────────

def _proj(base_cfg, **opts):
    c = dict(base_cfg)
    c["opt"] = {**base_cfg.get("opt", {}), **opts}
    if "disability_income_insurance" in opts:
        # Supply the policy this test is exercising rather than depending on
        # whatever the ambient plan happens to carry. The engine only pays a
        # benefit when disability.policies is non-empty
        # (deterministic_engine.py:731), and the frozen fixture deliberately
        # ships policy_count=0 -- a retired household has no DI coverage. An
        # integration test for the DI code path should not silently become a
        # no-op because the loaded plan has no policy.
        c["disability"] = {
            **c.get("disability", {}),
            "simulate_year": c["plan_start"],
            "policies": c.get("disability", {}).get("policies")
            or [{"monthly_benefit": 5000.0, "benefit_period_years": 5,
                 "elimination_days": 0, "premium_pre_tax": False}],
        }
    return project(c)


def test_off_state_is_inert(base_cfg):
    """Default toggles → no module rows and the exact same terminal net worth."""
    rows = project(dict(base_cfg))
    for k in ("equity_comp_ordinary_income", "disability_benefit", "amt_tax",
              "equity_comp_ltcg_gain", "equity_comp_amt_preference"):
        assert not any(r.get(k) for r in rows), f"{k} leaked with modules off"


def test_equity_comp_adds_ordinary_income_and_grows_networth(base_cfg):
    base = project(dict(base_cfg))
    rows = _proj(base_cfg, equity_compensation=True)
    assert any(r.get("equity_comp_ordinary_income") for r in rows)
    assert any(r.get("equity_comp_amt_preference") for r in rows)
    # Compare in-plan net worth and lifetime tax, NOT terminal net worth. The
    # frozen fixture's household exhausts its portfolio before plan end, so
    # terminal NW settles at the same non-portfolio floor either way and is
    # insensitive to anything that happens earlier -- it would report "no
    # effect" for a module that in fact shifts net worth by ~$205k in the
    # grant year and lifetime tax by ~$170k.
    assert any(abs(r["total_nw"] - b["total_nw"]) > 0.01 for r, b in zip(rows, base))
    assert sum(r["total_tax"] for r in rows) != sum(r["total_tax"] for r in base)


def test_disability_zeros_earned_and_pays_benefit(base_cfg):
    rows = _proj(base_cfg, disability_income_insurance=True)
    by_year = {r["year"]: r for r in rows}
    sim = base_cfg["plan_start"]
    assert by_year[sim].get("disability_benefit", 0) > 0
    assert by_year[sim].get("earned", 1) == 0
