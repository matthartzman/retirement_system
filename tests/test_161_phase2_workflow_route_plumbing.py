"""Route plumbing for the Phase 2 workflow endpoints — NOT an end-to-end test.

These tests assert that the plan, build and results routes wire together, hand
off the right payloads, and honour role headers. They deliberately do not run a
real build: `_run_build_progress_job` is replaced with a fake progress job and
`report_service.detailed_results_payload` with a hand-written dict.

Nothing here proves the real trigger path works. No test currently POSTs
/api/build/start and polls it to real completion against real sheet content —
that gap is tracked as Q2 in documentation/reports/SYSTEM_REVIEW_2026-07-18.md
(Wave 3 item 3.14). The file was previously named `..._live_workflow_journeys`,
which claimed coverage it does not provide.
"""

import sqlite3
import time
from pathlib import Path

from src.build_snapshot import sha256_file, write_build_snapshot
from src.server import app
import src.server.plan_routes as plan_routes
import src.server.workbook_routes as workbook_routes
from src.server_services import build_job_service


HEADERS = {"X-User-Role": "admin"}


def _make_db(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS marker (value TEXT)")
        conn.execute("DELETE FROM marker")
        conn.execute("INSERT INTO marker(value) VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()


def test_live_first_run_build_handoff_reaches_progress_and_results_routes(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    monkeypatch.setattr(workbook_routes, "_BUILD_JOBS", build_job_service.BuildJobRegistry())
    monkeypatch.setattr(workbook_routes, "workspace_output_dir", lambda workspace_id, base_dir: output)
    monkeypatch.setattr(workbook_routes, "_clear_current_build_outputs", lambda output_dir: None)

    def fake_progress_job(job_id, *_args, **_kwargs):
        workbook_routes._BUILD_JOBS.update(
            job_id,
            status="done",
            progress=100,
            phase="Build complete",
            detail="Live journey test completed without running the workbook builder.",
            result={"success": True, "qc_result": "QC: 1 / 1 PASS"},
        )

    monkeypatch.setattr(workbook_routes, "_run_build_progress_job", fake_progress_job)

    client = app.test_client()
    preflight = client.get("/api/build/preflight", headers=HEADERS)
    assert preflight.status_code == 200
    assert preflight.get_json()["schema"] == "build_preflight_v1"

    started = client.post("/api/build/start", json={"ui_saved_working_copy": True, "build_input_source": "sqlite_snapshot"}, headers=HEADERS)
    assert started.status_code == 200
    job_id = started.get_json()["job_id"]

    job = {}
    for _ in range(20):
        progress = client.get(f"/api/build/progress/{job_id}", headers=HEADERS)
        assert progress.status_code == 200
        job = progress.get_json()["job"]
        if job.get("status") == "done":
            break
        time.sleep(0.02)
    assert job["status"] == "done"
    assert job["progress"] == 100

    events = client.get(f"/api/build/events/{job_id}/snapshot", headers=HEADERS)
    assert events.status_code == 200
    assert any(event.get("event_type") == "completed" for event in events.get_json()["events"])

    def fake_detailed_results_payload(*, mode, sheet_name="", **_kwargs):
        if mode == "index":
            return {"success": True, "categories": [{"label": "Summary", "sheets": [{"name": "1. Summary"}]}], "sheets": []}, 200
        return {"success": True, "sheet": {"name": sheet_name or "1. Summary", "sections": []}}, 200

    monkeypatch.setattr(workbook_routes.report_service, "detailed_results_payload", fake_detailed_results_payload)
    index = client.get("/api/detailed-results?index=1", headers=HEADERS)
    assert index.status_code == 200
    assert index.get_json()["categories"][0]["sheets"][0]["name"] == "1. Summary"


def test_live_transactions_to_spending_model_journey_uses_canonical_routes(monkeypatch):
    class FakeYtdService:
        def bulk_save_transactions(self, body):
            rows = body.get("transactions") or body.get("rows") or []
            return {"success": True, "saved": len(rows), "source": "live_journey"}

    class FakeSpendingService:
        def model_payload(self, year):
            return {
                "success": True,
                "model_version": "unified_spending_taxonomy_budget_cashflow_v1",
                "year": year or 2026,
                "tracking_types": [{"tracking_type": "Expense", "groups": []}],
            }, 200

    monkeypatch.setattr(plan_routes, "_ytd_feature_service", lambda: FakeYtdService())
    monkeypatch.setattr(plan_routes, "_spending_feature_service", lambda: FakeSpendingService())

    client = app.test_client()
    saved = client.put(
        "/api/ytd/transactions/bulk",
        json={"transactions": [{"date": "2026-01-01", "merchant": "Test", "category": "Groceries", "account": "Checking", "amount": "-12.34"}]},
        headers=HEADERS,
    )
    assert saved.status_code == 200
    assert saved.get_json()["saved"] == 1

    model = client.get("/api/spending/model?year=2026", headers=HEADERS)
    assert model.status_code == 200
    payload = model.get_json()
    assert payload["model_version"] == "unified_spending_taxonomy_budget_cashflow_v1"
    assert payload["tracking_types"][0]["tracking_type"] == "Expense"


def test_live_holdings_to_allocation_preview_journey_reads_holdings_and_computes_preview():
    client = app.test_client()
    holdings = client.get("/api/holdings", headers=HEADERS)
    assert holdings.status_code == 200
    assert "account" in holdings.get_data(as_text=True).lower()

    preview = client.post(
        "/api/allocation-preview",
        json={"mode": "optimizer_recommendation", "rows": []},
        headers=HEADERS,
    )
    assert preview.status_code == 200
    payload = preview.get_json()
    assert payload["success"] is True
    assert payload["mode"] == "optimizer_recommendation"
    assert payload["selected_total_targets"]
    assert payload["optimizer_total_targets"]


def test_live_snapshot_compare_and_restore_routes_round_trip(monkeypatch, tmp_path):
    output = tmp_path / "output"
    active_db = tmp_path / "local_state" / "retirement_system_v10.db"
    snapshot_source = tmp_path / "snapshot_source.rpx"
    _make_db(active_db, "active")
    _make_db(snapshot_source, "snapshot")
    write_build_snapshot(output, build_id="journey", sqlite_db_path=snapshot_source, output_files=[])

    monkeypatch.setattr(plan_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(plan_routes, "_sqlite_db", lambda: active_db)

    client = app.test_client()
    compare = client.get("/api/plan/snapshot/compare", headers=HEADERS)
    assert compare.status_code == 200
    compare_payload = compare.get_json()
    assert compare_payload["schema"] == "plan_snapshot_compare_v1"
    assert compare_payload["database_matches"] is False

    restored = client.post("/api/plan/snapshot/restore", json={"backup_suffix": "journey"}, headers=HEADERS)
    assert restored.status_code == 200
    restore_payload = restored.get_json()
    assert restore_payload["schema"] == "plan_snapshot_restore_v1"
    assert Path(restore_payload["backup_database"]).exists()
    assert sha256_file(active_db) == sha256_file(snapshot_source)
