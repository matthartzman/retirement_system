"""Guards frontend/js/dashboard_shared_helpers.js's load-order dependency,
found and resolved while scoping system_review 2026-08-31 item 3.11 (frontend
leaf modules -> real ES imports).

Unlike pywebview_bridge.js (see test_pywebview_bridge_load_order_regression.py
for why THAT one stays classic), dashboard_shared_helpers.js's own top-level
code is inert: a handful of plain `function` declarations (esc, escJs,
fmtMoney, ...) plus one final `window.RPDashboardUtils = {...}` assignment --
nothing that reads any other file's globals. The dependency runs the other
way: everything ELSE reads ITS globals (esc/escJs/fmtMoney/fmtPct/
decimalTrim/numberFromDisplay/formatNumberValue/currencyDisplay/
percentDisplay/deleteIconBtn/annualizeToggleBtn), and it is loaded first
specifically so those are available as plain globals to every classic OR
module script that follows.

It is NOT used by admin.html (admin.js defines its own esc()/formatting
helpers) -- this file is index.html-only, so pywebview_bridge.js's
admin.js/admin.html complication does not apply here.

Verified before converting this file to type="module" (2026-08-3x): no
OTHER frontend/js file references any of its exported identifiers as a bare,
top-level (column-0, outside any function) statement -- every real call site
is inside a function body that only runs later, well after module evaluation
finishes. That means the classic-vs-module phase boundary was never actually
protecting anything for this file the way it genuinely does for
pywebview_bridge.js; the strict requirement is only that dashboard_shared_
helpers.js's own <script> tag precede every other script tag that reads its
globals, which document order among type="module" scripts (all scripts in
index.html now are) already guarantees on its own.

This file keeps both halves of that argument true going forward: the tag
stays first (right after pywebview_bridge.js, which has its own stronger
first-of-all requirement), and no other file gains a top-level reference to
one of its identifiers without this test catching it.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
ADMIN_HTML = ROOT / "frontend" / "admin.html"

MODULE_TAG = '<script type="module" src="js/dashboard_shared_helpers.js'
PYWEBVIEW_MODULE_TAG = '<script type="module" src="js/pywebview_bridge.js'

EXPORTED_IDENTIFIERS = [
    "esc",
    "escJs",
    "fmtMoney",
    "fmtPct",
    "decimalTrim",
    "numberFromDisplay",
    "formatNumberValue",
    "currencyDisplay",
    "percentDisplay",
    "deleteIconBtn",
    "annualizeToggleBtn",
]


def test_shared_helpers_tag_immediately_follows_pywebview_bridge_in_index_html():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert PYWEBVIEW_MODULE_TAG in html, "pywebview_bridge.js's tag not found -- see test_pywebview_bridge_load_order_regression.py"
    assert MODULE_TAG in html, (
        "dashboard_shared_helpers.js's type=\"module\" tag not found in index.html."
    )
    bridge_pos = html.index(PYWEBVIEW_MODULE_TAG)
    helpers_pos = html.index(MODULE_TAG)
    assert bridge_pos < helpers_pos, (
        "pywebview_bridge.js must still load before dashboard_shared_helpers.js."
    )
    between = html[bridge_pos + len(PYWEBVIEW_MODULE_TAG): helpers_pos]
    assert "<script" not in between, (
        "Another <script> tag now sits between pywebview_bridge.js and "
        "dashboard_shared_helpers.js. dashboard_shared_helpers.js does not "
        "strictly need to be second (only before every consumer of its "
        "globals), but keeping it second is the simplest way to keep that "
        "true without re-auditing every other script's position -- if this "
        "was intentional, re-run the top-level-reference scan below by hand "
        "for whatever now loads earlier."
    )


def test_shared_helpers_not_referenced_in_admin_html():
    """admin.js has its own esc()/formatting helpers and does not load this
    file. If that ever changes, admin.html would inherit the same
    classic-vs-module considerations pywebview_bridge.js already has to deal
    with there (admin.js's synchronous top-level boot code), which this
    test's sibling module addresses for pywebview_bridge.js specifically --
    re-examine both files together before wiring dashboard_shared_helpers.js
    into admin.html."""
    html = ADMIN_HTML.read_text(encoding="utf-8")
    assert "dashboard_shared_helpers.js" not in html


def test_no_other_frontend_js_file_uses_a_shared_helper_at_top_level():
    """Static guard, same column-0-is-top-level convention used throughout
    this test suite (see test_dashboard_startup_race_and_script_order.py and
    test_pywebview_bridge_load_order_regression.py): if a future file called
    esc(...) or one of shared_helpers' other exports as a bare top-level
    statement, document order among type="module" scripts would still
    protect it TODAY (this file loads first) -- but that is a positional
    guarantee, not a structural one, and is exactly the kind of thing that
    silently breaks when someone reorders <script> tags later. Catch it here
    instead."""
    js_dir = ROOT / "frontend" / "js"
    offenders = []
    for path in sorted(js_dir.rglob("*.js")):
        if path.name == "dashboard_shared_helpers.js":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for name in EXPORTED_IDENTIFIERS:
                if line.startswith(name + "("):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {name}(")
    assert not offenders, (
        "Found a bare, top-level call to a dashboard_shared_helpers.js export "
        f"outside that file itself: {offenders}. Move it inside a function "
        "(the existing convention everywhere else already does this), or "
        "re-verify dashboard_shared_helpers.js's script-tag position covers it."
    )
