"""RFC 6238 time-based one-time passwords (SHA-1, 6 digits, 30-second steps), stdlib only.

These are the parameters every common authenticator app accepts by default.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD = 30
WINDOW = 1  # steps accepted either side of now, for clock drift


def new_secret() -> str:
    """160 random bits as unpadded base32 (32 characters)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", int(step)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, now: float, last_step: int | None) -> int | None:
    """The matched step when ``code`` is valid at ``now`` and newer than ``last_step``, else None."""
    code = "".join(str(code or "").split())
    if len(code) != DIGITS or not code.isdigit():
        return None
    current = int(now // PERIOD)
    for step in range(max(0, current - WINDOW), current + WINDOW + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Retirement Planner") -> str:
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD})
    return f"otpauth://totp/{label}?{query}"
