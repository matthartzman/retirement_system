"""Sign-in throttling for the gateway (security review P7-O4).

Failures are counted per client address AND per username. Neither bucket can be filled by one party for everyone:
an address that fails against many usernames slows only itself, and many addresses failing against one username
slow only that username (which the 5-failure account lock already covers). The gateway-wide count no longer refuses
anyone; it only raises one audit event per window when failures are high, and reports on the admin health page.

The primitives come from ``src.access_core`` unchanged (they are shared with the trends reporter).
"""
from __future__ import annotations

import threading
from collections import deque

from src.access_core import KeyedThrottle


def login_username(raw: object) -> str:
    """The username exactly as the login route normalises it (and ``GatewayStore.find_user`` looks it up)."""
    return str(raw or "").strip().lower()[:64]


class SurgeMonitor:
    """Detection only: counts gateway-wide failures and reports a surge at most once per window."""

    def __init__(self, window: float, threshold: int) -> None:
        self.window, self.threshold = float(window), int(threshold)
        self._lock = threading.Lock()
        self._failures: deque[float] = deque()
        self._alerted_at: float | None = None

    def _prune(self, now: float) -> None:
        while self._failures and now - self._failures[0] >= self.window:
            self._failures.popleft()

    def record(self, now: float) -> int | None:
        """Count one failure; return the window's count when this failure should raise the (one) alert."""
        with self._lock:
            self._failures.append(now)
            # Memory stays bounded: anything past the window is dropped, and a surge beyond 100x the threshold is
            # still a surge, so the oldest are dropped first.
            while len(self._failures) > max(1000, self.threshold * 100):
                self._failures.popleft()
            self._prune(now)
            count = len(self._failures)
            if count <= self.threshold:
                return None
            if self._alerted_at is not None and now - self._alerted_at < self.window:
                return None
            self._alerted_at = now
            return count

    def status(self, now: float) -> dict:
        with self._lock:
            self._prune(now)
            count = len(self._failures)
            return {"failures_in_window": count, "window_seconds": round(self.window), "alert_threshold": self.threshold,
                    "high": count > self.threshold, "last_alert_at": self._alerted_at}


class SignInThrottle:
    """Per-address and per-username throttles plus the gateway-wide surge monitor."""

    def __init__(self, *, window: float, ip_free: int, ip_max_delay: float, user_free: int, user_max_delay: float,
                 user_max_keys: int, surge_threshold: int) -> None:
        self.by_ip = KeyedThrottle(window, ip_free, ip_max_delay)
        # Unknown usernames get a bucket exactly like known ones (no existence leak); the key table is capped and
        # the oldest buckets are evicted first (``KeyedThrottle``), so a username spray cannot grow memory.
        self.by_user = KeyedThrottle(window, user_free, user_max_delay, max_keys=max(1, int(user_max_keys)))
        self.surge = SurgeMonitor(window, surge_threshold)

    def retry_after(self, ip: str, username: str, now: float) -> float:
        wait = self.by_ip.retry_after(ip, now)
        if username:
            wait = max(wait, self.by_user.retry_after(login_username(username), now))
        return wait

    def record(self, ip: str, username: str, now: float) -> int | None:
        """Count one failure; return the surge count when the once-per-window alert is due."""
        self.by_ip.record(ip, now)
        if username:
            self.by_user.record(login_username(username), now)
        return self.surge.record(now)
