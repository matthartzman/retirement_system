"""Contextual Help Panel Phase 4: the prose inventory is closed out.

No class A row may remain in the centre panel (every row is moved:, deleted: or kept:), and every
class D row's merged_into target must exist. Counts are in documentation/future/ui_prose_inventory_summary.md.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import verify_ui_prose_inventory as v  # noqa: E402


def test_no_class_a_row_is_left_unmoved_and_merge_targets_exist():
    rows = v.load()
    assert len(rows) > 500
    assert v.problems(rows) == []


def test_every_page_level_row_has_a_slot_or_is_a_duplicate():
    rows = [r for r in v.load() if r["level"] == "page"]
    assert rows and all(r["slot"] for r in rows)


def test_prose_guard_test_exists():
    guard = (ROOT / "tests" / "frontend" / "ui_prose_guard.test.mjs").read_text(encoding="utf-8")
    assert 'data-kind' in guard and "MAX_LINE_CHARS" in guard
