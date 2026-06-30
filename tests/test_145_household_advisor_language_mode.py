from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_JS = ROOT / "frontend" / "js" / "dashboard.js"
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"
SPEC = ROOT / "documentation" / "CURRENT_SYSTEM_DESIGN_SPEC.md"
CHANGELOG = ROOT / "documentation" / "GOLDEN_MASTER_CHANGELOG.md"


def test_language_mode_is_browser_local_display_preference():
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "LANGUAGE_MODE_LS_KEY" in js
    assert "retirement.language_mode.v1" in js
    assert "function setLanguageMode" in js
    assert "function languageModeText" in js
    assert "function languageModeBannerHtml" in js
    assert "function languageModeControlsHtml" in js
    assert "Display preference only" in js
    assert "calculations, saved values, build snapshots, and exports are unchanged" in js


def test_language_mode_controls_are_normal_settings_not_logic_branching():
    js = DASHBOARD_JS.read_text(encoding="utf-8")

    assert "Language mode" in js
    assert "Household mode" in js
    assert "Advisor mode" in js
    assert "${languageModeControlsHtml()}" in js
    assert "window.setLanguageMode=setLanguageMode" in js
    assert "data-language-mode" in js or "dataset.languageMode" in js
    assert "runBuild" in js  # build logic remains separately defined
    assert "buildBody" in js
    assert "languageMode" not in js[js.index("async function runBuild") : js.index("function downloadFile")]


def test_language_mode_is_styled_and_roadmap_marked_complete():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    spec = SPEC.read_text(encoding="utf-8")
    changelog = CHANGELOG.read_text(encoding="utf-8")

    assert ".language-mode-banner" in css
    assert ".language-mode-card" in css
    assert ".language-mode-toggle" in css
    assert "Advisor vs household language mode. Completed" in spec
    assert "Add household/advisor language mode. Completed" in spec
    assert "v10 household/advisor language mode" in changelog
