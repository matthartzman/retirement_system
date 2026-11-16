"""Monarch's own CSV exports uploaded from the browser (multi-user Phase 4; desktop mode can use it too).

POST /api/monarch/upload   ``{"kind": "transactions"|"balances", "filename": ..., "content_base64": ...,
                             "dry_run": false}`` -> counts, masked account names, errors

Base64 inside JSON for the same reason as ``/api/plan/upload``: the CSRF gate accepts only JSON or text bodies.
The work is in ``src/monarch_upload.py``; design in
``documentation/future/multi-user-server-monarch-secrets-design.md`` section 1.
"""
from __future__ import annotations

from .app_core import _audit, _require, _runtime_config, app, jsonify, request
from .plan_routes import _ytd_input_root

try:
    from .. import monarch_upload as _upload
except ImportError:  # direct file loading fallback
    from src import monarch_upload as _upload  # type: ignore


@app.route("/api/monarch/upload", methods=["POST"])
def monarch_upload():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    payload, status = _upload.handle_upload(_ytd_input_root().parent, request.get_json(silent=True))
    if payload.get("success") and not payload.get("dry_run"):
        _audit("monarch_uploaded", {"kind": payload.get("kind"), "rows": payload.get("rows_read", payload.get("rows")),
                                    "accounts": payload.get("accounts")})
    return jsonify(payload), status
