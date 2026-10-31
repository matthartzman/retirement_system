# Investment-account cash tracking: design and plan

Date: 2026-10-31. Status: design for review, nothing built.

## 1. Goal

All cash in investment accounts is tracked. That cash belongs to the account, so the **account's tax treatment applies** (taxable, traditional, Roth, HSA), unlike cash in a checking account. It stays in the account until it is **withdrawn or transferred out**; buying a security, selling one, or receiving a dividend only moves value between cash and the account's other holdings.

Related: `2026-10-31-account-number-protection-design-and-plan.md` (descriptions and file names used here must be masked by that work) and `2026-10-30-broker-activity-bulk-import-design-and-plan.md` (the importer this builds on).

## 2. What exists today (checked 2026-10-31)

- **Holdings model cash as a lot.** A position with symbol `CASH` per account; its `shares` is the dollar balance. The engine reads positions per account (`{account: {CASH: balance}}`), classes it as Cash, and the account's tax class applies because the position lives in the account.
- **Cash-only accounts** have one CASH lot that follows the Monarch balance (the Monarch reconcile page writes it). For accounts with the **Investment** role the reconcile page is report-only: it never writes a cash balance.
- **The broker import already stores cash rows but does not use them.** Every broker row is kept in `broker_activity` with its `amount`. Rows of kind `other` (contributions, transfers, distributions, fees, misc income) and money-market sweep legs are listed as "ignored" and never touch lots, sales or any balance.
- **Broker files differ in what they say about cash.** Fidelity's history has a `Cash Balance ($)` column on every row, which the parser ignores. E*Trade and Vanguard files have no running balance (amount, quantity and price columns only).
- **Monarch rows kept for Investment accounts** (after the 2026-10-31 purge): Transfer, 401k Contribution, 401K Match, Financial Fees, Other Income, Uncategorized. These are the only record of cash movements for accounts with no broker file (for example the 401(k) plan accounts).
- **Money-market sweep funds** (for example FDRXX, VMFXX) are recorded as sweep rows. Whether the sweep fund balance is counted as cash or as a security position is not defined anywhere.

## 3. Gaps

1. No cash **ledger** per investment account: nothing says how a balance arose.
2. Nothing moves the CASH lot when a buy, sell, dividend, contribution or withdrawal happens. (Needs verifying: whether confirming a queued sale adds the proceeds to the CASH lot. Phase 0.)
3. Transfers between a person's own accounts are not recognised as such, so a withdrawal from one account and the deposit into another look like unrelated flows.
4. The spending tracker may count the kept investment-account cash rows. If it does, a transfer to checking is counted twice or a contribution counts as income. Needs verifying (Phase 0).
5. The sweep fund is neither clearly cash nor clearly a security.

## 4. Design

### 4.1 Principle

Cash is a **balance with a ledger**, not a transaction category. Every investment account has one cash balance (core cash plus its money-market sweep fund, shown as one Cash line with the fund as a sub-line) and a ledger of dated flows that explain it.

### 4.2 Flow classes

Each ledger row has a signed amount and one class:

| Class | Cash effect | Source |
|---|---|---|
| Income (dividend, interest, capital-gain distribution) | + | broker files (already parsed) |
| Trade settlement (buy −, sell +) | ± | broker files (already parsed); sweep legs excluded as internal |
| Contribution, employer match | + | broker files if present, else the kept Monarch rows |
| Fee | − | broker files, else Monarch |
| Transfer in / out | ± | both; paired (4.3) |
| Distribution / withdrawal | − | broker files (type "Distribution" and similar), else Monarch |
| Adjustment | ± | unpaired internal journals (for example cash-to-margin pairs), shown but netting to zero |

### 4.3 Transfer pairing

An outflow in one plan account and an inflow of the same amount in another within 3 days (the tolerance the income check already uses) are **one internal transfer**: no tax event, not spending. An outflow with no partner in a plan investment account is an **external withdrawal**: it pairs with a row in a Cash / spending account (checking) where one exists, and is a tax event according to the source account's class. Unpaired rows stay visible as "unmatched" and are never guessed at.

### 4.4 Source precedence

For any date range covered by an applied broker import, the **broker file wins**. The kept Monarch cash-movement rows fill only the days no broker file covers. This avoids double counting the same contribution from both sources.

### 4.5 Balance and anchor

Balance on a date = anchor + net flows since the anchor. Anchor, in priority order:

1. The Fidelity `Cash Balance ($)` value on the last row of a file (exact, needs a parser change; Phase 1).
2. The user's last confirmed balance: the account's CASH lot and its date.
3. Nothing: the balance is shown as **unanchored** with the flows only, never as a number that looks reliable.

The computed balance is compared with the account's CASH lot and the difference is shown. Nothing writes to the CASH lot silently: an explicit **Apply** step shows old and new values, the same preview-then-confirm pattern the reconcile page already uses.

### 4.6 Tax treatment

Cash inherits the account's tax class; no new tax logic is invented here.

- Taxable: interest and dividends on the cash are taxed in the year received (already handled by broker income by account class); moving cash within the account is not a tax event.
- Traditional: nothing is taxed while cash sits in the account; a withdrawal is taxed as ordinary income when it leaves.
- Roth and HSA: the existing rules for qualified and non-qualified withdrawals apply when cash leaves.
- Spending: only an **external withdrawal** reaches the spending tracker, once, as the transfer to checking. Investment-account contributions, matches, fees and internal transfers are excluded from spending and income totals.

### 4.7 Screens

A "Cash in investment accounts" panel beside the importer: one row per account with computed balance, as-of date, the account's CASH lot, difference, anchor type, and last flow date; click a row for its ledger (date, class, amount, running balance, pairing status). It reuses the collapsible, sortable-heading table pattern of the Imports list and shows account names, never numbers.

### 4.8 Data

Prefer a **derived view** over a new stored ledger: the ledger is computed from `broker_activity` plus the kept Monarch rows, so nothing can drift. The only new stored data is the Fidelity running balance column on `broker_activity` (a schema change) and, if wanted, the pairing decisions the user overrides.

## 5. Risks

1. **Double counting** between broker files and Monarch. Mitigated by source precedence (4.4) and a test with overlapping coverage.
2. **Wrong anchor.** An unanchored account must look unanchored. A silent opening balance of zero would be wrong for every account that held cash before the first file.
3. **Pairing errors** (two same-amount transfers on one day). Pair only when exactly one candidate exists; leave the rest unmatched.
4. **Sweep fund semantics** differ by broker and may change what Fidelity's `Cash Balance` includes. Phase 0 checks the real files before any parser change.
5. **Schema migration** risk for the plan file; follow the existing versioned migration with a backup.

## 6. Phases

Effort and usage are relative to a 5-hour Pro-plan session; check `/usage` against these as the work proceeds.

| Phase | Work | Model / effort | Usage estimate |
|---|---|---|---|
| 0. Verify assumptions | (a) does confirming a sale credit the CASH lot; (b) are the kept investment cash rows counted in spending totals; (c) what the Fidelity `Cash Balance` column includes, using the real files outside the repo; (d) what E*Trade and Vanguard files contain for contributions and withdrawals. | Sonnet, medium | Light to moderate. **Expensive risk:** `dashboard.js` (7,287 lines) and the spending tracker; use Grep for the spending totals and never read `dashboard.js` whole. |
| 1. Parse running balance | Fidelity `Cash Balance` into `broker_activity` (schema migration with backup); tests with fixtures. | Sonnet, medium | Moderate. |
| 2. Ledger builder | Pure function from broker rows plus kept Monarch rows to ledger rows with classes, sweep exclusion and source precedence. | Opus, high | Moderate. The core logic; plan for test-driven work. |
| 3. Transfer pairing | Internal vs external vs unmatched, with the exactly-one-candidate rule. | Opus, high | Moderate. Watch for a test-fix loop on pairing edge cases; scope with fixtures first. |
| 4. Balance, anchor, reconcile | Anchored balance, difference against the CASH lot, Apply with preview and confirm. | Opus, high | Moderate. Touches the reconcile module (53 Monarch references); Grep to the cash-lot code, do not read it whole. |
| 5. Screen | Cash panel and ledger view, sortable and collapsible. | Sonnet, medium | Moderate. Frontend line ceiling will need a dated raise. |
| 6. Engine and spending checks | Confirm engine treatment of the CASH lot per account class; exclude non-external flows from spending. | Opus, high | Moderate to heavy if golden masters move: run `measure` first, never regenerate in a loop. |

Total: roughly two to three working sessions after Phase 0. Regenerate the architecture diagram when new modules are added.

## 7. Open questions

1. Is a money-market sweep fund **cash** for this purpose (recommended) or a security position?
2. For accounts with no broker file (the 401(k) plan accounts), is Monarch's flow history plus the user's confirmed balance acceptable, or should those be entered by hand?
3. Should an external withdrawal be required to pair with a checking-account row, or may it stand alone?
4. Should Apply write the computed balance to the CASH lot automatically after an import, or always wait for the user?
5. Do you want cash interest inside a traditional IRA or HSA shown separately from taxable-account interest?
