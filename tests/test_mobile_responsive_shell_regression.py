from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_mobile_shell_dom_hooks_present_in_index_html():
    html = read("frontend/index.html")
    assert 'id="navToggleBtn"' in html
    assert 'onclick="toggleNavDrawer()"' in html
    assert 'id="navBackdrop"' in html
    assert 'onclick="closeNavDrawer()"' in html
    assert 'id="sideNav"' in html
    assert 'id="navCloseBtn"' in html
    assert 'id="mobileProgress"' in html
    assert 'id="mobileProgressBar"' in html
    assert 'id="helpPane"' in html
    assert 'onclick="toggleHelpSheet()"' in html


def test_mobile_shell_toggle_functions_defined_in_dashboard_js():
    js = read("frontend/js/dashboard.js")
    assert "function openNavDrawer()" in js
    assert "function closeNavDrawer()" in js
    assert "function toggleNavDrawer()" in js
    assert "function toggleHelpSheet()" in js
    # Mobile progress bar stays in sync with the sidebar progress bar.
    assert "mobileProgressBar" in js


def test_holdings_and_liabilities_tables_carry_data_label_for_card_layout():
    js = read("frontend/js/dashboard.js")
    assert 'data-label="${esc(humanLabel(c))}"' in js
    assert 'data-label="Actions"' in js
    assert "data-label=\"${lbl}\"" in js


def test_dashboard_css_has_phone_breakpoints_and_mobile_shell_rules():
    css = read("frontend/css/dashboard.css")
    assert "@media(max-width:768px)" in css
    assert "@media(max-width:480px)" in css
    # 1.1 drawer + collapsible help
    assert "aside.card.side{position:fixed" in css
    assert "body.nav-open aside.card.side{transform:translateX(0)}" in css
    assert "body.help-open aside.card.help #helpPanel{display:block}" in css
    # 1.2 touch targets + iOS zoom guard
    assert ".btn,.stepbtn,.helpbtn,button{min-height:44px}" in css
    assert "font-size:16px" in css
    # 1.3 card-layout table strategy
    assert ".lot-table thead{display:none}" in css
    assert "content:attr(data-label)" in css
    # 1.4 fixed bottom nav bar
    assert ".nav-actions{position:fixed;left:0;right:0;bottom:0" in css


def test_help_toggle_button_resets_desktop_chrome_outside_media_query():
    """The .help-toggle button must look like a plain heading on desktop —
    its interactive/collapsible chrome is scoped to the phone media query.
    Regression guard for a real bug caught during Phase 1 development where
    the button's default browser styling leaked into the desktop layout."""
    css = read("frontend/css/dashboard.css")
    base_rule_start = css.index(".help-toggle{")
    media_query_start = css.index("@media(max-width:768px)")
    assert base_rule_start < media_query_start, (
        "the desktop-safe .help-toggle reset must be declared before the "
        "phone media query so the media query's later declarations win there"
    )
    base_rule = css[base_rule_start:css.index("}", base_rule_start) + 1]
    assert "border:none" in base_rule
    assert "cursor:default" in base_rule
