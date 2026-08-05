from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_CSS = ROOT / "frontend" / "css" / "admin.css"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


def test_admin_ui_uses_guided_user_ui_shell_and_navigation_model():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for token in [
        "admin-shell",
        "card side nav",
        "card content",
        "card help",
        "stepbtn",
        "pane-head",
        "help-callout",
        "What this page controls",
        "setAdminStep",
        "ADMIN_HELP",
    ]:
        assert token in html


def test_admin_ui_preserves_compact_inputs_and_raw_fallback_in_user_style():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_CSS.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    for token in [
        "cfg-input",
        "cfg-select",
        "grid-input",
        "showSettingHelp",
        "setting-help-btn",
        "Advanced raw CSV",
        "Compact table view",
        "raw CSV",
    ]:
        assert token in html
