"""Next Housing Move off => the housing plan inputs are ignored, but kept.

Design 2026-09-24 §6, off semantics [C]: when `housing_location_search` is
off, the engine treats every Next Housing Move input as blank -- the plan
stays in the current home and the current state for its whole length. The
values themselves persist in the CSV and come back when the switch is turned
on again.
"""
from __future__ import annotations

import copy
import hashlib

from src import module_catalog as mc
from src.data_io import load_csv, parse_client
from tests.conftest import TEST_INPUT_DIR

KEY = "housing_location_search"


def _demo_with_housing_plan():
    """The demo plan with every Next Housing Move input filled in (the demo
    itself ships them blank, which would make the off-state vacuous)."""
    data = load_csv(TEST_INPUT_DIR / "client_data.csv")
    data.setdefault("Other Assets", {}).setdefault("Home", {})["home_sale_year"] = "2040"
    step = data.setdefault("Housing", {}).setdefault("next_step_1", {})
    step.update({"type": "rent", "start_year": "2040", "state": "FL",
                 "monthly_rent": "3000"})
    data.setdefault("State Residency Schedule", {})["period_1"] = {
        "state": "FL", "start_year": "2040", "end_year": ""}
    return data


def _parse(data, on):
    data = copy.deepcopy(data)
    data.setdefault("Optional Functions", {}).setdefault("", {})[KEY] = "TRUE" if on else "FALSE"
    before = _housing_rows(data)
    c = parse_client(data, "", skip_live_pricing=True)
    assert _housing_rows(data) == before, "the saved housing plan must be kept"
    return c


def _housing_rows(data):
    return copy.deepcopy((data["Other Assets"]["Home"], data["Housing"],
                          data["State Residency Schedule"]))


def _csv_digest():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(TEST_INPUT_DIR.glob("*.csv"))}


def test_off_ignores_the_housing_plan_and_keeps_it():
    data = _demo_with_housing_plan()
    digest = _csv_digest()

    on = _parse(data, True)
    assert mc.module_enabled(on, KEY)
    assert on["home_sale_yr"] == 2040
    assert [s["id"] for s in on["next_housing_steps"]] == ["next_step_1"]
    assert on["residency_schedule"]

    off = _parse(data, False)
    assert not mc.module_enabled(off, KEY)
    assert off["home_sale_yr"] == 0
    assert off["home_sale_splits"] == []
    assert off["next_housing_steps"] == []
    assert off["residency_schedule"] == []
    # Constant state across every plan year.
    from src.projection_stages.deterministic_engine import state_for_year
    years = range(int(off.get("plan_start", 2026)), int(off.get("plan_start", 2026)) + 40)
    assert {state_for_year(off, y) for y in years} == {off["state"]}

    # Values persisted: the plan's CSVs are untouched by either load.
    assert _csv_digest() == digest


def test_catalog_flags():
    m = mc.CATALOG[KEY]
    assert m.engine_participation is True
    assert KEY in mc.engine_participants()
    for dependent in ("housing_trajectory_comparison", "state_residency"):
        assert KEY in [dep for dep, _ in mc.CATALOG[dependent].degrades_without]
