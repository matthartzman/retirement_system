"""T4a (system review 2026-07-21, P1): the IRMAA guardrail on voluntary Roth
conversions must not throttle conversions in years whose MAGI is more than
irmaa_lookback_years (2) away from ever being looked back at for a Medicare
surcharge. Before this fix, the guardrail applied at every age with no gate
at all, over-restricting gap-year conversions for non-ACA-bridge clients
from the moment they became eligible to convert.
"""
from pathlib import Path

from src.data_io import load_csv, parse_client
from src.planning_engines import project

ROOT = Path(__file__).resolve().parents[1]


def _scenario():
    c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    c["roth_policy"] = "fill_to_bracket"
    c["roth_irmaa_cap"] = True
    c["irmaa_guardrail_mode"] = "AVOID_NEXT_TIER"
    c["roth_irmaa_target_tier"] = "TIER_1"  # tightest tier, so it binds whenever the gate is open
    c["aca_ptc_enabled"] = False  # isolate the IRMAA gate from the separate ACA PTC guardrail
    c["forced_roth"] = {}
    c["plan_start"] = 2026
    c["h_dob_yr"] = 2026 - 55  # h_age 55 at plan start
    c["w_dob_yr"] = 2026 - 53  # w_age 53 at plan start
    c["plan_end"] = c["plan_start"] + 15
    c["h_ret_yr"] = c["plan_start"]
    c["w_ret_yr"] = c["plan_start"]
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return project(c)


def test_irmaa_cap_absent_from_ranked_caps_while_both_spouses_are_under_the_gate_age():
    rows = _scenario()
    pre_gate_years = [r for r in rows if r["h_age"] < 63 and r["w_age"] < 63 and r.get("roth_conv", 0) > 0]
    assert pre_gate_years, "expected some real conversion activity before either spouse reaches 63"
    for r in pre_gate_years:
        assert r.get("conv_binding_limit") != "Tier 1"
        assert r.get("conv_secondary_binding_limit") != "Tier 1"


def test_irmaa_cap_appears_once_the_first_spouse_crosses_the_gate_age():
    # Mixed-age couple: h reaches 63 while w is still 61 -- the gate must open
    # on whichever spouse is closer to Medicare age, not wait for both.
    rows = _scenario()
    gated_open_years = [r for r in rows if r["h_age"] >= 63 and r["w_age"] < 63 and r.get("roth_conv", 0) > 0]
    assert gated_open_years, "expected h_age >= 63 while w_age < 63 to occur with real conversion activity"
    assert any(
        r.get("conv_binding_limit") == "Tier 1" or r.get("conv_secondary_binding_limit") == "Tier 1"
        for r in gated_open_years
    )


def test_irmaa_guardrail_age_gate_helper_matches_lookback_years_config():
    from src.planning_engines import _roth_irmaa_guardrail_age_gate_met

    assert not _roth_irmaa_guardrail_age_gate_met({}, 62, 60)
    assert _roth_irmaa_guardrail_age_gate_met({}, 63, 60)
    assert _roth_irmaa_guardrail_age_gate_met({}, 60, 63)
    # A shorter configured lookback opens the gate later (closer to 65).
    assert not _roth_irmaa_guardrail_age_gate_met({"irmaa_lookback_years": 1}, 63, 60)
    assert _roth_irmaa_guardrail_age_gate_met({"irmaa_lookback_years": 1}, 64, 60)


def _fill_to_irmaa_aca_scenario():
    c = parse_client(load_csv(ROOT / "input" / "client_data.csv"), "")
    c["roth_policy"] = "fill_to_irmaa"
    c["roth_irmaa_target_tier"] = "TIER_5"  # loose IRMAA cap so the ACA guardrail is what binds
    c["aca_ptc_enabled"] = True
    c["forced_roth"] = {}
    c["plan_start"] = 2026
    c["h_dob_yr"] = 2026 - 60
    c["w_dob_yr"] = 2026 - 58
    c["plan_end"] = c["plan_start"] + 8
    c["h_ret_yr"] = c["plan_start"]
    c["w_ret_yr"] = c["plan_start"]
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return project(c)


def test_fill_to_irmaa_policy_now_carries_the_aca_ptc_guardrail():
    # Before this fix, fill_to_irmaa capped only to the IRMAA threshold, with
    # no ACA guardrail at all -- an ACA-bridge client on this policy got
    # conversions sized straight into subsidy-destroying MAGI (a live,
    # money-losing gap; confirmed by temporarily reverting this fix, where
    # the same bridge-year conversions came out 5-10x larger, capped only by
    # the loose IRMAA tier).
    rows = _fill_to_irmaa_aca_scenario()
    bridge_years_with_conversions = [r for r in rows if r["h_age"] < 65 and r.get("roth_conv", 0) > 0]
    assert bridge_years_with_conversions, "expected some real conversion activity during ACA bridge years"
    assert any(
        r.get("conv_binding_limit") == "ACA PTC MAGI guardrail"
        or r.get("conv_secondary_binding_limit") == "ACA PTC MAGI guardrail"
        for r in bridge_years_with_conversions
    )
