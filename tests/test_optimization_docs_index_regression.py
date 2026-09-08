"""Finding DOC-205 (system review 2026-09-07, Wave 6 item W6-6):
documentation/ root held five-plus overlapping, ambiguously-titled
optimization-plan documents with no index distinguishing current from
superseded. documentation/OPTIMIZATION_DOCS_INDEX.md was added to name
every document in the cluster and, where the document's own content
already says so, its relationship to the others.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "documentation" / "OPTIMIZATION_DOCS_INDEX.md"

CLUSTER_DOCS = [
    "Final Optimization Implementation Plan.md",
    "Latest Optimization Implementation Plan.md",
    "Final Optimization Upgrade Plan.md",
    "OPTIMIZATION_REFACTOR_STATUS.md",
    "F0_F1_F2_COMPLETION_SUMMARY.md",
    "REMAINING_WORK_EXECUTION_PLAYBOOK.md",
]


def test_index_exists_and_lists_every_document_in_the_cluster():
    assert INDEX_PATH.exists(), "documentation/OPTIMIZATION_DOCS_INDEX.md is missing"
    text = INDEX_PATH.read_text(encoding="utf-8")
    missing = [name for name in CLUSTER_DOCS if name not in text]
    assert missing == [], f"index is missing these cluster documents: {missing}"


def test_every_cluster_document_points_back_to_the_index():
    for name in CLUSTER_DOCS:
        path = ROOT / "documentation" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "OPTIMIZATION_DOCS_INDEX.md" in text, (
            f"documentation/{name} does not point back to the index -- a reader landing on it "
            "directly (not via the index) has no way to discover the other documents in this cluster"
        )
