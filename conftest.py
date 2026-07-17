"""Shared pytest fixtures for the retirement planning test suite.

New tests should prefer these fixtures over redefining `ROOT`/`sample_config`
locally or reading the git-tracked `output/retirement_plan.xlsx` directly.
Existing test files are migrated incrementally; see
documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 5.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent


@pytest.fixture
def root() -> Path:
    return ROOT


@pytest.fixture
def sample_config():
    """Load the canonical sample Plan Data into an engine-ready config dict."""
    from src.data_io import load_csv, parse_client

    data = load_csv(ROOT / "input" / "client_data.csv")
    return parse_client(data, "")


@pytest.fixture(scope="session")
def built_workbook_dir(tmp_path_factory):
    """Build workbook/report artifacts once per test session into an isolated
    temp directory, instead of tests reading or mutating the git-tracked
    output/ folder in place.

    Live price providers are disabled and Monte Carlo path counts are reduced
    so the build stays fast and hermetic (no network calls) — callers that
    need to assert on Monte Carlo *values* should build separately with their
    own env vars rather than rely on this fixture's reduced sim counts.
    """
    out_dir = tmp_path_factory.mktemp("built_output")
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = str(out_dir)
    env["RETIREMENT_SYSTEM_APP_MODE"] = "LOCAL"
    env["RETIREMENT_SYSTEM_WORKSPACE_ID"] = "local"
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    # Optional modules are now gated: a module toggled off in the active plan
    # skips its computation and drops its workbook sheet.  This canonical build
    # force-enables the classic sheet-owning modules so the structural "all
    # sheets present" assertions (test_97/100/101/127, etc.) stay stable
    # regardless of saved toggles.  Newer default-off modules are intentionally
    # NOT force-enabled here so their sheets don't perturb those layouts.
    # Off-state behavior is covered by test_optional_module_gating.py.
    env["RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES"] = ",".join([
        "lifetime_tax_projection", "charts_dashboard", "retirement_strategy",
        "social_security_timing", "roth_conversion_plan", "charitable_giving",
        "state_residency", "estate_legacy_plan", "market_luck_stress_test",
        "what_if_analysis", "long_term_care_stress", "survivor_stress_test",
        "life_insurance_need", "rmd_audit", "glossary", "methodology_rerun",
    ])
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
    return out_dir


@pytest.fixture(scope="session")
def built_workbook_path(built_workbook_dir) -> Path:
    return built_workbook_dir / "retirement_plan.xlsx"
