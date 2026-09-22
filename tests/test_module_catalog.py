"""Module catalog (Inputs/Outputs reframing, v2) — consistency and the guardrail
that keeps it in lock-step with the authoritative build-time gate.

The catalog (``src.module_catalog``) is pure data + a resolver; it does not
replace ``workbook_common.OPTIONAL_MODULE_SHEETS`` (which still drives sheet
pruning). These tests assert the two never drift apart.
"""
from pathlib import Path

import pytest

import src.module_catalog as mc
from src.reporting.workbook_common import OPTIONAL_MODULE_SHEETS

ROOT = Path(__file__).resolve().parents[1]


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


def test_comparison_mode_is_comparison_kind_only():
    """`mode` says how a sheet is laid out; `kind` says what it is.

    The flag predates the COMPARISON kind and was a half-built version of it
    (#329 §3.1), so the one module carrying it must now also carry the kind.
    """
    for m in mc.CATALOG.values():
        if m.mode == mc.MODE_COMPARISON:
            assert m.kind == mc.COMPARISON


def test_every_optional_module_has_a_toggle_row():
    """The fourth W1 guard (#330 §7.1), kept out of `validate()` on purpose.

    An optional module with no row in client_optional_functions.csv is
    unreachable from the switch surface: `module_enabled` defaults an absent
    key to enabled, so the module is silently always-on and the Plan Features
    page has nothing to render for it. That is how Housing Comparison shipped
    "optional" while being impossible to turn off.

    This lives here rather than in `module_catalog.validate()` because it is
    the only one of the four guards that needs to read a data file.
    `module_catalog` imports nothing but the stdlib and is loaded by consumers
    that do not ship `input/demo/` -- making import-time validity depend on a
    CSV on disk would trade a real guard for a new failure mode.
    """
    import csv

    path = ROOT / "input" / "demo" / "client_optional_functions.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if (r.get("section") or "").strip() == "Optional Functions"]
    declared = {(r.get("label") or "").strip() for r in rows}

    missing = sorted(k for k, m in mc.CATALOG.items() if m.optional and k not in declared)
    assert not missing, (
        "optional modules with no toggle row in the default plan, so they are "
        f"silently always-on: {missing}")

    orphans = sorted(k for k in declared if k and k not in mc.CATALOG)
    assert not orphans, (
        f"toggle rows naming modules the catalog does not define: {orphans}")


def test_kind_and_domain_are_independent_axes():
    """#330 §4.1: neither axis may be a relabeling of the other.

    Stated as a property rather than a spot check -- if some future edit made
    every module of one kind share a domain (or vice versa), the switch nav
    would silently become a second copy of the workbook's grouping, which is
    the specific failure the two-axis design exists to prevent.
    """
    by_kind: dict[str, set[str]] = {}
    by_domain: dict[str, set[str]] = {}
    for m in mc.CATALOG.values():
        by_kind.setdefault(m.kind, set()).add(m.domain)
        by_domain.setdefault(m.domain, set()).add(m.kind)

    assert any(len(v) > 1 for v in by_kind.values()), (
        "every kind maps to exactly one domain, so domain carries no "
        "information kind does not already carry")
    assert any(len(v) > 1 for v in by_domain.values()), (
        "every domain maps to exactly one kind, so kind carries no "
        "information domain does not already carry")


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


# ── #330 §3.4: soft dependencies and engine participation (W5) ───────────────

def test_soft_dependencies_never_auto_enable():
    """`degrades_without` must stay out of the prerequisite resolver.

    The whole point of the field is that it is *not* `requires_outputs`:
    Exec Summary works fine with Monte Carlo off, it just says less, so
    auto-enabling would override a choice the user made deliberately.
    """
    for key, m in mc.CATALOG.items():
        for dep, _loses in m.degrades_without:
            assert dep not in mc.prerequisite_outputs(key), (
                f"{key}: {dep!r} is a soft dependency but resolves as a "
                f"prerequisite, so enabling {key} would silently turn it on")


def test_soft_dependents_is_the_exact_inverse_of_degrades_without():
    for key in mc.CATALOG:
        for dependent, loses in mc.soft_dependents(key):
            assert (key, loses) in mc.CATALOG[dependent].degrades_without
    # ...and nothing is missed in the other direction.
    forward = {(k, dep, loses) for k, m in mc.CATALOG.items() for dep, loses in m.degrades_without}
    reverse = {(dependent, key, loses)
               for key in mc.CATALOG for dependent, loses in mc.soft_dependents(key)}
    assert forward == reverse


def test_soft_dependents_raises_for_unknown_key():
    import pytest
    with pytest.raises(KeyError):
        mc.soft_dependents("not_a_module")


def test_monte_carlo_off_is_explainable_at_the_switch():
    """#330 §3.4's worked example, pinned.

    "Turning Monte Carlo off also removes the success-probability headline
    from Executive Summary and the fan chart from Charts" is only sayable if
    both of those modules declare the dependency. Planning Levers is the third
    site the W5 sweep found.
    """
    assert mc.soft_dependents("market_luck_stress_test") == [
        ("executive_summary", "the success-probability headline"),
        ("charts_dashboard", "the fan chart"),
        ("planning_levers_echo", "the Monte Carlo success figure in the model anchor"),
    ]


def test_engine_participants_are_the_modules_the_engine_reads():
    """The three toggles that move the projection, not just the sheet set.

    `deterministic_engine.py` reads `equity_compensation` and
    `disability_income_insurance`; `after_tax.business_taxable_estate_value`
    reads `business_succession`. W7 changes *how* those are read (raw
    `c['opt']` -> `module_enabled`), not which modules they are, so this pin
    should survive that workstream unchanged.
    """
    assert set(mc.engine_participants()) == {
        "equity_compensation", "disability_income_insurance", "business_succession"}


def test_engine_participation_defaults_off():
    # A module that says nothing must not be claimed to move the projection.
    assert mc.CATALOG["glossary"].engine_participation is False
    assert mc.CATALOG["roth_conversion_plan"].engine_participation is False


# ── #330 Q7: env-override disclosure (W4) ────────────────────────────────────

def test_force_override_is_silent_when_no_env_override_is_set(monkeypatch):
    for var in ("RETIREMENT_SYSTEM_FORCE_ALL_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"):
        monkeypatch.delenv(var, raising=False)
    assert mc.force_override("market_luck_stress_test") is None


def test_force_override_names_the_variable_that_decided_it(monkeypatch):
    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_ALL_MODULES", raising=False)
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES", "market_luck_stress_test")
    assert mc.force_override("market_luck_stress_test") == (
        "enabled", "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES")
    # A module the variable does not name is not forced.
    assert mc.force_override("survivor_stress_test") is None


def test_force_override_precedence_matches_the_gate_exactly(monkeypatch):
    """The disclosure must never name a different winner than `_base_enabled`.

    A UI that says "forced on by FORCE_ALL" about a module the build actually
    left off would be worse than showing nothing, so the two orderings are
    pinned against each other rather than just asserted separately.
    """
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ALL_MODULES", "1")
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", "market_luck_stress_test")
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES", "market_luck_stress_test")
    # FORCE_DISABLE beats both of the others, in the gate and in the disclosure.
    assert mc.force_override("market_luck_stress_test") == (
        "disabled", "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES")
    cfg = {"opt": {"market_luck_stress_test": True}}
    for key in mc.optional_keys():
        forced = mc.force_override(key)
        if forced is not None:
            assert mc.module_enabled(cfg, key) is (forced[0] == "enabled"), (
                f"{key}: disclosure says {forced[0]} but the gate says otherwise")


def test_module_status_discloses_the_override(monkeypatch):
    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES", raising=False)
    monkeypatch.delenv("RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES", raising=False)
    monkeypatch.setenv("RETIREMENT_SYSTEM_FORCE_ALL_MODULES", "1")
    row = mc.module_status({"opt": {}})["market_luck_stress_test"]
    assert row["enabled"] is True
    assert (row["forced"], row["forced_by"]) == (
        "enabled", "RETIREMENT_SYSTEM_FORCE_ALL_MODULES")


def test_module_status_reports_no_override_as_none(monkeypatch):
    for var in ("RETIREMENT_SYSTEM_FORCE_ALL_MODULES",
                "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
                "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"):
        monkeypatch.delenv(var, raising=False)
    row = mc.module_status({"opt": {"market_luck_stress_test": True}})["market_luck_stress_test"]
    # Present and explicitly null, not absent -- the UI branches on the key.
    assert row["forced"] is None and row["forced_by"] is None


# ── #330 §5.3 + Q2: plan flags as a gate kind (W6) ───────────────────────────

def test_plan_flags_are_catalogued_and_are_not_toggles():
    """The four features #330 §5.3 names, each switched by a plan row rather
    than a client_optional_functions.csv toggle."""
    assert set(mc.plan_flag_keys()) == {
        "heloc", "hybrid_ltc_policy", "daf_giving", "qcd_giving"}
    for key in mc.plan_flag_keys():
        m = mc.CATALOG[key]
        assert m.gate_kind == mc.GATE_PLAN_FLAG
        assert len(m.gate_ref) == 3 and all(m.gate_ref)
        assert m.gate_enable_label
        # Not a toggle, and therefore never in the gate the build reads...
        assert not m.optional
        assert key not in OPTIONAL_MODULE_SHEETS
        # ...but not "core always-on" either: HELOC and friends default to NO.
        assert key not in mc.core_keys()
        # A plan flag owns no workbook sheet, so it never reaches the
        # catalog-to-SHEET_REGISTRY join.
        assert m.sheet is None


def test_the_two_gate_maps_partition_rather_than_overlap():
    """A plan flag must never appear in a map whose values are fed to
    optionalFunctionEnabled() -- it has no toggle row, so it would read as
    permanently off. This is the defect that makes the filtering load-bearing
    rather than tidy."""
    toggle_keys = set(mc.optional_keys())
    flag_keys = set(mc.plan_flag_keys())
    assert not (toggle_keys & flag_keys)

    for gate_key in mc.step_gate_map().values():
        assert gate_key in toggle_keys
    for gate_key in mc.section_gate_map().values():
        assert gate_key in toggle_keys
    for gate in mc.flag_gate_map().values():
        assert gate["key"] in flag_keys
    for gate in mc.flag_section_gate_map().values():
        assert gate["key"] in flag_keys

    # No step or section is claimed by both halves.
    assert not (set(mc.step_gate_map()) & set(mc.flag_gate_map()))
    assert not (set(mc.section_gate_map()) & set(mc.flag_section_gate_map()))


def test_daf_and_qcd_are_gated_identically():
    """#330 Q2. DAF was double-gated -- `charitable_giving`'s csv_sections AND
    its own plan flag -- while QCD, the same feature from the other side, was
    gated by its plan flag alone. QCD *cannot* have a section gate: its rows
    live in the shared `Cashflow` section. So DAF was the anomaly, and the plan
    flag owns it now."""
    assert "DAF" not in mc.CATALOG["charitable_giving"].csv_sections
    assert "DAF" not in mc.section_gate_map()
    # ...and not re-introduced under the flag half either: the DAF flag's own
    # row lives in the section it would gate, so a section gate there would
    # hide the switch that turns it back on.
    assert "DAF" not in mc.flag_section_gate_map()

    daf, qcd = mc.CATALOG["daf_giving"], mc.CATALOG["qcd_giving"]
    for m in (daf, qcd):
        assert m.gate_kind == mc.GATE_PLAN_FLAG
        assert m.csv_sections == ()
        assert m.dashboard_step is None
    assert daf.domain == qcd.domain
    assert daf.kind == qcd.kind


def test_a_feature_may_not_carry_both_kinds_of_switch():
    """The double-gate Q2 removed must not be re-creatable. `optional=True`
    plus `gate_kind="plan_flag"` is exactly that shape, and validate() rejects
    it."""
    import dataclasses
    bad = dataclasses.replace(mc.CATALOG["heloc"], optional=True)
    original = mc.CATALOG["heloc"]
    mc.CATALOG["heloc"] = bad
    try:
        with pytest.raises(AssertionError, match="alternatives, not layers"):
            mc.validate()
    finally:
        mc.CATALOG["heloc"] = original
    mc.validate()
