"""The owner's share routes (Phase 9, ``multi-user-shared-view-design.md`` 5.8): members only.

A viewer never reaches these (the gate's viewer table has none of them), and with ``--shared-views`` off each one
answers 404. Every query includes ``owner_user_id = <session user>``: any other share id gets one uniform not-found,
and a ``viewer_id`` that is not a viewer the session user sponsors gets "That viewer was not found." (C5, C29). The gate
already enforces CSRF, Origin, Fetch-Metadata and body types on every write (C28). Admins have no route here into
anyone else's shares (C30).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request

from .share_store import ShareError, ShareLimit, ShareNotFound, ShareStore
from .store import MEMBER, GatewayStore

PAGES_DIR = Path(__file__).resolve().parent / "pages"
SHARING_PAGE = "sharing.html"
JS, CSS = "text/javascript; charset=utf-8", "text/css; charset=utf-8"
SHARING_STATIC: dict[str, str] = {"sharing.js": JS, "sharing.css": CSS}
NOT_FOUND_BODY = json.dumps({"success": False, "error": "Not found."})
LIMIT_CODES = ("too_soon", "busy")


def _not_found() -> Response:
    return Response(NOT_FOUND_BODY, status=404, content_type="application/json")


def register_share_routes(app, store: GatewayStore, shares: ShareStore, publisher, *, enabled: bool,  # noqa: ANN001
                          clock: Callable[[], float], actor: Callable, page: Callable, file_page: Callable,
                          json_response: Callable) -> None:

    def _owner() -> int | None:
        sess = request.environ.get("session")
        if not enabled or not sess or sess.get("stage") != "active" or sess.get("kind") != MEMBER:
            return None
        return int(sess["user_id"])

    def _body() -> dict:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else {}

    def _summary(r: dict) -> dict:
        return {"id": r["id"], "title": r["title"], "viewer": r.get("viewer_name", ""), "viewer_id": r["grantee_user_id"],
                "plan_id": r["plan_id"], "money_view": r["money_view"], "views": r["views"], "state": r["state"],
                "state_reason": r["state_reason"], "expires_at": r["expires_at"], "expired": r.get("expired", False),
                "published_at": r["published_at"], "scope_rev": r["scope_rev"], "last_viewed": r.get("last_viewed")}

    def _publish(owner: int, sid: str, *, extra: dict | None = None) -> Response:
        if publisher is None:
            return json_response({"success": True, "published": False, **(extra or {}),
                                  "message": "Publishing is not available on this server."}, 200)
        result = publisher.publish(owner, sid, actor=actor())
        if result.code == "not_found":
            return _not_found()
        payload = {"success": result.ok, "published": result.ok, "code": result.code, "message": result.message,
                   **(extra or {})}
        if result.ok or extra:
            return json_response({**payload, "success": True}, 200)
        return json_response(payload, 409 if result.code in LIMIT_CODES or result.code == "plan_not_active" else 422)

    def _error(exc: ShareError) -> Response:
        if isinstance(exc, ShareNotFound):
            msg = str(exc)
            if msg == "That viewer was not found.":
                return json_response({"success": False, "error": msg}, 404)
            return _not_found()
        if isinstance(exc, ShareLimit):
            return json_response({"success": False, "error": str(exc)}, 409)
        return json_response({"success": False, "error": str(exc)}, 400)

    @app.route("/gateway/sharing", methods=["GET"])
    def sharing_page():
        if _owner() is None:
            return Response("Not found", status=404, content_type="text/plain; charset=utf-8")
        return page(SHARING_PAGE)

    @app.route("/gateway/sharing/static/<name>", methods=["GET"])
    def sharing_static(name: str):
        if _owner() is None or name not in SHARING_STATIC:
            return Response("Not found", status=404, content_type="text/plain; charset=utf-8")
        return file_page(PAGES_DIR / name, SHARING_STATIC[name])

    @app.route("/api/share/list", methods=["GET"])
    def share_list():
        owner = _owner()
        if owner is None:
            return _not_found()
        return json_response({"success": True, "shares": [_summary(r) for r in shares.owner_list(owner, clock())],
                              "default_days": shares.settings.default_days, "max_days": shares.settings.max_days})

    @app.route("/api/share/viewers", methods=["GET"])
    def share_viewers():
        owner = _owner()
        if owner is None:
            return _not_found()
        return json_response({"success": True, "viewers": shares.sponsored_viewers(owner, clock())})

    @app.route("/api/share/create", methods=["POST"])
    def share_create():
        owner = _owner()
        if owner is None:
            return _not_found()
        b = _body()
        plan_id = b.get("expected_plan_id")
        if not isinstance(plan_id, str) or not plan_id.strip():
            return json_response({"success": False, "error": "Open the plan you want to share first."}, 400)
        try:
            sid = shares.create(owner, viewer_id=b.get("viewer_id"), title=b.get("title"),
                                money_view=b.get("money_view", "percent"),
                                views=b.get("views", ["live", "trends", "projections"]),
                                expires_in_days=b.get("expires_in_days", shares.settings.default_days),
                                plan_id=plan_id.strip(), now=clock(), actor=actor())
        except ShareError as exc:
            return _error(exc)
        return _publish(owner, sid, extra={"id": sid})

    @app.route("/api/share/<share_id>/preview", methods=["GET"])
    def share_preview(share_id: str):
        owner = _owner()
        row = shares.owner_get(owner, share_id) if owner is not None else None
        body = shares.read_body(row) if row is not None else None
        if body is None:
            return _not_found()
        return Response(body, status=200, content_type="application/json")

    @app.route("/api/share/<share_id>/publish", methods=["POST"])
    def share_publish(share_id: str):
        owner = _owner()
        if owner is None or shares.owner_get(owner, share_id) is None:
            return _not_found()
        return _publish(owner, share_id)

    @app.route("/api/share/<share_id>/scope", methods=["POST"])
    def share_scope(share_id: str):
        owner = _owner()
        if owner is None:
            return _not_found()
        b = _body()
        try:
            shares.set_scope(owner, share_id, money_view=b.get("money_view"), views=b.get("views"), now=clock(),
                             actor=actor())
        except ShareError as exc:
            return _error(exc)
        return _publish(owner, share_id, extra={"id": share_id})

    @app.route("/api/share/<share_id>/expiry", methods=["POST"])
    def share_expiry(share_id: str):
        owner = _owner()
        if owner is None:
            return _not_found()
        try:
            row = shares.set_expiry(owner, share_id, expires_in_days=_body().get("expires_in_days"), now=clock(),
                                    actor=actor())
        except ShareError as exc:
            return _error(exc)
        return json_response({"success": True, "expires_at": row["expires_at"]})

    @app.route("/api/share/<share_id>/revoke", methods=["POST"])
    def share_revoke(share_id: str):
        owner = _owner()
        if owner is None:
            return _not_found()
        try:
            shares.revoke(owner, share_id, now=clock(), actor=actor())
        except ShareError as exc:
            return _error(exc)
        return json_response({"success": True})

    @app.route("/api/share/<share_id>/enable", methods=["POST"])
    def share_enable(share_id: str):
        owner = _owner()
        if owner is None:
            return _not_found()
        try:
            shares.enable(owner, share_id, now=clock(), actor=actor())
        except ShareError as exc:
            return _error(exc)
        return _publish(owner, share_id, extra={"id": share_id})

    @app.route("/api/share/<share_id>/views", methods=["GET"])
    def share_views(share_id: str):
        owner = _owner()
        log = shares.access_log(owner, share_id, clock()) if owner is not None else None
        if log is None:
            return _not_found()
        return json_response({"success": True, "views": log})
