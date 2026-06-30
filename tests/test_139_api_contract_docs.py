from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "documentation" / "API_CONTRACTS.md"


def test_api_contract_doc_covers_p1_canonical_endpoints():
    text = DOC.read_text(encoding="utf-8")

    assert "# API Contracts" in text
    assert "build_preflight_v1" in text
    assert "build_snapshot_v1" in text
    assert "results_model_v10" in text
    assert "report_package_v1" in text
    for endpoint in [
        "/api/config/rows",
        "/api/spending/model",
        "/api/ytd/transactions",
        "/api/holdings",
        "/api/build/preflight",
        "/api/build/start",
        "/api/detailed-results",
        "/api/report-package",
        "/api/plan/exit-snapshot",
    ]:
        assert f"## `{endpoint}`" in text


def test_api_contract_doc_matches_current_route_names():
    text = DOC.read_text(encoding="utf-8")
    routes = "\n".join(
        [
            (ROOT / "src/server/plan_routes.py").read_text(encoding="utf-8"),
            (ROOT / "src/server/workbook_routes.py").read_text(encoding="utf-8"),
        ]
    )

    for endpoint in [
        "/api/config/rows",
        "/api/spending/model",
        "/api/ytd/transactions",
        "/api/holdings",
        "/api/build/preflight",
        "/api/build/start",
        "/api/detailed-results",
        "/api/report-package",
        "/api/plan/exit-snapshot",
    ]:
        assert endpoint in text
        assert endpoint in routes
