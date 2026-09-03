"""Guards frontend/js/pywebview_bridge.js's load-order dependency, found and
resolved while advancing system_review 2026-08-31 item 3.11 (frontend leaf
modules -> real ES imports).

pywebview_bridge.js's whole job is to monkey-patch window.fetch and
window.EventSource before ANYTHING ELSE on the page can call the native
versions -- that's what lets the unmodified dashboard/admin scripts run
inside the desktop (pywebview) build without a real HTTP socket. It is now a
type="module" script (converted alongside this test), and its tag is still
the first external <script> in both index.html and admin.html.

Converting it to type="module" moved its execution from the classic phase
(which always finishes, in its entirety, before ANY module script begins --
a browser-spec guarantee, not a document-order convention) into the deferred
module phase, which runs after every classic script. That was already safe
for index.html (nothing there makes a bare, top-level fetch() call -- see
test_no_frontend_js_file_makes_a_bare_top_level_fetch_call below). It was
NOT safe for admin.html as found: admin.js is a separate, fully classic
~2,100-line application (out of scope for the leaf-module conversion; see
frontend/js/modules/phase3_module_manifest.js, which only tracks
frontend/js/dashboard*.js's leaves) whose own top-level boot code called
showAppSettings() and checkApp() as bare, synchronous, top-level statements
-- both of which fire real fetch() calls through admin.js's api() helper.
Those calls would have run BEFORE pywebview_bridge.js's deferred module code,
so the fetch/EventSource patch would not yet be installed -- exactly the
failure shape test_dashboard_startup_race_and_script_order.py guards against
for dashboard.js, but for the admin console under pywebview specifically.

The fix (kept minimal -- admin.js itself was NOT converted to a module,
which was and remains out of scope): admin.js's boot sequence now waits for
DOMContentLoaded before calling showAppSettings()/checkApp(). DOMContentLoaded
fires only after every deferred/module script has run, which is what
actually closes the race -- a queueMicrotask (dashboard.js's own boot-defer
mechanism) does NOT: microtasks queued during a classic script's execution
flush within that same pre-parsing-complete phase, before any deferred
module runs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS = ROOT / "frontend" / "js" / "admin.js"

MODULE_TAG = '<script type="module" src="js/pywebview_bridge.js'
CLASSIC_TAG = '<script src="js/pywebview_bridge.js'


def _first_script_tag_pos(html: str) -> int:
    """Position of the first EXTERNAL <script src=...> tag (module or
    classic). Skips inline <script>...</script> blocks with no src, which
    carry no load-order guarantee relative to external files and aren't part
    of this argument (index.html has one, a tiny inline keydown handler)."""
    import re

    m = re.search(r'<script[^>]*\bsrc="[^"]+"', html)
    assert m, "no external <script src=...> tag found"
    return m.start()


def test_pywebview_bridge_is_a_module_and_first_in_index_html():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert CLASSIC_TAG not in html, (
        "pywebview_bridge.js reverted to a classic <script src=...> tag in "
        "index.html -- see this module's docstring for why it was converted."
    )
    assert MODULE_TAG in html, "pywebview_bridge.js's type=\"module\" tag not found in index.html"
    pos = html.index(MODULE_TAG)
    assert pos == _first_script_tag_pos(html), (
        "pywebview_bridge.js must be the first external script in index.html "
        "so its fetch()/EventSource patch applies before any other script's "
        "top-level code can make a real request."
    )


def test_pywebview_bridge_is_a_module_and_first_in_admin_html():
    html = ADMIN_HTML.read_text(encoding="utf-8")
    assert CLASSIC_TAG not in html, (
        "pywebview_bridge.js reverted to a classic <script src=...> tag in "
        "admin.html -- see this module's docstring for why it was converted."
    )
    assert MODULE_TAG in html, "pywebview_bridge.js's type=\"module\" tag not found in admin.html"
    pos = html.index(MODULE_TAG)
    assert pos == _first_script_tag_pos(html), (
        "pywebview_bridge.js must be the first external script in admin.html too."
    )


def test_admin_js_boot_is_deferred_past_dom_content_loaded():
    """The actual fix: admin.js must not call showAppSettings()/checkApp() as
    bare top-level statements (which run synchronously, in the classic
    phase, before pywebview_bridge.js's now-deferred module code). Both must
    be reachable only from inside a DOMContentLoaded handler, which fires
    after every deferred/module script -- including pywebview_bridge.js --
    has already run."""
    js = ADMIN_JS.read_text(encoding="utf-8")
    assert "\nshowAppSettings().catch(" not in js, (
        "admin.js calls showAppSettings() as a bare top-level statement again -- "
        "this races pywebview_bridge.js's fetch patch under pywebview. Wrap the "
        "boot sequence in a DOMContentLoaded listener (see this file's docstring)."
    )
    assert "\ncheckApp();" not in js, (
        "admin.js calls checkApp() as a bare top-level statement again -- same "
        "race as showAppSettings() above."
    )
    assert 'addEventListener("DOMContentLoaded"' in js, (
        "admin.js no longer defers its boot sequence via DOMContentLoaded."
    )


def test_no_frontend_js_file_makes_a_bare_top_level_fetch_call():
    """Static guard: if any frontend/js file (admin.js included, now that its
    boot call is fixed) made a fetch() call at its own top level (outside any
    function -- this codebase's convention keeps top-level statements at
    column 0, same convention test_dashboard_startup_race_and_script_order.py
    relies on), it would race pywebview_bridge.js's patch."""
    js_dir = ROOT / "frontend" / "js"
    offenders = []
    for path in sorted(js_dir.rglob("*.js")):
        if path.name == "pywebview_bridge.js":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.startswith("fetch("):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not offenders, (
        f"Found a bare, top-level fetch() call: {offenders}. This races "
        "pywebview_bridge.js's fetch patch; wrap it in a function called "
        "later, or defer it past DOMContentLoaded like admin.js's boot "
        "sequence."
    )
