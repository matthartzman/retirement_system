from pathlib import Path

from src.active_plan import PLAN_DB_ENV, ensure_plan_file, plan_state, read_build_results, write_build_results
from src.report_package import REPORT_PACKAGE_SCHEMA, build_report_package
from src.results_model import RESULTS_MODEL_SCHEMA
from src.server import app
from src.server_services import build_service, report_service


HEADERS = {"X-User-Role": "admin"}

SUMMARY = {"build_id": "phase4", "terminal_nw": 123}
EXPLORER = {"schema": RESULTS_MODEL_SCHEMA, "source": "test", "sheets": [{"name": "Summary"}], "categories": [{"label": "Summary"}]}
SNAPSHOT = {"schema": "build_snapshot_v1", "build_id": "phase4", "artifact_count": 3, "sqlite_database_snapshot": {"exists": True}}


def _write_bytes(path: Path, payload: bytes = b"artifact") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _seed_report_output(output: Path) -> None:
    _write_bytes(output / "retirement_plan.xlsx")
    _write_bytes(output / "retirement_dashboard.html")


def _package(output: Path) -> dict:
    return build_report_package(output, build_id="phase4", summary=SUMMARY, results_model=EXPLORER, build_snapshot=SNAPSHOT)


def _store(tmp_path, monkeypatch, package) -> Path:
    plan = tmp_path / "plan.rpx"
    monkeypatch.setenv(PLAN_DB_ENV, str(plan))
    ensure_plan_file(plan)
    write_build_results("phase4", path=plan, plan_state=plan_state(plan), summary=SUMMARY, explorer=EXPLORER,
                        snapshot=SNAPSHOT, package=package)
    return plan


def test_report_package_builds_versioned_advisor_contract(tmp_path):
    output = tmp_path / "output"
    _seed_report_output(output)

    package = _package(output)

    assert package["schema"] == REPORT_PACKAGE_SCHEMA
    assert package["success"] is True
    assert package["build_id"] == "phase4"
    assert package["contracts"]["results_model"] == RESULTS_MODEL_SCHEMA
    assert package["contracts"]["build_snapshot"] == "build_snapshot_v1"
    assert package["components"]["results_model"]["sheet_count"] == 1
    assert {artifact["role"] for artifact in package["artifacts"]} >= {"workbook", "results_model", "build_snapshot"}
    assert all("sha256" in artifact for artifact in package["artifacts"] if artifact["exists"])


def test_report_package_surfaces_missing_required_artifacts(tmp_path):
    package = build_report_package(tmp_path / "output", summary={}, results_model={}, build_snapshot={})

    assert package["schema"] == REPORT_PACKAGE_SCHEMA
    assert package["success"] is False
    assert "workbook" in package["required_missing"]
    assert "results_model" in package["required_missing"]


def test_report_package_service_and_route_return_current_package(monkeypatch, tmp_path):
    output = tmp_path / "output"
    _seed_report_output(output)
    _store(tmp_path, monkeypatch, _package(output))

    payload, status = report_service.report_package_payload()
    assert status == 200
    assert payload["schema"] == REPORT_PACKAGE_SCHEMA

    response = app.test_client().get("/api/report-package", headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json()["schema"] == REPORT_PACKAGE_SCHEMA


def test_report_package_service_404s_before_any_build(monkeypatch, tmp_path):
    monkeypatch.setenv(PLAN_DB_ENV, str(tmp_path / "plan.rpx"))

    payload, status = report_service.report_package_payload()

    assert status == 404
    assert payload["schema"] == REPORT_PACKAGE_SCHEMA


def test_build_preflight_exposes_report_package_artifact(monkeypatch, tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    _seed_report_output(output)
    plan = _store(tmp_path, monkeypatch, _package(output))

    payload = build_service.build_preflight_payload(
        output_dir=output,
        db_path=plan,
        csv_rows_payload=lambda: {"rows": []},
    )

    assert payload["schema"] == "build_preflight_v1"
    assert payload["artifacts"]["report_package"]["exists"] is True
    assert read_build_results(path=plan)["package"]["build_id"] == "phase4"


def test_workbook_builder_stores_report_package_after_build_snapshot():
    text = Path("src/reporting/workbook_builder.py").read_text(encoding="utf-8")

    assert "make_build_snapshot(" in text
    assert "build_report_package(" in text
    assert "write_build_results(" in text
    assert text.index("make_build_snapshot(") < text.index("build_report_package(") < text.index("write_build_results(")
