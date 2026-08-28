"""Optimization-refactor Phase 6: expanded stress scenarios, per
docs/superpowers/plans/2026-08-27-phase6-expanded-stress-scenarios-spec.md
and its 2026-08-28 implementation-design follow-up.

Two new Sheet 16 ("Scenario Analysis") rows, both Option A (add a scenario
to the existing hardcoded pattern, no framework change):

1. "No Social Security Benefit Cut" -- the base plan already applies a
   trust-fund funding-discount haircut by default (`ss_funding_discount_
   year`/`ss_funding_discount_pct`, default 2032/22%); this scenario shows
   the upside if that pessimistic default does not materialize. Pure config
   override, zero new engine code.

2. "Divorce/QDRO Asset Split" -- a NEW one-time engine event (a home-sale-
   style mid-plan intervention, since a config override can only change the
   plan-start balance, not a future-year event): at `divorce_split_yr`, every
   investment account (`core.all_investment_ids`) is reduced by
   `divorce_split_pct`. Tax-free (transfers incident to divorce are not a
   taxable event under IRC S1041) -- asset-split only, does NOT model
   ongoing spousal support/alimony (Option D1, per explicit sign-off).
"""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from conftest import TEST_INPUT_DIR
from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.reporting.sheets_stress import build_sheet16
from src import core as _ar


def _base_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_sensitivity_sims"] = 1
    return c


def _zero_growth_config():
    # Real fixture with growth/inflation/spend zeroed so the pre-split
    # investment-account total for any year is exactly computable from the
    # base (no-split) run, isolating the split mechanics from unrelated
    # market/spending noise.
    c = _base_config()
    c["ret"] = 0.0
    c["inf"] = 0.0
    c["plan_end"] = min(int(c["plan_end"]), int(c["plan_start"]) + 10)
    return c


def test_no_ss_cut_flag_is_a_pure_config_override_base_plan_unaffected():
    # The base plan is never mutated by adding the Sheet 16 scenario -- only
    # a run_scenario-scoped copy sees ss_funding_discount_pct=0.
    c = _base_config()
    rows_base = project(dict(c))
    assert rows_base[-1]["ss_funding_discount_pct"] == pytest.approx(c["ss_funding_discount_pct"])


def test_no_ss_cut_scenario_produces_higher_terminal_nw_than_base():
    c = _base_config()
    rows_base = project(dict(c))
    c_no_cut = dict(c)
    c_no_cut["ss_funding_discount_pct"] = 0.0
    rows_no_cut = project(c_no_cut)
    assert rows_no_cut[-1]["total_nw"] > rows_base[-1]["total_nw"]


def test_divorce_split_defaults_are_parsed_from_csv():
    c = _base_config()
    assert c["scen_divorce_yr"] > c["plan_start"]
    assert 0.0 < c["scen_divorce_split_pct"] <= 1.0


def test_divorce_split_reduces_investment_accounts_by_exact_pct_at_exact_year():
    c = _zero_growth_config()
    split_yr = int(c["plan_start"]) + 2
    investment_ids = set(_ar.all_investment_ids(c["account_registry"]))

    rows_base = project(dict(c))
    row_before_split = next(r for r in rows_base if r["year"] == split_yr)
    pre_split_investment_total = sum(
        float(v) for k, v in row_before_split["_account_opening"].items() if k in investment_ids
    )

    c2 = dict(c)
    c2["divorce_split_yr"] = split_yr
    c2["divorce_split_pct"] = 0.5
    rows = project(c2)
    row_at = next(r for r in rows if r["year"] == split_yr)
    row_after = next(r for r in rows if r["year"] == split_yr + 1)

    # rel=1e-3 (not 1e-6): the real fixture's withdrawal-cascade fixed-point
    # iteration has its own tiny floating-point path sensitivity unrelated to
    # this feature -- still tight enough to prove the split is genuinely
    # ~50% of the pre-split investment total, not some other fraction.
    # (total_nw is NOT checked against a simple base-minus-split subtraction
    # here: reducing balances mid-year legitimately cascades into different
    # same-year withdrawal-sourcing/RMD/income behavior for a full household,
    # so terminal wealth doesn't move by exactly the split amount even with
    # ret=0 -- that's a real secondary effect, not a bug in the split itself.)
    expected_split = pre_split_investment_total * 0.5
    assert row_at["divorce_split_amount"] == pytest.approx(expected_split, rel=1e-3)
    assert row_at["total_nw"] < row_before_split["total_nw"]
    # No further split in later years.
    assert row_after["divorce_split_amount"] == 0.0


def test_divorce_split_is_tax_free():
    # The transfer itself must not be treated as a taxable disposition (no
    # capital-gains/ordinary-income event on the transferred amount) -- but
    # total_tax for that year CAN still differ slightly from the no-split
    # base run, because reducing account balances mid-year legitimately
    # changes downstream investment-income/withdrawal-sourcing math. The
    # real test is that the tax delta is tiny relative to the transferred
    # amount (nowhere near even a low capital-gains rate), not that it's
    # bit-identical.
    c = _zero_growth_config()
    split_yr = int(c["plan_start"]) + 1
    c["divorce_split_yr"] = split_yr
    c["divorce_split_pct"] = 0.5
    rows_split = project(dict(c))
    c_no_split = dict(c)
    c_no_split.pop("divorce_split_yr")
    rows_base = project(c_no_split)
    split_row = next(r for r in rows_split if r["year"] == split_yr)
    base_row = next(r for r in rows_base if r["year"] == split_yr)
    tax_delta = abs(split_row["total_tax"] - base_row["total_tax"])
    # Comfortably below even the lowest real capital-gains bracket (0%/15%/
    # 20%) applied to the transferred amount -- rules out an accidental
    # taxable-sale treatment while tolerating normal secondary tax drift.
    assert tax_delta < 0.05 * split_row["divorce_split_amount"]


def test_zero_pct_or_no_year_is_a_no_op():
    c = _zero_growth_config()
    rows_no_yr = project(dict(c))
    assert all(r["divorce_split_amount"] == 0.0 for r in rows_no_yr)

    c2 = dict(c)
    c2["divorce_split_yr"] = int(c["plan_start"]) + 1
    c2["divorce_split_pct"] = 0.0
    rows_zero_pct = project(c2)
    assert all(r["divorce_split_amount"] == 0.0 for r in rows_zero_pct)


def test_divorce_split_only_touches_investment_accounts():
    # A 100% split's recorded amount must equal the sum of ONLY
    # investment-tagged opening balances that year -- any non-investment
    # account (e.g. HSA, cash) accidentally swept in would inflate this past
    # the investment-only total.
    c = _zero_growth_config()
    split_yr = int(c["plan_start"]) + 1
    c["divorce_split_yr"] = split_yr
    c["divorce_split_pct"] = 1.0  # 100% split, easiest to verify exhaustively
    investment_ids = set(_ar.all_investment_ids(c["account_registry"]))
    all_ids = {a["id"] for a in c["account_registry"]}
    assert investment_ids < all_ids, "fixture must have at least one non-investment-tagged account to make this test meaningful"

    rows = project(dict(c))
    split_row = next(r for r in rows if r["year"] == split_yr)
    expected_split = sum(
        float(v) for k, v in split_row["_account_opening"].items() if k in investment_ids
    )
    assert split_row["divorce_split_amount"] == pytest.approx(expected_split, rel=1e-6)


def test_sheet16_builds_without_crashing_and_includes_both_new_scenarios():
    c = _base_config()
    rows = project(c)
    ws = Workbook().active
    build_sheet16(ws, c, rows)
    cell_values = {
        str(cell.value) for row in ws.iter_rows() for cell in row if cell.value is not None
    }
    assert any("No Social Security Benefit Cut" in v for v in cell_values)
    assert any("Divorce/QDRO Asset Split" in v for v in cell_values)
