"""Seals the TOTP secret column of ``gateway.db`` (P7-O1).

The sealed form is ``dpapi1:<base64 of a DPAPI blob>`` in the same TEXT column; a base32 secret never contains
``:``, so a row without the prefix is a legacy clear-text secret and is still readable until ``protect_totp_secrets``
migrates it. DPAPI user scope belongs to the account the gateway service runs as (LocalSystem), the same scheme as the
worker account passwords in ``accounts.py``: the blobs open only for that account on that machine, so a copy of
``gateway.db`` or a backup is useless for minting codes. The consequence for a rebuilt machine is in the runbook.
"""
from __future__ import annotations

import base64
import binascii
import logging
from typing import Protocol

from . import winapi

LOG = logging.getLogger("retirement.gateway.secret_box")
PREFIX = "dpapi1:"


class SecretBox(Protocol):
    def protect(self, secret: str) -> str: ...

    def unprotect(self, stored: str) -> str | None:
        """The clear secret, or None when ``stored`` is sealed and cannot be opened here."""


class PlaintextSecretBox:
    """No sealing: for tests of the legacy layout and for hosts without DPAPI (development only)."""

    def protect(self, secret: str) -> str:
        return secret

    def unprotect(self, stored: str) -> str | None:
        return None if stored.startswith(PREFIX) else stored


class DpapiSecretBox:
    @staticmethod
    def available() -> bool:
        return winapi.IS_WINDOWS

    def protect(self, secret: str) -> str:
        return PREFIX + base64.b64encode(winapi.dpapi_protect(secret.encode("ascii"))).decode("ascii")

    def unprotect(self, stored: str) -> str | None:
        if not stored.startswith(PREFIX):
            return stored
        try:
            return winapi.dpapi_unprotect(base64.b64decode(stored[len(PREFIX):], validate=True)).decode("ascii")
        except (OSError, ValueError, binascii.Error):
            return None


def default_secret_box() -> SecretBox:
    if DpapiSecretBox.available():
        return DpapiSecretBox()
    LOG.warning("DPAPI is not available on this host: TOTP secrets are stored in clear text (development only)")
    return PlaintextSecretBox()
