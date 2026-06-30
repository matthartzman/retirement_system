from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]


def test_roth_conversion_controls_moved_to_user_ui_not_admin_editor():
    admin = (ROOT / 'frontend/js/admin.js').read_text(encoding='utf-8')
    user = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert "id:'roth_conversion'" in user
    assert "Roth conversion strategy" in user
    assert "sec==='Withdrawal Policy'&&sub==='roth_conversion'" in user
    assert "sec==='Model Constants'&&sub==='irmaa'" in user
    assert "title:'Roth conversion controls'" not in admin


def test_schema_exposes_roth_optimizer_governance_controls():
    labels = set()
    with (ROOT / 'reference_data/schema.csv').open(newline='', encoding='utf-8') as f:
        for row in csv.reader(f):
            if len(row) > 2:
                labels.add(row[2])
    assert {'roth_objective_mode','estate_tax_objective_mode','roth_headroom_usage_pct','irmaa_guardrail_mode','roth_irmaa_headroom_usage_pct'} <= labels


def test_engine_parses_and_uses_headroom_and_estate_controls():
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    engine = (ROOT / 'src/planning_engines.py').read_text(encoding='utf-8')
    assert "c['roth_objective_mode']" in data_io
    assert "c['estate_tax_objective_mode']" in data_io
    assert "c.get('roth_headroom_usage_pct'" in engine
    assert "estate_tax_penalty" in engine


def test_roth_user_page_uses_visible_purpose_built_layout():
    user = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'function renderRothConversion()' in user
    assert 'details class="roth-section"' in user or "details class='roth-section'" in user
    assert "ROTH_PRIMARY_LABELS" in user
    assert "ROTH_IRMAA_LABELS=['irmaa_guardrail_mode','roth_irmaa_target_tier','roth_irmaa_headroom_usage_pct','irmaa_annual_inflator']" in user
    assert "ROTH_LEGACY_IRMAA_LABELS" not in user
    assert "ROTH_LEGACY_LABELS=['roth_objective_mode','estate_tax_objective_mode','legacy_objective_mode'" in user
    assert "roth_conversion')content+=" in user and "renderRothConversion" in user


def test_choice_schema_fields_render_as_select_controls():
    user = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'function choiceOptions' in user
    assert "type==='choice'||norm(units)==='choice'" in user
    assert '<select data-row=' in user


def test_runtime_backfills_missing_roth_controls_for_older_plan_data():
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    assert 'ROTH_UI_PLAN_DATA_ROWS' in app_core
    assert 'def _ensure_roth_ui_plan_data_rows()' in app_core
    assert '_ensure_roth_ui_plan_data_rows()' in app_core
    for label in ['roth_objective_mode', 'estate_tax_objective_mode', 'roth_headroom_usage_pct', 'irmaa_guardrail_mode', 'roth_irmaa_headroom_usage_pct', 'roth_irmaa_target_tier']:
        assert label in app_core
