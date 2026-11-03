# Investment-account cash tracking: design and plan

Date: 2026-10-31.

Status: approved, with the owner's decisions of 2026-10-31 (section 7). Built 2026-11-02: Phase 0 (#343), 1 (#345), 2 (#350), 3 (#352), 4 (#353, anchor 1 only), and the spending half of Phase 6 (#354). Phase 5 (screen) is merged (#355). Phase 6 engine half built 2026-11-02 as audit plus report-only (section 10 Built note). Not built: anchor 2, and feeding the pair-status tax rule into the engine (needs the owner's approval of the numbers on real data).

Overlap with the transaction log (`2026-10-31-transaction-log-design-and-plan.md`): Phases 4 and 6 below are built
together with the log's phase 3 as the combined phase in `2026-11-02-cash-and-transaction-log-integration.md`. That note
fixes the `CASH` lot as written only by this ledger, shares the Phase 3 transfer pairing with the log's importer, keeps
sale confirmation from crediting `CASH` a second time, and makes schema version numbers "next free".

## 1. Goal

All cash in investment accounts is tracked. That cash belongs to the account, so the **account's tax treatment applies** (taxable, traditional, Roth, HSA), unlike cash in a checking account. It stays in the account until it is **withdrawn or transferred out**; buying a security, selling one, or receiving a dividend only moves value between cash and the account's other holdings.

Related: `2026-10-31-account-number-protection-design-and-plan.md` (descriptions and file names used here must be masked by that work) and `2026-10-30-broker-activity-bulk-import-design-and-plan.md` (the importer this builds on).

## 2. What exists today (checked 2026-10-31)

- **Holdings model cash as a lot.** A position with symbol `CASH` per account; its `shares` is the dollar balance. The engine reads positions per account (`{account: {CASH: balance}}`), classes it as Cash, and the account's tax class applies because the position lives in the account.
- **Cash-only accounts** have one CASH lot that follows the Monarch balance (the Monarch reconcile page writes it). For accounts with the **Investment** role the reconcile page is report-only: it never writes a cash balance.
- **The broker import already stores cash rows but does not use them.** Every broker row is kept in `broker_activity` with its `amount`. Rows of kind `other` (contributions, transfers, distributions, fees, misc income) and money-market sweep legs are listed as "ignored" and never touch lots, sales or any balance.
- **Broker files differ in what they say about cash.** Fidelity's history has a `Cash Balance ($)` column on every row, which the parser ignores. E*Trade and Vanguard files have no running balance (amount, quantity and price columns only).
- **Monarch rows kept for Investment accounts** (after the 2026-10-31 purge): Transfer, 401k Contribution, 401K Match, Financial Fees, Other Income, Uncategorized. Every investment account, including the 401(k)s, has a broker file (decision 2), so these rows are a fallback for date ranges no broker file covers and for flows the broker files do not carry; they are not the only record for any account.
- **Money-market sweep funds** (for example FDRXX, VMFXX) are recorded as sweep rows. They count as cash (decision 1); today nothing treats them either way.

## 3. Gaps

1. No cash **ledger** per investment account: nothing says how a balance arose.
2. Nothing moves the CASH lot when a buy, sell, dividend, contribution or withdrawal happens. (Needs verifying: whether confirming a queued sale adds the proceeds to the CASH lot. Phase 0.)
3. Transfers between a person's own accounts are not recognised as such, so a withdrawal from one account and the deposit into another look like unrelated flows.
4. The spending tracker may count the kept investment-account cash rows. If it does, a transfer to checking is counted twice or a contribution counts as income. Needs verifying (Phase 0).
5. The sweep fund is not yet treated as cash anywhere (decision 1 says it is).

## 4. Design

### 4.1 Principle

Cash is a **balance with a ledger**, not a transaction category. Every investment account has one cash balance (core cash plus its money-market sweep fund, which counts as cash by decision 1, shown as one Cash line with the fund as a sub-line) and a ledger of dated flows that explain it.

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

An outflow in one plan account and an inflow of the same amount in another within 3 days (the tolerance the income check already uses) are **one internal transfer**: no tax event, not spending. An outflow with no partner in a plan investment account is an **external withdrawal**: it pairs with a row in a Cash / spending account (checking) where one exists, and is a tax event according to the source account's class. Unpaired rows stay visible as "unmatched" and are never guessed at. A withdrawal does **not** need a checking-account partner to count (decision 3): with none it still is an external withdrawal and a tax event for its account class, and it is flagged "unmatched" so it stays visible.

### 4.4 Source precedence

For any date range covered by an applied broker import, the **broker file wins**. The kept Monarch cash-movement rows fill only the days no broker file covers. This avoids double counting the same contribution from both sources.

### 4.5 Balance and anchor

Balance on a date = anchor + net flows since the anchor. Anchor, in priority order:

1. The Fidelity `Cash Balance ($)` value on the last row of a file (exact, needs a parser change; Phase 1).
2. The user's last confirmed balance: the account's CASH lot and its date.
3. Nothing: the balance is shown as **unanchored** with the flows only, never as a number that looks reliable.

The computed balance is compared with the account's CASH lot and the difference is shown. **When the balance is anchored (anchor 1 or 2), an import writes it to the CASH lot automatically** (decision 4), recording the old and new values and the import in the history, with an undo like the reconcile page's. An unanchored balance is never written: the user confirms an anchor first (the preview-and-confirm step shows old and new values), and from then on imports update it.

### 4.6 Tax treatment

Cash inherits the account's tax class; no new tax logic is invented here.

- Taxable: interest and dividends on the cash are taxed in the year received (already handled by broker income by account class); moving cash within the account is not a tax event.
- Traditional: nothing is taxed while cash sits in the account; a withdrawal is taxed as ordinary income when it leaves.
- Roth and HSA: the existing rules for qualified and non-qualified withdrawals apply when cash leaves.
- Presentation: cash interest and dividends are grouped by the account's tax class (decision 5), so tax-deferred and Roth income is not mixed with taxable income taxed in the year.
- Spending: only an **external withdrawal** reaches the spending tracker, once, as the transfer to checking. Investment-account contributions, matches, fees and internal transfers are excluded from spending and income totals.

### 4.7 Screens

A "Cash in investment accounts" panel beside the importer: one row per account with computed balance, as-of date, the account's CASH lot, difference, anchor type, and last flow date; cash income for the year grouped by tax class beside it; click a row for its ledger (date, class, amount, running balance, pairing status). It reuses the collapsible, sortable-heading table pattern of the Imports list and shows account names, never numbers.

### 4.8 Data

Prefer a **derived view** over a new stored ledger: the ledger is computed from `broker_activity` plus the kept Monarch rows, so nothing can drift. The only new stored data is the Fidelity running balance column on `broker_activity` (a schema change) and, if wanted, the pairing decisions the user overrides.

## 5. Risks

1. **Double counting** between broker files and Monarch. Mitigated by source precedence (4.4) and a test with overlapping coverage.
2. **Wrong anchor.** An unanchored account must look unanchored. A silent opening balance of zero would be wrong for every account that held cash before the first file.
3. **Pairing errors** (two same-amount transfers on one day). Pair only when exactly one candidate exists; leave the rest unmatched.
4. **Sweep fund semantics** differ by broker and may change what Fidelity's `Cash Balance` includes. Phase 0 checks the real files before any parser change.
5. **Schema migration** risk for the plan file; follow the existing versioned migration with a backup.
6. **Automatic writes** (decision 4) can propagate a wrong flow into the CASH lot. Mitigated by writing only when anchored, recording old and new values, offering undo, and showing the difference in the panel; add a visible warning when one import changes a balance by an unusually large amount (threshold to be set from the real data in phase 0).

## 6. Phases

Effort and usage are relative to a 5-hour Pro-plan session; check `/usage` against these as the work proceeds.

| Phase | Work | Model / effort | Usage estimate |
|---|---|---|---|
| 0. Verify assumptions | (a) does confirming a sale credit the CASH lot; (b) are the kept investment cash rows counted in spending totals; (c) what the Fidelity `Cash Balance` column includes, using the real files outside the repo; (d) what E*Trade and Vanguard files contain for contributions and withdrawals. | Sonnet, medium | Light to moderate. **Expensive risk:** `dashboard.js` (7,287 lines) and the spending tracker; use Grep for the spending totals and never read `dashboard.js` whole. |
| 1. Parse running balance | Fidelity `Cash Balance` into `broker_activity` (schema migration with backup); tests with fixtures. | Sonnet, medium | Moderate. |
| 2. Ledger builder | Pure function from broker rows plus kept Monarch rows to ledger rows with classes, sweep exclusion and source precedence. | Opus, high | Moderate. The core logic; plan for test-driven work. |
| 3. Transfer pairing | Internal vs external vs unmatched, with the exactly-one-candidate rule. | Opus, high | Moderate. Watch for a test-fix loop on pairing edge cases; scope with fixtures first. |
| 4. Balance, anchor, reconcile | Anchored balance, difference against the CASH lot, automatic write when anchored with history and undo; confirm step for a first anchor. | Opus, high | Moderate. Touches the reconcile module (53 Monarch references); Grep to the cash-lot code, do not read it whole. |
| 5. Screen | Cash panel and ledger view, sortable and collapsible, with cash income grouped by tax class. | Sonnet, medium | Moderate. Frontend line ceiling will need a dated raise. |
| 6. Engine and spending checks | Confirm engine treatment of the CASH lot per account class; exclude non-external flows from spending. | Opus, high | Moderate to heavy if golden masters move: run `measure` first, never regenerate in a loop. |

Total: roughly two to three working sessions after Phase 0. Regenerate the architecture diagram when new modules are added.

## 7. Decisions (owner, 2026-10-31)

1. A money-market sweep fund counts as cash: one Cash line per account, core cash plus the fund.
2. Every investment account, the 401(k)s included, has a broker file. Monarch cash-movement rows are a fallback for uncovered date ranges and for flows the files lack, not the main source. (This corrects the earlier assumption that the 401(k) accounts had no file.)
3. An external withdrawal may stand alone; it does not need a checking-account partner.
4. An import writes the computed balance to the CASH lot automatically when the balance is anchored; it is recorded in history with an undo.
5. Cash interest and dividends are shown separately by the account's tax class.

## 8. Phase 2 decisions (owner, 2026-11-02; ledger builder is `src/cash_ledger.py`)

Answers to the open questions left for Phase 3 by the Phase 2 PR. Phase 2 itself is built (derived view, no schema change).

1. **Unclassified rows are paired.** Rows no rule classifies (and Monarch `Uncategorized`) are classed transfer in/out by sign with `needs_review`; Phase 3 pairs them like any transfer and keeps the review flag.
2. **Keep the E*Trade reference id.** Phase 3 adds the reference to the parsed row so own-account transfers pair on it first; amount within 3 days and exactly one candidate remains the fallback.
3. **In-kind transfers are paired too.** They stay zero-cash and `counts=False`, but Phase 3 pairs in-kind out/in across own accounts for visibility (the transaction log still owns the lots).
4. **Return of excess contribution gets its own class** (to be added in Phase 3, replacing `distribution` for these rows) so it is not taxed as a normal withdrawal; Phase 6 sets the tax treatment.
5. **Rollovers are distinguished** from own-account transfers (a marker on Vanguard `Rollover (incoming)` and similar), so an outside-plan rollover is not paired as an own-account transfer.
6. **Coverage gap: keep dropping, and warn.** A Monarch row inside a broker file's date range is still dropped (broker wins), but Phase 3/5 lists dropped Monarch rows with no broker row of the same amount within 3 days as a notice.

## 9. Phase 3 decisions (owner, 2026-11-02; pairing is `src/cash_pairing.py`, PR 352)

1. **Rollovers:** an unpartnered rollover stays `unmatched`. A plain contribution pairs with a matching outflow of another plan account, otherwise stays `unpaired`.
2. **Coverage gap notice:** deferred to a one-time query after the functionality is complete.
3. **Half-pairs (Phase 4):** each account's balance and anchor check count its own rows only. A missing or partly covered partner file never changes the other account's number; the row shows its pair status and the account is flagged "partner not imported".
4. **Tax rule (Phase 6):** tax by pair status, not class. Any `external_withdrawal` (class `distribution` or `transfer_out`) is a withdrawal from the account; an `internal` pair is not.
5. **`excess_return` (Phase 6):** untaxed and treated as the contribution coming back: not a taxable withdrawal and not external spending. Earnings on it are taxable, so the user is flagged to enter them.

**Built 2026-11-02 (Phase 5):** `src/cash_view.py`, `GET /api/cash` (per-account summary and income by tax class; `?account=` for one ledger), panel `frontend/js/dashboard_decomp_cash_investment.js` on the Sales Ledger page below the broker import. Balance anchors on the file's latest running balance, else the confirmed `CASH` lot, else the account shows "unanchored" with no number. Difference is balance minus the `CASH` lot. The ledger shows the broker's running balance on rows that have one. Tests: `tests/test_cash_view_unit.py`, `tests/frontend/cash_investment_panel.test.mjs`.

## 10. Phase 6 engine-half decisions (owner, 2026-11-02)

1. **`CASH` lot in the engine:** audit first. Run `measure`, record how the engine values `CASH` per account class, and change code only where a class is wrong. The golden master does not move without owner approval.
2. **`excess_return`:** as section 9 item 5. Untaxed, not external spending, and the user is flagged to enter the taxable earnings.
3. **Pair-status tax rule:** report-only first. Show per-account taxable withdrawals by pair status in the Cash panel and compare with the plan's current assumptions; feed the engine only after the owner approves the numbers on real data.
4. **Sequencing:** start after PR #355 (Phase 5 screen) merges.

**Built 2026-11-02 (Phase 6 engine half; audit plus report-only, no engine change, golden master `measure` MATCH before and after):**

*Audit of the `CASH` lot in the engine* (no code change; no real inconsistency found):
- Balance: every class values the lot as shares x 1.00 (`market_data` hardcodes the CASH price); `parse_capital_market_returns` sums it into the account balance. Taxable, traditional, Roth and HSA are identical here. Cash growth uses the `CASH` asset-class default (2.0% income, no growth).
- Tax: only taxable draws reach the lot engine (`_realize_taxable_gain`, `LotEngine.gain_on_withdrawal`). Traditional is taxed as ordinary income and Roth/HSA by their own withdrawal rules, none of which read lots, so the lot's basis never matters there.
- Taxable gain on cash: basis = shares x `purchase_price`. Lots the app writes (`cash_accounts`) use price 1, so cash withdrawn from a taxable account realizes no gain, and the anchored write (`cash_anchor`) changes only shares. Hazard, not an engine fault: a hand-entered CASH lot with a blank or 0 `purchase_price` has zero basis and would be taxed as pure gain (and if all lots have no basis, the engine falls back to the flat gain fraction). Check `purchase_price` is 1 on CASH lots. No change made.

*Report-only additions* (`src/cash_view.py`, `GET /api/cash`, Cash panel): per account `tax_class`; `withdrawals` for the year by pair status (`external_withdrawal` = a withdrawal from the account, `internal` = not a withdrawal, `unmatched` = undecided); `excess_return` (count and amount of the year, untaxed, not external spending, with the note to enter its taxable earnings). Nothing feeds the engine's tax numbers. Tests: `tests/test_cash_view_unit.py`, `tests/frontend/cash_investment_panel.test.mjs`. Next step (owner): compare the reported withdrawals with the plan's assumptions on real data, then decide whether to feed the rule into the engine.

## 11. Plan vs reported withdrawals (owner decisions, 2026-11-02; report only)

1. Plan side is the engine's per-account ledger `row['_account_withdrawals']` in `projection_rows`. Only the current year is compared; the engine projects from plan_start, so past years show reported withdrawals by pair status with no engine column.
2. The panel reads the newest saved result snapshot (`local_store.latest_result_snapshot`) and never runs the engine. It shows the snapshot's build time and says it may be stale.
3. The current year is PACE: year-to-date reported `external_withdrawal` beside the engine's full-year figure, no difference column. A difference (plan minus reported) appears only for a closed year. Year close is designed separately and not built: `cash_view.is_year_closed(store, year)` returns False for every year and is the seam.
4. A row counts in the year of its own date. An internal pair with one leg within 5 days of 31 Dec and the other in the other year is listed as "straddles year-end", never reallocated.

**Built 2026-11-02:** `cash_view.comparison`, `past_years`, `year_straddles`, `plan_year_withdrawals`, `is_year_closed`; `build_view` carries `comparison`, `past_years`, `straddles` on the existing `GET /api/cash` (no new route, no schema change); panel section in `dashboard_decomp_cash_investment.js`. Engine tax numbers unchanged; golden master `measure` MATCH before and after. Tests: `tests/test_cash_view_unit.py`, `tests/frontend/cash_investment_panel.test.mjs`.

**Limits found in review (2026-11-02), then closed by the owner's go-ahead:** saved results carried no plan identifier (`plan_snapshot_id` was always NULL) and `app.db` is machine-level (newest 10 kept), so the newest snapshot could belong to another plan. Now `report_compute` saves the active plan's id in the existing `plan_snapshot_id` column (no schema change) and `local_store.latest_result_snapshot(plan_id=...)` returns only that plan's newest run. Runs saved before this change have no id and are ignored until the plan is run again. Retention is still 10 runs across all plans, so heavy use of other plans can push a plan's last run out. `plan_start` is today's year, so a snapshot counts only when its first projection row is the compared year, otherwise "No plan figure for <year>".

**Built 2026-11-03:** the `is_year_closed` seam is now real: the owner closes a year by hand (`src/cash_year_close.py`, design in `2026-11-02-year-end-transition-design-and-plan.md`). A closed year shows its plan-minus-reported difference from the plan figure frozen at close; the close feeds no tax number.
