from pathlib import Path

from src.build_snapshot import SNAPSHOT_SCHEMA
import src.server.workbook_routes as workbook_routes


def _meta(path, *, exists=True, mtime=100.0):
    return {
        "exists": exists,
        "path": str(path),
        "bytes": 10 if exists else 0,
        "mtime": mtime if exists else 0,
        "modified_at": "2026-06-26 05:00:00" if exists else "",
    }


def test_build_preflight_reports_current_artifacts(monkeypatch, tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    output.mkdir(parents=True)
    (output / "plan_summary.json").write_text('{"qc_result": "QC: pass"}', encoding="utf-8")
    (output / "pricing_diagnostics.json").write_text('{"pricing_mode": "LIVE"}', encoding="utf-8")
    (output / "build_snapshot.json").write_text(
        '{"schema": "' + SNAPSHOT_SCHEMA + '", "artifacts": [{"file": "retirement_plan.xlsx", "sha256": "abc"}]}',
        encoding="utf-8",
    )

    def fake_file_meta(path):
        p = Path(path)
        if p == db:
            return _meta(p, mtime=100)
        return _meta(p, mtime=120)

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    monkeypatch.setattr(workbook_routes, "_file_meta", fake_file_meta)
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert payload["schema"] == "build_preflight_v1"
    assert payload["source"] == "sqlite_snapshot"
    assert payload["current"] is True
    assert payload["readiness"] == "current"
    assert payload["blockers"] == []
    assert payload["snapshot_schema"] == SNAPSHOT_SCHEMA
    assert payload["output_fingerprints"][0]["file"] == "retirement_plan.xlsx"
    assert payload["pricing_mode"] == "LIVE"


def test_build_preflight_warns_for_missing_outputs(monkeypatch, tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "local_state" / "retirement_system_v10.db"

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    monkeypatch.setattr(workbook_routes, "_file_meta", lambda path: _meta(Path(path), exists=Path(path) == db, mtime=100))
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert payload["current"] is False
    assert payload["readiness"] == "warning"
    assert "No complete current output package exists yet." in payload["warnings"]
    assert "Build outputs before relying on Reports or Retirement Plan Workbook." in payload["recommendations"]
    assert "A successful build will create build_snapshot.json for output fingerprints." in payload["recommendations"]


def test_build_preflight_blocks_missing_required_and_schema_errors(monkeypatch, tmp_path):
    output = tmp_path / "output"
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    rows = [
        {
            "section": "Household",
            "subsection": "",
            "label": "client_name",
            "value": "",
            "schema": {"required": "TRUE"},
            "is_header": False,
            "is_comment": False,
        }
    ]

    def fake_file_meta(path):
        p = Path(path)
        if p == db:
            return _meta(p, mtime=100)
        return _meta(p, mtime=120)

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    monkeypatch.setattr(workbook_routes, "_file_meta", fake_file_meta)
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": rows})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: ["bad row"])

    payload = workbook_routes._build_preflight_payload()

    assert payload["readiness"] == "blocked"
    assert payload["missing_required_count"] == 1
    assert payload["schema_error_count"] == 1
    assert any("required Plan Data" in item for item in payload["blockers"])
    assert any("schema validation" in item for item in payload["blockers"])
