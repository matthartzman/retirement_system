from __future__ import annotations

from datetime import date

from src import ytd_tracking as ytd


def test_ytd_transaction_csv_header_is_strict(tmp_path):
    rows, errors = ytd.load_transactions_from_csv_text('Date,Merchant,Amount\n2026-01-01,A,-1\n')
    assert rows == []
    assert errors
    assert 'Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner' in errors[0]


def test_ytd_import_replace_and_incremental(tmp_path):
    csv_text = ytd.csv_template()
    out = ytd.import_transactions(tmp_path, csv_text, mode='replace')
    assert out['success'] is True
    assert out['added'] == 2
    assert (tmp_path / 'ytd_transactions.csv').exists()
    assert (tmp_path / 'ytd_account_setup.csv').exists()
    # Incremental reload of same rows should add nothing because latest date already exists.
    out2 = ytd.import_transactions(tmp_path, csv_text, mode='incremental')
    assert out2['success'] is True
    assert out2['added'] == 0
    assert out2['skipped'] == 2


def test_ytd_summary_gates_until_transactions_uploaded(tmp_path):
    s0 = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s0['enabled'] is False
    ytd.import_transactions(tmp_path, ytd.csv_template(), mode='replace')
    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s['enabled'] is True
    assert s['ytd_start'] == '2026-01-01'
    assert s['latest_transaction_date'] == '2026-01-31'
    assert s['actual']['spending'] == 100.43
    assert s['actual']['income'] == 0.0
    assert s['category_totals'] == [{'category': 'Groceries', 'amount': 100.43}]


def test_ytd_growth_uses_current_holdings_minus_prior_year_balance(tmp_path):
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-02-01,Transfer,Investment,Joint Brokerage,Bank,,5000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace')
    (tmp_path / 'client_holdings.csv').write_text('account,symbol,purchase_date,shares,purchase_price,lot_type\nJoint Brokerage,CASH,2026-01-01,112000,1,buy\n', encoding='utf-8')
    ytd.write_account_setup(tmp_path, [{
        'Account': 'Joint Brokerage',
        'Role': 'Investment',
        'Mapped Investment Account': 'Joint Brokerage',
        'Prior Year End Date': '2025-12-31',
        'Prior Year End Balance': '100000',
        'Notes': '',
    }])
    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s['investment_balance']['actual_growth_available'] is True
    assert s['actual']['growth'] == 12000.0
    assert s['growth_series'] == [
        {'label': '12/31', 'date': '2025-12-31', 'balance': 100000.0, 'growth': 0.0},
        {'label': 'Today', 'date': '2026-06-12', 'balance': 112000.0, 'growth': 12000.0},
    ]


def test_ytd_ui_contains_step_upload_table_and_account_mapping():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert "id:'ytd_transactions'" in text
    assert 'YTD spending and growth' in text
    assert 'Income &amp; Expense Transactions' in text
    assert 'Replace all' in text
    assert 'Add to merge new transactions' in text
    assert 'Expected YTD' in text
    assert 'Mortgage and RE Tax' in text
    assert 'annual_real_estate_taxes' in text
    assert 'real_estate_tax_annual_adjustment_pct' in text
    assert 'Top 20 YTD spending categories' not in text
    assert 'Accounts &amp; Sources' in text
    assert 'Investment current value is derived from mapped client_holdings.csv accounts' in text
    assert 'growthSeries' in text
    assert 'Current value' in text
    assert 'Income categories only' in text
    assert '<th>Current Balance</th>' not in text
    assert 'renderYtdTransactions' in text
    assert 'renderYtdAccounts' in text



def test_ytd_import_skips_non_current_year_rows(tmp_path):
    csv_text = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2025-12-31,Old,Groceries,Checking,Bank,,-10,,Household\n2026-01-02,New,Groceries,Checking,Bank,,-20,,Household\n'
    out = ytd.import_transactions(tmp_path, csv_text, mode='replace', today=date(2026, 6, 12))
    assert out['success'] is True
    assert out['added'] == 1
    assert out['skipped_not_current_year'] == 1
    rows = ytd.read_transactions(tmp_path, today=date(2026, 6, 12))
    assert len(rows) == 1
    assert rows[0]['Merchant'] == 'New'


def test_ytd_growth_is_point_to_point_and_reports_external_flows_diagnostics(tmp_path):
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-01-10,ACH,Deposit,Joint Brokerage,Bank,,5000,,Household\n2026-02-10,ETF Distribution,Dividends and Capital Gains,Joint Brokerage,Broker,,200,,Household\n2026-03-10,Transfer Out,Withdrawal,Joint Brokerage,Broker,,-1000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 12))
    (tmp_path / 'client_holdings.csv').write_text('account,symbol,purchase_date,shares,purchase_price,lot_type\nJoint Brokerage,CASH,2026-01-01,110000,1,buy\n', encoding='utf-8')
    ytd.write_account_setup(tmp_path, [{
        'Account': 'Joint Brokerage',
        'Role': 'Investment',
        'Mapped Investment Account': 'Joint Brokerage',
        'Prior Year End Date': '2025-12-31',
        'Prior Year End Balance': '100000',
        'Notes': '',
    }])
    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s['investment_balance']['external_deposits'] == 5000.0
    assert s['investment_balance']['external_withdrawals'] == 1000.0
    assert s['investment_balance']['net_ytd_investment_cashflow'] == 4000.0
    assert s['actual']['investment_income'] == 200.0
    assert s['actual']['growth'] == 10000.0
    assert s['investment_balance']['growth_method'] == 'mapped_accounts_current_value_minus_prior_year_end_balance'
    assert s['growth_series'][-1]['balance'] == 110000.0


def test_ytd_positive_cash_account_flows_net_as_refunds_not_income(tmp_path):
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-01-31,Store Refund,Groceries,Checking,Bank,,25,,Household\n2026-02-01,Grocery,Groceries,Checking,Bank,,-100,,Household\n2026-04-15,IRS,Income Tax,Checking,Bank,,-3000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 12))
    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s['actual']['earned_income'] == 0.0
    assert s['actual']['other_income'] == 0.0
    assert s['actual']['taxes'] == 3000.0
    assert s['actual']['spending'] == 75.0
    assert s['actual']['income'] == 0.0
    assert s['category_totals'] == [{'category': 'Groceries', 'amount': 75.0}]




def test_ytd_real_estate_taxes_are_housing_spending_not_income_tax(tmp_path):
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-04-01,County Treasurer,Real Estate Taxes,Checking,Bank,,-9000,,Household\n2026-04-15,IRS,Income Tax,Checking,Bank,,-3000,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 30))

    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 30))

    assert s['actual']['spending'] == 9000.0
    assert s['actual']['taxes'] == 3000.0
    assert s['category_totals'] == [{'category': 'Real Estate Taxes', 'amount': 9000.0}]


def test_ytd_spending_excludes_investment_transfers_and_uses_expected_plan_ytd(tmp_path):
    tx = '''Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner
2026-06-30,Grocery,Groceries,Checking,Bank,,-100,,Household
2026-06-30,Mortgage Co,Mortgage,Checking,Bank,,-2000,,Household
2026-06-30,Contractor,Home Improvement,Checking,Bank,,-5000,,Household
2026-06-30,Broker Buy,Buy,Checking,Bank,,-10000,,Household
2026-06-30,Broker Sell,Sell,Checking,Bank,,5000,,Household
2026-06-30,Internal Transfer,Transfer,Checking,Bank,,-1000,,Household
2026-06-30,Card Pay,Credit Card Payment,Checking,Bank,,-2000,,Household
2026-06-30,Employer,401K Match,Checking,Bank,,1000,,Household
2026-06-30,Payroll,401k Contribution,Checking,Bank,,-500,,Household
2026-06-30,HSA,HSA Contribution,Checking,Bank,,-100,,Household
2026-06-30,Best Buy,Electronics,Checking,Bank,,-50,,Household
'''
    (tmp_path / 'client_spending.csv').write_text('''section,subsection,label,value,units,notes
Cashflow,Spending,annual_spending_base_year,"$120,000",,
Cashflow,Mortgage,monthly_payment,"$3,000",,
Cashflow,Mortgage,annual_real_estate_taxes,"$12,000",USD,
Cashflow,Mortgage,real_estate_tax_annual_adjustment_pct,0.00%,percent,
Cashflow,Mortgage,last_payment_year,2030,,
Cashflow,Large Discretionary Expenses,extra_1_amount,"$12,000",USD,
Cashflow,Large Discretionary Expenses,extra_1_year,2026,year,
Cashflow,Large Discretionary Expenses,extra_2_amount,"$6,000",USD,
Cashflow,Large Discretionary Expenses,extra_2_start_year,2025,year,
Cashflow,Large Discretionary Expenses,extra_2_end_year,2027,year,
''', encoding='utf-8')
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 30))

    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 30))

    assert s['actual']['spending'] == 7150.0
    assert s['ytd_days'] == 181
    assert s['forecast']['spending_plan_components'] == {
        'core_spending': 120000.0,
        'mortgage': 48000.0,
        'mortgage_payment': 36000.0,
        'real_estate_taxes': 12000.0,
        'real_estate_tax_annual_adjustment_pct': 0.0,
        'mortgage_and_re_tax': 48000.0,
        'large_discretionary': 18000.0,
        'annual_total': 186000.0,
    }
    assert s['forecast']['spending'] == round(186000 * 181 / 365, 2)
    assert s['forecast']['spending_annualized_actual'] == round(7150 * 365 / 181, 2)


def test_ytd_status_exposes_account_dropdown_sources(tmp_path):
    tx = 'Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner\n2026-01-02,New,Groceries,Checking,Bank,,-20,,Household\n'
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 12))
    (tmp_path / 'client_holdings.csv').write_text('account,symbol,purchase_date,shares,purchase_price,lot_type\nJoint Brokerage,VTI,2026-01-01,1,100,buy\n', encoding='utf-8')
    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 12))
    assert s['transaction_accounts'] == ['Checking']
    assert s['investment_holding_accounts'] == ['Joint Brokerage']

def test_ytd_role_change_rerenders_mapping_dropdown_enabled_state():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert "if(field==='Role')renderMain()" in text
    assert 'Mapped Investment Account' in text
    assert 'ytdInvestmentOptions' in text


def test_ytd_category_totals_are_top_spending_only_and_descending(tmp_path):
    tx = """Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner
2026-02-01,A,Groceries,Checking,Bank,,-100,,Household
2026-02-02,B,Travel,Checking,Bank,,-250,,Household
2026-02-03,C,Groceries,Checking,Bank,,-75,,Household
2026-02-04,D,Transfer,Checking,Bank,,-999,,Household
2026-02-05,E,Income Tax,Checking,Bank,,-300,,Household
"""
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 30))

    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 30))

    assert s['category_totals'] == [
        {'category': 'Travel', 'amount': 250.0},
        {'category': 'Groceries', 'amount': 175.0},
    ]



def test_ytd_income_category_totals_use_only_allowed_income_categories(tmp_path):
    tx = """Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner
2026-02-01,Store Refund,Groceries,Checking,Bank,,25,,Household
2026-02-02,Employer,Paychecks,Checking,Bank,,2500,,Household
2026-02-03,RedMane,RedMane Annual Note P&I,Checking,Bank,,2000,,Household
2026-02-04,Other Deposit,other Income,Checking,Bank,,100,,Household
2026-02-05,Bank Interest,Interest,Joint Brokerage,Broker,,50,,Household
2026-02-06,ETF Distribution,Dividends and Capital Gains,Joint Brokerage,Broker,,500,,Household
2026-02-07,Old Dividend Label,Dividend,Joint Brokerage,Broker,,700,,Household
2026-02-08,Employer Bonus,Bonus,Checking,Bank,,900,,Household
2026-02-09,Grocery,Groceries,Checking,Bank,,-100,,Household
2026-02-10,Internal Transfer,Transfer,Checking,Bank,,999,,Household
2026-02-11,Broker Buy,Buy,Checking,Bank,,300,,Household
"""
    ytd.import_transactions(tmp_path, tx, mode='replace', today=date(2026, 6, 30))
    ytd.write_account_setup(tmp_path, [
        {'Account': 'Checking', 'Role': 'Cash / spending', 'Mapped Investment Account': '', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '0', 'Notes': ''},
        {'Account': 'Joint Brokerage', 'Role': 'Investment', 'Mapped Investment Account': 'Joint Brokerage', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '0', 'Notes': ''},
    ])

    s = ytd.ytd_summary(tmp_path, today=date(2026, 6, 30))

    assert s['allowed_income_categories'] == [
        'Paychecks',
        'RedMane Annual Note P&I',
        'Dividends and Capital Gains',
        'other Income',
        'Interest',
    ]
    assert s['actual']['earned_income'] == 2500.0
    assert s['actual']['investment_income'] == 550.0
    assert s['actual']['note_receivable_income'] == 2000.0
    assert s['actual']['other_income'] == 100.0
    assert s['actual']['income'] == 5150.0
    assert s['income_category_totals'] == [
        {'category': 'Paychecks', 'amount': 2500.0},
        {'category': 'RedMane Annual Note P&I', 'amount': 2000.0},
        {'category': 'Dividends and Capital Gains', 'amount': 500.0},
        {'category': 'other Income', 'amount': 100.0},
        {'category': 'Interest', 'amount': 50.0},
    ]
    assert {'category': 'Dividend', 'amount': 700.0} not in s['income_category_totals']
    assert {'category': 'Bonus', 'amount': 900.0} not in s['income_category_totals']
    assert s['category_totals'] == [{'category': 'Groceries', 'amount': 75.0}]

def test_planned_spending_components_include_real_estate_taxes_with_mortgage(tmp_path):
    (tmp_path / 'client_spending.csv').write_text("""section,subsection,label,value,units,notes
Cashflow,Spending,annual_spending_base_year,"$100,000",,
Cashflow,Mortgage,monthly_payment,"$2,000",,
Cashflow,Mortgage,annual_real_estate_taxes,"$10,000",USD,
Cashflow,Mortgage,real_estate_tax_annual_adjustment_pct,3.00%,percent,
Cashflow,Mortgage,last_payment_year,2030,,
""", encoding='utf-8')

    components = ytd.planned_spending_components(tmp_path, 2026)

    assert components['core_spending'] == 100000.0
    assert components['mortgage_payment'] == 24000.0
    assert components['real_estate_taxes'] == 10000.0
    assert components['real_estate_tax_annual_adjustment_pct'] == 0.03
    assert components['mortgage_and_re_tax'] == 34000.0
    assert components['mortgage'] == 34000.0
    assert components['annual_total'] == 134000.0


def test_planned_real_estate_taxes_apply_annual_adjustment_when_plan_start_known(tmp_path):
    (tmp_path / 'client_household.csv').write_text("""section,subsection,label,value,units,notes
Household,Plan,plan_start,2025,year,
""", encoding='utf-8')
    (tmp_path / 'client_spending.csv').write_text("""section,subsection,label,value,units,notes
Cashflow,Mortgage,annual_real_estate_taxes,"$10,000",USD,
Cashflow,Mortgage,real_estate_tax_annual_adjustment_pct,3.00%,percent,
""", encoding='utf-8')

    assert round(ytd.annual_real_estate_tax_spending(tmp_path, 2027), 2) == 10609.0


def test_ytd_save_buttons_enable_immediately_after_inline_edits():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert 'function setYtdDirtyButtonStates()' in text
    assert "id=\"ytdSaveAccountSetupBtn\"" in text
    assert "id=\"ytdSaveTransactionsBtn\"" in text
    assert 'markYtdAccountsDirty(){ytdAccountsChanged=true' in text
    assert 'markYtdTransactionsDirty(){ytdTransactionsChanged=true' in text
    assert 'setYtdDirtyButtonStates()' in text
    assert 'Add account/source' in text


def test_ytd_transactions_table_formats_amounts_compactly():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    css = open('frontend/css/dashboard.css', encoding='utf-8').read()
    assert 'function ytdTxnMoneyDisplay' in text
    assert 'ytd-amount-input' in text
    assert 'ytd-negative-amount' in text
    assert 'focusYtdTxnAmount(this)' in text
    assert 'blurYtdTxnAmount' in text
    assert 'ytd-date-input' in text
    assert 'font-variant-numeric:tabular-nums' in css
    assert 'color:var(--danger)' in css


def test_ytd_account_mapping_allows_manual_non_transaction_sources_and_broader_types(tmp_path):
    ytd.write_account_setup(tmp_path, [
        {'Account': 'Pension Plan A', 'Role': 'Pension', 'Mapped Investment Account': '', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '0', 'Notes': 'manual source'},
        {'Account': 'Offline Rental', 'Role': 'Real estate', 'Mapped Investment Account': '', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '500000', 'Notes': 'manual asset'},
        {'Account': 'SPIA', 'Role': 'Annuity', 'Mapped Investment Account': '', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '100000', 'Notes': ''},
    ])

    rows = ytd.read_account_setup(tmp_path)

    assert [r['Role'] for r in rows] == ['Pension', 'Real estate', 'Annuity']


def test_ytd_account_mapping_ui_has_manual_add_and_grouped_broader_account_types():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert 'Add account/source' in text
    assert 'addManualYtdAccount' in text
    assert 'Assets and income sources' in text
    assert 'Liabilities' in text
    for role in ['Annuity', 'Pension', 'Social Security', 'Offline asset', 'Real estate', 'Note receivable', 'Income source', 'Credit card', 'Mortgage', 'HELOC', 'Loan', 'Other liability']:
        assert role in text
    assert "'Liability'" in text[text.index('function ytdAccountRoleOptions'):text.index('function ytdInvestmentOptions')]  # legacy CSV value maps forward
    assert "'Liability'," not in text[text.index('function ytdAccountRoleOptions'):text.index('function ytdInvestmentOptions')]
    assert 'Account / Source' in text
    assert 'Account Type' in text


def test_ytd_account_mapping_preserves_non_investment_current_values(tmp_path):
    ytd.write_account_setup(tmp_path, [
        {'Account': 'Rental House', 'Role': 'Real estate', 'Mapped Investment Account': '', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '500000', 'Current Value': '550000', 'Notes': 'legacy note'},
        {'Account': 'Brokerage', 'Role': 'Investment', 'Mapped Investment Account': 'Brokerage', 'Prior Year End Date': '2025-12-31', 'Prior Year End Balance': '100000', 'Current Value': '999999', 'Notes': ''},
    ])

    rows = ytd.read_account_setup(tmp_path)

    assert rows[0]['Current Value'] == '550000'
    assert rows[1]['Role'] == 'Investment'


def test_ytd_account_mapping_ui_uses_inline_source_add_current_value_no_notes_or_prior_date_column():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert 'id="ytdManualAccountName"' in text
    assert 'id="ytdManualAccountRole"' in text
    assert "prompt('Account/source" not in text
    assert '<th>Prior Year End Balance</th><th>Current Value</th>' in text
    assert 'From holdings' in text
    account_section = text[text.index('function renderYtdAccounts'):text.index('function renderYtdTracking')]
    assert '<th>Notes</th>' not in account_section
    assert '<th>Prior Year End Date</th>' not in account_section
    assert 'ytdAddAccountSelect' not in account_section
    assert 'Add transaction account' not in account_section
    assert 'ytd-delete-cell' in text


def test_ytd_transaction_table_uses_pagination_controls_instead_of_first_500_only():
    text = open('frontend/js/dashboard.js', encoding='utf-8').read()
    assert 'const YTD_TX_PAGE_SIZE=500' in text
    assert 'function ytdTxnPager' in text
    assert 'setYtdTxnPage(0' in text
    assert 'Previous' in text and 'Next' in text and 'Last' in text
    assert 'tx.slice(0,500)' not in text
    assert 'pageRows=tx.slice(start,start+YTD_TX_PAGE_SIZE)' in text
