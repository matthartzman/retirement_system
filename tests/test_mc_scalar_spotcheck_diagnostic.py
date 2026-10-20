"""WI-009: scalar spot-check diagnostic field and tolerance-label policy table."""
from __future__ import annotations

import re
from pathlib import Path

from tests.plan_fixture import plan_config
from src import planning_engines as pe

ROOT = Path(__file__).resolve().parents[1]


def _cfg(**kw):
    c = plan_config()
    c["plan_end"] = int(c["plan_start"]) + 30
    c["mc_sensitivity_sims"] = 1
    c["mc_wellness_shocks"] = False
    c.update(kw)
    return c


def test_spotcheck_not_run_by_default():
    mc = pe.monte_carlo(_cfg(), n_sims=20, seed=3)
    assert mc["scalar_spotcheck"]["status"] == "not_run"


def test_spotcheck_reports_signed_gap_when_enabled():
    mc = pe.monte_carlo(_cfg(mc_scalar_spotcheck_n=6, roth_policy="none"), n_sims=20, seed=3)
    sc = mc["scalar_spotcheck"]
    assert sc["status"] == "run" and sc["n_paths"] == 6 and sc["roth_policy"] == "none"
    expected = (sc["vectorized_success_rate"] - sc["scalar_success_rate"]) * 100.0
    assert abs(sc["signed_gap_pp"] - expected) < 1e-9
    assert 0.0 <= sc["path_agreement"] <= 1.0
    assert sc["policy_tolerance_demonstrated"] == ("none" in pe.MC_PARITY_DEMONSTRATED_POLICIES)


def test_policy_demonstration_flag_follows_table():
    mc = pe.monte_carlo(_cfg(roth_policy="fixed_dollar"), n_sims=20, seed=3)
    assert mc["mc_parity_policy_demonstrated"] is False


def test_frontend_policy_table_matches_python():
    js = (ROOT / "frontend/js/dashboard_decomp_home_panels.js").read_text(encoding="utf-8")
    m = re.search(r"MC_TOLERANCE_DEMONSTRATED_POLICIES\s*=\s*\[(.*?)\]", js, re.S)
    assert m
    names = set(re.findall(r"[\"']([a-z_]+)[\"']", m.group(1)))
    assert names == set(pe.MC_PARITY_DEMONSTRATED_POLICIES)
