"""Module catalog (Inputs/Outputs reframing, v2) — consistency and the guardrail
that keeps it in lock-step with the authoritative build-time gate.

The catalog (``src.module_catalog``) is pure data + a resolver; it does not
replace ``workbook_common.OPTIONAL_MODULE_SHEETS`` (which still drives sheet
pruning). These tests assert the two never drift apart.
"""
import src.module_catalog as mc
from src.reporting.workbook_common import OPTIONAL_MODULE_SHEETS


# ── Internal consistency ─────────────────────────────────────────────────────

def test_validate_passes():
    # Also runs at import time; calling explicitly documents the contract.
    mc.validate()


def test_every_output_has_valid_kind_and_demand():
    for key, m in mc.CATALOG.items():
        assert m.kind in mc.KINDS, f"{key}: bad kind {m.kind}"
        assert m.demand in mc.DEMAND_BANDS, f"{key}: bad demand {m.demand}"


def test_prerequisites_are_resolvable_and_acyclic():
    for key in mc.CATALOG:
        deps = mc.prerequisite_outputs(key)
        assert key not in deps, f"{key} is in its own prerequisite closure (cycle)"
        for dep in deps:
            assert dep in mc.CATALOG, f"{key} requires unknown output {dep}"


def test_required_inputs_reference_known_modules():
    for key, m in mc.CATALOG.items():
        for module_id, _elements in m.requires_inputs:
            assert module_id in mc.INPUT_MODULES, f"{key}: unknown input {module_id}"


def test_comparison_mode_is_optimization_only():
    for m in mc.CATALOG.values():
        if m.mode == mc.MODE_COMPARISON:
            assert m.kind == mc.OPTIMIZATION


# ── Resolver behavior ────────────────────────────────────────────────────────

def test_resolve_pulls_transitive_prerequisites():
    # Life Insurance Need is a protection *decision* that reads the Survivor
    # stress, which itself reads the base projection.
    out = set(mc.resolve_selection(["life_insurance_need"])["outputs"])
    assert {"life_insurance_need", "survivor_stress_test", "net_worth", "cash_flow"} <= out


def test_resolve_charts_pulls_allocation_and_base():
    out = set(mc.resolve_selection(["charts_dashboard"])["outputs"])
    assert {"charts_dashboard", "net_worth", "cash_flow", "asset_allocation"} <= out


def test_resolve_aggregates_input_modules_and_elements():
    res = mc.resolve_selection(["tax_loss_harvesting"])
    assert "holdings" in res["input_modules"]
    # TLH needs lot/basis depth, not just balances.
    assert {"basis", "lots"} <= set(res["input_elements"]["holdings"])


def test_by_kind_is_demand_ordered():
    ranks = [mc.DEMAND_RANK[m.demand] for m in mc.by_kind(mc.OPTIMIZATION)]
    assert ranks == sorted(ranks)


# ── Guardrail: catalog vs authoritative OPTIONAL_MODULE_SHEETS ────────────────

def test_every_registry_toggle_is_an_optional_catalog_entry():
    catalog_optional = set(mc.optional_keys())
    for key in OPTIONAL_MODULE_SHEETS:
        assert key in catalog_optional, f"{key} in OPTIONAL_MODULE_SHEETS but not optional in catalog"


def test_optional_catalog_sheets_match_registry():
    # Every optional module that owns a sheet must map to exactly the legacy
    # sheet name the gate records. (divorce_qdro has a toggle but no sheet yet,
    # so it is exempt.)
    for key in mc.optional_keys():
        m = mc.CATALOG[key]
        if m.sheet is None:
            assert key not in OPTIONAL_MODULE_SHEETS, (
                f"{key} has no sheet in the catalog but is registered in OPTIONAL_MODULE_SHEETS")
            continue
        assert key in OPTIONAL_MODULE_SHEETS, f"{key} owns a sheet but is not registered"
        assert OPTIONAL_MODULE_SHEETS[key] == [m.sheet], (
            f"{key}: catalog sheet {m.sheet!r} != registry {OPTIONAL_MODULE_SHEETS[key]!r}")


def test_core_catalog_entries_are_not_registry_toggles():
    # Always-on core modules must never appear in the optional gate.
    for key in mc.core_keys():
        assert key not in OPTIONAL_MODULE_SHEETS, f"core module {key} must not be gated"
