from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _dashboard_js() -> str:
    return (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")


def _plan_routes() -> str:
    return (ROOT / "src" / "server" / "plan_routes.py").read_text(encoding="utf-8")


def _workbook_routes() -> str:
    return (ROOT / "src" / "server" / "workbook_routes.py").read_text(encoding="utf-8")


def test_first_run_to_build_journey_has_preflight_and_results_review():
    js = _dashboard_js()
    routes = _workbook_routes()

    assert "function firstRunChecklistHtml" in js
    assert "Review and build" in js
    assert "async function runBuild" in js
    assert "saveWorkingCopy" in js
    assert "/api/build/preflight" in js
    assert "/api/build/start" in js
    assert "renderBuildImpactAfterBuild" in js
    assert '@app.route("/api/build/preflight", methods=["GET"])' in routes
    assert '@app.route("/api/build/start", methods=["POST"])' in routes


def test_transactions_to_spending_sync_journey_invalidates_spending_model():
    js = _dashboard_js()
    routes = _plan_routes()

    assert "id:'ytd_transactions'" in js
    assert "id:'spending_dashboard'" in js
    assert "Sync Actual Rate" in js
    assert "async function saveYtdTransactions" in js
    assert "/api/ytd/transactions/bulk" in js
    assert "spendingData=null" in js
    assert "function renderSpendingDashboardOrLoad" in js
    assert "/api/spending/model" in js
    assert '@app.route("/api/ytd/transactions/bulk", methods=["PUT"])' in routes
    assert '@app.route("/api/spending/model", methods=["GET"])' in routes


def test_holdings_to_allocation_journey_refreshes_preview_contract():
    js = _dashboard_js()
    routes = _plan_routes() + "\n" + _workbook_routes()

    assert "id:'holdings'" in js
    assert "id:'allocation_assets'" in js
    assert "holdingsChanged" in js
    assert "allocationPreviewFingerprint" in js
    assert "holdingsLen" in js
    assert "requestAllocationPreview" in js
    assert "/api/allocation-preview" in js
    assert "renderAllocationRecommendation" in js
    assert '@app.route("/api/holdings", methods=["POST"])' in routes
    assert '@app.route("/api/allocation-preview", methods=["POST"])' in routes


def test_snapshot_restore_journey_uses_local_database_copy_routes():
    js = _dashboard_js()
    routes = _plan_routes()

    assert "async function savePlanAs" in js
    assert "async function loadSavedPlan" in js
    assert "/api/plan/save-as" in js
    assert "/api/plan/load-file" in js
    assert "/api/plan/exit-snapshot" in js
    assert "show_save_dialog" in js
    assert "show_open_dialog" in js
    assert '@app.route("/api/plan/save-as", methods=["POST"])' in routes
    assert '@app.route("/api/plan/load-file", methods=["POST"])' in routes
    assert '@app.route("/api/plan/exit-snapshot", methods=["POST"])' in routes
    assert "wal_checkpoint(FULL)" in routes
