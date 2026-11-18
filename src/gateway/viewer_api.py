"""The guest's routes (Phase 9, design 5.6): the viewer page, its exact static files and the three record routes.

The gate in ``app.py`` lets a viewer reach only the routes in ``viewer_routes.VIEWER_ALLOWED``; this module adds no
authorization of its own beyond the selection rule, which is the boundary for records: every query is scoped by the
session's own user id (``grantee_user_id = <session user>``), the share id only picks within that set, and every miss
(unknown, malformed, revoked, expired, unpublished, someone else's, a body that does not match its row) gets the same
bytes (C5, C6). The record body is served exactly as stored; nothing in the request changes it (AC-13).
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.http_runtime.wsgi_facade import Response, request

from .share_store import ShareStore
from .store import MEMBER, GatewayStore
from .viewer_routes import NOT_AVAILABLE_BODY

PAGES_DIR = Path(__file__).resolve().parent / "pages"
VIEWER_PAGE = "viewer.html"
JS, CSS = "text/javascript; charset=utf-8", "text/css; charset=utf-8"
# The exact files the viewer page may load (like ADMIN_STATIC); nothing else is served under this path.
VIEWER_STATIC: dict[str, str] = {"viewer.js": JS, "viewer.css": CSS}
_AUDITED_MAX = 10000


def _not_available() -> Response:
    return Response(NOT_AVAILABLE_BODY, status=404, content_type="application/json")


def register_viewer_api(app, store: GatewayStore, shares: ShareStore, *, enabled: bool, clock: Callable[[], float],
                        actor: Callable, page: Callable, file_page: Callable, json_response: Callable) -> None:
    viewed: set[tuple[str, str]] = set()  # (session token, share id): one share_viewed audit event per pair

    def _viewer_id() -> int | None:
        """The session's own user id when it is a viewer session; None for members (they are never grantees)."""
        sess = request.environ.get("session")
        if not sess or sess.get("stage") != "active" or sess.get("kind") == MEMBER:
            return None
        return int(sess["user_id"])

    def _summary(row: dict) -> dict:
        return {"id": row["id"], "title": row["title"], "owner": row["owner_name"], "as_of": row["published_at"],
                "expires_at": row["expires_at"], "views": row["views"], "money_view": row["money_view"]}

    @app.route("/gateway/viewer", methods=["GET"])
    def viewer_page():
        if not enabled:
            return Response("Not found", status=404, content_type="text/plain; charset=utf-8")
        if _viewer_id() is None:
            resp = Response(b"", status=302)
            resp.headers["Location"] = "/"
            return resp
        return page(VIEWER_PAGE)

    @app.route("/gateway/viewer/static/<name>", methods=["GET"])
    def viewer_static(name: str):
        if not enabled or name not in VIEWER_STATIC:
            return Response("Not found", status=404, content_type="text/plain; charset=utf-8")
        return file_page(PAGES_DIR / name, VIEWER_STATIC[name])

    @app.route("/api/viewer/shares", methods=["GET"])
    def viewer_shares():
        vid = _viewer_id()
        if not enabled or vid is None:
            return _not_available()
        return json_response({"success": True, "shares": [_summary(r) for r in shares.viewer_list(vid, clock())]})

    @app.route("/api/viewer/shares/<share_id>", methods=["GET"])
    def viewer_share(share_id: str):
        vid = _viewer_id()
        if not enabled or vid is None:
            return _not_available()
        now = clock()
        row = shares.viewer_get(vid, share_id, now)
        if row is None:
            return _not_available()
        body = shares.read_body(row)
        if body is None:
            store.audit("share_integrity_failed", now=now, actor=actor(), target_user_id=row["owner_user_id"],
                        details=f"share {row['id']}")
            return _not_available()
        token = str(request.environ.get("session_token") or "")
        if (token, row["id"]) not in viewed:
            if len(viewed) >= _AUDITED_MAX:
                viewed.clear()
            viewed.add((token, row["id"]))
            store.audit("share_viewed", now=now, actor=actor(), target_user_id=row["owner_user_id"],
                        details=f"share {row['id']} rev {row['scope_rev']}")
        shares.log_access(row["id"], vid, now)
        return Response(body, status=200, content_type="application/json")

    @app.route("/api/viewer/shares/<share_id>/status", methods=["GET"])
    def viewer_share_status(share_id: str):
        vid = _viewer_id()
        if not enabled or vid is None:
            return _not_available()
        row = shares.viewer_get(vid, share_id, clock())
        if row is None:
            return _not_available()
        return json_response({"success": True, "available": True, "as_of": row["published_at"],
                              "scope_rev": row["scope_rev"]})
