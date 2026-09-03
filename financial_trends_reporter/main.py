#!/usr/bin/env python3
"""Financial trends reporter -- standalone entry point (ticket 306).

A small local server (reusing retirement_system's stdlib HTTP runtime, not a
new web framework) that serves the trend dashboard and the JSONL log history
as JSON. Run this to view trends interactively; the weekday-5pm log entry
itself is written by tools/append_trends_log.py (headless, via Windows Task
Scheduler), not by this server.

Usage: python financial_trends_reporter/main.py [--retirement-system-dir PATH] [--port 5057]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _APP_ROOT.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.http_runtime.server import run_local_server  # noqa: E402
from src.http_runtime.wsgi_facade import Flask, Response  # noqa: E402

from financial_trends_reporter.trends_job import run as run_trends_job  # noqa: E402
from financial_trends_reporter.trends_log import default_log_path, read_history  # noqa: E402

INDEX_HTML_PATH = _APP_ROOT / "frontend" / "index.html"


def create_app(retirement_system_dir: Path, log_path: Path | None = None) -> Flask:
    app = Flask("financial_trends_reporter", static_folder=str(_APP_ROOT / "frontend"))
    resolved_log_path = log_path or default_log_path(_APP_ROOT)

    @app.route("/", methods=["GET"])
    def index():
        return Response(INDEX_HTML_PATH.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")

    @app.route("/api/history", methods=["GET"])
    def history():
        return Response(json.dumps(read_history(resolved_log_path)), content_type="application/json")

    @app.route("/api/run-now", methods=["POST"])
    def run_now():
        result = run_trends_job(retirement_system_dir, log_path=resolved_log_path)
        return Response(json.dumps(result), status=200 if result.get("success") else 400, content_type="application/json")

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retirement-system-dir", default=str(_REPO_ROOT), help="retirement_system workspace root; defaults to this repo's own root")
    # 5060 (SIP) is deliberately avoided: it's on Chrome/Chromium's built-in
    # restricted-ports list, so a browser tab opened against it fails with
    # ERR_UNSAFE_PORT even though the server itself is listening fine.
    parser.add_argument("--port", type=int, default=5057)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="Don't auto-open a browser tab")
    args = parser.parse_args(argv)

    app = create_app(Path(args.retirement_system_dir))
    url = f"http://{args.host}:{args.port}"
    print(f"Financial trends reporter listening on {url}")
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    run_local_server(app, host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
