"""RFC 6238 TOTP used for the gateway's mandatory two-factor login."""
from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlsplit

from src.gateway import totp

RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


def test_rfc6238_sha1_vectors():
    # RFC 6238 appendix B (SHA-1), last 6 of the 8-digit values.
    for t, code8 in [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"), (1234567890, "89005924"),
                     (2000000000, "69279037"), (20000000000, "65353130")]:
        assert totp.code_at(RFC_SECRET, t // 30) == code8[-6:]


def test_verify_accepts_one_step_either_side_and_returns_the_step():
    now = 1_000_000.0
    step = int(now // 30)
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step), now, last_step=None) == step
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 1), now, last_step=None) == step - 1
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step + 1), now, last_step=None) == step + 1
    assert totp.verify(RFC_SECRET, totp.code_at(RFC_SECRET, step - 2), now, last_step=None) is None


def test_verify_refuses_replay_and_junk():
    now = 1_000_000.0
    step = int(now // 30)
    code = totp.code_at(RFC_SECRET, step)
    assert totp.verify(RFC_SECRET, code, now, last_step=step) is None
    assert totp.verify(RFC_SECRET, "", now, last_step=None) is None
    assert totp.verify(RFC_SECRET, "12345", now, last_step=None) is None
    assert totp.verify(RFC_SECRET, "abcdef", now, last_step=None) is None
    assert totp.verify(RFC_SECRET, f" {code[:3]} {code[3:]} ", now, last_step=None) == step  # spaces tolerated


def test_new_secret_and_provisioning_uri():
    s1, s2 = totp.new_secret(), totp.new_secret()
    assert s1 != s2 and len(s1) == 32 and s1.isalnum() and s1.upper() == s1
    uri = totp.provisioning_uri(s1, "ann", issuer="Retirement Planner")
    parts = urlsplit(uri)
    assert parts.scheme == "otpauth" and parts.netloc == "totp"
    q = parse_qs(parts.query)
    assert q["secret"] == [s1] and q["issuer"] == ["Retirement Planner"]
    assert q["digits"] == ["6"] and q["period"] == ["30"] and q["algorithm"] == ["SHA1"]
