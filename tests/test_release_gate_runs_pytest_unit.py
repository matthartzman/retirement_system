"""WI-005 / QA-002: the release gate must run pytest and enforce a collected-count floor."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import release_gate  # noqa: E402

pytestmark = pytest.mark.unit


def test_gate_source_invokes_pytest_not_only_unittest():
    src = (ROOT / 'tools' / 'release_gate.py').read_text(encoding='utf-8')
    assert "'pytest'" in src
    assert "'discover'" not in src


def test_gate_excludes_nightly_and_has_sane_floor():
    assert 'nightly' in release_gate.PYTEST_MARKER_EXPR
    assert release_gate.MIN_COLLECTED_TESTS >= 1000


def _fake_run(collected_out: str, calls: list):
    def run(args, **kw):
        calls.append(list(args))
        if '--collect-only' in args:
            return subprocess.CompletedProcess(args, 0, stdout=collected_out, stderr='')
        return subprocess.CompletedProcess(args, 0)
    return run


def test_gate_fails_when_collected_below_floor():
    calls: list = []
    out = f'{release_gate.MIN_COLLECTED_TESTS - 1}/5000 tests collected (1 deselected) in 1s\n'
    with mock.patch.object(release_gate.subprocess, 'run', _fake_run(out, calls)):
        with pytest.raises(SystemExit):
            release_gate._run_pytest()
    assert not any('--collect-only' not in c for c in calls)  # real run never started


def test_gate_runs_pytest_when_at_floor():
    calls: list = []
    out = f'{release_gate.MIN_COLLECTED_TESTS} tests collected in 1s\n'
    with mock.patch.object(release_gate.subprocess, 'run', _fake_run(out, calls)):
        release_gate._run_pytest()
    real = [c for c in calls if '--collect-only' not in c]
    assert len(real) == 1 and real[0][1:3] == ['-m', 'pytest']
    assert release_gate.PYTEST_MARKER_EXPR in real[0]
