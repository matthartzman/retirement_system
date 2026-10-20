# Transaction and account import format notes

These notes describe the CSV shapes the app imports and exports for spending
actuals. They are not working files: the app keeps transactions and account
setup in your plan file, and editing a CSV left in `input/` does not change it.

## Transactions

Bring a file in on the **Actual Spending** page (the **Income & Expense Transactions** table) with **Import
transactions**. Choose **Replace all** or **Add without replacing**.

Columns: `Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner`

- Only `Date` and `Amount` are required.
- Column order does not matter, capitalization is ignored, and extra columns are skipped.
- All rows with a valid date are imported, whatever the year. Use the Year
  pull-down on the page to choose which calendar year's actuals are shown.
- An optional `Monarch Id` column is used to avoid importing the same
  transaction twice.

`input/ytd_transactions_sample.csv` is a two-row example.

## Account setup (export and import shape)

Columns: `Account, Role, Mapped Investment Account, Prior Year End Date, Prior Year End Balance, Current Value, Current Balance, Notes`

The app builds this list from your imported transaction accounts; you set each
account's role and mapped investment account under **Accounts & Sources** on the same page. A mapped investment
account is chosen from the account names on your **Investment Holdings** page.

## How investment growth is figured

`current balance - prior-year-end balance - net external investment cashflow`

Dividends and interest count as investment income/growth; deposits and
withdrawals count as external investment cashflow.
