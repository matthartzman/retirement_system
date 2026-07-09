from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

try:
    from ..schema_registry import validate_rows as _schema_validate_rows
except Exception:  # pragma: no cover - direct execution fallback
    from src.schema_registry import validate_rows as _schema_validate_rows

try:
    from ..report_package import REPORT_PACKAGE_FILENAME
except Exception:  # pragma: no cover - direct execution fallback
    from src.report_package import REPORT_PACKAGE_FILENAME


def file_meta(path: Path) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    meta: dict[str, Any] = {"exists": bool(exists), "path": str(path)}
    if exists:
        try:
            st = path.stat()
            meta.update({"bytes": st.st_size, "mtime": st.st_mtime, "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))})
        except Exception:
            pass
    return meta


def read_summary_payload(output_dir: Path, fallback_output_dir: Path | None = None) -> tuple[dict[str, Any], int]:
    p = output_dir / "plan_summary.json"
    if not p.exists() and fallback_output_dir is not None:
        fallback = fallback_output_dir / "plan_summary.json"
        if fallback.exists():
            p = fallback
    if not p.exists():
        return {"success": False, "error": "No prior build summary found", "kpi": {}}, 404
    try:
        summary = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "error": str(exc), "kpi": {}}, 500
    return {"success": True, "kpi": summary, "summary": summary}, 200


def build_preflight_payload(
    *,
    output_dir: Path,
    db_path: Path,
    snapshot_filename: str,
    read_build_snapshot: Callable[[Path], dict[str, Any] | None],
    csv_rows_payload: Callable[[], dict[str, Any]],
    file_meta_func: Callable[[Path], dict[str, Any]] | None = None,
    validate_rows_func: Callable[[list[dict[str, Any]]], list[str]] | None = None,
) -> dict[str, Any]:
    meta = file_meta_func or file_meta
    artifacts = {
        "workbook": meta(output_dir / "retirement_plan.xlsx"),
        "pdf": meta(output_dir / "retirement_plan.pdf"),
        "html_dashboard": meta(output_dir / "retirement_dashboard.html"),
        "results_model": meta(output_dir / "results_explorer_model.json"),
        "summary": meta(output_dir / "plan_summary.json"),
        "build_snapshot": meta(output_dir / snapshot_filename),
        "report_package": meta(output_dir / REPORT_PACKAGE_FILENAME),
        "pricing_diagnostics": meta(output_dir / "pricing_diagnostics.json"),
    }
    db_meta = meta(db_path)
    summary: dict[str, Any] = {}
    warnings: list[str] = []
    blockers: list[str] = []
    recommendations: list[str] = []

    essential = ["workbook", "html_dashboard", "results_model", "summary", "build_snapshot"]
    missing_outputs = [name for name in essential if not artifacts[name].get("exists")]
    if missing_outputs:
        warnings.append("No complete current output package exists yet.")
        recommendations.append("Build outputs before relying on Reports or Retirement Plan Workbook.")

    stale_outputs: list[str] = []
    db_mtime = float(db_meta.get("mtime") or 0)
    if db_mtime:
        for name in essential:
            meta = artifacts[name]
            if meta.get("exists") and float(meta.get("mtime") or 0) < db_mtime:
                stale_outputs.append(name)
        if stale_outputs:
            # Not a real anomaly: the DB is touched by nearly every user edit,
            # so it is almost always newer than the last build's outputs until
            # the next manual rebuild. Surface this as a recommendation (the
            # "Next" informational channel), not a scary warning.
            recommendations.append("Saved plan data is newer than one or more report outputs. Rebuild reports from the saved local database snapshot.")

    if artifacts["summary"].get("exists"):
        try:
            summary = json.loads((output_dir / "plan_summary.json").read_text(encoding="utf-8"))
        except Exception as exc:
            warnings.append(f"Prior build summary could not be read: {exc}")
    else:
        recommendations.append("A successful build will create plan_summary.json for KPI status.")

    snapshot = read_build_snapshot(output_dir / snapshot_filename)
    if artifacts["build_snapshot"].get("exists") and not snapshot:
        warnings.append("Build snapshot could not be parsed.")
    elif not artifacts["build_snapshot"].get("exists"):
        recommendations.append("A successful build will create build_snapshot.json for output fingerprints.")

    if not artifacts["report_package"].get("exists"):
        recommendations.append("A successful build will create report_package.json as the canonical advisor package manifest.")

    rows: list[dict[str, Any]] = []
    schema_errors: list[str] = []
    missing_required: list[dict[str, str]] = []
    try:
        payload = csv_rows_payload()
        rows = list(payload.get("rows") or [])
        editable = [r for r in rows if not r.get("is_header") and not r.get("is_comment") and r.get("section") and r.get("label")]
        for row in editable:
            spec = row.get("schema") or {}
            if str(spec.get("required", "")).upper() == "TRUE" and not str(row.get("value") or "").strip():
                missing_required.append({
                    "section": str(row.get("section") or ""),
                    "subsection": str(row.get("subsection") or ""),
                    "label": str(row.get("label") or ""),
                })
        schema_errors = (validate_rows_func or _schema_validate_rows)(editable)
    except Exception as exc:
        warnings.append(f"Plan validation preflight could not read all config rows: {exc}")

    if missing_required:
        blockers.append(f"{len(missing_required)} required Plan Data value(s) are blank.")
        recommendations.append("Complete required fields before building advisor-ready reports.")
    if schema_errors:
        blockers.append(f"{len(schema_errors)} schema validation issue(s) detected.")
        recommendations.append("Review validation issues before final report delivery.")

    pricing_status = "unknown"
    pricing_mode = "unknown"
    pricing_diag_path = output_dir / "pricing_diagnostics.json"
    if pricing_diag_path.exists():
        try:
            diag = json.loads(pricing_diag_path.read_text(encoding="utf-8"))
            pricing_mode = str(diag.get("pricing_mode") or "unknown")
            # failure_symbols/failures count individual provider ATTEMPTS, which
            # is noisy: a symbol commonly fails on one provider (e.g. a
            # placeholder/expired FMP key) and still resolves a good price from
            # the next provider or from cache — normal graceful degradation, not
            # a problem. unpriced_symbols is the terminal "no live quote, no
            # cache, no cost-basis fallback" state — the only case where the
            # symbol genuinely has no number to show, which is what should drive
            # an actionable warning.
            failed = diag.get("unpriced_symbols")
            if failed is None:
                failed = diag.get("failure_symbols") or diag.get("failures") or []
            # fallback_warning_symbols reflects symbols that actually resolved to a
            # degraded source (cache/stale/cost-basis); fallback_symbols is just the
            # configured cost-basis pool available for fallback, which is not the
            # same thing and overstates how many symbols actually needed it.
            fallback = diag.get("fallback_warning_symbols") or diag.get("fallback_symbols") or []
            pricing_status = "fallback" if fallback else ("warning" if failed else "ok")
            if failed and diag.get("connectivity_unavailable"):
                # Every configured pricing provider hit a network-level failure
                # (DNS/timeout/connection refused/etc.) — every symbol will show
                # up as unpriced whenever this build runs without internet
                # access, so a per-symbol count is noise, not a signal. Report
                # one general, non-alarming notice instead.
                recommendations.append("Live pricing providers could not be reached (no network connectivity detected); cached or fallback prices were used for all symbols.")
            elif failed:
                warnings.append(f"Market pricing diagnostics: {len(failed)} symbol(s) have no usable price (no live quote, cache, or fallback available).")
            if fallback:
                # pricing_source_note describes the OVERALL/primary pricing mode
                # (e.g. "Live provider quotes were used...") and is often fine
                # even when a handful of unrelated symbols fell back to cache or
                # cost basis. Using that overall note here as a "warning" is
                # misleading, so report the specific fallback symbol count as an
                # informational recommendation instead of a warning.
                recommendations.append(f"Market pricing used fallback values for {len(fallback)} symbol(s): {', '.join(fallback[:10])}{'...' if len(fallback) > 10 else ''}.")
        except Exception:
            warnings.append("Pricing diagnostics could not be parsed.")
    else:
        recommendations.append("Refresh or build once to create pricing diagnostics.")

    current = bool(not missing_outputs and not stale_outputs)
    if blockers:
        readiness = "blocked"
    elif warnings:
        readiness = "warning"
    elif current:
        readiness = "current"
    else:
        readiness = "ready"

    return {
        "success": True,
        "schema": "build_preflight_v1",
        "source": "sqlite_snapshot",
        "current": current,
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "recommendations": list(dict.fromkeys(recommendations)),
        "missing_required": missing_required[:50],
        "missing_required_count": len(missing_required),
        "schema_errors": schema_errors[:50],
        "schema_error_count": len(schema_errors),
        "row_count": len(rows),
        "db": db_meta,
        "artifacts": artifacts,
        "summary": summary,
        "snapshot": snapshot or {},
        "snapshot_schema": (snapshot or {}).get("schema", ""),
        "output_fingerprints": (snapshot or {}).get("artifacts", []),
        "pricing_status": pricing_status,
        "pricing_mode": pricing_mode,
    }
