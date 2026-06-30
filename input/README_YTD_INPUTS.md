# YTD Spending & Growth Input Files

Use `ytd_transactions.csv` for uploaded transactions. The header must remain exactly:

`Date,Merchant,Category,Account,Original Statement,Notes,Amount,Tags,Owner`

Only current-calendar-year transactions are loaded. Older/future rows are skipped.

Use `ytd_account_setup.csv` only if you want to pre-seed account mappings. In the UI, transaction accounts are selected from uploaded transaction accounts, and mapped investment accounts are selected from `client_holdings.csv` account names.

Investment growth is calculated as:

`current balance - prior-year-end balance - net external investment cashflow`

Dividends and interest count as investment income/growth; deposits and withdrawals count as external investment cashflow.
