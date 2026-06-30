"""PyWebView desktop launcher for the Retirement Planning System.

Opens a native window (Edge WebView2 on Windows) that loads the frontend
HTML directly from the filesystem.  The JS bridge shim intercepts all
``fetch('/api/...')`` calls and routes them through ``DesktopApi.request()``
instead of over HTTP, so no local server socket is ever opened.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def start() -> int:
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        print(
            "pywebview is not installed.\n"
            "Run: python -m pip install pywebview\n",
            file=sys.stderr,
        )
        return 1

    from src.desktop_api import DesktopApi  # noqa: PLC0415

    api = DesktopApi()

    index_html = FRONTEND / "index.html"
    if not index_html.exists():
        print(f"Frontend not found: {index_html}", file=sys.stderr)
        return 1

    window = webview.create_window(
        title="Retirement Planner",
        url=index_html.as_uri(),
        js_api=api,
        width=1440,
        height=900,
        min_size=(900, 600),
        # Always open maximized; width/height/min_size remain the size the
        # window restores to when the user un-maximizes.
        maximized=True,
        # Resizable native window — no server address bar
        text_select=True,
    )

    # Expose a helper so the bridge shim can detect desktop mode before
    # window.pywebview is fully injected.
    window.expose(api.navigate)

    def on_closing():
        """Intercept OS-level window close (X button).

        If JS has already confirmed shutdown (DesktopApi._app_exiting is True),
        allow the native close.  Otherwise cancel the native close immediately
        and trigger exitApp() in JS via a daemon thread — keeping the OS event
        handler non-blocking to prevent the Windows spinner.
        """
        import threading  # noqa: PLC0415

        if api._app_exiting:
            return  # allow native close — JS confirmed shutdown via /api/shutdown

        # Cancel the native close and let JS drive the save-or-discard modal.
        # evaluate_js() is synchronous and blocks the calling thread; running it
        # in a daemon thread prevents the OS from showing a "not responding"
        # spinner while the modal is open.
        def _trigger_exit():
            try:
                window.evaluate_js("exitApp()")
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_trigger_exit, daemon=True).start()
        return False  # cancel native close; JS will call /api/shutdown later

    window.events.closing += on_closing

    webview.start(debug=False)
    return 0
