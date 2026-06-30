from pathlib import Path

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
    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")

    assert "Preview &amp; import CSV" in js
    assert "/api/ytd/transactions/preview" in js
    assert "ytdImportPreviewMessage" in js
    assert "Duplicate candidates" in js
    assert "Unmapped categories" in js
    assert "Preview &amp; replace CSV" in js
    assert "/api/holdings/preview" in js
    assert "holdingsImportPreviewMessage" in js
    assert "use Save Changes to write them to disk" in js
    assert "holdingsText=text" in js
