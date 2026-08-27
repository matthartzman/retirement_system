"""Optimization-refactor Phase 2: "probability of meeting a user legacy
floor" -- fraction of Monte Carlo paths whose after-tax terminal bequest
(post_tax_inheritance, already computed by both engines for
after_tax_terminal_nw_pct/post_tax_inheritance_pct) meets or exceeds a
household-configured ``legacy_floor`` dollar target.

Schema: ``Estate Planning / Legacy / legacy_floor`` (dollars, default 0) in
``reference_data/schema.csv``, read by ``parse_client`` into
``c['legacy_floor']`` (src/data_io.py). Both engines still read it
defensively via ``c.get('legacy_floor', 0.0)`` and report ``None`` (not a
misleading 0.0 or 1.0) whenever the value is 0/unset, matching the same
None-when-inapplicable convention already used elsewhere in this codebase
(``liquidity_coverage_pct_by_year``, ``survivor_period_*``).

Reporting-only: reads each engine's already-finalized post_tax_inheritance
tracking and never feeds back into unfunded/liquid/total/path_success/
success_rate.
"""
from __future__ import annotations

import shutil

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import (
    monte_carlo,
    monte_carlo_exact_scalar,
    project,
)


def _base_config(**overrides):
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 8)
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c.update(overrides)
    return c


def test_no_floor_configured_reports_none_vectorized():
    c = _base_config()
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert "probability_legacy_floor_met" in mc
    assert mc["probability_legacy_floor_met"] is None


def test_no_floor_configured_reports_none_scalar():
    c = _base_config()
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert "probability_legacy_floor_met" in result
    assert result["probability_legacy_floor_met"] is None


def test_trivially_low_floor_is_almost_always_met_vectorized():
    c = _base_config(legacy_floor=1000.0)
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert mc["probability_legacy_floor_met"] is not None
    assert mc["probability_legacy_floor_met"] >= 0.99


def test_trivially_low_floor_is_almost_always_met_scalar():
    c = _base_config(legacy_floor=1000.0)
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert result["probability_legacy_floor_met"] is not None
    assert result["probability_legacy_floor_met"] >= 0.99


def test_absurdly_high_floor_is_almost_never_met_vectorized():
    c = _base_config(legacy_floor=999_999_999.0)
    base_rows = project(c)
    mc = monte_carlo(c, n_sims=20, seed=3, base_rows=base_rows)
    assert mc["probability_legacy_floor_met"] is not None
    assert mc["probability_legacy_floor_met"] <= 0.01


def test_absurdly_high_floor_is_almost_never_met_scalar():
    c = _base_config(legacy_floor=999_999_999.0)
    base_rows = project(c)
    result = monte_carlo_exact_scalar(c, n_sims=15, seed=2, base_rows=base_rows)
    assert result["probability_legacy_floor_met"] is not None
    assert result["probability_legacy_floor_met"] <= 0.01


def test_legacy_floor_schema_row_is_read_by_parse_client(tmp_path):
    shutil.copytree(TEST_INPUT_DIR, tmp_path, dirs_exist_ok=True)
    estate_csv = tmp_path / "client_insurance_estate.csv"
    text = estate_csv.read_text(encoding="utf-8")
    assert "Estate Planning,Legacy,legacy_floor,$0,USD" in text, (
        "frozen fixture's legacy_floor row moved or was removed -- update this test's "
        "string match to match the fixture"
    )
    estate_csv.write_text(
        text.replace(
            "Estate Planning,Legacy,legacy_floor,$0,USD",
            "Estate Planning,Legacy,legacy_floor,$750000,USD",
        ),
        encoding="utf-8",
    )
    c = parse_client(load_csv(tmp_path / "client_data.csv"), "")
    assert c["legacy_floor"] == 750000.0


def test_higher_floor_never_produces_a_higher_probability_vectorized():
    c_low = _base_config(legacy_floor=100_000.0)
    c_high = _base_config(legacy_floor=5_000_000.0)
    base_rows_low = project(c_low)
    base_rows_high = project(c_high)
    low = monte_carlo(c_low, n_sims=30, seed=7, base_rows=base_rows_low)
    high = monte_carlo(c_high, n_sims=30, seed=7, base_rows=base_rows_high)
    assert high["probability_legacy_floor_met"] <= low["probability_legacy_floor_met"]
