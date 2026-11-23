"""Sign-in primitives shared by the trends reporter's remote access and the multi-user gateway.

Password hashing (scrypt), the password length rule, per-account lockout arithmetic, failure
throttles, and the listener checks that make the port the trust boundary behind Tailscale Funnel
(Funnel delivers every request from 127.0.0.1). Stdlib only; holds no state on disk.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import subprocess
import threading

from .common_passwords import is_common_password

MIN_PASSWORD_LENGTH = 10
MAX_FAILED_BEFORE_LOCK = 5
LOCK_SECONDS = 15 * 60
# SEC-05 design. Five failures lock a username only for the source (client address) that made them, so a stranger
# cannot lock the owner out. Failures from every source also feed one account-wide count; reaching this many (for
# example a spray from many addresses) locks the account for LOCK_SECONDS against sources that have never completed a
# sign-in, while an address with a recent completed sign-in (a known-good source) still reaches the password check.
MAX_FAILED_ACCOUNT = 50
KNOWN_GOOD_SECONDS = 30 * 24 * 3600
DEFAULT_SCRYPT_N = 2**16  # SEC-06: was 2**15; stored hashes below the configured cost are upgraded on sign-in
_DUMMY_SALT = b"\0" * 16


# ---- passwords ----
def new_salt() -> bytes:
    return secrets.token_bytes(16)


def hash_password(password: str, salt: bytes, n: int) -> bytes:
    return hashlib.scrypt((password or "").encode("utf-8"), salt=salt, n=n, r=8, p=1, maxmem=128 * 1024 * 1024, dklen=32)


def password_matches(password: str, salt: bytes, n: int, expected: bytes) -> bool:
    return hmac.compare_digest(hash_password(password, salt, n), expected)


def burn_password_check(password: str, n: int) -> None:
    """Do the work of a real check, so an unknown username takes as long as a known one."""
    hash_password(password, _DUMMY_SALT, n)


def check_password_policy(password: str, min_length: int = MIN_PASSWORD_LENGTH, max_length: int | None = None) -> None:
    if len(password or "") < min_length:
        raise ValueError(f"password must be at least {min_length} characters")
    if max_length is not None and len(password) > max_length:
        raise ValueError(f"password must be at most {max_length} characters")
    if is_common_password(password):  # SEC-06
        raise ValueError("that password is on the list of passwords everyone tries first; choose another")


def failure_outcome(failed_count: int, now: float, max_failed: int = MAX_FAILED_BEFORE_LOCK,
                    lock_seconds: float = LOCK_SECONDS) -> tuple[int, float]:
    """(new failed count, locked_until) after one more failure; the count resets when the lock starts."""
    failed = int(failed_count) + 1
    if failed >= max_failed:
        return 0, now + lock_seconds
    return failed, 0.0


# ---- throttles ----
class FailureThrottle:
    """Refuse sign-ins for a growing delay once more than ``free`` failures fall in ``window`` seconds."""

    def __init__(self, window: float = 600.0, free: int = 20, max_delay: float = 60.0) -> None:
        self.window, self.free, self.max_delay = float(window), int(free), float(max_delay)
        self._lock = threading.Lock()
        self._failures: list[float] = []

    def record(self, now: float) -> None:
        with self._lock:
            self._failures.append(now)

    def delay(self, now: float) -> float:
        with self._lock:
            self._failures = [t for t in self._failures if now - t < self.window]
            over = len(self._failures) - self.free
            if over <= 0:
                return 0.0
            return min(self.max_delay, float(2 ** min(over, 20)))

    def last_failure_at(self) -> float:
        with self._lock:
            return self._failures[-1] if self._failures else 0.0

    def retry_after(self, now: float) -> float:
        """Seconds still to wait (0 when a sign-in may be tried now)."""
        delay = self.delay(now)
        if not delay:
            return 0.0
        return max(0.0, delay - (now - self.last_failure_at()))


class KeyedThrottle:
    """One ``FailureThrottle`` per key (a client address), with the key table bounded in size."""

    def __init__(self, window: float = 600.0, free: int = 10, max_delay: float = 300.0, max_keys: int = 10_000) -> None:
        self.window, self.free, self.max_delay, self.max_keys = window, free, max_delay, max_keys
        self._lock = threading.Lock()
        self._by_key: dict[str, FailureThrottle] = {}

    def _get(self, key: str, create: bool) -> FailureThrottle | None:
        with self._lock:
            item = self._by_key.get(key)
            if item is None and create:
                if len(self._by_key) >= self.max_keys:
                    stale = [k for k, t in self._by_key.items() if not t.last_failure_at()]
                    for k in stale or list(self._by_key)[: self.max_keys // 10 or 1]:
                        self._by_key.pop(k, None)
                item = self._by_key[key] = FailureThrottle(self.window, self.free, self.max_delay)
            return item

    def record(self, key: str, now: float) -> None:
        self._get(key, create=True).record(now)  # type: ignore[union-attr]

    def retry_after(self, key: str, now: float) -> float:
        item = self._get(key, create=False)
        return item.retry_after(now) if item else 0.0


# ---- listener checks (the port is the trust boundary behind Funnel) ----
def has_proxy_headers(headers: dict) -> bool:
    for key in headers:
        k = str(key).lower()
        if k == "x-forwarded-for" or k.startswith("tailscale-"):
            return True
    return False


def forwarded_client_ip(headers, fallback: str = "") -> str:
    """The client address Tailscale Funnel appended to ``X-Forwarded-For``: the right-most entry.

    Earlier entries are whatever the client sent, so they are never trusted (F-06). ``fallback`` is returned when the
    header is absent or empty.
    """
    parts = [p.strip() for p in str(headers.get("X-Forwarded-For", "") or "").split(",") if p.strip()]
    return parts[-1][:64] if parts else fallback


def is_loopback_host(host_header: str) -> bool:
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        name = host.split("]", 1)[0] + "]"
    else:
        name = host.rsplit(":", 1)[0] if ":" in host else host
    return name in {"127.0.0.1", "localhost", "[::1]"}


def tailscale_serves_port(local_port: int, run=subprocess.run) -> bool | None:
    """True when ``tailscale serve status`` names the port, False when it does not.

    None when the ``tailscale`` command is unavailable or its output is unreadable.
    """
    try:
        out = run(["tailscale", "serve", "status", "--json"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    text = getattr(out, "stdout", "") or ""
    try:
        json.loads(text)
    except ValueError:
        return None
    return bool(re.search(rf"[:/]{int(local_port)}\b", text))
