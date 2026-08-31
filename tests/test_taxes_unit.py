"""Characterization tests for src/taxes.py's pure helpers.

System review 2026-08-31, finding Q3 / Wave 1 item 1.13. See
test_tlh_unit.py's module docstring for the fixture-derivation approach.

Note on scope: the review's item 1.13 description names "taxes.py's core
federal bracket calc" and "after_tax.py's NIIT/IRMAA logic" as example
targets. Those specific functions (``compute_fed_tax``, ``niit_tax``,
``irmaa_surcharge``/``irmaa_tier``, ``marginal_rate``) actually live in
``src/core.py``, not in ``src/taxes.py`` or ``src/after_tax.py`` -- a
naming mismatch between the review and the current module layout, not a
missing function. ``src/taxes.py`` itself is mostly the externalized
tax-law-table loader (``_load_federal_tax_law_tables``, etc.); its actual
pure calculation helpers are the geographic cost-of-living factor lookup
(``col_factors``), small string parsers, and the annuity purchase-rate /
reserve calibration formulas. Those are what this file characterizes. Each
assertion is exact to the cent (or exact dict/string), so a one-cent or
one-branch change fails.
"""
from __future__ import annotations

import pytest

from src.taxes import (
    DEFAULT_ANNUITY_CALIB,
    STATE_COL_FACTORS,
    _parse_bool,
    _parse_float,
    annuity_purchase_rate_from_calib,
    annuity_reserve_from_calib,
    col_factors,
)


# ─────────────────────────────────────────────────────────────────────────────
# col_factors
# ─────────────────────────────────────────────────────────────────────────────

def test_col_factors_known_state_matches_the_embedded_table():
    factors = col_factors("California")
    assert factors == STATE_COL_FACTORS["California"]


def test_col_factors_unknown_state_defaults_to_all_ones():
    assert col_factors("Nowhereland") == {"auto": 1.0, "home_ins": 1.0, "utilities": 1.0, "maintenance": 1.0}


def test_col_factors_csv_override_wins_over_the_embedded_table():
    base = STATE_COL_FACTORS["California"]
    rules = {"col_auto": 2.5}
    factors = col_factors("California", rules=rules)
    assert factors["auto"] == 2.5
    # Non-overridden categories keep the embedded table's values.
    assert factors["home_ins"] == base["home_ins"]
    assert factors["utilities"] == base["utilities"]
    assert factors["maintenance"] == base["maintenance"]


def test_col_factors_csv_override_ignores_none_values():
    rules = {"col_auto": None, "col_home_ins": 1.8}
    factors = col_factors("Nowhereland", rules=rules)
    assert factors["auto"] == 1.0  # None does not overwrite the 1.0 default
    assert factors["home_ins"] == 1.8


# ─────────────────────────────────────────────────────────────────────────────
# _parse_bool / _parse_float
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", ["TRUE", "true", "Yes", "1", "T"])
def test_parse_bool_true_variants(raw):
    assert _parse_bool(raw) is True


@pytest.mark.parametrize("raw", ["FALSE", "no", "0", "", "garbage"])
def test_parse_bool_false_variants(raw):
    assert _parse_bool(raw) is False


def test_parse_bool_passes_through_actual_bools():
    assert _parse_bool(True) is True
    assert _parse_bool(False) is False


def test_parse_float_strips_currency_formatting():
    assert _parse_float("$1,234.56") == pytest.approx(1234.56)


def test_parse_float_handles_percent_strings():
    assert _parse_float("24%") == pytest.approx(0.24)


def test_parse_float_returns_default_on_garbage():
    assert _parse_float("not-a-number", default=7.5) == 7.5


def test_parse_float_passes_through_numeric_types():
    assert _parse_float(42) == 42.0
    assert _parse_float(3.14) == pytest.approx(3.14)


# ─────────────────────────────────────────────────────────────────────────────
# annuity_purchase_rate_from_calib / annuity_reserve_from_calib
# ─────────────────────────────────────────────────────────────────────────────

def test_annuity_purchase_rate_flat_in_the_first_segment():
    # Segment 0: age_start=0, age_end=68, base_rate=0.05, slope=0.0 -- flat.
    assert annuity_purchase_rate_from_calib(30) == pytest.approx(0.05)
    assert annuity_purchase_rate_from_calib(67) == pytest.approx(0.05)


def test_annuity_purchase_rate_applies_slope_within_a_segment():
    # Segment 1: age_start=68, age_end=75, base_rate=0.05, slope=0.002.
    # At age 70: 0.05 + 0.002 * (70 - 68) = 0.054.
    assert annuity_purchase_rate_from_calib(70) == pytest.approx(0.054)


def test_annuity_purchase_rate_extrapolates_past_the_last_segment():
    # Segment 4 (last): age_start=95, age_end=999, base_rate=0.184, slope=0.015.
    # At age 100: 0.184 + 0.015 * (100 - 95) = 0.259.
    assert annuity_purchase_rate_from_calib(100) == pytest.approx(0.259)


def test_annuity_purchase_rate_default_calib_matches_explicit_calib():
    assert annuity_purchase_rate_from_calib(70, calib=None) == pytest.approx(
        annuity_purchase_rate_from_calib(70, calib=DEFAULT_ANNUITY_CALIB)
    )


def test_annuity_reserve_decays_within_the_first_period():
    # decay_rate=0.975, decay_period=6: at yr_offset=3, reserve = start * 0.975**3.
    reserve = annuity_reserve_from_calib(100_000.0, 3)
    assert reserve == pytest.approx(100_000.0 * 0.975 ** 3)


def test_annuity_reserve_at_start_of_mortality_credit_boost_period():
    # At yr_offset == decay_period (6), still governed by the first branch.
    reserve = annuity_reserve_from_calib(100_000.0, 6)
    assert reserve == pytest.approx(100_000.0 * 0.975 ** 6)


def test_annuity_reserve_applies_mortality_credit_boost_after_decay_period():
    # yr_offset=10: r_dp = start*0.975**6, then boosted by mc_boost and decayed
    # by post_decay for (10-6)=4 more years.
    r_dp = 100_000.0 * 0.975 ** 6
    expected = r_dp * 1.29 * (0.96 ** 4)
    assert annuity_reserve_from_calib(100_000.0, 10) == pytest.approx(expected)


def test_annuity_reserve_applies_late_life_growth_after_the_transition():
    # transition = decay_period(6) + post_period(16) = 22. At yr_offset=25:
    r_dp = 100_000.0 * 0.975 ** 6
    r_tr = r_dp * 1.29 * (0.96 ** 16)
    expected = r_tr * (1.07 ** (25 - 22))
    assert annuity_reserve_from_calib(100_000.0, 25) == pytest.approx(expected)
