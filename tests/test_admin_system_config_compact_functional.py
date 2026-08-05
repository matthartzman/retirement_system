from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"
SYSTEM_CONFIG = ROOT / "system_config.csv"


def test_admin_system_config_uses_compact_table_editor():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "Compact table view" in html
    assert "buildConfigTable" in html
    assert "showSettingHelp" in html
    assert "setting-help-btn" in html
    assert "Advanced raw CSV" in html
    assert "cfgSearch" in html
    assert "rows:sysCfgRows" in html


def test_admin_system_config_has_pricing_and_optimizer_helper_notes():
    html = ADMIN_HTML.read_text(encoding="utf-8") + "\n" + ADMIN_JS.read_text(encoding="utf-8")
    assert "LIVE tries quote providers first" in html
    assert "CACHE uses cached prices" in html
    assert "GLOBAL_TAX_AWARE solves household-level drift/tax/location tradeoffs" in html
    assert "Startup-only settings" in html


def test_system_config_contains_notes_for_compact_editor():
    csv_text = SYSTEM_CONFIG.read_text(encoding="utf-8-sig")
    assert "section,subsection,label,value,units,notes" in csv_text.splitlines()[0]
    assert "Market Pricing,Holdings,pricing_mode" in csv_text
    assert "Rebalancing,Optimization,trade_optimizer_mode" in csv_text
