#!/usr/bin/env python3
"""Standalone entry point for the Retirement Planning System.

Startup modes (selected by --mode flag or RETIREMENT_SYSTEM_LAUNCH_MODE env var):

  desktop  (default) — PyWebView native window; no HTTP server, no browser.
                        The JS bridge shim routes all fetch() calls through
                        the local stdlib route registry in-process.

  server             — Stdlib local HTTP server on port 5050, opens browser.
                        Use for debugging or CLI/browser access.

When frozen with PyInstaller the exe also acts as a script runner:
  retirement_planner.exe tools/build_workbook.py [args...]
  This preserves the subprocess.Popen([sys.executable, script]) pattern used
  by workbook_routes and plan_routes.
"""
from __future__ import annotations

import argparse
import os
import runpy
import sys
import threading
import webbrowser

# ---------------------------------------------------------------------------
# Script-runner mode (frozen exe only)
# ---------------------------------------------------------------------------
def _is_script_arg(arg: str) -> bool:
    return not arg.startswith("-") and arg.endswith(".py")


if getattr(sys, "frozen", False) and len(sys.argv) >= 2 and _is_script_arg(sys.argv[1]):
    _script = sys.argv[1]
    sys.argv = sys.argv[1:]
    try:
        runpy.run_path(_script, run_name="__main__")
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as _exc:
        print(f"Script runner error in {_script}: {_exc}", file=sys.stderr)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Shared env-var defaults (both modes need these)
# ---------------------------------------------------------------------------
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
        "RETIREMENT_SYSTEM_PUBLIC_BASE_URL": "",
        "RETIREMENT_SYSTEM_CONFIG_FILE": "input/client_data.csv",
        "RETIREMENT_SYSTEM_JSON_CONFIG_FILE": "input/client_data.json",
        "RETIREMENT_SYSTEM_YAML_CONFIG_FILE": "input/client_data.yaml",
        "RETIREMENT_SYSTEM_OUTPUT_DIR": "output",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# Desktop mode — PyWebView, no HTTP socket
# ---------------------------------------------------------------------------
def _run_desktop() -> int:
    from src.desktop_app import start  # noqa: PLC0415
    return start()


# ---------------------------------------------------------------------------
# Server mode — stdlib local HTTP runtime
# ---------------------------------------------------------------------------
def _run_server() -> int:
    os.environ["RETIREMENT_SYSTEM_NO_AUTO_OPEN"] = "1"
    from src.server import create_app, _runtime_config  # noqa: PLC0415
    from src.http_runtime.server import run_local_server  # noqa: PLC0415

    cfg = _runtime_config()
    host = cfg.dashboard_host or "127.0.0.1"
    port = int(cfg.dashboard_port or 5050)
    url = f"http://{host}:{port}"

    print(f"""
======================================================
  RETIREMENT PLAN SYSTEM v11  [server mode]
======================================================
  Dashboard:  {url}
  Runtime:    stdlib local HTTP
  Mode:       {cfg.app_mode}
======================================================
""")
    # (NO_AUTO_OPEN above suppresses the inner server's own auto-open, not this
    # intentional desktop open.)
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    run_local_server(create_app(), host=host, port=port, debug=False)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    _set_local_mode_defaults()

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--mode",
        choices=["desktop", "server"],
        default=os.getenv("RETIREMENT_SYSTEM_LAUNCH_MODE", "desktop"),
    )
    parser.add_argument("-h", "--help", action="store_true")
    args, _ = parser.parse_known_args()

    if args.help:
        parser.print_help()
        return 0

    # Migrate stored Plan Data once, before either mode opens it. This runs
    # after _set_local_mode_defaults() because the workspace root it resolves
    # against is env-driven, and before the dispatch below so both modes get it.
    #
    # It is deliberately NOT above the frozen script-runner branch at module
    # scope: that path runs tools/build_workbook.py in a subprocess, and a
    # build has no business rewriting plan data at rest.
    #
    # run_startup_plan_data_migration() swallows its own failures by design --
    # a bad CSV degrades to the existing per-load normalization rather than
    # stopping the app from booting.
    from src.plan_data_migration import run_startup_plan_data_migration
    _migration = run_startup_plan_data_migration()
    if _migration["total_changed"]:
        print(f"Plan Data migrated at rest: {_migration['migrated']}")
    if _migration.get("error"):
        # DB snapshots stayed unmigrated this boot; CSVs (if any changed above)
        # did not. The version is deliberately left unstamped so this retries
        # on next boot -- see migrate_plan_data_at_rest's own comment.
        print(f"WARNING: Plan Data DB-snapshot migration failed and will retry next boot: {_migration['error']}")

    if args.mode == "server":
        return _run_server()
    return _run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
