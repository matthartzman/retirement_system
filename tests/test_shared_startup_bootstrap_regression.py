"""Finding ARC-002 (system review 2026-09-25, Wave 0 item WI-000):
the local-mode environment-variable defaults were maintained in three
separately-drifting copies (main.py, tools/launchers/START_DESKTOP.py,
src/desktop_api.py -- the last already missing
CONFIG_FILE/OUTPUT_DIR/JSON_CONFIG_FILE/YAML_CONFIG_FILE relative to the
other two), and the at-rest Plan Data migration ran only from main.py --
so launching via the desktop shortcut or START_APP.bat (both of which run
START_DESKTOP.py, not main.py) never migrated legacy flat category ids in
budget/rules/alias files.

This pins that all three launch paths now reach the one shared
src/bootstrap.py function, that it sets every env default, and that it runs
the migration at most once per process.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

import src.bootstrap as bootstrap

ROOT = Path(__file__).resolve().parents[1]

_EXPECTED_ENV_DEFAULTS = (
    "RETIREMENT_SYSTEM_APP_MODE",
    "RETIREMENT_SYSTEM_WORKSPACE_ID",
    "RETIREMENT_SYSTEM_CLIENT_ID",
    "RETIREMENT_SYSTEM_DASHBOARD_HOST",
    "RETIREMENT_SYSTEM_DASHBOARD_PORT",
    "RETIREMENT_SYSTEM_REQUIRE_API_TOKEN",
    "RETIREMENT_SYSTEM_ALLOW_UNAUTHENTICATED_SAAS",
    "RETIREMENT_SYSTEM_FORCE_HTTPS",
    "RETIREMENT_SYSTEM_REVERSE_PROXY_ENABLED",
    "RETIREMENT_SYSTEM_PUBLIC_BASE_URL",
    "RETIREMENT_SYSTEM_CONFIG_FILE",
    "RETIREMENT_SYSTEM_JSON_CONFIG_FILE",
    "RETIREMENT_SYSTEM_YAML_CONFIG_FILE",
    "RETIREMENT_SYSTEM_OUTPUT_DIR",
)


@pytest.fixture
def _clean_env(monkeypatch):
    for key in _EXPECTED_ENV_DEFAULTS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(bootstrap, "_BOOTSTRAPPED", False)
    yield


def test_set_local_mode_env_defaults_sets_every_expected_key(_clean_env):
    bootstrap.set_local_mode_env_defaults()
    for key in _EXPECTED_ENV_DEFAULTS:
        # RETIREMENT_SYSTEM_PUBLIC_BASE_URL legitimately defaults to "" --
        # check presence, not truthiness.
        assert key in os.environ, f"{key} was not defaulted"


def test_set_local_mode_env_defaults_does_not_override_an_existing_value(_clean_env, monkeypatch):
    monkeypatch.setenv("RETIREMENT_SYSTEM_DASHBOARD_PORT", "9999")
    bootstrap.set_local_mode_env_defaults()
    assert os.environ["RETIREMENT_SYSTEM_DASHBOARD_PORT"] == "9999"


def test_run_startup_bootstrap_runs_the_migration_at_most_once_per_process(_clean_env):
    fake_result = {"migrated": ["client_data.csv"], "total_changed": 1}
    with mock.patch(
        "src.plan_data_migration.run_startup_plan_data_migration",
        return_value=fake_result,
    ) as fake_migrate:
        first = bootstrap.run_startup_bootstrap()
        second = bootstrap.run_startup_bootstrap()

    fake_migrate.assert_called_once()
    assert first == fake_result
    assert second.get("already_ran") is True
    assert second["total_changed"] == 0


def test_run_startup_bootstrap_can_skip_the_migration_explicitly(_clean_env):
    with mock.patch(
        "src.plan_data_migration.run_startup_plan_data_migration",
    ) as fake_migrate:
        result = bootstrap.run_startup_bootstrap(run_migration=False)

    fake_migrate.assert_not_called()
    assert result["total_changed"] == 0
    for key in _EXPECTED_ENV_DEFAULTS:
        assert key in os.environ, f"{key} was not defaulted even with run_migration=False"


@pytest.mark.parametrize("launcher_path", [
    "main.py",
    "tools/launchers/START_DESKTOP.py",
    "src/desktop_api.py",
])
def test_every_launch_path_reaches_the_shared_bootstrap(launcher_path):
    text = (ROOT / launcher_path).read_text(encoding="utf-8")
    assert "run_startup_bootstrap" in text, (
        f"{launcher_path} no longer calls the shared bootstrap -- "
        "it will drift from the other launch paths again"
    )
