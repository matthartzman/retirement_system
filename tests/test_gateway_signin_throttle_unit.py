"""Sign-in throttle primitives for the gateway: per address, per username, and the detection-only surge count."""
from __future__ import annotations

from src.gateway.signin_throttle import SignInThrottle, SurgeMonitor, login_username

T0 = 1_000_000.0


def _throttle(**kw) -> SignInThrottle:
    args = dict(window=600.0, ip_free=10, ip_max_delay=300.0, user_free=10, user_max_delay=300.0,
                user_max_keys=10_000, surge_threshold=50)
    args.update(kw)
    return SignInThrottle(**args)


def test_login_username_matches_the_login_route():
    assert login_username("  Ann ") == "ann"
    assert login_username(None) == ""
    assert len(login_username("x" * 200)) == 64


def test_one_address_failing_many_usernames_delays_only_that_address():
    t = _throttle()
    for i in range(20):
        t.record("203.0.113.66", f"user{i}", T0)
    assert t.retry_after("203.0.113.66", "ann", T0) > 0
    assert t.retry_after("198.51.100.1", "user0", T0) == 0
    assert t.retry_after("198.51.100.1", "ann", T0) == 0


def test_many_addresses_failing_one_username_delay_only_that_username():
    t = _throttle()
    for i in range(20):
        t.record(f"192.0.2.{i}", "Ann", T0)
    assert t.retry_after("198.51.100.1", " ann", T0) > 0
    assert t.retry_after("198.51.100.1", "bob", T0) == 0
    assert t.retry_after("192.0.2.1", "bob", T0) == 0  # each address used once: still quiet


def test_the_global_count_never_delays_anyone():
    t = _throttle()
    for i in range(5000):
        t.record(f"10.{i // 250}.{i % 250}.1", f"u{i}", T0)
    assert t.retry_after("198.51.100.1", "ann", T0 + 1) == 0


def test_tracked_usernames_are_capped():
    t = _throttle(user_max_keys=100)
    for i in range(1000):
        t.record(f"10.0.{i // 250}.{i % 250}", f"spray{i}", T0)
    assert len(t.by_user._by_key) <= 100


def test_surge_alerts_once_per_window():
    m = SurgeMonitor(600.0, 3)
    alerts = [m.record(T0 + i) for i in range(10)]
    assert alerts == [None, None, None, 4, None, None, None, None, None, None]
    assert m.status(T0 + 10)["high"] is True
    assert m.record(T0 + 650) is None  # old failures aged out: only 1 in the window now
    for i in range(3):
        m.record(T0 + 651 + i)
    assert m.status(T0 + 700)["last_alert_at"] == T0 + 653
    assert m.status(T0 + 5000)["high"] is False
