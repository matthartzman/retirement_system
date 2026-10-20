# Monarch daily account balances, trends charts and reconciliation, October 2026

What changed, and where the data lives now. No projection or build result moves: nothing here
touches the planning engine, so the golden masters are unchanged.

## What changed

- **Daily balances from Monarch.** A new extractor step, `Monarch Extractor/monarch_balances.py`, runs
  after the transaction export in `run_monarch.ps1` (03:30). It downloads Monarch's full balance
  history (one row per account per day) through the same saved browser login, normalizes it (ISO dates,
  cleaned account names, a stable key per account) and writes `output/balances.csv`. A failure in one of
  the two steps does not stop the other.
- **Two copies of the balances, for two apps.**
  - The **Financial Trends Reporter** keeps its own store,
    `financial_trends_reporter/data/monarch_balances.sqlite3` (gitignored): balances, a registry of
    accounts (type, mapping to an app account, confirmed flag) and per-chart on/off choices. It is loaded
    by `financial_trends_reporter/tools/import_monarch_balances.py` at the end of the 03:30 chain and again
    by the trends job.
  - The **main app** keeps the balances in the plan file (schema v13: `monarch_balances`,
    `monarch_balance_imports`, `monarch_account_map`, `reconcile_log`), loaded by the 04:00 import job.
    These are typed tables outside the revision snapshots, so a plan revision does not copy about 18,000
    balance rows. A plan file is upgraded to v13 the first time the new version opens it for writing;
    older versions cannot open it afterwards.
- **Import guards (both stores).** A balances file is rejected, and recorded, without writing anything when
  its header is wrong, a value cannot be read, its latest date is older than yesterday, or its account count
  is more than 20% below the last accepted import. A missing file is a quiet skip.
- **Trends reporter charts.**
  - Net worth and Holdings are drawn from Monarch's daily balances. Holdings is liquid investments, checking
    and Venmo; annuities, pensions, "Other" accounts, property, vehicles and debts are off by default.
    Dates Monarch does not cover keep the plan-derived figures.
  - Every chart has an **Accounts** control to switch accounts on and off, and a **Monarch accounts &
    mapping** panel sets each account's type and the plan account it maps to.
  - The hover detail on Net worth and Holdings omits accounts whose balance that day is zero.
  - Investment flows are a **monthly line** (net contributions) with a year-to-date summary of credits
    (into investments), debits (out of investments) and the total. The monthly ledger is written by the
    trends job, so the chart switches from the old bars at the next run.
- **Monarch Reconciliation page (main app, Reports & Review).** Lists each app account number beside
  Monarch's balance as of a chosen date and the difference. You can copy Monarch's number into the app for
  cash, cards and loans, manual accounts, and the home, autos and mortgage plan inputs: tick the rows,
  preview old and new values, confirm, and each change is logged and can be undone. Investment accounts
  and annuities that take their value from an income stream are report only. Monarch accounts that do not
  match an app account by name are matched by hand on the page; several can map to one app number
  (their balances are summed).

## Things to know

- Plan-start inputs (home, autos, mortgage) hold the plan's own starting figures. Changing them changes the
  next build, so the page asks you to rebuild afterwards.
- Undo restores the old number only while the app still holds the number that change wrote. If it was edited
  since, Undo refuses rather than overwrite that edit.
- The Monarch balance export has no account id, so accounts are keyed by name. A renamed account appears as a
  closed account plus a new one; both can map to the same app account.
- Closed accounts count as zero after their last row, in the trends charts and on the reconciliation page.

## Files

New: `Monarch Extractor/monarch_balances.py`, `src/monarch_balances_import.py`, `src/reconcile.py`,
`src/stores/monarch_repo.py`, `financial_trends_reporter/{balance_store,balance_series,account_registry,flows}.py`,
`frontend/js/dashboard_decomp_monarch_reconciliation.js`. Routes: `/api/reconcile*` (see
`../API_CONTRACTS.md`). Design and plan: `documentation/archive/superpowers/specs/2026-10-14-monarch-account-balances-trends-plan.md`.
