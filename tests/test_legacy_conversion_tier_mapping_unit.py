"""WP10.2 step T8: tier mapping of an existing plan (feature-tiers design section 6)."""
from __future__ import annotations

from src import module_catalog as mc
from src.active_plan import build_plan_file_from_csv_folder
from src.legacy_conversion.steps import t8_tier_mapping as t8
from src.legacy_conversion.steps.t8_tier_mapping import FeatureState as F
from src.stores import PlanStore
from tests import plan_fixture as pf


def test_smallest_tier_covering_used_features():
    m = t8.map_tier({
        "a": F(on=True, tier="simple", engine=False, entered_rows=None),
        "b": F(on=True, tier="standard", engine=False, entered_rows=3),
        "c": F(on=True, tier="expert", engine=False, entered_rows=0),
    })
    assert m.tier == "standard" and m.in_use == ["b"]
    assert m.switches == {"a": True, "b": True, "c": False}
    assert m.turn_off == ["c"] and not m.customized


def test_nothing_used_maps_to_simple():
    m = t8.map_tier({"x": F(on=True, tier="advanced", engine=False, entered_rows=None)})
    assert m.tier == "simple" and m.turn_off == ["x"]


def test_plan_flag_on_counts_as_used():
    m = t8.map_tier({"heloc": F(on=True, tier="advanced", engine=False, entered_rows=None, plan_flag=True)})
    assert m.tier == "advanced" and m.switches["heloc"]


def test_engine_feature_with_data_is_never_switched_off():
    # An on engine feature whose data cannot be counted is not "in use" (it does not lift the
    # tier) but the safeguard keeps it on:
    m = t8.map_tier({
        "eng_unknown": F(on=True, tier="expert", engine=True, entered_rows=None),
        "rep": F(on=True, tier="expert", engine=False, entered_rows=None),
    })
    assert m.tier == "simple"
    assert m.switches == {"eng_unknown": True, "rep": False}
    assert "cannot be counted" in m.kept_on["eng_unknown"] and m.customized


def test_engine_feature_with_entered_rows_lifts_the_tier():
    m = t8.map_tier({"eq": F(on=True, tier="expert", engine=True, entered_rows=4)})
    assert m.tier == "expert" and m.switches["eq"] and not m.kept_on


def test_off_engine_feature_and_off_plan_flag_are_not_switched_on():
    m = t8.map_tier({
        "used": F(on=True, tier="advanced", engine=False, entered_rows=1),
        "eng_off": F(on=False, tier="standard", engine=True, entered_rows=0),
        "flag_off": F(on=False, tier="standard", engine=False, entered_rows=None, plan_flag=True),
        "rep_off": F(on=False, tier="simple", engine=False, entered_rows=None),
    })
    assert m.tier == "advanced"
    assert not m.switches["eng_off"] and not m.switches["flag_off"]
    assert set(m.kept_off) == {"eng_off", "flag_off"}
    assert m.switches["rep_off"] and m.turn_on == ["rep_off"]


def test_run_writes_tier_and_switches_and_is_idempotent(tmp_path):
    plan = tmp_path / "p.rpx"
    build_plan_file_from_csv_folder(plan, pf.fixture_dir("sample_frozen"))
    with PlanStore.open(plan) as store:
        before = {k: mc.stored_switch(store, k) for k in mc.switchable_keys()}
        rep = t8.run(store)
        assert not rep.skipped
        prof = mc.plan_profile(store)
        assert prof["tier"] == rep.mapping.tier and prof["tier_stored"]
        assert set(prof["differing"]) == set(rep.mapping.kept_on) | set(rep.mapping.kept_off)
        for key in mc.switchable_keys():
            m = mc.CATALOG[key]
            if before[key] and m.engine_participation and key in rep.mapping.in_use:
                assert mc.stored_switch(store, key)
            if not before[key] and (m.engine_participation or m.gate_kind == mc.GATE_PLAN_FLAG):
                assert not mc.stored_switch(store, key)  # never switched on
        assert t8.run(store).skipped


def test_plan_with_a_chosen_tier_is_left_alone(tmp_path):
    plan = tmp_path / "p.rpx"
    build_plan_file_from_csv_folder(plan, pf.fixture_dir("sample_frozen"))
    with PlanStore.open(plan) as store:
        mc.apply_tier(store, "expert")
        rep = t8.run(store)
        assert rep.skipped and rep.reason == "tier already chosen"
        assert mc.plan_tier(store) == "expert"


def test_keep_switches_writes_only_the_marker(tmp_path):
    """WP10.3: the user's answer when the safeguard blocked a mapping: nothing moves."""
    plan = tmp_path / "p.rpx"
    build_plan_file_from_csv_folder(plan, pf.fixture_dir("sample_frozen"))
    with PlanStore.open(plan) as store:
        rows, switches = store.sectioned_data(), {k: mc.stored_switch(store, k) for k in mc.switchable_keys()}
        rep = t8.run(store, keep_switches=True)
        assert not rep.skipped and rep.reason == "switches kept" and rep.mapping is None
        assert store.sectioned_data() == rows and not mc.plan_profile(store)["tier_stored"]
        assert {k: mc.stored_switch(store, k) for k in mc.switchable_keys()} == switches
        assert t8.run(store).skipped  # marker set: never mapped later by the converter
