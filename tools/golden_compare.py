#!/usr/bin/env python
"""Golden before/after harness (WP0.1).

Builds the frozen sample plan and the demo plan in a throwaway workspace and
records three things per plan: full-row engine output, the cell values of the
required workbook sheets, and the headline KPIs from the build's stored summary (``build_results``).
The committed baseline lives in ``tests/fixtures/golden_phase_baseline/``;
``tests/test_phase_golden_equality_regression.py`` compares live output to it.

Usage
-----
    python tools/golden_compare.py compare            # exit 1 on any diff
    python tools/golden_compare.py record --reason "<why the baseline moves>"

``record`` is the only sanctioned way to rewrite the baseline (reason rules
match tools/regen_full_row_snapshot.py). The compare step is the gate that
every later file-elimination phase must keep green.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_DIR = ROOT / "tests" / "fixtures" / "golden_phase_baseline"
PLAN_SOURCES = {
    "sample_frozen": ROOT / "tests" / "fixtures" / "sample_plan_frozen",
    "demo": ROOT / "input" / "demo",
}
SNAPSHOT_FIXTURE = ROOT / "tests" / "fixtures" / "workbook_snapshot_expectations.json"
# Files that carry spending history and YTD; a plan missing them would make the
# baseline blind to the spending/YTD pipeline, so capture refuses to run.
REQUIRED_PLAN_FILES = (
    "client_data.csv", "client_spending.csv", "client_spending_budget.csv",
    "ytd_transactions.csv", "ytd_account_setup.csv",
)
EXCLUDED_NAMES = {
    ".git", ".claude", ".pytest_cache", "tests", "documentation", "output",
    "local_state", "__pycache__", "node_modules", "frontend", "docs",
}
FLOAT_PLACES = 2
FROZEN_TODAY = "2026-08-04"  # same pin as tests/conftest.py FROZEN_PLAN_TODAY


def _mask_build_date(value):
    """Replace the real build date (``Built: <today>`` on the executive summary).

    The summary stamps ``datetime.date.today()`` and ignores FROZEN_TODAY, so
    without masking every capture differs from the baseline once the day changes.
    """
    if isinstance(value, str):
        return value.replace(datetime.date.today().isoformat(), "<build-date>")
    return value


def _round(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return round(value, FLOAT_PLACES)
    if isinstance(value, dict):
        return {str(k): _round(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_round(v) for v in value]
    return value


def _stage_workspace(plan_dir: Path, scratch: Path) -> Path:
    for name in REQUIRED_PLAN_FILES:
        if not (plan_dir / name).is_file():
            raise SystemExit(f"golden plan {plan_dir} is missing {name}")
    ws = scratch / "ws"
    shutil.copytree(
        ROOT, ws,
        ignore=lambda _d, names: [n for n in names if n in EXCLUDED_NAMES or n.endswith(".pyc") or n == "input"],
        dirs_exist_ok=True,
    )
    (ws / "input").mkdir()
    for f in sorted(plan_dir.iterdir()):
        if f.is_file():
            shutil.copy(f, ws / "input" / f.name)
    # The build reads the plan file (WP4.5: nothing bootstraps it from the CSVs any more); the
    # engine capture below still reads the CSV set through data_io.load_csv.
    subprocess.run(
        [sys.executable, "-c",
         "from src.active_plan import build_plan_file_from_csv_folder as b; b('plan.rpx', 'input')"],
        cwd=ws, check=True, capture_output=True, text=True,
    )
    # Same tree-relative imports the engine tests use.
    shutil.copytree(ROOT / "tests", ws / "tests", ignore=shutil.ignore_patterns("__pycache__", "e2e", "frontend", "fixtures"))
    return ws


def _env(ws: Path) -> dict:
    env = os.environ.copy()
    # Hermetic: drop knobs a parent test process may have set (conftest forces
    # OFFLINE pricing, which changes workbook wording vs. a plain CLI run).
    for k in [k for k in env if k.startswith(("RETIREMENT_SYSTEM_FORCE_", "RETIREMENT_MC_"))]:
        del env[k]
    env.update({
        "RETIREMENT_SYSTEM_WORKSPACE_ROOT": str(ws),
        "RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS": "1",
        "RETIREMENT_SYSTEM_APP_MODE": "LOCAL",
        "RETIREMENT_SYSTEM_WORKSPACE_ID": "local",
        "TAX_REFERENCE_YEAR": "2026",
        "RETIREMENT_MC_SIMS": "16",
        "RETIREMENT_MC_SENSITIVITY_SIMS": "3",
        "RETIREMENT_SKIP_REPORT_SIDECARS": "1",
        "RETIREMENT_SYSTEM_FROZEN_TODAY": FROZEN_TODAY,
        "PYTHONHASHSEED": "0",
    })
    return env


_ENGINE_WORKER = r"""
import json, sys
sys.path.insert(0, ".")
from tests.golden_pricing import frozen_holdings_prices
from src.data_io import load_csv
from src.report_compute import prepare_config_from_sectioned_data
from src.planning_engines import project
with frozen_holdings_prices():
    c = prepare_config_from_sectioned_data(load_csv("input/client_data.csv"), "", optimize_roth=True)
    rows = project(c)
from src import spending_tracker as st
spend = {
    "group_actuals": st.group_actuals(None, 2026),
    "core_actual": st.ytd_core_spending_actual(None, 2026),
    "by_tracking_type": st.ytd_actual_by_tracking_type(None, 2026),
    "hierarchy": st.ytd_spending_hierarchy(None, 2026),
    "n_transactions": len(st.load_transactions(None, 2026)),
}
json.dump({"rows": rows, "spending_ytd": spend}, open(sys.argv[1], "w"), default=str)
"""


def capture(plan: str) -> dict:
    plan_dir = PLAN_SOURCES[plan]
    with tempfile.TemporaryDirectory(prefix=f"golden_{plan}_") as tmp:
        scratch = Path(tmp)
        ws = _stage_workspace(plan_dir, scratch)
        env = _env(ws)
        rows_path = scratch / "rows.json"
        r = subprocess.run([sys.executable, "-c", _ENGINE_WORKER, str(rows_path)],
                           cwd=ws, env=env, text=True, capture_output=True, timeout=600)
        if r.returncode != 0:
            raise SystemExit(f"[{plan}] engine capture failed:\n{r.stdout}{r.stderr}")
        captured = json.loads(rows_path.read_text(encoding="utf-8"))
        r = subprocess.run([sys.executable, "tools/build_workbook.py"],
                           cwd=ws, env=env, text=True, capture_output=True, timeout=900)
        if r.returncode != 0:
            raise SystemExit(f"[{plan}] workbook build failed:\n{r.stdout}{r.stderr}")
        import openpyxl
        wb = openpyxl.load_workbook(ws / "output" / "retirement_plan.xlsx", data_only=True, read_only=True)
        required = json.loads(SNAPSHOT_FIXTURE.read_text(encoding="utf-8"))["required_sheets"]
        sheets = {}
        for name in required:
            if name not in wb.sheetnames:
                sheets[name] = None
                continue
            grid = [[_mask_build_date(_round(v) if not hasattr(v, "isoformat") else v.isoformat()) for v in row]
                    for row in wb[name].iter_rows(values_only=True)]
            while grid and all(v is None for v in grid[-1]):
                grid.pop()
            sheets[name] = grid
        # Release the read-only workbook handle: on Windows the open file blocks
        # TemporaryDirectory cleanup (WinError 32).
        wb.close()
        summary = _stored_summary(ws)
    return {
        "engine_rows": _round(captured["rows"]),
        "spending_ytd": _round(captured["spending_ytd"]),
        "workbook_sheets": sheets,
        # Every scalar in the build's stored KPI summary (build_id is per-run noise).
        "headline_kpis": {k: _round(v) for k, v in sorted(summary.items())
                          if k != "build_id" and isinstance(v, (int, float, str, bool, type(None)))},
        "plan_summary_keys": sorted(summary),
    }


def _stored_summary(ws: Path) -> dict:
    """The KPI summary the build stored in the workspace's plan file (``build_results``)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.stores import PlanStore

    with PlanStore.open(ws / "plan.rpx", create=False, readonly=True) as store:
        return store.build_results.get()["summary"]


def _baseline_path(plan: str) -> Path:
    return BASELINE_DIR / f"{plan}.json"


def diff(expected, actual, path="", out=None, limit=40):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(expected, dict) and isinstance(actual, dict):
        for k in sorted(set(expected) | set(actual)):
            if k not in expected:
                out.append(f"{path}/{k}: unexpected key")
            elif k not in actual:
                out.append(f"{path}/{k}: missing key")
            else:
                diff(expected[k], actual[k], f"{path}/{k}", out, limit)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            out.append(f"{path}: length {len(expected)} -> {len(actual)}")
        for i, (e, a) in enumerate(zip(expected, actual)):
            diff(e, a, f"{path}[{i}]", out, limit)
    elif expected != actual:
        out.append(f"{path}: {expected!r} -> {actual!r}")
    return out


def cmd_compare(plans) -> int:
    bad = 0
    for plan in plans:
        base = json.loads(_baseline_path(plan).read_text(encoding="utf-8"))
        problems = diff(base, json.loads(json.dumps(capture(plan))))
        print(f"[{plan}] {'OK' if not problems else 'DIFF'}")
        for p in problems:
            print("   ", p)
        bad += bool(problems)
    return 1 if bad else 0


def cmd_record(plans, reason: str) -> int:
    from tools.regen_full_row_snapshot import _validate_reason
    reason = _validate_reason(reason)
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    for plan in plans:
        _baseline_path(plan).write_text(
            json.dumps(capture(plan), indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Wrote {_baseline_path(plan).relative_to(ROOT)}")
    print(f"Reason: {reason}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("compare", "record"))
    ap.add_argument("--plan", choices=sorted(PLAN_SOURCES), action="append")
    ap.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    plans = a.plan or sorted(PLAN_SOURCES)
    sys.path.insert(0, str(ROOT))
    return cmd_compare(plans) if a.mode == "compare" else cmd_record(plans, a.reason)


if __name__ == "__main__":
    raise SystemExit(main())
