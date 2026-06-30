"""Planning Workbench case contract helpers.

The Planning Workbench is intentionally transport- and framework-neutral.  The
browser owns the local planning_case_v1 store, while Python keeps a small shared
contract validator for documentation, tests, and future import/export support.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal

PlanningCaseSource = Literal["strategy", "scenario", "stress", "manual"]
PlanningCaseRunType = Literal["quick_compare", "full_build", "stress_suite"]

VALID_SOURCES = {"strategy", "scenario", "stress", "manual"}
VALID_RUN_TYPES = {"quick_compare", "full_build", "stress_suite"}


@dataclass(frozen=True)
class PlanningCaseV1:
    """Named browser-local planning case.

    A case describes proposed overrides and comparison context.  It must not be
    applied to the saved plan without an explicit source-page edit/save/build.
    """

    case_id: str
    name: str
    base_snapshot_id: str
    source: PlanningCaseSource
    overrides: list[dict[str, Any]] = field(default_factory=list)
    run_type: PlanningCaseRunType = "quick_compare"
    result_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    schema: str = "planning_case_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_source(value: Any) -> PlanningCaseSource:
    source = str(value or "manual").strip().lower()
    return source if source in VALID_SOURCES else "manual"  # type: ignore[return-value]


def normalize_run_type(value: Any) -> PlanningCaseRunType:
    run_type = str(value or "quick_compare").strip().lower()
    return run_type if run_type in VALID_RUN_TYPES else "quick_compare"  # type: ignore[return-value]


def validate_planning_case_v1(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate the public planning_case_v1 shape without persistence side effects."""

    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload must be an object"]
    if payload.get("schema", "planning_case_v1") != "planning_case_v1":
        errors.append("schema must be planning_case_v1")
    for key in ["case_id", "name", "base_snapshot_id"]:
        if not str(payload.get(key, "")).strip():
            errors.append(f"{key} is required")
    if normalize_source(payload.get("source")) != payload.get("source"):
        errors.append("source must be one of strategy, scenario, stress, manual")
    if normalize_run_type(payload.get("run_type")) != payload.get("run_type", "quick_compare"):
        errors.append("run_type must be one of quick_compare, full_build, stress_suite")
    if not isinstance(payload.get("overrides", []), list):
        errors.append("overrides must be a list")
    if not isinstance(payload.get("result_summary", {}), dict):
        errors.append("result_summary must be an object")
    return not errors, errors


def contract_example() -> dict[str, Any]:
    return PlanningCaseV1(
        case_id="case_example",
        name="Retire later bridge",
        base_snapshot_id="latest_saved_baseline",
        source="scenario",
        overrides=[
            {
                "sourceStep": "scenarios",
                "sourceTitle": "Scenario Change Sets",
                "field": "retirement_year",
                "before": "2027",
                "after": "2029",
                "rationale": "Test bridge years before adopting the assumption.",
            }
        ],
        run_type="quick_compare",
        result_summary={
            "success_probability": 0.86,
            "terminal_nw": 2400000,
            "lifetime_tax": 720000,
            "roth_conversion_total": 180000,
        },
    ).to_dict()
