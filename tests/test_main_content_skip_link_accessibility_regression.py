"""Finding UX-107 (system review 2026-09-07, Wave 6 item W6-7):
frontend/index.html had no skip-link, and #mainPane (the content landmark
inside <main>, alongside the full ~45-step guided-nav sidebar) had no
accessible name -- a keyboard user had to tab through the entire nav on
every page load before reaching content.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASHBOARD_CSS = ROOT / "frontend" / "css" / "dashboard.css"


def test_a_skip_link_targeting_main_pane_exists_before_the_header():
    html = INDEX_HTML.read_text(encoding="utf-8")
    body_idx = html.index("<body>")
    header_idx = html.index("<header>")
    between = html[body_idx:header_idx]
    assert re.search(r'<a[^>]+href="#mainPane"[^>]*class="skip-link"', between), (
        "expected a skip-link anchor (href=\"#mainPane\", class=\"skip-link\") between <body> and <header>"
    )


def test_main_pane_has_an_accessible_name_and_is_focusable():
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r'<section[^>]*id="mainPane"[^>]*>', html)
    assert match, "no #mainPane section found"
    tag = match.group(0)
    assert 'aria-label=' in tag or 'aria-labelledby=' in tag, (
        "#mainPane must carry aria-label or aria-labelledby so a skip-link jump lands on a named landmark"
    )
    assert 'tabindex="-1"' in tag, (
        "#mainPane must be programmatically focusable (tabindex=\"-1\") for the skip-link's focus jump to land there"
    )


def test_skip_link_css_hides_it_until_focused():
    css = DASHBOARD_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.skip-link\{[^}]*position:absolute", css), "skip-link must be visually hidden by default"
    assert re.search(r"\.skip-link:focus\{[^}]*top:0", css), "skip-link must become visible on :focus"
