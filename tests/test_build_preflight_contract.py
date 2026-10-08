from pathlib import Path

from src.active_plan import PLAN_DB_ENV, ensure_plan_file, plan_state, write_build_results
from src.build_snapshot import SNAPSHOT_SCHEMA
import src.server.workbook_routes as workbook_routes


def _plan_with_build(tmp_path, monkeypatch, *, state=None, **parts):
    """The active plan file with one build's results; ``state`` defaults to the plan's current state."""
    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    ensure_plan_file(plan)
    write_build_results("b1", path=plan, plan_state=plan_state(plan) if state is None else state, **parts)
    return plan


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
    (output / "pricing_diagnostics.json").write_text('{"pricing_mode": "LIVE"}', encoding="utf-8")
    _plan_with_build(
        tmp_path, monkeypatch,
        summary={"qc_result": "QC: pass"}, explorer={"schema": "m"}, package={"schema": "p"},
        snapshot={"schema": SNAPSHOT_SCHEMA, "artifacts": [{"file": "retirement_plan.xlsx", "sha256": "abc"}]},
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
    monkeypatch.setenv(PLAN_DB_ENV, str(tmp_path / "no_plan.rpx"))

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    monkeypatch.setattr(workbook_routes, "_file_meta", lambda path: _meta(Path(path), exists=False, mtime=100))
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert payload["current"] is False
    assert payload["readiness"] == "warning"
    assert "No complete current output package exists yet." in payload["warnings"]
    assert "Build outputs before relying on Reports or Retirement Plan Workbook." in payload["recommendations"]
    assert "A successful build will store a build snapshot for output fingerprints." in payload["recommendations"]


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


def test_build_preflight_surfaces_format_override_warning(monkeypatch, tmp_path):
    """A workbook build that fails to apply saved column-width/alignment
    overrides (workbook_builder.py's apply_overrides() try/except) used to
    only print to console -- invisible to anyone not watching a terminal.
    the stored summary's format_override_warning field is the one place that
    failure is now recorded, and this preflight panel is the UI surface a
    user actually sees, so the wiring between the two must not regress."""
    output = tmp_path / "output"
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    output.mkdir(parents=True)
    _plan_with_build(tmp_path, monkeypatch, summary={
        "qc_result": "QC: pass",
        "format_override_warning": "Workbook format overrides (column widths/alignment) were not applied: boom",
    })

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    def fake_file_meta(path):
        p = Path(path)
        if p == db:
            return _meta(p, mtime=100)
        return _meta(p, mtime=120)

    monkeypatch.setattr(workbook_routes, "_file_meta", fake_file_meta)
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert any("were not applied" in item for item in payload["warnings"])


def test_build_preflight_omits_format_override_warning_when_absent(monkeypatch, tmp_path):
    """The common case: no override failure, so the field is null/missing and
    must not produce a phantom warning."""
    output = tmp_path / "output"
    db = tmp_path / "local_state" / "retirement_system_v10.db"
    output.mkdir(parents=True)
    _plan_with_build(tmp_path, monkeypatch, summary={"qc_result": "QC: pass", "format_override_warning": None})

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_sqlite_db", lambda: db)
    def fake_file_meta(path):
        p = Path(path)
        if p == db:
            return _meta(p, mtime=100)
        return _meta(p, mtime=120)

    monkeypatch.setattr(workbook_routes, "_file_meta", fake_file_meta)
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert not any("were not applied" in item for item in payload["warnings"])


def test_build_preflight_marks_outputs_stale_when_the_plan_changed_since_the_build(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir(parents=True)
    _plan_with_build(tmp_path, monkeypatch, state="an-older-plan-state",
                     summary={"qc_result": "QC: pass"}, explorer={"schema": "m"},
                     snapshot={"schema": SNAPSHOT_SCHEMA})
    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    monkeypatch.setattr(workbook_routes, "_file_meta", lambda path: _meta(Path(path), mtime=120))
    monkeypatch.setattr(workbook_routes, "_csv_rows_payload", lambda: {"rows": []})
    monkeypatch.setattr(workbook_routes, "_schema_validate_rows", lambda rows: [])

    payload = workbook_routes._build_preflight_payload()

    assert payload["current"] is False
    assert any("newer than one or more report outputs" in r for r in payload["recommendations"])
