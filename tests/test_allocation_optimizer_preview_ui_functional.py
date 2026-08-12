from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text


def test_allocation_recommendation_ui_has_optimizer_preview_columns():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8") + "\n" + dashboard_js_text()
    html += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert "Computed Optimizer Target %" in html
    assert "Active Target Used %" in html
    assert "inactive in optimizer mode" in html
    assert "requestAllocationPreview" in html
    assert "allocation-preview" in html


def test_routes_expose_allocation_preview_endpoint():
    source = (ROOT / "src" / "server" / "plan_routes.py").read_text(encoding="utf-8")
    service = (ROOT / "src" / "server_services" / "config_service.py").read_text(encoding="utf-8")
    assert "allocation-preview" in source
    assert "allocation_preview_payload" in source
    assert "compute_optimal_allocation" in service
