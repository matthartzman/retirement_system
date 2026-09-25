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

    # W8b: a bundled module's switch is its PARENT's row (#330 §3.3), so it is
    # exempt from needing one -- and, below, forbidden from having one.
    missing = sorted(k for k, m in mc.CATALOG.items()
                     if m.optional and m.gated_by is None and k not in declared)
    assert not missing, (
        "optional modules with no toggle row in the default plan, so they are "
        f"silently always-on: {missing}")

    bundled = sorted(k for k, m in mc.CATALOG.items()
                     if m.gated_by is not None and k in declared)
    assert not bundled, (
        "client_optional_functions.csv carries a toggle row for a bundled "
        f"module: {bundled}. The bundle exists because those modules must "
        "always agree with their parent (#330 §3.3: 'neither can compute "
        "without the other's data'); a row of their own is a second switch "
        "that can disagree with the first, and `_base_enabled` would ignore "
        "it anyway -- it reads the parent's toggle -- so the row would render "
        "a dead switch on Plan Features.")

    orphans = sorted(k for k in declared if k and k not in mc.CATALOG)
    assert not orphans, (
        f"toggle rows naming modules the catalog does not define: {orphans}")

    # W8b: the third failure mode, and the one `validate()` structurally cannot
    # catch. It rejects `optional=True` on a plan flag (see
    # test_a_feature_may_not_carry_both_kinds_of_switch), but the double gate
    # #330 Q2 removed can also arrive from the *data* side -- a
    # client_optional_functions.csv row naming a plan-flag module. The catalog
    # would still say `optional=False`, so every assertion in this file would
    # pass, and the row would be worse than harmless: Plan Features renders one
    # switch per toggle row (`rowsForStep("optional_functions")` ->
    # `taxonomy.modules[r.label]`), so the page would show a live ON/OFF control
    # for a module whose real switch is somewhere else entirely, driving nothing
    # -- a plan flag owns no sheet, so it is in no OPTIONAL_MODULE_SHEETS entry
    # for the gate to read.
    flagged = sorted(set(declared) & set(mc.plan_flag_keys()))
    assert not flagged, (
        "client_optional_functions.csv carries a toggle row for a plan-flag "
        f"module: {flagged}. That is the #330 Q2 double gate arriving through "
        "the data rather than the catalog, and it renders a dead switch on "
        "Plan Features. A plan flag's switch is its own plan row "
        "(`gate_ref`); W8b converts rather than layers.")


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
    """The toggles that move the projection, not just the sheet set.

    `deterministic_engine.py` reads `equity_compensation` and
    `disability_income_insurance`; `after_tax.business_taxable_estate_value`
    reads `business_succession`. W7 changed *how* those are read (raw
    `c['opt']` -> `module_enabled`), not which modules they are, and this pin
    survived that workstream unchanged.

    W8b adds a fourth: `spending_tracker_ytd` gates
    `ytd_projection_blend.compute_current_year_overrides`' flow blend, which
    replaces the pro-rated projection of this year's earned income and core
    spending with the real tracked amounts for the elapsed part of the year.
    That is the projection, not a sheet, so the flag is not optional
    bookkeeping -- it is what makes #330 §3.1's F3 checkable for this module
    and what earns the stronger toggle confirmation in the UI.
    """
    assert set(mc.engine_participants()) == {
        "equity_compensation", "disability_income_insurance",
        "business_succession", "spending_tracker_ytd",
        # Design 2026-09-24 §6 [C]: off blanks the housing plan inputs.
        "housing_location_search"}


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

    # No step is claimed by both halves.
    assert not (set(mc.step_gate_map()) & set(mc.flag_gate_map()))
    # No plan flag declares csv_sections today, so section_gate_map() has
    # nothing to leak -- confirmed directly rather than via a second map that
    # has no consumer yet.
    for key in flag_keys:
        assert mc.CATALOG[key].csv_sections == ()


def test_every_module_has_exactly_one_kind_of_switch_or_none():
    """W8b's standing check on W6's outcome, and the reason W8b converts
    nothing.

    The master plan lists Hybrid LTC and DAF+QCD under "newly optional", but
    W6 had already given all three a switch -- a plan flag -- and `validate()`
    now rejects `optional=True` on top of one, because that combination *is*
    the DAF double gate #330 Q2 exists to end. So W8b's job for those three is
    to keep the partition true, not to move them across it.

    The partition asserted here: every catalogued module is exactly one of
    core (no switch), toggle-switched (`optional`), or flag-switched
    (`gate_kind="plan_flag"`) -- never two, never none-of-the-above. W6's
    `test_the_two_gate_maps_partition_rather_than_overlap` asserts the halves
    are disjoint; this asserts they are also *exhaustive*, which is what makes
    "which switch does this feature have?" a question with an answer for every
    module rather than for the ones someone remembered to classify.
    """
    core = set(mc.core_keys())
    toggles = set(mc.optional_keys())
    flags = set(mc.plan_flag_keys())

    assert not (core & toggles) and not (core & flags) and not (toggles & flags)
    assert core | toggles | flags == set(mc.CATALOG), (
        "modules classified by no switch kind at all: "
        f"{sorted(set(mc.CATALOG) - (core | toggles | flags))}")

    # And the three W8b names stay on the flag side, with the reason attached.
    for key in ("hybrid_ltc_policy", "daf_giving", "qcd_giving"):
        assert key in flags, f"{key} left the plan-flag partition"
        assert key not in toggles, (
            f"{key} gained a client_optional_functions.csv toggle on top of its "
            f"plan flag -- the #330 Q2 double gate")


def test_daf_and_qcd_are_gated_identically():
    """#330 Q2. DAF was double-gated -- `charitable_giving`'s csv_sections AND
    its own plan flag -- while QCD, the same feature from the other side, was
    gated by its plan flag alone. QCD *cannot* have a section gate: its rows
    live in the shared `Cashflow` section. So DAF was the anomaly, and the plan
    flag owns it now."""
    assert "DAF" not in mc.CATALOG["charitable_giving"].csv_sections
    assert "DAF" not in mc.section_gate_map()

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


def test_topics_are_the_nine_life_areas():
    """#332 topic re-cut (§1.1): Risk & Resilience dissolves, Assets &
    Protection renames to Insurance & Care, Reports & Documentation renames
    to Whole Plan."""
    assert mc.DOMAINS == (
        "Income & Benefits", "Spending", "Housing & Property", "Investments",
        "Taxes", "Insurance & Care", "Estate & Legacy", "Family & Business",
        "Whole Plan",
    )


def test_topic_recut_membership():
    """#332 §1.1: the 11 modules whose domain moves to a different topic
    (not merely renamed in place)."""
    want = {
        "market_luck_stress_test": "Investments",
        "daf_giving": "Taxes", "qcd_giving": "Taxes",
        "life_insurance_need": "Insurance & Care",
        "survivor_stress_test": "Insurance & Care",
        "long_term_care_stress": "Insurance & Care",
        "existing_life_insurance": "Insurance & Care",
        "hybrid_ltc_policy": "Insurance & Care",
        "divorce_qdro": "Family & Business",
        "what_if_analysis": "Whole Plan",
        "charts_dashboard": "Whole Plan",
    }
    assert {k: mc.CATALOG[k].domain for k in want} == want


def test_no_module_uses_a_retired_topic():
    retired = {"Risk & Resilience", "Assets & Protection", "Reports & Documentation"}
    assert not [k for k, m in mc.CATALOG.items() if m.domain in retired]


def test_answer_types_drive_letter_groups():
    assert mc.ANSWER_TYPES == ("Reports", "Optimizers", "Comparisons", "Risks", "Reference")
    assert mc.KIND_ANSWER_TYPE == {
        "projection": "Reports", "worksheet": "Reports",
        "optimization": "Optimizers", "comparison": "Comparisons",
        "stress_test": "Risks", "protection": "Risks",
        "diagnostics": "Reference", "reference": "Reference",
    }
    for kind, at in mc.KIND_ANSWER_TYPE.items():
        assert mc.KIND_LETTER_PREFIX[kind] == str(mc.ANSWER_TYPES.index(at) + 1)


def test_workbook_section_titles_match_answer_types():
    from src.reporting.workbook_common import _SECTION_META
    assert [t.split(". ", 1)[1] for t, _ in (_SECTION_META[str(i)] for i in range(1, 6))] == list(mc.ANSWER_TYPES)


def test_housing_location_search_is_named_next_housing_move():
    assert mc.CATALOG["housing_location_search"].name == "Next Housing Move"
