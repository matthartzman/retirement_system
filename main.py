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

# Windows defaults stdout/stderr to the legacy ANSI code page (cp1252) unless
# PYTHONUTF8/PYTHONIOENCODING is set, which this app does not require of its
# users. Any print()/logging call anywhere in the process -- including ones
# that echo user-entered config text (e.g. a note containing "μ") -- then
# raises UnicodeEncodeError the moment that text can't be represented in
# cp1252, surfacing as a raw crash (or, via app_core.py's catch-all
# @app.errorhandler(Exception), as an opaque "UnicodeEncodeError: 'charmap'
# codec can't encode character..." shown to the user in place of whatever the
# request was actually trying to do). reconfigure() with errors="replace" is
# a no-op on platforms where the stream is already UTF-8-capable.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - never block startup over this
            pass

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
# Shared startup sequence (env defaults + at-rest Plan Data migration) --
# system review 2026-09-25, Wave 0 WI-000 / ARC-002. Moved to src/bootstrap.py
# so tools/launchers/START_DESKTOP.py and DesktopApi.__init__ share the exact
# same defaults and migration call instead of each maintaining (and drifting
# from) their own copy. Imported lazily inside main(), matching this file's
# existing pattern for every other src.* import.
# ---------------------------------------------------------------------------


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

    # Sets local-mode env defaults, then migrates stored Plan Data once,
    # before either mode opens it (the workspace root it resolves against is
    # env-driven, so the defaults must land first). Shared with
    # tools/launchers/START_DESKTOP.py and DesktopApi.__init__ via
    # src/bootstrap.py (system review 2026-09-25, WI-000/ARC-002) so every
    # launch path runs the identical sequence -- previously only this one did.
    #
    # run_startup_plan_data_migration() swallows its own failures by design --
    # a bad CSV degrades to the existing per-load normalization rather than
    # stopping the app from booting.
    from src.bootstrap import run_startup_bootstrap
    _migration = run_startup_bootstrap()
    if _migration.get("total_changed"):
        print(f"Plan Data migrated at rest: {_migration['migrated']}")
    if _migration.get("error"):
        # The plan file's rows stayed unmigrated this boot; CSVs (if any changed
        # above) did not. The version is deliberately left unstamped so this
        # retries on next boot -- see migrate_plan_data_at_rest's own comment.
        print(f"WARNING: Plan Data plan-rows migration failed and will retry next boot: {_migration['error']}")

    if args.mode == "server":
        return _run_server()
    return _run_desktop()


if __name__ == "__main__":
    # MUST be the first statement in this block. This app ships as a
    # PyInstaller onedir exe, and a workbook build inside it creates a
    # ProcessPoolExecutor (the Sheet 10 claim-age sweep). Under sys.frozen,
    # multiprocessing spawns children as
    # [sys.executable, '--multiprocessing-fork', <fds>] -- i.e. re-runs THIS
    # exe. PyInstaller's runtime hook only rebinds freeze_support() to a
    # working implementation; it never calls it. Without this call the child
    # would fall through and re-enter main() (launching a second app window
    # or hanging the parent's fut.result()) instead of becoming a pool
    # worker. In a non-frozen, non-child run this is a no-op.
    import multiprocessing

    multiprocessing.freeze_support()

    raise SystemExit(main())
