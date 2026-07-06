from pathlib import Path

from src.api_contracts import CONTRACT_BY_KEY, validate_payload

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_batch_assumption_overlay_is_loaded_and_preview_first():
    html = read("frontend/index.html")
    js = read("frontend/js/dashboard_batch_assumption_edit.js")
    assert "dashboard_batch_assumption_edit.js" in html
    assert "batch_assumption_edit_v1" in js
    assert "Preview batch" in js
    assert "Apply preview to staged edits" in js
    assert "Save Changes to persist" in js
    assert "downloadPreviewCsv" in js


def test_batch_tools_cover_all_assumptions_and_system_configuration():
    js = read("frontend/js/dashboard_batch_assumption_edit.js")
    assert "batch-assumption-edit" in js
    assert "system-config-batch-edit" in js
    assert "rowsForStep('all_assumptions')" in js
    assert "/api/admin/system-config" in js
    assert "Enter a field filter before previewing a broad batch edit" in js
    assert "system_config.csv immediately" in js


def test_batch_tools_have_styles_and_output_asset_copy():
    css = read("frontend/css/dashboard.css")
    out_js = read("output/js/dashboard_batch_assumption_edit.js")
    assert "batch-edit-panel" in css
    assert "batch-preview-table" in css
    assert "batch_assumption_edit_v1" in out_js


def test_system_config_api_contracts_are_registered():
    keys = set(CONTRACT_BY_KEY)
    assert "GET /api/admin/system-config" in keys
    assert "POST /api/admin/system-config" in keys
    ok = validate_payload(
        "GET",
        "/api/admin/system-config",
        {"success": True, "path": "system_config.csv", "rows": []},
    )
    assert ok == []


def test_docs_mark_batch_assumption_editing_complete():
    spec = read("documentation/CURRENT_SYSTEM_DESIGN_SPEC.md")
    api = read("documentation/API_CONTRACTS.md")
    changelog = read("documentation/GOLDEN_MASTER_CHANGELOG.md")
    assert "Add batch edit tools for assumptions. Completed." in spec
    assert "Preview-first batch editors" in spec
    assert "`/api/admin/system-config`" in api
    assert "Roadmap continuation: batch assumption editing" in changelog
