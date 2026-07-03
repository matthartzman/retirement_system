from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .app_core import *
from ..http_runtime.wsgi_facade import Response
try:
    from ..schema_registry import load_schema as _load_schema_registry, validate_value as _schema_validate_value, validate_rows as _schema_validate_rows
except Exception:
    from src.schema_registry import load_schema as _load_schema_registry, validate_value as _schema_validate_value, validate_rows as _schema_validate_rows

try:
    from ..build_snapshot import SNAPSHOT_FILENAME, read_build_snapshot
except Exception:
    from src.build_snapshot import SNAPSHOT_FILENAME, read_build_snapshot

try:
    from ..server_services import build_job_service, build_service, holdings_service, plan_data_file_service, plan_forms_service, report_service, spending_service
except Exception:
    from src.server_services import build_job_service, build_service, holdings_service, plan_data_file_service, plan_forms_service, report_service, spending_service


# Build-job orchestration is owned by server_services.build_job_service.
# This route module keeps thin HTTP adapter calls and desktop push registration.
# Plan Data load/save materialization ensures current UI rows:
# _ensure_user_ui_plan_data_rows()
_BUILD_JOBS = build_job_service.BuildJobRegistry()

_CURRENT_BUILD_OUTPUT_FILES = [
    "plan_summary.json",
    "retirement_plan.xlsx",
    "retirement_plan.pdf",
    "retirement_dashboard.html",
    RESULTS_MODEL_FILENAME if "RESULTS_MODEL_FILENAME" in globals() else "results_explorer_model.json",
    SNAPSHOT_FILENAME,
    "report_package.json",
    "forecast_package.json",
]


def register_progress_push(callback: Any) -> None:
    """Register a desktop progress callback without exposing route internals."""
    _BUILD_JOBS.register_push_callback(callback)


def _clear_current_build_outputs(output_dir: Path) -> None:
    build_job_service.clear_current_build_outputs(output_dir, _CURRENT_BUILD_OUTPUT_FILES)


def _file_meta(path: Path) -> dict[str, Any]:
    return build_service.file_meta(path)


def _build_preflight_payload() -> dict[str, Any]:
    return build_service.build_preflight_payload(
        output_dir=_workspace_output(),
        db_path=_sqlite_db(),
        snapshot_filename=SNAPSHOT_FILENAME,
        read_build_snapshot=read_build_snapshot,
        csv_rows_payload=_csv_rows_payload,
        file_meta_func=_file_meta,
        validate_rows_func=_schema_validate_rows,
    )


def _summary_matches_build(summary: dict, build_id: str) -> bool:
    return build_job_service.summary_matches_build(summary, build_id)


def _friendly_build_detail(low: str, fallback: str = "Working through the build steps...") -> str:
    return build_job_service.friendly_build_detail(low, fallback)


def _build_progress_from_line(line: str, current: int) -> tuple[int, str, str]:
    return build_job_service.build_progress_from_line(line, current)


def _build_job_snapshot(job_id: str) -> dict:
    return _BUILD_JOBS.snapshot(job_id)


def _update_build_job(job_id: str, **kwargs) -> None:
    _BUILD_JOBS.update(job_id, **kwargs)


def _extract_build_failure_message(returncode: int, stdout: str = "", stderr: str = "") -> str:
    return build_job_service.extract_build_failure_message(returncode, stdout, stderr)


def _build_error_message(returncode: int, summary: dict, stale_summary: bool, stdout: str = "", stderr: str = "") -> str:
    return build_job_service.build_error_message(returncode, summary, stale_summary, stdout, stderr)


def _plan_data_file_feature_service() -> plan_data_file_service.PlanDataFileService:
    return plan_data_file_service.PlanDataFileService(
        plan_data_file_service.PlanDataFileServiceContext(
            plan_data_files=PLAN_DATA_FILES,
            client_data_csv_file_set=CLIENT_DATA_CSV_FILE_SET,
            sqlite_db=_sqlite_db,
            normalize_plan_data_file_name=_normalize_plan_data_file_name,
            read_plan_data_file=_read_plan_data_file,
            write_plan_data_file=lambda name, content: _write_plan_data_file(name, content),
            write_blank_plan_data_file=lambda name, content: _write_plan_data_file(name, content, preserve_protected=False),
            make_blank_plan_files=_make_blank_plan_files,
            protected_client_data_status=_protected_client_data_status,
            ensure_user_ui_plan_data_rows=_ensure_user_ui_plan_data_rows,
            sync_config_backends=_sync_config_backends,
            audit=_audit,
        )
    )


def _spending_budget_feature_service() -> spending_service.SpendingService:
    return spending_service.SpendingService(
        spending_service.SpendingServiceContext(
            base_dir=BASE_DIR,
            read_plan_data_file=_read_plan_data_file,
            write_plan_data_file=lambda name, content: _write_plan_data_file(name, content),
            audit=_audit,
        )
    )


def _admin_changes_for_build_job(workspace_id: str, after_ts: float, before_ts: float) -> list[dict[str, Any]]:
    return _admin_changes_between(workspace_id, after_ts=after_ts, before_ts=before_ts)


def _run_build_progress_job(job_id: str, workspace_id: str, client_id: str, env: dict, output_dir: Path, previous_build_ts: float, build_start_ts: float, timeout_seconds: int, redact_logs: bool) -> None:
    build_job_service.run_build_progress_job(
        registry=_BUILD_JOBS,
        job_id=job_id,
        workspace_id=workspace_id,
        client_id=client_id,
        env=env,
        output_dir=output_dir,
        build_script=BUILD_SCRIPT,
        base_dir=BASE_DIR,
        previous_build_ts=previous_build_ts,
        build_start_ts=build_start_ts,
        timeout_seconds=timeout_seconds,
        redact_logs=redact_logs,
        admin_changes_between=_admin_changes_for_build_job,
        write_last_build_metadata=_write_last_build_metadata,
        redact_text=redact_text,
    )


@app.route("/api/summary", methods=["GET"])
def get_summary():
    denied = _require("view_dashboard")
    if denied:
        return denied
    fallback = BASE_DIR / "output" if _workspace_id() != "local" else None
    payload, status = build_service.read_summary_payload(_workspace_output(), fallback)
    return jsonify(payload), status




@app.route("/api/build/start", methods=["POST"])
def build_start():
    denied = _require("build_workbook")
    if denied:
        return denied
    cfg = _runtime_config()
    body = request.get_json(silent=True) or {}
    if body.get("csv_content") or body.get("plan_data_files"):
        return jsonify({
            "success": False,
            "error": "Direct CSV payloads are no longer accepted by the build endpoint. Import Plan Data CSV files in System Configuration, save the local database, then build outputs from the SQLite snapshot.",
        }), 400

    workspace_id = _workspace_id()
    client_id = _client_id()
    # Local-only package builds from the saved SQLite-backed working copy; input/ files are import/export adapters.
    output_dir = workspace_output_dir(workspace_id, BASE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV"] = str(_make_request_system_config_csv_for(workspace_id, client_id, output_dir))
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8:replace")
    env["PYTHONUNBUFFERED"] = "1"
    env["RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC"] = "1"
    job_id = uuid.uuid4().hex
    build_start_ts = time.time()
    env["RETIREMENT_SYSTEM_BUILD_ID"] = job_id
    env["RETIREMENT_SYSTEM_BUILD_STARTED_AT_TS"] = str(build_start_ts)
    _clear_current_build_outputs(output_dir)
    previous_build_ts = _read_last_build_timestamp(workspace_id)
    _BUILD_JOBS.create(job_id, created_at=build_start_ts)
    thread = threading.Thread(
        target=_run_build_progress_job,
        args=(job_id, workspace_id, client_id, env, output_dir, previous_build_ts, build_start_ts, int(cfg.max_build_seconds), bool(cfg.redact_secrets_in_logs)),
        daemon=True,
    )
    thread.start()
    _audit("build_started", {"job_id": job_id})
    return jsonify({"success": True, "job_id": job_id, "progress": 0, "phase": "Preparing build"})


@app.route("/api/build/progress/<job_id>", methods=["GET"])
def build_progress(job_id):
    denied = _require("build_workbook")
    if denied:
        return denied
    job = _build_job_snapshot(job_id)
    if not job:
        return jsonify({"success": False, "error": "build job not found"}), 404
    # Keep the in-memory table bounded.
    _BUILD_JOBS.prune_older_than(3600)
    return jsonify({"success": True, "job": job})


@app.route("/api/build/events/<job_id>", methods=["GET"])
def build_events(job_id):
    denied = _require("build_workbook")
    if denied:
        return denied

    def _stream():
        last = 0
        while True:
            job = _build_job_snapshot(job_id)
            if not job:
                yield 'event: error\ndata: {"error": "build job not found"}\n\n'
                return
            events = [e for e in job.get("events", []) if int(e.get("sequence") or 0) > last]
            for event in events:
                last = int(event.get("sequence") or last)
                yield f"event: {event.get('event_type','progress')}\ndata: {json.dumps(event, sort_keys=True)}\n\n"
            if job.get("status") in {"done", "failed"}:
                return
            yield ": heartbeat\n\n"
            time.sleep(1.0)

    return (Response or app.response_class)(_stream(), mimetype="text/event-stream")


@app.route("/api/build/events/<job_id>/snapshot", methods=["GET"])
def build_event_snapshot(job_id):
    denied = _require("build_workbook")
    if denied:
        return denied
    job = _build_job_snapshot(job_id)
    if not job:
        return jsonify({"success": False, "error": "build job not found"}), 404
    return jsonify({"success": True, "events": job.get("events", [])})


@app.route("/api/build/status", methods=["GET"])
def build_status():
    """Return whether the last build artifacts are current (db unchanged since build)."""
    try:
        payload = _build_preflight_payload()
        return jsonify(payload)
    except Exception:
        return jsonify({"success": True, "current": False})


@app.route("/api/build/preflight", methods=["GET"])
def build_preflight():
    denied = _require("build_workbook")
    if denied:
        return denied
    try:
        return jsonify(_build_preflight_payload())
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "readiness": "blocked", "blockers": [str(exc)]}), 500


@app.route("/api/build", methods=["POST"])
def build():
    denied = _require("build_workbook")
    if denied:
        return denied
    cfg = _runtime_config()
    body = request.get_json(silent=True) or {}
    if body.get("csv_content") or body.get("plan_data_files"):
        return jsonify({
            "success": False,
            "error": "Direct CSV payloads are no longer accepted by the build endpoint. Import Plan Data CSV files in System Configuration, save the local database, then build outputs from the SQLite snapshot.",
        }), 400

    # Local-only package builds from the saved SQLite-backed working copy; input/ files are import/export adapters.
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_SYSTEM_CONFIG_CSV"] = str(_request_system_config_csv())
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8:replace")
    env["PYTHONUNBUFFERED"] = "1"
    env["RETIREMENT_SYSTEM_SKIP_PLAN_DATA_ENV_SYNC"] = "1"
    start = time.time()
    build_id = uuid.uuid4().hex
    env["RETIREMENT_SYSTEM_BUILD_ID"] = build_id
    env["RETIREMENT_SYSTEM_BUILD_STARTED_AT_TS"] = str(start)
    _clear_current_build_outputs(_workspace_output())
    try:
        result = subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=str(BASE_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=cfg.max_build_seconds, env=env)
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": f"Build timed out after {cfg.max_build_seconds} seconds"}), 500
    elapsed = round(time.time() - start, 1)
    stdout = result.stdout or ""
    finished_ts = time.time()
    summary_path = _workspace_output() / "plan_summary.json"
    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
    stale_summary = bool(summary) and not _summary_matches_build(summary, build_id)
    qc_match = re.search(r"QC:\s*(\d+)\s*/\s*(\d+)\s+PASS", stdout)
    success = result.returncode == 0 and (bool(qc_match) or summary.get("qc_result")) and bool(summary) and not stale_summary
    previous_build_ts = _read_last_build_timestamp(_workspace_id())
    admin_changes = _admin_changes_between(_workspace_id(), after_ts=previous_build_ts, before_ts=start)
    if success:
        _write_last_build_metadata(_workspace_id(), {"finished_at_ts": finished_ts, "client_id": _client_id(), "elapsed_seconds": elapsed, "qc_result": summary.get("qc_result") or (qc_match.group(0) if qc_match else "Unknown")})
    _audit("build_completed", {"success": success, "returncode": result.returncode, "elapsed": elapsed})
    return jsonify({
        "success": bool(success),
        "returncode": result.returncode,
        "elapsed_seconds": elapsed,
        "qc_result": summary.get("qc_result") or (qc_match.group(0) if qc_match else "Unknown"),
        "kpi": summary,
        "output_dir": str(_workspace_output()),
        "admin_changes": admin_changes,
        "previous_build_ts": previous_build_ts,
        "build_started_at_ts": start,
        "build_finished_at_ts": finished_ts,
        "stdout": redact_text(stdout[-3000:]) if cfg.redact_secrets_in_logs else stdout[-3000:],
        "stderr": redact_text((result.stderr or "")[-1000:]) if cfg.redact_secrets_in_logs else (result.stderr or "")[-1000:],
        "error": _build_error_message(result.returncode, summary, stale_summary, stdout, result.stderr or ""),
    })


@app.route("/api/csv", methods=["GET"])
def get_csv():
    denied = _require("read_config")
    if denied:
        return denied
    if CSV_PATH.exists():
        return send_file(str(CSV_PATH), mimetype="text/csv")
    return jsonify({"error": "CSV not found"}), 404


@app.route("/api/csv", methods=["POST"])
def save_csv():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    data = request.get_json(silent=True) or {}
    if "csv_content" not in data:
        return jsonify({"success": False, "error": "No csv_content in request"}), 400
    _write_plan_data_file("client_data.csv", data["csv_content"])
    _audit("csv_saved", {"bytes": len(data["csv_content"])})
    return jsonify({"success": True})


def _download_file(name: str):
    denied = _require("download")
    if denied:
        return denied
    if not _runtime_config().allow_downloads:
        return jsonify({"success": False, "error": "Downloads are disabled"}), 403
    fallback = BASE_DIR / "output" if _workspace_id() != "local" else None
    payload, status = report_service.downloadable_artifact(name, _workspace_output(), fallback)
    if status == 200:
        _audit("file_downloaded", {"file": name})
        return send_file(str(payload["path"]), as_attachment=True, download_name=name)
    return jsonify(payload), status




@app.route("/api/detailed-results", methods=["GET"])
def get_detailed_results():
    # Detailed Results parsing lives in report_service.
    denied = _require("view_dashboard")
    if denied:
        return denied
    fallback = BASE_DIR / "output" if _workspace_id() != "local" else None
    mode = "index" if request.args.get("index") in {"1", "true", "yes"} else ("sheet" if request.args.get("sheet") is not None else "full")
    payload, status = report_service.detailed_results_payload(
        output_dir=_workspace_output(),
        fallback_output_dir=fallback,
        mode=mode,
        sheet_name=request.args.get("sheet") or "",
    )
    return jsonify(payload), status


@app.route("/api/report-package", methods=["GET"])
def get_report_package():
    denied = _require("view_dashboard")
    if denied:
        return denied
    fallback = BASE_DIR / "output" if _workspace_id() != "local" else None
    payload, status = report_service.report_package_payload(_workspace_output(), fallback)
    return jsonify(payload), status


@app.route("/api/xlsx", methods=["GET"])
def get_xlsx():
    return _download_file("retirement_plan.xlsx")


@app.route("/api/pdf", methods=["GET"])
def get_pdf():
    return _download_file("retirement_plan.pdf")


@app.route("/api/schema", methods=["GET"])
def get_schema():
    denied = _require("read_config")
    if denied:
        return denied
    if SCHEMA_PATH.exists():
        return send_file(str(SCHEMA_PATH), mimetype="text/csv")
    return jsonify({"error": "Schema not found"}), 404


@app.route("/api/history", methods=["GET"])
def get_history():
    denied = _require("view_dashboard")
    if denied:
        return denied
    payload, status = report_service.read_history_payload(_workspace_output())
    return jsonify(payload), status


@app.route("/api/history", methods=["POST"])
def append_history():
    denied = _require("build_workbook")
    if denied:
        return denied
    payload, status = report_service.append_history_payload(_workspace_output(), request.get_json(silent=True) or {})
    return jsonify(payload), status


@app.route("/api/plan-data/files", methods=["GET"])
def plan_data_files():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _plan_data_file_feature_service().files_payload()
    return jsonify(payload), status

@app.route("/api/plan-data/blank", methods=["POST"])
def start_blank_plan_data():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    payload, status = _plan_data_file_feature_service().start_blank_payload()
    return jsonify(payload), status


@app.route("/api/plan-data/<path:file_name>", methods=["GET"])
def get_plan_data_file(file_name):
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _plan_data_file_feature_service().get_file_payload(file_name)
    if status == 200:
        return payload["content"], 200, {"Content-Type": payload["content_type"]}
    return jsonify(payload), status


@app.route("/api/plan-data/<path:file_name>", methods=["POST"])
def save_plan_data_file(file_name):
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    content = body.get("csv_content")
    if content is None:
        content = request.get_data(as_text=True)
    if content is None:
        return jsonify({"success": False, "error": "No csv_content in request"}), 400
    payload, status = _plan_data_file_feature_service().save_file_payload(file_name, str(content))
    return jsonify(payload), status


@app.route("/api/holdings", methods=["GET"])
def get_holdings():
    denied = _require("read_config")
    if denied:
        return denied
    result = holdings_service.read_holdings(base_dir=BASE_DIR, workspace_id=_workspace_id(), client_id=_client_id(), db_path=_sqlite_db())
    if result.get("path"):
        return send_file(str(result["path"]), mimetype="text/csv")
    return result.get("content") or holdings_service.EMPTY_HOLDINGS_CSV, 200, {"Content-Type": result.get("content_type") or "text/csv"}


@app.route("/api/holdings", methods=["POST"])
def save_holdings():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    content = request.get_data(as_text=True)
    try:
        result = holdings_service.save_holdings(content=content, base_dir=BASE_DIR, workspace_id=_workspace_id(), client_id=_client_id(), user_id=_current_user().user_id, db_path=_sqlite_db())
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    _audit("holdings_saved", {"bytes": result.get("bytes", len(content)), "path": result.get("path")})
    return jsonify({"success": True, "path": result.get("path")})


@app.route("/api/holdings/preview", methods=["POST"])
def preview_holdings_import():
    denied = _require("read_config")
    if denied:
        return denied
    try:
        from ..import_preview import preview_holdings_import as _preview_holdings_import
    except Exception:
        from src.import_preview import preview_holdings_import as _preview_holdings_import
    body = request.get_json(silent=True) or {}
    incoming = body.get("csv_text") or body.get("csv") or body.get("content") or ""
    current = holdings_service.read_holdings(base_dir=BASE_DIR, workspace_id=_workspace_id(), client_id=_client_id(), db_path=_sqlite_db())
    current_text = current.get("content") or ""
    if current.get("path"):
        try:
            current_text = Path(str(current["path"])).read_text(encoding="utf-8-sig")
        except Exception:
            current_text = ""
    payload = _preview_holdings_import(current_text, str(incoming), project_root=BASE_DIR, mode=str(body.get("mode") or "replace"))
    return jsonify(payload), 200 if payload.get("success") else 422



@app.route("/api/liabilities", methods=["GET"])
def get_liabilities():
    denied = _require("read_config")
    if denied:
        return denied
    result = holdings_service.read_liabilities(base_dir=BASE_DIR, workspace_id=_workspace_id(), client_id=_client_id(), db_path=_sqlite_db())
    if result.get("path"):
        return send_file(str(result["path"]), mimetype="text/csv")
    return result.get("content") or holdings_service.EMPTY_LIABILITIES_CSV, 200, {"Content-Type": result.get("content_type") or "text/csv"}


@app.route("/api/liabilities", methods=["POST"])
def save_liabilities():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    content = request.get_data(as_text=True)
    try:
        result = holdings_service.save_liabilities(content=content, base_dir=BASE_DIR, workspace_id=_workspace_id(), client_id=_client_id(), user_id=_current_user().user_id, db_path=_sqlite_db())
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    _audit("liabilities_saved", {"bytes": result.get("bytes", len(content)), "path": result.get("path")})
    return jsonify({"success": True, "path": result.get("path")})


@app.route("/api/spending/budget-lines", methods=["GET"])
def get_spending_budget_lines():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _spending_budget_feature_service().budget_lines_payload()
    payload["sections"] = SPENDING_BUDGET_SECTIONS
    return jsonify(payload), status


@app.route("/api/spending/budget-lines", methods=["POST"])
def save_spending_budget_lines():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True) or {}
    return _spending_budget_save_result(lambda: _spending_budget_feature_service().save_budget_lines_payload(body))


@app.route("/api/spending/budget-lines/defaults", methods=["GET"])
def get_spending_budget_lines_defaults():
    denied = _require("read_config")
    if denied:
        return denied
    payload, status = _spending_budget_feature_service().budget_lines_defaults_payload()
    return jsonify(payload), status


@app.route("/api/plan", methods=["POST"])
def run_plan_from_json():
    denied = _require("build_workbook")
    if denied:
        return denied
    plan = request.get_json(silent=True)
    if not plan:
        return jsonify(status="error", error="No JSON body"), 400
    try:
        try:
            from ..server_forecast import forecast_from_plan_json
        except Exception:
            from src.server_forecast import forecast_from_plan_json
        result = forecast_from_plan_json(plan, run_mc=True)
        return jsonify(**result)
    except ValueError as exc:
        return jsonify(status="error", error=str(exc)), 422
    except Exception as exc:
        return jsonify(status="error", error=str(exc), trace=traceback.format_exc()), 500


@app.route("/api/validate", methods=["POST"])
def validate():
    denied = _require("read_config")
    if denied:
        return denied
    data = request.get_json(silent=True) or {}
    csv_content = data.get("csv_content", "")
    errors = []
    schema = {}
    try:
        schema = _load_schema_registry()
        reader_rows = list(csv.DictReader(io.StringIO(csv_content)))
        errors.extend(_schema_validate_rows(reader_rows))
    except Exception as exc:
        errors.append(f"Parse error: {exc}")
    return jsonify({"valid": not errors, "errors": errors, "fields_checked": len(schema)})


@app.route("/files/<path:filename>")
def serve_file(filename):
    denied = _require("download")
    if denied:
        return denied
    if not _runtime_config().allow_downloads:
        return jsonify({"success": False, "error": "Downloads are disabled"}), 403
    payload, status = report_service.local_output_file_payload(_workspace_output(), filename)
    if status == 200:
        _audit("file_downloaded", {"filename": filename})
        return send_from_directory(str(payload["root"]), filename)
    if status == 403:
        _audit("file_download_denied", {"filename": filename})
    return jsonify(payload), status


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    if _runtime_config().is_saas:
        denied = _require("manage_users")
        if denied:
            return denied
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
        return jsonify({"status": "shutting down"})
    import threading
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return jsonify({"status": "shutting down"})


# ---- Versioned SaaS/readiness APIs ----


# First-class database-backed Plan Data form APIs.  Legacy CSV endpoints are
# import/export adapters only; User/Admin forms should read and write these
# sectioned SQLite snapshots.
@app.route("/api/plan/forms", methods=["GET"])
def plan_forms_get():
    # plan_forms_service imports latest_sectioned_data and import_sectioned_plan.
    # The runtime payload keeps "backend": "sqlite" for database-backed forms.
    denied = _require("view_dashboard")
    if denied:
        return denied
    return jsonify(plan_forms_service.get_forms_payload(_sqlite_db()))


@app.route("/api/plan/forms", methods=["POST"])
def plan_forms_post():
    denied = _require("edit_config")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    sections = body.get("sections") or body.get("data") or {}
    payload, status = plan_forms_service.save_forms_payload(sections, _sqlite_db())
    if status == 200:
        _audit("plan_forms_saved", {"snapshot_id": payload.get("snapshot_id"), "section_count": len(sections) if isinstance(sections, dict) else 0})
    return jsonify(payload), status


@app.route("/api/plan/forms/<path:section_path>", methods=["PATCH"])
def plan_forms_patch(section_path):
    denied = _require("edit_config")
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    values = body.get("values") or body.get("fields") or {}
    payload, status = plan_forms_service.patch_forms_payload(section_path, values, _sqlite_db())
    if status == 200:
        _audit("plan_form_section_saved", {"snapshot_id": payload.get("snapshot_id"), "section": payload.get("section"), "subsection": payload.get("subsection")})
    return jsonify(payload), status
