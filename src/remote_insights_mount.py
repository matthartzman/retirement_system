"""Mount Financial Insight under ``/insights`` inside a remote worker (multi-user server).

``PrefixMount`` has the shape of ``financial_trends_reporter.listeners.ListenerApp`` (``handle_http``). Paths under
``/insights`` go to the Financial Insight app with the prefix stripped; everything else goes to the planner app
untouched, so the planner route table, allow-list and manifest do not change.

The planner's worker-token and Host/Origin checks live inside the planner app, so a request for FI never meets
them. The mount therefore applies them itself, before dispatching: worker token (``/api/ping`` included), loopback
Host, the planner's Origin/Referer rule, then on the way out the path scrub and the generic error body.

Design: ``documentation/future/multi-user-insights-design.md`` (4.3).
"""
from __future__ import annotations

import json
from typing import Any

from . import remote_mode
from .http_runtime import host_guard
from .http_runtime.wsgi_facade import HeaderMap, Response
from .security import constant_time_token_ok

INSIGHTS_ENV = "RETIREMENT_SYSTEM_INSIGHTS"
PREFIX = "/insights"
_WORKER_HOST = "127.0.0.1"


def insights_enabled() -> bool:
    """True when the worker was started with the Financial Insight flag (environment only, never a request)."""
    import os  # noqa: PLC0415

    return (os.environ.get(INSIGHTS_ENV) or "").strip() == "1"


def _json(payload: dict, status: int) -> Response:
    return Response(json.dumps(payload), status=status, content_type="application/json")


class PrefixMount:
    def __init__(self, planner_app: Any, insights_app: Any, prefix: str = PREFIX) -> None:
        self.planner_app = planner_app
        self.insights_app = insights_app
        self.prefix = prefix.rstrip("/")

    def _is_insights(self, path: str) -> bool:
        return path == self.prefix or path.startswith(self.prefix + "/")

    def handle_http(self, method: str, target: str, headers: dict | None = None, body: bytes = b"",
                    remote_addr: str = "127.0.0.1"):
        path, sep, query = target.partition("?")
        if not self._is_insights(path):
            return self.planner_app.handle_http(method, target, headers, body, remote_addr)
        hdrs = HeaderMap(headers or {})
        denied = self._gate(hdrs)
        if denied is not None:
            return denied
        if path == self.prefix:
            return Response(b"", status=302, headers={"Location": self.prefix + "/" + (sep + query if sep else "")})
        inner = path[len(self.prefix):] + (sep + query if sep else "")
        try:
            response = self.insights_app.handle_http(method, inner, headers, body, remote_addr)
        except Exception:  # noqa: BLE001 - never echo exception text to a remote user
            import logging  # noqa: PLC0415

            logging.getLogger("retirement_system.insights_mount").exception("insights mount: unhandled error")
            return _json({"success": False, "error": remote_mode.GENERIC_ERROR}, 500)
        return self._clean(response)

    @staticmethod
    def _gate(hdrs: HeaderMap) -> Response | None:
        auth = str(hdrs.get("Authorization", "") or "").strip()
        candidate = auth[7:].strip() if auth.lower().startswith("bearer ") else str(hdrs.get(remote_mode.TOKEN_HEADER, "") or "")
        if not constant_time_token_ok(candidate.strip(), remote_mode.worker_token()):
            return _json({"success": False, "error": "Access token required"}, 401)
        if not host_guard.host_allowed(str(hdrs.get("Host", "") or ""), _WORKER_HOST):
            return _json({"success": False, "error": "Host not allowed"}, 403)
        for name in ("Origin", "Referer"):
            value = str(hdrs.get(name, "") or "")
            if value and not host_guard.origin_netloc_allowed(value, _WORKER_HOST):
                return _json({"success": False, "error": "Cross-origin requests are not allowed"}, 403)
        return None

    @staticmethod
    def _clean(response: Response) -> Response:
        """No server path in a JSON body, and no exception text in a server error."""
        if response.mimetype != "application/json":
            return response
        try:
            data = response.get_json(silent=True)
        except Exception:  # noqa: BLE001
            return response
        if data is None:
            return response
        scrubbed = remote_mode.scrub(data)
        if response.status_code >= 500 and isinstance(scrubbed, dict) and "error" in scrubbed:
            scrubbed = {**scrubbed, "error": remote_mode.GENERIC_ERROR}
        if scrubbed == data:
            return response
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(json.dumps(scrubbed, ensure_ascii=False), status=response.status_code, headers=headers,
                        content_type="application/json")
