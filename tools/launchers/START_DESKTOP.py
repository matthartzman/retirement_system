#!/usr/bin/env python3
"""Start the Retirement System as a native desktop window (no Flask HTTP server).

Uses PyWebView + the in-process DesktopApi bridge so no port is bound and no
server process needs to stay running in a terminal.  All API calls are
dispatched directly to the Python backend through Flask's test client.

Usage (from project root):
    python tools/launchers/START_DESKTOP.py
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Local-mode defaults — same as the HTTP-server launcher.
os.environ.setdefault("RETIREMENT_SYSTEM_APP_MODE", "LOCAL")
os.environ.setdefault("RETIREMENT_SYSTEM_WORKSPACE_ID", "local")
os.environ.setdefault("RETIREMENT_SYSTEM_CLIENT_ID", "local")
os.environ.setdefault("RETIREMENT_SYSTEM_DASHBOARD_HOST", "127.0.0.1")
os.environ.setdefault("RETIREMENT_SYSTEM_DASHBOARD_PORT", "5050")
os.environ.setdefault("RETIREMENT_SYSTEM_REQUIRE_API_TOKEN", "NO")
os.environ.setdefault("RETIREMENT_SYSTEM_ALLOW_UNAUTHENTICATED_SAAS", "YES")
os.environ.setdefault("RETIREMENT_SYSTEM_FORCE_HTTPS", "NO")
os.environ.setdefault("RETIREMENT_SYSTEM_REVERSE_PROXY_ENABLED", "NO")
os.environ.setdefault("RETIREMENT_SYSTEM_PUBLIC_BASE_URL", "")
os.environ.setdefault("RETIREMENT_SYSTEM_CONFIG_FILE", "input/client_data.csv")
os.environ.setdefault("RETIREMENT_SYSTEM_JSON_CONFIG_FILE", "input/client_data.json")
os.environ.setdefault("RETIREMENT_SYSTEM_YAML_CONFIG_FILE", "input/client_data.yaml")
os.environ.setdefault("RETIREMENT_SYSTEM_OUTPUT_DIR", "output")

if __name__ == "__main__":
    from src.desktop_app import start
    raise SystemExit(start())
