from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..schema_registry import validate_rows as _schema_validate_rows

from .. import active_plan

from . import build_job_service


_QC_RE = re.compile(r"QC:\s*(\d+)\s*/\s*(\d+)\s+PASS")


@dataclass(frozen=True)
class BuildResultSummary:
    """The single interpretation of "did this build succeed" -- computed once
    here instead of independently (and identically) inline in both the sync
    build route and the async build-progress job."""

    success: bool
    qc_result: str
    stale_summary: bool
    summary: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


def interpret_build_result(
    *,
    returncode: int,
    stdout: str,
    build_id: str,
    stderr: str = "",
) -> BuildResultSummary:
    """Read the finished build's KPI summary from ``build_results`` and decide
    success/staleness/error. The one place both the sync route and the async job
    call instead of each re-implementing an identical inline sequence (A2, system
    review 2026-07-21). The row is looked up by ``build_id``, so an older build's
    summary is never taken for this one; ``stale_summary`` says the plan file holds
    results only from a different build."""
    row = active_plan.read_build_results(build_id or None)
    summary: dict[str, Any] = dict((row or {}).get("summary") or {})
    stale_summary = bool(summary) and not build_job_service.summary_matches_build(summary, build_id)
    if build_id and row is None:
        latest = active_plan.read_build_results()
        stale_summary = bool(latest and latest.get("summary"))
    qc_match = _QC_RE.search(stdout or "")
    success = returncode == 0 and (bool(qc_match) or summary.get("qc_result")) and bool(summary) and not stale_summary
    qc_result = summary.get("qc_result") or (qc_match.group(0) if qc_match else "Unknown")
    error_message = build_job_service.build_error_message(returncode, summary, stale_summary, stdout, stderr)
    return BuildResultSummary(
        success=bool(success),
        qc_result=qc_result,
        stale_summary=stale_summary,
        summary=summary,
        error_message=error_message,
    )


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


def read_summary_payload() -> tuple[dict[str, Any], int]:
    row = active_plan.read_build_results()
    summary = (row or {}).get("summary")
    if not summary:
        return {"success": False, "error": "No prior build summary found", "kpi": {}}, 404
    return {"success": True, "kpi": summary, "summary": summary}, 200


def _part_meta(row: dict[str, Any] | None, part: str) -> dict[str, Any]:
    return {"exists": bool(row and row.get(part)), "stored_in": "plan_file"}


def build_preflight_payload(
    *,
    output_dir: Path,
    db_path: Path,
    csv_rows_payload: Callable[[], dict[str, Any]],
    file_meta_func: Callable[[Path], dict[str, Any]] | None = None,
    validate_rows_func: Callable[[list[dict[str, Any]]], list[str]] | None = None,
) -> dict[str, Any]:
    meta = file_meta_func or file_meta
    row = active_plan.read_build_results(path=db_path)
    artifacts = {
        "workbook": meta(output_dir / "retirement_plan.xlsx"),
        "html_dashboard": meta(output_dir / "retirement_dashboard.html"),
        "results_model": _part_meta(row, "explorer"),
        "summary": _part_meta(row, "summary"),
        "build_snapshot": _part_meta(row, "snapshot"),
        "report_package": _part_meta(row, "package"),
        "pricing_diagnostics": _part_meta(row, "pricing"),
    }
    db_meta = meta(db_path)
    summary: dict[str, Any] = dict((row or {}).get("summary") or {})
    warnings: list[str] = []
    blockers: list[str] = []
    recommendations: list[str] = []

    essential = ["workbook", "html_dashboard", "results_model", "summary", "build_snapshot"]
    missing_outputs = [name for name in essential if not artifacts[name].get("exists")]
    if missing_outputs:
        warnings.append("No complete current output package exists yet.")
        recommendations.append("Build outputs before relying on Reports or Retirement Plan Workbook.")

    # The outputs are stale when the plan (rows and datasets) is not the one the last build read.
    stale_outputs: list[str] = []
    built_state = str((row or {}).get("plan_state") or "")
    if built_state:
        try:
            current_state = active_plan.plan_state(db_path)
        except Exception:
            current_state = ""
        if current_state and current_state != built_state:
            stale_outputs = [name for name in essential if artifacts[name].get("exists")]
            # Not a real anomaly: the plan is edited far more often than it is built, so it is
            # usually newer than the last build's outputs until the next manual rebuild. Surface
            # this as a recommendation (the "Next" informational channel), not a scary warning.
            recommendations.append("Saved plan data is newer than one or more report outputs. Rebuild reports from the saved local database snapshot.")

    if summary:
        format_warning = summary.get("format_override_warning")
        if format_warning:
            warnings.append(str(format_warning))
    else:
        recommendations.append("A successful build will store its KPI summary for KPI status.")

    snapshot = (row or {}).get("snapshot") or {}
    if not artifacts["build_snapshot"].get("exists"):
        recommendations.append("A successful build will store a build snapshot for output fingerprints.")

    if not artifacts["report_package"].get("exists"):
        recommendations.append("A successful build will store the report package as the canonical advisor package manifest.")

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

        # item 2.6: IRMAA plan years 1-2 have no projected AGI row yet to
        # look back at, so they fall back to retirement-year AGI unless the
        # household's actual historical MAGI is entered. That fallback is a
        # known approximation (peak working-year MAGI is often very
        # different from retirement-year AGI), so nudge -- but never block
        # a build, since older saved plans predate these optional inputs
        # and must still build with the old behavior.
        irmaa_hist = {
            r.get("label"): str(r.get("value") or "").strip()
            for r in editable
            if r.get("section") == "Model Constants" and r.get("subsection") == "IRMAA"
            and r.get("label") in ("irmaa_actual_magi_2yr_prior", "irmaa_actual_magi_1yr_prior")
        }
        if not irmaa_hist.get("irmaa_actual_magi_2yr_prior") or not irmaa_hist.get("irmaa_actual_magi_1yr_prior"):
            recommendations.append(
                "IRMAA guidance for plan years 1-2 is using retirement-year AGI as a stand-in "
                "because actual historical MAGI is blank (Model Constants > IRMAA > "
                "irmaa_actual_magi_2yr_prior / irmaa_actual_magi_1yr_prior). Enter the "
                "household's actual MAGI from the two tax years before plan start for more "
                "accurate early-year IRMAA guidance."
            )
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
    diag = (row or {}).get("pricing") or {}
    if diag:
        try:
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
        recommendations.append("Build once to create pricing diagnostics.")

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
