"""DOC-006: code, tests and living docs must not cite documentation paths that do not exist.

Historical material under documentation/archive/ is exempt (it describes the
tree as it was). Only tracked files are scanned.
"""
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
_PATH = re.compile(r"(?<![\w/.-])((?:documentation|docs)/[A-Za-z0-9_./ -]*?\.(?:md|txt|json|csv))(?![\w])")
_SUFFIXES = (".py", ".md", ".js", ".mjs", ".html", ".bat", ".sh", ".yml", ".yaml", ".txt", ".spec")


def test_no_dead_documentation_path_citations():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    dead = []
    for rel in out.stdout.splitlines():
        if rel.startswith("documentation/archive/") or not rel.endswith(_SUFFIXES):
            continue
        if rel == "tests/test_documentation_path_citations_regression.py":
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in _PATH.finditer(line):
                cited = m.group(1)
                if any(ch in cited for ch in "*<{"):
                    continue
                if not (ROOT / cited).exists():
                    dead.append(f"{rel}:{lineno} -> {cited}")
    assert dead == [], "dead documentation path citations:\n" + "\n".join(dead)


def test_release_note_covers_result_affecting_backlog_items():
    text = (ROOT / "documentation/reference/release_notes/2026-09-changes-334-339.md").read_text(encoding="utf-8")
    for item in ("#334", "#336", "#338"):
        assert item in text
