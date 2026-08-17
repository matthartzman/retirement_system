from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"
RECOMMENDATIONS_JS = ROOT / "frontend" / "js" / "dashboard_decomp_page_recommendations.js"
SPEC = ROOT / "documentation" / "CURRENT_SYSTEM_DESIGN_SPEC.md"
CHANGELOG = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"


def test_page_recommendations_are_explainable_and_source_linked():
    js = dashboard_js_text()

    assert "RECOMMENDATION_ENGINE_VERSION" in js
    assert "page_recommendations_v1" in js
    assert "function pageRecommendationsHtml" in js
    assert "function pageRecommendationsForStep" in js
    assert "function jumpRecommendationSource" in js
    assert "recommendation-source-jump" in js
    assert "Each item links back to the input" in js
    assert "Explainable suggestions only" in js


def test_recommendations_cover_initial_roadmap_domains_without_auto_applying_values():
    js = dashboard_js_text()

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

    # "Recommendations suggest, they never apply" used to be checked by slicing
    # dashboard.js between two landmarks that happened to bracket the
    # recommendation functions. That slice stopped meaning anything once the
    # cluster was extracted (F3.1): the landmarks are both still in
    # dashboard.js, so the slice keeps passing while covering unrelated code.
    # The recommendation functions now have a file of their own, which is a
    # stronger and far more stable boundary than two neighbouring symbols.
    recommendations_section = RECOMMENDATIONS_JS.read_text(encoding="utf-8")
    assert "function pageRecommendationsHtml" in recommendations_section
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
