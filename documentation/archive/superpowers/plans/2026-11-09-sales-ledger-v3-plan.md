# Investment Sales Ledger v3 Implementation Plan

Status: implemented (merged to main as PR #418 on 2026-11-09); open items are in BACKLOG.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Slim the Sales Ledger to three single-purpose tabs, move the transaction log and broker import onto Investment Holdings, and make wash-sale handling follow the IRS rules (proportional disallowance, basis add-back, 1099-B tie, open-window warning).

**Architecture:** Server logic stays in `src/` modules (`history_sales`, `sales_service`, `sales_tax_year`, `wash_sales`, `transactions`) behind thin routes in `src/server/plan_routes.py`. Frontend pieces are ES modules named `frontend/js/dashboard_decomp_*.js`; the ledger and Holdings pages become tab hosts that mount existing panels. New stored data goes in new plan-schema migrations (append to `PLAN_MIGRATIONS` in `src/stores/plan_store.py`, currently 22 entries).

**Tech Stack:** Python 3 / Flask / SQLite plan store, vanilla-JS ES modules, `node --test` frontend tests (`tests/frontend/load_dashboard.mjs` vm sandbox), pytest.

**Spec:** `documentation/archive/superpowers/specs/2026-11-09-sales-ledger-v3-design.md` (approved). Mockup: `documentation/future/superpowers/mockups/sales-ledger-v3.html`. Read both first.

## Global Constraints

- Work on a new branch off `main` (e.g. `sales-ledger-v3`); never commit `tools/js_codemod/census_report.json`.
- `frontend/js` total line ceiling (`tests/test_frontend_size_ratchet.py`): each frontend phase must net-remove lines; never raise the ceiling, lower it after real extraction.
- New tests must not assert string literals against frontend source (`test_freeze_frontend_source_grep`); use the Node vm sandbox or API responses.
- Test file names: `tests/test_<scope>_<type>.py`, type one of regression, functional, contract, smoke, unit, integration. No tracking ids in names.
- New spec/plan docs under `documentation/future/` need `Status:` in the first 20 lines.
- After adding/moving/deleting any file under `src/` or `frontend/`, run `python tools/generate_system_diagram.py` and commit `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` in the same commit.
- Run `python tools/fast_gates.py` before every push. Prefer Edit/Write over script rewrites; regexes are raw strings; preserve line endings.
- Run pytest with `-v -rfE` redirected to a scratchpad log file, in the background for long runs.
- Never display a full account number; last 4 only. Account names shown to users come from `src/person_labels.py` `display_account` (server) or the existing frontend label helper.
- Golden masters must not move. Before and after any engine-adjacent change run `python tools/regen_golden_master.py measure` and `pytest tests/test_phase_golden_equality_regression.py -v`. Any move is a defect, not a regen.
- Do not touch `frontend/js/dashboard.js` (7,287 lines), `dashboard_decomp_row_model.js` (5,188 lines) or other files listed in `.claude/CLAUDE.md` "Reading Large Files" except by Grep plus offset/limit Read.
- Docs-only commits: push and open the PR, don't wait on CI.

## Review Focus

Failure modes the spec implies but no single task's happy path exercises; each has a pinned test in the owning task (marked **RF**).

1. **Two same-day sales of one symbol in one account** merge into one sale row (accepted), but the wash review and the W1 exclusion must still not corrupt each other (Task 14).
2. **A review that must survive "Send back to queue" and re-record**, where the new lot rows get new `sale_id`s (Task 13).
3. **Voiding a bank account's opening CASH rows while the account is still managed** wipes its holdings (Task 3).
4. **A plan with no wash sales**: everything is byte-identical, and the golden masters don't move (Task 16).
5. **"All years" selected** on Tax year (shows "Pick a year", never a blended total) and on Holdings deep links (Task 5, Task 8).

## File Map

| Area | Create | Modify | Delete |
|---|---|---|---|
| Server | `src/wash_adjustments.py` (phase 3) | `src/history_sales.py`, `src/sales_service.py`, `src/sales_tax_year.py`, `src/wash_sales.py`, `src/transactions.py`, `src/broker_import.py`, `src/stores/sales_repo.py`, `src/stores/transactions_repo.py`, `src/stores/plan_store.py`, `src/server/plan_routes.py`, `src/year_end.py`, `src/broker_1099b/report.py` | `preview_csv`, `commit_csv`, `_parse_csv` in `sales_service.py` |
| Frontend | `frontend/js/dashboard_decomp_sales_group.js`, `frontend/js/dashboard_decomp_sales_entry.js`, `frontend/js/dashboard_decomp_sales_wash.js`, `frontend/js/dashboard_decomp_holdings_tabs.js` | `dashboard_decomp_sales_ledger.js`, `…_sales_ledger_ui.js`, `…_sales_tax.js`, `…_sales_1099b.js`, `…_sales_queue.js`, `…_transactions_log.js`, `…_broker_import.js`, `…_cash_investment.js`, `…_year_end.js`, `…_holdings.js` | the CSV, Density and "More views" code |
| Tests | one new file per task below | `tests/frontend/{sales_ledger_page,sales_ledger_ui,sales_ledger_followups,cash_investment_panel,transactions_log_panel,broker_import_panel,sales_1099b_panel,year_end_page}.test.mjs`, Holdings tests, `tests/test_sales_routes_functional.py` | — |

## Phases, models and expected usage

Check `/usage` against these as the plan executes. Estimates are relative to a 5-hour Pro-plan session, not token counts.

| Phase | Tasks | Recommended model / effort | Size | What drives context |
|---|---|---|---|---|
| 1. Ledger cleanup and defects | 1–9 | Sonnet, medium (Task 6 high) | **Heavy** (about 1–1.5 sessions) | Several 200–370-line modules, 8 frontend tests to rewrite, test-fix loops |
| 1b. Holdings tabs | 10–12 | Sonnet, medium | Moderate | `dashboard_decomp_holdings.js` (grep only), moving two panels |
| 2. Wash rules and review | 13–15 | Opus, high | Moderate–heavy | Algorithm plus a schema migration; one careful pass |
| 3. Basis add-back | 16–17 | Opus, high | **Heavy, riskiest** | Touches lots, holdings and engine-adjacent numbers; golden-master loop |
| 4. 1099-B wash tie | 18 | Sonnet, medium | Light–moderate | `broker_1099b/report.py`, one panel |
| 5. Open-window warning | 19 | Sonnet, low | Light | One server function and one card |

**Flagged as likely disproportionately expensive:** Task 6 (largest new UI; build it against a fixture so it can be tested without running the app), Task 16 (golden-master loops; run `measure` once, don't regenerate), and Task 9 (deleting from `…_sales_ledger.js` and moving panels; do deletions per module with the frontend suite after each, not the full `pytest`). Use `pytest -m "not slow"` and `npm test` for loops, and the full suite only before the PR.

---

## Phase 1: Ledger cleanup and defects

### Task 1: History finds: working hide, unhide, hidden listing

**Files:** Modify `src/history_sales.py` (`_items` 99–137, `dismiss` 172), `src/server/plan_routes.py` (around 1437). Test `tests/test_history_sales_unit.py`.

**Interfaces:**
- Produces: `list_unrecorded(input_dir, *, year: int | None = None, include_hidden: bool = False) -> dict`; each item gains `hidden: bool` and `hidden_on: str | None` (ISO date). `undismiss(input_dir, key: str) -> None`. Route `POST /api/sales/history/undismiss` body `{key}`. `GET /api/sales/history?include_hidden=1`.

- [ ] **Step 1: Write failing tests**: `test_treasury_row_hidden_after_dismiss` (dismiss a `account|symbol|date|interest` key, `list_unrecorded` omits it), `test_include_hidden_returns_row_with_hidden_on` (assert `hidden is True` and `hidden_on` equals the clock date), `test_undismiss_restores_row`, `test_year_filters_hidden_count`, `test_old_dismissed_set_still_read` (a store holding the legacy set of keys reads as hidden with `hidden_on is None`).
- [ ] **Step 2: Run**: `pytest tests/test_history_sales_unit.py -v -rfE > <scratchpad>/pytest_t1.txt 2>&1`; expect the new tests FAIL.
- [ ] **Step 3: Implement.** Store the hidden date by changing `_dismissed(store)` to read a map `{key: iso_date}` from `DISMISS_KEY`, accepting the legacy list. Apply the dismissed check in the Treasury loop too. Add `undismiss`. Return hidden items only when `include_hidden`, marked.
- [ ] **Step 4: Run** the same tests; expect PASS.
- [ ] **Step 5: Commit** `fix: history Dismiss now hides Treasury rows; add Unhide`.

### Task 2: Investment-account definition

**Files:** Modify `src/broker_import.py` (`plan_accounts` 166–169), `src/transactions.py` (`backfill` 279). Test `tests/test_investment_accounts_unit.py`.

**Interfaces:**
- Produces: `investment_accounts(store_or_dir) -> list[str]` in `src/broker_import.py`: accounts whose `ytd_account_setup` Role is `Investment` (`src/ytd_tracking.py:233`), never accounts with a missing Role (`src/cash_accounts.py:33`). `plan_accounts` is rebuilt on it.

- [ ] **Step 1: Failing tests**: `test_checking_accounts_are_not_investment_accounts` (Business_Checking and Family_Checking excluded), `test_backfill_skips_non_investment_accounts` (no `opening` CASH rows for them), `test_missing_role_is_cash`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** `investment_accounts`; make `plan_accounts` return it and `backfill` skip any account not in it.
- [ ] **Step 4: Run**; expect PASS. Also run `pytest tests/test_broker_import_unit.py tests/test_broker_import_log_unit.py -v`.
- [ ] **Step 5: Commit**.

### Task 3: Bank-account cleanup with confirmation

**Files:** Modify `src/transactions.py`, `src/server/plan_routes.py`. Test `tests/test_bank_account_cleanup_functional.py`.

**Interfaces:**
- Consumes: `investment_accounts`, `set_managed`, `materialize_managed`, `void`.
- Produces: `bank_account_cleanup_preview(input_dir) -> {"accounts": [{"account", "managed": bool, "opening_rows": [txn_id]}]}` and `bank_account_cleanup_apply(input_dir, accounts: list[str]) -> {"voided": int, "unmanaged": list[str]}`. Routes `GET /api/transactions/bank-cleanup` and `POST /api/transactions/bank-cleanup` (body `{accounts}`; refused without an explicit list).

- [ ] **Step 1: Failing tests**: `test_preview_lists_checking_accounts_with_opening_rows`; **RF** `test_apply_unmanages_before_voiding_so_cash_holdings_survive` (a managed checking account's CASH holding row is still present afterwards); `test_apply_requires_explicit_accounts`; `test_apply_never_touches_investment_accounts`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement.** Order is fixed: unmanage, then void rows, then no `materialize_managed` for those accounts.
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit**. The UI for this is one line in Task 12 (Activity tab banner "2 bank accounts have log rows… Clean up").

### Task 4: Sales summary equal to Tax year, sale grouping, year list

**Files:** Modify `src/sales_service.py`, `src/sales_tax_year.py` (reuse `_live_sales` 75–77), `src/server/plan_routes.py`. Create `frontend/js/dashboard_decomp_sales_group.js`. Tests `tests/test_sales_summary_functional.py`, `tests/frontend/sales_group.test.mjs`.

**Interfaces:**
- Produces: `sales_summary(input_dir, year: int | None, *, taxable_only: bool = True) -> {"count", "st_gain", "lt_gain", "fees"}` using exactly Tax year's filter (`status=="confirmed"`, `tax_class=="taxable"` when taxable_only, `gain is not None`, sale-date year). `sales_years(input_dir) -> list[int]` (years with ledger or log rows, ascending, never future). Routes `GET /api/sales/summary?year&taxable_only`, `GET /api/sales/years`. JS `slGroupSales(rows) -> [{key, account, symbol, sale_date, shares, proceeds, basis, gain, term, lots: [row], wash: bool}]` where `key = account|symbol|sale_date`, term `"Mixed"` when lots differ.

- [ ] **Step 1: Failing tests**: `test_summary_matches_tax_year_totals` (same fixture plan, `sales_summary(...).st_gain == tax_year_summary(...).totals.st_gain`); `test_summary_taxable_only_off_includes_ira_sales`; `test_years_exclude_future_and_empty`; node: `groups two same-day same-symbol orders into one sale`, `groups lots of mixed term as "Mixed"`, `a single lot is a single-row sale`.
- [ ] **Step 2: Run** both; expect FAIL.
- [ ] **Step 3: Implement** the three server functions and the pure JS grouper (no DOM).
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit**.

### Task 5: Ledger shell: three tabs and shared header

**Files:** Modify `…_sales_ledger_ui.js` (`SL_TABS`, `slUiLoad`), `…_sales_ledger.js` (`slHeadHtml` 111, `slBodyHtml` 195, `slSetYear` 335), the nav test baseline only if the sidebar changes (it shouldn't). Tests `tests/frontend/sales_ledger_ui.test.mjs`, `sales_ledger_page.test.mjs`.

**Interfaces:**
- Consumes: Task 4 routes.
- Produces: `SL_TABS = [["fix","To fix"],["ledger","Sales"],["tax","Tax year"]]`; persisted UI state `{tab, sections, taxableOnly: true}` (the `density` field is dropped; an old stored value is ignored); `slSetTaxableOnly(on)`; header shows Year (from `/api/sales/years`, plus "All years"), the Taxable accounts only checkbox with a friendly-name caption, and a `Voided rows (n)` link replacing the checkbox.

- [ ] **Step 1: Failing tests** (Node vm): `SL_TABS has three tabs in order`; `old stored tab "import" falls back to "fix"`; `year options list only years returned by the server plus All years`; `Taxable accounts only defaults on and persists`; **RF** `All years on the Tax tab renders "Pick a year" and no totals`.
- [ ] **Step 2: Run** `npm test`; expect new tests FAIL.
- [ ] **Step 3: Implement.** Delete `slDensityHtml`, the "More views" divider, the Import tab host and Sale-year label; Tax year heading reads the year from state.
- [ ] **Step 4: Run** `npm test`; expect PASS (update the pinned-structure tests listed in the File Map as part of this step).
- [ ] **Step 5: Commit**.

### Task 6: Record sales grid and lot chooser

**Files:** Create `frontend/js/dashboard_decomp_sales_entry.js`. Modify `src/sales_service.py`, `src/server/plan_routes.py`, `…_sales_ledger.js` (mount point, delete the old form `slFormHtml` 78). Tests `tests/test_sales_entry_functional.py`, `tests/frontend/sales_entry.test.mjs`.

**Interfaces:**
- Produces: `GET /api/sales/open-lots?account&symbol&as_of` → `[{txn_id, purchase_date, open_shares, unit_cost, term, source}]` wrapping `transactions.open_lots`; `add_sales(input_dir, rows: list[dict]) -> {"ids": list[int]}`, atomic (all rows or none), each row one lot with `txn_lot` set when chosen from the log; route `POST /api/sales/batch`. JS `seFill(lots, shares, method)` with method `"fifo" | "hifo" | "losses"` returning `{[txn_id]: shares}`; `seRowState(row) -> {matched, gain, label}` where label is `"2 lots ✓"` or `"0 / 200 · pick"`.

- [ ] **Step 1: Failing tests**: py `test_batch_is_atomic` (one invalid row writes nothing), `test_batch_links_txn_lot`, `test_open_lots_as_of_sale_date`; node `fifo fills oldest first`, `hifo fills highest cost first`, `losses fills lowest gain first`, `save is disabled until every row is matched`, `non-taxable account row reads "not taxable"`, `account with no log shows blank lot rows`, `Enter in the last field of the last row adds a row`, `an empty chooser renders a link to Holdings Activity` (link shape per Task 10).
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** server first, then the module. One chooser open at a time. The default lot method is the broker import's `biMethod`.
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit**.

### Task 7: Sales table: one row per sale, lot actions

**Files:** Modify `…_sales_ledger.js` (`slRowHtml` 39, `slTableHtml` 52, `slTotalsHtml` 59, `slRequeue`, `slVoid`). Test `tests/frontend/sales_ledger_page.test.mjs`.

**Interfaces:** Consumes `slGroupSales` and `GET /api/sales/summary`. Produces the KPI strip (count, short-term, long-term, fees; labelled "realized"), sale rows with ▸ lot expansion, a lot-row ⋯ menu (Edit, Void; calls today's `replace_sale`/`void_sale`) and a sale-row ⋯ menu with only "Send back to queue" (`slRequeue`). Inapplicable actions are disabled with a reason.

- [ ] **Step 1: Failing tests**: `one row per sale with lots hidden until expanded`; `sale row menu offers only Send back to queue`; `lot row menu offers Edit and Void`; `Back to queue is disabled with a reason for a manual sale`; `KPI strip uses summary endpoint values`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**.

### Task 8: Tax year tab: year-driven headings, fund-type table, 1099-B card

**Files:** Modify `…_sales_tax.js` (wash block at 58–61 moves out in Task 15; fund-type radios), `…_sales_1099b.js`, `src/sales_tax_year.py`. Tests `tests/frontend/sales_1099b_panel.test.mjs`, a new `tests/frontend/sales_tax_headings.test.mjs`.

**Interfaces:** the 1099-B card is mounted inside Tax year; `s1099bAutoOpen(year, state, today) -> boolean` true when no 1099-B exists for the Year's taxable accounts and `today` is after January 31 of Year+1. The paste textarea and step labels are removed; the Account list uses `investment_accounts` filtered to taxable.

- [ ] **Step 1: Failing tests**: `no heading contains a hardcoded year`; `carryforward label reads "Loss carried in from {Year-1}"`; `fund types render one select per symbol`; `1099-B card has no paste textarea`; `1099-B account list excludes IRA and checking accounts`; `s1099bAutoOpen is false before Feb 1 of the next year`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**.

### Task 9: Remove Sales CSV; move the cash material to Year-End

**Files:** Modify `src/sales_service.py` (delete `preview_csv`, `commit_csv`, `_parse_csv`), `src/server/plan_routes.py` (delete `/api/sales/import/{preview,commit}` at 1110–1126), `tests/test_sales_routes_functional.py`, `…_cash_investment.js`, `…_year_end.js`, `src/year_end.py`. Tests `tests/frontend/year_end_page.test.mjs`, `tests/frontend/cash_investment_panel.test.mjs`.

**Interfaces:** Year-End page gains four cards in this order: **Investment cash agrees with the broker** (matching rows collapsed behind "n of n match"), **Withdrawals: actual vs plan** (rows that are $0 on both sides hidden), **One-time: verify accounts for the tax feed** (expanded until every account is verified), **Closed years** (one collapsed list; years with nothing reported omitted). The "Reinvest dividends default" setting moves to Plan Features (its stored key is `Economic Assumptions` / `reinvest_dividends_default`, read at `src/parsing/client_sections.py:1586`; keep it unchanged).

- [ ] **Step 1: Failing tests**: `Sales CSV routes return 404`; `year-end page renders the four cash cards for the closing year`; `all-matching accounts collapse to "8 of 8 match"`; `closed years with only zero rows are omitted`; `reinvest default setting reads and writes the same stored key from Plan Features`.
- [ ] **Step 2–4:** run, implement (move the panel; don't rewrite its logic), run to PASS.
- [ ] **Step 5: Commit**, regenerate the diagram, run `python tools/fast_gates.py`.

---

## Phase 1b: Holdings tabs

### Task 10: Holdings tab host and deep links

**Files:** Create `frontend/js/dashboard_decomp_holdings_tabs.js`. Modify `…_holdings.js` (find the render entry with `grep -n "export function renderHoldings"`; no linear read). Test `tests/frontend/holdings_tabs.test.mjs`.

**Interfaces:**
- Produces: `HOLDINGS_TABS = [["positions","Positions"],["activity","Activity"],["import","Import"]]`; `hsParseHash(hash) -> {tab, account, symbol, type, source, year, back}` for `#holdings/activity?account=…&symbol=…&type=…&source=backfill&year=…&back=sales`; `hsActivityLink({account, symbol, type, source, year, back}) -> string`. The tab is remembered like the ledger's. The sidebar entry is unchanged.

- [ ] **Step 1: Failing tests**: `parses an activity deep link into filters`; `round-trips hsActivityLink and hsParseHash`; `unknown tab falls back to positions`; **RF** `a deep link survives a page reload`; `back=sales shows "← Back to Sales Ledger"`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**. Run the WI015 navigation spec once: `npx playwright test tests/e2e/wi015-navigation-baseline.spec.js`; it must pass unchanged.

### Task 11: Activity tab (log) and Import tab (broker) mounted on Holdings

**Files:** Modify `…_transactions_log.js` (remove `tlModeHtml` 101, `tlManagedChipsHtml` 50, `tlSetManaged` 239 and the mode switch; add the year filter, `showCashOpening`, and a "Changes here save immediately" line), `…_transactions.js` (delete the held-lots mode), `…_broker_import.js` (account list from `investment_accounts`; hide reverted imports; year filter), `…_holdings.js` (mount). Tests `tests/frontend/transactions_log_panel.test.mjs`, `tests/frontend/broker_import_panel.test.mjs`.

**Interfaces:** `tlFilterRows(rows, {account, symbol, type, year, showCashOpening})` hides `opening` rows on symbol CASH unless `showCashOpening`; no change to add/transfer/edit calls. `biImportsHtml(list, {year, showReverted})` filters by `date_from`/`date_to` overlap.

- [ ] **Step 1: Failing tests**: `cash opening rows hidden by default and counted in the toolbar`; `no managed checkboxes or chips are rendered`; `Void is inside the edit dialog`; `import history hides reverted imports unless asked`; `import history filters by year overlap`; `broker account list excludes checking accounts`; `Activity shows a bank-account cleanup banner when Task 3's preview is non-empty`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**; regenerate the diagram.

### Task 12: Positions markers and cross-links

**Files:** Modify `…_holdings.js` (`isManagedHoldingAccount` 416 region), `src/transactions.py` (open-lot payload). Test `tests/frontend/holdings_tabs.test.mjs`.

**Interfaces:** each open-lot row exposes `date_not_on_file: boolean` (source `backfill` and type `opening`); `wash_adjustment: number | null` and `tacked_date: string | null` (null until Task 17); Positions shows the "date not on file" chip with **Fix date**, the **History** link on lot rows, and **Edit in Activity** in place of "edit them in the log". A "Log agrees with holdings" toolbar status. The To fix tab's items and the chooser's empty state link through `hsActivityLink`.

- [ ] **Step 1: Failing tests**: `backfilled lot row shows the date-not-on-file chip and Fix date`; `managed row shows an Edit in Activity link`; `History link opens Activity filtered to the account and symbol`; `holding-period check Review link carries source=backfill`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**. Also add the holding-period check server function here: `holding_period_check(input_dir, year) -> {"lots": int, "sales": int}` counting sales whose `txn_lot` joins to a backfill `opening` row, with test `test_holding_period_check_counts_backfilled_lots` in `tests/test_sales_summary_functional.py`; unmanaged-account sales are not covered (document in the card text).

---

## Phase 2: Wash rules, reviews, cards

### Task 13: `wash_reviews` table and review routes

**Files:** Modify `src/stores/sales_repo.py`, `src/stores/plan_store.py` (append a `SCHEMA_V23_DDL` to `PLAN_MIGRATIONS`), `src/server/plan_routes.py`. Tests `tests/test_wash_reviews_unit.py`, plus the existing schema-version tests.

**Interfaces:** table `wash_reviews(sale_key TEXT PRIMARY KEY, outcome TEXT CHECK(outcome IN ('wash','broker_reported','not_wash')), reason TEXT, broker_amount REAL, updated_at TEXT)`. Store methods `set_review(sale_key, outcome, reason=None, broker_amount=None)`, `reviews() -> dict[str, dict]`, `clear_review(sale_key)`. Routes `POST /api/sales/wash/review`, `POST /api/sales/wash/review/clear`. `not_wash` requires a non-empty reason. The `wash_flag` CHECK constraint is untouched.

- [ ] **Step 1: Failing tests**: `test_not_wash_requires_reason`; **RF** `test_review_survives_requeue_and_rerecord` (review keyed `account|symbol|sale_date`; voiding the rows and writing new ones keeps it); `test_migration_adds_table_on_existing_plan`; `test_clear_review`.
- [ ] **Step 2–4:** run, implement, run to PASS (including `pytest -m "not slow" -k schema`).
- [ ] **Step 5: Commit**.

### Task 14: Detection rules W1–W3

**Files:** Modify `src/wash_sales.py` (`detect_wash_sales` 72–127). Test `tests/test_wash_sales_unit.py`.

**Interfaces:**
- Produces: `detect_wash_sales(sales, buys, *, identical_groups=None, accounts=None, reviews=None) -> dict[sale_key, dict]` (the result is now keyed by the grouping key `account|symbol|sale_date`, not `sale_id`, with `loss`, `shares_sold`, `replacement_shares`, `disallowed`, `deductible`, and `matches` each carrying `txn_id`, `account`, `label`, `date`, `shares`, `value`, `is_reinvest`, `taxable: bool`, `used_shares`, `amount`). `plan_flag_updates` and `wash_flagged` skip `not_wash` reviews. Adapt the callers in `src/sales_tax_year.py` (`refresh_wash_flags_in` 211, `wash_run_status` 197).

Algorithm decisions (these are the spec's rules): sale lots are grouped by key; losses within a group are summed; buys inside ±30 days qualify unless their shares are among the lots sold in that same sale (W1); sale groups are processed in date order and each buy's shares serve only one sale, oldest buys first (W2); `used = min(shares_sold, unclaimed shares)` and `disallowed = loss × used ÷ shares_sold` (W3), spread across lots by loss share and across buys in W2 order.

- [ ] **Step 1: Failing tests** using the spec's 2026 numbers: `test_w1_same_sale_reinvests_are_not_replacements` (VGSH and VTEB 4-01 produce no flag); `test_w3_proportional_disallowance` (MUB: loss 123.61, shares sold 160.848, replacement 0.860 + 0.412 → disallowed ≈ 0.98, deductible ≈ 122.63; assert with `pytest.approx`); `test_w2_each_buy_serves_one_sale` (two loss sales, one buy: the earlier sale claims it, the later gets 0); `test_ira_replacement_marks_amount_lost_permanently` (`taxable False`); `test_not_wash_review_removes_flag`; **RF** `test_two_same_day_orders_one_key_do_not_double_count_replacements`; `test_gain_sales_never_flag`.
- [ ] **Step 2–4:** run, implement, run to PASS; also run `pytest tests/test_sales_tax_year_unit.py -v` (find with `ls tests | grep tax_year`).
- [ ] **Step 5: Commit**. The CPA must confirm W1 before release (spec). Note this in the PR description.

### Task 15: Wash cards and the Tax-year disallowed line

**Files:** Create `frontend/js/dashboard_decomp_sales_wash.js`. Modify `src/sales_tax_year.py` (`tax_year_summary` 86–125), `…_sales_queue.js` (mount in To fix), `…_sales_tax.js` (remove the old wash block, add the netting line). Tests `tests/test_sales_tax_year_wash_functional.py`, `tests/frontend/sales_wash.test.mjs`.

**Interfaces:** `tax_year_summary` gains `wash: {"disallowed", "deferred", "lost_permanently", "sales": int}` and lowers the loss used in `netting` by `disallowed`. `GET /api/sales/wash?year` returns the cards (friendly account names, `matches` with the where-it-goes text). JS renders: sold-at-loss side, replacement lines ("adds $0.66 to this lot's cost" or "lost permanently" in red), the amount line ("Disallowed $0.98 of $123.61 · $122.63 still deductible"), a Review select (Wash sale / Broker already reported it / Not a wash sale…, reason required), a "Reviewed (n)" link with Undo, and the Tax year line "Wash-sale losses disallowed (deferred $x · lost in IRA $y)".

- [ ] **Step 1: Failing tests**: py `test_netting_uses_loss_net_of_disallowed`; `test_estimated_tax_drops_with_disallowed_loss_only_when_flagged`; node `card shows both sides with friendly names`, `IRA replacement renders "lost permanently"`, `Not a wash sale without a reason is rejected`, `Reviewed list shows Undo`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**; run `python tools/fast_gates.py`.

---

## Phase 3: Basis add-back

### Task 16: `wash_adjustments` and adjusted open lots

**Files:** Create `src/wash_adjustments.py`. Modify `src/transactions.py` (`open_lots` 67, `materialize` 447), `src/stores/plan_store.py` (`SCHEMA_V24_DDL`), `src/stores/transactions_repo.py`. Test `tests/test_wash_adjustments_unit.py`.

**Interfaces:**
- Produces: table `wash_adjustments(adjustment_id INTEGER PRIMARY KEY, sale_key TEXT, replacement_txn_id INTEGER, shares REAL, amount REAL, tacked_purchase_date TEXT)`. `recompute_adjustments(store) -> int` rebuilds all rows from `detect_wash_sales` (taxable replacements only, reviews respected) and is called after any log change, sale confirm or void, review change, and wash refresh. `open_lots(...)` rows gain `wash_adjustment: float`, `adjusted_unit_cost: float` and `tacked_date`; the `lot_date` of an adjusted portion is the tacked date. W5 chains: adjustments are computed in sale-date order using adjusted costs.

- [ ] **Step 1: Failing tests**: `test_taxable_replacement_gets_basis_add_back_and_tacked_date`; `test_ira_replacement_gets_no_add_back`; `test_void_of_either_side_recomputes`; `test_w5_chain_uses_adjusted_cost`; `test_later_sale_of_adjusted_lot_includes_add_back_pro_rata`; `test_log_rows_are_never_edited`; **RF** `test_plan_with_no_wash_sales_is_byte_identical` (holdings output equals the output from before this task for a fixture plan).
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement.** Run `tools/regen_golden_master.py measure` first (record the starting values in the PR), then after implementing.
- [ ] **Step 4: Run** the unit tests, then `pytest tests/test_phase_golden_equality_regression.py -v > <scratchpad>/pytest_golden.txt 2>&1` in the background; expect no golden moves.
- [ ] **Step 5: Commit**.

### Task 17: Surface adjustments on Positions

**Files:** Modify `…_holdings.js`, `…_sales_wash.js`. Test `tests/frontend/holdings_tabs.test.mjs`.

**Interfaces:** the lot-row marker `incl. $x wash` with a tooltip naming the sale and the tacked date, linking to the wash card; the lot row shows `adjusted_unit_cost`.

- [ ] **Step 1–4:** test `adjusted lot shows incl. wash marker and adjusted unit cost`, `lot with no adjustment shows no marker`; run, implement, run to PASS.
- [ ] **Step 5: Commit**.

---

## Phase 4 and 5

### Task 18: 1099-B wash tie

**Files:** Modify `src/broker_1099b/report.py`, the apply path in `src/sales_1099b.py`, `…_sales_1099b.js`. Test `tests/test_sales_1099b_wash_unit.py`.

**Interfaces:** on apply, a row with `wash_disallowed > 0` calls `set_review(sale_key, "broker_reported", broker_amount=…)` unless the user already chose an outcome. The tie report gains `wash: {"same_account": [{"sale_key","broker","computed"}], "cross_account": [{"sale_key","amount","label"}]}`; cross-account amounts display as "not on any 1099-B: your return must include these". For a `broker_reported` sale, the broker's amount replaces ours, and the add-back is kept only for replacements in other accounts.

- [ ] **Step 1: Failing tests**: `test_apply_sets_broker_reported`; `test_user_outcome_not_overwritten`; `test_cross_account_amount_listed_separately`; `test_broker_amount_replaces_computed_without_double_count`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit**.

### Task 19: Open-window warning

**Files:** Modify `src/wash_sales.py` (new function), `src/server/plan_routes.py`, `…_sales_wash.js`, `…_sales_queue.js` (strip alert). Test `tests/test_wash_open_windows_unit.py`.

**Interfaces:** `open_windows(store, today: date) -> [{"sale_key","symbol","closes_on","reinvesting": [account labels], "also_holds": [account labels]}]` for every loss sale less than 31 days old (the window closes sale date + 30 days). An account is "reinvesting" when the log has a `reinvest` row for the symbol or an identical-group symbol in the last 12 months; wording is always "has reinvested", never "has reinvest on". `GET /api/sales/wash/open-windows`.

- [ ] **Step 1: Failing tests**: `test_window_open_for_sale_29_days_ago`; `test_window_closed_after_30_days`; `test_reinvesting_uses_last_12_months`; `test_account_holding_fund_without_reinvest_listed_as_also_holds`; `test_no_loss_sales_means_no_windows`.
- [ ] **Step 2–4:** run, implement, run to PASS.
- [ ] **Step 5: Commit.**

---

## Release steps

- [ ] Run `npm test`, `pytest -m "not slow" -v -rfE > <scratchpad>/pytest_fast.txt 2>&1`, then full `pytest` once, then `python tools/fast_gates.py`.
- [ ] Walk the app (`preview_start retirement-planner`) on the demo plan: the ledger's three tabs, Record sales, a wash card review, Holdings Positions/Activity/Import, the Year-End cash cards.
- [ ] Open the PR with the CPA-confirmation note on rule W1. Check `/usage` against the phase estimates above.

## Self-review notes

- **Spec coverage:** header and year/taxable switch (5); To fix items, including holding period (12), hide/unhide (1), wash cards (15), open windows (19); Sales (4, 6, 7); Tax year (8, 15); removals and Year-End (9); Holdings tabs (10–12); defects 1–4 (1, 2, 3, 11/12); wash rules W1–W6 (14, 16); reviews (13); 1099-B tie (18). The spec's "Calls I made" are implemented as written; nothing is left to guess except the builder choices the spec lists.
- **Type consistency:** the grouping key `account|symbol|sale_date` is used by `slGroupSales` (4), `wash_reviews.sale_key` (13), `detect_wash_sales` (14), `wash_adjustments.sale_key` (16) and `set_review` (18).
- **Open items for the builder to settle by reading the code:** the existing schema-version test names (Task 13).
