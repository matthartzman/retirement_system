"""Probe executed INSIDE the frozen build by scripts/pyinstaller_smoke.py.

Run as ``retirement_planner <this file>`` (main.py's script-runner mode), so it
exercises the frozen interpreter's bundled numpy/scipy/lxml/openpyxl, the
bundled ``src`` package and the bundled demo plan -- everything a hidden-import
or data-file omission in retirement_planner.spec would break. Prints one
``SMOKE_PROBE_OK {json}`` line on success; any exception exits non-zero.
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS", "1")

import lxml.etree  # noqa: F401,E402
import numpy  # noqa: E402
import openpyxl  # noqa: F401,E402
import scipy.optimize  # noqa: F401,E402

from src.data_io import load_csv  # noqa: E402
from src.planning_engines import monte_carlo  # noqa: E402
from src.platform_runtime import package_root  # noqa: E402
from src.report_compute import prepare_config_from_sectioned_data  # noqa: E402

demo = package_root() / "input" / "demo" / "client_data.csv"
if not demo.is_file():
    raise SystemExit(f"bundled demo plan missing: {demo}")

cfg = prepare_config_from_sectioned_data(load_csv(demo), "")
cfg.update(mc_sims=20, mc_sensitivity_sims=1, mc_engine_mode="vectorized")
mc = monte_carlo(cfg, seed=1)
rate = float(mc["success_rate"])
if not 0.0 <= rate <= 1.0:
    raise SystemExit(f"success_rate out of range: {rate}")

print("SMOKE_PROBE_OK " + json.dumps({
    "frozen": bool(getattr(sys, "frozen", False)),
    "numpy": numpy.__version__,
    "success_rate": rate,
    "mc_status": mc.get("mc_approximation_status"),
}))
