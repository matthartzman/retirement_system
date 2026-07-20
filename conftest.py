"""Shared pytest fixtures for the retirement planning test suite.

New tests should prefer these fixtures over redefining `ROOT`/`sample_config`
locally or reading the git-tracked `output/retirement_plan.xlsx` directly.
Existing test files are migrated incrementally; see
documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 5.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import warnings
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


def _hash_input_dir() -> dict[str, str]:
    """Content hash of every file under input/, keyed by relative path.

    Deliberately does not assert input/ is CLEAN at session start (it may
    already carry the user's own uncommitted edits, which is not this
    fixture's business) -- only that it does not change FURTHER while the
    test session runs. See memory: pytest_mutates_input_files.
    """
    input_dir = ROOT / "input"
    if not input_dir.exists():
        return {}
    out = {}
    for f in sorted(input_dir.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(input_dir))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


@pytest.fixture(scope="session", autouse=True)
def _warn_if_input_dir_mutated_during_session():
    """Session-wide guardrail, not a per-test fixture: most tests should be
    fully isolated from input/ via tests/conftest.py's workspace redirect,
    but that redirect only takes effect for code paths that resolve files
    through workspace_context.candidate_input_files(). Code that reads
    input/ via a hardcoded ROOT-relative path (as at least one path in
    src/data_io.py's parse_client does for client_holdings.csv -- see
    tests/test_199_frozen_sample_plan_golden_master.py's docstring) bypasses
    that redirect entirely. This is a warn-only tripwire for exactly that
    gap: it cannot tell WHICH test mutated input/, but it will say the
    session as a whole did, which the previous behaviour (silence) did not.
    """
    before = _hash_input_dir()
    yield
    after = _hash_input_dir()
    if before != after:
        changed = sorted(set(before) ^ set(after)) or sorted(
            k for k in before if before[k] != after.get(k)
        )
        warnings.warn(
            f"input/ changed during this test session: {changed}. "
            "Some test read input/ through a path that bypasses the "
            "workspace-root redirect in tests/conftest.py. See memory: "
            "pytest_mutates_input_files.",
            UserWarning,
        )
