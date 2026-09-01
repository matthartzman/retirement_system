"""Wave 3 item 3.1 (system review 2026-08-31, finding F3), full-pipeline
companion to test_roth_conversion_guardrails_past_rmd_age_unit.py: the unit
file isolates ``plan_roth_conversion`` directly; this drives the same
scenario through the real ``project()`` pipeline on the live household
fixture, so a real-world interaction (state tax, NIIT, ACA, standard
deduction, senior bonus deduction, RMD amount itself derived from account
balances rather than handed in as a fixed number) can't quietly break what
the isolated unit test proved.

Before this window ever gets extended by default (item 3.2), nothing in
this codebase's test suite has run a household through a conversion window
that outlives its own RMD start age -- the shipped default
(conv_window_offset=-1) always closes voluntary conversions the year
before RMDs begin.
"""
from pathlib import Path

from src.core import statutory_rmd_start_age
from src.data_io import load_csv, parse_client
from src.planning_engines import project, conversion_window_end_year

ROOT = Path(__file__).resolve().parents[1]

from conftest import TEST_INPUT_DIR


def _scenario():
    c = parse_client(load_csv(TEST_INPUT_DIR / "client_data.csv"), "")
    c["roth_policy"] = "fill_to_bracket"
    c["roth_target_rate"] = 0.22
    c["roth_irmaa_cap"] = True
    c["irmaa_guardrail_mode"] = "AVOID_NEXT_TIER"
    c["roth_irmaa_target_tier"] = "TIER_1"  # tightest tier, so it binds whenever the gate is open
    c["aca_ptc_enabled"] = False  # isolate from the separate ACA PTC guardrail
    c["roth_ltcg_cap"] = False  # isolate from the separate LTCG rate-tier guardrail
    c["roth_niit_cap"] = False  # isolate from the separate NIIT threshold guardrail
    c["forced_roth"] = {}
    c["plan_start"] = 2026
    c["h_dob_yr"] = 1960  # statutory RMD age 75
    c["w_dob_yr"] = 1962
    c["rmd_start_age"] = statutory_rmd_start_age(1960)
    c["plan_end"] = c["plan_start"] + 20
    c["h_ret_yr"] = c["plan_start"]
    c["w_ret_yr"] = c["plan_start"]
    # Push the window well past RMD start -- the item 3.2 default this test
    # anticipates -- rather than relying on the shipped conv_window_offset=-1
    # default, which never reaches an RMD year at all.
    c["conv_window_offset"] = 10
    c["roth_max_conversion_years"] = 0  # don't let the v8.3 cap silently re-shorten the window
    c["mc_paths"] = 5
    c["mc_sensitivity_sims"] = 1
    return c, project(c)


def test_window_reaches_past_rmd_start_in_this_scenario():
    c, rows = _scenario()
    end_year = conversion_window_end_year(c)
    rmd_start_year = c["plan_start"] + (c["rmd_start_age"] - (c["plan_start"] - c["h_dob_yr"]))
    assert end_year > rmd_start_year, (
        "this scenario must genuinely extend past RMD start, or the rest of this "
        "test file isn't testing what it claims to"
    )


def test_real_rmds_and_real_conversions_coexist_in_the_same_years():
    _, rows = _scenario()
    rmd_active_conversion_years = [
        r for r in rows
        if r["h_age"] >= 75 and r.get("rmd_total", 0.0) > 0 and r.get("roth_conv", 0.0) > 0
    ]
    assert rmd_active_conversion_years, (
        "expected at least one year at/past RMD age with both a real RMD and a "
        "real voluntary conversion -- if this is empty, the window extension or "
        "the conversion sizing silently stopped once RMDs began"
    )


def test_irmaa_guardrail_still_participates_in_rmd_active_years():
    _, rows = _scenario()
    rmd_years = [r for r in rows if r["h_age"] >= 75 and r.get("rmd_total", 0.0) > 0]
    assert rmd_years
    assert any(
        r.get("conv_binding_limit") == "Tier 1" or r.get("conv_secondary_binding_limit") == "Tier 1"
        for r in rmd_years
    ), "TIER_1 (the tightest tier) should bind or at least be tracked as the secondary cap in some RMD-active year"


def test_conversion_never_exceeds_bracket_ceiling_once_rmd_is_included():
    # Direct check on the row-level intermediate fields plan_roth_conversion
    # exposes: conv_pre_agi + roth_conv must never exceed the bracket top it
    # was sized against, in any RMD-active year where the bracket (not IRMAA)
    # was the binding constraint -- proof the RMD dollars were already
    # counted in conv_pre_agi before the conversion was sized, not added on
    # top of a headroom figure that ignored them.
    _, rows = _scenario()
    checked_any = False
    for r in rows:
        if r["h_age"] < 75 or r.get("rmd_total", 0.0) <= 0:
            continue
        if r.get("conv_binding_limit") != "22% bracket":
            continue
        checked_any = True
        assert r["conv_pre_agi"] + r["roth_conv"] <= r["conv_top_24"] + 1.0  # $1 float slack
    assert checked_any, "expected at least one RMD-active year where the bracket (not IRMAA) bound the conversion"
