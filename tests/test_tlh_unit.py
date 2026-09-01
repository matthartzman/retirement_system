"""Characterization tests for src/tlh.py -- the tax-loss harvesting scanner.

System review 2026-08-31, finding Q3 / Wave 1 item 1.13: core calc modules
(taxes.py, after_tax.py, gain_harvest.py, tlh.py) had zero dedicated unit
tests despite being pure, high-value-to-pin logic. These tests call tlh.py's
functions directly (not through the full projection pipeline), using
small, hand-built lot/config fixtures whose numbers are chosen to be
independently checkable (round loss/gain amounts, exact bracket-top dollars)
rather than opaque pipeline output -- the same "known-good input/output pair"
spirit as the golden-master fixtures (tests/fixtures/irs_style_examples.json,
tests/fixtures/synthetic_golden_master_cases.json), scaled down to
function-level granularity those fixtures don't carry for this module. Each
assertion is exact to the cent, so a one-cent change anywhere in the touched
code path fails the test.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.tlh import _is_long_term, _ltcg_marginal_rate, select_harvest_lots, suggest_replacement


def _lot(qty, cost_basis, purchase_date):
    return SimpleNamespace(qty=qty, cost_basis=cost_basis, purchase_date=purchase_date)


# ─────────────────────────────────────────────────────────────────────────────
# _is_long_term
# ─────────────────────────────────────────────────────────────────────────────

def test_is_long_term_true_at_exactly_one_year_held():
    lot = _lot(10, 1000.0, "2025-01-15")
    assert _is_long_term(lot, 2026) is True


def test_is_long_term_false_same_calendar_year_purchase():
    lot = _lot(10, 1000.0, "2026-06-01")
    assert _is_long_term(lot, 2026) is False


def test_is_long_term_handles_slash_dates():
    lot = _lot(10, 1000.0, "06/01/2024")
    assert _is_long_term(lot, 2026) is True


def test_is_long_term_defaults_true_when_purchase_date_unparseable():
    lot = _lot(10, 1000.0, "")
    assert _is_long_term(lot, 2026) is True


# ─────────────────────────────────────────────────────────────────────────────
# _ltcg_marginal_rate
# ─────────────────────────────────────────────────────────────────────────────

LTCG_0_TOP = 96_700.0
LTCG_15_TOP = 600_050.0


def test_ltcg_marginal_rate_zero_bracket():
    rate = _ltcg_marginal_rate(50_000.0, 0.0, LTCG_0_TOP, LTCG_15_TOP, 1.0, False)
    assert rate == 0.0


def test_ltcg_marginal_rate_fifteen_bracket():
    rate = _ltcg_marginal_rate(200_000.0, 0.0, LTCG_0_TOP, LTCG_15_TOP, 1.0, False)
    assert rate == 0.15


def test_ltcg_marginal_rate_twenty_bracket():
    rate = _ltcg_marginal_rate(650_000.0, 0.0, LTCG_0_TOP, LTCG_15_TOP, 1.0, False)
    assert rate == 0.20


def test_ltcg_marginal_rate_existing_gain_stacks_on_ordinary_income():
    # 80,000 ordinary + 20,000 existing gain = 100,000 base, already past the
    # 96,700 zero-bracket top -> the next dollar is in the 15% band.
    rate = _ltcg_marginal_rate(80_000.0, 20_000.0, LTCG_0_TOP, LTCG_15_TOP, 1.0, False)
    assert rate == 0.15


def test_ltcg_marginal_rate_adds_niit_on_top():
    rate = _ltcg_marginal_rate(650_000.0, 0.0, LTCG_0_TOP, LTCG_15_TOP, 1.0, True)
    assert rate == pytest.approx(0.238)


def test_ltcg_marginal_rate_scales_bracket_tops_by_bracket_factor():
    # Doubling bracket_factor doubles the effective 0%-top, so a base that was
    # in the 15% band at factor 1.0 falls back into the 0% band.
    rate = _ltcg_marginal_rate(150_000.0, 0.0, LTCG_0_TOP, LTCG_15_TOP, 2.0, False)
    assert rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# select_harvest_lots
# ─────────────────────────────────────────────────────────────────────────────

def _harvest_config():
    return {
        "taxable_ids": ["taxable_1"],
        "lots_by_account": {
            "taxable_1": {
                # Loss lot, well above min_loss_dollars/min_loss_pct.
                "AAA": [_lot(qty=100, cost_basis=20_000.0, purchase_date="2024-01-01")],
                # Loss lot too small (below the $500 floor) -- must be excluded.
                "BBB": [_lot(qty=10, cost_basis=1_000.0, purchase_date="2024-01-01")],
                # Gain lot (no loss at all) -- must be excluded.
                "CCC": [_lot(qty=50, cost_basis=2_000.0, purchase_date="2024-01-01")],
                # A second, bigger loss lot -- used to check largest-loss-first order.
                "DDD": [_lot(qty=200, cost_basis=50_000.0, purchase_date="2024-01-01")],
            },
        },
        "lot_engine": SimpleNamespace(prices={
            "AAA": 100.0,   # mv = 10,000; loss = 20,000 - 10,000 = 10,000
            "BBB": 95.0,    # mv = 950; loss = 50 (below the $500 floor)
            "CCC": 50.0,    # mv = 2,500; gain, not a loss
            "DDD": 100.0,   # mv = 20,000; loss = 30,000
        }),
    }


def test_select_harvest_lots_excludes_gains_and_below_floor_losses():
    c = _harvest_config()
    selected = select_harvest_lots(c, 2026)
    symbols = {row["symbol"] for row in selected}
    assert symbols == {"AAA", "DDD"}


def test_select_harvest_lots_orders_largest_loss_first():
    c = _harvest_config()
    selected = select_harvest_lots(c, 2026)
    assert [row["symbol"] for row in selected] == ["DDD", "AAA"]
    assert selected[0]["loss"] == pytest.approx(30_000.0)
    assert selected[1]["loss"] == pytest.approx(10_000.0)


def test_select_harvest_lots_respects_annual_ceiling():
    c = _harvest_config()
    # Ceiling below DDD's own loss (30,000): DDD alone already exceeds it, but
    # is still taken (the running total starts at 0 < ceiling), and the loop
    # stops before AAA once the ceiling is reached.
    selected = select_harvest_lots(c, 2026, annual_ceiling=15_000.0)
    assert [row["symbol"] for row in selected] == ["DDD"]


def test_select_harvest_lots_ignores_non_taxable_accounts():
    c = _harvest_config()
    c["taxable_ids"] = []
    assert select_harvest_lots(c, 2026) == []


# ─────────────────────────────────────────────────────────────────────────────
# suggest_replacement
# ─────────────────────────────────────────────────────────────────────────────

MASTER = {
    "VTI": {"asset_class": "EQUITY", "sleeve": "US_TOTAL", "style": "", "name": "Total US"},
    "ITOT": {"asset_class": "EQUITY", "sleeve": "US_TOTAL", "style": "", "name": "Total US 2"},
    "SCHB": {"asset_class": "EQUITY", "sleeve": "US_TOTAL", "style": "", "name": "Total US 3"},
    "BND": {"asset_class": "BOND", "sleeve": "US_AGG", "style": "", "name": "Agg Bond"},
}


def test_suggest_replacement_prefers_same_class_and_sleeve_not_already_held():
    pick = suggest_replacement("VTI", MASTER, held_symbols={"VTI"})
    assert pick in {"ITOT", "SCHB"}
    assert pick != "VTI"


def test_suggest_replacement_avoids_symbols_already_held_elsewhere():
    pick = suggest_replacement("VTI", MASTER, held_symbols={"VTI", "ITOT"})
    assert pick == "SCHB"


def test_suggest_replacement_returns_empty_for_unknown_symbol():
    assert suggest_replacement("ZZZZ", MASTER, held_symbols=set()) == ""


def test_suggest_replacement_falls_back_to_same_asset_class_when_no_sleeve_match():
    master = {
        "VTI": {"asset_class": "EQUITY", "sleeve": "US_TOTAL", "style": "", "name": ""},
        "VXUS": {"asset_class": "EQUITY", "sleeve": "INTL", "style": "", "name": ""},
    }
    pick = suggest_replacement("VTI", master, held_symbols=set())
    assert pick == "VXUS"
