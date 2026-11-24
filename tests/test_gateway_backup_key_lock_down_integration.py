"""SEC-08: the REAL icacls lock-down of a rewritten backup key, against a real temp folder.

``write_keyring_file`` gives the new key file exactly Administrators (full) and SYSTEM (read), then renames it into
place from the same process. The caller can do that only while its token has the Administrators entry enabled: an
elevated shell, SYSTEM, or a GitHub-hosted Windows runner (administrator, UAC off). A normal desktop session runs the
same account with a filtered token (Administrators is "deny only"): it loses the file the moment icacls has run, and
``os.replace`` fails with WinError 5. The code must then fail closed: the old key stays and no temp file is left behind.

test_gateway_backup_key_rotation_functional.py replaces icacls with a fake so it gives the same answer everywhere. This
file runs it for real and asserts the contract that applies to the token it runs under, instead of skipping (QA-006).
"""
from __future__ import annotations

import sys

import pytest

from src.gateway import backup_crypto as bc
from src.gateway import key_acl


def _caller_survives_the_lock_down() -> bool:
    """True where the caller can still rename the file after icacls: off Windows (nothing is locked down), or with the
    Administrators entry enabled in the token (an elevated shell, SYSTEM, the CI runner)."""
    if sys.platform != "win32":
        return True
    from src.gateway import winapi  # noqa: PLC0415

    return winapi.is_admin()


def _rewrite(path) -> None:
    bc.write_keyring_file(path, bc.read_key_file(path), protect=lambda data: b"SEALED:" + data)  # real icacls


def test_the_real_lock_down_lets_an_elevated_caller_finish_and_makes_any_other_caller_fail_closed(tmp_path):
    f = tmp_path / "backup.key"
    old = bc.write_key_file(f)
    if _caller_survives_the_lock_down():
        _rewrite(f)
        assert bc.is_sealed(f) and not (tmp_path / "backup.key.new").exists()
        assert key_acl.key_file_findings(f) == []  # the real DACL: SYSTEM, Administrators and the owner only
    else:
        with pytest.raises(OSError):
            _rewrite(f)
        assert bytes(bc.read_key_file(f)) == bytes(old) and not bc.is_sealed(f)  # the protected key was not replaced
        assert not (tmp_path / "backup.key.new").exists()  # and no locked-down temp file is left behind
