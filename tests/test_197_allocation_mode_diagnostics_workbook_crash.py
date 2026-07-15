"""Regression test for a live production bug (item 191): building the
workbook with allocation_selection_mode set to a mode that doesn't use
risk-tolerance/glide-path inputs (tangency, and now real_loss_aware) crashed
with KeyError: 'years_to_retirement' inside build_sheet4's "Allocation
Policy Inputs" section (src/reporting/sheets_summary.py), which assumed
every mode's diagnostics dict carries the full risk-tolerance-mode key set
(years_to_retirement, stability_factor, glide_path_mode).

Root-caused and fixed two ways:
  1. compute_optimal_allocation's tangency and real_loss_aware branches now
     include years_to_retirement/stability_factor/glide_path_mode in their
     diagnostics (the underlying values are already computed upstream of
     the mode branch; they just weren't being surfaced).
  2. sheets_summary.py's Allocation Policy Inputs section now reads these
     fields via .get() with fallbacks instead of direct [] subscripting, as
     a safety net against any future mode with a slimmer diagnostics shape.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

import src.allocation_policy as ap
import src.optimization as opt
from src.data_io import load_csv, parse_client
from src.planning_engines import project
from src.reporting.sheets_summary import build_sheet4

ROOT = Path(__file__).resolve().parents[1]


def sample_config():
    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


@pytest.mark.parametrize("mode", [
    ap.ALLOCATION_MODE_USER,
    ap.ALLOCATION_MODE_OPTIMIZER,
    ap.ALLOCATION_MODE_MAX_SHARPE,
    ap.ALLOCATION_MODE_TANGENCY,
    ap.ALLOCATION_MODE_REAL_LOSS_AWARE,
])
def test_compute_optimal_allocation_diagnostics_has_full_key_set_for_every_mode(mode):
    c = sample_config()
    out = opt.compute_optimal_allocation(c, force_mode=mode)
    diag = out["diagnostics"]
    for key in ("years_to_retirement", "stability_factor", "glide_path_mode", "withdrawal_rate", "inflation_sensitive_pct"):
        assert key in diag, f"mode {mode} is missing diagnostics key {key!r}"


@pytest.mark.parametrize("mode", [
    ap.ALLOCATION_MODE_USER,
    ap.ALLOCATION_MODE_OPTIMIZER,
    ap.ALLOCATION_MODE_MAX_SHARPE,
    ap.ALLOCATION_MODE_TANGENCY,
    ap.ALLOCATION_MODE_REAL_LOSS_AWARE,
])
def test_build_sheet4_does_not_raise_for_every_allocation_mode(mode):
    c = sample_config()
    c["allocation_selection_mode"] = mode
    rows = project(c)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "4. Asset Allocation"
    build_sheet4(ws, c, rows)  # must not raise KeyError
