# Financial Trends: time scope and Spending by window, October 2026

Companion Financial Trends reporter only. No projection or build result moves; the golden masters are
unchanged.

## What you see

- **Title Case titles.** Page and card titles are Title Case; the spending card is now "Spending".
- **No Run now button.** Opening the page runs an automatic update and shows an **Updating Data** overlay
  with the elapsed time and the average of recent runs (shared `frontend/js/runtime_history.js`, served at
  `/shared/runtime_history.js`). The update is skipped when a run finished in the last 15 minutes. A run lock
  stops two updates from overlapping.
- **One Time scope pulldown** drives all four charts: 1 Week, 1 Month, 3 Months, 6 Months, YTD, 1 Year,
  All Time and Custom. Your choice is remembered. The old per-chart timeframe buttons are gone.
- **Line charts fit the card width** with scope-aware x-axis labels; there is no horizontal scroll.
- **Investment Net Flows** is built from a new daily flows ledger and follows the scope.
- **Spending is computed per window.** Three markers are drawn on a thin card-coloured outline: same period
  last year (near-black in light mode, near-white in dark), budget for this period (prorated, orange) and
  full-year budget (dashed magenta).

## New endpoints and log field

- `GET /api/run-status` reports whether an update is running and when the last one finished.
- `GET /api/spending` returns the spending hierarchy for a window (`spending_hierarchy_window` in
  `src/spending_tracker.py`, `financial_trends_reporter/spending_window.py`).
- `/api/flows` now also returns `daily`, the daily investment flows.
- The trends log gains `investment_flows_daily`.

## Notes

- The old YTD-only Spending figures are unchanged: they are the same at the YTD scope.
- **All Time starts 2025-02-01**, for balances, flows and Spending.
- The first page open after this change triggers one update, which writes the daily flows ledger.
- **Known limitation, not addressed here:** a Monarch account rename creates a new account key and loses its
  mapping. The key is the cleaned account name, case-folded (`account_key` in
  `Monarch Extractor/monarch_balances.py`), because the export carries no account id; balances are stored
  per `(date, account_key)` in `financial_trends_reporter/balance_store.py`.
