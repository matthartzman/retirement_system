"""Run the release gate: tests, sample projection validation, and package cleanliness."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# WI-005 / QA-002: the gate runs the pytest suite (not just unittest-style files)
# and refuses to pass if the collected count shrinks below this floor.
# Measured 2026-10-19: `pytest --collect-only -q -m "not nightly"` -> 4709
# collected (4800 total, 91 nightly deselected). The floor sits ~4% below that
# so ordinary churn does not trip it but a silently-shrinking suite does.
# Raise it when the suite grows; never lower it to make the gate pass.
MIN_COLLECTED_TESTS = 4500
# The repo's pyproject.toml defines `nightly` as run by the nightly workflow,
# not the PR/release tier. `slow` (real build pipeline) stays IN the gate.
PYTEST_MARKER_EXPR = 'not nightly'
_COLLECTED_RE = re.compile(r'(\d+)(?:/\d+)? tests? (?:collected|selected)')


def _remove_runtime_artifacts() -> None:
    for path in ROOT.rglob('__pycache__'):
        shutil.rmtree(path, ignore_errors=True)
    for pattern in ('*.pyc', '*.pyo'):
        for path in ROOT.rglob(pattern):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _run(args: list[str]) -> None:
    print('$ ' + ' '.join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def _pytest_base() -> list[str]:
    return [sys.executable, '-m', 'pytest', 'tests', '-m', PYTEST_MARKER_EXPR]


def _collected_count() -> int:
    """Return how many tests pytest collects for the gate's marker expression."""
    args = _pytest_base() + ['--collect-only', '-q', '-o', 'addopts=']
    print('$ ' + ' '.join(args))
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout + proc.stderr)
        raise SystemExit('pytest collection failed; release gate cannot count tests')
    match = _COLLECTED_RE.search(proc.stdout)
    if not match:
        raise SystemExit('Could not parse pytest collected-test count')
    return int(match.group(1))


def _run_pytest() -> None:
    count = _collected_count()
    print(f'pytest collected {count} tests (floor {MIN_COLLECTED_TESTS})')
    if count < MIN_COLLECTED_TESTS:
        raise SystemExit(
            f'Collected test count {count} is below the floor {MIN_COLLECTED_TESTS}; '
            'the suite shrank or collection is broken'
        )
    args = _pytest_base()
    if importlib.util.find_spec('xdist') is not None:
        args += ['-n', 'auto']
    _run(args)


def main() -> int:
    _remove_runtime_artifacts()
    _run([sys.executable, 'tools/generate_schema_coverage.py'])
    _run_pytest()
    _run([sys.executable, 'tools/check_version_surfaces.py'])
    _remove_runtime_artifacts()  # unittest imports create pycache; release packages must not.
    with tempfile.TemporaryDirectory(prefix='retirement_release_gate_') as tmp:
        package_check = Path(tmp) / 'release_gate_package_check.zip'
        _run([sys.executable, 'tools/build_release_package.py', '--output', str(package_check)])
        if not package_check.exists():
            raise SystemExit('Release package check did not produce an artifact')
    print('RELEASE GATE PASSED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
