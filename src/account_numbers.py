"""Account-number masking: the one place that knows the rules.

Design: documentation/future/superpowers/plans/2026-10-31-account-number-protection-design-and-plan.md

A full account number must never be stored, shown, logged or exported; at most
the last 4 digits may appear. Detection is cue-based (decision 2), so CUSIPs,
amounts, share counts and payment ids are never damaged:

* free text: digit runs next to a cue word (ACCT, ACCOUNT, A/C, ACC#, ROUTING,
  IBAN), after ``XXXX-``, or in the ``XXXXX-NNNN-N`` transfer form;
* file names: any digit run of 6 or more;
* ``known_ids``: caller-supplied numbers, masked wherever they appear;
* ``exempt``: per-row values (symbol/CUSIP) that are never masked.

Pure and dependency-free. Masking is idempotent: a ``…NNNN`` result has no run
of 5+ digits, so masking it again changes nothing.
"""
from __future__ import annotations

import re
from typing import Iterable

ELLIPSIS = "…"
_SEP = r"[-\s]?"
# digits with optional single dash/space separators; at least 5 digits in total
# so an already-masked "…1234" (4 digits) is never rewritten.
_NUM = r"\d(?:[-\s]?\d){4,}"

_CUE = re.compile(
    r"(?P<cue>\b(?:ACCT|ACCOUNT|ACC|A/C)\b\.?\s*(?:#|NO\.?|NUMBER|NUM)?[\s:#=\"'-]*"
    r"|\b(?:ROUTING|IBAN)\b\.?\s*(?:#|NO\.?|NUMBER)?[\s:#=\"'-]*)"
    r"(?P<num>[A-Z]{0,4}" + _NUM + r")",
    re.IGNORECASE,
)
# a "#" cue has no word boundary after ACC  (acct-scan: ok)
_CUE_HASH = re.compile(r"(?P<cue>\bACC#\s*:?\s*)(?P<num>" + _NUM + r")", re.IGNORECASE)
# masked-prefix transfer references; a bare XXXX-0042 (last 4 only) is already safe  (acct-scan: ok)
_XFORM = re.compile(r"\b[Xx*]{3,}[-\s]?(?:(?P<grp>\d{5,})|(?P<grp2>\d{3,})-\d+)\b")
_FILE_RUN = re.compile(r"\d{6,}")


def last4(value: object) -> str:
    """Digits only, last four ('' if there are no digits)."""
    return "".join(ch for ch in str(value or "") if ch.isdigit())[-4:]


def _masked(num: str) -> str:
    return ELLIPSIS + last4(num)


def _digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def _known_pattern(known_ids: Iterable[str]) -> re.Pattern | None:
    parts = []
    for k in known_ids or ():
        d = _digits(str(k))
        if len(d) >= 5:
            parts.append(r"[-\s]?".join(re.escape(c) for c in d))
    if not parts:
        return None
    return re.compile(r"(?<!\d)(?:" + "|".join(parts) + r")(?!\d)")


def _protect(text: str, exempt: Iterable[str]) -> tuple[str, dict[str, str]]:
    """Swap exempt tokens for placeholders so no rule can touch them."""
    held: dict[str, str] = {}
    for i, tok in enumerate(t for t in (str(e).strip() for e in (exempt or ())) if t):
        ph = f"\u0000{i}\u0000"
        if tok in text:
            text = text.replace(tok, ph)
            held[ph] = tok
    return text, held


def mask_text(text: object, *, known_ids: Iterable[str] = (), exempt: Iterable[str] = ()) -> str:
    """Mask cue-based account numbers in free text, keeping the last 4 digits."""
    out = "" if text is None else str(text)
    if not out:
        return out
    out, held = _protect(out, exempt)
    kp = _known_pattern(known_ids)
    if kp is not None:
        out = kp.sub(lambda m: _masked(m.group(0)), out)
    out = _CUE.sub(lambda m: m.group("cue") + _masked(m.group("num")), out)
    out = _CUE_HASH.sub(lambda m: m.group("cue") + _masked(m.group("num")), out)
    out = _XFORM.sub(lambda m: _masked(m.group("grp") or m.group("grp2")), out)
    for ph, tok in held.items():
        out = out.replace(ph, tok)
    return out


def contains_account_number(text: object, *, known_ids: Iterable[str] = (), exempt: Iterable[str] = ()) -> bool:
    """True when mask_text would change the text (i.e. a full number is present)."""
    s = "" if text is None else str(text)
    return bool(s) and mask_text(s, known_ids=known_ids, exempt=exempt) != s


def mask_file_name(name: object) -> str:
    """Mask every 6+ digit run in a file name to ``…NNNN`` (decision 1)."""
    return _FILE_RUN.sub(lambda m: _masked(m.group(0)), "" if name is None else str(name))


import logging as _logging  # noqa: E402


class MaskingFilter(_logging.Filter):
    """Logging filter: every record's message passes through ``mask_text`` (cue-based)."""

    def filter(self, record: _logging.LogRecord) -> bool:
        try:
            msg = mask_text(record.getMessage())
            record.msg, record.args = msg, None
        except Exception:  # never let logging fail because of masking
            pass
        return True
