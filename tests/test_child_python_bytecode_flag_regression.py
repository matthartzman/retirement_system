from __future__ import annotations
"""Child Python processes inherit "do not write bytecode" from their parent.

Multi-user workers run as ``python -E -s -B ...``. ``-B`` is not inherited by a
child started with ``sys.executable`` and ``-E`` makes the child ignore
``PYTHONDONTWRITEBYTECODE``, so the workbook build (and the price refresh /
drift tools) used to write ``__pycache__`` folders into the install. The owner's
per-account isolation run found them, owned by a throwaway worker account, in a
test copy whose folder the workers could write.

The parent's flag cannot be faked in-process (``sys.flags`` is read-only), so
these tests start a real interpreter with and without ``-B`` and look at what it
builds and what its children actually do.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from src import platform_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_python(flags: list[str], code: str, *args: str) -> str:
    # -E so PYTHONDONTWRITEBYTECODE in the test runner's environment cannot stand in for -B,
    # exactly as in a worker; with -E and -c, sys.path[0] is the cwd, so `src` imports.
    proc = subprocess.run(
        [sys.executable, "-E", *flags, "-c", code, *args],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip().splitlines()[-1]


_ARGV_PROBE = textwrap.dedent("""
    import json
    from src.platform_runtime import python_child_argv
    print(json.dumps([python_child_argv("job.py"), python_child_argv("job.py", unbuffered=True)]))
""")


@pytest.mark.parametrize("parent_flags, expected_flags", [(["-B"], ["-B"]), ([], [])])
def test_child_argv_carries_dont_write_bytecode_only_when_the_parent_has_it(parent_flags, expected_flags):
    plain, unbuffered = json.loads(_run_python(parent_flags, _ARGV_PROBE))
    assert plain[1:] == [*expected_flags, "job.py"]
    assert unbuffered[1:] == [*expected_flags, "-u", "job.py"]


def test_frozen_executable_gets_the_script_alone(monkeypatch):
    monkeypatch.setattr(platform_runtime.sys, "frozen", True, raising=False)
    assert platform_runtime.python_child_argv("job.py", unbuffered=True) == [sys.executable, "job.py"]


# Each fake child imports a sibling module (what would be compiled into __pycache__)
# and records whether it was started with dont_write_bytecode.
_FAKE_CHILD = textwrap.dedent("""
    import sys
    from pathlib import Path
    import _probe_dep  # noqa: F401
    Path(__file__).with_suffix(".flag").write_text(str(int(sys.flags.dont_write_bytecode)))
    print("{}")
""")

_LAUNCH_ALL = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    base = Path(sys.argv[1])
    from src.server_services import build_job_service, build_service, pricing_service, portfolio_service
    from financial_trends_reporter import trends_job

    registry = build_job_service.BuildJobRegistry()
    registry.create("job", created_at=time.time())
    build_job_service.run_build_progress_job(
        registry=registry, job_id="job", workspace_id="local", client_id="local", env={},
        output_dir=base / "output", build_script=base / "build" / "build_workbook.py", base_dir=base,
        previous_build_ts=0.0, build_start_ts=time.time(), timeout_seconds=60, redact_logs=False,
        admin_changes_between=lambda *a: [], write_last_build_metadata=lambda *a: None,
        redact_text=lambda t: t, interpret_build_result=build_service.interpret_build_result)
    kw = dict(base_dir=base, output_dir=base / "output", app_db=base / "app.db", max_build_seconds=60)
    pricing_service.refresh_prices(**kw)
    portfolio_service.drift_payload(**kw)
    (base / "tools" / "refresh_prices.flag").rename(base / "tools" / "service_refresh_prices.flag")
    trends_job.refresh_prices(base, timeout=60)
    print("done")
""")

_CHILDREN = ["build/build_workbook", "tools/service_refresh_prices", "tools/analyze_drift", "tools/refresh_prices"]


@pytest.mark.parametrize("parent_flags, expect_no_bytecode", [(["-B"], True), ([], False)])
def test_children_of_a_worker_shaped_parent_follow_its_bytecode_flag(tmp_path, parent_flags, expect_no_bytecode):
    base = tmp_path / "install"
    for folder, scripts in (("build", ["build_workbook.py"]), ("tools", ["refresh_prices.py", "analyze_drift.py"])):
        (base / folder).mkdir(parents=True)
        (base / folder / "_probe_dep.py").write_text("VALUE = 1\n", encoding="utf-8")
        for name in scripts:
            (base / folder / name).write_text(_FAKE_CHILD, encoding="utf-8")
    (base / "output").mkdir()

    assert _run_python(parent_flags, _LAUNCH_ALL, str(base)) == "done"

    flags = {name: (base / f"{name}.flag").read_text(encoding="utf-8") for name in _CHILDREN}
    assert flags == {name: str(int(expect_no_bytecode)) for name in _CHILDREN}
    caches = sorted(p.relative_to(base).as_posix() for p in base.rglob("__pycache__"))
    assert caches == ([] if expect_no_bytecode else ["build/__pycache__", "tools/__pycache__"])
