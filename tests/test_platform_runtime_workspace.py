from __future__ import annotations
"""Phase 0 (Android groundwork): platform_runtime roots, capabilities, and the
workspace-root override that redirects all writable data off the package root.
"""

import importlib
import os
from pathlib import Path

import pytest

import src.platform_runtime as platform_runtime


@pytest.fixture(autouse=True)
def _clear_platform_env(monkeypatch):
    for name in (
        platform_runtime.WORKSPACE_ROOT_ENV,
        platform_runtime.PLATFORM_ENV,
        platform_runtime.BUILD_MODE_ENV,
        platform_runtime.NO_AUTO_OPEN_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def test_defaults_are_byte_identical_to_package_root():
    # With no override, the writable tree is the package tree: desktop behavior
    # is unchanged.
    assert platform_runtime.workspace_root() == platform_runtime.package_root()
    assert not platform_runtime.is_mobile()
    assert platform_runtime.can_subprocess() is True
    assert platform_runtime.can_open_browser() is True
    assert platform_runtime.build_mode() == "subprocess"


def test_workspace_root_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path))
    assert platform_runtime.workspace_root() == tmp_path
    # package_root is unaffected — code/reference assets stay put.
    assert platform_runtime.package_root() != tmp_path
    assert platform_runtime.workspace_subdir("output") == tmp_path / "output"


def test_resolve_workspace_path_relative_and_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path))
    assert platform_runtime.resolve_workspace_path("local_state/db.sqlite") == tmp_path / "local_state" / "db.sqlite"
    absolute = tmp_path / "elsewhere" / "x.db"
    assert platform_runtime.resolve_workspace_path(absolute) == absolute


def test_ensure_workspace_dirs_creates_standard_subdirs(monkeypatch, tmp_path):
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path))
    root = platform_runtime.ensure_workspace_dirs()
    assert root == tmp_path
    for name in platform_runtime.WORKSPACE_SUBDIRS:
        assert (tmp_path / name).is_dir()


def test_mobile_platform_disables_subprocess_and_browser(monkeypatch):
    monkeypatch.setenv(platform_runtime.PLATFORM_ENV, "android")
    assert platform_runtime.is_mobile() is True
    assert platform_runtime.can_subprocess() is False
    assert platform_runtime.can_open_browser() is False
    # A mobile host must build in-process (no second interpreter available).
    assert platform_runtime.build_mode() == "inprocess"


def test_no_auto_open_flag_suppresses_browser(monkeypatch):
    monkeypatch.setenv(platform_runtime.NO_AUTO_OPEN_ENV, "1")
    assert platform_runtime.can_open_browser() is False
    # ...but suppressing auto-open does not force in-process builds on desktop.
    assert platform_runtime.build_mode() == "subprocess"


def test_build_mode_env_override(monkeypatch):
    monkeypatch.setenv(platform_runtime.BUILD_MODE_ENV, "inprocess")
    assert platform_runtime.build_mode() == "inprocess"
    monkeypatch.setenv(platform_runtime.BUILD_MODE_ENV, "subprocess")
    assert platform_runtime.build_mode() == "subprocess"


def test_capabilities_snapshot_shape():
    caps = platform_runtime.capabilities()
    for key in ("platform", "is_mobile", "is_frozen", "package_root", "workspace_root", "can_subprocess", "can_open_browser", "build_mode"):
        assert key in caps


def test_writable_root_modules_follow_override(monkeypatch, tmp_path):
    """config_backend and local_store resolve their DB under the workspace root.

    They read the override at import time (matching a shell-launched process), so
    reload them with the env set and confirm the writable paths track it while
    the code root does not.
    """
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path))
    import src.config_backend as config_backend
    import src.local_store as local_store

    config_backend = importlib.reload(config_backend)
    local_store = importlib.reload(local_store)
    try:
        assert Path(config_backend.DEFAULT_DB) == tmp_path / "local_state" / "retirement_system_v10.db"
        assert Path(config_backend.DEFAULT_CSV) == tmp_path / "input" / "client_data.csv"
        assert Path(local_store.DEFAULT_DB) == tmp_path / "local_state" / "retirement_system_v10.db"
        # Code root is unchanged.
        assert Path(config_backend.PROJECT_ROOT) == platform_runtime.package_root()
    finally:
        # Restore module state to the default workspace for other tests.
        monkeypatch.delenv(platform_runtime.WORKSPACE_ROOT_ENV, raising=False)
        importlib.reload(config_backend)
        importlib.reload(local_store)


def test_workspace_context_helpers_follow_override(monkeypatch, tmp_path):
    monkeypatch.setenv(platform_runtime.WORKSPACE_ROOT_ENV, str(tmp_path))
    import src.workspace_context as workspace_context

    # These helpers resolve lazily, so no reload is needed.
    assert workspace_context.workspace_output_dir() == tmp_path / "output"
    assert workspace_context.workspace_file("client_data.csv") == tmp_path / "input" / "client_data.csv"
    # An explicit root still wins (server routes pass their package BASE_DIR).
    explicit = Path("/opt/pkg")
    assert workspace_context.workspace_file("x.csv", root=explicit) == explicit / "input" / "x.csv"
