import json
from pathlib import Path

from src.report_package import REPORT_PACKAGE_FILENAME, REPORT_PACKAGE_SCHEMA, build_report_package, read_report_package, write_report_package
from src.results_model import RESULTS_MODEL_FILENAME, RESULTS_MODEL_SCHEMA
from src.server import app
import src.server.workbook_routes as workbook_routes
from src.server_services import build_service, report_service


HEADERS = {"X-User-Role": "admin"}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_bytes(path: Path, payload: bytes = b"artifact") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _seed_report_output(output: Path) -> None:
    _write_bytes(output / "retirement_plan.xlsx")
    _write_bytes(output / "retirement_plan.pdf")
    _write_bytes(output / "retirement_dashboard.html")
    _write_json(output / RESULTS_MODEL_FILENAME, {"schema": RESULTS_MODEL_SCHEMA, "source": "test", "sheets": [{"name": "Summary"}], "categories": [{"label": "Summary"}]})
    _write_json(output / "plan_summary.json", {"build_id": "phase4", "terminal_nw": 123})
    _write_json(output / "build_snapshot.json", {"schema": "build_snapshot_v1", "build_id": "phase4", "artifact_count": 3, "sqlite_database_snapshot": {"exists": True}})


def test_report_package_builds_versioned_advisor_contract(tmp_path):
    output = tmp_path / "output"
    _seed_report_output(output)

    package = write_report_package(output)
    saved = read_report_package(output)

    assert package["schema"] == REPORT_PACKAGE_SCHEMA
    assert saved and saved["schema"] == REPORT_PACKAGE_SCHEMA
    assert package["success"] is True
    assert package["build_id"] == "phase4"
    assert package["contracts"]["results_model"] == RESULTS_MODEL_SCHEMA
    assert package["contracts"]["build_snapshot"] == "build_snapshot_v1"
    assert package["components"]["results_model"]["sheet_count"] == 1
    assert {artifact["role"] for artifact in package["artifacts"]} >= {"workbook", "results_model", "build_snapshot"}
    assert all("sha256" in artifact for artifact in package["artifacts"] if artifact["exists"])


def test_report_package_surfaces_missing_required_artifacts(tmp_path):
    package = build_report_package(tmp_path / "output")

    assert package["schema"] == REPORT_PACKAGE_SCHEMA
    assert package["success"] is False
    assert "workbook" in package["required_missing"]
    assert "results_model" in package["required_missing"]


def test_report_package_service_and_route_return_current_package(monkeypatch, tmp_path):
    output = tmp_path / "output"
    _seed_report_output(output)
    write_report_package(output)

    payload, status = report_service.report_package_payload(output)
    assert status == 200
    assert payload["schema"] == REPORT_PACKAGE_SCHEMA

    monkeypatch.setattr(workbook_routes, "_workspace_output", lambda: output)
    client = app.test_client()
    response = client.get("/api/report-package", headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json()["schema"] == REPORT_PACKAGE_SCHEMA


def test_build_preflight_exposes_report_package_artifact(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    db = tmp_path / "local_state" / "plan.db"
    _write_bytes(db)
    _seed_report_output(output)
    write_report_package(output)

    payload = build_service.build_preflight_payload(
        output_dir=output,
        db_path=db,
        snapshot_filename="build_snapshot.json",
        read_build_snapshot=lambda path: json.loads(Path(path).read_text(encoding="utf-8")),
        csv_rows_payload=lambda: {"rows": []},
    )

    assert payload["schema"] == "build_preflight_v1"
    assert payload["artifacts"]["report_package"]["exists"] is True


def test_workbook_builder_writes_report_package_after_build_snapshot():
    text = Path("src/reporting/workbook_builder.py").read_text(encoding="utf-8")

    assert "write_build_snapshot(" in text
    assert "write_report_package(" in text
    assert text.index("write_build_snapshot(") < text.index("write_report_package(")
