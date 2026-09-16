r"""The spending screen and the optimizer describe the same dwelling (§10).

The plan's own draft test extracted select options with
``js.split(select_id)[1].split('</select>')[0]`` plus a
``re.findall(r'value="([^"]+)"', block)`` regex, on the theory that each select's
options appear as literal ``<option value="...">`` markup near its id in the
source text. That assumption doesn't hold for either file: after Task 16's
extraction, both the optimizer panel
(``frontend/js/dashboard_decomp_housing_optimizer.js``) and the spending
screen's next-housing-step fields
(``frontend/js/dashboard_decomp_housing_scenarios.js``) build every dwelling
select from an array of ``{value, label}`` objects (``HOUSING_DWELLING_OPTIONS``
in ``frontend/js/dashboard_shared_helpers.js``, the two screens' single shared
source), assembled into ``<option>`` tags at render time by a small helper
(``housingOptSelect`` / ``_housingDwellingSelect``). The optimizer file has only
three literal ``<option value=`` strings in it (unrelated one-offs) and the
scenarios file only one (the empty "Select area type" placeholder) -- nowhere
near the five to six option values each dwelling field actually renders. A
regex over the raw source finds nothing for four of the five parametrized
fields below and would make the comparison vacuously true or throw.

This file instead runs the three files together in node (no jsdom needed --
every render function here is pure string building) exactly the way
tests/test_housing_optimizer_panel_functional.py's ``_run_node_smoke`` already
does for the same module, and inspects two things per field:

  1. the REAL rendered HTML -- ``renderHousingOptimizePanelHtml()`` for the
     optimizer (whose per-field ids, e.g. ``housingOptMove1AreaType``, only
     exist in the assembled output, never as source-text literals) and the
     exported ``housing<Field>Select(row)`` functions for the spending screen
     (called directly with a synthetic row, the same way
     dashboard_decomp_housing_scenarios.js's own renderer calls them); and
  2. the shared ``HOUSING_DWELLING_OPTIONS`` array both screens render from,
     read back out of the sandbox's ``window`` after evaluation.

Comparing the rendered HTML is the primary assertion (it is what a user
actually sees); comparing the arrays is a cheap, redundant backstop that
would catch a screen quietly bypassing the shared source without changing its
own visible output in this particular fixture.
"""
from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from src.server_services.strategy_asset_service import HOUSING_SEED_ROWS

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SHARED_HELPERS_PATH = ROOT / "frontend" / "js" / "dashboard_shared_helpers.js"
ROW_MODEL_PATH = ROOT / "frontend" / "js" / "dashboard_decomp_row_model.js"
OPTIMIZER_PATH = ROOT / "frontend" / "js" / "dashboard_decomp_housing_optimizer.js"
SCENARIOS_PATH = ROOT / "frontend" / "js" / "dashboard_decomp_housing_scenarios.js"

OPTIMIZER_JS = OPTIMIZER_PATH.read_text(encoding="utf-8")
SCENARIOS_JS = SCENARIOS_PATH.read_text(encoding="utf-8")


def _seed_keys(section):
    return {r[2] for r in HOUSING_SEED_ROWS if r[1] == section}


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], check=True, capture_output=True)
        return True
    except Exception:
        return False


NODE_AVAILABLE = _node_available()


def _run_node_extraction(tmp_path: Path) -> dict:
    """Evaluates dashboard_shared_helpers.js + both housing modules in node,
    then extracts real rendered <select> option sets: the optimizer's from the
    actual assembled panel HTML (its ids exist only there), the spending
    screen's by calling its exported housing<Field>Select(row) functions
    directly with a synthetic row (a plain object carrying the row_index and
    label/value fields those functions read), plus the shared
    HOUSING_DWELLING_OPTIONS array itself as a cross-check.
    """
    # dashboard_decomp_row_model.js is needed alongside the two housing
    # modules for norm()/valOf(), which housing<Field>Select(row) calls; it
    # loads before both housing modules in index.html. `dirty` is the one
    # binding it in turn reaches back into dashboard.js for (see that
    # module's own header comment) -- stubbed below as an empty Map, which is
    # exactly what a fresh, unedited row looks like.
    files = [SHARED_HELPERS_PATH, ROW_MODEL_PATH, OPTIMIZER_PATH, SCENARIOS_PATH]
    files_js_array = "[" + ", ".join(repr(str(p)) for p in files) + "]"
    script = tmp_path / "housing_screen_parity.js"
    harness = textwrap.dedent(f"""
        const fs = require('fs');
        const code = {files_js_array}.map(f => fs.readFileSync(f, 'utf8')
          .replace(/^export (async )?function /gm, '$1function ')
          .replace(/^export (const|let|var) /gm, '$1 ')
        ).join('\\n');

        global.window = {{}};
        global.dirty = new Map();
        let evalError = null;
        try {{
          eval(code);
        }} catch (e) {{
          evalError = String((e && e.stack) || e);
        }}

        const result = {{ evalError }};

        if (!evalError) {{
          result.sharedOptions = window.HOUSING_DWELLING_OPTIONS;

          let panelHtml = '';
          let panelError = null;
          try {{
            panelHtml = window.renderHousingOptimizePanelHtml();
          }} catch (e) {{
            panelError = String((e && e.stack) || e);
          }}
          result.panelError = panelError;
          result.panelHtml = panelHtml;

          function fakeRow(value) {{
            return {{ row_index: 1, label: 'x', value: value }};
          }}
          // valOf(row) in dashboard_decomp_row_model.js reads dirty-overlay
          // state first, falling back to row.value -- a plain {{value}} object
          // is exactly what that fallback path reads.
          result.spendingSelects = {{
            housingAreaTypeSelect: window.housingAreaTypeSelect(fakeRow('')),
            housingBedroomsSelect: window.housingBedroomsSelect(fakeRow('3')),
            housingBathroomsSelect: window.housingBathroomsSelect(fakeRow('2')),
            housingPropertyTypeSelect: window.housingPropertyTypeSelect(fakeRow('single_family')),
            housingSqftBandSelect: window.housingSqftBandSelect(fakeRow('1800_2500')),
            housingLotSizeSelect: window.housingLotSizeSelect(fakeRow('quarter_half')),
          }};
        }}

        console.log(JSON.stringify(result));
    """)
    script.write_text(harness, encoding="utf-8")
    proc = subprocess.run(["node", str(script)], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        pytest.fail(f"node extraction script failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def extraction():
    if not NODE_AVAILABLE:
        pytest.skip("node is not available in this environment")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        yield _run_node_extraction(Path(td))


def _select_block(html: str, select_id: str) -> str:
    marker = f'id="{select_id}"'
    assert marker in html, f"no element with {marker} in rendered HTML"
    block = html.split(marker, 1)[1]
    assert "</select>" in block, f"{marker} is not inside a <select>...</select>"
    return block.split("</select>", 1)[0]


def _values(block: str) -> set[str]:
    return set(re.findall(r'value="([^"]*)"', block))


def _optimizer_options(panel_html: str, select_id: str) -> set[str]:
    return _values(_select_block(panel_html, select_id))


def _spending_options(spending_selects: dict, fn_name: str) -> set[str]:
    return _values(spending_selects[fn_name])


# ---------------------------------------------------------------------------
# Node evaluation sanity
# ---------------------------------------------------------------------------


def test_modules_evaluate_and_render_cleanly(extraction):
    assert extraction["evalError"] is None, extraction["evalError"]
    assert extraction["panelError"] is None, extraction["panelError"]
    assert extraction["panelHtml"], "renderHousingOptimizePanelHtml() returned no HTML"


# ---------------------------------------------------------------------------
# Seed-row coverage (strategy_asset_service.py)
# ---------------------------------------------------------------------------


def test_both_next_steps_carry_the_full_dwelling_spec():
    expected = {'bedrooms', 'bathrooms', 'property_type', 'sqft_band',
                'lot_size_band', 'built_within_years', 'zip_code'}
    for section in ('next_step_1', 'next_step_2'):
        assert expected <= _seed_keys(section), f'{section} missing {expected - _seed_keys(section)}'


def test_the_seed_descriptions_name_all_four_area_types():
    for row in HOUSING_SEED_ROWS:
        if row[2] == 'city_type':
            assert 'exurban' in row[5], row


def test_lot_size_band_is_purchase_only_with_the_expected_default():
    for section in ('next_step_1', 'next_step_2'):
        row = next(r for r in HOUSING_SEED_ROWS if r[1] == section and r[2] == 'lot_size_band')
        assert row[3] == 'quarter_half'
        assert 'purchase only' in row[5].lower()


def test_zip_code_is_optional_and_not_type_restricted():
    for section in ('next_step_1', 'next_step_2'):
        row = next(r for r in HOUSING_SEED_ROWS if r[1] == section and r[2] == 'zip_code')
        assert row[3] == ''
        assert 'optional' in row[5].lower()


# ---------------------------------------------------------------------------
# Shared source (HOUSING_DWELLING_OPTIONS in dashboard_shared_helpers.js)
# ---------------------------------------------------------------------------


def test_shared_area_types_have_no_wildcard_and_include_exurban(extraction):
    values = {o['value'] for o in extraction['sharedOptions']['areaTypes']}
    assert values == {'urban', 'suburban', 'exurban', 'rural'}
    assert 'any' not in values


# ---------------------------------------------------------------------------
# Rendered-option parity: optimizer's real panel HTML vs. the spending
# screen's real exported select functions, both read from the shared source.
# ---------------------------------------------------------------------------


def test_area_type_includes_exurban_on_both_screens(extraction):
    spending = _values(extraction['spendingSelects']['housingAreaTypeSelect'])
    optimizer = _optimizer_options(extraction['panelHtml'], 'housingOptMove1AreaType')
    assert 'exurban' in spending
    assert 'exurban' in optimizer


def test_area_type_option_sets_are_identical_except_the_optimizers_wildcard(extraction):
    spending = _values(extraction['spendingSelects']['housingAreaTypeSelect']) - {''}
    optimizer = _optimizer_options(extraction['panelHtml'], 'housingOptMove1AreaType') - {'any'}
    assert spending == optimizer


@pytest.mark.parametrize('spending_fn, optimizer_id', [
    ('housingBedroomsSelect', 'housingOptMove1Bedrooms'),
    ('housingBathroomsSelect', 'housingOptMove1Bathrooms'),
    ('housingPropertyTypeSelect', 'housingOptMove1PropertyType'),
    ('housingSqftBandSelect', 'housingOptMove1SqftBand'),
    ('housingLotSizeSelect', 'housingOptMove1LotSize'),
])
def test_dwelling_option_sets_match_field_for_field(extraction, spending_fn, optimizer_id):
    spending = _spending_options(extraction['spendingSelects'], spending_fn)
    optimizer = _optimizer_options(extraction['panelHtml'], optimizer_id)
    assert spending == optimizer


# ---------------------------------------------------------------------------
# Cross-link copy
# ---------------------------------------------------------------------------


def test_the_cross_link_names_what_carries_across():
    assert 'Optimize next housing move' in SCENARIOS_JS
    for word in ('ZIP', 'price', 'distance'):
        assert word in SCENARIOS_JS
