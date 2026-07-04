from __future__ import annotations

"""Field Finder ("All Assumptions") grouping and redundancy fixes.

The user reported redundant explanatory text at the top of the page and
asked for grouping by top-level plan area (matching the left navigation)
rather than by individual guided page, with fields sorted alphabetically
within each area."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_field_finder_groups_by_top_level_category_not_individual_page():
    js = read("frontend/js/dashboard.js")
    assert "function fieldFinderCategoryName(group)" in js
    assert "function fieldFinderCategoryOrder()" in js
    # Categories are keyed by each field's owning step's nav group, not its
    # individual step id/title - the old per-page grouping is gone.
    assert "const name=st?fieldFinderCategoryName(st.group):'Uncategorized'" in js
    assert "const ai=catOrder.indexOf(a.name),bi=catOrder.indexOf(b.name)" in js


def test_field_finder_still_sorts_fields_alphabetically_within_a_group():
    js = read("frontend/js/dashboard.js")
    assert "const la=humanLabel(a.label,a),lb=humanLabel(b.label,b);" in js
    assert "return la.localeCompare(lb)||friendlyGroup(a).localeCompare(friendlyGroup(b));" in js


def test_field_finder_shows_source_page_per_field_after_dropping_page_grouping():
    """Item 121 required the source page to be visible per field. Grouping by
    the broader category (instead of by page) would silently lose that
    unless each field row carries its own page label."""
    js = read("frontend/js/dashboard.js")
    assert "field-source-page" in js
    assert "stepTitleById(stepId)" in js
    css = read("frontend/css/dashboard.css")
    assert ".field-source-page" in css


def test_field_finder_disambiguates_same_labeled_fields_across_subsections():
    """Multiple distinct fields (e.g. additional_income_pct on each of five
    Income Streams subsections - Member 2 Pension, Member 2 Single Annuity,
    etc.) share the same humanized label ('Additional Income') and, before
    this fix, the same source-page label too ('Income & Social Security'),
    making them indistinguishable in the flat alphabetized list. The
    subsection-derived qualifier (friendlyGroup) must be appended whenever it
    differs from the page title, and used as a secondary sort key so
    identically-labeled fields group together in a stable order."""
    js = read("frontend/js/dashboard.js")
    assert "const qualifier=friendlyGroup(r);" in js
    assert "const sourceLine=[pageTitle,qualifier&&norm(qualifier)!==norm(pageTitle)?qualifier:''].filter(Boolean).join(' · ');" in js


def test_field_finder_intro_desc_and_section_note_are_not_near_duplicates():
    """Previously intro, desc, and the section-note all repeated variations
    of 'every editable field ... search ... prefer the source page', which
    read as redundant when shown stacked at the top of the page."""
    js = read("frontend/js/dashboard.js")
    assert "id:'all_assumptions'" in js
    step_start = js.index("id:'all_assumptions'")
    step_line = js[step_start:js.index("\n", step_start)]
    assert "desc:'Use when a value doesn\\'t appear on its guided page.'" in step_line
    assert "Every editable plan field in one place" not in js
    assert "Grouped by source page in guided-navigation order" not in js
    assert "Grouped by plan area, matching the left navigation" in js
