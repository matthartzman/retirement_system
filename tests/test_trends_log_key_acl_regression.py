"""The trend-log key file's Windows ACL must stay readable to SYSTEM and Administrators (``acl setup`` reads every DACL)."""
from __future__ import annotations

import subprocess

from financial_trends_reporter import trends_log


def test_key_file_acl_grants_owner_plus_system_and_administrators_read(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    class _Proc:
        returncode = 0

        def communicate(self, timeout=None):
            return (None, None)

    def fake_popen(cmd, **_kw):
        calls.append(list(cmd))
        return _Proc()

    monkeypatch.setattr(trends_log.sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    key = tmp_path / "k"
    trends_log._restrict_key_file(key)
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[:2] == ["icacls", str(key)] and "/inheritance:r" in cmd
    grants = cmd[cmd.index("/grant:r") + 1:]
    assert grants[0].endswith(":F")
    assert grants[1:] == ["*S-1-5-32-544:R", "*S-1-5-18:R"]
