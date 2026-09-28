#!/usr/bin/env python3
"""Start the Retirement System as a native desktop window (no Flask HTTP server).

Uses PyWebView + the in-process DesktopApi bridge so no port is bound and no
server process needs to stay running in a terminal.  All API calls are
dispatched directly to the Python backend through Flask's test client.

Usage (from project root):
    python tools/launchers/START_DESKTOP.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    # System review 2026-09-25, Wave 0 WI-000 / ARC-002: this is the entry
    # point the desktop shortcut and START_APP.bat actually launch (see
    # launchers/START_APP.bat and launchers/CREATE_DESKTOP_SHORTCUT.vbs) --
    # not main.py. It used to set its own copy of the local-mode env
    # defaults and never ran the at-rest Plan Data migration at all, so a
    # user who only ever launched from the desktop icon never got a legacy
    # flat-category-id migration applied. Now shares the same bootstrap
    # sequence main.py and DesktopApi.__init__ use.
    from src.bootstrap import run_startup_bootstrap
    run_startup_bootstrap()
    from src.desktop_app import start
    raise SystemExit(start())
