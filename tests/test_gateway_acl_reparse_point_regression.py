"""``icacls FOLDER/* /reset /T`` follows a junction a worker planted in its own folder and resets the permissions
of the target (reproduced against a hardened file). Applying the layout must remove links first."""
from __future__ import annotations

import os
import subprocess

import pytest

from src.gateway import acl, winapi

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.name != "nt", reason="Windows-only")]


def test_applying_a_user_folder_does_not_reset_the_permissions_behind_a_junction(tmp_path):
    import _winapi  # noqa: PLC0415

    me = winapi.current_user_sid()
    victim = tmp_path / "victim"
    victim.mkdir()
    secret = victim / "key.bin"
    secret.write_bytes(b"k")
    subprocess.run(["icacls", str(secret), "/inheritance:r", "/grant:r", f"*{me}:(F)"], capture_output=True, check=True)
    before = subprocess.run(["icacls", str(secret)], capture_output=True, text=True).stdout
    folder = tmp_path / "users" / "1"
    (folder / "sub").mkdir(parents=True)
    (folder / "plan.rpx").write_bytes(b"a")
    _winapi.CreateJunction(str(victim), str(folder / "sub" / "link"))
    try:
        acl.lock_user_folder(folder, account_sid="S-1-5-32-559", gateway_sid=me)
        after = subprocess.run(["icacls", str(secret)], capture_output=True, text=True).stdout
        assert after == before, "the permissions of a file behind a junction were rewritten"
        assert secret.read_bytes() == b"k"
        assert not (folder / "sub" / "link").exists(), "the planted junction was left in place"
    finally:
        subprocess.run(["icacls", str(tmp_path), "/reset", "/T", "/C", "/Q"], capture_output=True)
