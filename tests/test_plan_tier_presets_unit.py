"""WP5.1: tier presets, the plan tier row and the derived profile (``module_catalog``).

A tier is a starting set of switches (design 2026-10-04 §2-§4): ``tier_preset`` is every
switchable feature whose catalog tier ranks at or below it, so the presets are cumulative.
``apply_tier`` writes the tier row and the switches in one transaction; "customized" is derived
from the stored switches and never stored; a plan with no tier row reads as EXPERT and nothing
about it changes.
"""
from __future__ import annotations

import pytest

from src import module_catalog as mc
from src.data_io import parse_client
from tests import plan_fixture as pf


@pytest.fixture(autouse=True)
def _no_env_overrides(monkeypatch):
    # The RETIREMENT_SYSTEM_FORCE_* admin tier decides feature_enabled() above the stored switch;
    # these tests are about the stored switches.
    for var in ("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ALL_MODULES"):
        monkeypatch.delenv(var, raising=False)


def _parsed(ws):
    return parse_client(ws.store_data(), "", skip_live_pricing=True)


# ------------------------------------------------------------------------------- presets
def test_switchable_keys_are_exactly_the_features_with_a_switch_of_their_own():
    keys = mc.switchable_keys()
    assert len(keys) == len(set(keys))
    for key, m in mc.CATALOG.items():
        try:
            mc.feature_row_key(key)
            own = True
        except ValueError:
            own = False
        assert (key in keys) == own, key
    # spot checks of the three kinds of "no switch of its own" and of a plan flag
    assert "net_worth" not in keys                 # always-on core
    assert "spending_summary" not in keys          # gated_by spending_tracker_ytd
    assert "charitable_giving" not in keys         # gated_by_any_flag DAF / QCD
    assert "heloc" in keys and "planning_workbench" in keys


def test_each_preset_holds_the_previous_one():
    previous: frozenset = frozenset()
    for tier in mc.TIERS:
        preset = mc.tier_preset(tier)
        assert previous < preset, f"{tier} must strictly extend the tier below it"
        previous = preset
    assert mc.tier_preset(mc.EXPERT) == frozenset(mc.switchable_keys())


def test_a_preset_is_the_catalog_tier_column():
    for tier in mc.TIERS:
        want = {k for k in mc.switchable_keys() if mc.TIER_RANK[mc.CATALOG[k].tier] <= mc.TIER_RANK[tier]}
        assert mc.tier_preset(tier) == want, tier


def test_simple_preset_matches_the_design_table():
    simple = mc.tier_preset(mc.SIMPLE)
    # design §4: Simple = core pages + Roth Conversion, Monte Carlo, Lifetime Taxes, Charts
    assert {"roth_conversion_plan", "market_luck_stress_test", "lifetime_tax_projection",
            "charts_dashboard"} <= simple
    # ...and the reference sheets every tier builds (Methodology, Glossary)
    assert simple - {"roth_conversion_plan", "market_luck_stress_test", "lifetime_tax_projection",
                     "charts_dashboard"} == {"methodology_rerun", "glossary"}
    # Standard's own additions are not in it
    for key in ("estate_legacy_plan", "existing_life_insurance", "reserve_requirements",
                "social_security_timing", "survivor_stress_test", "education_funding_529", "hybrid_ltc_policy"):
        assert key not in simple and key in mc.tier_preset(mc.STANDARD), key
    for key in ("heloc", "daf_giving", "qcd_giving", "what_if_analysis", "spending_tracker_ytd"):
        assert mc.CATALOG[key].tier == mc.ADVANCED and key not in mc.tier_preset(mc.STANDARD), key
    for key in ("planning_workbench", "equity_compensation", "business_succession", "rmd_audit"):
        assert key not in mc.tier_preset(mc.ADVANCED) and key in mc.tier_preset(mc.EXPERT), key


def test_unknown_tier_is_refused():
    with pytest.raises(ValueError, match="unknown tier"):
        mc.tier_preset("platinum")
    assert mc.tier_preset(" Standard ") == mc.tier_preset(mc.STANDARD)


# ----------------------------------------------------------------------------- tier row
def test_plan_tier_reads_the_row_on_a_store_and_on_dicts(tmp_path):
    ws = pf.make_plan(tmp_path)
    section, subsection, label = mc.PLAN_TIER_ROW
    assert mc.plan_tier({}) == mc.DEFAULT_PLAN_TIER == mc.EXPERT
    assert mc.plan_tier({section: {subsection: {label: "Standard"}}}) == mc.STANDARD
    assert mc.plan_tier({"plan_tier": "simple"}) == mc.SIMPLE
    assert mc.plan_tier({section: {subsection: {label: "gold"}}}) == mc.EXPERT  # not a tier: the default
    with ws.store() as store:
        assert mc.plan_tier(store) == mc.EXPERT and not mc.plan_profile(store)["tier_stored"]
        store.set_value(section, subsection, label, "advanced")
        assert mc.plan_tier(store) == mc.ADVANCED and mc.plan_profile(store)["tier_stored"]
    assert mc.plan_tier(ws.store_data()) == mc.ADVANCED


@pytest.mark.parametrize("fixture", sorted(pf.FIXTURES))
def test_a_plan_with_no_tier_row_reads_expert_and_nothing_changes(tmp_path, fixture):
    ws = pf.make_plan(tmp_path, fixture)
    parsed = _parsed(ws)
    before = {key: mc.feature_enabled(parsed, key) for key in mc.CATALOG}
    with ws.store() as store:
        revision = store.revision()
        profile = mc.plan_profile(store)
        mc.tier_changes(store, mc.SIMPLE)
        assert store.revision() == revision  # reading the profile or a preview writes nothing
        assert profile["tier"] == mc.EXPERT and profile["tier_stored"] is False
        # every switch reads as it did before the tier machinery existed
        assert {key: mc.feature_enabled(store, key) for key in mc.CATALOG} == before
    assert {key: mc.feature_enabled(_parsed(ws), key) for key in mc.CATALOG} == before
    # the fixtures leave several features off, which against the all-on Expert preset is a
    # customized Expert plan; the switches differing are exactly the stored-off ones
    assert profile["differing"] == [k for k in mc.switchable_keys() if not mc.stored_switch(parsed, k)]
    assert profile["customized"] is bool(profile["differing"])
    assert profile["label"] == ("Expert (customized)" if profile["customized"] else "Expert")


# ---------------------------------------------------------------------------- apply_tier
def _non_switch_rows(store):
    switch_rows = {mc.feature_row_key(k) for k in mc.switchable_keys()} | {mc.PLAN_TIER_ROW}
    return [(r["row_id"], r["value"]) for r in store.all_rows()
            if (r["section"], r["subsection"], r["label"]) not in switch_rows]


@pytest.mark.parametrize("tier", mc.TIERS)
def test_apply_tier_round_trip(tmp_path, tier):
    ws = pf.make_plan(tmp_path)
    preset = mc.tier_preset(tier)
    with ws.store() as store:
        data_before = _non_switch_rows(store)
        expected = mc.tier_changes(store, tier)
        changes = mc.apply_tier(store, tier)
        assert changes == expected
        profile = mc.plan_profile(store)
        assert profile == {"tier": tier, "tier_stored": True, "customized": False,
                           "label": mc.TIER_LABELS[tier], "differing": []}
        for key in mc.switchable_keys():
            assert mc.stored_switch(store, key) == (key in preset), key
            assert mc.feature_enabled(store, key) == (key in preset), key
        assert mc.tier_changes(store, tier) == {"turn_on": [], "turn_off": []}
        assert _non_switch_rows(store) == data_before  # entered data is kept, untouched
        (tier_row,) = store.find_rows(*mc.PLAN_TIER_ROW)
        assert tier_row["value"] == tier and tier_row["units"] == mc.PLAN_TIER_UNITS
    # the engine view of the same plan agrees (the parsed config carries the switches, not
    # the tier row: the engine ignores the tier, so the profile is read from the rows)
    parsed = _parsed(ws)
    for key in mc.switchable_keys():
        assert mc.stored_switch(parsed, key) == (key in preset), key
        assert mc.feature_enabled(parsed, key) == (key in preset), key


def test_switching_tiers_back_and_forth_ends_on_the_last_preset(tmp_path):
    ws = pf.make_plan(tmp_path)
    with ws.store() as store:
        mc.apply_tier(store, mc.SIMPLE)
        changes = mc.apply_tier(store, mc.EXPERT)
        assert changes["turn_off"] == [] and set(changes["turn_on"]) == mc.tier_preset(mc.EXPERT) - mc.tier_preset(mc.SIMPLE)
        assert all(mc.stored_switch(store, k) for k in mc.switchable_keys())
        assert len(store.find_rows(*mc.PLAN_TIER_ROW)) == 1  # one tier row, updated in place
        assert mc.plan_profile(store)["label"] == "Expert"


def test_customized_is_derived_from_the_switches(tmp_path):
    ws = pf.make_plan(tmp_path)
    with ws.store() as store:
        mc.apply_tier(store, mc.STANDARD)
        mc.set_feature(store, "heloc", True)                 # an Advanced feature turned on
        mc.set_feature(store, "estate_legacy_plan", False)   # a Standard feature turned off
        profile = mc.plan_profile(store)
        assert profile["tier"] == mc.STANDARD and profile["customized"] is True
        assert profile["label"] == "Standard (customized)"
        assert profile["differing"] == [k for k in mc.switchable_keys() if k in ("heloc", "estate_legacy_plan")]
        # nothing about "customized" is stored: putting the switches back un-customizes it
        rows_before = len(store.all_rows())
        mc.set_feature(store, "heloc", False)
        mc.set_feature(store, "estate_legacy_plan", True)
        assert mc.plan_profile(store)["customized"] is False
        assert len(store.all_rows()) == rows_before
        assert mc.plan_tier(store) == mc.STANDARD


def test_apply_tier_is_one_transaction_and_refuses_bad_input(tmp_path):
    ws = pf.make_plan(tmp_path)
    with ws.store() as store:
        revision = store.revision()
        with pytest.raises(ValueError, match="unknown tier"):
            mc.apply_tier(store, "gold")
        with pytest.raises(RuntimeError):
            with store.transaction():
                mc.apply_tier(store, mc.SIMPLE)
                raise RuntimeError("boom")
        assert store.revision() == revision and not store.find_rows(*mc.PLAN_TIER_ROW)
    with pytest.raises(TypeError):
        mc.apply_tier({"opt": {}}, mc.SIMPLE)


def test_tier_changes_lists_what_a_pick_would_flip(tmp_path):
    ws = pf.make_plan(tmp_path)
    with ws.store() as store:
        changes = mc.tier_changes(store, mc.SIMPLE)
        stored = {k: mc.stored_switch(store, k) for k in mc.switchable_keys()}
    simple = mc.tier_preset(mc.SIMPLE)
    assert changes["turn_on"] == [k for k in mc.switchable_keys() if k in simple and not stored[k]]
    assert changes["turn_off"] == [k for k in mc.switchable_keys() if k not in simple and stored[k]]
    assert "estate_legacy_plan" in changes["turn_off"] and "roth_conversion_plan" not in changes["turn_off"]
