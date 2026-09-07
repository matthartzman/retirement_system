"""FUNCTIONAL_SPEC.md staleness guard (finding DOC-201 / Wave 5 item W4-8).

System review 2026-09-07 found the spec ("Generated: 2026-08-29... describes
the system as the code currently behaves") omitted five features shipped
after its own stated generation date: QLAC, the Monarch Money auto-import
module, the Financial Trends Reporter companion app, phase-varying Roth
conversions, and the adoptable Guyton-Klinger/floor-ceiling spending policy.
All five were backfilled in this same commit.

This test is deliberately a fixed manifest, not an automatic "detect any new
feature" scanner -- there is no single registry a QLAC-shaped feature, a
standalone companion app, and a strategy-lever option would all show up in
together. Per this project's own established pattern for this class of
problem (test_freeze_frontend_source_grep.py, test_no_tracking_id_test_names_
regression.py): the existing manifest is frozen and checked mechanically;
extending it when a new user-facing feature ships is a process discipline
(system review §6 Option B), not something this test can derive on its own.
When you ship a new user-facing feature, document it in FUNCTIONAL_SPEC.md
and add its marker term(s) to FEATURE_MARKERS below in the same change.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "documentation" / "FUNCTIONAL_SPEC.md"

# (marker substring, human-readable feature name, case-sensitive?)
FEATURE_MARKERS = [
    ("QLAC", "QLAC (Qualified Longevity Annuity Contract)", True),
    ("Monarch Money", "Monarch Money auto-import", True),
    ("Financial Trends Reporter", "Financial Trends Reporter companion app", True),
    ("phase-varying", "phase-varying Roth conversion strategy", False),
    ("floor-ceiling", "floor-ceiling band spending policy", False),
    ("Guyton-Klinger", "Guyton-Klinger adaptive spending guardrail", True),
]


def test_functional_spec_mentions_every_known_shipped_feature():
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    missing = []
    for marker, feature_name, case_sensitive in FEATURE_MARKERS:
        haystack = spec_text if case_sensitive else spec_text.lower()
        needle = marker if case_sensitive else marker.lower()
        if needle not in haystack:
            missing.append(feature_name)
    assert missing == [], (
        f"FUNCTIONAL_SPEC.md is missing documentation for: {missing}. "
        "Add a description under the relevant '## 4. What the household can "
        "do' subsection (see documentation/FUNCTIONAL_SPEC.md's own "
        "structure) -- this guard exists because the spec already went "
        "stale once (finding DOC-201, system review 2026-09-07)."
    )


def test_functional_spec_states_it_has_been_updated_past_its_original_date():
    # The original 2026-08-29 generation date alone, with no later update
    # note, is exactly the state DOC-201 found stale. Require the header to
    # show at least one later date once any FEATURE_MARKERS entry exists.
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    header = spec_text.splitlines()[0:6]
    header_text = "\n".join(header)
    assert "2026-08-29" in header_text
    assert "updated" in header_text.lower(), (
        "FUNCTIONAL_SPEC.md's header still shows only its original "
        "generation date with no later 'updated' note -- update the header "
        "whenever the manifest in this test file grows."
    )
