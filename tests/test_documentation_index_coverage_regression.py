"""DOC-007 / DOC-004: every reference/ file is indexed, and future/ statuses name their merge evidence."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "documentation"
INDEX = (DOCS / "DOCUMENTATION_INDEX.md").read_text(encoding="utf-8")


def _indexed(rel: str) -> bool:
    """A file is indexed when its path, its file name or one of its folders (with a trailing slash) is named."""
    parts = rel.split("/")
    folders = ["/".join(parts[: i + 1]) + "/" for i in range(len(parts) - 1)]
    return rel in INDEX or parts[-1] in INDEX or any(f in INDEX for f in folders[1:])


def test_every_reference_file_is_indexed_or_archived():
    missing = []
    for p in sorted((DOCS / "reference").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rel = p.relative_to(DOCS).as_posix()
            if not _indexed(rel):
                missing.append(rel)
    assert missing == [], "add to documentation/DOCUMENTATION_INDEX.md or move to archive/:\n" + "\n".join(missing)


def _status_line(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines()[:20]:
        if line.startswith("Status:"):
            return line
    return ""


def test_implemented_future_documents_name_a_merge_reference():
    bad = []
    for p in sorted((DOCS / "future").rglob("*.md")):
        st = _status_line(p)
        if st.startswith("Status: implemented") and not re.search(r"PR #\d+|#\d{3}\b|merged|commit", st):
            bad.append(f"{p.relative_to(DOCS).as_posix()}: {st[:100]}")
    assert bad == [], "an 'implemented' status must cite the merge (PR number, merged, or commit):\n" + "\n".join(bad)


def test_no_future_status_says_not_yet_merged():
    bad = [p.relative_to(DOCS).as_posix() for p in sorted((DOCS / "future").rglob("*.md"))
           if "not yet merged" in _status_line(p).lower()]
    assert bad == [], "reconcile against git log --merges:\n" + "\n".join(bad)
