"""Paired-path scalar vs. vectorized Monte Carlo agreement (nightly).

The independent-sample gates (``test_monte_carlo_default_engine_mode``, the
survivor reconciliation test) compare two success rates that were each
estimated from DIFFERENT random draws (stdlib ``random`` vs. numpy), so their
difference carries ~2.4pp (n=800) to ~4.8pp (n=200) of pure sampling noise
before any engine bias shows up. This test removes that noise: it samples ONE
set of paths (death years, asset-class returns, inflation) with the vectorized
engine's own generators and feeds the identical paths to both engines --
``project()`` per path for the exact scalar engine, ``_mc_vectorized_projection``
for the vectorized one -- then compares path by path.

What it pins: the vectorized engine's headline ("funded as asked") funding
allocation replays the deterministic engine's per-bucket draws, sequesters the
credit-shelter trust at first death, and so tracks the exact scalar engine path
by path -- see documentation/archive/reports/N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md
for the decomposition that led here. Measured on the frozen sample plan (n=200,
seeds 11/5/3, survivor economics ON, wellness shocks off, 30-year horizon):
path agreement 95.5-100%, signed success-rate gap within +-3.5pp, for both
roth_policy none and fill_to_bracket (before the change: agreement 82-85% with
a +17pp gap under none, 91% with a -6pp gap under fill_to_bracket).

The floors below leave ~2.5 standard errors of margin at the default n=200.
"""

from __future__ import annotations

from tests.plan_fixture import plan_config
import os

import numpy as np
import pytest

from conftest import TEST_INPUT_DIR
from src import planning_engines as pe
from tests.paired_path_harness import _paired_success
from src.data_io import load_csv, parse_client

pytestmark = pytest.mark.nightly

N_PATHS = int(os.environ.get("RETIREMENT_PAIRED_PARITY_SIMS", "200"))
SEED = 11


def _config(roth_policy: str | None):
    c = plan_config()
    if roth_policy:
        c["roth_policy"] = roth_policy
    c["plan_end"] = int(c["plan_start"]) + 30
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c["mc_sims"] = N_PATHS
    return c


@pytest.fixture(scope="module", params=[("none", 0.90), (None, 0.90)], ids=["roth_none", "roth_fill_to_bracket"])
def paired(request):
    policy, floor = request.param
    scalar_ok, vec_ok = _paired_success(_config(policy), N_PATHS, SEED)
    return {"scalar": scalar_ok, "vec": vec_ok, "floor": floor}


def test_path_level_agreement_holds_the_measured_floor(paired):
    agree = float(np.mean(paired["scalar"] == paired["vec"]))
    assert agree >= paired["floor"], (
        f"paired-path scalar/vectorized agreement {agree:.3f} fell below the measured floor "
        f"{paired['floor']:.2f} (scalar success {paired['scalar'].mean():.3f}, vectorized "
        f"{paired['vec'].mean():.3f}); see N1_MC_PARITY_RESIDUAL_DIAGNOSTIC_2026-09-30.md"
    )


def test_success_rate_level_matches_scalar(paired):
    gap = abs(float(paired["vec"].mean()) - float(paired["scalar"].mean()))
    assert gap <= 0.06, (
        f"paired-path success-rate gap {gap:.3f} (scalar {paired['scalar'].mean():.3f}, "
        f"vectorized {paired['vec'].mean():.3f}) exceeds 6pp"
    )


def test_engines_see_the_same_paths(paired):
    # Sanity on the harness itself: identical inputs must give a non-degenerate
    # mix of outcomes in both engines, or agreement above would be vacuous.
    for key in ("scalar", "vec"):
        rate = float(paired[key].mean())
        assert 0.05 < rate < 0.98, f"{key} success rate {rate:.3f} is degenerate; paired harness broken"
