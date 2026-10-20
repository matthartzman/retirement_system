"""WI-019 / ARC-003: swallowed derived-result steps (config_contract_warnings) reach the build result."""
from src import active_plan
from src.server_services import build_service


def test_build_warnings_parsed_deduped_from_stdout():
    out = "Running projection...\nBuild warning: PlanResult contract build failed: boom\nBuild warning: PlanResult contract build failed: boom\nQC: 3 / 3 PASS\n"
    assert build_service.build_warnings_from_stdout(out) == ("PlanResult contract build failed: boom",)
    assert build_service.build_warnings_from_stdout("QC: 3 / 3 PASS") == ()


def test_interpret_build_result_carries_warnings(monkeypatch):
    monkeypatch.setattr(active_plan, "read_build_results", lambda build_id=None: {"summary": {"build_id": "b1", "qc_result": "QC: 3 / 3 PASS"}})
    outcome = build_service.interpret_build_result(
        returncode=0,
        stdout="Build warning: ReportSpec contract build failed: x\nQC: 3 / 3 PASS\n",
        build_id="b1",
    )
    assert outcome.success
    assert outcome.warnings == ("ReportSpec contract build failed: x",)
