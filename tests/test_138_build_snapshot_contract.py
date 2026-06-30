import hashlib
import json

from src.build_snapshot import SNAPSHOT_FILENAME, SNAPSHOT_SCHEMA, read_build_snapshot, write_build_snapshot


def test_build_snapshot_records_artifact_fingerprints_and_summary(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    workbook = output / "retirement_plan.xlsx"
    dashboard = output / "retirement_dashboard.html"
    summary = output / "plan_summary.json"
    pricing = output / "pricing_diagnostics.json"
    system_config = tmp_path / "system_config.csv"

    workbook.write_bytes(b"workbook-bytes")
    dashboard.write_text("<html>dashboard</html>", encoding="utf-8")
    summary.write_text('{"qc_result": "QC: pass"}', encoding="utf-8")
    pricing.write_text('{"failed_symbols": []}', encoding="utf-8")
    system_config.write_text("Section,Subsection,Label,Value\n", encoding="utf-8")

    snapshot = write_build_snapshot(
        output,
        build_id="build-123",
        plan_input_fingerprint={"sha256": "plan-fingerprint", "files": [{"file": "input/client_data.csv"}]},
        summary={"qc_result": "QC: pass", "terminal_nw": 42},
        output_files=["retirement_plan.xlsx", "retirement_dashboard.html", "plan_summary.json"],
        system_config_path=system_config,
        pricing_diagnostics_path=pricing,
    )

    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["build_id"] == "build-123"
    assert snapshot["input_fingerprint"]["sha256"] == "plan-fingerprint"
    assert snapshot["summary"]["terminal_nw"] == 42
    assert snapshot["artifact_count"] == 3

    records = {item["file"]: item for item in snapshot["artifacts"]}
    assert records["retirement_plan.xlsx"]["sha256"] == hashlib.sha256(b"workbook-bytes").hexdigest()
    assert records["retirement_dashboard.html"]["exists"] is True
    assert snapshot["pricing_diagnostics"]["exists"] is True
    assert snapshot["system_config"]["exists"] is True

    disk = json.loads((output / SNAPSHOT_FILENAME).read_text(encoding="utf-8"))
    assert disk["schema"] == SNAPSHOT_SCHEMA
    assert read_build_snapshot(output / SNAPSHOT_FILENAME)["build_id"] == "build-123"


def test_read_build_snapshot_rejects_missing_or_wrong_schema(tmp_path):
    assert read_build_snapshot(tmp_path / SNAPSHOT_FILENAME) is None

    path = tmp_path / SNAPSHOT_FILENAME
    path.write_text('{"schema": "older"}', encoding="utf-8")

    assert read_build_snapshot(path) is None
