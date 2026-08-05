"""Ensure the project root is importable as `src` regardless of how pytest is
invoked. Most test modules do `from src.xxx import yyy` with no sys.path setup
of their own, relying on `python -m pytest` adding the current working
directory to sys.path automatically. CI (and any bare `pytest` invocation)
does not get that for free, so this must run before test collection imports
any test module.
"""
import copy
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The committed, static, self-contained plan every test should load instead of
# the user's live input/. Kept in sync with test_199's FROZEN_TODAY.
_FROZEN_PLAN_DIR = ROOT / "tests" / "fixtures" / "sample_plan_frozen"
FROZEN_PLAN_TODAY = "2026-08-04"

# Absolute path to the staged plan-data directory for this test process.
# Tests that previously hardcoded `ROOT / "input"` should import this instead:
# it points at the frozen plan, not the live workspace.
TEST_INPUT_DIR: Path

# Redirect the app's writable workspace (input/, output/, local_state/,
# saved_plans/) to a throwaway copy for the whole test process. Some code path
# deeper in the load/save layer falls back to the default workspace root
# (src/platform_runtime.py workspace_root(), which defaults to the repo root)
# instead of an explicit path, so running certain tests together has silently
# overwritten the real input/client_data.json/.yaml/client_household.csv (SS
# claim ages, dropped keys) — see memory: pytest_mutates_input_files. This uses
# the RETIREMENT_SYSTEM_WORKSPACE_ROOT override, so every load/save path that
# resolves lazily via workspace_root() lands in the throwaway copy instead of
# the real client files, without needing to find/patch the actual culprit.
# setdefault-style: only redirect if the environment doesn't already override it.
if not os.environ.get("RETIREMENT_SYSTEM_WORKSPACE_ROOT"):
    import atexit
    import shutil
    import tempfile

    from src import platform_runtime as _platform_runtime

    _TEST_WORKSPACE_ROOT = Path(tempfile.mkdtemp(prefix="retirement_system_test_workspace_"))
    for _name in _platform_runtime.WORKSPACE_SUBDIRS:
        _src_dir = ROOT / _name
        # Only "input" needs real content copied in — it's the one directory
        # whose default-path fallback has been observed loading (and then
        # silently overwriting) the real client files. "local_state" in
        # particular can contain a live, locked webview cache on desktop that
        # copytree can't read; the other subdirs are write-only scratch space
        # for the app, so an empty throwaway directory is sufficient for them.
        if _name == "input":
            # Staged from the FROZEN FIXTURE, not the real input/. The live
            # workspace is a user's actual plan: it changes under us, it can be
            # blanked (a new plan starts with zero balances, which trips
            # plan_config's "zero starting account balances" guard), and any
            # test asserting dollar figures against it is really asserting
            # against whatever the user last saved. tests/fixtures/
            # sample_plan_frozen/ is a committed, static, self-contained plan --
            # the same one test_199 pins -- so every test that resolves through
            # workspace_root() now gets a known household instead.
            (_TEST_WORKSPACE_ROOT / _name).mkdir(parents=True, exist_ok=True)
            for _f in sorted(_FROZEN_PLAN_DIR.iterdir()):
                if _f.is_file():
                    shutil.copy(_f, _TEST_WORKSPACE_ROOT / _name / _f.name)
            # client_data.json/.yaml are DERIVED outputs (architecture: "CSV is
            # canonical"), not hand-maintained fixture inputs, so the frozen
            # fixture directory deliberately does not commit them -- generate
            # them here instead of staging a second, driftable copy. Any test
            # asserting against TEST_INPUT_DIR/client_data.json (e.g. a
            # forecast-API config-contract check) needs this present.
            from src.config_backend import export_client_json_yaml as _export_json_yaml
            _export_json_yaml(_TEST_WORKSPACE_ROOT / _name / "client_data.csv", _TEST_WORKSPACE_ROOT / _name)
        else:
            (_TEST_WORKSPACE_ROOT / _name).mkdir(parents=True, exist_ok=True)
    os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"] = str(_TEST_WORKSPACE_ROOT)
    # Pin the date too: plan_start derives from the current year and the YTD
    # blend prorates by day-of-year, so static inputs alone do not make a
    # projection reproducible. Tests needing a specific date override this.
    os.environ.setdefault("RETIREMENT_SYSTEM_FROZEN_TODAY", FROZEN_PLAN_TODAY)
    atexit.register(shutil.rmtree, _TEST_WORKSPACE_ROOT, ignore_errors=True)
    TEST_INPUT_DIR = _TEST_WORKSPACE_ROOT / "input"
else:
    # An outer harness already chose the workspace; honor it.
    TEST_INPUT_DIR = Path(os.environ["RETIREMENT_SYSTEM_WORKSPACE_ROOT"]) / "input"

def _install_real_input_write_guard() -> None:
    """Turn any write into the REAL (un-redirected) repo input/ directory into
    an immediate PermissionError with a full traceback at the offending call
    site, instead of only being caught after the fact by the session-end
    hash-diff warning below. A permanent sys.addaudithook (cannot be removed,
    which is fine -- it should be active for the life of every test process).
    See memory: pytest_mutates_input_files.
    """
    real_input_dir = (ROOT / "input").resolve()

    def _hook(event: str, args: tuple) -> None:
        if event == "open":
            path, mode = args[0], (args[1] or "")
            if not any(flag in str(mode) for flag in ("w", "a", "+", "x")):
                return
            try:
                target = Path(os.fsdecode(path)).resolve()
            except Exception:
                return
            if target == real_input_dir or real_input_dir in target.parents:
                raise PermissionError(
                    f"Blocked write to the REAL repo input/ during a test run: {target}. "
                    "Some code path resolved a path outside the redirected "
                    "RETIREMENT_SYSTEM_WORKSPACE_ROOT. See memory: pytest_mutates_input_files."
                )
        elif event in ("os.rename", "os.replace"):
            for raw in args[:2]:
                if raw is None:
                    continue
                try:
                    target = Path(os.fsdecode(raw)).resolve()
                except Exception:
                    continue
                if target == real_input_dir or real_input_dir in target.parents:
                    raise PermissionError(
                        f"Blocked rename/replace touching the REAL repo input/ during a "
                        f"test run: {target}. See memory: pytest_mutates_input_files."
                    )

    sys.addaudithook(_hook)


_install_real_input_write_guard()

# Pin holdings pricing to OFFLINE for the whole test run so projections are
# reproducible in CI. Without this, the active plan config requests LIVE
# pricing, so every golden-master run re-prices holdings against live market
# data (and rewrites output/market_price_cache.json), making dollar-total
# assertions drift by thousands between identical runs. OFFLINE routes every
# quote through the committed cache snapshot / holdings cost basis — no network,
# no cache mutation. Only the default provider that parse_client drives honors
# this; tests that build their own MarketDataProvider to exercise live/frozen
# behavior call the instance method directly and are unaffected. setdefault so
# a developer can still override (e.g. LIVE) for an intentional refresh.
os.environ.setdefault("RETIREMENT_SYSTEM_FORCE_PRICING_MODE", "OFFLINE")


# Prevent one test's live/cache-mode price fetch from leaking into another
# (nominally OFFLINE/FROZEN) test's financial-projection results via the
# process-wide MarketDataProvider singleton (src/market_data.py's
# _DEFAULT_PROVIDER). Its .cache dict is loaded once from disk at provider
# construction (module import) time and never reloaded afterward, and
# reset_runtime_state()/set_frozen_prices() never clear it - so a test that
# fetches a live/cached price mutates .cache for the rest of the whole pytest
# process, silently changing later tests' results depending on run order
# (observed: test_recommendations_regression.py's golden-master terminal net worth
# shifted ~$800k depending on whether an earlier test in the same file had
# called forecast_from_plan_json first). Snapshot the pristine on-disk cache
# once, then restore it before/after every test - mirrors the same pattern
# tests/test_market_data_module.py already uses for its own file, generalized
# to the whole suite.
import src.market_data as _market_data  # noqa: E402

_PRISTINE_PROVIDER_CACHE = copy.deepcopy(_market_data._DEFAULT_PROVIDER.cache)


@pytest.fixture(autouse=True)
def _reset_market_data_price_cache():
    _market_data._DEFAULT_PROVIDER.cache = copy.deepcopy(_PRISTINE_PROVIDER_CACHE)
    yield
    _market_data._DEFAULT_PROVIDER.cache = copy.deepcopy(_PRISTINE_PROVIDER_CACHE)
