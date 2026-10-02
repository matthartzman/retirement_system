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


from src.bootstrap import run_startup_bootstrap  # noqa: E402


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
        # System review 2026-09-25, Wave 0 WI-000 / ARC-002: shared with
        # main.py and tools/launchers/START_DESKTOP.py via src/bootstrap.py,
        # rather than this module's own (previously incomplete -- it omitted
        # CONFIG_FILE/OUTPUT_DIR/JSON_CONFIG_FILE/YAML_CONFIG_FILE) copy of
        # the local-mode env defaults. Also runs the at-rest Plan Data
        # migration, guarded to run at most once per process.
        run_startup_bootstrap()
        # Desktop-bridge-specific, not part of the shared bootstrap (server
        # mode wants its own auto-open behavior): suppress the local HTTP
        # runtime's auto browser-open, since this bridge never starts one.
        os.environ.setdefault("RETIREMENT_SYSTEM_NO_AUTO_OPEN", "1")
        from src.server import create_app  # noqa: PLC0415
        from src.server.workbook_routes import register_progress_push  # noqa: PLC0415
        self._app = create_app()
        # ARC-001 (system review 2026-09-25): _security_gate's CSRF/Origin
        # allow-list exists to stop a remote page from forging a non-GET
        # request. This bridge dispatches every call in-process through
        # test_client() below -- no socket is ever opened (see module
        # docstring) -- so there is no network boundary for a remote page to
        # cross, and it never sends an Origin/Referer or CSRF token anyway
        # (headers are not forwarded across the bridge). Marked once, here,
        # rather than guessed at in _security_gate from header shape.
        self._app._no_http_transport = True
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

        filename = ""
        cd = resp.headers.get("Content-Disposition", "")
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                filename = part[9:].strip("\"'")
                break

        is_xlsx = "spreadsheet" in ct or "excel" in ct or (filename and filename.endswith(".xlsx"))
        if is_xlsx:
            # Ticket <workbook-filename>: this used to always fall through to
            # the generic tempfile.NamedTemporaryFile branch below, so every
            # workbook download landed at a random path like
            # AppData\Local\Temp\tmpXXXXXXXX.xlsx and Excel's title bar showed
            # that cryptic name -- the file was never actually saved anywhere
            # the user could find it again. The server now sends a real name
            # via Content-Disposition (report_service.workbook_download_filename()),
            # so this saves it under that name in the configured folder
            # (Data & Maintenance > Downloads; blank falls back to the OS
            # Downloads folder, same default used by save_text_file() below)
            # instead of a temp directory.
            from src import system_config  # noqa: PLC0415

            data = system_config.load_system_config()
            configured = system_config.workbook_desktop_download_folder(data)
            folder = Path(configured) if configured else None
            if not folder or not folder.is_dir():
                folder = next(
                    (p for p in (Path.home() / "Downloads", Path.home() / "Documents", Path.home())
                     if p.is_dir()),
                    Path.home(),
                )
            dest = self._write_unique(folder / (filename or "Retirement Workbook.xlsx"), raw)
            self._open_path(dest)
            return {"success": True, "opened": True, "path": str(dest)}

        import tempfile  # noqa: PLC0415

        if "pdf" in ct or (filename and filename.endswith(".pdf")):
            suffix = ".pdf"
        else:
            suffix = Path(filename).suffix if filename else ".bin"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(raw)
            tmp = Path(tf.name)
        self._open_path(tmp)
        return {"success": True, "opened": True}

    @staticmethod
    def _write_unique(dest: Path, raw: bytes) -> Path:
        """Write ``raw`` to ``dest``; if that file cannot be written (on Windows,
        typically because the same-named workbook from a moments-ago download is
        still open in Excel and locked), write "name (2).xlsx", "name (3).xlsx", ...
        instead of failing the download."""
        try:
            dest.write_bytes(raw)
            return dest
        except PermissionError as first_error:
            for n in range(2, 100):
                alt = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
                try:
                    alt.write_bytes(raw)
                    return alt
                except PermissionError:
                    continue
            raise first_error

    @staticmethod
    def _open_path(path: Path) -> None:
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415

        if sys.platform == "win32":
            os.startfile(str(path))  # Windows-only os attribute
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

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

    def save_text_file(self, default_name: str, text: str, kind: str = "CSV") -> dict:
        """Save generated text through a native Save As dialog, returning the path.

        Ticket 279. The browser blob-download path (`downloadBlob`) is a no-op
        worth nothing in desktop mode: PyWebView has no download manager, so an
        `<a download>` click either does nothing visible or drops the file
        somewhere the user never finds -- reported as "download template either
        does nothing or just doesn't let me know where it put the template."
        Same reasoning as ``export_csv_backup`` above, which already sidesteps
        downloads for exactly this.

        Defaults to the user's Downloads folder (falling back to Documents,
        then home) so the suggested location matches where a browser would have
        put it. Returns the real path so the caller can TELL the user where it
        landed rather than leaving them to guess.
        """
        try:
            import webview  # noqa: PLC0415
            if not webview.windows:
                return {"cancelled": True, "error": "No window"}
            suffix = Path(default_name).suffix or ".csv"
            start_dir = next(
                (p for p in (Path.home() / "Downloads", Path.home() / "Documents", Path.home())
                 if p.is_dir()),
                Path.home(),
            )
            result = webview.windows[0].create_file_dialog(
                webview.SAVE_DIALOG,
                directory=str(start_dir),
                save_filename=default_name,
                file_types=(f"{kind} (*{suffix})", "All files (*.*)"),
            )
            if not result:
                return {"cancelled": True}
            path = result[0] if isinstance(result, (list, tuple)) else result
            if path and not str(path).lower().endswith(suffix.lower()):
                path = str(path) + suffix
            Path(path).write_text(text or "", encoding="utf-8", newline="")
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
