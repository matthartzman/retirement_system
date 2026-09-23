from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "frontend" / "js" / "dashboard.js"
DASH_STATIC = ROOT / "src" / "dashboard_ui" / "static" / "js" / "dashboard.js"
ADMIN = ROOT / "frontend" / "js" / "admin.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def dashboard_all() -> str:
    """dashboard.js plus every extracted dashboard_decomp_*.js sibling module.

    The decomposition moved cohesive UI blocks (e.g. estate/insurance rendering)
    into classic scripts loaded before dashboard.js. Dependency-ordering
    assertions target the assembled behavior, so read them together."""
    js_dir = ROOT / "frontend" / "js"
    parts = [text(DASH)]
    parts += [text(p) for p in sorted(js_dir.glob("dashboard_decomp_*.js"))]
    return "\n".join(parts)


def test_special_strategies_is_unreachable_so_it_needs_no_gate_of_its_own():
    """#330 §5.3 (W6) removed the hand-written `special_strategies` branch from
    stepGatedByOptionalModule(). That is behavior-preserving only because the
    step is no longer reachable at all, so this pins the three facts the
    removal rests on -- if any of them is undone, the gate has to come back.

    1. The former "Advanced Workflow Steps" preference toggle is still gone.
    2. The STEPS entry is an ungrouped, hidden shell (#323 kept it only so row
       routing still keys off the id), and visibleSteps() drops a
       `group === null` step before gating could matter.
    3. navigation.js redirects the id (to heloc_strategy since #329/#330 W9
       moved HELOC off strategy_optimize -- the redirect target changed, the
       fact that it always redirects rather than becoming active did not), so
       it can never become the active step either -- the one case where
       visibleSteps() ignores the group check.
    """
    dash = dashboard_all()
    assert "showAdvanced" not in dash
    assert "toggleAdvanced" not in dash
    assert 'if (stepId === "special_strategies")' not in dash
    assert (
        'return !helocModuleEnabled() && !optionalFunctionEnabled("charitable_giving");'
        not in dash
    )

    # (2) the hidden, ungrouped shell
    shell = text(DASH)[text(DASH).index('id: "special_strategies"') :][:200]
    assert "group: null" in shell
    assert "hidden: true" in shell
    assert 'if (s.group === null && s.id !== activeStep) return false;' in dash

    # (3) the redirect that keeps it from ever being the active step
    nav = text(ROOT / "frontend" / "js" / "navigation.js")
    assert "special_strategies:{step:'heloc_strategy'}" in nav


def test_heloc_step_gating_is_declared_not_hand_written():
    """The other half of the same removal: HELOC's gate is now the catalog's
    gate_ref, served as moduleGates.flag_gates, rather than an `if` naming the
    step id. Pinned here too because this file is where the old branch was
    asserted from."""
    dash = dashboard_all()
    assert 'if (stepId === "heloc_strategy") return !helocModuleEnabled();' not in dash
    assert "moduleGates.flag_gates" in dash


def test_helocs_empty_page_note_is_also_declared_not_hand_written():
    """#329/#330 W9: rowsForStep()'s renderFields() note -- the LAST hand-
    written HELOC-only branch named in W6's handoff to W9 -- now reads
    moduleGates.flag_gates[step] generically (like the two branches above,
    which W6 already removed) instead of a HELOC-only `if`."""
    dash = dashboard_all()
    assert (
        'if (step === "heloc_strategy" && !helocModuleEnabled())' not in dash
    )
    assert "(moduleGates.flag_gates || {})[step]" in dash


def test_roth_policy_controls_relevance_and_bracket_strategy_visibility():
    dash = dashboard_all()
    assert 'if (policyIsFixed) {\n    strategy = orderedRowsByLabel([\n      "roth_fixed_annual_amount"' in dash
    assert 'else if (policyIsBracket) {\n    strategy = orderedRowsByLabel([\n      "roth_bracket_strategy",\n      "roth_target_bracket_rate"' in dash
    assert 'else if (policyIsOptimizer) {\n    strategy = orderedRowsByLabel([\n      "roth_objective_mode",\n      "roth_bracket_strategy"' in dash
    assert '} else if (policyIsNone) {\n    strategy = orderedRowsByLabel(["max_conversion_years"]);' in dash


def test_monte_carlo_hsa_home_sale_and_estate_dependencies_are_dynamic():
    dash = dashboard_all()
    assert "Start here: choose the Monte Carlo engine" in dash
    assert 'mode === "quick_vectorized"' in dash
    assert "Start here:</b> choose HSA withdrawal mode" in dash
    assert 'mode === "annual_pct"' in dash and '"smooth_window"' in dash
    assert "renderHomeSaleScenarioRows" in dash
    assert 'renderToggleRows(\n    "QTIP Trust"' in dash
    assert 'renderToggleRows(\n    "Credit Shelter Trust"' in dash


def test_admin_editor_orders_dependency_controls_first():
    admin = text(ADMIN)
    assert "function adminDependencyRank" in admin
    assert "mc_engine_mode" in admin and "roth_conversion_policy" in admin
    assert "groups.forEach((g) =>\n    g.rows.sort" in admin
