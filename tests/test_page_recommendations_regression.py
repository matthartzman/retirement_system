from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"
SPEC = ROOT / "documentation" / "CURRENT_SYSTEM_DESIGN_SPEC.md"
CHANGELOG = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"


def test_page_recommendations_are_explainable_and_source_linked():
    js = (DASHBOARD_JS.read_text(encoding="utf-8") + (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8"))

    assert "RECOMMENDATION_ENGINE_VERSION" in js
    assert "page_recommendations_v1" in js
    assert "function pageRecommendationsHtml" in js
    assert "function pageRecommendationsForStep" in js
    assert "function jumpRecommendationSource" in js
    assert "recommendation-source-jump" in js
    assert "Each item links back to the input" in js
    assert "Explainable suggestions only" in js


def test_recommendations_cover_initial_roadmap_domains_without_auto_applying_values():
    js = (DASHBOARD_JS.read_text(encoding="utf-8") + (ROOT / "frontend/js/dashboard_decomp_row_model.js").read_text(encoding="utf-8"))

    for fn in [
        "function rothPageRecommendations",
        "function allocationPageRecommendations",
        "function spendingPageRecommendations",
        "function socialSecurityPageRecommendations",
    ]:
        assert fn in js

    # Social Security recommendations were merged into the Income & Social Security
    # page (income_retirement); the standalone ss_timing step no longer exists.
    for step in ["roth_conversion", "allocation_assets", "allocation_policy", "spending_core", "income_retirement"]:
        assert step in js

    # stepStats moved to dashboard_decomp_row_model.js (domain-module-split
    # shared-core extraction) -- no longer physically adjacent to the
    # recommendation functions in dashboard.js. pageSaveMode is the next
    # top-level function after them in the current file.
    recommendations_section = js[js.index("const RECOMMENDATION_ENGINE_VERSION") : js.index("function pageSaveMode")]
    assert "editValue(" not in recommendations_section
    assert "saveAll(" not in recommendations_section
    assert "runBuild(" not in recommendations_section


def test_recommendation_ui_is_styled_and_roadmap_updated():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")

    assert ".page-recommendations" in css
    assert ".recommendation-card" in css
    assert ".recommendation-source-jump" in css
    assert "Recommendation engine for Roth/allocation/spending/SS. Initial explainable" in spec
    assert "page_recommendations_v1" in spec
    assert "# v11 page-local recommendation engine" in changelog
