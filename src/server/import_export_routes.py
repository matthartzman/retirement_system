"""WP9.3: the CSV import/export API, a thin layer over ``csv_exchange``.

POST /api/import/preview   what an import would change (nothing written)
POST /api/import/commit    the same import, written in one transaction
GET  /api/export/<dataset> one dataset as CSV text
GET  /api/export/plan-set  the whole plan set as a zip

Import body (JSON): ``{"dataset": "<name>", "csv_text": "..."}`` for one dataset, or
``{"dataset": "plan-set", "zip_base64": "..."}`` (or a raw ``application/zip`` body) for a plan-set zip.
"""
from __future__ import annotations

import base64
import binascii

try:
    from .. import csv_exchange as _cx
    from ..active_plan import _PLAN_LOCK, active_plan_store
    from .app_core import _require, _runtime_config, app, jsonify, make_response, request
except ImportError:  # direct file loading fallback
    from src import csv_exchange as _cx  # type: ignore
    from src.active_plan import _PLAN_LOCK, active_plan_store  # type: ignore
    from src.server.app_core import _require, _runtime_config, app, jsonify, make_response, request  # type: ignore

PLAN_SET = "plan-set"


def _err(message: str, status: int = 400, **extra):
    return jsonify({"success": False, "error": message, **extra}), status


def _read_request():
    """``(dataset, csv text | zip bytes)`` from the request, or an error response."""
    ctype = str(request.headers.get("Content-Type", "")).split(";")[0].strip().lower()
    if ctype in ("application/zip", "application/octet-stream"):
        return PLAN_SET, bytes(request.get_data()), None
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, None, _err("JSON object body required")
    dataset = str(body.get("dataset") or "").strip()
    if body.get("zip_base64") is not None:
        try:
            return dataset or PLAN_SET, base64.b64decode(str(body["zip_base64"]), validate=True), None
        except (binascii.Error, ValueError):
            return None, None, _err("zip_base64 is not valid base64")
    text = body.get("csv_text", body.get("csv"))
    if not dataset or not isinstance(text, str):
        return None, None, _err("dataset and csv_text (or zip_base64) are required")
    return dataset, text, None


def _run(dry_run: bool):
    dataset, payload, bad = _read_request()
    if bad:
        return bad
    try:
        if dataset == PLAN_SET or isinstance(payload, bytes):
            with _PLAN_LOCK, active_plan_store() as store:
                result = _cx.import_plan_set(store, payload, dry_run=dry_run)
            return jsonify({"success": True, "committed": not dry_run and result["committed"] is not None, **result})
        parsed = _cx.parse(payload, dataset)
        with _PLAN_LOCK, active_plan_store() as store:
            preview = _cx.preview(store, parsed)
            committed = None if dry_run else _cx.commit(store, parsed)
        return jsonify({"success": True, "committed": committed is not None, "preview": preview, "result": committed})
    except _cx.ImportRejected as exc:
        return _err(str(exc), 422, issues=[i.as_dict() for i in exc.issues])
    except KeyError as exc:
        return _err(f"unknown dataset: {exc.args[0] if exc.args else dataset}", 404)


@app.route("/api/import/preview", methods=["POST"])
def import_preview_route():
    denied = _require("read_config")
    if denied:
        return denied
    return _run(True)


@app.route("/api/import/commit", methods=["POST"])
def import_commit_route():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return _err("CSV writes are disabled", 403)
    return _run(False)


@app.route("/api/export/plan-set", methods=["GET"])
def export_plan_set_route():
    denied = _require("read_config")
    if denied:
        return denied
    with active_plan_store(readonly=True) as store:
        data = _cx.export_plan_set(store)
    resp = make_response(data)
    resp.headers["Content-Type"] = "application/zip"
    resp.headers["Content-Disposition"] = 'attachment; filename="plan-set.zip"'
    return resp


@app.route("/api/export/<dataset>", methods=["GET"])
def export_dataset_route(dataset: str):
    denied = _require("read_config")
    if denied:
        return denied
    try:
        with active_plan_store(readonly=True) as store:
            text = _cx.export_dataset(store, dataset)
    except KeyError:
        return _err(f"unknown or import-only dataset: {dataset}", 404)
    resp = make_response(text)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{dataset}.csv"'
    return resp
