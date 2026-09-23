r"""Panel layout and help wiring (design 2026-09-16 Sec 9.2, Sec 9.5, Task 14).

Adapted from the plan's own Step 1 draft. The plan's test extracted registry
keys with ``JS.split('HOUSING_OPT_FIELD_HELP')[1]`` and a
``re.findall(r"^\s{2}(\w+):", block)`` regex, which assumed the registry was a
single flat object literal with a top-level `HOUSING_OPT_FIELD_HELP = {...}`
declaration. That assumption doesn't hold here: `pageHelp()` -- the formatter
the registry is built with -- is defined in dashboard.js, which index.html
loads AFTER every dashboard_decomp_*.js module (see the load-order comment at
the top of dashboard_decomp_housing_scenarios.js). Calling `pageHelp(...)` at
HOUSING_OPT_FIELD_HELP's module-eval time would throw a ReferenceError on
every page load. So the registry here is built as plain per-field DATA
objects ({title, meaning, connections, options, impact}), assembled by an
IIFE plus one Object.assign() call (for the per-move fields and the
general/year fields respectively), and only turned into HTML by calling
pageHelp() lazily inside showHousingOptFieldHelp() at click time. A regex
over the literal source text can't recover "every key passed to
showHousingOptFieldHelp(...) in the rendered markup" that way, so this file
instead runs the module in node (jsdom-free -- the render functions build
plain strings) and inspects the real, assembled registry and the real
rendered HTML, the same way tests/test_holding_period_ui_wiring_functional.py
smoke-tests dashboard.js. This keeps the plan's *intent* (every field id the
rendered panel can ask help for must resolve to real content; `_panel` must
exist) without depending on one particular registry literal shape.
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "frontend" / "js" / "dashboard_decomp_housing_optimizer.js"
SHARED_HELPERS_PATH = ROOT / "frontend" / "js" / "dashboard_shared_helpers.js"
CSS_PATH = ROOT / "frontend" / "css" / "dashboard.css"

JS = JS_PATH.read_text(encoding="utf-8")
CSS = CSS_PATH.read_text(encoding="utf-8")

# Fields the design doc's Sec 9.5 calls out as carrying real decisions --
# these must be full four-section entries (title/meaning/connections/
# options/impact all non-empty), not just present.
FULL_CONTENT_KEYS = [
    "housingOptDisposition",
    "housingOptNoDualOwnership",
    "housingOptObjective",
    "housingOptSearchMode",
    "housingOptMove2Strategy",
    "housingOptMove2Concurrent",
    "housingOptPresenceZip",
    "housingOptPresenceRadius",
] + [
    f"housingOptMove{n}{field}"
    for n in (1, 2)
    # "ShortlistSize" -> "SelectedZips", deliberately, not as collateral
    # damage: the 2026-09-19 anchor-flow design §5.4 removes the per-move
    # "Shortlist size" control outright and step 1's selection table takes
    # over the decision it stood in for. The help obligation moves with the
    # decision rather than being dropped -- picking candidate locations is
    # still a field "carrying a real decision" under §9.5, so it is still
    # required to be a full four-section entry.
    for field in ("AreaType", "MaxPopulation", "LotSize", "MinScore", "Radius", "SelectedZips")
]

# Year fields (Sec 9.5: "simple year fields get a one-paragraph What this
# value means plus the validation rule that governs them").
YEAR_KEYS = [
    "housingOptEarliestSale",
    "housingOptLatestSale",
    "housingOptMove1Earliest",
    "housingOptMove1Latest",
    "housingOptMove2Earliest",
    "housingOptMove2Latest",
    "housingOptPresenceFrom",
    "housingOptPresenceThrough",
]


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        return True
    except Exception:
        return False


NODE_AVAILABLE = _node_available()


def _run_node_smoke(tmp_path: Path) -> dict:
    """Evaluates dashboard_shared_helpers.js + dashboard_decomp_housing_optimizer.js
    in node with NO `pageHelp` global defined (proving the load-order fix: the
    module must evaluate cleanly before dashboard.js -- which defines
    pageHelp -- has run), renders the full panel HTML (pure string building,
    no DOM needed for that part), then defines `pageHelp`/`document`/
    `ensureHelpPanelVisible` (simulating dashboard.js having since loaded) and
    exercises showHousingOptFieldHelp('_panel') for real.
    """
    files_js_array = "[" + ", ".join(repr(str(p)) for p in (SHARED_HELPERS_PATH, JS_PATH)) + "]"
    script = tmp_path / "housing_opt_help_smoke.js"
    harness = textwrap.dedent(f"""
        const fs = require('fs');
        const code = {files_js_array}.map(f => fs.readFileSync(f, 'utf8')
          .replace(/^export (async )?function /gm, '$1function ')
          .replace(/^export (const|let|var) /gm, '$1 ')
        ).join('\\n');

        global.window = {{}};
        // Deliberately NOT defining `pageHelp` here -- dashboard.js (which
        // defines it) loads AFTER this module in index.html. If the registry
        // called pageHelp(...) at module-eval time this eval() would throw.
        let evalError = null;
        try {{
          eval(code);
        }} catch (e) {{
          evalError = String((e && e.stack) || e);
        }}

        const result = {{ evalError }};

        if (!evalError) {{
          const help = window.HOUSING_OPT_FIELD_HELP || {{}};
          result.keys = Object.keys(help);
          result.entries = help;

          let renderError = null;
          let html = '';
          try {{
            html = window.renderHousingOptimizePanelHtml();
          }} catch (e) {{
            renderError = String((e && e.stack) || e);
          }}
          result.renderError = renderError;
          result.html = html;

          const requested = new Set();
          const re = /showHousingOptFieldHelp\\('([^']+)'\\)/g;
          let m;
          while ((m = re.exec(html))) {{ requested.add(m[1]); }}
          result.requested = Array.from(requested);

          // Now simulate dashboard.js having loaded: pageHelp, document,
          // ensureHelpPanelVisible all become available as bare globals.
          global.pageHelp = function(title, meaning, connections, options, impact) {{
            return '<div class="help-title">' + title + '</div>' +
              '<div class="help-body">' +
              '<h3>What this page is for</h3><p>' + meaning + '</p>' +
              '<h3>How the values work together</h3><p>' + connections + '</p>' +
              '<h3>How to choose values</h3><p>' + options + '</p>' +
              '<h3>Likely planning impact</h3><p>' + impact + '</p>' +
              '</div>';
          }};
          let helpPanelHtml = '';
          global.document = {{
            getElementById: (id) => id === 'helpPanel' ? {{
              set innerHTML(v) {{ helpPanelHtml = v; }},
              get innerHTML() {{ return helpPanelHtml; }},
            }} : null,
          }};
          global.ensureHelpPanelVisible = function() {{}};

          let clickError = null;
          try {{
            window.showHousingOptFieldHelp('_panel');
          }} catch (e) {{
            clickError = String((e && e.stack) || e);
          }}
          result.clickError = clickError;
          result.panelClickHtml = helpPanelHtml;

          helpPanelHtml = '';
          let unknownClickError = null;
          try {{
            window.showHousingOptFieldHelp('thisKeyDoesNotExist');
          }} catch (e) {{
            unknownClickError = String((e && e.stack) || e);
          }}
          result.unknownClickError = unknownClickError;
          result.unknownKeyFallbackHtml = helpPanelHtml;
        }}

        console.log(JSON.stringify(result));
    """)
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run(["node", str(script)], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.fail(f"node smoke script failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def smoke():
    if not NODE_AVAILABLE:
        pytest.skip("node is not available in this environment")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        yield _run_node_smoke(Path(td))


# ---------------------------------------------------------------------------
# Load-order fix (the hazard this task exists to avoid)
# ---------------------------------------------------------------------------


def test_module_evaluates_without_pageHelp_defined(smoke):
    """The core assertion for the load-order hazard: dashboard_decomp_*.js
    modules load BEFORE dashboard.js (which defines pageHelp), so this
    module's top level must never call pageHelp(). Proven here by actually
    evaluating it in node with no `pageHelp` global bound at all."""
    assert smoke["evalError"] is None, smoke["evalError"]


# Two source-text assertions were removed here on 2026-09-16
# (test_help_writes_to_the_apps_existing_panel_and_reveals_it, and a static
# "pageHelp( is not inside the registry builder" backstop). Both duplicated a
# test in this file that proves the same property by EXECUTING the module in
# the Node sandbox -- test_clicking_help_renders_through_pageHelp_and_reveals_
# the_panel and test_module_evaluates_without_pageHelp_defined. A string match
# on the source would have broken on a behaviour-preserving rename while the
# runtime tests kept passing, which is the failure mode
# tests/test_freeze_frontend_source_grep.py exists to stop.

# ---------------------------------------------------------------------------
# Registry coverage
# ---------------------------------------------------------------------------


def test_screen_level_help_exists(smoke):
    assert "_panel" in smoke["keys"]


def test_every_field_asked_for_in_the_rendered_panel_has_a_registry_entry(smoke):
    # Anchor entries are keyed per-index (housingOptMove1Anchor0, ...Anchor1,
    # ...) -- the design's Sec 9.2 field list treats "Anchors (2-5)" as one
    # field per move, not one per anchor slot, so individual anchor entries
    # are allowed to fall back to `_panel` rather than requiring their own
    # dedicated content.
    anchor_index_pattern = re.compile(r"^housingOptMove[12]Anchor\d+$")
    missing = [
        k for k in smoke["requested"]
        if k not in smoke["keys"] and not anchor_index_pattern.match(k)
    ]
    assert not missing, f"no help content for: {sorted(missing)}"


def test_full_content_keys_present_with_all_four_sections(smoke):
    entries = smoke["entries"]
    missing_key = [k for k in FULL_CONTENT_KEYS if k not in entries]
    assert not missing_key, f"missing registry entries: {missing_key}"
    for k in FULL_CONTENT_KEYS:
        entry = entries[k]
        for section in ("title", "meaning", "connections", "options", "impact"):
            assert entry.get(section), f"{k}.{section} is empty"


def test_year_fields_present_with_meaning_and_rule(smoke):
    entries = smoke["entries"]
    missing_key = [k for k in YEAR_KEYS if k not in entries]
    assert not missing_key, f"missing registry entries: {missing_key}"
    for k in YEAR_KEYS:
        entry = entries[k]
        assert entry.get("meaning"), f"{k}.meaning is empty"
        assert entry.get("connections"), f"{k}.connections should carry the validation rule"


def test_clicking_help_renders_through_pageHelp_and_reveals_the_panel(smoke):
    assert smoke["clickError"] is None, smoke["clickError"]
    assert "help-title" in smoke["panelClickHtml"]
    assert "help-body" in smoke["panelClickHtml"]


def test_unknown_key_falls_back_to_panel_help_without_throwing(smoke):
    assert smoke["unknownClickError"] is None, smoke["unknownClickError"]
    assert smoke["unknownKeyFallbackHtml"], "expected fallback content, got nothing"


# ---------------------------------------------------------------------------
# Two content requirements the task calls out explicitly
# ---------------------------------------------------------------------------


def test_lot_size_help_says_it_does_not_filter_zips(smoke):
    for n in (1, 2):
        entry = smoke["entries"][f"housingOptMove{n}LotSize"]
        blob = " ".join(entry.values()).lower()
        assert "does not" in blob or "never" in blob or "no per-zip lot" in blob
        assert "screen" in blob or "filter" in blob


def test_disposition_help_says_keep_means_no_rental_income_modelled(smoke):
    entry = smoke["entries"]["housingOptDisposition"]
    blob = " ".join(entry.values()).lower()
    assert "keep" in blob
    assert "no rental income" in blob or "not modelled" in blob or "not modeled" in blob
    assert "phase 2" in blob


def test_panel_help_also_states_the_phase1_limitation(smoke):
    entry = smoke["entries"]["_panel"]
    blob = " ".join(entry.values()).lower()
    assert "no rental income" in blob or "not modelled" in blob or "not modeled" in blob
    assert "phase 1" in blob or "phase1" in blob


# ---------------------------------------------------------------------------
# CSS (Task 14 Step 3)
# ---------------------------------------------------------------------------


def test_no_inline_helper_text_under_fields():
    """Inline helper text widens every field and forces the row to wrap."""
    assert "housing-opt-hint" not in CSS


def test_selects_are_sized_to_their_longest_option():
    rule = re.search(r"\.housing-opt-field select\s*\{[^}]*\}", CSS)
    assert rule and "width:auto" in rule.group(0).replace(" ", "")


def test_year_inputs_are_narrow():
    rule = re.search(r"\.housing-opt-field input\.year\s*\{[^}]*\}", CSS)
    assert rule and "5em" in rule.group(0)


def test_zip_inputs_are_narrow():
    rule = re.search(r"\.housing-opt-field input\.zip\s*\{[^}]*\}", CSS)
    assert rule and "5em" in rule.group(0)


def test_money_and_count_inputs_are_wider():
    rule = re.search(r"\.housing-opt-field input\.money,\.housing-opt-field input\.count\s*\{[^}]*\}", CSS)
    assert rule and "8em" in rule.group(0)


def test_no_inline_width_styles_remain_in_the_panel():
    assert 'style="width:' not in JS


def test_results_use_shading_and_a_rank_badge_together():
    for selector in [
        ".housing-opt-result-odd",
        ".housing-opt-result-even",
        ".housing-opt-rank",
    ]:
        assert selector in CSS, f"{selector} missing"


def test_a_result_boundary_is_ruled():
    rule = re.search(r"\.housing-opt-result\s*\+\s*\.housing-opt-result\s*\{[^}]*\}", CSS)
    assert rule and "border-top" in rule.group(0)


def test_rank_one_gets_its_own_accent():
    assert ".housing-opt-result-top .housing-opt-rank" in CSS


def test_row_and_field_layout_rules_exist():
    assert ".housing-opt-row{" in CSS.replace(" ", "")
    assert ".housing-opt-row-label{" in CSS.replace(" ", "")
    assert ".housing-opt-row-fields{" in CSS.replace(" ", "")
    assert ".housing-opt-field{" in CSS.replace(" ", "")
