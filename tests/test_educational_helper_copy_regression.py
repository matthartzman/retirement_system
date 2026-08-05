from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_user_helper_uses_educational_page_and_field_sections():
    js = (ROOT / "frontend/js/dashboard.js").read_text(encoding="utf-8")
    for token in [
        "What this page is for",
        "How the values work together",
        "How to choose values",
        "What this value means",
        "Value options and how to choose",
        "How it relates to this page",
        "Likely impact of changing it",
        "Higher values generally",
        "Changing No to Yes usually",
    ]:
        assert token in js
    for old in ["<h3>Purpose</h3>", "What it impacts", "Questions to ask before changing", "Common mistakes"]:
        assert old not in js


def test_admin_helper_uses_educational_sections_and_value_options():
    js = (ROOT / "frontend/js/admin.js").read_text(encoding="utf-8")
    html = (ROOT / "frontend/admin.html").read_text(encoding="utf-8")
    combined = js + html
    for token in [
        "What this page controls",
        "How the settings work together",
        "What this value means",
        "Value options and how to choose",
        "How it relates to this page",
        "Likely planning or system impact",
        "LIVE</b>: request fresh provider quotes",
    ]:
        assert token in combined
    for old in ["<h3>Purpose</h3>", "What it impacts", "Questions to ask before changing"]:
        assert old not in combined
