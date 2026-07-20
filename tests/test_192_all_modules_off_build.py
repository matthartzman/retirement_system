"""Item 192 (system review, Addendum A): prove a workbook build survives every
optional-module configuration, not just the two the rest of the suite already
covers.

`conftest.built_workbook_dir` force-enables 16 of the 24 registered optional
modules and leaves the rest untouched — deliberately, per its own comment, so
the structural "which sheets exist" assertions in test_97/100/101/127 stay
stable. That is a reasonable reason to exclude them from THAT fixture, but it
also means the 8 newer "Phase 1 advanced planning" modules (education_529,
existing_life_insurance, disability_income_insurance, property_casualty_umbrella,
business_succession, equity_compensation, special_needs_planning) plus
divorce_qdro had never been built together with everything else, and no test
enumerated the module list programmatically to guarantee new modules get
built-tested automatically as they're added.

This file closes both gaps:
  * every optional module OFF at once (the explicit ask)
  * every optional module ON at once, including the 8 the canonical fixture skips
  * each optional module OFF individually, all others ON — a regression here
    means some other module's builder assumes a sheet exists unconditionally
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _all_optional_modules() -> list[str]:
    """Enumerate registered optional modules from the catalog rather than a
    hand-maintained list, so a newly added module is swept automatically."""
    import src.module_catalog as mc
    return mc.optional_keys()


def _run_build(tmp_path_factory, *, env_overrides: dict[str, str], label: str):
    out_dir = tmp_path_factory.mktemp(f"m192_{label}")
    env = os.environ.copy()
    env["RETIREMENT_SYSTEM_OUTPUT_DIR"] = str(out_dir)
    env["RETIREMENT_SYSTEM_APP_MODE"] = "LOCAL"
    env["RETIREMENT_SYSTEM_WORKSPACE_ID"] = "local"
    env["RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS"] = "1"
    env.setdefault("RETIREMENT_MC_SIMS", "16")
    env.setdefault("RETIREMENT_MC_SENSITIVITY_SIMS", "3")
    # Never let a leftover FORCE_* from the surrounding shell contaminate a run.
    for k in ("RETIREMENT_SYSTEM_FORCE_ALL_MODULES",
              "RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES",
              "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES"):
        env.pop(k, None)
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "tools/build_workbook.py"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=180,
    )
    return out_dir, result


def _assert_core_artifacts(out_dir: Path, result, label: str):
    tail = (result.stdout + result.stderr)[-4000:]
    assert result.returncode == 0, f"{label} build failed:\n{tail}"
    assert (out_dir / "retirement_plan.xlsx").exists(), f"{label}: workbook missing"
    assert (out_dir / "retirement_plan.pdf").exists(), f"{label}: PDF missing"
    assert (out_dir / "retirement_dashboard.html").exists(), f"{label}: HTML dashboard missing"
    html = (out_dir / "retirement_dashboard.html").read_text(encoding="utf-8")
    assert len(html) > 1000, f"{label}: HTML dashboard suspiciously small ({len(html)} chars)"


def test_build_succeeds_with_every_optional_module_off(tmp_path_factory):
    """The explicit ask: turn off all optional modules, build, and confirm the
    result is a real, non-empty workbook/PDF/HTML set rather than a crash.

    Regression pin: charts_dashboard off used to raise
    ``KeyError('Workbook charts sheet not found...')`` out of
    ``_find_workbook_charts_sheet``, because ``build_html_dashboard`` assumed
    the hidden chart-data helper sheet always exists. It is optional and is
    not built when charts_dashboard is off. Fixed by returning ``None`` and
    falling back to deriving series from the projection rows directly.
    """
    modules = _all_optional_modules()
    out_dir, result = _run_build(
        tmp_path_factory,
        env_overrides={"RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": ",".join(modules)},
        label="all_off",
    )
    _assert_core_artifacts(out_dir, result, "all-off")


def test_build_succeeds_with_every_optional_module_on(tmp_path_factory):
    """The complementary extreme: every registered optional module on at once,
    including the 7 advanced-planning modules and divorce_qdro that
    conftest's canonical fixture deliberately excludes. Never previously
    built together."""
    out_dir, result = _run_build(
        tmp_path_factory,
        env_overrides={"RETIREMENT_SYSTEM_FORCE_ALL_MODULES": "1"},
        label="all_on",
    )
    _assert_core_artifacts(out_dir, result, "all-on")


@pytest.mark.parametrize("module_key", _all_optional_modules())
def test_build_succeeds_with_single_module_off(tmp_path_factory, module_key):
    """Sweep: each optional module off individually, everything else on.

    Catches a builder that references another module's sheet unconditionally
    (a cross-sheet formula, a nav index, a PDF section) instead of checking
    whether that module is actually enabled.
    """
    out_dir, result = _run_build(
        tmp_path_factory,
        env_overrides={
            "RETIREMENT_SYSTEM_FORCE_ALL_MODULES": "1",
            "RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES": module_key,
        },
        label=f"off_{module_key}",
    )
    _assert_core_artifacts(out_dir, result, f"{module_key}-off")


def test_optional_keys_registry_is_the_single_source_of_truth():
    """Guardrail for this file itself: if module_catalog gains or loses an
    optional module, the sweep above changes size automatically on the next
    collection. This just pins that the registry is non-empty and stable in
    shape, so a catalog import failure doesn't silently collapse the sweep to
    zero parametrizations."""
    modules = _all_optional_modules()
    assert len(modules) >= 20, (
        f"Expected at least 20 registered optional modules, found {len(modules)}: {modules}. "
        "If modules were intentionally removed, this floor can move down; if this is "
        "unexpected, module_catalog.optional_keys() may be returning an empty/partial set."
    )
    assert len(modules) == len(set(modules)), "Duplicate keys in optional_keys()"
