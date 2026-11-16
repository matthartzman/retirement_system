"""Shared sign-in primitives used by the trends reporter and the multi-user gateway."""
from __future__ import annotations

import json
import subprocess

import pytest

from src import access_core


def test_password_hash_is_salted_and_verifies():
    a, b = access_core.new_salt(), access_core.new_salt()
    assert a != b
    ha = access_core.hash_password("correct horse", a, 2**4)
    assert access_core.password_matches("correct horse", a, 2**4, ha)
    assert not access_core.password_matches("wrong horse!", a, 2**4, ha)
    assert access_core.hash_password("correct horse", b, 2**4) != ha


def test_password_policy_bounds():
    with pytest.raises(ValueError):
        access_core.check_password_policy("short")
    access_core.check_password_policy("x" * 10)
    with pytest.raises(ValueError):
        access_core.check_password_policy("x" * 11, min_length=12)
    with pytest.raises(ValueError):
        access_core.check_password_policy("x" * 30, min_length=12, max_length=20)


def test_failure_outcome_locks_on_fifth_failure_and_resets_count():
    failed, until = 0, 0.0
    for _ in range(4):
        failed, until = access_core.failure_outcome(failed, 100.0)
        assert until == 0.0
    failed, until = access_core.failure_outcome(failed, 100.0)
    assert failed == 0 and until == 100.0 + access_core.LOCK_SECONDS


def test_failure_throttle_grows_then_clears_after_window():
    t = access_core.FailureThrottle(window=600, free=3, max_delay=60)
    for _ in range(3):
        t.record(1000)
    assert t.delay(1000) == 0 and t.retry_after(1000) == 0
    t.record(1000)
    assert t.delay(1000) == 2 and t.retry_after(1000) == 2
    assert t.retry_after(1001.5) == pytest.approx(0.5)
    for _ in range(20):
        t.record(1000)
    assert t.delay(1000) == 60
    assert t.delay(1000 + 601) == 0


def test_keyed_throttle_is_per_key_and_bounded():
    t = access_core.KeyedThrottle(window=600, free=1, max_delay=300, max_keys=5)
    t.record("a", 10)
    t.record("a", 10)
    assert t.retry_after("a", 10) > 0
    assert t.retry_after("b", 10) == 0
    for i in range(20):
        t.record(f"k{i}", 10)
    assert len(t._by_key) <= 5


def test_listener_checks():
    assert access_core.is_loopback_host("127.0.0.1:5064")
    assert access_core.is_loopback_host("localhost")
    assert access_core.is_loopback_host("[::1]:80")
    assert not access_core.is_loopback_host("evil.example:5064")
    assert access_core.has_proxy_headers({"X-Forwarded-For": "1.2.3.4"})
    assert access_core.has_proxy_headers({"Tailscale-User-Login": "x"})
    assert not access_core.has_proxy_headers({"Host": "127.0.0.1"})


def test_tailscale_serves_port_reads_status_json():
    def run_with(text):
        return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=text, stderr="")

    status = json.dumps({"Web": {"node:8443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:5065"}}}}})
    assert access_core.tailscale_serves_port(5065, run=run_with(status)) is True
    assert access_core.tailscale_serves_port(5064, run=run_with(status)) is False
    assert access_core.tailscale_serves_port(5064, run=run_with("not json")) is None

    def missing(*_a, **_k):
        raise FileNotFoundError("tailscale")

    assert access_core.tailscale_serves_port(5064, run=missing) is None
