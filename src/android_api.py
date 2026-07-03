"""Android API bridge for the Chaquopy-embedded WebView shell.

Mirrors ``src/desktop_api.py``'s single ``request(...)`` entry point — same
local route registry, same in-process test-client dispatch — but adapted for
the Android transport instead of PyWebView's:

- No native window / file-dialog integration (Android uses
  ``ACTION_CREATE_DOCUMENT`` / ``ACTION_OPEN_DOCUMENT`` on the Kotlin side, fed
  by the plain ``<input type=file>`` flows already in the frontend and by the
  ``_binary`` payload below).
- Binary responses are returned as base64 (``_binary``) instead of written to
  a temp file and shelled out to a desktop file-open command — there is no
  desktop file manager to hand off to on Android. ``frontend/js/android_bridge.js``
  forwards this payload to Kotlin's ``saveFile()``, which writes it via
  MediaStore/Downloads.
- No build-progress push over ``evaluate_js``: the frontend's existing polling
  UX (already used to replace SSE in ``pywebview_bridge.js``) is the only
  progress mechanism, so nothing extra is needed here.
- ``configure()`` must be called once, before the first :func:`get_api` call,
  to point ``platform_runtime.workspace_root()`` at the app's private
  ``filesDir`` and to flip ``platform_runtime.is_mobile()`` on. Flipping
  ``is_mobile()`` on is what makes the Phase 0 ``BuildRunner`` pick the
  in-process (threaded) build path automatically — no Android-specific build
  code is needed here.
"""
from __future__ import annotations

import base64
import json
import os
import threading
from typing import Any


def _set_local_mode_defaults() -> None:
    defaults = {
        "RETIREMENT_SYSTEM_APP_MODE": "LOCAL",
        "RETIREMENT_SYSTEM_WORKSPACE_ID": "local",
        "RETIREMENT_SYSTEM_CLIENT_ID": "local",
        "RETIREMENT_SYSTEM_DASHBOARD_HOST": "127.0.0.1",
        "RETIREMENT_SYSTEM_DASHBOARD_PORT": "5050",
        "RETIREMENT_SYSTEM_REQUIRE_API_TOKEN": "NO",
        "RETIREMENT_SYSTEM_ALLOW_UNAUTHENTICATED_SAAS": "YES",
        "RETIREMENT_SYSTEM_FORCE_HTTPS": "NO",
        "RETIREMENT_SYSTEM_REVERSE_PROXY_ENABLED": "NO",
        "RETIREMENT_SYSTEM_NO_AUTO_OPEN": "1",
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)


_SHUTDOWN_URLS = frozenset(["/api/shutdown", "/api/admin/server/shutdown"])

_instance: "AndroidApi | None" = None


def configure(workspace_root: str) -> None:
    """Point the workspace root at the Android app's private storage.

    Must be called (from Kotlin, via Chaquopy) before :func:`get_api` so every
    writable-path helper that consults ``platform_runtime`` resolves against
    app-private ``filesDir`` instead of the read-only, APK-bundled package
    root. Also marks the platform as mobile, which is what selects the
    in-process build runner and disables subprocess/browser capabilities.
    """
    os.environ["RETIREMENT_SYSTEM_PLATFORM"] = "android"
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = workspace_root
    # No display server on Android: force matplotlib's file-only backend before
    # anything imports it (the report pipeline renders charts to PNG buffers).
    os.environ.setdefault("MPLBACKEND", "Agg")


def get_api() -> "AndroidApi":
    """Return the process-lifetime :class:`AndroidApi` singleton, creating it on first use."""
    global _instance
    if _instance is None:
        _instance = AndroidApi()
    return _instance


class AndroidApi:
    """Bridge target for the Kotlin ``JavascriptInterface``.

    One instance lives for the app's process lifetime. Construct it (via
    :func:`get_api`) only after :func:`configure` has run.
    """

    def __init__(self) -> None:
        _set_local_mode_defaults()
        from src.server import create_app  # noqa: PLC0415
        self._app = create_app()
        self._client = self._app.test_client()
        self._request_lock = threading.Lock()

    def request(
        self,
        method: str,
        url: str,
        body_json: Any = None,
        body_text: str | None = None,
    ) -> dict:
        """Dispatch one HTTP-style call through the local stdlib route registry."""
        if url in _SHUTDOWN_URLS:
            return {"success": True}

        method_lower = method.lower()
        client_fn = getattr(self._client, method_lower, None)
        if client_fn is None:
            return {"success": False, "error": f"Unsupported method: {method}"}

        with self._request_lock:
            try:
                if body_json is not None:
                    resp = client_fn(url, json=body_json)
                elif body_text is not None:
                    resp = client_fn(
                        url,
                        data=body_text.encode("utf-8", errors="replace"),
                        content_type="text/plain; charset=utf-8",
                    )
                else:
                    resp = client_fn(url)
            except Exception as exc:  # noqa: BLE001
                return {"success": False, "error": str(exc)}

            return self._convert(resp)

    def request_json(
        self,
        method: str,
        url: str,
        body_json_text: str | None = None,
        body_text: str | None = None,
    ) -> str:
        """String-in/string-out wrapper around :meth:`request` for the Kotlin side.

        Chaquopy converts a returned Python ``dict`` to a Java ``Map``
        automatically, but a single JSON string is simpler for Kotlin to parse
        consistently (nested lists/dicts included) and to hand back to JS
        verbatim. ``body_json_text``, when provided, is a JSON-encoded body.
        """
        body_json = json.loads(body_json_text) if body_json_text else None
        result = self.request(method, url, body_json=body_json, body_text=body_text)
        return json.dumps(result)

    def _convert(self, resp) -> dict:
        ct = (resp.content_type or "").lower()
        raw: bytes = resp.get_data()

        if resp.status_code >= 500:
            try:
                return json.loads(raw) or {"success": False}
            except Exception:  # noqa: BLE001
                return {
                    "success": False,
                    "error": raw.decode("utf-8", errors="replace"),
                }

        if "json" in ct:
            try:
                return json.loads(raw) or {}
            except Exception:  # noqa: BLE001
                return {"success": False, "error": "Invalid JSON from server"}

        if "text" in ct or "csv" in ct or "html" in ct:
            return {
                "success": True,
                "_text": raw.decode("utf-8", errors="replace"),
                "_content_type": ct,
            }

        filename = ""
        cd = resp.headers.get("Content-Disposition", "")
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                filename = part[9:].strip("\"'")
                break

        return {
            "success": True,
            "_binary": base64.b64encode(raw).decode("ascii"),
            "_content_type": ct or "application/octet-stream",
            "_filename": filename or "download",
        }
