from pathlib import Path
import csv
import pytest

ROOT = Path(__file__).resolve().parents[1]
from tests._decomp_dashboard import dashboard_js_text

from conftest import TEST_INPUT_DIR

ROTH_PRIMARY = {
    'roth_conversion_policy',
    'roth_objective_mode',
    'estate_tax_objective_mode',
    'roth_headroom_usage_pct',
    'roth_target_bracket_rate',
    'roth_irmaa_target_tier',
    'irmaa_guardrail_mode',
    'roth_irmaa_headroom_usage_pct',
    'roth_fixed_annual_amount',
}


def _norm(s: str) -> str:
    import re
    return re.sub(r'[^a-z0-9]+', '_', str(s or '').lower()).strip('_')


def test_user_ui_roth_step_matches_normalized_subsection_names():
    js = dashboard_js_text()
    js += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert 'case "roth_conversion"' in js
    # rowsForStep() normalizes subsection names before comparison. Comparing to
    # title-case values made only forced-conversion rows visible.
    assert '(sec === "Withdrawal Policy" &&' in js
    assert 'sec === "Model Constants" && sub === "roth_conversion"' in js
    assert 'sec === "Model Constants" &&\n            sub === "irmaa"' in js
    assert "sub==='Roth Conversion'" not in js


def test_input_package_contains_all_primary_roth_controls_with_defaults():
    p = TEST_INPUT_DIR / 'client_policy.csv'
    if not p.exists():
        pytest.skip('secure complete package excludes input/; run with input overlay for Plan Data assertions')
    with p.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    labels = {
        r['label'] for r in rows
        if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'
    }
    assert ROTH_PRIMARY <= labels
    defaults = {r['label']: r['value'] for r in rows if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'}
    # The frozen sample household explicitly overrides this to
    # MAXIMIZE_TERMINAL_NET_WORTH (reference_data/schema.csv's own declared
    # default is BALANCED_RETIREMENT -- this asserts the fixture's actual
    # per-household choice, not the schema default).
    assert defaults['roth_objective_mode'] == 'MAXIMIZE_TERMINAL_NET_WORTH'
    assert defaults['estate_tax_objective_mode'] == 'BALANCED'
    assert defaults['roth_headroom_usage_pct'] == '100.00%'
    assert defaults['roth_irmaa_headroom_usage_pct'] == '100.00%'
    assert defaults['roth_irmaa_target_tier'] == 'TIER_2'


def test_roth_step_filter_would_return_controls_from_input_rows():
    p = TEST_INPUT_DIR / 'client_policy.csv'
    if not p.exists():
        pytest.skip('secure complete package excludes input/; run with input overlay for Plan Data assertions')
    with p.open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    ui_rows = [
        r for r in rows
        if (r['section'] == 'Withdrawal Policy' and _norm(r['subsection']) == 'roth_conversion')
        or (r['section'] == 'Model Constants' and _norm(r['subsection']) in {'roth_conversion', 'irmaa'})
        or (r['section'] == 'Forced Actions' and 'roth' in _norm(r['label']))
    ]
    labels = {r['label'] for r in ui_rows}
    assert ROTH_PRIMARY <= labels
    assert 'roth_conversion_wife_ira_to_roth' not in labels
    assert len(ui_rows) >= 15


def test_roth_conversion_controls_moved_to_user_ui_not_admin_editor():
    """Roth conversion controls live in main UI (dashboard.js), not admin.js."""
    admin = (ROOT / 'frontend/js/admin.js').read_text(encoding='utf-8')
    user = dashboard_js_text()
    user += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert 'id: "roth_conversion"' in user
    assert "Roth conversion strategy" in user
    assert '(sec === "Withdrawal Policy" &&' in user
    assert 'sec === "Model Constants" &&\n            sub === "irmaa"' in user
    assert "title:'Roth conversion controls'" not in admin


def test_schema_exposes_roth_optimizer_governance_controls():
    """Reference data schema includes roth objective and headroom controls."""
    labels = set()
    with (ROOT / 'reference_data/schema.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) > 2:
                labels.add(row[2])
    assert {'roth_objective_mode','estate_tax_objective_mode','roth_headroom_usage_pct','irmaa_guardrail_mode','roth_irmaa_headroom_usage_pct'} <= labels


def test_engine_parses_and_uses_headroom_and_estate_controls():
    """Engine reads and applies roth objective, headroom, and estate tax controls."""
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    engine = (ROOT / 'src/planning_engines.py').read_text(encoding='utf-8')
    assert "c['roth_objective_mode']" in data_io
    assert "c['estate_tax_objective_mode']" in data_io
    assert "c.get('roth_headroom_usage_pct'" in engine
    assert "estate_tax_penalty" in engine


def test_roth_user_page_uses_visible_purpose_built_layout():
    """Roth step has purpose-built layout with section details, label arrays, content rendering."""
    user = dashboard_js_text()
    user += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert 'function renderRothConversion()' in user
    assert 'details class="roth-section"' in user or "details class='roth-section'" in user
    assert "ROTH_PRIMARY_LABELS" in user
    assert (
        'const ROTH_IRMAA_LABELS = [\n  "irmaa_guardrail_mode",\n  "roth_irmaa_target_tier",\n  "roth_irmaa_headroom_usage_pct",\n  "irmaa_annual_inflator",\n];'
        in user
    )
    assert "ROTH_LEGACY_IRMAA_LABELS" not in user
    assert (
        'const ROTH_LEGACY_LABELS = [\n  "roth_objective_mode",\n  "estate_tax_objective_mode",\n  "legacy_objective_mode",'
        in user
    )
    assert 'roth_conversion")\n    content +=' in user and "renderRothConversion" in user


def test_choice_schema_fields_render_as_select_controls():
    """Choice-type fields render as HTML select dropdowns."""
    user = dashboard_js_text()
    user += (ROOT / 'frontend/js/dashboard_decomp_row_model.js').read_text(encoding='utf-8')
    assert 'function choiceOptions' in user
    assert 'type === "choice" || norm(units) === "choice"' in user
    assert '<select data-row=' in user


def test_runtime_backfills_missing_roth_controls_for_older_plan_data():
    """App backfills missing roth controls on load via PLAN_DATA_BACKFILL_ENTRIES table."""
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    assert 'ROTH_UI_PLAN_DATA_ROWS' in app_core
    for label in ['roth_objective_mode', 'estate_tax_objective_mode', 'roth_headroom_usage_pct', 'irmaa_guardrail_mode', 'roth_irmaa_headroom_usage_pct', 'roth_irmaa_target_tier']:
        assert label in app_core

    # A7 (Wave 3 item 3.12): backfilling itself is now the declarative
    # PLAN_DATA_BACKFILL_ENTRIES table over src/plan_data_backfill.py's
    # batched engine, not a dedicated _ensure_roth_ui_plan_data_rows()
    # function - assert this row set is actually wired into that table.
    import src.server.app_core as ac
    assert any(
        entry.rows is ac.ROTH_UI_PLAN_DATA_ROWS
        for entry in ac.PLAN_DATA_BACKFILL_ENTRIES
    )


def test_phase_varying_added_to_bracket_strategy_choice_enum():
    js = dashboard_js_text()
    assert '"PHASE_VARYING"' in js
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    assert '"PHASE_VARYING"' in app_core
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    assert "'PHASE_VARYING'" in data_io


def test_phase_varying_config_fields_present_in_schema_and_backfill():
    labels = set()
    with (ROOT / 'reference_data/schema.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) > 2:
                labels.add(row[2])
    expected = {
        'roth_phase_first_bracket_rate', 'roth_phase_second_bracket_rate',
        'roth_phase_third_bracket_rate', 'roth_phase_count',
    }
    assert expected <= labels

    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    for label in expected:
        assert label in app_core

    with (ROOT / 'input/demo/client_policy.csv').open(newline='', encoding='utf-8-sig') as f:
        demo_rows = list(csv.DictReader(f))
    demo_labels = {
        r['label'] for r in demo_rows
        if r['section'] == 'Withdrawal Policy' and r['subsection'] == 'Roth Conversion'
    }
    assert expected <= demo_labels


def test_phase_varying_labels_grouped_with_roth_primary_controls():
    js = dashboard_js_text()
    assert '"roth_phase_first_bracket_rate"' in js
    assert '"roth_phase_second_bracket_rate"' in js
    assert '"roth_phase_third_bracket_rate"' in js
    assert '"roth_phase_count"' in js
