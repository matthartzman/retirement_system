from pathlib import Path

from _decomp_dashboard import dashboard_js_text

ROOT = Path(__file__).resolve().parents[1]


def test_import_preview_routes_are_documented_and_side_effect_named():
    plan_routes = (ROOT / "src" / "server" / "plan_routes.py").read_text(encoding="utf-8")
    workbook_routes = (ROOT / "src" / "server" / "workbook_routes.py").read_text(encoding="utf-8")
    docs = (ROOT / "documentation" / "API_CONTRACTS.md").read_text(encoding="utf-8")

    assert '@app.route("/api/ytd/transactions/preview", methods=["POST"])' in plan_routes
    assert "preview_ytd_transactions_import" in plan_routes
    assert '@app.route("/api/holdings/preview", methods=["POST"])' in workbook_routes
    assert "preview_holdings_import" in workbook_routes
    assert "import_preview_v1" in docs
    assert "will_write" in docs


def test_import_preview_ui_confirms_transactions_and_stages_holdings():
    # dashboard_decomp_holdings.js (Wave 6.4) now owns the holdings-import
    # strings; dashboard_js_text() reads dashboard.js plus every extracted
    # dashboard_decomp_*.js module so this assertion targets the assembled
    # behavior regardless of which file a given string now lives in.
    js = dashboard_js_text()

    assert "Preview &amp; import CSV" in js
    assert "/api/ytd/transactions/preview" in js
    assert "ytdImportPreviewMessage" in js
    assert "Duplicate candidates" in js
    assert "Unmapped categories" in js
    assert "Preview &amp; replace CSV" in js
    assert "/api/holdings/preview" in js
    assert "holdingsImportPreviewMessage" in js
    assert "use Save Changes to write them to disk" in js
    assert 'window.holdingsText = text' in js
