from pathlib import Path

from src import spending_tracker as st

ROOT = Path(__file__).resolve().parents[1]


def test_tracker_hides_zero_rows_and_normalizes_requested_groups():
    summary = st.spending_summary_taxonomy(ROOT, year=2026)
    assert summary["tracking_types"]

    def has_visible_value(row):
        return any(
            round(float(row.get(key, 0) or 0), 2) != 0
            for key in ("actual", "budget", "projection_seed", "line_count", "template_available_count")
        )

    for tt in summary["tracking_types"]:
        assert has_visible_value(tt) or any(
            has_visible_value(cat)
            for group in tt["groups"]
            for cat in group["categories"]
        )
        for group in tt["groups"]:
            assert has_visible_value(group) or any(has_visible_value(cat) for cat in group["categories"])
            assert group["categories"]
            for cat in group["categories"]:
                assert has_visible_value(cat)

    groups_by_type = {
        t["tracking_type"]: {g["group"] for g in t["groups"]}
        for t in summary["tracking_types"]
    }
    assert "Food & Dining" in groups_by_type.get("Core Expenses", set())
    assert "Food / Dining" not in groups_by_type.get("Core Expenses", set())
    assert "Gifts Charity" in groups_by_type.get("Core Expenses", set())
    assert "Gifts & Donations" not in groups_by_type.get("Core Expenses", set())
    assert "Utilities" in groups_by_type.get("Housing", set())
    assert "Bills & Utilities" not in groups_by_type.get("Housing", set())


def test_business_is_in_main_hierarchy_without_separate_dashboard_section():
    js = (ROOT / "frontend/js/spending_dashboard.js").read_text(encoding="utf-8")
    assert "Business now appears inside the main Tracking Type hierarchy" in js
    assert "if (d.business) html += renderBusinessSection(d);" not in js

    summary = st.spending_summary_taxonomy(ROOT, year=2026)
    business = next(t for t in summary["tracking_types"] if t["tracking_type"] == "Business")
    labels = {c["label"] for g in business["groups"] for c in g["categories"]}
    expected = {
        "Business Auto Expenses",
        "Business Events",
        "Business Hardware and Software",
        "Business Memberships",
        "Business Services",
        "Business Taxi - Uber",
        "Business Travel & Meals",
        "Office Supplies & Expenses",
    }
    assert labels == expected


def test_top_20_ytd_sections_removed_and_tracker_levels_are_visually_distinct():
    dash = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    spend_js = (ROOT / "frontend/js/spending_dashboard.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend/css/dashboard.css").read_text(encoding="utf-8")
    assert "Top 20 YTD income categories" not in dash
    assert "Top 20 YTD spending categories" not in dash
    assert "Tracking Type" in spend_js and "Group" in spend_js and "Category" in spend_js
    assert ".spend-type-row" in css and ".spend-group-row" in css and ".spend-cat-row" in css
