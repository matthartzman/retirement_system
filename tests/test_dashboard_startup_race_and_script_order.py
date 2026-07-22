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
"""
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "frontend" / "index.html"
DASH = ROOT / "frontend" / "js" / "dashboard.js"


def test_local_backups_module_loads_before_dashboard_js():
    html = INDEX_HTML.read_text(encoding="utf-8")
    backups_pos = html.index('<script src="js/dashboard_decomp_local_backups.js')
    dashboard_pos = html.index('<script src="js/dashboard.js')
    assert backups_pos < dashboard_pos, (
        "dashboard_decomp_local_backups.js must load before dashboard.js: "
        "dashboard.js's top-level boot chain calls refreshLocalBackupStatus(), "
        "which that file defines."
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
        const endMarker = 'function setAppControls(on) {{';
        const startIdx = code.indexOf(startMarker);
        const endIdx = code.indexOf(endMarker);
        if (startIdx < 0 || endIdx < 0) throw new Error('markers not found');
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
