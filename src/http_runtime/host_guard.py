"""Server-mode hardening helpers (WI-006; ARC-001, ARC-009).

Pure functions so the Host allow-list, the non-loopback start guard and the
request-body cap are unit-testable without opening a socket.
"""
from __future__ import annotations

import ipaddress

LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::", "*"})
# Largest accepted request body. Plan-set zip import caps the uncompressed
# total at 200 MiB (csv_exchange.plan_set.MAX_ZIP_BYTES); uploads are compressed.
MAX_REQUEST_BODY_BYTES = 64 * 1024 * 1024


class ServerStartRefused(RuntimeError):
    """Raised when server mode is asked to bind a non-loopback host unsafely."""


def split_host(value: str) -> str:
    """Return the lower-case hostname of a Host header / netloc (port removed)."""
    text = str(value or "").strip().lower()
    if text.startswith("["):  # [::1]:5050
        return text[1:].split("]", 1)[0]
    if text.count(":") == 1:  # name:port or ipv4:port
        return text.split(":", 1)[0]
    return text  # bare name, bare ipv6


def is_loopback_host(host: str) -> bool:
    name = split_host(host)
    if name in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def allowed_hosts(configured_host: str) -> frozenset[str]:
    """Loopback names plus the explicitly configured (non-wildcard) host."""
    hosts = set(LOOPBACK_NAMES)
    name = split_host(configured_host)
    if name not in WILDCARD_HOSTS:
        hosts.add(name)
    return frozenset(hosts)


def host_allowed(host_header: str, configured_host: str) -> bool:
    name = split_host(host_header)
    return bool(name) and name in allowed_hosts(configured_host)


def origin_netloc_allowed(value: str, configured_host: str) -> bool:
    """True when an Origin/Referer value names an allow-listed host."""
    netloc = str(value or "").split("://", 1)[-1].split("/", 1)[0]
    return host_allowed(netloc, configured_host)


def assert_safe_to_bind(host: str, token: str | None) -> None:
    """Refuse a non-loopback (or wildcard) bind unless an access token is set."""
    if is_loopback_host(host):
        return
    if not (token or "").strip():
        raise ServerStartRefused(
            f"Refusing to start: host {host!r} is not a loopback address and no "
            "access token is configured (set Security/server_api_token or "
            "RETIREMENT_SYSTEM_SERVER_API_TOKEN, or bind to 127.0.0.1)."
        )


def body_too_large(content_length: int) -> bool:
    return int(content_length) > MAX_REQUEST_BODY_BYTES
