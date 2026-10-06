"""WP1.3: six formerly always-on pages are switchable, default on, rowless."""
import csv
from pathlib import Path

from src import module_catalog as mc

ROOT = Path(__file__).resolve().parent.parent
PAGE_GATES = {
    "estate": "estate_legacy_plan",
    "annuity_death_benefits": "insurance_inputs",
    "assets_home_cash": "reserve_requirements",
    "strategy_scenarios": "what_if_analysis",
    "strategy_workbench": "planning_workbench",
}


def test_pages_are_gated_by_their_features():
    gates = mc.step_gate_map()
    for step, key in PAGE_GATES.items():
        assert gates[step] == key


def test_new_features_default_on_with_no_csv_row():
    new = [k for k, m in mc.CATALOG.items() if not m.csv_row]
    assert sorted(new) == ["insurance_inputs", "planning_workbench", "reserve_requirements"]
    assert set(mc.rowless_defaults()) == set(new)
    for plan in ("demo", "sample_plan_frozen"):
        for path in (ROOT / "input" / plan).glob("client_optional_functions.csv") if (ROOT / "input" / plan).exists() else []:
            with path.open(encoding="utf-8-sig", newline="") as fh:
                labels = {r.get("label") for r in csv.DictReader(fh)}
            assert not (labels & set(new))
    for k in new:
        assert mc.feature_enabled({}, k) is True
        assert mc.feature_enabled({"opt": {}}, k) is True
        mc.get(k)  # validated
    mc.validate()


def test_set_feature_turns_them_off_in_memory():
    c = {}
    mc.set_feature(c, "planning_workbench", False)
    assert mc.feature_enabled(c, "planning_workbench") is False
