"""Launcher for the Playwright browser E2E suite (system review 2026-08-04,
finding `no-browser-execution-testing`).

Deliberately does NOT go through main.py --mode server: that entry point
unconditionally schedules ``webbrowser.open()`` 1.5s after startup regardless
of RETIREMENT_SYSTEM_NO_AUTO_OPEN (that env var only suppresses a different,
inner auto-open path), which is noisy and fragile under CI/headless
conditions. This calls the same primitive main.py uses
(``run_local_server(create_app(), ...)``) directly, so no browser-open side
effect exists to suppress.

Workspace setup mirrors tests/test_workbook_pdf_build_snapshot.py's pattern:
a throwaway directory seeded from the committed, static, self-contained
tests/fixtures/sample_plan_frozen/ plan, with pricing and the wall-clock date
pinned so every E2E run sees the same household regardless of when or where
it runs. Monte Carlo sim counts are reduced the same way that file's
subprocess build reduces them, since J2 (build -> results) would otherwise
pay full simulation cost on every CI run.

Intended to be launched by playwright.config.js's `webServer` option, which
owns starting it, polling for readiness, and killing it after the run --
nothing here manages its own lifecycle beyond serve_forever().
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"

# Fixed port so playwright.config.js's url check has a stable target.
E2E_PORT = int(os.environ.get("RETIREMENT_SYSTEM_E2E_PORT", "5951"))
# Frozen date kept in sync with conftest.py/test_199's FROZEN_TODAY by
# convention, not by import -- this script must run standalone in a fresh
# Playwright-spawned process with no guarantee tests/ is on sys.path.
FROZEN_TODAY = "2026-08-04"


def _clear_readonly(func, path, _exc_info):
    os.chmod(path, 0o666)
    func(path)


def _stage_workspace() -> Path:
    import tempfile

    workspace = Path(tempfile.mkdtemp(prefix="e2e_workspace_"))
    for name in ("input", "output", "local_state", "saved_plans"):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    for f in sorted(FROZEN_DIR.iterdir()):
        if f.is_file():
            shutil.copy(f, workspace / "input" / f.name)
    return workspace


def main() -> int:
    workspace = _stage_workspace()

    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace)
    os.environ["RETIREMENT_SYSTEM_FROZEN_TODAY"] = FROZEN_TODAY
    os.environ["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    os.environ["RETIREMENT_SYSTEM_NO_AUTO_OPEN"] = "1"
    # Keep builds fast: J2 triggers a real build through the UI, and the
    # default sim counts make that a multi-minute wait. Same reduction
    # test_workbook_pdf_build_snapshot.py's subprocess build already uses.
    os.environ.setdefault("RETIREMENT_MC_SIMS", "16")
    os.environ.setdefault("RETIREMENT_MC_SENSITIVITY_SIMS", "3")

    sys.path.insert(0, str(ROOT))
    from src.server import create_app  # noqa: PLC0415
    from src.http_runtime.server import run_local_server  # noqa: PLC0415

    print(f"E2E server workspace: {workspace}")
    print(f"E2E server listening on http://127.0.0.1:{E2E_PORT}")
    try:
        run_local_server(create_app(), host="127.0.0.1", port=E2E_PORT, debug=False)
    finally:
        shutil.rmtree(workspace, ignore_errors=True, onerror=_clear_readonly)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
