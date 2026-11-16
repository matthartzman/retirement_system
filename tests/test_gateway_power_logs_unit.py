"""No-sleep policy (never applied without confirmation, reversible) and worker log housekeeping."""
from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace

import pytest

from src.gateway import logs, power

pytestmark = pytest.mark.unit

QUERY = "  Power Setting GUID: 29f6c1db\n    Current AC Power Setting Index: 0x{:08x}\n    Current DC Power Setting Index: 0x00000258\n"


class FakePowercfg:
    def __init__(self, standby=1800, hibernate=3600, fail=False):
        self.vals = {"STANDBYIDLE": standby, "HIBERNATEIDLE": hibernate}
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        if argv[1] == "/q":
            return SimpleNamespace(stdout=QUERY.format(self.vals[argv[4]]), returncode=0)
        if self.fail:
            return SimpleNamespace(stdout="", returncode=1)
        flag, minutes = argv[2], int(argv[3])
        self.vals["STANDBYIDLE" if flag.startswith("standby") else "HIBERNATEIDLE"] = minutes * 60
        return SimpleNamespace(stdout="", returncode=0)


def test_parse_and_show_policy():
    assert power.parse_ac_seconds(QUERY.format(0x708)) == 1800
    assert power.parse_ac_seconds("garbage") is None
    assert power.sleeps(power.read_policy(FakePowercfg())) is True
    assert power.sleeps({"standby": 0, "hibernate": 0}) is False


def test_apply_needs_confirmation_and_changes_nothing_without_it(tmp_path):
    fake = FakePowercfg()
    with pytest.raises(power.PowerError, match="approval"):
        power.apply_policy(tmp_path / "state.json", confirmed=False, run=fake)
    assert not any(c[1] == "/change" for c in fake.calls) and not (tmp_path / "state.json").exists()


def test_apply_then_revert_restores_the_original_values_even_after_two_applies(tmp_path):
    fake, state = FakePowercfg(standby=1800, hibernate=3600), tmp_path / "before.json"
    res = power.apply_policy(state, confirmed=True, run=fake)
    assert res["before"] == {"standby": 1800, "hibernate": 3600} and res["after"] == {"standby": 0, "hibernate": 0}
    power.apply_policy(state, confirmed=True, run=fake)  # second apply must not overwrite the saved original
    assert json.loads(state.read_text()) == {"standby": 1800, "hibernate": 3600}
    power.revert_policy(state, confirmed=True, run=fake)
    assert power.read_policy(fake) == {"standby": 1800, "hibernate": 3600} and not state.exists()


def test_refused_powercfg_and_missing_state_are_errors(tmp_path):
    with pytest.raises(power.PowerError, match="elevated"):
        power.apply_policy(tmp_path / "s.json", confirmed=True, run=FakePowercfg(fail=True))
    with pytest.raises(power.PowerError, match="no saved"):
        power.revert_policy(tmp_path / "none.json", confirmed=True, run=FakePowercfg())


def _user_log(root, uid, size, age_days=0.0, rotated=False):
    f = root / "users" / str(uid) / logs.CONSOLE_LOG
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x" * size)
    if rotated:
        old = f.with_name(f.name + ".1")
        old.write_bytes(b"old")
        past = time.time() - age_days * 86400
        os.utime(old, (past, past))
    return f


def test_housekeeping_trims_only_stopped_workers_and_drops_stale_rotated_logs(tmp_path):
    big_stopped = _user_log(tmp_path, 1, 3000, rotated=True, age_days=30)
    big_running = _user_log(tmp_path, 2, 3000, rotated=True, age_days=30)
    small = _user_log(tmp_path, 3, 10)
    res = logs.prune_worker_logs(tmp_path, lambda uid: uid == 2, max_bytes=1000)
    assert res == {"trimmed": 1, "removed": 1}
    assert big_stopped.stat().st_size < 1000 and big_stopped.read_bytes().startswith(b"[older output trimmed")
    assert not big_stopped.with_name("worker_console.log.1").exists()
    assert big_running.stat().st_size == 3000 and big_running.with_name("worker_console.log.1").exists()
    assert small.stat().st_size == 10


def test_housekeeping_ignores_a_missing_root_and_non_user_folders(tmp_path):
    assert logs.prune_worker_logs(tmp_path / "nope", lambda u: False) == {"trimmed": 0, "removed": 0}
    (tmp_path / "users" / "notanumber").mkdir(parents=True)
    assert logs.prune_worker_logs(tmp_path, lambda u: False)["trimmed"] == 0
