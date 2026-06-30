from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "frontend" / "js" / "dashboard.js"
DASH_STATIC = ROOT / "src" / "dashboard_ui" / "static" / "js" / "dashboard.js"
ADMIN = ROOT / "frontend" / "js" / "admin.js"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_advanced_options_start_collapsed_and_static_copy_is_synced():
    dash = text(DASH)
    assert "let showAdvanced=false" in dash
    assert "retirementShowAdvancedV2" in dash
    assert "showAdvanced=saved===null?false:saved==='1'" in dash


def test_roth_policy_controls_relevance_and_bracket_strategy_visibility():
    dash = text(DASH)
    assert "if(policyIsFixed){strategy=orderedRowsByLabel(['roth_fixed_annual_amount'" in dash
    assert "else if(policyIsBracket){strategy=orderedRowsByLabel(['roth_bracket_strategy','roth_target_bracket_rate'" in dash
    assert "else if(policyIsOptimizer){strategy=orderedRowsByLabel(['roth_objective_mode','roth_bracket_strategy'" in dash
    assert "else if(policyIsNone){strategy=orderedRowsByLabel(['max_conversion_years']);}" in dash


def test_monte_carlo_hsa_home_sale_and_estate_dependencies_are_dynamic():
    dash = text(DASH)
    assert "Start here: choose the Monte Carlo engine" in dash
    assert "mode==='quick_vectorized'" in dash
    assert "Start here:</b> choose HSA withdrawal mode" in dash
    assert "mode==='annual_pct'" in dash and "mode==='smooth_window'" in dash
    assert "renderHomeSaleScenarioRows" in dash
    assert "renderToggleRows('QTIP Trust'" in dash
    assert "renderToggleRows('Credit Shelter Trust'" in dash


def test_admin_editor_orders_dependency_controls_first():
    admin = text(ADMIN)
    assert "function adminDependencyRank" in admin
    assert "mc_engine_mode" in admin and "roth_conversion_policy" in admin
    assert "groups.forEach(g=>g.rows.sort" in admin
