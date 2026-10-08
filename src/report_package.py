from __future__ import annotations

"""Canonical advisor report package contract.

The workbook and HTML dashboard remain files; the Results Explorer model, KPI summary and build
snapshot are stored with the build's results (``build_results`` in the plan file). The package
manifest, stored there too, gives the UI and future renderers one versioned description of the
current report bundle and the contracts each artifact satisfies.
"""

from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from .active_plan import build_part_record
from .build_snapshot import SNAPSHOT_SCHEMA, sha256_file
from .results_model import RESULTS_MODEL_SCHEMA
from .version import VERSION

REPORT_PACKAGE_SCHEMA = "report_package_v1"


def _artifact_record(path: Path, *, role: str, schema: str = "", required: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {
        "role": role,
        "file": path.name,
        "path": str(path),
        "schema": schema,
        "required": bool(required),
        "exists": path.exists() and path.is_file(),
    }
    if record["exists"]:
        stat = path.stat()
        record.update(
            {
                "bytes": stat.st_size,
                "sha256": sha256_file(path),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
            }
        )
    return record


def _part_artifact(part: str, doc: dict[str, Any], *, role: str, schema: str) -> dict[str, Any]:
    return {"role": role, "schema": schema, "required": True, **build_part_record(part, doc)}


def _artifact_map(output_dir: Path, summary: dict[str, Any], results: dict[str, Any], snapshot: dict[str, Any], pricing: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _artifact_record(output_dir / "retirement_plan.xlsx", role="workbook", schema="xlsx_workbook"),
        _artifact_record(output_dir / "retirement_dashboard.html", role="html_dashboard", schema="offline_dashboard"),
        _part_artifact("explorer", results, role="results_model", schema=RESULTS_MODEL_SCHEMA),
        _part_artifact("summary", summary, role="summary", schema="plan_summary_v1"),
        _part_artifact("snapshot", snapshot, role="build_snapshot", schema=SNAPSHOT_SCHEMA),
        {**_part_artifact("pricing", pricing, role="pricing_diagnostics", schema="pricing_diagnostics_v1"), "required": False},
    ]


def build_report_package(
    output_dir: str | Path,
    *,
    build_id: str = "",
    summary: dict[str, Any],
    results_model: dict[str, Any],
    build_snapshot: dict[str, Any],
    pricing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    summary_payload, results_payload, snapshot_payload = summary, results_model, build_snapshot
    artifacts = _artifact_map(out, summary_payload, results_payload, snapshot_payload, pricing or {})

    required_missing = [a["role"] for a in artifacts if a.get("required") and not a.get("exists")]
    result_sheets = results_payload.get("sheets") if isinstance(results_payload.get("sheets"), list) else []
    result_categories = results_payload.get("categories") if isinstance(results_payload.get("categories"), list) else []

    return {
        "success": not required_missing,
        "schema": REPORT_PACKAGE_SCHEMA,
        "version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "saved_sqlite_snapshot",
        "build_id": build_id or str(summary_payload.get("build_id") or snapshot_payload.get("build_id") or ""),
        "contracts": {
            "results_model": str(results_payload.get("schema") or RESULTS_MODEL_SCHEMA),
            "build_snapshot": str(snapshot_payload.get("schema") or SNAPSHOT_SCHEMA),
            "summary": "plan_summary_v1",
        },
        "renderer_roles": {
            "workbook": "excel_renderer",
            "html_dashboard": "offline_dashboard_renderer",
            "results_model": "canonical_semantic_report_model",
        },
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "required_missing": required_missing,
        "summary": summary_payload,
        "components": {
            "results_model": {
                "schema": str(results_payload.get("schema") or RESULTS_MODEL_SCHEMA),
                "sheet_count": len(result_sheets),
                "category_count": len(result_categories),
                "source": str(results_payload.get("source") or "semantic_results_model"),
            },
            "build_snapshot": {
                "schema": str(snapshot_payload.get("schema") or ""),
                "build_id": str(snapshot_payload.get("build_id") or ""),
                "artifact_count": int(snapshot_payload.get("artifact_count") or 0),
                "database_snapshot_exists": bool((snapshot_payload.get("sqlite_database_snapshot") or {}).get("exists")),
            },
        },
    }
