from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"


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


def test_system_config_contains_notes_for_compact_editor(tmp_path):
    # WP8.1: the editor rows are the app.db runtime settings plus the engine knobs of the plan.
    from src.server_services.admin_service import system_config_payload
    payload = system_config_payload(tmp_path / "app.db")
    rows = payload["rows"]
    assert rows[0] == ["section", "subsection", "label", "value", "units", "notes"]
    keys = {tuple(r[:3]) for r in rows[1:]}
    assert ("Market Pricing", "Holdings", "pricing_mode") in keys
    assert ("Rebalancing", "Optimization", "trade_optimizer_mode") in keys
    assert all(r[5] for r in rows[1:]), "every default row carries a note for the editor"
    assert "section,subsection,label,value,units,notes" in payload["csv_content"].splitlines()[0]
