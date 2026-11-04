"""Left-nav follow-ups (E): the Features popover and Plan Features cannot disagree.

Both pages flip a switch through ``setPlanFeatureSwitch`` -> ``POST /api/plan/feature`` ->
``module_catalog.set_feature``. This pins the storage contract from the other side: writing the plan
row named by ``feature_row_key`` directly (what a row switch on Plan Features ends up as) and
calling ``set_feature`` store the same value and read back through ``feature_enabled`` identically,
on and off, for a module-toggle feature and for a plan flag.
"""
from __future__ import annotations

import pytest

from src import module_catalog as mc
from src.data_io import parse_client
from tests import plan_fixture as pf

# one module-toggle feature and one plan flag, each with a switch of its own
CASES = [("hsa_drawdown", mc.GATE_MODULE_TOGGLE), ("heloc", mc.GATE_PLAN_FLAG)]


def _stored(ws, key):
    section, subsection, label = mc.feature_row_key(key)
    return ws.store_data().get(section, {}).get(subsection, {}).get(label)


def _state(ws, key):
    with ws.store() as store:
        live = mc.feature_enabled(store, key)
    parsed = mc.feature_enabled(parse_client(ws.store_data(), "", skip_live_pricing=True), key)
    return _stored(ws, key), live, parsed


@pytest.mark.parametrize("key,kind", CASES)
@pytest.mark.parametrize("on", [True, False])
def test_popover_and_plan_features_write_the_same_row(tmp_path, key, kind, on):
    assert mc.CATALOG[key].gate_kind == kind
    popover = pf.make_plan(tmp_path / "popover")
    plan_features = pf.make_plan(tmp_path / "plan_features")
    # start both from the opposite value so a no-op write cannot pass
    for ws in (popover, plan_features):
        with ws.store() as store:
            mc.set_feature(store, key, not on)

    with popover.store() as store:  # the popover path
        mc.set_feature(store, key, on)
    with plan_features.store() as store:  # the row Plan Features' switch writes
        store.set_value(*mc.feature_row_key(key), mc.SWITCH_ON if on else mc.SWITCH_OFF)

    a, b = _state(popover, key), _state(plan_features, key)
    assert a == b
    assert a[0] == (mc.SWITCH_ON if on else mc.SWITCH_OFF)
    assert a[1] is on and a[2] is on
