"""#270: DAF contribution recommendation engine.

recommend_daf_contribution() maximizes a DAF contribution within the IRS
AGI-based ceiling (60% of AGI cash / 30% of AGI appreciated), and surfaces
federal-bracket/IRMAA/NIIT context. It is read-only -- the UI applies the
number itself via the existing daf_amount field the projection engine
already reads.
"""
from __future__ import annotations

from src.daf_optimizer import recommend_daf_contribution
from src.data_io import load_csv, parse_client
from tests.golden_pricing import FROZEN_GOLDEN_MASTER_PRICES, frozen_holdings_prices

from conftest import TEST_INPUT_DIR


def sample_config():
    return parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")


def test_cash_limit_is_60pct_of_agi_and_appreciated_is_30pct():
    c = sample_config()
    c = dict(c)
    c["earned"] = 400000
    c["h_ss"] = c["w_ss"] = c["pension"] = 0
    cash = recommend_daf_contribution(c, rows=None, year=c.get("plan_start"), appreciated=False)
    appreciated = recommend_daf_contribution(c, rows=None, year=c.get("plan_start"), appreciated=True)
    assert cash["agi_limit_pct"] == 0.60
    assert appreciated["agi_limit_pct"] == 0.30
    # Appreciated ceiling is exactly half the cash ceiling for the same AGI.
    assert abs(appreciated["recommended_amount"] - cash["recommended_amount"] / 2) < 1.0


def test_recommendation_scales_with_agi():
    c = sample_config()
    c = dict(c)
    c["h_ss"] = c["w_ss"] = c["pension"] = 0
    c["earned"] = 100000
    low = recommend_daf_contribution(c, rows=None, year=c.get("plan_start"))
    c["earned"] = 500000
    high = recommend_daf_contribution(c, rows=None, year=c.get("plan_start"))
    assert high["recommended_amount"] > low["recommended_amount"]


def test_recommendation_never_mutates_the_plan_config():
    c = sample_config()
    before = dict(c)
    recommend_daf_contribution(c, rows=None, year=c.get("plan_start"))
    assert c == before


def test_uses_projected_agi_when_rows_available():
    c = sample_config()
    with frozen_holdings_prices(FROZEN_GOLDEN_MASTER_PRICES):
        from src.plan_config import ensure_engine_config
        from src.planning_engines import project

        c2 = ensure_engine_config(dict(c), source="test")
        rows = project(c2)
    plan_start = c2.get("plan_start")
    out = recommend_daf_contribution(c2, rows=rows, year=plan_start)
    first_row = next((r for r in rows if r.get("year") == plan_start), None)
    assert first_row is not None
    assert out["agi"] == round(float(first_row.get("agi", 0) or 0), 2)
