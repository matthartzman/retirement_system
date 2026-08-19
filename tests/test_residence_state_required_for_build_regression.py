"""Ticket 291, Class 1: a missing or unsupported residence_state must BLOCK a
real build, not silently borrow Illinois' numbers.

Two layers, deliberately kept distinct -- do not merge them:

  - `src.core._require_supported_state` -- pre-existing (item 1.11), stays
    lenient on a BLANK state. That leniency is for low-level/defensive
    callers (partial snapshots, autosave backups) that were never a full
    build in the first place. `test_unsupported_state_preflight_regression.py`
    pins this and is NOT touched here.

  - `src.core.require_residence_state_for_build` -- new. The actual per-build
    gate: treats missing exactly like unsupported. Wired into both real build
    entry points in data_io.py (`parse_client`, `build_plan_from_json`'s flat
    path), right after `c['state']` is set and before any downstream engine
    code can read it.

This split only works because data_io.py no longer silently substitutes
'Illinois' for a blank residence_state (this same ticket's Class 1 fix) -- by
the time `require_residence_state_for_build` runs, blank genuinely means "the
field was never filled in", not "an incomplete snapshot got this far".
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FROZEN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"


def _staged_workspace(*, residence_state=None):
    """Copy the frozen fixture into a temp workspace, optionally overwriting
    residence_state in the staged client_household.csv. `residence_state=None`
    leaves the fixture's own value (Illinois) untouched."""
    workspace = Path(tempfile.mkdtemp(prefix="residence_state_test_"))
    (workspace / "input").mkdir(parents=True)
    for f in sorted(FROZEN_DIR.iterdir()):
        if f.is_file():
            shutil.copy(f, workspace / "input" / f.name)

    if residence_state is not None:
        household = workspace / "input" / "client_household.csv"
        text = household.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        out = []
        for line in lines:
            if line.startswith("Household,,residence_state,"):
                out.append(f"Household,,residence_state,{residence_state},,State tax and residency analysis,\n")
            else:
                out.append(line)
        household.write_text("".join(out), encoding="utf-8")

    return workspace


def _parse_from_workspace(workspace):
    from src.data_io import load_csv, parse_client

    prev_root = os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT")
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(workspace)
    try:
        data = load_csv(workspace / "input" / "client_data.csv")
        return parse_client(data, "")
    finally:
        if prev_root is None:
            os.environ.pop("RETIREMENT_SYSTEM_WORKSPACE_ROOT", None)
        else:
            os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = prev_root


# --------------------------------------------------------------------------
# require_residence_state_for_build -- unit level
# --------------------------------------------------------------------------


def test_blank_state_raises_and_names_the_field_and_page():
    from src.core import require_residence_state_for_build

    with pytest.raises(ValueError) as exc:
        require_residence_state_for_build("")
    message = str(exc.value)
    assert "residence_state" in message
    assert "State Residency" in message, "must point at the page where residency is set"


def test_blank_state_error_lists_supported_states():
    from src.core import require_residence_state_for_build, supported_states

    with pytest.raises(ValueError) as exc:
        require_residence_state_for_build(None)
    message = str(exc.value)
    for state in supported_states():
        assert state in message


def test_unsupported_state_still_raises_via_the_shared_message():
    from src.core import require_residence_state_for_build

    with pytest.raises(ValueError) as exc:
        require_residence_state_for_build("Minnesota")
    assert "Minnesota" in str(exc.value)


def test_supported_state_does_not_raise():
    from src.core import require_residence_state_for_build

    require_residence_state_for_build("Illinois")  # must not raise
    require_residence_state_for_build("Texas")


def test_existing_low_level_leniency_is_unaffected():
    """The pre-existing, deliberately-lenient function must still be exactly
    as lenient as before -- this ticket adds a new gate, it does not change
    the old one. Mirrors
    test_unsupported_state_preflight_regression.py::test_blank_state_still_falls_back_silently_not_bricked
    directly, so a regression here is caught in this file too, not only there.
    """
    from src.core import state_income_tax

    tax_blank = state_income_tax('', 100_000, 0, 0, 0, 0, 0, 2026)
    tax_illinois = state_income_tax('Illinois', 100_000, 0, 0, 0, 0, 0, 2026)
    assert tax_blank == pytest.approx(tax_illinois)


# --------------------------------------------------------------------------
# Real build entry points -- integration level, against the frozen fixture
# --------------------------------------------------------------------------


def test_parse_client_blocks_a_real_build_with_blank_residence_state():
    workspace = _staged_workspace(residence_state="")
    try:
        with pytest.raises(ValueError) as exc:
            _parse_from_workspace(workspace)
        assert "residence_state" in str(exc.value)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_parse_client_blocks_a_real_build_with_unsupported_residence_state():
    workspace = _staged_workspace(residence_state="Minnesota")
    try:
        with pytest.raises(ValueError) as exc:
            _parse_from_workspace(workspace)
        assert "Minnesota" in str(exc.value)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_parse_client_still_builds_normally_for_the_frozen_illinois_household():
    """The frozen fixture is an Illinois resident and must build exactly as
    before -- this is the golden-master safety check for this ticket at unit-
    test speed, ahead of the full frozen golden-master suite."""
    workspace = _staged_workspace()  # unmodified: Illinois, per the fixture
    try:
        c = _parse_from_workspace(workspace)
        assert c["state"] == "Illinois"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_build_plan_from_json_flat_path_blocks_missing_state():
    from src.data_io import build_plan_from_json

    plan = {
        "members": [{"name": "You", "dob_year": 1965, "retirement_year": 2030, "mortality_age": 90}],
        # no "state" key at all
    }
    with pytest.raises(ValueError) as exc:
        build_plan_from_json(plan, "")
    assert "residence_state" in str(exc.value)


def test_build_plan_from_json_flat_path_accepts_a_supported_state():
    """A supported state must not be what stops this plan from building.
    (The flat wizard schema still requires account balances to build a full
    engine config -- unrelated to this ticket -- so this asserts the
    residence_state gate specifically passes, rather than asserting the
    whole build succeeds on a deliberately minimal, account-less plan.)"""
    from src.data_io import build_plan_from_json

    plan = {
        "members": [{"name": "You", "dob_year": 1965, "retirement_year": 2030, "mortality_age": 90}],
        "state": "Texas",
    }
    with pytest.raises(ValueError) as exc:
        build_plan_from_json(plan, "")
    assert "residence_state" not in str(exc.value)
    assert "Texas" not in str(exc.value), "a supported state must not itself be flagged as a problem"
