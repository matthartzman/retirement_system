"""Regression test: the live client_data.csv's Wellness section is literally
named "Wellness", but rowIsRetirementWellness() and several other row filters
in dashboard.js compared against the stale section name "healthcare" (an old
pre-rename name still used correctly as an internal *domain key* elsewhere,
e.g. renderDomainBudgetPage("healthcare") -> maps to the "Wellness" section
name via domainSectionsFor -- that mapping function was correct; these row-
level comparisons bypassed it and hardcoded the wrong literal instead).

Impact confirmed via direct browser testing before the fix: the real,
editable "Wellness" step (STEPS id retirement_wellness) rendered as
completely empty -- rowsForStep('retirement_wellness') returned 0 rows for
every real household, regardless of what Wellness data was actually entered.
"""
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "frontend" / "js" / "dashboard.js"
JS_DIR = ROOT / "frontend" / "js"


def _dashboard_smoke_sources():
    mods = sorted(JS_DIR.glob("dashboard_decomp_*.js"))
    return [str(JS_DIR / "dashboard_shared_helpers.js")] + [str(m) for m in mods] + [str(JS)]


def _smoke_sources_js_array():
    return "[" + ", ".join(repr(s) for s in _dashboard_smoke_sources()) + "]"


def read_js():
    return JS.read_text(encoding="utf-8")


def test_no_stale_lowercase_healthcare_row_comparisons_remain():
    js = read_js()
    # These specific literal comparisons must never reappear: real CSV rows
    # are section "Wellness", never lowercase "healthcare". The domain-key
    # usages (renderDomainBudgetPage("healthcare"), domainSectionsFor, the
    # REPORT_SECS id) are a separate, correct internal identifier and are not
    # asserted against here.
    assert 'row.section === "healthcare"' not in js
    assert 'r.section === "healthcare"' not in js
    assert 'sec === "healthcare"' not in js
    assert 's.includes("healthcare")' not in js


def _run_smoke(rows_literal: str, call: str, tmp_path: Path) -> str:
    script = tmp_path / "wellness_section_smoke.js"
    script.write_text(textwrap.dedent(f"""
        const fs = require('fs');
        const code = {_smoke_sources_js_array()}.map(f => fs.readFileSync(f, 'utf8')).join('\\n');
        const el = () => ({{
          style: {{}}, innerHTML: '', textContent: '', value: '', disabled: false,
          classList: {{ toggle(){{}}, remove(){{}}, add(){{}}, contains(){{return false;}} }},
          setAttribute(){{}}, addEventListener(){{}}, focus(){{}}, select(){{}}, click(){{}}
        }});
        global.window = {{
          sessionStorage: {{ getItem(){{return null;}}, setItem(){{}}, removeItem(){{}} }},
          localStorage: {{ getItem(){{return null;}}, setItem(){{}} }},
          open(){{}}, addEventListener(){{}}, location: {{ href: '' }}
        }};
        global.document = {{
          getElementById(){{return el();}}, querySelector(){{return el();}}, querySelectorAll(){{return [];}}, addEventListener(){{}},
          body: {{ classList: {{ toggle(){{}}, remove(){{}}, add(){{}} }} }}
        }};
        global.fetch = async () => ({{ ok: true, text: async () => '', json: async () => ({{success:true, rows:[]}}) }});
        global.setInterval = () => 0; global.clearInterval = () => {{}};
        global.setTimeout = () => 0; global.clearTimeout = () => {{}};
        const smoke = `
          rows = {rows_literal};
          console.log(JSON.stringify({call}));
        `;
        eval(code + '\\n' + smoke);
    """), encoding="utf-8")
    return subprocess.run(
        ["node", str(script)], check=True, cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip().splitlines()[-1]


WELLNESS_ROWS = """[
    {row_index:1,section:'Wellness',subsection:'Pre-65 Bridge',label:'annual_premium_base_year',value:'12000'},
    {row_index:2,section:'Wellness',subsection:'Medicare',label:'part_b_base_premium_monthly',value:'175'},
    {row_index:3,section:'Wellness',subsection:'Medicare',label:'part_d_base_premium_monthly',value:'40'},
    {row_index:4,section:'Wellness',subsection:'Medicare',label:'part_g_base_premium_monthly',value:'200'},
    {row_index:5,section:'Wellness',subsection:'Out-of-Pocket',label:'annual_oop_estimate_today',value:'3000'},
    {row_index:6,section:'Wellness',subsection:'Out-of-Pocket',label:'medical_annual',value:'1000'},
    {row_index:7,section:'Wellness',subsection:'Out-of-Pocket',label:'dental_annual',value:'500'},
    {row_index:8,section:'Wellness',subsection:'Out-of-Pocket',label:'vision_annual',value:'300'},
    {row_index:9,section:'Wellness',subsection:'Out-of-Pocket',label:'pharmacy_annual',value:'400'}
]"""


def test_rows_for_step_retirement_wellness_matches_real_wellness_section(tmp_path):
    out = _run_smoke(WELLNESS_ROWS, "rowsForStep('retirement_wellness').map(r => r.label)", tmp_path)
    import json
    labels = json.loads(out)
    assert set(labels) == {
        "annual_premium_base_year", "part_b_base_premium_monthly",
        "part_d_base_premium_monthly", "part_g_base_premium_monthly",
        "annual_oop_estimate_today", "medical_annual", "dental_annual",
        "vision_annual", "pharmacy_annual",
    }


def test_row_is_retirement_wellness_true_for_real_section_name(tmp_path):
    out = _run_smoke(
        WELLNESS_ROWS,
        "rows.map(r => rowIsRetirementWellness(r))",
        tmp_path,
    )
    import json
    flags = json.loads(out)
    assert all(flags), f"expected every Wellness-section row to match, got {flags}"
