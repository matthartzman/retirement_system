"""Characterization tests for src/gain_harvest.py -- the 0%-bracket LTCG gain
harvesting scanner.

System review 2026-08-31, finding Q3 / Wave 1 item 1.13. See
test_tlh_unit.py's module docstring for the fixture-derivation approach: small
hand-built lot/config scenarios with independently checkable round numbers,
exercised directly against the module's real functions rather than through
the full projection pipeline. Each assertion is exact to the cent.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.gain_harvest import compute_zero_bracket_headroom, select_gain_harvest_lots


def _lot(qty, cost_basis, purchase_date):
    return SimpleNamespace(qty=qty, cost_basis=cost_basis, purchase_date=purchase_date)


# ─────────────────────────────────────────────────────────────────────────────
# compute_zero_bracket_headroom
# ─────────────────────────────────────────────────────────────────────────────

def test_headroom_is_top_minus_ordinary_income():
    headroom = compute_zero_bracket_headroom(ltcg_0_top=96_700.0, bracket_factor=1.0, ordinary_income=40_000.0)
    assert headroom == pytest.approx(56_700.0)


def test_headroom_floors_at_zero_when_income_exceeds_the_top():
    headroom = compute_zero_bracket_headroom(ltcg_0_top=96_700.0, bracket_factor=1.0, ordinary_income=200_000.0)
    assert headroom == 0.0


def test_headroom_scales_top_by_bracket_factor():
    headroom = compute_zero_bracket_headroom(ltcg_0_top=96_700.0, bracket_factor=1.10, ordinary_income=40_000.0)
    assert headroom == pytest.approx(96_700.0 * 1.10 - 40_000.0)


def test_headroom_treats_missing_inputs_as_zero_not_error():
    assert compute_zero_bracket_headroom(ltcg_0_top=None, bracket_factor=None, ordinary_income=None) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# select_gain_harvest_lots
# ─────────────────────────────────────────────────────────────────────────────

def _harvest_config():
    return {
        "taxable_ids": ["taxable_1"],
        "lots_by_account": {
            "taxable_1": {
                # Small appreciated lot: gain = 5,000 - 2,000 = 3,000
                "AAA": [_lot(qty=100, cost_basis=2_000.0, purchase_date="2024-01-01")],
                # Larger appreciated lot: gain = 10,000 - 4,000 = 6,000
                "BBB": [_lot(qty=100, cost_basis=4_000.0, purchase_date="2024-01-01")],
                # Depreciated lot (a loss, not a gain) -- must be excluded here.
                "CCC": [_lot(qty=100, cost_basis=9_000.0, purchase_date="2024-01-01")],
                # Appreciated but short-term (same-year purchase) -- excluded.
                "DDD": [_lot(qty=100, cost_basis=1_000.0, purchase_date="2026-06-01")],
            },
        },
        "lot_engine": SimpleNamespace(prices={
            "AAA": 50.0,   # mv = 5,000
            "BBB": 100.0,  # mv = 10,000
            "CCC": 50.0,   # mv = 5,000 (loss vs. 9,000 basis)
            "DDD": 50.0,   # mv = 5,000, gain = 4,000 but short-term
        }),
    }


def test_select_gain_harvest_lots_excludes_losses_and_short_term():
    c = _harvest_config()
    selected = select_gain_harvest_lots(c, 2026, headroom=1_000_000.0)
    symbols = {row["symbol"] for row in selected}
    assert symbols == {"AAA", "BBB"}


def test_select_gain_harvest_lots_orders_smallest_gain_first():
    c = _harvest_config()
    selected = select_gain_harvest_lots(c, 2026, headroom=1_000_000.0)
    assert [row["symbol"] for row in selected] == ["AAA", "BBB"]
    assert selected[0]["gain"] == pytest.approx(3_000.0)
    assert selected[1]["gain"] == pytest.approx(6_000.0)


def test_select_gain_harvest_lots_packs_within_headroom_skipping_overshoot():
    c = _harvest_config()
    # Headroom fits AAA (3,000) but not AAA+BBB (9,000); BBB alone (6,000)
    # would also fit under a 8,000 ceiling, but AAA is evaluated first
    # (smallest-gain-first) and consumes the running total, so BBB is
    # skipped as an overshoot rather than swapped in.
    selected = select_gain_harvest_lots(c, 2026, headroom=8_000.0)
    assert [row["symbol"] for row in selected] == ["AAA"]


def test_select_gain_harvest_lots_zero_headroom_selects_nothing():
    c = _harvest_config()
    assert select_gain_harvest_lots(c, 2026, headroom=0.0) == []


def test_select_gain_harvest_lots_min_gain_dollars_filters_small_lots():
    c = _harvest_config()
    selected = select_gain_harvest_lots(c, 2026, headroom=1_000_000.0, min_gain_dollars=5_000.0)
    assert [row["symbol"] for row in selected] == ["BBB"]
