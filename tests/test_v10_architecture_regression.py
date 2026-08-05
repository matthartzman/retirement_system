from __future__ import annotations

from pathlib import Path
import sqlite3

from src import local_store
from src.domain_models import plan_input_from_sectioned_data, money_cents
from src.local_store import import_sectioned_plan, latest_sectioned_data, init_local_store
from src.tax_law import load_tax_law_dataset, dataset_freshness_summary
from src.projection_pipeline import run_projection_pipeline, DEFAULT_STAGE_ORDER
from src.results_model import build_result_explorer_model, RESULTS_MODEL_SCHEMA
from src.report_spec import report_spec_from_results_model


def test_v10_typed_plan_input_and_local_store_round_trip(tmp_path):
    data = {
        'Household': {'Client': {'husband_name': 'Matt', 'wife_name': 'Pat'}},
        'Spending': {'Core': {'annual_spending_base_year': '$200,000', 'core_spending_growth_mode': 'manual', 'manual_core_spending_increase_pct': '3%'}},
        'Cashflow': {'Mortgage': {'annual_mortgage_payment': '$36,000', 'annual_real_estate_taxes': '$18,000', 'real_estate_tax_annual_adjustment_pct': '2.5%'}},
        'YTD Account Setup': {'Offline House': {'Account Type': 'Real estate', 'Current Value': '$750,000', 'Prior Year End Balance': '$725,000'}},
    }
    plan = plan_input_from_sectioned_data(data)
    assert plan.schema == 'plan_input_v10'
    assert plan.members[0].display_name == 'Matt'
    assert plan.spending_policy.annual_core_spending_cents == money_cents('$200,000')
    db = tmp_path / 'store.db'
    sid = import_sectioned_plan(data, db_path=db)
    assert sid
    assert latest_sectioned_data(db)['Cashflow']['Mortgage']['annual_real_estate_taxes'] == '$18,000'
    with sqlite3.connect(db) as con:
        assert con.execute('select count(*) from plan_snapshots').fetchone()[0] == 1


def test_latest_sectioned_data_breaks_same_second_ties_by_recency(tmp_path, monkeypatch):
    """System review 2026-07-21 (Q4 e2e audit): created_at has only second
    precision (now_utc() truncates to seconds), so two distinct-content saves
    landing in the same wall-clock second -- routine for a save-then-sync-
    then-build sequence, e.g. a user edit followed immediately by a workbook
    build -- used to make `ORDER BY created_at DESC LIMIT 1` resolve "latest"
    arbitrarily between them. rowid (monotonic per INSERT) now breaks the tie
    in favor of the actually-latest snapshot."""
    monkeypatch.setattr(local_store, 'now_utc', lambda: '2026-01-01T00:00:00Z')

    def _data(mortgage):
        return {
            'Household': {'Client': {'husband_name': 'Matt', 'wife_name': 'Pat'}},
            'Spending': {'Core': {'annual_spending_base_year': '$200,000', 'core_spending_growth_mode': 'manual', 'manual_core_spending_increase_pct': '3%'}},
            'Cashflow': {'Mortgage': {'annual_mortgage_payment': mortgage, 'annual_real_estate_taxes': '$18,000', 'real_estate_tax_annual_adjustment_pct': '2.5%'}},
            'YTD Account Setup': {'Offline House': {'Account Type': 'Real estate', 'Current Value': '$750,000', 'Prior Year End Balance': '$725,000'}},
        }

    db = tmp_path / 'store.db'
    import_sectioned_plan(_data('$36,000'), db_path=db)
    import_sectioned_plan(_data('$40,000'), db_path=db)

    with sqlite3.connect(db) as con:
        created_ats = [r[0] for r in con.execute('SELECT created_at FROM plan_snapshots').fetchall()]
    assert len(set(created_ats)) == 1, "test setup didn't actually reproduce a same-second tie"

    assert latest_sectioned_data(db)['Cashflow']['Mortgage']['annual_mortgage_payment'] == '$40,000'


def test_v10_tax_law_dataset_has_no_embedded_fallbacks():
    ds = load_tax_law_dataset()
    val = ds.lookup('standard_deduction', 2024, filing_status='MFJ')
    assert val.value > 0
    summary = dataset_freshness_summary()
    assert summary['schema'] == 'tax_law_v10'
    assert summary['value_count'] >= 5


def test_v10_projection_pipeline_contract_uses_named_stages():
    def fake_project(c):
        return [{'year': 2026, 'total_nw': 1000, 'h_age': 60, 'w_age': 58}]
    result = run_projection_pipeline({'plan_start': 2026}, engine_project=fake_project)
    names = [s.name for s in DEFAULT_STAGE_ORDER]
    assert names[:3] == ['DeathTransition', 'AssetAppreciation', 'EarnedIncome']
    assert result.rows[0]['year'] == 2026
    assert any(e.stage == 'ProjectionEngine' and e.event_type == 'completed' for e in result.events)


def test_v10_results_model_and_report_spec_are_renderer_neutral():
    rows = [{'year': 2026, 'h_age': 60, 'w_age': 58, 'total_nw': 1000000, 'earned': 100000, 'fed_tax': 10000, 'state_tax': 5000, 'spend_base_yr': 90000}]
    model = build_result_explorer_model({'plan_start': 2026, 'plan_end': 2026, 'h_name': 'Matt', 'w_name': 'Pat'}, rows, {'success_rate': 0.95})
    assert model['schema'] == RESULTS_MODEL_SCHEMA == 'results_model_v10'
    assert model['source'] == 'semantic_results_model'
    spec = report_spec_from_results_model(model)
    assert spec.schema == 'report_spec_v10'
    assert any(p.name == 'Cash Flow' for p in spec.pages)


