"""DOC-001 / DOC-002: design documents carry a status, and docs/ stays empty.

* Every markdown file under documentation/future/ and every spec or plan under
  documentation/archive/superpowers/ dated 2026-09-16 or later must have a
  ``Status: <draft|approved|implemented|superseded|planned>`` line in its
  first 20 lines. (Older archived files predate the convention and are exempt.)
* No tracked file may live under a top-level docs/ directory; new specs and
  plans go to documentation/future/.
"""
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
_STATUS = re.compile(r"^Status: (draft|approved|implemented|superseded|planned)\b")
_CUTOFF = "2026-09-16"


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        # Packaged release or exported tree: walk the files instead of skipping.
        return sorted(
            p.relative_to(ROOT).as_posix() for p in (ROOT / "documentation").rglob("*") if p.is_file()
        )
    return out.stdout.splitlines()


def _needs_status(rel):
    if not rel.endswith(".md"):
        return False
    if rel.startswith("documentation/future/"):
        return True
    parts = rel.split("/")
    if rel.startswith("documentation/archive/superpowers/") and len(parts) >= 5:
        return parts[-1] >= _CUTOFF
    return False


def test_design_documents_declare_a_status():
    missing = []
    for rel in _tracked():
        if not _needs_status(rel):
            continue
        head = (ROOT / rel).read_text(encoding="utf-8").splitlines()[:20]
        if not any(_STATUS.match(line) for line in head):
            missing.append(rel)
    assert missing == [], "missing a 'Status: <draft|approved|implemented|superseded|planned>' line:\n" + "\n".join(missing)


def test_no_tracked_files_under_docs():
    stray = [rel for rel in _tracked() if rel.startswith("docs/")]
    assert stray == [], (
        "do not add files under docs/; new specs and plans go to documentation/future/:\n" + "\n".join(stray)
    )
