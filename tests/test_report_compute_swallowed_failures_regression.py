"""WI-007 / ARC-003: swallowed derived-result failures must be logged and surfaced."""
from __future__ import annotations

import logging
from unittest import mock

from src import report_compute
from src.data_io import build_plan_from_json
from tests.synthetic_plans import base_plan


def _cfg():
    return build_plan_from_json(base_plan(), "")


def test_attach_plan_result_failure_is_logged_and_surfaced(caplog):
    with mock.patch.object(report_compute, "attach_plan_result", side_effect=RuntimeError("boom-plan-result")):
        with caplog.at_level(logging.ERROR, logger="retirement_system.report"):
            art = report_compute.run_projection_artifacts(_cfg(), run_mc=False, enforce_release_gate=False)

    records = [r for r in caplog.records if r.name == "retirement_system.report" and r.exc_info]
    assert any("PlanResult contract build failed" in r.getMessage() for r in records)
    assert any("boom-plan-result" in str(r.exc_info[1]) for r in records)

    expected = "PlanResult contract build failed: boom-plan-result"
    assert expected in art.config["config_contract_warnings"]
    assert expected in art.config_contract_warnings


def test_no_warnings_on_clean_run():
    art = report_compute.run_projection_artifacts(_cfg(), run_mc=False, enforce_release_gate=False)
    assert art.config_contract_warnings == []
