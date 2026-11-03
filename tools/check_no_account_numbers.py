#!/usr/bin/env python3
"""Fail if a tracked file contains an account number (account-number protection, plan section 4.4).

Two parts:
* pattern part (runs in CI and locally): cue-word number patterns (``ACCT 123456789``, ``XXXXX-1234-5`` ...) via  (acct-scan: ok)
  ``src/account_numbers.contains_account_number``. A line carrying the marker ``acct-scan: ok`` is exempt (synthetic
  test fixtures only).
* list part (local only): the real numbers, one per line, in an ignored local file
  (``local_state/account_numbers.local.txt`` or ``$ACCOUNT_NUMBER_LIST``). Any tracked file containing one fails.
  Run this tool before pushing.

Prints file:line and the kind of hit, NEVER the matched value. Scans tracked files only (``git ls-files``).
Exit 1 on any hit.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.account_numbers import contains_account_number  # noqa: E402

MARKER = "acct-scan: ok"
ALLOWED_FILES = {"tests/test_account_numbers.py", "tests/test_account_numbers_import.py", "tests/test_redact_account_numbers_tool.py",
                 "tests/test_account_number_guards.py"}  # masking tests need fake numbers by design
LOCAL_LIST = ROOT / "local_state" / "account_numbers.local.txt"
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".xlsx", ".zip", ".rpx", ".db", ".woff", ".woff2", ".pyc"}
SKIP_PARTS = {"node_modules"}


def tracked_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [ROOT / n for n in out.decode("utf-8", "replace").split("\0") if n]


def load_list() -> list[str]:
    path = Path(os.environ.get("ACCOUNT_NUMBER_LIST") or LOCAL_LIST)
    if not path.is_file():
        return []
    return ["".join(ch for ch in ln if ch.isdigit()) for ln in path.read_text(encoding="utf-8").splitlines()
            if len("".join(ch for ch in ln if ch.isdigit())) >= 5]


def scan_text(text: str, known: list[str], *, cues: bool = True) -> list[tuple[int, str]]:
    hits = []
    digits_known = tuple(known)
    for n, line in enumerate(text.splitlines(), 1):
        if MARKER in line:
            continue
        if digits_known and contains_account_number(line, known_ids=digits_known):
            hits.append((n, "listed number"))
        elif cues and contains_account_number(line):
            hits.append((n, "cue-word number"))
    return hits


def main() -> int:
    known = load_list()
    bad = 0
    for path in tracked_files():
        if path.suffix.lower() in SKIP_SUFFIXES or SKIP_PARTS & set(path.parts) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        cues = path.relative_to(ROOT).as_posix() not in ALLOWED_FILES
        for n, kind in scan_text(text, known, cues=cues):
            print(f"{path.relative_to(ROOT).as_posix()}:{n}: {kind}")
            bad += 1
    print(f"account-number scan: {bad} hit(s); list part {'ran' if known else 'skipped (no local list)'}.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
