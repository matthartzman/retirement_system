"""SEC-03: ``acl setup`` refuses up front, before it changes any folder, when a user folder has files and the caller did
not say the workers are stopped (the data-root and users-folder resets recurse into every user folder)."""
from __future__ import annotations

import pytest

from src.gateway import acl

SID = "S-1-5-18"


@pytest.fixture
def calls(monkeypatch):
    seen: list[tuple] = []
    for name in ("lock_gateway_only", "lock_user_folder", "lock_install_readonly"):
        monkeypatch.setattr(acl, name, lambda *a, _n=name, **k: seen.append((_n, a[0] if a else None)))
    monkeypatch.setattr(acl, "check_layout", lambda **k: [])
    return seen


def _setup(root, *extra):
    return acl.main(["setup", "--data-root", str(root), "--gateway-sid", SID, *extra])


def test_user_folders_with_content_ignores_empty_folders_and_a_missing_users_dir(tmp_path):
    assert acl.user_folders_with_content(tmp_path / "data") == []  # first install: nothing there yet
    (tmp_path / "data" / "users" / "1").mkdir(parents=True)
    (tmp_path / "data" / "users" / "2").mkdir()
    (tmp_path / "data" / "users" / "2" / "plan.rpx").write_bytes(b"x")
    (tmp_path / "data" / "users" / "stray.txt").write_text("not a folder")
    assert [d.name for d in acl.user_folders_with_content(tmp_path / "data")] == ["2"]


def test_setup_refuses_before_touching_anything_when_a_user_folder_has_files(tmp_path, calls, capsys):
    root = tmp_path / "data"
    (root / "users" / "1").mkdir(parents=True)
    (root / "users" / "1" / "plan.rpx").write_bytes(b"x")
    assert _setup(root) == 2
    assert calls == []  # not even the data root was re-locked
    err = capsys.readouterr().err
    assert "workers may be running" in err and "--workers-stopped" in err and "Nothing was changed" in err


def test_setup_runs_with_the_flag_and_on_a_first_install(tmp_path, calls):
    root = tmp_path / "data"
    (root / "users" / "1").mkdir(parents=True)
    (root / "users" / "1" / "plan.rpx").write_bytes(b"x")
    assert _setup(root, "--workers-stopped") == 0 and calls  # the operator says the service is stopped
    calls.clear()
    fresh = tmp_path / "fresh"
    (fresh / "users" / "1").mkdir(parents=True)  # empty user folders only: nothing to race with
    assert _setup(fresh) == 0 and calls
