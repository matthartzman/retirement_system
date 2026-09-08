from __future__ import annotations

"""security.py — optional security helpers for SaaS wrappers.

This module is deliberately not required by the calculation engine.  Local
Python usage works without tokens, user accounts, cloud storage, or databases.
"""

import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

SECRET_PATTERNS = [
    re.compile(r'("?(?:api[_-]?key|token|secret|password)"?\s*[:=]\s*)[^,&\s\n\r]+', re.I),
    re.compile(r'((?:apikey|api_key)=)[^&\s]+', re.I),
]

# Finding SEC-4 (system review 2026-09-07, Wave 6 item W6-2): redact_text()
# above only ever matched credential-shaped keys (api_key/token/secret/
# password) -- balances, DOBs, and merchant names passed through untouched.
# SECRET_PATTERNS's "key: value" regex approach doesn't fit every sink,
# though: the admin-config-change diff log (src/server/security_audit.py's
# _summarize_csv_row_changes) stores a human label ("Household / DOB /
# Husband") and its before/after value as SEPARATE JSON keys, not collapsed
# into one "key: value" string a regex could match. This keyword list lets
# that call site (and any other label+value sink) decide per-field whether
# to redact the value, by matching against the human label text instead.
SENSITIVE_FIELD_LABEL_KEYWORDS = (
    "dob",
    "date of birth",
    "birth date",
    "ssn",
    "social security",
    "balance",
    "account number",
    "account #",
    "merchant",
)


def is_sensitive_change_label(label: object) -> bool:
    text = str(label or "").lower()
    return any(keyword in text for keyword in SENSITIVE_FIELD_LABEL_KEYWORDS)


def redact_secret(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


def redact_text(text: object) -> str:
    output = str(text or "")
    for pattern in SECRET_PATTERNS:
        output = pattern.sub(lambda m: m.group(1) + "***", output)
    return output


def sha256_fingerprint(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def get_server_token() -> Optional[str]:
    """Read the configured SaaS API token from multi_user/system_config.csv."""
    from .runtime_config import load_runtime_config
    token = (load_runtime_config().server_api_token or "").strip()
    return token or None


def constant_time_token_ok(candidate: object, expected: Optional[str]) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(str(candidate or ""), expected)


def append_audit_event(base_dir: str | Path, event: str, details: Optional[Dict[str, Any]] = None, redact: bool = True) -> None:
    try:
        path = Path(base_dir) / "output" / "audit_log.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "timestamp": time.time(),
            "event": event,
            "details": details or {},
        }
        line = json.dumps(payload, sort_keys=True, default=str)
        if redact:
            line = redact_text(line)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Audit logging must not break local or SaaS builds.
        pass

# ===== Version 7 completion helpers =====
def extract_bearer_or_header(headers) -> str:
    auth = headers.get('Authorization', '') if headers is not None else ''
    if str(auth).lower().startswith('bearer '):
        return str(auth).split(' ', 1)[1].strip()
    return (headers.get('X-API-Token', '') if headers is not None else '').strip()
