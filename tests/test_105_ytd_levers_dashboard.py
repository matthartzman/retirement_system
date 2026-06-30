import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ytd_tracking import ytd_summary


def write_csv(path: Path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator='\n')
        w.writeheader()
        for row in rows:
            w.writerow(row)


def test_ytd_re_tax_income_and_growth_rules(tmp_path):
    root = tmp_path
    plan_cols = ['section','subsection','label','value','units','notes']
    write_csv(root/'client_spending.csv', [
        {'section':'Cashflow','subsection':'Spending','label':'annual_spending_base_year','value':'100000'},
        {'section':'Cashflow','subsection':'Mortgage','label':'monthly_payment','value':'1000'},
        {'section':'Cashflow','subsection':'Mortgage','label':'annual_real_estate_taxes','value':'0'},
        {'section':'Cashflow','subsection':'Mortgage','label':'real_estate_tax_annual_adjustment_pct','value':'2%'},
    ], plan_cols)
    write_csv(root/'client_income.csv', [
        {'section':'Cashflow','subsection':'Earned Income','label':'annual_earned_income','value':'100000'},
        {'section':'Cashflow','subsection':'Earned Income','label':'earned_income_start_year','value':'2026'},
        {'section':'Cashflow','subsection':'Earned Income','label':'earned_income_last_year','value':'2026'},
        {'section':'Cashflow','subsection':'Earned Income','label':'earned_income_annual_increase','value':'0%'},
    ], plan_cols)
    write_csv(root/'ytd_transactions.csv', [
        {'Date':'2025-06-01','Merchant':'County','Category':'Real Estate Taxes','Account':'Checking','Original Statement':'DUPAGE CO TAX','Notes':'','Amount':'-2000','Tags':'','Owner':'Shared'},
        {'Date':'2025-09-01','Merchant':'County','Category':'Real Estate Taxes','Account':'Checking','Original Statement':'DUPAGE CO TAX','Notes':'','Amount':'-2000','Tags':'','Owner':'Shared'},
        {'Date':'2026-06-30','Merchant':'Employer','Category':'Paychecks','Account':'Checking','Original Statement':'payroll','Notes':'','Amount':'40000','Tags':'','Owner':'Shared'},
        {'Date':'2026-06-30','Merchant':'RedMane','Category':'RedMane Annual Note P&I','Account':'Checking','Original Statement':'note payment','Notes':'','Amount':'12000','Tags':'','Owner':'Shared'},
        {'Date':'2026-06-30','Merchant':'Broker','Category':'Dividends and Capital Gains','Account':'Investment Tx','Original Statement':'dividend','Notes':'','Amount':'1000','Tags':'','Owner':'Shared'},
    ], ['Date','Merchant','Category','Account','Original Statement','Notes','Amount','Tags','Owner'])
    write_csv(root/'ytd_account_setup.csv', [
        {'Account':'Investment Tx','Role':'Investment','Mapped Investment Account':'InvAcct','Prior Year End Date':'2025-12-31','Prior Year End Balance':'1000','Current Value':'','Current Balance':'','Notes':''},
        {'Account':'Checking','Role':'Cash / spending','Mapped Investment Account':'','Prior Year End Date':'2025-12-31','Prior Year End Balance':'500','Current Value':'650','Current Balance':'650','Notes':''},
    ], ['Account','Role','Mapped Investment Account','Prior Year End Date','Prior Year End Balance','Current Value','Current Balance','Notes'])
    write_csv(root/'client_holdings.csv', [
        {'account':'InvAcct','symbol':'VTI','purchase_date':'2025-12-31','shares':'10','purchase_price':'100','current_price':'120','lot_type':'buy'},
    ], ['account','symbol','purchase_date','shares','purchase_price','current_price','lot_type'])

    s = ytd_summary(root, today=date(2026, 6, 30))
    assert s['forecast']['spending_plan_components']['real_estate_taxes'] > 4000
    assert s['forecast']['earned_income_remaining'] == 60000
    assert s['actual']['note_receivable_income'] == 12000
    assert s['forecast']['note_receivable_income_non_extrapolated'] == 12000
    assert s['actual']['growth'] == 200
    rows = s['investment_balance']['account_growth_rows']
    assert any(r['account'] == 'Investment Tx' and r['growth'] == 200 for r in rows)
    assert not any(r['account'] == 'Checking' for r in rows)  # Cash/spending roles excluded from growth rows


def test_planning_levers_ui_and_workbook_source_present():
    js = Path('frontend/js/dashboard.js').read_text(encoding='utf-8')
    wb = Path('src/reporting/workbook_builder.py').read_text(encoding='utf-8')
    common = Path('src/reporting/workbook_common.py').read_text(encoding='utf-8')
    assert "id:'planning_levers'" in js
    assert 'renderPlanningLevers' in js
    assert '2H. Planning Levers' in common
    assert 'build_sheet27_planning_levers' in wb
    assert 'RANK.EQ' in wb
