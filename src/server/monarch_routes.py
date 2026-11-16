"""Monarch data for remote users (multi-user Phase 4; desktop mode can use both too).

POST /api/monarch/upload   ``{"kind": "transactions"|"balances", "filename": ..., "content_base64": ...,
                             "dry_run": false}`` -> counts, masked account names, errors

Base64 inside JSON for the same reason as ``/api/plan/upload``: the CSRF gate accepts only JSON or text bodies.
The work is in ``src/monarch_upload.py``.

The optional MCP connector (``src/monarch_connector.py``, off unless the worker has
``RETIREMENT_SYSTEM_MONARCH_CONNECTOR=1``):

GET  /api/monarch/connector             -> {available, connected, connected_at, last_sync, sign_in_pending, reason?}
POST /api/monarch/connector/start       -> {authorize_url, redirect_uri, expires_in}
POST /api/monarch/connector/complete    {"callback_url": "<the address the browser showed>"} -> status
POST /api/monarch/connector/sync        {"dry_run": false, "full": false} -> counts per kind
POST /api/monarch/connector/disconnect  -> status + revoked

Design: ``documentation/future/multi-user-server-monarch-secrets-design.md`` sections 1 and 6.
"""
from __future__ import annotations

from .app_core import _audit, _require, _runtime_config, app, jsonify, request
from .plan_routes import _ytd_input_root

try:
    from .. import monarch_connector as _connector
    from .. import monarch_upload as _upload
    from ..secrets_store import SecretStoreUnavailable
except ImportError:  # direct file loading fallback
    from src import monarch_connector as _connector  # type: ignore
    from src import monarch_upload as _upload  # type: ignore
    from src.secrets_store import SecretStoreUnavailable  # type: ignore


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


def _connector_call(fn, event: str | None = None, details=None):
    try:
        payload = fn()
    except _connector.ConnectorError as exc:
        return jsonify({"success": False, "error": str(exc)}), exc.status
    except SecretStoreUnavailable as exc:
        return jsonify({"success": False, "error": _upload.mask_names(exc)}), 403
    ok = payload.get("success", True)
    if event and ok:
        _audit(event, details(payload) if details else {})
    return jsonify({"success": True, **payload} if ok else payload), (200 if ok else 400)


@app.route("/api/monarch/connector", methods=["GET"])
def monarch_connector_status():
    denied = _require("read_config")
    if denied:
        return denied
    return jsonify({"success": True, **_connector.status()})


@app.route("/api/monarch/connector/start", methods=["POST"])
def monarch_connector_start():
    denied = _require("write_config")
    if denied:
        return denied
    return _connector_call(_connector.start)


@app.route("/api/monarch/connector/complete", methods=["POST"])
def monarch_connector_complete():
    denied = _require("write_config")
    if denied:
        return denied
    body = request.get_json(silent=True)
    pasted = body.get("callback_url") if isinstance(body, dict) else None
    return _connector_call(lambda: _connector.complete(str(pasted or "")), "monarch_connected")


@app.route("/api/monarch/connector/sync", methods=["POST"])
def monarch_connector_sync():
    denied = _require("write_config")
    if denied:
        return denied
    if not _runtime_config().allow_csv_write:
        return jsonify({"success": False, "error": "CSV writes are disabled"}), 403
    body = request.get_json(silent=True)
    body = body if isinstance(body, dict) else {}
    return _connector_call(
        lambda: _connector.sync(_ytd_input_root().parent, dry_run=bool(body.get("dry_run")), full=bool(body.get("full"))),
        "monarch_synced",
        lambda p: {"dry_run": p.get("dry_run"), "transactions": (p.get("transactions") or {}).get("rows_read"),
                   "balance_rows": (p.get("balances") or {}).get("rows"), "accounts": p.get("accounts_seen")})


@app.route("/api/monarch/connector/disconnect", methods=["POST"])
def monarch_connector_disconnect():
    denied = _require("write_config")
    if denied:
        return denied
    return _connector_call(_connector.disconnect, "monarch_disconnected", lambda p: {"revoked": p.get("revoked")})
