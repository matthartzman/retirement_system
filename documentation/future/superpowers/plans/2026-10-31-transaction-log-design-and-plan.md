# Transaction log: design and implementation plan

Status: **proposed, not started.** Written 2026-10-31 after the broker import shipped (#329, #330). Decisions marked
**Claude's call** can be overridden. It builds on `2026-10-30-broker-activity-bulk-import-design-and-plan.md` and the
realized-sales ledger (`2026-10-28-realized-sales-ledger-design-and-plan.md`).

> **For agentic workers:** use superpowers:subagent-driven-development or superpowers:executing-plans, task by task.
> Phases are gates: do not start a phase until the previous one is merged and its gate (section 7) is met.

**Goal:** one chronological record of every purchase, reinvestment, sale and in-kind transfer for the brokerage
accounts, from which unsold purchases show up as holdings, and which the user can add to, revise and delete.

**Architecture:** three phases, each shippable alone. (1) A read-only Transactions view over data that already exists.
(2) A `transactions` table that imports and manual entries write to, reconciled against the holdings (holdings stay
authoritative). (3) Per account, the log becomes authoritative and that account's holdings lots are rebuilt from it.
Alternative C (adding buys to the sales ledger table) is rejected and not planned.

**Tech Stack:** Python 3.12 / SQLite plan store (`src/stores`), `src/server` routes, ES-module frontend panels,
pytest + `node --test`.

## 1. Intent

Today a purchase lives in two places that do not know about each other: the holdings table (a lot, edited in place,
shares reduced when sold, removed at zero) and, for imported accounts, a `broker_activity` row. A sale is a ledger row
that points back at a lot by a JSON `lot_key` and a **position index** in the holdings. There is no single place to see
"everything that happened in this account", no way to correct a purchase other than editing the lot, and an in-kind
transfer between accounts cannot be expressed at all.

### Goals
- **Transactions page:** every buy, reinvest, sell, transfer out and transfer in, filterable by account, symbol, year,
  type, with a "Held" filter that shows the lots still open (unsold purchases = holdings).
- **Manual add, revise, delete** of any transaction the user owns (imported rows can be revised or deleted too, see 3.4).
- **Transfers between accounts** (in kind), keeping the original purchase date, price (basis) and lot type so holding
  period and gain are preserved. No realized sale, no ledger row.
- **No Monarch-sourced sales** in the log (user decision). Monarch candidates keep flowing through the sales queue.
- Holdings, the engine and the workbook keep reading the same `holdings_lots` rows, so no existing consumer changes.

### Non-goals
- Dividends, interest and fees as log rows. They stay in `broker_activity` and the income check.
- Cash transfers, contributions, Roth conversions (the plan already models conversions; a transfer here moves lots only).
- Stock splits, spin-offs, mergers (a manual adjust row can express them later; not planned).
- Tax-lot methods other than the existing allocation helpers (`suggest_allocation`, `allocate_lots`).
- Changing the sales ledger table or its tax panels.

### Anti-goals (failure even if it "works")
- Any engine, workbook or golden-master output changes. Holdings rows must come out identical.
- A rebuild that silently drops a hand-entered lot or a lot consumed by a Monarch-confirmed sale.
- A sale confirmed twice, or shares consumed twice, once both the old path and the log exist.
- Edit or delete that loses the audit trail (always void-and-replace, never hard delete).

## 2. What exists (verified 2026-10-31)

- `src/stores/broker_repo.py`: `broker_imports`, `broker_activity` (every imported row: `kind` in `normalized.KINDS`,
  `quantity`, `price`, `amount`, `row_key` unique, `candidate_id`, `lot_ref` JSON), `broker_account_map`. Schema v19 is
  the latest: `PLAN_MIGRATIONS` in `src/stores/plan_store.py:162` ends at `SCHEMA_V19_DDL`.
- `src/stores/sales_repo.py`: `realized_sales` (one row per lot sold, `source` includes `broker`, `monarch`, `manual`,
  `lot_key` JSON, status `confirmed`/`voided`, `revision_ref`), `sale_candidates` (the queue), void-and-replace editing.
- `src/sales_confirm.py`: `_holdings_lots` reads open lots from `store.dataset("holdings")` with `lot_id` = row index;
  `confirm_in` reduces shares and drops zero lots; `undo` restores them. `default_tax_class(store, account)`.
- `src/broker_import.py::_commit_part` writes holdings lots, queue candidates and activity rows in one transaction.
- Holdings row shape (`HoldingLot`): `account, symbol, purchase_date, shares, purchase_price, lot_type, note` as text.
- `broker_activity` has no transfer kind today: E*Trade "Transfer" and Fidelity journals parse as `other`.

## 3. Design

### 3.1 Storage (plan schema v20, phase 2)

New module `src/stores/transactions_repo.py` (`store.transactions`), DDL appended to `PLAN_MIGRATIONS` as
`SCHEMA_V20_DDL`.

`transactions`
| column | notes |
|---|---|
| `txn_id` INTEGER PK | also the **lot id** of the lot a buy/reinvest/transfer_in creates |
| `txn_date`, `settle_date` | ISO dates |
| `account` NOT NULL | plan account (internal name) |
| `type` | `buy`, `reinvest`, `sell`, `transfer_out`, `transfer_in`, `opening` |
| `symbol`, `shares` (>0), `price`, `amount`, `fees` | `price` = basis per share for lot-creating types |
| `lot_type` | `buy` / `reinvestment` / other holdings lot types, copied to the holdings row |
| `transfer_group` TEXT NULL | shared by the out/in pair |
| `lot_date`, `origin_lot_txn_id` | on `transfer_in`: the origin lot's purchase date (the holding-period clock) and its `txn_id` |
| `source` | `broker`, `manual`, `backfill` (never `monarch`) |
| `activity_id` INTEGER NULL | the `broker_activity` row it mirrors |
| `candidate_id`, `sale_ids` | links to the queue candidate and ledger rows for a `sell` |
| `note`, `status` (`active`/`voided`), `revision_ref`, `created_at`, `updated_at` | void-and-replace like the ledger |

`transaction_lots` (what a `sell` or `transfer_out` consumed): `txn_id`, `lot_txn_id`, `shares`. A lot's remaining shares
= its creating row's shares minus the sum of `transaction_lots` rows from active disposals. A `transfer_in` creates a
new lot (its own `txn_id`) and records `origin_lot_txn_id` so the chain is traceable; it copies purchase date, price and
lot type from the origin lot (stored on the row as `lot_date`).

`opening` rows are the escape hatch for lots that exist in holdings with no purchase on file (hand-entered, pre-2026,
Monarch-era). They carry the lot's own purchase date and price.

Why a lot id instead of the holdings position index: the index is only valid against the holdings the panel was read
from and breaks if the user reorders or deletes a row. Phase 2 keeps the index path for the old queue, and phase 3
switches managed accounts to lot ids.

### 3.2 Service `src/transactions.py` (pure functions plus store calls)

- `open_lots(store, account=None, symbol=None, as_of=None) -> list[Lot]` replays active rows.
- `add(input_dir, **fields) -> int`, `revise(input_dir, txn_id, **fields) -> int` (void old, insert new with
  `revision_ref`), `void(input_dir, txn_id) -> None`. Refuse when it would make any lot negative at any later date
  (replay check) or when a later sale already consumed the lot (message names the sale, "undo it in the queue first").
- `transfer(input_dir, *, from_account, to_account, symbol, allocation, txn_date) -> {"group": str}`: writes the out/in
  pair in one transaction; allocation is `{lot_txn_id: shares}`.
- `reconcile(store, account=None) -> list[Drift]` compares `open_lots` to `holdings_lots` per (account, symbol,
  purchase date, price) and returns differences with a plain-language reason.
- `backfill(store) -> dict` builds the log from existing data (3.3).

### 3.3 Backfill (idempotent)

For each account with broker imports: one row per `broker_activity` trade row (`buy`/`reinvest`/`sell`), `source =
broker`, `activity_id` set. Sells take their allocations from the confirmed `realized_sales` rows of that candidate
(`lot_key` -> purchase date/price -> the matching created lot). **Monarch-sourced ledger sales are skipped** and the
lots they consumed are not replayed: so for every open holdings lot with no matching log lot, write an `opening` row
with the lot's current shares, date and price. This makes `open_lots` equal holdings on day one by construction, and
the reconciliation proves it. Re-running adds nothing (keyed on `activity_id` / lot identity).

### 3.4 Editing imported rows

Revising or voiding a `broker`-source row is allowed (user decision) but it diverges from the file. Rule (**Claude's
call**): the original `broker_activity` row is never changed; the log row is voided/replaced and carries a note
"revised from import". A later re-import of the same file does not resurrect it because `row_key` already exists.
Reverting the whole import is refused while any of its log rows was revised, with the list of revised rows.

### 3.5 Transfers

An in-kind move is two rows with one `transfer_group`: `transfer_out` in the source account (consumes lots like a sell,
via `transaction_lots`) and `transfer_in` in the destination (creates lots with the same date, price and lot type).
No `realized_sales` row and no queue candidate. Importing: phase 2 adds a `transfer` kind to the E*Trade and Fidelity
parsers only when a sample file shows both legs with symbol and shares; until then transfers are manual entries. A
transfer across tax classes (for example taxable to Roth) is recorded but flagged "check whether this is a
conversion or contribution; the log does not model the tax".

### 3.6 Monarch exclusion

The log never stores a Monarch sale. Phase 2 leaves the queue as is for all accounts. In phase 3 a managed account
refuses to confirm a `monarch` candidate with "this account is managed by the transaction log; record the sale there
and dismiss this one" (it already offers dismiss), because a Monarch confirm would reduce a holdings lot the log does
not know about.

### 3.7 Phase 3: authoritative per account

A per-account flag `ledger_managed` (table `transaction_accounts`, one row per managed account). On every log write,
inside the same transaction, `materialize(store, account)` rewrites that account's rows in `holdings_lots` from
`open_lots` (account's rows replaced, every other row untouched, order stable by account, symbol, purchase date). The
holdings editor shows managed accounts read-only with a link to the Transactions page. The existing queue confirm for
a managed account writes a `sell` log row with allocations, then materializes, instead of editing holdings directly.
Un-managing an account stops materialization and leaves its last rows in place.

### 3.8 UI

Transactions panel on the Sales Ledger page (new file `frontend/js/dashboard_decomp_transactions.js`, mounted like the
broker import panel): filter bar (account via friendly names, symbol, year, type, Held only), table (date, account,
type, symbol, shares, price, remaining, linked sale or transfer, source), per-row Edit / Void (phase 2), an "Add
transaction" form and a "Transfer between accounts" form with lot pick (phase 2), a reconciliation banner (phase 2),
and a Managed toggle per account (phase 3). Account pull-downs use `accountDisplayLabel` and keep internal values.

### 3.9 Routes (`src/server/plan_routes.py`, `route_manifest.py`)

`GET /api/transactions?account&symbol&year&type&held` (phase 1), `POST /api/transactions`, `POST
/api/transactions/<id>/revise`, `POST /api/transactions/<id>/void`, `POST /api/transactions/transfer`, `GET
/api/transactions/reconcile`, `POST /api/transactions/backfill` (phase 2), `POST /api/transactions/accounts/<account>/managed`
(phase 3).

## 4. Phases and tasks

Each task: tests first, commit at the end. Per the project convention, every task lists recommended model/effort and
a relative usage estimate; check `/usage` against these as the plan runs.

### Phase 1: read-only Transactions view (alternative B)

Gate to start: none. Produces no schema change, so it is safe to ship alone.

**Task 1.1: view model `src/transactions_view.py`**
- Files: create `src/transactions_view.py`; test `tests/test_transactions_view_unit.py`.
- Produces: `build_view(store, *, account=None, symbol=None, year=None, types=None, held_only=False) -> dict` with
  `rows: list[{date, account, type, symbol, shares, price, amount, remaining, linked, source}]` and `held:
  list[{account, symbol, purchase_date, price, shares}]`.
- Sources: `store.broker.activity(kinds=("buy","reinvest","sell"))`; confirmed `realized_sales` with `source` in
  (`broker`, `manual`) (never `monarch`); `store.dataset("holdings").rows()` for `remaining` and the Held list (a buy's
  `remaining` = the matching holdings lot's shares, matched by `lot_ref`).
- Tests: `test_monarch_sales_excluded`, `test_unsold_buy_listed_as_held_with_remaining`,
  `test_partly_sold_lot_shows_remaining`, `test_manual_sale_included`, `test_filters_by_account_symbol_year`.
- Model/effort: Sonnet, medium. Usage: light-moderate. Driver: reading `broker_import.py` lot_ref handling
  (grep, do not read whole) and two store repos.

**Task 1.2: route `GET /api/transactions`**
- Files: modify `src/server/plan_routes.py`, `src/server/route_manifest.py`; test `tests/test_transactions_routes_functional.py`.
- Tests: `test_get_transactions_returns_rows`, `test_unknown_filter_value_is_empty_not_error`.
- Model/effort: Sonnet, low. Usage: light.

**Task 1.3: panel `dashboard_decomp_transactions.js`**
- Files: create `frontend/js/dashboard_decomp_transactions.js`; modify `frontend/index.html` (script tag), the Sales
  Ledger page mount; test `tests/frontend/transactions_panel.test.mjs`.
- Produces: `renderTransactions()`, `trLoad()`, `trHtml(view)`; account cells use `accountDisplayLabel`.
- Tests: `renders friendly account names`, `Held filter lists only open lots`, `escapes user text`.
- Housekeeping in the same PR: raise `TOTAL_JS_MAX_LINES` in `tests/test_frontend_size_ratchet.py` with a dated note;
  run `python tools/generate_system_diagram.py` and commit the diagram (CI checks both).
- Model/effort: Sonnet, medium. Usage: moderate. Driver: wiring into the ledger page (grep `renderSalesLedger`, read
  only that region of the large dashboard files).

### Phase 2: transactions table and reconciliation (alternative D)

Gate to start: phase 1 merged and used on the real plan for one import cycle.

**Task 2.1: schema v20 and repo**
- Files: create `src/stores/transactions_repo.py` (`SCHEMA_V20_DDL`, `TransactionsRepo`); modify
  `src/stores/plan_store.py` (append to `PLAN_MIGRATIONS`, add `store.transactions`); test
  `tests/test_transactions_repo_unit.py`.
- Produces: `TransactionsRepo.insert(**f) -> int`, `get(txn_id)`, `list(*, account=None, symbol=None, year=None,
  include_voided=False)`, `void(txn_id)`, `add_disposal(txn_id, lot_txn_id, shares)`, `disposals(txn_id)`.
- Tests: `test_migration_from_v19_keeps_existing_data`, `test_type_check_rejects_unknown_type`,
  `test_monarch_source_rejected`, `test_shares_must_be_positive`, `test_void_keeps_row`.
- Model/effort: Sonnet, high (schema work, mirror `broker_repo.py` conventions). Usage: moderate. Driver: migration
  tests; check any test that asserts the schema version number and update it.

**Task 2.2: service core (`open_lots`, `add`, `revise`, `void`)**
- Files: create `src/transactions.py`; test `tests/test_transactions_unit.py`.
- Tests: `test_open_lots_replays_buys_and_sells`, `test_revise_voids_old_and_links_revision`,
  `test_void_buy_refused_when_later_sale_consumed_it`, `test_revise_refused_if_lot_goes_negative_later`,
  `test_date_order_independent_of_entry_order`.
- Model/effort: Opus, high (the replay rules decide correctness). Usage: moderate-heavy. Driver: test-fix loop on the
  negative-position rule; scope it by writing the replay as a pure function over lists first.

**Task 2.3: transfers**
- Files: modify `src/transactions.py`; test `tests/test_transactions_transfer_unit.py`.
- Produces: `transfer(...)` per 3.2.
- Tests: `test_transfer_preserves_date_price_and_lot_type`, `test_transfer_writes_no_ledger_row`,
  `test_transfer_atomic_when_destination_write_fails`, `test_transfer_more_than_lot_refused`,
  `test_cross_tax_class_transfer_flagged`.
- Model/effort: Sonnet, high. Usage: moderate.

**Task 2.4: backfill and reconcile**
- Files: modify `src/transactions.py`; test `tests/test_transactions_backfill_unit.py`.
- Tests: `test_backfill_idempotent`, `test_monarch_sales_skipped_and_lots_become_opening_rows`,
  `test_open_lots_equal_holdings_after_backfill`, `test_reconcile_reports_hand_edited_lot`,
  `test_reconcile_clean_after_import_commit`.
- Model/effort: Opus, high. Usage: heavy. Driver: realistic fixtures (reuse `tests/broker_activity_fixtures.py`); keep
  the fixture set small and add one Vanguard multi-account case.

**Task 2.5: dual-write from the importer and the queue**
- Files: modify `src/broker_import.py::_commit_part` (write log rows in the same transaction; do not change holdings or
  queue behavior), `src/sales_confirm.py::confirm_in` / `undo` (write or void the `sell` row and its disposals); tests
  `tests/test_broker_import_log_unit.py`.
- Tests: `test_commit_writes_log_rows_and_holdings_unchanged`, `test_revert_voids_log_rows`,
  `test_revert_refused_when_log_row_revised`, `test_confirm_writes_sell_with_disposals`, `test_undo_voids_sell`,
  `test_monarch_confirm_writes_no_log_row`, plus the whole existing broker and sales suites unchanged.
- Model/effort: Opus, high. Usage: heavy. Driver: touching two hot paths; run `pytest tests/test_broker_*` and
  `tests/test_sales_*` after each edit, and read only `_commit_part` and `confirm_in`/`undo` (see the large-file list).

**Task 2.6: routes and panel (add, revise, void, transfer, reconcile)**
- Files: modify `src/server/plan_routes.py`, `route_manifest.py`, `frontend/js/dashboard_decomp_transactions.js`; tests
  `tests/test_transactions_routes_functional.py`, `tests/frontend/transactions_panel.test.mjs`.
- Tests: route round-trips for each endpoint; panel: `edit form posts revise`, `void asks to confirm`,
  `transfer form lists only lots with remaining shares`, `reconciliation banner lists drift`.
- Housekeeping: line ceiling note, system diagram regen.
- Model/effort: Sonnet, medium. Usage: moderate-heavy. Driver: panel size; split into a second file if the line count
  of the transactions module passes about 300.

**Task 2.7: transfer kind in importers (only with a real sample)**
- Files: `src/broker_activity/etrade.py`, `fidelity.py`, `normalized.py` (`KINDS`), tests with a trimmed sample.
- Gate: a real file showing both legs. Without it, skip; manual transfers cover the need.
- Model/effort: Sonnet, medium. Usage: light-moderate.

### Phase 3: authoritative per account (alternative A, staged)

Gate to start: phase 2 merged and `reconcile` shows zero drift on the real plan through one more import cycle.

**Task 3.1: `transaction_accounts` and `materialize`**
- Files: modify `src/stores/transactions_repo.py` (table in a `SCHEMA_V21_DDL`), `src/transactions.py`; test
  `tests/test_transactions_materialize_unit.py`.
- Produces: `set_managed(input_dir, account, on: bool)`, `materialize(store, account) -> int` (rows written).
- Tests: `test_materialize_leaves_other_accounts_untouched`, `test_materialized_rows_match_pre_switch_holdings`,
  `test_materialize_is_idempotent`, `test_unmanage_keeps_last_rows`.
- Model/effort: Opus, high. Usage: heavy.

**Task 3.2: managed accounts in confirm and holdings editor**
- Files: modify `src/sales_confirm.py` (managed account: sell goes through the log, lot ids not indexes; Monarch
  candidates refused per 3.6), holdings editor panel `frontend/js/dashboard_decomp_holdings.js` (read-only rows for
  managed accounts, link to Transactions); tests alongside the existing ones, and
  `tests/test_zip_screen_panel_functional.py`-style text assertions read first if any apply to holdings panel JS.
- Tests: `test_managed_account_confirm_materializes_holdings`, `test_monarch_confirm_refused_for_managed_account`,
  `test_holdings_editor_marks_managed_rows_read_only`.
- Model/effort: Opus, high. Usage: heavy. Driver: the holdings panel is a large JS file; grep the row renderer, read
  only that region.

**Task 3.3: switch-over and golden check**
- Not code. For each account: run `reconcile`, switch on, run the plan build, compare workbook and engine outputs with
  the pre-switch build using `tools/regen_golden_master.py measure` (never `regen`). Any delta stops the switch.
- Model/effort: Sonnet, medium. Usage: light-moderate (one build per account).

## 5. Global constraints

- Holdings and golden-master outputs must not change at any step; `measure` before any pin work, never regen.
- Docs-only commits do not wait on CI; code commits do. Regenerate the system diagram on any `src/` or `frontend/`
  structural change; keep `TOTAL_JS_MAX_LINES` honest with a dated note.
- Account names shown in the UI use `accountDisplayLabel`; values stay internal.
- Read large files by grep and offset (`dashboard.js`, `dashboard_decomp_row_model.js`, `module_catalog.py`, and so on).
- pytest runs use `-v -rfE` redirected to a scratchpad log.

## 6. Review focus (inputs the tasks do not otherwise force)

- Out-of-order entry: a back-dated buy added after a sale that predates it; the replay must judge by date, not entry
  order (`test_date_order_independent_of_entry_order`).
- Partly sold lot revised: changing a buy's shares below what later sales consumed must be refused with the sale named.
- Same-day buy and sell of one symbol: the buy counts first (matches how the importer orders a day).
- Fractional shares: use the existing `_EPS` tolerance and `_fmt`; reinvestments produce 4+ decimals.
- Transfer where source and destination are the same account, or the destination account does not exist in the plan:
  refuse with a plain message.
- Re-import after a revision or void: no duplicate, no resurrection (3.4).
- Account renamed in the plan: log rows keep the old name; reconcile reports it as drift rather than losing it.

## 7. Gates and rollback

- **Phase 1:** view matches the broker import for the 2026 data (spot check three accounts by hand).
- **Phase 2:** `reconcile` clean after backfill on a copy of the real plan, and again after the next real import.
  Rollback: the log is additive; dropping dual-write returns to today's behavior. The table stays unused.
- **Phase 3:** per account, zero drift and unchanged build outputs. Rollback: `set_managed(account, False)`.

## 8. Cost summary (relative to a 5-hour Pro session; check `/usage`)

| Phase | Rough size | Heaviest steps |
|---|---|---|
| 1 | one light-to-moderate session | 1.3 (panel wiring) |
| 2 | two to three sessions | 2.4 backfill fixtures, 2.5 hot-path dual-write: both are repeated test-fix cycles; scope by running only the broker and sales test files while iterating, the full suite once at the end |
| 3 | one to two sessions | 3.1 and 3.2; avoid reading the holdings panel whole |

Disproportionately expensive if unscoped: any step that runs the full `pytest` repeatedly (use the fast loop
`pytest -m "not slow"` and single files), and 2.6 if the panel is built in one file.

## 9. Open items

- A real transfer sample from E*Trade and Fidelity (task 2.7).
- Whether phase 3 should eventually cover Monarch-fed accounts that have no broker file (they would need `opening`
  rows and manual entries only). Deferred until phases 1 and 2 are in use.
