"""Regression guard for a real workspace-isolation bug (2026-08-20).

holdings_service.py's read/save functions for holdings, liabilities, and the
HSA schedule all call workspace_context.workspace_file(name, workspace_id,
base_dir, ...) directly. That function's own docstring is explicit: when a
caller passes `root`/`base_dir` explicitly, that value wins outright over
platform_runtime.workspace_root() -- the whole point of RETIREMENT_SYSTEM_WORKSPACE_ROOT.

src/server/workbook_routes.py's six route handlers for these three CSVs
(GET/POST holdings, GET/POST liabilities, GET/POST hsa-schedule) plus the
holdings-import preview were passing `base_dir=BASE_DIR` -- BASE_DIR is
Path(__file__).resolve().parents[2], the real package directory, computed
once at import time and NEVER redirected. Under a redirected workspace (any
isolated/test/multi-workspace session), a save through these routes silently
wrote into the REAL, unredirected package's own input/ directory instead of
the active workspace's -- discovered when verifying the HSA optimizer UI:
a schedule save through an isolated verification server actually landed in
this repo's own real input/client_hsa_schedule.csv.

This is the exact same bug class as the one already documented and fixed at
workbook_routes.py's _run_build (search "Found via the Playwright E2E build
journey" in that file) -- this was a second, unfixed instance of it.

Two layers of guard, matching this repo's own established convention (see
test_plan_data_budget_service_extraction_functional.py for the same
source-text-assertion pattern used for the same class of route-wiring bug):

1. Source-text: every one of the seven call sites must reference
   WORKSPACE_ROOT, never BASE_DIR, for these three CSVs specifically.
2. Functional: holdings_service's own functions, called directly with two
   different base_dir values, must write to the exact directory passed --
   proving the underlying function contract holds, so a future caller wiring
   itself correctly gets correct behavior.
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

ROUTES_FILE = Path("src/server/workbook_routes.py")


def _route_source() -> str:
    return ROUTES_FILE.read_text(encoding="utf-8")


# Each entry: the exact function call substring, anchored enough that it
# cannot match an unrelated call. Deliberately checks base_dir=WORKSPACE_ROOT
# is present rather than merely checking base_dir=BASE_DIR is absent -- the
# latter would pass if a call site were rewritten to omit base_dir entirely,
# which would raise a TypeError, not silently break isolation the way this
# bug did. Presence of the correct positive is the real guard.
_EXPECTED_CALLS = [
    "holdings_service.read_holdings(base_dir=WORKSPACE_ROOT,",
    "holdings_service.save_holdings(content=content, base_dir=WORKSPACE_ROOT,",
    "holdings_service.read_liabilities(base_dir=WORKSPACE_ROOT,",
    "holdings_service.save_liabilities(content=content, base_dir=WORKSPACE_ROOT,",
    "holdings_service.read_hsa_schedule(base_dir=WORKSPACE_ROOT,",
    "holdings_service.save_hsa_schedule(content=content, base_dir=WORKSPACE_ROOT,",
]


@pytest.mark.parametrize("expected_call", _EXPECTED_CALLS, ids=lambda c: c.split("(")[0])
def test_holdings_liabilities_hsa_schedule_routes_use_workspace_root(expected_call):
    routes = _route_source()
    assert expected_call in routes, (
        f"{expected_call!r} not found in {ROUTES_FILE} -- if this route was "
        "rewritten, confirm it still passes base_dir=WORKSPACE_ROOT (not "
        "BASE_DIR) so a redirected/isolated workspace's save/read cannot leak "
        "into the real, unredirected package directory."
    )


def test_holdings_import_preview_also_reads_via_workspace_root():
    """The preview endpoint has its own extra read_holdings call, easy to
    miss since it is not one of the six GET/POST pairs above."""
    routes = _route_source()
    assert "current = holdings_service.read_holdings(base_dir=WORKSPACE_ROOT," in routes


def test_no_remaining_base_dir_equals_base_dir_for_these_three_services():
    """The specific failure mode: BASE_DIR passed where WORKSPACE_ROOT was
    needed, for exactly these three service modules' calls. Scoped to lines
    naming holdings_service.* / *_hsa_schedule / *_liabilities so this does
    not false-positive on _run_build's base_dir=BASE_DIR, which is correct
    and already documented as such in this same file.
    """
    routes = _route_source()
    offenders = [
        line for line in routes.splitlines()
        if re.search(r"holdings_service\.(read|save)_(holdings|liabilities|hsa_schedule)\(", line)
        and "base_dir=BASE_DIR" in line
    ]
    assert not offenders, f"Found base_dir=BASE_DIR reintroduced in: {offenders}"


def test_workspace_root_is_imported_in_workbook_routes():
    routes = _route_source()
    assert re.search(r"^\s*WORKSPACE_ROOT,\s*$", routes, re.MULTILINE), (
        "WORKSPACE_ROOT must be imported from .app_core for the calls above "
        "to resolve at all."
    )


# ---------------------------------------------------------------------------
# Functional layer (WP6): the three datasets are tables of the ACTIVE PLAN FILE, so
# isolation is by plan file. A save lands in the active plan only, a read sees only the
# active plan, and switching the active plan (Load / demo swap) switches the data.
# ---------------------------------------------------------------------------

_CONTENT = {
    "holdings": "account,symbol,shares\nA_IRA,VTI,1\n",
    "liabilities": "liability_id,type,balance\nL1,auto,5000\n",
    "hsa_schedule": "year,optimizer_amount,override_amount,locked,note\n2026,,999,FALSE,\n",
}


@pytest.mark.parametrize("name", ["holdings", "liabilities", "hsa_schedule"])
def test_save_and_read_follow_the_active_plan_file(tmp_path, monkeypatch, name):
    import src.server_services.holdings_service as holdings_service
    from src.active_plan import PLAN_DB_ENV

    plan_a, plan_b = tmp_path / "a.rpx", tmp_path / "b.rpx"
    kw = dict(base_dir=tmp_path, workspace_id="ws1", client_id="c1", db_path=tmp_path / "x.sqlite")
    save_fn, read_fn = getattr(holdings_service, f"save_{name}"), getattr(holdings_service, f"read_{name}")

    monkeypatch.setenv(PLAN_DB_ENV, str(plan_a))
    assert save_fn(content=_CONTENT[name], user_id="u1", **kw)["success"] is True
    assert _CONTENT[name].splitlines()[1].split(",")[0] in read_fn(**kw)["content"]  # key cell of the saved row

    monkeypatch.setenv(PLAN_DB_ENV, str(plan_b))  # another plan: nothing of plan A's leaks in
    assert read_fn(**kw)["source"] == "empty_template"
    assert not (tmp_path / "input").exists()  # and no workspace file was written

    monkeypatch.setenv(PLAN_DB_ENV, str(plan_a))
    assert read_fn(**kw)["source"] == "plan_file"
