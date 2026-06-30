from __future__ import annotations

"""Canonical advisor report package contract.

The workbook, PDF, HTML dashboard, Results Explorer model, and build snapshot
remain independent files.  This sidecar gives the UI and future renderers one
versioned package manifest that identifies the current report bundle and the
contracts each artifact satisfies.
"""

from datetime import datetime, UTC
import json
from pathlib import Path
from typing import Any, Iterable

from .build_snapshot import SNAPSHOT_FILENAME, SNAPSHOT_SCHEMA, sha256_file
from .results_model import RESULTS_MODEL_FILENAME, RESULTS_MODEL_SCHEMA
from .version import VERSION

REPORT_PACKAGE_FILENAME = "report_package.json"
REPORT_PACKAGE_SCHEMA = "report_package_v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _artifact_map(output_dir: Path, output_files: Iterable[tuple[str, str, str, bool]] | None = None) -> list[dict[str, Any]]:
    files = list(
        output_files
        or [
            ("workbook", "retirement_plan.xlsx", "xlsx_workbook", True),
            ("pdf", "retirement_plan.pdf", "pdf_report", False),
            ("html_dashboard", "retirement_dashboard.html", "offline_dashboard", True),
            ("results_model", RESULTS_MODEL_FILENAME, RESULTS_MODEL_SCHEMA, True),
            ("summary", "plan_summary.json", "plan_summary_v1", True),
            ("build_snapshot", SNAPSHOT_FILENAME, SNAPSHOT_SCHEMA, True),
            ("pricing_diagnostics", "pricing_diagnostics.json", "pricing_diagnostics_v1", False),
        ]
    )
    return [_artifact_record(output_dir / name, role=role, schema=schema, required=required) for role, name, schema, required in files]


def build_report_package(
    output_dir: str | Path,
    *,
    build_id: str = "",
    summary: dict[str, Any] | None = None,
    results_model: dict[str, Any] | None = None,
    build_snapshot: dict[str, Any] | None = None,
    output_files: Iterable[tuple[str, str, str, bool]] | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    summary_payload = summary if summary is not None else _read_json(out / "plan_summary.json")
    results_payload = results_model if results_model is not None else _read_json(out / RESULTS_MODEL_FILENAME)
    snapshot_payload = build_snapshot if build_snapshot is not None else _read_json(out / SNAPSHOT_FILENAME)
    artifacts = _artifact_map(out, output_files)
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
            "pdf": "pdf_renderer",
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


def write_report_package(output_dir: str | Path, **kwargs: Any) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    package = build_report_package(out, **kwargs)
    (out / REPORT_PACKAGE_FILENAME).write_text(json.dumps(package, indent=2, sort_keys=True), encoding="utf-8")
    return package


def read_report_package(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if p.is_dir():
        p = p / REPORT_PACKAGE_FILENAME
    payload = _read_json(p)
    if not payload or payload.get("schema") != REPORT_PACKAGE_SCHEMA:
        return None
    return payload
