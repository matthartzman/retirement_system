"""Regression tests for two startup bugs found 2026-07-22:

1. index.html loaded dashboard_decomp_local_backups.js AFTER dashboard.js, but
   dashboard.js's own top-level boot code (the checkAppStatus(true).then(...)
   chain) calls refreshLocalBackupStatus(), which is only defined in that
   later-loaded file. Every real page load threw
   "ReferenceError: refreshLocalBackupStatus is not defined" inside that
   chain's unguarded promise callback, silently killing the whole boot
   sequence (build-status banner, autoload) with no console output because
   nothing on the chain had a .catch().

2. checkAppStatus() guarded re-entrancy with a plain boolean
   (appCheckInFlight): a concurrent caller during the brief window before the
   very first ping resolved got the STALE appReady value returned immediately
   instead of the real result, so every api() call chained off it (build
   status, refreshLocalBackupStatus, prefs/autoload) failed with "Application
   is not available" even though the app was actually up moments later.
   loadCanonicalGlossary()'s api("/api/glossary") call — two lines above the
   explicit startup checkAppStatus(true) — was enough to trigger this on
   every single load.

system_review 2026-08-31 item 3.11 later converted both
dashboard_decomp_local_backups.js and dashboard_decomp_monarch_autoupdate.js
from classic to type="module" scripts, and changed the boot chain to reach
them via dynamic import() instead of a bare global reference. See
test_local_backups_and_monarch_autoupdate_are_now_modules and
test_dynamic_import_specifiers_match_script_tags below for what that changed
and what still needs guarding.
"""
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASH = ROOT / "frontend" / "js" / "dashboard.js"


def test_local_backups_and_monarch_autoupdate_are_now_modules():
    """system_review 2026-08-31 item 3.11: both files converted from classic
    to type="module". The load-order guarantee this test used to assert
    (classic scripts always finish before module scripts, so tag order
    didn't even matter) no longer applies now that both sides are modules --
    module scripts without async run in relative document order, which is a
    POSITIONAL guarantee, not a structural one. dashboard.js's boot chain no
    longer relies on that positioning at all: it reaches these two files
    through a dynamic import() that force-awaits each module's own
    evaluation before calling into its window bridge, which is correct
    regardless of script-tag order. See
    test_dynamic_import_specifiers_match_script_tags below for the guard
    that actually matters now, and dashboard_decomp_local_backups.js's own
    header comment for the full reasoning."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    for name in (
        "dashboard_decomp_local_backups.js",
        "dashboard_decomp_monarch_autoupdate.js",
    ):
        assert f'<script src="js/{name}' not in html, (
            f"{name} reverted to a classic <script src=...> tag -- see this "
            "test's docstring."
        )
        assert f'<script type="module" src="js/{name}' in html, (
            f"{name}'s type=\"module\" tag not found in index.html."
        )


def test_dynamic_import_specifiers_match_script_tags():
    """dashboard.js's boot chain calls
    import("./dashboard_decomp_local_backups.js?v=1") /
    import("./dashboard_decomp_monarch_autoupdate.js?v=1") instead of the
    bare global refreshLocalBackupStatus()/refreshMonarchAutoUpdateStatus()
    calls this file used to guard the load order of. A dynamic import
    specifier is a literal cache key: if it doesn't byte-match the <script
    src=...> tag's path+query exactly, the browser fetches and evaluates a
    SECOND, independent copy of the module -- with its own independent
    localBackupStatus/monarchAutoUpdateStatus closure state, silently
    diverging from the one the rest of the page's window bridge and
    onclick handlers use. Whoever next bumps one of these files' ?v= cache-
    buster must bump both the <script> tag and this dynamic import together,
    or this test catches the drift."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = DASH.read_text(encoding="utf-8")
    for name in (
        "dashboard_decomp_local_backups.js",
        "dashboard_decomp_monarch_autoupdate.js",
    ):
        m = re.search(
            r'<script type="module" src="js/' + re.escape(name) + r'(\?[^"]*)?"',
            html,
        )
        assert m, f"{name}'s <script type=\"module\"> tag not found in index.html"
        query = m.group(1) or ""
        expected_specifier = f'import("./{name}{query}")'
        assert expected_specifier in js, (
            f"dashboard.js's dynamic import of {name} does not match its "
            f"<script> tag's src (including query string). Expected to find "
            f"{expected_specifier!r} in dashboard.js."
        )


def test_dashboard_boot_chain_has_no_bare_unhandled_promise():
    """The checkAppStatus(true).then(...) boot chain must end in a .catch —
    without one, any exception inside it (like the refreshLocalBackupStatus
    ReferenceError this item fixed) is a silent unhandled rejection that
    permanently strands the UI on its unloaded initial state."""
    js = DASH.read_text(encoding="utf-8")
    match = re.search(r"checkAppStatus\(true\)\.then\(function \(ok\) \{", js)
    assert match, "expected the startup checkAppStatus(true).then(...) chain"
    tail = js[match.end():match.end() + 4000]
    assert "}).catch(function (e) {" in tail


def _node_smoke(js_body: str, tmp_path: Path) -> str:
    script = tmp_path / "checkappstatus_smoke.js"
    script.write_text(textwrap.dedent(f"""
        const fs = require('fs');
        const code = fs.readFileSync({str(DASH)!r}, 'utf8');
        global.window = {{ addEventListener(){{}}, location: {{href: ''}} }};
        global.document = {{
          getElementById(){{return null;}}, querySelectorAll(){{return [];}}, addEventListener(){{}}
        }};
        global.localStorage = {{ getItem(){{return null;}}, setItem(){{}} }};
        global.setInterval = () => 0; global.clearInterval = () => {{}};
        // The real declarations (appReady, apiBase, etc.) live earlier in the
        // file in an unrelated destructured `let` chain -- declare stand-ins
        // here rather than pulling in that whole chain's other dependencies.
        let appReady = false;
        let apiBase = '';
        let detailedResultsLoading = false;
        let detailedResultSheetLoading = false;
        function renderSteps() {{}}
        function showMessage() {{}}
        function setAppControls() {{}}
        // Extract just the pieces under test (avoids needing the whole
        // ~16k-line file's other top-level boot side effects for this smoke).
        const startMarker = 'let appCheckPromise = null;';
        // The region under test is appCheckPromise + checkAppStatus +
        // _checkAppStatusRun. Its END is found STRUCTURALLY -- the next
        // top-level declaration after _checkAppStatusRun -- rather than by
        // naming whichever function currently follows it.
        //
        // Naming the neighbour has already broken this test twice, once per
        // extraction pass that happened to move that neighbour out of
        // dashboard.js: setAppControls (row-model extraction, 2026-08-06) and
        // then seedHousingRows (housing/scenarios extraction, 2026-08-11).
        // Both times the marker vanished, the slice failed, and node exited 1
        // with 'markers not found' -- a confusing failure for a test whose
        // real subject is a startup race. There are ~10 more extraction passes
        // planned, so this stops paying that toll.
        //
        // Top-level declarations in dashboard.js all start at column 0 and
        // nested code is indented, so a newline-anchored match is a reliable
        // boundary. NOTE the doubled backslashes: this whole harness is a
        // Python f-string, so a single \\r there would reach node as a real
        // carriage return and split the regex literal across two lines.
        const startIdx = code.indexOf(startMarker);
        if (startIdx < 0) throw new Error('start marker not found: ' + startMarker);
        const runIdx = code.indexOf('async function _checkAppStatusRun', startIdx);
        if (runIdx < 0) throw new Error('_checkAppStatusRun not found after the start marker');
        const rest = code.slice(runIdx + 1);
        const nextDecl = /\\r?\\n(?:async function|function|let|const|var) /.exec(rest);
        const endIdx = nextDecl ? runIdx + 1 + nextDecl.index : code.length;
        const slice = code.slice(startIdx, endIdx);
        eval(slice);
        {js_body}
    """), encoding="utf-8")
    return subprocess.run(
        ["node", str(script)], check=True, cwd=ROOT, capture_output=True, text=True,
    ).stdout


def test_concurrent_checkappstatus_calls_share_the_same_in_flight_result(tmp_path):
    """Two calls to checkAppStatus() started before the first ping resolves
    must both observe the real (eventual) result, not a stale appReady snapshot.
    Mirrors the real bug: loadCanonicalGlossary()'s api() call kicks off an
    implicit checkAppStatus(false) just before the explicit startup
    checkAppStatus(true) two lines later -- both must see the ping succeed."""
    out = _node_smoke(textwrap.dedent("""
        let pingCount = 0;
        global.fetchWithTimeout = async () => {
          pingCount++;
          await new Promise(r => setTimeout(r, 20));
          return { ok: true };
        };
        (async () => {
          const [a, b] = await Promise.all([checkAppStatus(false), checkAppStatus(true)]);
          console.log(JSON.stringify({ a, b, pingCount, appReady }));
        })();
    """), tmp_path)
    import json
    result = json.loads(out.strip().splitlines()[-1])
    assert result["a"] is True
    assert result["b"] is True
    assert result["appReady"] is True
    # Exactly one real ping for the whole overlapping window -- the point of
    # sharing the in-flight promise instead of each caller pinging separately.
    assert result["pingCount"] == 1


def test_checkappstatus_result_is_not_stale_false_during_the_race_window(tmp_path):
    """Before the fix, a second call arriving while the first is still
    in-flight returned whatever `appReady` happened to be at that instant
    (false, pre-ping) instead of awaiting the real outcome -- this is the
    exact mechanism that made every api() call chained off the startup
    checkAppStatus(true) throw "Application is not available" even though
    the ping succeeded moments later."""
    out = _node_smoke(textwrap.dedent("""
        global.fetchWithTimeout = async () => {
          await new Promise(r => setTimeout(r, 20));
          return { ok: true };
        };
        (async () => {
          const first = checkAppStatus(false);   // starts the real ping, unawaited
          const second = await checkAppStatus(true);  // must wait for the same result
          const firstResolved = await first;
          console.log(JSON.stringify({ second, firstResolved }));
        })();
    """), tmp_path)
    import json
    result = json.loads(out.strip().splitlines()[-1])
    assert result["second"] is True
    assert result["firstResolved"] is True
