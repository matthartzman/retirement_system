"""WP4.1 / WP4.5: feature switches and the plan tier are ordinary plan_rows settings.

Pins the storage contract ``_read_switch`` / ``_write_switch`` work on: every switch the fixtures
store sits in the row ``module_catalog.feature_row_key`` names, and reading that row with the
parser's own boolean rule gives the switch ``parse_client`` stores. Since WP4.5 the same two
functions read and write those rows when handed an open ``PlanStore`` (``set_feature`` /
``feature_enabled``), in one transaction.
"""
from __future__ import annotations

import pytest

from src import module_catalog as mc
from src.data_io import _b, parse_client
from tests import plan_fixture as pf


def _own_switches():
    out = []
    for key in mc.CATALOG:
        try:
            out.append((key, mc.feature_row_key(key)))
        except ValueError:
            continue
    return out


def test_row_keys_follow_the_gate_kind():
    for key, (section, subsection, label) in _own_switches():
        m = mc.CATALOG[key]
        if m.gate_kind == mc.GATE_PLAN_FLAG:
            assert (section, subsection, label) == tuple(m.gate_ref)
        else:
            assert (section, subsection, label) == (mc.MODULE_TOGGLE_SECTION, "", key)
    assert mc.feature_row_key("heloc") == ("HELOC", "Setup", "heloc_enabled")
    with pytest.raises(KeyError):
        mc.feature_row_key("no_such_feature")
    core = next(k for k, m in mc.CATALOG.items() if m.gate_kind == mc.GATE_MODULE_TOGGLE and not m.optional)
    with pytest.raises(ValueError, match="always-on core"):
        mc.feature_row_key(core)


@pytest.mark.parametrize("fixture", sorted(pf.FIXTURES))
def test_stored_switch_rows_read_back_as_the_parsed_switches(tmp_path, fixture):
    ws = pf.make_plan(tmp_path, fixture)
    view = ws.store_data()
    c = parse_client(view, "", skip_live_pricing=True)
    checked = 0
    for key, (section, subsection, label) in _own_switches():
        raw = view.get(section, {}).get(subsection, {}).get(label)
        stored = mc._read_switch(c, key)
        m = mc.CATALOG[key]
        if raw is None:
            # no row: the parser stores nothing for a toggle (default_on applies) and the
            # flag's own default (off) for a plan flag; the rowless WP1.3 pages are here
            assert stored in (None, False if m.gate_kind == mc.GATE_PLAN_FLAG else None), key
            assert m.csv_row is False or m.gate_kind == mc.GATE_PLAN_FLAG, f"{key}: toggle row missing"
            continue
        assert _b(raw) == stored, key
        checked += 1
    assert checked >= 30
    # Every Optional Functions row is a known switch (no stray row would be lost by WP4.5).
    toggles = {k for k, (s, _sub, _l) in _own_switches() if s == mc.MODULE_TOGGLE_SECTION}
    assert set(view[mc.MODULE_TOGGLE_SECTION][""]) <= toggles


def test_tier_row_is_an_ordinary_setting_the_engine_ignores(tmp_path):
    ws = pf.make_plan(tmp_path)
    before = parse_client(ws.store_data(), "", skip_live_pricing=True)
    section, subsection, label = mc.PLAN_TIER_ROW
    assert section not in ws.store_data()  # fixtures carry no tier: read as DEFAULT_PLAN_TIER
    assert mc.DEFAULT_PLAN_TIER == mc.EXPERT and mc.EXPERT in mc.TIERS
    with ws.store() as store:
        rid = store.set_value(section, subsection, label, mc.ADVANCED)
        assert store.set_value(section, subsection, label, mc.STANDARD) == rid  # updated in place
        # a switch flip is the same keyed write
        flag = mc.feature_row_key("heloc")
        store.set_value(*flag, mc.SWITCH_ON)
    view = ws.store_data()
    assert view[section][subsection][label] == mc.STANDARD
    after = parse_client(view, "", skip_live_pricing=True)
    assert after["heloc_enabled"] is True and before["heloc_enabled"] is False
    assert mc.feature_enabled(after, "heloc")
    # with the switch back off, the tier row alone changes nothing the engine reads
    with ws.store() as store:
        store.set_value(*mc.feature_row_key("heloc"), mc.SWITCH_OFF)
    assert pf.plain(parse_client(ws.store_data(), "", skip_live_pricing=True)) == pf.plain(before)


# ----------------------------------------------------------------- WP4.5: the rows themselves
def test_feature_enabled_reads_the_rows_of_an_open_plan(tmp_path):
    ws = pf.make_plan(tmp_path)
    parsed = parse_client(ws.store_data(), "", skip_live_pricing=True)
    with ws.store() as store:
        for key, _row in _own_switches():
            # the rows answer what the parsed config answers (stored switches, default_on otherwise)
            assert mc.feature_enabled(store, key) == mc.feature_enabled(parsed, key), key
            stored = mc._read_switch(store, key)
            if stored is not None:  # a stored row is what the parser stored (a flag with no row parses as off)
                assert stored == mc._read_switch(parsed, key), key


def test_set_feature_writes_the_named_row_in_one_transaction(tmp_path):
    ws = pf.make_plan(tmp_path)
    key = "planning_workbench"  # a rowless WP1.3 page: no row until it is flipped
    with ws.store() as store:
        row = mc.feature_row_key(key)
        assert not store.find_rows(*row) and mc.feature_enabled(store, key) is True
        mc.set_feature(store, key, False)
        (stored,) = store.find_rows(*row)
        assert stored["value"] == mc.SWITCH_OFF and mc.feature_enabled(store, key) is False
        mc.set_feature(store, key, True)  # updated in place
        assert [r["row_id"] for r in store.find_rows(*row)] == [stored["row_id"]]
        assert store.find_rows(*row)[0]["value"] == mc.SWITCH_ON
        # a plan flag writes its own row; reading follows the parser's rule (default off)
        assert mc.feature_enabled(store, "heloc") is False
        mc.set_feature(store, "heloc", True)
        assert store.find_rows("HELOC", "Setup", "heloc_enabled")[0]["value"] == "TRUE" and mc.feature_enabled(store, "heloc")
    # persisted: the parsed config of the same plan reads the same
    parsed = parse_client(ws.store_data(), "", skip_live_pricing=True)
    assert parsed["heloc_enabled"] is True and mc.feature_enabled(parsed, key) is True


def test_set_feature_on_a_store_rolls_back_with_the_enclosing_transaction(tmp_path):
    ws = pf.make_plan(tmp_path)
    with ws.store() as store:
        with pytest.raises(RuntimeError):
            with store.transaction():
                mc.set_feature(store, "planning_workbench", False)
                raise RuntimeError("boom")
        assert not store.find_rows(*mc.feature_row_key("planning_workbench"))


def test_set_feature_still_refuses_features_without_a_switch_of_their_own(tmp_path):
    ws = pf.make_plan(tmp_path)
    core = next(k for k, m in mc.CATALOG.items() if m.gate_kind == mc.GATE_MODULE_TOGGLE and not m.optional)
    with ws.store() as store:
        with pytest.raises(ValueError, match="always-on core"):
            mc.set_feature(store, core, False)
        with pytest.raises(KeyError):
            mc.set_feature(store, "no_such_feature", True)
        assert store.all_rows() == ws.store().all_rows()
