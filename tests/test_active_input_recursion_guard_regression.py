from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "frontend" / "js" / "dashboard.js"
JS_DIR = ROOT / "frontend" / "js"


def _dashboard_smoke_sources():
    """dashboard_shared_helpers.js, dashboard.js, and every extracted
    dashboard_decomp_*.js module.

    The decomposition moved cohesive blocks (e.g. the estate/insurance UI) out
    of dashboard.js into sibling classic scripts loaded before dashboard.js in
    index.html. The node smoke harness must load them together so boot code and
    any exercised function still resolve, mirroring the browser load order.
    esc/escJs/fmtMoney/fmtPct live in dashboard_shared_helpers.js (A13), loaded
    first in index.html - same requirement here.
    """
    mods = sorted(JS_DIR.glob("dashboard_decomp_*.js"))
    return [str(JS_DIR / "dashboard_shared_helpers.js")] + [str(m) for m in mods] + [str(JS)]


def _smoke_sources_js_array():
    return "[" + ", ".join(repr(s) for s in _dashboard_smoke_sources()) + "]"


def read_js():
    return JS.read_text(encoding="utf-8")


def test_active_input_mode_helpers_do_not_call_filtered_rows_for_step():
    js = read_js()
    assert 'function coreSpendingGrowthMode() {\n  const r =\n    findEditableRow("Cashflow", "Spending", "core_spending_growth_mode")' in js
    assert "function mcEngineModeValue() {\n  const r =\n    rows.find(\n      (x) =>\n        isEditable(x) &&" in js
    assert 'function rowByNormLabel(label) {\n  const key = norm(label);\n  return (\n    rawRowsForStep("roth_conversion")' in js
    assert "function coreSpendingGrowthMode(){const r=rowsForStep('spending_core')" not in js
    assert "function mcEngineModeValue(){const r=rowsForStep('monte_carlo_options')" not in js
    assert "function rowByNormLabel(label){const key=norm(label);return rowsForStep('roth_conversion')" not in js


def test_active_input_usage_state_smoke_does_not_recurse(tmp_path):
    script = tmp_path / "dashboard_recursion_smoke.js"
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
          rows = [
            {{row_index:1,section:'Cashflow',subsection:'Spending',label:'core_spending_growth_mode',value:'cpi'}},
            {{row_index:2,section:'Cashflow',subsection:'Spending',label:'core_spending_manual_growth_rate',value:'5%'}},
            {{row_index:3,section:'Model Constants',subsection:'Monte_Carlo',label:'mc_engine_mode',value:'quick_vectorized'}},
            {{row_index:4,section:'Model Constants',subsection:'Monte_Carlo',label:'stochastic_tax_brackets',value:'YES'}},
            {{row_index:5,section:'Withdrawal Policy',subsection:'Roth_Conversion',label:'roth_conversion_policy',value:'none'}},
            {{row_index:6,section:'Withdrawal Policy',subsection:'Roth_Conversion',label:'roth_fixed_annual_amount',value:'10000'}},
            {{row_index:7,section:'Model Constants',subsection:'IRMAA',label:'irmaa_guardrail_mode',value:'OFF'}},
            {{row_index:8,section:'Model Constants',subsection:'IRMAA',label:'irmaa_annual_inflator',value:'2%'}}
          ];
          rows.map(r => rowBuildUsageState(r, 'all_assumptions'));
          overallStats();
          renderSteps();
        `;
        eval(code + '\\n' + smoke);
    """), encoding="utf-8")
    subprocess.run(["node", str(script)], check=True, cwd=ROOT)
