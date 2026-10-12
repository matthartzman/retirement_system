#!/usr/bin/env python3
"""Reset the v11 local desktop/development runtime settings.

The packaged app is local-only. This helper writes the local-mode runtime settings into this
install's app.db (``src/app_state.app_store_path()``; ``RETIREMENT_SYSTEM_APP_DB`` or
``--app-db`` overrides it). A setting equal to its built-in default is simply unset.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UPDATES = {
    ("System Configuration", "Runtime", "app_mode"): "LOCAL",
    ("System Configuration", "Runtime", "output_dir"): "output",
    ("System Configuration", "Dashboard", "host"): "127.0.0.1",
    ("System Configuration", "Dashboard", "port"): "5050",
    ("System Configuration", "Security", "session_cookie_secure"): "NO",
}


def main(app_db: str | Path | None = None) -> int:
    from src.system_config import set_system_settings  # noqa: PLC0415

    set_system_settings(UPDATES, app_db)
    print("Local development mode restored.")
    print("Open UI: http://127.0.0.1:5050")
    print("Admin UI: http://127.0.0.1:5050/admin")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-db", default=None, help="app.db to write (default: this install's)")
    raise SystemExit(main(parser.parse_args().app_db))
