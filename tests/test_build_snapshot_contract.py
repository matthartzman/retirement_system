import hashlib

from src.build_snapshot import SNAPSHOT_SCHEMA, make_build_snapshot

import pytest

pytestmark = pytest.mark.contract


def test_build_snapshot_records_artifact_fingerprints_and_summary(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    workbook = output / "retirement_plan.xlsx"
    dashboard = output / "retirement_dashboard.html"
    pricing = output / "pricing_diagnostics.json"
    system_config = tmp_path / "system_config.csv"

    workbook.write_bytes(b"workbook-bytes")
    dashboard.write_text("<html>dashboard</html>", encoding="utf-8")
    pricing.write_text('{"failed_symbols": []}', encoding="utf-8")
    system_config.write_text("Section,Subsection,Label,Value\n", encoding="utf-8")

    snapshot = make_build_snapshot(
        output,
        build_id="build-123",
        plan_input_fingerprint={"sha256": "plan-fingerprint", "files": [{"file": "input/client_data.csv"}]},
        summary={"qc_result": "QC: pass", "terminal_nw": 42},
        explorer={"schema": "m"},
        system_config_path=system_config,
        pricing_diagnostics_path=pricing,
    )

    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["build_id"] == "build-123"
    assert snapshot["input_fingerprint"]["sha256"] == "plan-fingerprint"
    assert snapshot["summary"]["terminal_nw"] == 42
    assert snapshot["artifact_count"] == 5

    records = {item["file"]: item for item in snapshot["artifacts"]}
    assert records["retirement_plan.xlsx"]["sha256"] == hashlib.sha256(b"workbook-bytes").hexdigest()
    assert records["retirement_dashboard.html"]["exists"] is True
    assert snapshot["pricing_diagnostics"]["exists"] is True
    assert snapshot["system_config"]["exists"] is True
    assert records["build_results.summary_json"]["exists"] is True
    assert records["build_results.explorer_json"]["sha256"]
