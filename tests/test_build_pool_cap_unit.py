"""The per-build process pool cap the multi-user gateway sets; unset keeps today's cpu_count - 1."""
from __future__ import annotations

import pytest

from src.reporting import sheets_strategy

pytestmark = pytest.mark.unit


@pytest.fixture
def cpus(monkeypatch):
    monkeypatch.setattr(sheets_strategy.os, "cpu_count", lambda: 12)


@pytest.mark.parametrize("value,expected", [(None, 11), ("", 11), ("4", 4), ("1", 1), ("0", 11), ("-3", 11),
                                            ("abc", 11), ("64", 11), (" 5 ", 5)])
def test_pool_size_cap(cpus, monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(sheets_strategy.BUILD_POOL_MAX_ENV, raising=False)
    else:
        monkeypatch.setenv(sheets_strategy.BUILD_POOL_MAX_ENV, value)
    assert sheets_strategy._pool_size_cap() == expected


def test_the_cap_reaches_the_build_through_the_scrubbed_environment(monkeypatch):
    from src import remote_mode

    monkeypatch.setenv("RETIREMENT_SYSTEM_REMOTE_MODE", "1")
    env = remote_mode.subprocess_env({sheets_strategy.BUILD_POOL_MAX_ENV: "4", "RETIREMENT_SYSTEM_SERVER_API_TOKEN": "t"})
    assert env == {sheets_strategy.BUILD_POOL_MAX_ENV: "4"}
