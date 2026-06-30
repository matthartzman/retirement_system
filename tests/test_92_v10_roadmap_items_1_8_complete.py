from __future__ import annotations

import sqlite3

from src.config_backend import import_csv_to_sqlite, load_sqlite
from src.domain_models import plan_input_from_sectioned_data
from src.local_store import latest_plan_snapshot, save_plan_input
from src.projection_pipeline import run_projection_pipeline
from src.result_contract import attach_plan_result
from src.report_spec import report_spec_from_plan_result
from src.results_model import build_result_explorer_model
from src.tax_law import load_tax_law_dataset
from src.taxes import FEDERAL_BRACKETS_BASE_YEAR, load_tax_constants


def _sample_sectioned():
    return {
        'Household': {'Client': {'husband_name': 'Matt', 'wife_name': 'Pat'}},
        'Spending': {'Core': {'annual_spending_base_year': '$200,000'}},
        'Cashflow': {'Mortgage': {'annual_mortgage_payment': '$36,000', 'annual_real_estate_taxes': '$18,000'}},
        'YTD Account Setup': {
            'Brokerage': {'Account Type': 'Investment', 'Current Value': '$100,000', 'Prior Year End Balance': '$90,000'},
            'Visa': {'Account Type': 'Credit card', 'Current Value': '$-2,500'},
        },
    }


def test_items_2_3_4_5_canonical_typed_store_is_runtime_source(tmp_path):
    plan = plan_input_from_sectioned_data(_sample_sectioned())
    db = tmp_path / 'local.db'
    sid = save_plan_input(plan, source='unit', db_path=db)
    snap = latest_plan_snapshot(db)
    assert snap and snap['snapshot_id'] == sid
    assert any(a['account_id'] == 'Visa' and a['account_type'] == 'credit_card' for a in snap['accounts'])
    assert load_sqlite(db)['YTD Account Setup']['Visa']['Account Type'] == 'credit_card'
    with sqlite3.connect(db) as con:
        assert con.execute('select count(*) from plan_accounts where snapshot_id=?', (sid,)).fetchone()[0] == 2
        assert con.execute('select annual_core_spending_cents from plan_spending_policy where snapshot_id=?', (sid,)).fetchone()[0] == 20_000_000


def test_item_6_tax_law_dataset_drives_engine_tables_without_csv_requirement():
    ds = load_tax_law_dataset()
    tables = ds.as_engine_tables(2025)
    assert tables['ordinary_brackets']['MFJ'][0] == (0, 23850, 0.10)
    assert tables['standard_deduction']['MFJ'] == 30000
    registry = load_tax_constants([])
    assert registry['_v10_tax_law_dataset']['value'] >= 20
    assert FEDERAL_BRACKETS_BASE_YEAR['MFJ'][0] == (0, 23850, 0.10)


def test_items_1_2_result_contract_contains_projection_pages_report_spec_and_events():
    rows = [{'year': 2026, 'h_age': 60, 'w_age': 58, 'total_nw': 1_000_000, 'earned': 100_000, 'total_tax': 12_000, 'fed_tax': 10_000, 'state_tax': 2_000, 'spend_base_yr': 90_000}]
    c = {'plan_start': 2026, 'plan_end': 2026, 'projection_event_log': [{'stage': 'NetWorth', 'event_type': 'completed'}]}
    attach_plan_result(c, rows, {'success_rate': 0.95}, {'failures': []})
    pr = c['plan_result']
    assert pr['schema'] == 'plan_result_v10'
    assert pr['projection_rows'][0]['year'] == 2026
    assert pr['summary_metrics']['terminal_net_worth'] == 1_000_000
    assert any(p['display_name'] == 'Cash Flow' for p in pr['result_pages'])
    assert pr['report_spec']['schema'] == 'report_spec_v10'
    assert pr['event_log'][0]['stage'] == 'NetWorth'
    assert report_spec_from_plan_result(pr).schema == 'report_spec_v10'


def test_item_7_stage_pipeline_emits_completed_stage_summaries():
    rows = [{'year': 2026, 'earned': 1000, 'spend_base_yr': 500, 'total_tax': 100, 'total_nw': 9000}]
    result = run_projection_pipeline({'plan_start': 2026}, engine_project=lambda c: rows)
    by_stage = {s.stage: s.metrics for s in result.stage_summaries}
    assert by_stage['EarnedIncome']['total_earned_income'] == 1000
    assert by_stage['Spending']['total_spending'] == 500
    assert by_stage['TaxAssessment']['total_tax'] == 100
    assert by_stage['NetWorth']['terminal_net_worth'] == 9000
    assert any(e.stage == 'TaxAssessment' and e.event_type == 'completed' for e in result.events)


def test_item_8_deterministic_oracle_preserved_while_planresult_is_rich():
    calls = []
    def fake_project(c):
        calls.append(dict(c))
        return [{'year': 2026, 'total_nw': 123}]
    result = run_projection_pipeline({'x': 1}, engine_project=fake_project)
    assert calls == [{'x': 1}]
    assert result.rows == [{'year': 2026, 'total_nw': 123}]
