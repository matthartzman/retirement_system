"""The worker's parent check must not read 'access denied' as 'parent gone' (per-account workers under a SYSTEM gateway)."""
from __future__ import annotations

import ctypes
import os

import pytest

from src import remote_worker

pytestmark = [pytest.mark.unit, pytest.mark.skipif(os.name != "nt", reason="Windows process handles")]


def _class(monkeypatch):
    # OpenProcess is called as an attribute with .restype set first; give it a settable callable.
    class Fn:
        def __init__(self, ret):
            self.ret, self.restype = ret, None

        def __call__(self, *a):
            return self.ret

    return Fn


def test_access_denied_means_alive(monkeypatch):
    Fn = _class(monkeypatch)
    k = type("K", (), {})()
    k.OpenProcess = Fn(0)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: k)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)
    assert remote_worker._parent_alive(1234) is True


def test_no_such_process_means_gone(monkeypatch):
    Fn = _class(monkeypatch)
    k = type("K", (), {})()
    k.OpenProcess = Fn(0)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: k)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87)
    assert remote_worker._parent_alive(1234) is False


def test_own_process_is_alive_and_a_bogus_pid_is_gone():
    assert remote_worker._parent_alive(os.getpid()) is True
    assert remote_worker._parent_alive(999999) is False
