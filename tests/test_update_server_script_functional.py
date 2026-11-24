"""The one-step server update: tools/update_server.ps1 and its desktop shortcut."""
from __future__ import annotations

import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "update_server.ps1"
UPGRADE = ROOT / "tools" / "upgrade_installed_server.ps1"
INSTALLER = ROOT / "tools" / "INSTALL_DESKTOP_ICON.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_the_script_updates_the_checkout_safely_before_upgrading():
    s = _text(SCRIPT)
    # part A refuses rather than guesses: main only, no tracked changes, fast-forward only
    assert 'rev-parse --abbrev-ref HEAD' in s and '-ne "main"' in s
    assert "status --porcelain --untracked-files=no" in s
    assert "merge --ff-only origin/main" in s
    assert "reset --hard" not in s and "checkout -f" not in s and "git pull" not in s
    # the checkout is updated BEFORE the upgrade script runs, so the script that runs is the new one
    assert s.index("merge --ff-only origin/main") < s.index('& "$repo\\tools\\upgrade_installed_server.ps1"')


def test_the_script_runs_the_repos_upgrade_in_the_same_window_and_then_checks():
    s = _text(SCRIPT)
    assert 'upgrade_installed_server.ps1" -Elevated' in s  # no second elevation prompt, same console
    for check in ("service status", "SCHEMA_VERSION", "key check", "ops health", "5065/api/auth/session", "ALL CHECKS PASSED"):
        assert check in s, check
    assert s.index('& "$repo\\tools\\upgrade_installed_server.ps1"') < s.index("== C. Checks")


def test_the_script_uses_the_same_install_locations_as_the_upgrade_script():
    s, u = _text(SCRIPT), _text(UPGRADE)
    for literal in ('C:\\RetirementPlanner\\app', 'C:\\RetirementPlanner\\state'):
        assert literal in s and literal in u
    assert "-Elevated" in u  # the switch this script passes exists on the upgrade script


def test_the_installer_creates_an_update_shortcut_that_runs_the_script_through_powershell(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0))
    runpy.run_path(str(INSTALLER))
    commands = [c[-1] for c in calls if c and c[0] == "powershell" and c[-2] == "-Command"]
    update = [c for c in commands if "Update Retirement Server" in c]
    assert len(update) == 1
    assert "TargetPath = 'powershell.exe'" in update[0]
    assert "-File" in update[0] and "update_server.ps1" in update[0] and "-ExecutionPolicy Bypass" in update[0]
    # the existing shortcuts are still made
    assert any("Retirement Planner Admin" in c for c in commands)
