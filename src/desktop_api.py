"""Desktop API bridge for PyWebView.

Exposes a single ``request(method, url, body_json, body_text)`` method that
the JS bridge shim calls instead of ``fetch()``.  All routing and business
logic is handled by the dependency-free local route registry via its test
client — no network socket is opened, no port is bound.

The only special-cased URLs are the shutdown endpoints, which destroy the
PyWebView window directly instead of routing through the local route registry.
"""
from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable


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


def _safe_evaluate_js(window, js: str) -> None:
    """Call evaluate_js without raising — used for fire-and-forget pushes."""
    try:
        window.evaluate_js(js)
    except Exception:  # noqa: BLE001
        pass

# URL prefixes that must reach the local router; everything else is a static asset and
# should never arrive at this bridge.
_API_PREFIXES = ("/api/", "/files/", "/frontend/")


class DesktopApi:
    """PyWebView JS-API class.  One instance lives for the app\'s lifetime."""

    def __init__(self) -> None:
        _set_local_mode_defaults()
        from src.server import create_app  # noqa: PLC0415
        from src.server.workbook_routes import register_progress_push  # noqa: PLC0415
        self._app = create_app()
        self._client = self._app.test_client()
        self._request_lock = threading.Lock()
        self._last_push_key: tuple = ()
        register_progress_push(self._push_build_progress)
        self._app_exiting = False  # set True by _shutdown() before window.destroy()

    # ------------------------------------------------------------------
    # Public bridge method — called from JS as window.pywebview.api.request(...)
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        body_json: Any = None,
        body_text: str | None = None,
    ) -> dict:
        """Dispatch one HTTP-style call through the local stdlib route registry."""
        if url in _SHUTDOWN_URLS:
            self._shutdown()
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

    def navigate(self, url: str) -> None:
        """Called by the JS bridge when the page performs an internal navigation."""
        import webview  # noqa: PLC0415

        if not webview.windows:
            return
        window = webview.windows[0]
        root = Path(__file__).resolve().parents[1]
        if url.rstrip("/") in ("", "/", "/frontend"):
            target = root / "frontend" / "index.html"
        elif "/admin" in url or "/system-configuration" in url:
            target = root / "frontend" / "admin.html"
        else:
            return
        window.load_url(target.as_uri())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

        import tempfile  # noqa: PLC0415

        filename = ""
        cd = resp.headers.get("Content-Disposition", "")
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                filename = part[9:].strip("\"'")
                break

        if "spreadsheet" in ct or "excel" in ct or (filename and filename.endswith(".xlsx")):
            suffix = ".xlsx"
        elif "pdf" in ct or (filename and filename.endswith(".pdf")):
            suffix = ".pdf"
        else:
            suffix = Path(filename).suffix if filename else ".bin"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(raw)
            tmp = Path(tf.name)
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415
        if sys.platform == "win32":
            os.startfile(str(tmp))  # Windows-only os attribute
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(tmp)])
        else:
            subprocess.Popen(["xdg-open", str(tmp)])

        return {"success": True, "opened": True}

    def _push_build_progress(self, job: dict) -> None:
        """Forward a build progress snapshot to the JS layer via evaluate_js."""
        import webview  # noqa: PLC0415

        if not webview.windows:
            return

        status = job.get("status") or ""
        key = (status, job.get("progress"), job.get("phase"))
        if key == self._last_push_key and status not in ("done", "failed"):
            return
        self._last_push_key = key

        payload = {
            "job_id": job.get("job_id", ""),
            "status": status,
            "progress": job.get("progress", 0),
            "phase": job.get("phase", ""),
            "detail": job.get("detail", ""),
            "result": job.get("result"),
        }
        js = f"typeof updateBuildProgress==='function'&&updateBuildProgress({json.dumps(payload)})"
        # Fire-and-forget: don't block the build thread waiting for the UI thread.
        # The polling loop in JS is the primary progress mechanism; this is a bonus update.
        import threading  # noqa: PLC0415
        win = webview.windows[0]
        threading.Thread(target=lambda: _safe_evaluate_js(win, js), daemon=True).start()

    def show_save_dialog(self, default_name: str = "myplan.rpx") -> dict:
        """Open a native Save As dialog filtered to .rpx files."""
        try:
            import webview  # noqa: PLC0415
            if not webview.windows:
                return {"cancelled": True, "error": "No window"}
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=str(Path.home() / "Documents"),
                save_filename=default_name,
                file_types=("Retirement Plan (*.rpx)", "All files (*.*)")
            )
            if not result:
                return {"cancelled": True}
            path = result[0] if isinstance(result, (list, tuple)) else result
            if path and not str(path).lower().endswith(".rpx"):
                path = str(path) + ".rpx"
            return {"cancelled": False, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"cancelled": True, "error": str(exc)}

    def export_csv_backup(self) -> dict:
        """Build the CSV backup zip and let the user choose where to save it via a native dialog.

        A plain ``<input type=file>``/download fallback can't select a save
        folder, and generic binary downloads fall back to opening the file in
        Explorer with no save affordance — so this uses the same native
        Save As dialog as ``show_save_dialog`` instead.
        """
        try:
            import webview  # noqa: PLC0415
            if not webview.windows:
                return {"cancelled": True, "error": "No window"}
            from src.server_services import admin_service  # noqa: PLC0415
            from src.server.app_core import BASE_DIR  # noqa: PLC0415
            data, default_name = admin_service.build_csv_backup_zip(BASE_DIR)
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=str(Path.home() / "Documents"),
                save_filename=default_name,
                file_types=("Zip archive (*.zip)", "All files (*.*)")
            )
            if not result:
                return {"cancelled": True}
            path = result[0] if isinstance(result, (list, tuple)) else result
            if path and not str(path).lower().endswith(".zip"):
                path = str(path) + ".zip"
            Path(path).write_bytes(data)
            return {"cancelled": False, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"cancelled": True, "error": str(exc)}

    def show_open_dialog(self) -> dict:
        """Open a native Open File dialog filtered to .rpx files."""
        try:
            import webview  # noqa: PLC0415
            if not webview.windows:
                return {"cancelled": True, "error": "No window"}
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                directory=str(Path.home() / "Documents"),
                file_types=("Retirement Plan (*.rpx)", "All files (*.*)")
            )
            if not result:
                return {"cancelled": True}
            path = result[0] if isinstance(result, (list, tuple)) else result
            return {"cancelled": False, "path": str(path)}
        except Exception as exc:  # noqa: BLE001
            return {"cancelled": True, "error": str(exc)}

    def _shutdown(self) -> None:
        """Signal shutdown and destroy the PyWebView window to exit.

        Called when JS routes a /api/shutdown request through the bridge.
        Sets _app_exiting so the on_closing handler knows JS has already
        confirmed the exit and will allow the native window close.
        """
        import webview  # noqa: PLC0415

        self._app_exiting = True
        if webview.windows:
            webview.windows[0].destroy()
