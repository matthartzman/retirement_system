"""Optional-module gating: a module toggled off must run no logic, build no
sheet, and leave the workbook layout coherent (no dangling section dividers).

The canonical `built_workbook_*` fixtures force every module ON, so this module
builds its own workbook with a deterministic set of modules forced OFF via
RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES.
"""
import os
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Whole of section 3 (Risk & Stress Tests) plus a couple of System/Optimizer
# sheets, so we can assert both sheet removal and empty-section pruning.
FORCED_OFF = [
    "market_luck_stress_test",   # 3A. Monte Carlo
    "survivor_stress_test",      # 3B. Survivor
    "long_term_care_stress",     # 3C. (LTC half)
    "life_insurance_need",       # 3C. (Life Insurance half)
    "glossary",                  # 4G. Glossary
    "state_residency",           # 2C. State Residency
]


def _sheet_names(xlsx_path: Path):
    ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(xlsx_path) as zf:
        root = ET.fromstring(zf.read("xl/workbook.xml"))
    return [s.attrib["name"] for s in root.find("a:sheets", ns)]


@pytest.fixture(scope="module")
def gated_build(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("gated_output")
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = str(out_dir)
    env["RETIREMENT_SYSTEM_APP_MODE"] = "LOCAL"
    env["RETIREMENT_SYSTEM_WORKSPACE_ID"] = "local"
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    env["RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"] = ",".join(FORCED_OFF)
    env.pop("RETIREMENT_SYSTEM_FORCE_ALL_MODULES", None)
    env.setdefault("RETIREMENT_MC_SIMS", "16")
    env.setdefault("RETIREMENT_MC_SENSITIVITY_SIMS", "3")
    result = subprocess.run(
        [sys.executable, "tools/build_workbook.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return out_dir, result.stdout + result.stderr


@pytest.mark.slow
def test_build_succeeds_with_modules_off(gated_build):
    out_dir, _ = gated_build
    assert (out_dir / "retirement_plan.xlsx").exists()
    # Nothing breaks: the PDF and in-app dashboard are still produced.
    assert (out_dir / "retirement_plan.pdf").exists()
    assert (out_dir / "retirement_dashboard.html").exists()


@pytest.mark.slow
def test_disabled_module_sheets_are_absent(gated_build):
    out_dir, _ = gated_build
    names = _sheet_names(out_dir / "retirement_plan.xlsx")
    for gone in ["3A. Monte Carlo", "3B. Survivor", "3C. LTC + Life Insurance",
                 "4G. Glossary", "2C. State Residency"]:
        assert gone not in names, f"{gone} should be gated out but was present"
    # Core, always-on sheets remain.
    for present in ["1A. Executive Summary", "1C. Cash Flow", "2B. Asset Allocation",
                    "4A. Plan Data", "4D. Quality Control"]:
        assert present in names, f"{present} is core and must always be present"


@pytest.mark.slow
def test_empty_section_divider_is_dropped(gated_build):
    out_dir, _ = gated_build
    names = _sheet_names(out_dir / "retirement_plan.xlsx")
    # Every sheet under "3. Risk & Stress Tests" is disabled, so its divider is
    # dropped entirely; the sections whose sheets survive stay.
    assert "3. Risk & Stress Tests" not in names
    assert "1. Reports" in names
    assert "2. Optimizers" in names
    assert "4. System" in names


@pytest.mark.slow
def test_monte_carlo_is_not_run(gated_build):
    _, log = gated_build
    assert "Monte Carlo disabled" in log


def test_nav_gating_source_covers_monte_carlo():
    # The reported bug: Monte Carlo had no nav gate. §7.4 moved nav-step
    # gating out of dashboard.js's hand-listed optionalFunctionEnabled(...)
    # calls into module_catalog.step_gate_map(), server-declared and consumed
    # via moduleGates.step_gates (see dashboard.js's gateModule lookup at the
    # STEPS array). Confirm the mapping still exists at its new source.
    from src.module_catalog import step_gate_map

    gates = step_gate_map()
    assert gates.get("monte_carlo_options") == "market_luck_stress_test"
    assert gates.get("survivor_stress") == "survivor_stress_test"
    assert gates.get("scenarios") == "what_if_analysis"

    js = (ROOT / "frontend" / "js" / "dashboard.js").read_text(encoding="utf-8")
    assert "moduleGates.step_gates" in js, "dashboard.js must still consume the server-declared step gates"


def test_registry_covers_every_optional_sheet_module():
    from src.reporting.workbook_common import OPTIONAL_MODULE_SHEETS
    # Guardrail: the modules that own a workbook sheet are all registered.
    for key in ["market_luck_stress_test", "survivor_stress_test", "long_term_care_stress",
                "life_insurance_need", "glossary", "methodology_rerun", "rmd_audit",
                "state_residency", "charitable_giving", "roth_conversion_plan"]:
        assert key in OPTIONAL_MODULE_SHEETS
