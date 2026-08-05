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


def test_special_strategies_visibility_follows_optional_module_capability():
    # The former "Advanced Workflow Steps" preference toggle was removed; the
    # Special Strategies page now appears in navigation only when its underlying
    # optional modules (HELOC or Charitable Giving) are enabled.
    dash = dashboard_all()
    assert "showAdvanced" not in dash
    assert "toggleAdvanced" not in dash
    assert 'if (stepId === "special_strategies")' in dash
    assert (
        'return !helocModuleEnabled() && !optionalFunctionEnabled("charitable_giving");'
        in dash
    )


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
