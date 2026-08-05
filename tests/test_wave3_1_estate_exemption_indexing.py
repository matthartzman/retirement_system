"""Wave 3.1 (system review 2026-08-04, finding estate-tax-engine-il-only-
unindexed): the federal estate exemption must grow with the same bracket
inflator used for income-tax brackets rather than staying frozen at its
plan-start value for a terminal estate tax computed decades later, and
Illinois estate tax must only apply to a household whose residence state is
Illinois -- the engine only models Illinois estate tax.
"""
from __future__ import annotations

import copy

from src.core import indexed_federal_estate_exemption
from src.after_tax import estimate_terminal_estate_tax
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


def test_indexed_exemption_grows_with_brk_inf():
    base = 13_000_000.0
    same_year = indexed_federal_estate_exemption(base, 2026, 2026, 0.02)
    assert same_year == base
    ten_years_out = indexed_federal_estate_exemption(base, 2026, 2036, 0.02)
    assert ten_years_out == base * (1.02 ** 10)
    assert ten_years_out > base


def test_indexed_exemption_never_goes_backward_in_time():
    # A target_year before plan_start should not shrink the exemption below
    # its base value -- clamped to zero years, not negative compounding.
    base = 13_000_000.0
    result = indexed_federal_estate_exemption(base, 2030, 2026, 0.02)
    assert result == base


def test_terminal_estate_tax_uses_indexed_exemption_not_plan_start_value():
    c = sample_config()
    c["fed_exempt"] = 13_000_000.0
    c["brk_inf"] = 0.02
    c["plan_start"] = 2026
    terminal_near = {"total_nw": 20_000_000.0, "year": 2026}
    terminal_far = {"total_nw": 20_000_000.0, "year": 2056}
    tax_near = estimate_terminal_estate_tax(c, terminal_near)
    tax_far = estimate_terminal_estate_tax(c, terminal_far)
    # Same taxable estate, but the far-future exemption is larger (indexed
    # 30 years), so less is above the exemption and federal tax is lower --
    # the opposite of what an un-indexed (frozen) exemption would produce.
    assert tax_far < tax_near


def test_illinois_estate_tax_not_charged_to_non_illinois_resident():
    c = sample_config()
    c["il_exempt"] = 4_000_000.0
    c["model_state_est"] = True
    terminal = {"total_nw": 20_000_000.0, "year": 2056}

    c_il = copy.deepcopy(c)
    c_il["state"] = "Illinois"
    c_other = copy.deepcopy(c)
    c_other["state"] = "Florida"

    tax_il = estimate_terminal_estate_tax(c_il, terminal)
    tax_other = estimate_terminal_estate_tax(c_other, terminal)
    # Same estate, same exemption config -- the only difference is residence
    # state. A Florida resident must not be charged Illinois estate tax.
    assert tax_il > tax_other


def test_credit_shelter_trust_savings_none_for_non_illinois_resident():
    from src.reporting.summary_figures import credit_shelter_trust_savings
    c = sample_config()
    c["cs_enabled"] = True
    c["il_exempt"] = 4_000_000.0
    c["state"] = "Texas"
    assert credit_shelter_trust_savings(c) is None
