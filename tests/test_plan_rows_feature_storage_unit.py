"""WP4.1: feature switches and the plan tier are ordinary plan_rows settings.

Pins the storage contract WP4.5 moves ``_read_switch`` / ``_write_switch`` onto (their
internals are unchanged here): every switch the fixtures store sits in the row
``module_catalog.feature_row_key`` names, and reading that row with the parser's own boolean
rule gives the switch ``parse_client`` stores today.
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
