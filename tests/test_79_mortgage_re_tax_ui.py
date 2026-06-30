from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mortgage_re_tax_ui_and_reporting_labels_are_present():
    js = (ROOT / 'frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'Mortgage and RE Tax' in js
    assert 'Annual Real Estate Taxes' in js
    assert 'Annual RE Tax Adjustment' in js
    assert 'real_estate_tax_annual_adjustment_pct' in js
    assert 'Top 20 YTD income categories' not in js
    assert '<th>Current Balance</th>' not in js
    assert 'Top 20 YTD spending categories' not in js

    index = (ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    assert '?v=' in index

    projection = (ROOT / 'src/reporting/sheets_projection.py').read_text(encoding='utf-8')
    assert 'real_estate_tax' in projection


def test_server_backfills_real_estate_tax_input_row():
    app_core = (ROOT / 'src/server/app_core.py').read_text(encoding='utf-8')
    assert 'MORTGAGE_RE_TAX_UI_PLAN_DATA_ROWS' in app_core
    assert 'annual_real_estate_taxes' in app_core
    assert 'real_estate_tax_annual_adjustment_pct' in app_core
    assert 'insert_after=("Cashflow", "Mortgage")' in app_core


def test_engine_uses_dedicated_real_estate_tax_adjustment_rate():
    engine = (ROOT / 'src/planning_engines.py').read_text(encoding='utf-8')
    data_io = (ROOT / 'src/data_io.py').read_text(encoding='utf-8')
    schema = (ROOT / 'reference_data/schema.csv').read_text(encoding='utf-8')

    assert 'real_estate_tax_growth_rate' in data_io
    assert 'real_estate_tax_annual_adjustment_pct' in data_io
    assert "c.get('real_estate_tax_growth_rate'" in engine
    assert 'real_estate_tax_annual_adjustment_pct,percent' in schema
