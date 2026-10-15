# Monarch mapping redesign and Financial Reporting fixes, October 2026

Items 349 to 354. No projection or build result moves; the golden masters are unchanged.

## Monarch Reconciliation page (349)

- **Opens on "Needs a decision".** Every difference on an account set to *ask* gets four choices:
  **Update app** (previews old and new, then writes), **Ignore this time** (hidden until Monarch's number
  changes), **Always update** (sets the policy to auto and updates now) and **App is source** (report only).
- **All mappings tab** shows every match with its policy: `ask`, `auto`, `app` (report only) or `ignore`.
  **Import mapping CSV** seeds matches and policies from the hand-made mapping file; rows the page cannot
  resolve yet are kept and matched by name to Other Asset Items, notes and liabilities.
- **New targets:** Other Asset Items (one update writes the value **and** the as-of date, so depreciation does
  not apply twice; one Undo restores both), note receivable face value, and liability balances.
- **Closed accounts:** closed with no balance is quiet (collapsed, nothing to decide); closed but still holding
  money is flagged with "Money moved: mark done".
- **Automatic updates:** accounts set to *auto* are copied at the 04:00 import, logged as automatic. A change
  is held for the inbox (with its reason) when it is the home or mortgage plan-start input, or when it is over
  both 10% and $5,000. A banner counts the last 7 days of automatic updates with **Undo all automatic updates**.
- **Schema v14** adds `monarch_account_map.policy` and `reconcile_log.source`. A plan file is upgraded the first
  time it is opened for writing; older versions cannot open it afterwards. Back up `plan.rpx` first.
- New routes: `POST /api/reconcile/policy`, `/undo-auto`, `/seed` (see `API_CONTRACTS.md`).

## Financial Reporting app (350 to 353)

- **350.** The "Monarch accounts & mapping" table is gone. Account type, the match to the plan and Ignore are
  read from the Retirement app at each import (`financial_trends_reporter/app_sync.py`); an Ignore in the app
  switches the account off in every chart. Per-chart inclusion stays in each chart's Accounts popover.
- **351.** Full-year budget (orange) and prior-year (black) markers now have the same height on the YTD bars,
  and appear on both detail boxes: categories show prior-year and budget, merchants show prior-year only where
  last year had that merchant (merchants have no budget). The detail markers appear after the next **Run now**
  (new log fields `ytd_expense_prior_detail` and `annual_budget_by_category`).
- **352.** All time now starts 2025-02-01 (earlier Monarch history has too few accounts linked and stretched the
  axis). A missing value breaks the line instead of dropping to zero.
- **353.** "Holdings value" is now **Liquid Investments and Cash**.

## Main app (354)

- Reverting to a snapshot no longer fails with "expected percentage format ending with %": the revert now
  formats each before-value the same way a normal save does.
