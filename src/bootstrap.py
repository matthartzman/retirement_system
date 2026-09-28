"""Shared startup sequence for every launch path (system review 2026-09-25,
Wave 0 item WI-000, closing ARC-002).

Before this module existed, the same local-mode environment-variable
defaults were maintained in three separately-drifting copies --
``main.py``'s own ``_set_local_mode_defaults``, ``tools/launchers/
START_DESKTOP.py``'s inline ``os.environ.setdefault`` calls, and
``src/desktop_api.py``'s own ``_set_local_mode_defaults`` (which already
omitted ``CONFIG_FILE``/``OUTPUT_DIR``/``JSON_CONFIG_FILE``/
``YAML_CONFIG_FILE`` relative to the other two) -- and the at-rest Plan Data
migration (``run_startup_plan_data_migration``) ran only from ``main.py``,
so launching via the desktop shortcut or ``START_APP.bat`` (which both run
``START_DESKTOP.py``, not ``main.py`` -- see ``launchers/START_APP.bat`` and
``launchers/CREATE_DESKTOP_SHORTCUT.vbs``) never migrated legacy flat
category ids in budget/rules/alias files.

``main.py``, ``tools/launchers/START_DESKTOP.py`` and
``DesktopApi.__init__`` all call :func:`run_startup_bootstrap` now, so every
launch path sets the same env defaults and runs the same migration. The
module-level :data:`_BOOTSTRAPPED` guard makes a second call in the same
process a no-op for the migration half (env defaults are themselves
idempotent via ``setdefault``) -- necessary because ``main.py``'s desktop
mode calls this, then ``src.desktop_app.start()`` constructs a
``DesktopApi``, which calls it again.
"""
from __future__ import annotations

import os

_BOOTSTRAPPED = False

# Local-mode env defaults every launch path needs. Order matches main.py's
# pre-fix _set_local_mode_defaults (the most complete of the three prior
# copies).
_LOCAL_MODE_ENV_DEFAULTS = {
    "RETIREMENT_SYSTEM_APP_MODE": "LOCAL",
    "RETIREMENT_SYSTEM_WORKSPACE_ID": "local",
    "RETIREMENT_SYSTEM_CLIENT_ID": "local",
    "RETIREMENT_SYSTEM_DASHBOARD_HOST": "127.0.0.1",
    "RETIREMENT_SYSTEM_DASHBOARD_PORT": "5050",
    "RETIREMENT_SYSTEM_REQUIRE_API_TOKEN": "NO",
    "RETIREMENT_SYSTEM_ALLOW_UNAUTHENTICATED_SAAS": "YES",
    "RETIREMENT_SYSTEM_FORCE_HTTPS": "NO",
    "RETIREMENT_SYSTEM_REVERSE_PROXY_ENABLED": "NO",
    "RETIREMENT_SYSTEM_PUBLIC_BASE_URL": "",
    "RETIREMENT_SYSTEM_CONFIG_FILE": "input/client_data.csv",
    "RETIREMENT_SYSTEM_JSON_CONFIG_FILE": "input/client_data.json",
    "RETIREMENT_SYSTEM_YAML_CONFIG_FILE": "input/client_data.yaml",
    "RETIREMENT_SYSTEM_OUTPUT_DIR": "output",
}


def set_local_mode_env_defaults() -> None:
    """Set every local-mode env var this package needs, without overriding
    a value the environment (or an earlier caller) already set.
    """
    for key, value in _LOCAL_MODE_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)


def run_startup_bootstrap(*, run_migration: bool = True) -> dict:
    """Set local-mode env defaults and, once per process, run the at-rest
    Plan Data migration.

    Safe to call from every launch path: env defaults are idempotent via
    ``setdefault``, and the migration itself is designed to be idempotent
    (ARC-002's stated dependency) but is still guarded here to never run
    twice in one process (main.py's desktop mode calls this directly, then
    ``src.desktop_app.start()`` constructs a ``DesktopApi``, which calls it
    again).

    Deliberately NOT wired into the frozen exe's script-runner branch
    (``main.py``'s module-level dispatch, before this function would ever
    be reached): that path runs ``tools/build_workbook.py`` in a subprocess,
    and a build has no business rewriting plan data at rest.

    Returns the migration result dict (``run_startup_plan_data_migration``'s
    own return shape), or ``{"migrated": [], "total_changed": 0,
    "already_ran": True}`` if the migration was skipped because it already
    ran this process, or ``run_migration=False`` was passed.
    """
    global _BOOTSTRAPPED
    set_local_mode_env_defaults()
    if not run_migration or _BOOTSTRAPPED:
        return {"migrated": [], "total_changed": 0, "already_ran": _BOOTSTRAPPED}
    _BOOTSTRAPPED = True
    from src.plan_data_migration import run_startup_plan_data_migration  # noqa: PLC0415
    return run_startup_plan_data_migration()
