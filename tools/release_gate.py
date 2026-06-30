"""Run the release gate: tests, sample projection validation, and package cleanliness."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def main() -> int:
    _remove_runtime_artifacts()
    _run([sys.executable, 'tools/generate_schema_coverage.py'])
    _run([sys.executable, 'tools/check_plan_data_sync.py', '--write'])
    _run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
    _run([sys.executable, 'tools/check_version_surfaces.py'])
    _run([sys.executable, 'tools/check_plan_data_sync.py'])
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
