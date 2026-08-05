"""Wave 3.2 (system review 2026-08-04, finding no-medical-expense-deduction):
Sec 213 medical expense itemized deduction, with the statutory 7.5% of AGI
floor, and LTC cost shocks routed into the same deductible pool they already
flow into as a cash cost.
"""
from __future__ import annotations

import copy

from src.data_io import load_csv, parse_client
from src.plan_config import ensure_engine_config
from src.planning_engines import project

from conftest import TEST_INPUT_DIR


def sample_config():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "none"
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return ensure_engine_config(c, source="test")


def test_medical_deduction_present_and_non_negative_every_year():
    c = sample_config()
    rows = project(c)
    for r in rows:
        assert "medical_expense_deduction" in r
        assert r["medical_expense_deduction"] >= 0.0


def test_medical_deduction_appears_when_agi_drops_after_retirement():
    c = sample_config()
    rows = project(c)
    # A deduction should appear in at least one year, once income (and the
    # 7.5% AGI floor) drops enough for wellness spend to exceed it.
    assert any(r["medical_expense_deduction"] > 0 for r in rows)


def test_medical_deduction_scales_down_with_higher_agi_floor():
    # Same medical spend, much higher AGI -> smaller (or zero) deduction,
    # since the 7.5% floor grows with AGI.
    c = sample_config()
    year = c["plan_start"]
    c.update({"plan_end": year})
    rows_normal = project(copy.deepcopy(c))
    ded_normal = rows_normal[0]["medical_expense_deduction"]

    c_high_income = copy.deepcopy(c)
    c_high_income["earned"] = float(c_high_income.get("earned", 0.0) or 0.0) + 2_000_000.0
    rows_high = project(c_high_income)
    ded_high = rows_high[0]["medical_expense_deduction"]

    assert ded_high <= ded_normal


def test_ltc_shock_increases_medical_deduction():
    c = sample_config()
    year = c["plan_start"] + 1
    c["wellness_shock_by_year"] = {year: 50_000.0}
    rows = project(c)
    row_shock_year = next(r for r in rows if r["year"] == year)
    assert row_shock_year["wellness_shock_yr"] == 50_000.0

    c_no_shock = sample_config()
    rows_no_shock = project(c_no_shock)
    row_no_shock = next(r for r in rows_no_shock if r["year"] == year)

    assert row_shock_year["medical_expense_deduction"] >= row_no_shock["medical_expense_deduction"]
