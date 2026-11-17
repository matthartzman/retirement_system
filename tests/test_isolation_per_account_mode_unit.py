"""Argument handling and skip behaviour of the opt-in per-account isolation mode (no elevation needed)."""
from __future__ import annotations

from pathlib import Path

import pytest

import isolation_per_account as ipa

pytestmark = pytest.mark.unit


def test_default_is_same_account_and_unchanged():
    assert ipa.per_account_config({}) is None
    assert ipa.per_account_config({ipa.LAUNCHER_ENV: "same-account"}) is None
    cmd = ipa.gateway_command("py", Path("g.db"), Path("d"), Path("r.json"), public_origin="https://o", shared_key_env="K",
                              per_account=None)
    assert "--launcher" not in cmd and "--install-dir" not in cmd and "--account-prefix" not in cmd


def test_unknown_launcher_value_is_an_error_not_a_silent_default():
    with pytest.raises(ipa.PerAccountConfigError):
        ipa.per_account_config({ipa.LAUNCHER_ENV: "per_account"})


def test_per_account_without_elevation_skips(monkeypatch):
    monkeypatch.setattr(ipa, "elevated_allowed", lambda environ=None: False)
    with pytest.raises(pytest.skip.Exception):
        ipa.per_account_config({ipa.LAUNCHER_ENV: "per-account", ipa.INSTALL_ENV: "x", ipa.PYTHON_ENV: "y"})


def test_per_account_elevated_validates_install_dir_and_python(monkeypatch, tmp_path):
    monkeypatch.setattr(ipa, "elevated_allowed", lambda environ=None: True)
    env = {ipa.LAUNCHER_ENV: "per-account"}
    with pytest.raises(ipa.PerAccountConfigError):
        ipa.per_account_config(env)  # nothing given
    install = tmp_path / "app"
    (install / "src" / "gateway").mkdir(parents=True)
    py = tmp_path / "python.exe"
    env |= {ipa.INSTALL_ENV: str(install), ipa.PYTHON_ENV: str(py)}
    with pytest.raises(ipa.PerAccountConfigError):
        ipa.per_account_config(env)  # python missing
    py.write_text("")
    cfg = ipa.per_account_config(env)
    assert cfg == {"install_dir": install, "python": py}
    with pytest.raises(ipa.PerAccountConfigError):
        ipa.per_account_config(env | {ipa.INSTALL_ENV: str(tmp_path)})  # no src/gateway


def test_per_account_command_carries_the_installed_paths_and_test_prefix():
    per = {"install_dir": Path("C:/RetirementPlanner/app"), "python": Path("C:/RetirementPlanner/app/runtime/python.exe")}
    cmd = ipa.gateway_command(per["python"], Path("g.db"), Path("C:/rpwtest_ab/data"), Path("r.json"),
                              public_origin="https://o", shared_key_env="K", per_account=per)
    i = cmd.index("--launcher")
    assert cmd[i + 1] == "per-account"
    assert cmd[cmd.index("--account-prefix") + 1] == "rpwtest_"
    assert cmd[cmd.index("--install-dir") + 1] == str(per["install_dir"])
    assert cmd[cmd.index("--python") + 1] == str(per["python"])


def test_owner_data_and_state_folders_are_refused():
    for p in ("C:/RetirementPlanner/data", "C:/RetirementPlanner/data/users/1", "C:/RetirementPlanner/state"):
        with pytest.raises(ipa.PerAccountConfigError):
            ipa.assert_throwaway(Path(p))
    ipa.assert_throwaway(Path("C:/rpwtest_abc123/data"))


def test_diagnostics_are_copied_only_when_a_destination_is_set(tmp_path):
    box = tmp_path / "rpwtest_ab"
    (box / "gateway").mkdir(parents=True)
    (box / "gateway" / "gateway.log").write_text("gw")
    logs = box / "data" / "users" / "1" / "local_state" / "logs"
    logs.mkdir(parents=True)
    (logs / "worker_console.log").write_text("boom")
    ipa.save_diagnostics(box, box / "data", environ={})
    assert not (tmp_path / "diag").exists()
    ipa.save_diagnostics(box, box / "data", environ={ipa.DIAG_ENV: str(tmp_path / "diag")})
    saved = {p.name: p.read_text() for p in (tmp_path / "diag" / "rpwtest_ab").iterdir()}
    assert saved["gateway__gateway.log"] == "gw"
    assert saved["data__users__1__local_state__logs__worker_console.log"] == "boom"
