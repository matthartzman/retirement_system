"""Provenance digests for the synthetic and full-row snapshot golden masters.

WI-404 (system review 2026-09-25-2, QA-006): ``test_golden_master_pin_provenance``
bound only the frozen-plan pins to a changelog marker, so the two JSON fixtures
below could be hand-edited without the suite noticing. Each fixture is now
bound by a content digest that must appear in a
``documentation/reference/GOLDEN_MASTER_CHANGELOG.md`` marker:

    <!-- fixture-provenance: <fixture filename> sha256=<digest> -->

The digest is taken over the parsed JSON re-serialized canonically (sorted
keys, no whitespace), so line endings and indentation do not matter -- only
the pinned values do. ``tools/regen_synthetic_golden_master.py`` and
``tools/regen_full_row_snapshot.py`` print the marker to paste into the
changelog entry that records the regeneration.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = (
    ROOT / "tests" / "fixtures" / "synthetic_golden_master_cases.json",
    ROOT / "tests" / "fixtures" / "deterministic_engine_full_row_snapshot_cases.json",
)
FIXTURE_PROVENANCE_MARKER_RE = re.compile(
    r"<!--\s*fixture-provenance:\s*(?P<name>[\w.\-]+)\s+sha256=(?P<digest>[0-9a-f]{64})\s*-->"
)


def fixture_digest(path: Path) -> str:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def fixture_marker(path: Path) -> str:
    return f"<!-- fixture-provenance: {Path(path).name} sha256={fixture_digest(path)} -->"
