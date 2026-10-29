# Realized-sales ledger — design + implementation plan

Date: 2026-10-28
Status: approved (Phase 1 step 1.1 implemented; later steps pending). Decisions in section 2 are the user's and are not reopened here.

All dollar figures below are sample numbers, not real balances.

## 1. Intent

Today a sale leaves no trace. `input/client_holdings.csv` (stored as the `holdings_lots` table of the plan file) is a snapshot of *current* lots; when a lot is sold the row simply disappears on the next import. Nothing records the proceeds, the basis taken, the gain or loss, the holding period, or the tax. Monarch's transaction export does carry Sell rows, but the YTD pipeline throws them away as transfers. The Financial Trends Live Snapshot says so on its face: "Gains on positions sold since <start> are not included."

The goal is a **realized-sales ledger** that is the system of record for sales, feeds a correct tax picture (current-year estimate and the projection's year 1), and lets Trends count sold lots in returns.

### Goals
- One ledger row per lot sold (or part of a lot), with proceeds, basis, gain/loss, holding period, wash-sale flag, source and link to the Monarch transaction.
- Specific-lot identification only, with fast, undoable confirmation.
- Correct tax netting for taxable accounts; sales in IRA/Roth/HSA recorded as trades with no tax.
- Realized gains/losses reach the current-year tax estimate and seed the projection's year 1, and the plan is **byte-identical when the ledger is empty**.
- Trends: sold lots count in returns (removes the "sold positions not included" caveat), a Realized gains and losses view, daily logged year-to-date figures, and a tax line that does not double count unrealized-gain tax.
- Year-end 1099-B import corrects the ledger and reports every difference.

### Non-goals (v1)
- No automatic lot guessing and no silent pre-fill.
- No automatic wash-sale basis adjustment (flag only).
- No trading, no brokerage connection.
- No Form 8949 / Schedule D export (a later phase can render one from the ledger).
- No crypto, options, or short sales; no mutual-fund average-cost method beyond what section 11 notes.

### Anti-goals (failure even if it "works")
- A sale attributed to the wrong lot without the user having confirmed it.
- Double counting: a sale reducing holdings *and* being counted again as a Monarch outflow or as spending; capital-gain distributions counted as both investment income and realized gains.
- A percent-only user receiving any dollar amount, share count or price.
- A changed golden master when the user has recorded no sales.

## 2. Decisions (user)

| Topic | Decision |
|---|---|
| Lot selection | **Specific lots only.** A sale stays *unmatched* until the user confirms the lots. |
| Account types | Only taxable accounts (trusts, brokerage) create tax events. IRA, Roth, HSA sales are trades with no gain or tax. |
| 1099-B | The ledger is the running estimate; the year-end 1099-B import corrects basis/gain with official numbers and flags every difference. |
| Wash sales | **Flag only** in v1, across the household's accounts including IRAs and the spouse's. |

### Calls made by Claude (override any of these)
- Ledger lives in the **plan file** (`plan.db`), not the Trends balance store, because the Planner (tax, projection) and Trends both need it and the plan file already owns holdings lots and revisions. Trends reads it through the existing app-sync path.
- Proceeds are **net of fees**; fees kept in a separate column.
- Holding period uses the **calendar rule** (more than one year: purchase date + 1 year strictly before the sale date), computed in one shared helper, not the existing year-granularity helper (section 10).
- "Unmatched" sales do **not** touch holdings or the ledger totals until confirmed; they appear as a queue and as a visible "unconfirmed sales" figure on Trends.

## 3. What exists today (verified in the repo)

| Need | Where | Notes |
|---|---|---|
| Lots on disk | `input/client_holdings.csv`; plan-file table `holdings_lots` (`src/stores/datasets.py`, `HOLDINGS_COLUMNS`, `_V2_DATASETS`) | Columns on disk: `account,symbol,purchase_date,shares,purchase_price,lot_type` (the service template also has `note`). `lot_type` includes `buy` and `reinvest…`. No sale history. |
| Lot loading | `src/parsing/client_sections.py` ~1303-1337 | Builds `lots_by_account[acct][sym] = [TaxLot…]` from `active_dataset_text('holdings')`; cost basis = shares × `purchase_price`; skips `shares <= 0`. |
| Lot objects | `src/core.py` `TaxLot` (`symbol, qty, cost_basis, purchase_date`), `LotEngine` (HIFO/LIFO/FIFO selection for *projected* withdrawals) | `LotEngine` is for simulated draws; it is not a record of real sales and is not reused as a ledger. |
| Holdings import | `src/import_preview.py` `preview_holdings_import(current_text, incoming_text, mode=...)`; `src/server_services/holdings_service.py` (`read_holdings`/`save_holdings` → `write_active_dataset`) | Side-effect-free preview, modes replace/reload/merge-style. Duplicate key `_holding_key` = account, symbol, purchase date, shares, price. **It has no notion of "lots that disappeared"**; that is the hook for sale detection. |
| Plan store | `src/stores/plan_store.py`: `PLAN_MIGRATIONS` = `_SCHEMA_V1 … SCHEMA_V16_DDL` (16 today), `PLAN_SCHEMA_VERSION = len(PLAN_MIGRATIONS)`; DDL for datasets in `src/stores/datasets.py` (`SCHEMA_V15_DDL`, `SCHEMA_V16_DDL` are `ALTER TABLE` migrations); revisions snapshot dataset rows (`revision_rows`) | A new table is a new `SCHEMA_V17_DDL` appended to the tuple. Monarch tables (`monarch_balances`, `monarch_account_map`, `reconcile_log`) live in `src/stores/monarch_repo.py` as precedent for a non-dataset table. |
| Demo seed | `tools/build_demo_seed.py` builds `src/reference/demo_seed.rpx` from `input/demo`; `--check` fails if stale | A schema bump changes the seed file's schema version; the seed must be rebuilt in the same PR. |
| Tax lots → tax | `src/gain_harvest.py`, `src/tlh.py` (`select_harvest_lots`, `_is_long_term`, replacement universe comments about the 30-day rule) | `tlh._is_long_term` compares **calendar years** (`year - acquisition_year >= 1`); good enough for planning, wrong for a ledger. `tlh.py` contains wash-sale *avoidance* (replacement choice), not a detector over past trades — there is little to reuse beyond the substantially-identical groupings in the security master. |
| Carryforward | `src/projection_stages/year_state.py` `cap_loss_carryforward` (default `0.0`, rolled between years); threaded through `deterministic_engine.py` (~309, ~1421-1434) into `apply_investment_tax_cascade` | Year 1 starts from `create_initial_year_state(config)`, which is where a prior-year carryforward would enter. Gains from the engine's own withdrawals use `ltcg_gain`; home/rental sales enter AGI via `sale_gain_in_agi` (`deterministic_engine.py` ~1275). |
| AGI policy | `documentation/reference/CAPITAL_GAINS_IN_AGI.md` | Home/rental sale gains already enter AGI/MAGI/IRMAA; investment-sale gains from the withdrawal cascade do too (WI-024). Realized gains from the ledger must use the same path, not a new one. |
| YTD spending | `src/ytd_tracking.py`: `EXCLUDED_SPENDING_CATEGORIES`, `TRANSFER_RE` (matches "investment buy/sell", "transfer"…), `is_ignored_ytd_spending_flow`, `classify_investment_transaction`, `income_kind_for_category` | Buy/Sell/Transfer never count as spending. "Dividends & Capital Gains" counts as investment income. |
| Monarch Sell rows | `input/ytd_transactions.csv`, columns `Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner, Monarch Id` | At design time: ~5,400 rows, **~315 Sell** and ~470 Buy. About **243** Sell rows have parseable text of the form `Sold <n> <TICKER> @ <price>`; about **72** are bare (49 are literally "Sell", the rest are fund-sponsor-style names). `Monarch Id` gives a stable key. |
| Reconciliation | `src/reconcile.py` (account mapping, `reconcile_log`); Trends `live_snapshot.py` `_reconcile_accounts`, `_hints` | Hints today: `after_balance_date`, `stale_prices`, `matches_position`, `direction`. The "a sale or transfer out may not be entered yet" text is a UI phrase for the `direction` case. |
| Trends returns | `financial_trends_reporter/live_snapshot.py`: `_positions` (Modified Dietz over current lots: baseline-held lot → `start`; later buy → `new_money`, time-weighted into `weighted`; reinvested → neither), `_summarize`, `_position_rows`, `_planner_tax` (tax roll-up on **unrealized** gains via `src/after_tax`), `compute`; `frontend/live_snapshot.js` (note text ~299), `frontend/live_groups.js` (Group By totals), `trends_metrics.py`, `trends_log.py` (daily log, `append_or_replace_entry`) | Returns are over lots held *now*; a sold lot has no row, so its gain vanishes — the stated caveat. |
| Percent view | `financial_trends_reporter/percent_view.py`: `NON_MONEY_KEYS` allowlist, ratio suffixes `_rate/_pct/_ratio/_fraction`, `_PUBLIC_QUANTITY_KEYS = shares/quantity/purchase_price/price` stripped, `find_money_leaks`, `scale_payload` | Fail closed: unknown numeric keys are scaled by one constant. Share counts and prices must be removed, since shares × public price reveals the scale. |

## 4. Data model and schema change

### 4.1 Table `realized_sales` (plan file, migration v17)

One row per lot (or partial lot) sold. Money is stored as integer cents or REAL consistent with neighboring tables (check `datasets.py` conventions when building; the dataset tables use TEXT columns, so decide in Phase 1 whether the ledger is a typed table like `monarch_*` — **recommended** — rather than a text dataset).

| Column | Meaning |
|---|---|
| `sale_id` | PK, stable id (UUID or autoincrement + `source_key` unique) |
| `sale_date` | trade date (ISO) |
| `settle_date` | nullable; informational (see risks) |
| `account` | account key as in holdings |
| `tax_class` | snapshot of `taxable / pre_tax / roth / hsa` at entry, so later renames don't rewrite history |
| `symbol` | uppercase ticker |
| `shares` | shares sold from this lot |
| `proceeds` | gross proceeds for these shares |
| `fees` | selling costs |
| `basis` | cost basis taken from the lot |
| `purchase_date` | lot's acquisition date (holding-period clock, after wash-sale adjustments in a later phase) |
| `holding_period` | `short` / `long` (derived, stored for audit) |
| `gain` | proceeds − fees − basis (null for non-taxable classes) |
| `wash_flag` | `none` / `possible` / `confirmed_by_user`; plus `wash_note` |
| `source` | `holdings_diff` / `monarch` / `manual` / `1099b` |
| `monarch_id` | nullable link to the Monarch transaction |
| `lot_key` | the holdings lot identity at the time (account, symbol, purchase date, price) for audit |
| `status` | `confirmed` / `voided` (void = undo; rows are never hard-deleted, so undo is reversible) |
| `official_*` | nullable 1099-B proceeds/basis/gain/holding period, filled by the import (Phase 5) |
| `created_at`, `updated_at`, `revision_ref` | audit |

### 4.2 Table `sale_candidates` (the unmatched queue)

A *sale event* that is not yet tied to lots: source (`monarch` / `holdings_diff`), date, account, symbol (nullable), shares (nullable), price (nullable), amount, `monarch_id`, `state` (`unmatched` / `confirmed` / `dismissed` / `not_a_sale`), `confirmed_sale_ids` (JSON). The queue is the only place unconfirmed sales exist; they never feed tax or returns, but their count and amount are surfaced.

### 4.3 Table `realized_adjustments`
Year-level inputs the ledger cannot derive: prior-year capital-loss carryforward (short and long term, entered by the user from last year's Schedule D), and an optional override of the state rate. One row per tax year.

### 4.4 Schema bump
- Append `SCHEMA_V17_DDL` to `PLAN_MIGRATIONS` (`plan_store.py`); `PLAN_SCHEMA_VERSION` follows automatically. Upgrading old plan files is a pure `CREATE TABLE`, no data rewrite, so it is safe and cheap.
- Rebuild `src/reference/demo_seed.rpx` with `python tools/build_demo_seed.py` and check `--check`.
- Decide whether `revision_rows` should snapshot ledger rows. **Recommendation:** no; the ledger carries its own `status`/audit columns and is append-mostly. Confirm in Phase 1 that restoring a plan revision does not silently delete sales (must not).
  **Resolved in step 1.1 (2026-10-28): restores leave ledger rows intact.** `restore_revision` / `_restore_tables` only delete and refill `plan_rows`, the flat `_DATASETS` tables and the rental tables; `_capture_tables` snapshots the same set. The ledger tables are typed (like `monarch_*`) and in neither list, so they are neither captured nor touched. Pinned by `test_ledger_survives_revision_restore` (a sale recorded after the snapshot survives the restore). Revisions mechanism unchanged. Consequence to remember: restoring an old revision brings back old holdings lots but not the ledger's effect on them, so a sale undone by restore will reappear as lots while its ledger row stays; the confirm/undo flow (Phase 2) is the supported path, not revision restore.
- Any test that pins `PLAN_SCHEMA_VERSION` or counts tables will need updating; grep the tests for `PLAN_SCHEMA_VERSION` and `plan_meta` when starting Phase 1.
- Does the Trends reporter read the plan file? **Resolved in step 1.1: yes, through the store.** `financial_trends_reporter/app_sync.py` (`sync_from_app`) and `live_snapshot.py` (~905) open the active plan with `active_plan.workspace_store(Path(base_dir))` and read typed repos off it (`store.monarch.mapping()`, `store.dataset(...)`). The ledger is reachable the same way as `store.sales.list_sales(year=...)`; Phase 4 needs no new path, only to wrap the call in the same try/except (plan missing, locked, or older than v17 opens migrated, so the tables exist).
- Types/shape chosen in 1.1: money columns `REAL` (as `monarch_balances`), ISO text dates, `sale_id`/`candidate_id` autoincrement; `sale_candidates.monarch_id` is UNIQUE (partial index) so re-importing the same file is a no-op, while `realized_sales.monarch_id` is not unique because one Monarch sale can split across several lots. `realized_adjustments` is keyed by `tax_year`. Repo: `src/stores/sales_repo.py`, reached as `store.sales`.

### 4.5 Why a new table, not more holdings columns
Holdings lots are mutable current state, rewritten wholesale by an import. A ledger needs history that survives that rewrite. They are linked by `lot_key`, not by foreign key.

## 5. How rows get in

### 5.1 Holdings-import diff (Phase 1)
`preview_holdings_import` already compares incoming and current rows by `_holding_key`. Extend it (pure function, no side effects) to also return `disappeared_lots` and `reduced_lots`: current lots absent from the incoming file, or present with fewer shares (same account/symbol/purchase date, smaller `shares`). Rules:
- In **replace** mode, a disappeared/reduced lot is a *candidate sale*, shown in the preview ("3 lots look sold").
- In **merge** mode (add-only), nothing is inferred.
- A lot that disappeared in one account while the same symbol appears in another account within a few days is flagged as a possible **transfer**, not a sale.
- A lot whose share count changed with a basis change is flagged as a possible **split or corporate action** (section 11), not a sale.
- Because lots are the user's specific lots, a diff-detected sale is **already lot-specific** (we know which lot vanished) — it needs only price/proceeds. Proceeds come from a matching Monarch Sell row if any (section 5.2), otherwise from the user (default suggested: previous close on the sale date, shown but not applied).
- Saving the import writes the new holdings and creates `sale_candidates` rows; the user confirms them in the queue. Nothing is auto-confirmed.

### 5.2 Monarch Sell matching (Phase 2)
Source: the YTD transaction rows with `Category == Sell` (and Buy rows, used for wash-sale detection and for cost of replacement lots).
- **Parse** `Original Statement` / `Merchant` with a conservative regex for `Sold <shares> <TICKER> @ <price>` → symbol, shares, price; proceeds = Amount (positive on the sell). Parseable rows (~three quarters at design time) are pre-parsed; the rest are *bare*: only date, account, amount.
- **Candidate matching to holdings events:** for a parsed row, look for a disappeared/reduced lot in that account and symbol (same shares ± rounding). If exactly one clean match exists, show it as "suggested" — still confirmed by the user.
- **Unmatched queue:** every Sell row that has not been confirmed or dismissed. Sorted newest first, filtered by account, year, parseable/bare. Bare rows need the user to supply the ticker and shares (or dismiss as e.g. a mutual-fund exchange).
- **Idempotent:** key on `Monarch Id`; re-importing the YTD file never re-queues a confirmed or dismissed row (`INSERT … ON CONFLICT DO NOTHING`).
- Sells in non-taxable accounts are accepted the same way but need no lots chosen for tax (see 5.5); holdings reduction still needs lots to keep share counts honest.

### 5.2b Broker activity CSV (Phase 2)
Source: the broker's own all-transactions history file (Fidelity's "History for Account" export is the first and is in hand; other brokers are expected to have an equivalent, unverified). For a broker that offers it this is a **better sale source than Monarch**: it has the symbol in its own column, a signed quantity, the price, the fees, the amount, the trade date and the settlement date. It still has **no lot detail**, so the specific-lot confirmation queue is unchanged.
- **Sales:** rows whose Action starts with "YOU SOLD". Proceeds = the Amount column, which is already net of fees (checked on the sample: shares times price less the fee equals the amount). Trade date = Run Date; `settle_date` = Settlement Date. This answers the trade-versus-settlement question for that broker, so the confirm panel no longer needs to guess the trade date.
- **Combine fills:** one order can arrive as several rows on the same day at the same price (a whole-share row plus a fractional row, or separate fee lines). Group rows by account, symbol, run date and price into one sale; the queue shows the combined shares and proceeds with the source rows listed.
- **Other rows, read-only:** "YOU BOUGHT" and "REINVESTMENT" rows (excluding the money-market sweep, which stays at par like the `CASH` lots) feed the wash-sale scan and cross-check new lots; "DIVIDEND RECEIVED" rows cross-check the Monarch income category (section 12). Contributions, distributions and adjustments are counted and ignored.
- **Which account:** the account is **not inside the file** (only in the file name). The import asks which Planner account the file belongs to and remembers the file-name pattern per account; that choice also supplies the account's tax class (taxable, or retirement and HSA, where sales are trades with no tax).
- **Duplicates with Monarch:** match a broker sale to a Monarch Sell row on account, symbol, shares and proceeds within three days. The broker row wins (price, trade date, fees); the Monarch row is linked and marked "covered by broker file". Bare Monarch rows for that account are thereby resolved. Unmatched rows on either side stay in the queue.
- **Idempotent without an id:** the file has no transaction id. Key each row on a hash of account, run date, action, symbol, quantity and amount plus an occurrence counter, so two identical fills on one day are both kept and a re-import adds nothing.
- **Coverage:** the user picks the export date range. Record the range of each import and warn about gaps between imports and before the ledger start date.
- Parse rules (a few lines before the header are blank, a disclaimer and a "date downloaded" line follow the data, quantities are signed, numbers can be quoted) are in the Fidelity sample notes in section 14.

### 5.3 Manual and CSV entry
A form (account, symbol, date, shares, proceeds, fees, lot picker) and a CSV importer with the ledger columns, using the same preview/commit pattern as the holdings importer (`import_preview_v1` shape: received, will_write, warnings, duplicates). Manual entries are `source=manual`, and must pick lots (section 6).

### 5.4 1099-B import and difference report (Phase 5)
Parse the broker's 1099-B CSV (per broker column maps; one parser per broker, starting with the one the user has — **open question**). Match each 1099-B line to a ledger row by account/symbol/sale date/shares. For each match write the `official_*` columns and **replace** `basis`, `proceeds`, `gain`, `holding_period` with the official numbers (the ledger is the estimate, the 1099-B corrects it), keeping the pre-correction values in an audit table. The **difference report** lists every line where proceeds, basis, gain or holding period changed (with the delta), plus 1099-B lines with no ledger row (add as `source=1099b`, flagged "not previously entered"), and ledger rows for the year with no 1099-B line (flag: wrong lot, wrong account or a non-reported account). Wash-sale adjustments and disallowed losses reported in column 1g are imported and displayed (this is the first place official wash-sale data enters).

**Aggregated and corrected statements.** Some brokers (Vanguard in the sample) report most sales as one "Various" line per security and sale date rather than per lot. Matching is then many-to-one: the confirmed ledger rows for the account, security and date must sum to the line's quantity, proceeds and basis, and the official numbers are apportioned back to those rows in proportion to shares, with the aggregate kept as the audited figure. A statement marked CORRECTED supersedes an earlier import of the same account and year; the difference report shows what changed since that import.

### 5.5 Non-taxable accounts
Sales in IRA/Roth/HSA (via `tax_class`) are recorded with `gain` null and `holding_period` omitted: they update holdings and returns but create no tax event. They still appear in the ledger (filterable) because they are buys-for-wash-sale purposes and for returns.

## 6. Lot-selection UX (specific lots only)

The unmatched queue is a table, one sale per row; selecting a row opens a side panel:
1. **Header:** sale date, account, symbol, shares, proceeds/price (parsed or entered), source.
2. **Lot list** for that account and symbol: purchase date, shares remaining, basis per share, holding period as of the sale date, implied gain per lot at the sale price, wash-sale warning icon.
3. **Aids, never silent:** three read-only chips — "FIFO would pick…", "HIFO would pick…", "Highest-loss/lowest-gain would pick…" — each shows the lots and the resulting gain/tax. Clicking a chip **fills the share allocation inputs as a draft** the user can edit; nothing is saved until **Confirm**. No lot is pre-selected on open. If the sale exactly equals one lot's shares, that lot is highlighted as "only exact fit" but still unselected.
4. **Allocation inputs:** shares per lot; running total must equal shares sold; Confirm is disabled until it does. Over-allocation beyond a lot's remaining shares is blocked.
5. **Confirm** writes the ledger rows (`status=confirmed`), reduces the lots (or records the reduction if the holdings import already removed them), and marks the candidate `confirmed`. A toast with **Undo** (same pattern as the Monarch mapping page) sets the rows `voided`, restores the lots, and returns the candidate to `unmatched`. Undo is available later from the ledger too, until a 1099-B has been applied to that row (then it is locked and must be edited via the import).
6. **Keyboard/bulk:** next/previous sale, and "apply the same method to all selected" which opens a *review list* of drafts rather than saving, so ~300 historical rows are reviewable in one pass but still individually confirmed.

### 6.1 Confirm / undo / dismiss state machine (step 2.2, single sale; the bulk review list is a follow-up)

Candidate states: `unmatched` (queue) -> `confirmed` | `dismissed` | `not_a_sale`. Every move is one plan-file transaction (ledger rows, holdings, candidate state together), so a failure leaves nothing half-done.

| Action | From -> to | Effects | Refused when |
|---|---|---|---|
| Confirm | `unmatched` -> `confirmed` | Allocation `{lot_id: shares}` (lot_id = row index in holdings, no lot pre-selected) validated by `allocate_lots`; one `realized_sales` row per lot (`source` = candidate source, `monarch_id`, trade date; `settle_date` = Monarch date for Monarch rows); proceeds split pro-rata by shares (last lot takes the rounding remainder); basis = shares x lot price; holdings lots reduced, a lot at zero is removed; candidate gets `confirmed_sale_ids`. Non-taxable `tax_class`: `gain` null, lots still reduced. | already confirmed (idempotent: no second set of rows), allocation total != shares sold, a lot over-allocated, taxable lot with no purchase date, candidate not `unmatched` |
| Undo | `confirmed` -> `unmatched` | Rows voided; shares added back to the lot (a removed lot is re-inserted at its original position with its original text); `confirmed_sale_ids` cleared. | any of the candidate's rows has an `official_*` value (a 1099-B was applied: locked) |
| Dismiss | `unmatched` -> `dismissed` (reasons `before_ledger_start`, `other`) or `not_a_sale` | State only; no ledger or holdings change. | not `unmatched` |
| Restore | `dismissed`/`not_a_sale` -> `unmatched` | State only. | not dismissed |

The sold lot's identity (account, symbol, purchase date, price, lot type, note, original index and original share text) is stored as JSON in the row's `lot_key`, which is what makes confirm -> undo -> confirm restore identical holdings. Trade date for a Monarch row is pre-filled as the prior business day (weekends only; exchange holidays are not modelled) and the panel flags a Dec trade date with a Jan settle date. Aids (FIFO, HIFO, loss-first) are pure functions returning a draft allocation and its gain; nothing is saved by them. A bare candidate (no symbol or shares) needs both supplied at confirm. Scoped out and recorded: a `holdings_diff` candidate's lots were already removed by the import, so Confirm on it is refused with a pointer to manual entry (the candidate carries no lot detail to restore); the account's tax class is entered in the panel (defaulting to the account's last ledger row, else taxable) rather than read from the Planner account registry.

Cost to the user is the real risk: ~315 sells at design time. The historical backlog can be handled by year (default: current tax year first), and old years can be dismissed in bulk as "before ledger start" (a ledger start date setting), which is the explicit alternative to guessing.

## 7. Tax netting (Phase 3)

### 7.1 Rules, per tax year, taxable accounts only
1. Net short-term gains/losses; net long-term gains/losses.
2. Apply the **prior-year carryforward** (entered in `realized_adjustments`, separated short and long) to the matching bucket first.
3. **Cross-net:** a net loss in one bucket offsets a net gain in the other; short-term losses offset long-term gains first at the preserved character rules (net short-term gain taxed as ordinary, net long-term gain at LTCG rates).
4. **Overall net loss:** deductible up to **$3,000** (MFS $1,500) against ordinary income; the rest carries forward, keeping character. (Constants should come from the existing tax tables in the repo, not be re-typed; verify where the engine stores the $3,000 offset — `tlh_ordinary_credit` in the investment-tax cascade — and reuse it.)
5. Output per year: `net_st`, `net_lt`, `ordinary_offset`, `carryforward_st`, `carryforward_lt`, `gain_to_tax_ordinary`, `gain_to_tax_ltcg`.
6. **NIIT hook:** net gain after the offsets is net investment income; feed it to the existing NIIT computation (`niit_tax(nii, magi)`), not a new formula. **State hook:** reuse the state capital-gain treatment already in `after_tax` (`terminal_deferred_state_cap_gain_tax` path); the ledger supplies a realized-gain amount where the engine currently supplies an estimate.
7. Pure function in a new module (suggested `src/realized_tax.py`) with no I/O, unit-tested with worked examples (section 15).

### 7.2 Current-year tax estimate (Trends and Planner)
Add a separate line **"Tax on gains realized this year"** = tax computed by 7.1 on year-to-date ledger gains (federal ordinary/LTCG + NIIT + state), using the same `after_tax` rate functions as the existing estimate. The existing **"Estimated tax"** is the tax *on unrealized gains if liquidated*. Realized gains are by definition no longer unrealized (the lot is gone), so the two never overlap *provided the sold lot is removed from holdings*, which it is. Trends must still guard against a stale holdings file where the lot has not yet been removed; section 9 handles this by treating a confirmed ledger sale whose lot is still present as a **warning**, not as both.

### 7.3 Seeding the projection (Phase 3, heavy)
- **Carryforward into year 1:** `create_initial_year_state(config)` initializes `cap_loss_carryforward = 0.0`. Read the entered carryforward (if any) from config and set it there. A single scalar exists today; the ledger distinguishes short and long term. v1: collapse to the single magnitude the engine understands (loses character nuance; documented); v2: split it only if the engine gains two buckets.
- **Actual realized gains for the current year:** feed the year-1 net realized gain as an additional line alongside `sale_gain_in_agi` (~`deterministic_engine.py` 1275) so it flows to AGI, NIIT MAGI and IRMAA MAGI (as `CAPITAL_GAINS_IN_AGI.md` already specifies for sale gains), and reduce the year-1 simulated taxable draw's gain accordingly only by what the plan already treats as spent. A realized sale also reduced the taxable balance (cash came in, lots left), which is already reflected in the holdings snapshot, so **only the tax effect** is added, not the proceeds.
- **Do not double count:** the engine's own year-1 simulated withdrawals still generate `ltcg_gain`; ledger gains are *actual, already-happened* gains in the same calendar year. Both go through the same netting stage so they net against each other (a harvested loss offsets a simulated gain).
- **Empty ledger = unchanged plan:** with no confirmed taxable sales in the plan year and no carryforward entered, the new inputs are exactly `0.0` / absent; the code path adds `0.0`, and floating-point addition of zero is exact. Guard: skip the whole stage when the ledger is empty, and assert in a test that every golden-master fixture produces byte-identical output with and without the feature flag. Golden masters (`.claude/CLAUDE.md`): run `python tools/regen_golden_master.py measure` first and expect **zero delta**; any delta means the empty-ledger guard is broken — do **not** regenerate.
- **Ship order:** 7.1 + 7.2 first (year-to-date netting and the Trends tax line, no projection change); 7.3 seeding as a separate step after, behind a plan setting "Use realized sales in the plan", default on only when the ledger is non-empty.

## 8. Wash-sale flags (Phase 3, flag only)

A loss sale (confirmed ledger row with `gain < 0`, taxable account) is flagged **possible wash** when, within 30 days before or after the sale date (61-day window), the household bought the same or a substantially identical security in **any** account: the owner's taxable and IRA/Roth/HSA accounts, and the spouse's. Data sources: holdings lots with `purchase_date` in the window (includes reinvested dividends, `lot_type = reinvest…`), and Monarch Buy rows in the window.
- "Substantially identical" = same symbol, or same group in the security master (reuse the replacement-universe groupings that `tlh.py` uses to *avoid* wash sales; verify the exact structure in `load_security_master` when building). Where unsure the flag says "possible" with the reason.
- The partial-lot case: shares repurchased limit the disallowed amount; v1 flags and shows the repurchased share count but does not compute the disallowed loss.
- Surfaces: a column on the ledger and the queue panel ("Loss on X; bought X 12 days later in Spouse IRA"), and a warning on the tax line ("includes $… of losses flagged possible wash sales — this may overstate the deduction"; use sample number style in docs only).
- IRA repurchase: flagged specially, because the loss is disallowed with no basis add-back (the worst case); the message says so.
- **Later phase (not v1):** automatic disallowance and basis adjustment of the replacement lot, holding-period tacking, tracking of the disallowed-loss carry within the ledger, and importing 1099-B column 1g adjustments as the authority (Phase 5 imports the numbers; applying them to replacement lots is the later work).

## 9. Trends reflection (Phase 4)

### 9.1 Sold lots in the returns math
In `_positions`, add **sold-lot rows** alongside the current lots, built from confirmed ledger sales (all account classes):
- A lot **held at the baseline** and sold since: `start` = shares × baseline price (as for a held lot); `current` = 0; it carries `proceeds` as `money_out` (a withdrawal) on its sale date, time-weighted as `proceeds × (days remaining after sale) / period` subtracted from `weighted`, which is the Modified Dietz treatment of an outflow.
- A lot **bought after the baseline** and sold since: its `new_money` (shares × purchase price, on its purchase date, time-weighted) and `money_out` (proceeds on sale date, time-weighted).
- A lot bought before the scope start but with the scope start later than the sale (sold before the window): not in the window at all (sale date < start day): excluded.
- Gain for a sold lot over the window = `current (0) + proceeds − start − new_money`; consistent with current lots' `current − start − new_money`.
- Proceeds stay in brokerage cash (confirmed by the user, section 14): the sale is a swap inside the account, so total-portfolio return is unaffected. Per-group views count proceeds as money out of the sold lot's group and money into Cash, time-weighted. A later transfer to checking is handled by the existing `_checking_net_flows`, which must not also count the sale. Check with a worked example in Phase 4; this is the highest-risk correctness point.
- **Result:** the caveat note in `frontend/live_snapshot.js` (~299, "Gains on positions sold since … are not included") is replaced by "Includes N positions sold since <start>" and, when unconfirmed sales exist, "N sales not yet confirmed are not included" with a link to the queue. The Time scope (`start_day_for`) filters sales by date: sales before the scope start are excluded; the baseline price for a sold symbol comes from the same `baseline_prices` call (it must include sold symbols — extend the symbol set).
- `Group By`: sold lots roll into their asset class / sub-class / account / tax group rows like current lots, with a "(sold)" ticker row drill-down so a user sees where gain came from. `live_groups.js` totals then include them. No quotes are needed for sold symbols today except the baseline close (a `closes_on`-style fetch, cached).

### 9.2 Realized gains and losses view
A third segment ("Realized") in the Live Snapshot area, **scope-aware** (uses the shared Time scope for the date range; also a Tax-year shortcut, because tax is by calendar year, not by rolling window):
- Summary: net short-term, net long-term, total, proceeds, basis, wash-flagged amount.
- Table grouped by symbol (default) or account, with expandable lots: sale date, purchase date, shares, proceeds, basis, gain, term, source, wash flag, 1099-B status.
- Filters: taxable vs all accounts, confirmed vs include-unconfirmed, wash only.
- Header chips: "N sales waiting for lots" → opens the queue.
- The `$ | %` toggle: dollars mode shows all of the above; percent mode shows only returns and ratios (see 10).

### 9.3 Daily log fields
`trends_log.py` writes the 5 pm snapshot. Add year-to-date realized figures: `realized_ytd.{st_gain, lt_gain, net, tax_estimate, wash_flagged, unconfirmed_count, unconfirmed_amount}`. Keys must be named so the percent view treats them as money (do **not** use `_pct`/`_rate` suffixes for dollar fields; counts use the existing `count` key). Old entries without the field must read as "no data", not zero.

### 9.4 Tax line that does not double count
In `compute`/`_planner_tax`, keep `ltcg_tax` (unrealized, liquidating today) and add `realized_tax` (7.2). Display as two lines under "Estimated tax": "On unrealized gains" and "On gains realized this year", plus the sum. The unrealized computation iterates *current* lots only, so a sold lot is excluded by construction. Add a test: sell a lot (ledger + holdings removal) and assert the sum of the two lines changes only by the true difference (the tax on the gain between sale price and current price for the *remaining* lots is unchanged).

## 10. Percent view and privacy

Rules from `percent_view.py`: money keys are scaled by one constant unless allowlisted; `shares/quantity/purchase_price/price` are removed; `find_money_leaks` flags any number > 50 outside the allowlist and any "$"-text.
For every new field:
- Dollar fields (`proceeds`, `basis`, `gain`, `realized_tax`, `st_gain`, `lt_gain`, `net`, `unconfirmed_amount`): leave unlisted so they are **scaled** — but prefer to **withhold** per-lot detail in percent mode (lot rows reveal share counts × dates ≈ scale). Recommendation: percent mode receives only group-level scaled totals and returns (%); no lot rows, no sale dates tied to amounts, no proceeds per sale. Implement by stripping the `sales`/`lots` arrays in `strip_detail` for the realized route, as spending detail is stripped.
- Counts (`unconfirmed_count`, `wash_count`): use keys on the allowlist (`count`); never name a count with a money-like key.
- Ratios (`return_pct`, `share_of_gain`) pass untouched.
- Text: the caveat/hint strings must not interpolate dollars ("$…"); the leak guard catches this.
- Sold-lot symbol/ticker names are public information but combined with percentages are fine; share counts are not (stripped).
- New test: build a realized-view payload from a synthetic ledger, run through the percent transform, and assert `find_money_leaks(result) == []`; plus a "forgot to list a key" test that adds an unknown numeric key and expects it to be scaled, not passed through (fail-closed).

## 11. Reconciliation hints

`_hints` gains two kinds, ahead of the generic direction hint:
- `unmatched_sale`: when the gap between holdings and Monarch for an account is within the 5% (`RECONCILE_MATCH_PCT`) of an **unmatched sale or confirmed-ledger sale** amount dated after Monarch's balance date → "Sale of ~N SYMBOL on <date> is waiting to be confirmed" (a concrete replacement for "a sale or transfer out may not be entered yet"). Percent mode shows it without the amount.
- `sale_not_in_holdings`: a confirmed ledger sale whose lot is still present in holdings (stale holdings file) → "Holdings still list the lot you sold."
`src/reconcile.py` mapping logic is unchanged. The Planner's reconcile page can show the same queue count.

## 12. Double counting and Monarch

- **Sell rows** stay excluded from spending (`EXCLUDED_SPENDING_CATEGORIES`, `TRANSFER_RE`); they become *ledger inputs* instead. No change to `ytd_tracking` classification is needed; add a read-only extractor (`sell_rows(ytd_rows)`).
- **"Dividends & Capital Gains"** is Monarch's income category and includes dividends and **capital-gain distributions from funds**. Those are distributions the fund paid you, not sales you made, so they are never ledger rows. They remain investment income. The ledger records only *your* sale of shares. To avoid the same dollars appearing twice in a "total investment return" view, the Realized view labels itself "Gains on sales you made" and the Trends return math counts fund distributions only through price/NAV and reinvested lots as today. A sale transaction row (Sell) is never also summed as income because it is not in the income category set.
- **Cash from a sale** shows up in the brokerage cash balance and, if transferred out, in a Transfer row; neither is re-classified.
- **Buy rows** are used read-only for wash-sale windows and as a cross-check against new lots, never to create lots (holdings stay the record of positions).

## 13. Risks and edge cases

| Case | Handling |
|---|---|
| Partial lot sold | Ledger row for the shares sold; holdings lot reduced with proportional basis; `lot_key` uses the original purchase date and per-share basis. |
| Stock split / reverse split / spin-off | Holdings diff sees changed shares + changed price with the same total basis: flagged "possible corporate action", never a sale; user can mark "adjust lot" which rewrites shares/price without a ledger row. Ledger rows record shares *as of the sale*, with a split factor field in a later phase if needed. |
| Reinvested dividends changing basis | Reinvest lots are separate lots (`lot_type=reinvest…`) with their own purchase date, so a sale can choose them specifically; holding period is per lot. They are wash-sale buys too (flagged in 8). |
| Mutual-fund average cost (out of scope: the user has none) | Specific-lot identification contradicts average-cost accounts. v1: allow a lot to be flagged `avg_cost` in a later phase; in v1 the user picks lots and the 1099-B import (which reports average-cost basis) will show differences — the report is the safety net. |
| Spouse and IRA wash sales | Window search spans all household accounts, includes pre-tax/Roth/HSA buys; flagged with the special IRA message. |
| Bare sells (no ticker) | Land in the queue as "needs detail"; user supplies symbol/shares or dismisses (e.g. a fund exchange). Never guessed. |
| Same-day buy and sell | Sale and buy on one date: lot purchased that day can be sold that day (holding period 0, short term); a buy the same day triggers a wash flag. Order within the day is unknown, so both are shown. |
| Trade date vs settlement date | Gain and holding period use trade date (that's the tax rule for securities); Monarch dates may be settlement or posting dates, so matching tolerates ±3 days and the ledger records both when known. Year-end sales posted in January must be assigned to the tax year of the trade date; the confirm panel shows the date and lets the user correct it. |
| Fees/commissions | Net out of proceeds; separate column. |
| Short-term/long-term boundary | Long term only if the sale is after the first anniversary of purchase; test the exact boundary (sample: purchase 2025-03-05, sale 2026-03-05 is short, 2026-03-06 is long). |
| Missing purchase date on a lot | Existing code treats it as held before baseline; the ledger marks holding period `unknown` and blocks confirm until supplied. |
| Backlog of ~300 sales | Ledger start date setting; year filter; per-year bulk dismissal. |
| Holdings replaced from a broker file that has *different lot ids* | Diff keys (account, symbol, date, shares, price) tolerate rounding via an epsilon on price/shares; mismatches fall to the queue. |
| Broker reports a "Various" summary line | Many-to-one match to the confirmed ledger rows for that account, security and date; official numbers apportioned by shares; unmatched remainder goes to the difference report, never forced. |
| Corrected 1099-B after an earlier import | Corrected statement supersedes the earlier import for that account and year; show the delta against the earlier import and ask for confirmation before replacing. |
| Bond or CD redemption, security with no ticker | Ledger row with `kind=redemption` and `symbol` null, keyed by CUSIP and description; never matched to a holdings symbol by guess. |
| Return of capital lowers basis | Holdings basis can lag the official covered basis; the difference report labels the likely cause; no automatic basis edit in v1. |
| Broker activity file has no account number or transaction id | Ask which Planner account the file is for (remember the file-name pattern); key rows on a hash plus an occurrence counter so identical same-day fills are kept and re-imports add nothing. |
| Split fills (whole shares plus a fraction) | Combine rows with the same account, symbol, run date and price into one sale before queuing. |
| Dividend reinvestment of a fund sold at a loss within 30 days | Reinvestment rows count as purchases in the wash-sale scan; the money-market sweep at par does not. |
| Lots held in the same account under two names (alias) | Use the account alias map already in Trends (`saved_setup_aliases`) for matching Monarch accounts to holdings accounts. |
| Price precision | Store raw price/proceeds as parsed; round only for display. |

## 14. Answers received and remaining open questions

### Answered by the user (2026-10-28)
1. **Brokers:** Fidelity, E*Trade and Vanguard issue the 1099-Bs. Some may arrive as PDF, so Phase 5 gets a PDF-to-CSV step (extract tables from the PDF, then show the parsed lines in the same preview for the user to check before applying). One parser per broker; build Fidelity, E*Trade and Vanguard in that order of whichever sample file arrives first. Samples must have values obfuscated before they go in the repo.
2. **Backlog:** ledger start = the current tax year; older Sell rows are dismissed in bulk as "before ledger start" (the setting stays editable).
3. **Carryforward:** the user has last year's short- and long-term figures; the Phase 3a carryforward form takes both.
4. **Proceeds stay in brokerage cash.** So a sale is a swap inside the account: sold lot out, cash in. The returns math in 9.1 therefore must **not** treat proceeds as money leaving the household. Revised rule: for the account group the sale is a rebalancing, value moves from the lot to the cash position, and the gain is recognized in the lot. Only a later transfer out (existing `_checking_net_flows`) is a flow. The sold lot's `current` becomes 0 and its proceeds are already present as cash in holdings. Total-portfolio return is unchanged by the sale itself; per-group (asset class, symbol) returns count the proceeds as money taken out of that group, time-weighted, and as money in for the Cash group at the same weight, so group totals still add up. Test both views.
5. **State tax applies to realized gains, tracked by state in the Retirement Planner.** The state comes from the Planner's household/state setting, and state tax on realized gains uses the Planner's per-state treatment (reuse the `after_tax` state capital-gain path). Because a household can move states, the ledger stores the sale's tax year and the realized-tax calculation takes the state in effect for that year from the Planner (a per-year state lookup, verified in Phase 3a), not a single global rate. The `realized_adjustments` state-rate override is kept as an optional override only.
6. **No average-cost funds.** The average-cost items in section 13 are dropped from v1 scope; specific-lot logic applies everywhere.
7. **Unconfirmed sales appear both ways:** a warning chip with count (and amount in dollar mode), and an optional **"include unconfirmed (estimate)"** toggle in the returns and Realized views. Estimate mode values an unconfirmed Monarch sale using its parsed or Monarch amount with basis taken from the sale's best-guess lots **for display only**; it is clearly labelled estimate, never written to the ledger, never feeds tax or the projection, and never logged to the daily log. This is the only place lot suggestions are used without the user confirming, and it stays visual. Default is off.
8. **Settlement date:** Monarch posts sells on settlement date. The ledger needs the **trade date** for tax, so for Monarch-sourced rows the confirm panel pre-fills trade date = the prior business day (T+1 settlement for stocks and ETFs since May 2024; mutual funds often settle same day), shown as a suggestion the user can correct, and stored with `settle_date` = the Monarch date. Matching to holdings events tolerates the settle/trade offset. Year-end rule: a sale settling in January with a December trade date belongs to the December tax year; the panel highlights this case. The 1099-B import then overwrites with the official trade date.


### E*Trade sample reviewed (2025 Consolidated Tax Statement, 12 pages)
The user supplied the E*Trade from Morgan Stanley 2025 consolidated statement (PDF, held outside the repo). Findings that shape the Phase 5 parser (structure only; no figures recorded here):
- **The PDF has a text layer**, so `pypdf` extracts it; no OCR is needed. `pypdf` is already installed in the dev environment; confirm it is (or add it as) a declared dependency before building, and keep the parser optional-import so the app runs without it.
- **Sections:** 1099-DIV (dividends), 1099-INT, a 1099-B **totals summary** (short term, long term, unknown term, split by Box A/B/D/E basis-reported or not, with proceeds, basis, market discount, wash-sale disallowed, realized gain) and the detailed **1099-B lines**, grouped as Short/Long Term x Covered/Noncovered. The summary page doubles as a **control total**: the parser must reproduce it from the detail lines, or the preview refuses to apply and shows the gap.
- **Detail line layout:** a header line `CUSIP: <cusip> Symbol: <symbol><description>` (symbol and description run together with no separator, so split using the security master's symbol list), then one line per lot sold: date acquired, date sold (MM/DD/YY), proceeds, cost basis, accrued market discount, wash-sale loss disallowed, gain/(loss) with parentheses for losses, federal tax withheld, quantity. This is lot-level data, so it maps one-to-one onto ledger rows and is also the easiest source of **trade date, acquisition date and holding period**.
- **Section headings give the term and basis-reported box**, so term (short/long) and covered/noncovered come from the heading, not from the lines.
- **Page breaks** repeat the column headers mid-section; the parser must skip repeated headers and the "Total" lines.
- **Account scope:** one statement covers one account (here a taxable trust account); Fidelity and Vanguard statements will be separate files with different layouts, so one parser per broker with a shared normalized output (`account, symbol, date_acquired, date_sold, proceeds, basis, wash_disallowed, gain, term, covered, quantity`).
- **Cautions:** the file carries the owner's name, address and partial account number. Only an obfuscated copy (names, addresses, account numbers, amounts perturbed) may be committed as a test fixture; tests otherwise generate synthetic text in the same shape. Never commit the original.
- **Proceeds note:** the statement defines proceeds as gross proceeds less commissions, matching the ledger's net-of-fees proceeds; no separate fee column exists on the form.
- **Wash-sale and noncovered securities:** noncovered lots may have basis not reported to the IRS; the parser records `covered=false`, and the difference report shows those basis values as "broker did not report basis; ledger value kept".

### Vanguard sample reviewed (2025 tax information statement, 16 pages; a CORRECTED statement)
The user supplied the Vanguard Brokerage 2025 statement (PDF, held outside the repo; text was extracted in a scratch folder, nothing copied into the repo). Findings that shape the Phase 5 parser (structure only; no figures, names or account numbers recorded here):
- **Text layer:** pages 3 to 16 extract with `pypdf`; pages 1 and 2 are image-only (cover material; contents not checked and not needed for sales).
- **It is a corrected statement.** Every page header carries the word CORRECTED and a statement date. The parser must read both. A corrected statement **supersedes** an earlier import of the same account and year: the difference report lists changes against the earlier import as well as against the ledger, and applying it asks the user to confirm the replacement.
- **Sections:** a summary page (term by form type: Short A/B/C, Long D/E/F, Undetermined; proceeds, cost basis, market discount, wash-sale loss disallowed, net gain or loss), then 1099-DIV, 1099-INT, the 1099-B detail, dividend and distribution detail, foreign-source percentages and boilerplate. The summary rows are the **control totals**, as with E*Trade. This sample has covered sections only (Box A short term, Box D long term); noncovered and undetermined sections are referenced but absent, so their layout is **unverified**.
- **Security header:** `DESCRIPTION / CUSIP: <cusip> / Symbol: <symbol>`, with explicit separators (unlike E*Trade, where symbol and description run together). The description is a fixed-width abbreviation, so map by CUSIP or symbol, never by description. **Symbol can be blank** (bonds, CDs): such rows are keyed by CUSIP plus description with `symbol` null, and will not match a holdings symbol.
- **Most lines are not lot-level.** There are two line shapes: (a) a **"Various" line**: date sold, quantity, proceeds, date acquired = "Various", basis, gain, and "Total of N transactions", meaning N sales rolled into one line; (b) individual lines with an explicit acquisition date, used for lots with adjustments (wash-sale marker, or an "Original basis" line when basis was adjusted). So the 1099-B cannot give lot-by-lot data for most Vanguard sales. **Matching is many-to-one:** the confirmed ledger rows for that account, security and sale date must sum to the line's quantity, proceeds and basis, and the term comes from the section heading because the acquisition date is "Various". The difference report compares at (account, security, sale date) level for "Various" lines and at lot level for the individual ones.
- **Column notation:** proceeds carry a (G)ross or (N)et marker; accrued market discount and wash-sale disallowed share one column and are told apart by a trailing letter D or W; X and Z mark losses not allowed; an "Additional information" column reads "Sale" or "Redemption" plus a number; a few lines end in a single-letter code whose meaning is in the form's legend and is **not decoded here**. Losses are shown with a leading minus (E*Trade uses parentheses), dates are MM/DD/YY, quantities have three decimals.
- **Layout traps:** a long multi-line column header repeats at every section and page break, the form header says "(continued)", and a security block can continue on the next page ("cont'd"). Skip "Security total:" and "Totals:" lines when reading rows, and use them as checks.
- **Redemptions:** bonds and CDs at maturity appear as "Redemption", not "Sale". The ledger records them as dispositions (`kind=redemption`). Whether the holdings file tracks such securities is **unverified**.
- **Distributions:** the dividend detail lists, by security, long-term capital gain distributions and **nondividend distributions** (return of capital). Capital gain distributions are income, never sales (the rule in section 12). Return of capital lowers basis, so basis kept in the holdings lots can lag the covered basis the 1099-B reports; the difference report labels a basis difference of that size "possible return of capital" (display only in v1).
- **Account scope:** the sample is one brokerage account; confirm for statements that cover several. The normalized parser output gains `cusip`, `aggregated` (true for "Various" lines), `transaction_count`, `corrected` and `statement_date`.
- **Cautions:** the file carries the owner's name, address and partial identifiers. The same fixture rules apply as for E*Trade: only an obfuscated copy may be committed, tests otherwise generate synthetic text in the same shape, and the original is never committed.

### Fidelity activity export reviewed (account history CSV, year to date)
The user supplied a Fidelity "History for Account" CSV (held outside the repo; the account number is only in its file name and is not recorded here). This is **not a 1099-B**: it is the all-transactions export the user can download during the year. Findings that shape the Phase 2 parser (structure only; no figures):
- **Layout:** two blank lines, then the header `Run Date, Action, Symbol, Description, Type, Price ($), Quantity, Commission ($), Fees ($), Accrued Interest ($), Amount ($), Cash Balance ($), Settlement Date`; data rows; a blank line; a multi-line legal disclaimer; a blank line; "Date downloaded ...". The parser finds the header by name, stops at the first blank line after data, and ignores the footer.
- **Dates and numbers:** MM/DD/YYYY. Negative and empty values are quoted; empty cells are empty strings. Sold quantities are negative; the Amount of a sale is positive; the Amount of a purchase is negative.
- **Symbol is its own column**, so no splitting is needed; the Action text embeds a truncated name ending in "..." and the symbol in parentheses, and the Description column holds the full name. Do not parse the Action for names.
- **Action vocabulary seen:** YOU SOLD, YOU BOUGHT, REINVESTMENT, DIVIDEND RECEIVED, plus account-specific text for contributions, distributions and adjustments (symbol blank, description "No Description"). Only the first three matter here.
- **Dates:** Run Date is the trade date. **Settlement Date is filled only on trades** (YOU SOLD, YOU BOUGHT) and was one business day later in the sample; it is blank on dividends and reinvestments.
- **Fees:** sells carry a small regulatory fee in the Fees column and the Amount is net of it; fractional-share sells show no fee. Commission was blank.
- **Split fills:** the sample shows one order as two rows on one day at one price (whole shares, then a fraction). Combine them (section 5.2b).
- **Reinvestments are purchases.** Dividend reinvestments appear as purchase rows with a price and a positive quantity. The sample itself has the wash-sale pattern: a sale of a fund followed within 30 days by a reinvestment of the same fund. Whether that sale was at a loss is unknown, but the wash-sale scan must include these rows. Money-market sweep reinvestments at par are ignored.
- **Account type:** the sample account's activity includes HSA-style contribution and distribution actions, which under the design makes its sales trades with no tax. The tax class must come from the Planner's account setup, never be inferred from the file.
- **Not in the file:** lot detail, cost basis, realized gain or loss, and the account number inside the data. It is not suitable for tax reporting (its own disclaimer says so), so it feeds the running ledger only; the 1099-B still corrects it.

### Still open
- **Fidelity sample not available until about February 2027** (the user's word; the 2026 1099-Bs are issued then). E*Trade and Vanguard samples are in hand. The Fidelity parser therefore cannot be built from a real file before then. Until it arrives, Fidelity sales go through the Monarch queue with manual lot confirmation, plus a generic CSV import with user-mapped columns for any realized gain/loss export. **Answered:** during the year Fidelity offers an all-transactions CSV (sample reviewed above) with the word "Sold" in the action text and no lot detail, not a realized gain/loss export. It is parsed in Phase 2 (section 5.2b), so Fidelity sales can be captured this year; only the 1099-B parser (Phase 5b) waits for February 2027. PDF extraction stays best-effort with a check-before-apply preview and control totals.
- **Timing:** the 1099-B import (Phase 5) corrects the 2026 ledger and is not needed before about February 2027, so Phases 1 to 4 are what matter during 2026. Phase 5 is split: 5a E*Trade and Vanguard (samples in hand), 5b Fidelity (when its sample arrives).
- Whether the Planner already stores state per year (for moves) or one household state; verify in Phase 3a.

Not verified while writing: the exact `monarch` YTD storage location in the plan file (CSV file vs table), the structure of `load_security_master` for substantially-identical groups, how the Trends reporter reads the plan file in production, whether `revision_rows` should include the ledger, and the numeric constants for the $3,000 offset in the engine. Each is a first task of the relevant phase.

## 15. Testing strategy

- **Pure functions first:** holding-period boundary, netting (7.1) with worked cases: ST gain + LT loss, both losses > $3,000 limit, carryforward in/out, cross-net, MFS limit; wash-window detection with same-day, spouse, IRA, partial repurchase; Monarch Sell regex on the real shapes (parseable, bare, odd tickers); lot-allocation validation.
- **Golden masters:** `python tools/regen_golden_master.py measure` before and after Phase 3; require zero delta with empty ledger. A dedicated fixture with a non-empty ledger gets its own new pin (added with `regen --reason`, never by regenerating existing pins). Verify one representative delta by hand (a single sale with a known tax) before pinning.
- **Percent-view leak guard:** a test that passes the full realized payload through the percent transform and asserts `find_money_leaks` is empty and that `shares`/`price`/per-lot rows are absent; plus the fail-closed unknown-key test (section 10).
- **Idempotency:** re-import the same YTD file and the same holdings file twice; the queue and ledger are unchanged.
- **Undo:** confirm, undo, confirm again restores identical holdings.
- **Double count:** the unrealized + realized tax test in 9.4; the Sell-row/spending test (a Sell row must not alter spending totals).
- **Returns:** a Modified Dietz test with a sold lot over (a) baseline-held, (b) bought-and-sold in window, (c) sold before window; assert the combined return equals the manual calculation, and the old caveat text is gone.
- **Repo-required tests:**
  - `tests/test_freeze_frontend_source_grep.py` forbids new tests that read frontend source text and assert substrings. New UI coverage goes through Playwright (`tests/e2e/`), the Node vm sandbox (`tests/frontend/load_dashboard.mjs`) or API/server-rendered output. Do not copy the existing "panel JS read as text" pattern.
  - `tests/test_frontend_size_ratchet.py` caps `frontend/js` growth (the ceiling only ratchets down). Put new UI in **new modules** under `financial_trends_reporter/frontend/` (outside the ratcheted dir) or a new small file under `frontend/js`; check the ratchet's scope when starting (it names `dashboard.js`); do not append to the big files (`dashboard.js` 7,287 lines etc. per `.claude/CLAUDE.md`).
  - Schema: tests that pin `PLAN_SCHEMA_VERSION`; `python tools/build_demo_seed.py --check`.
  - Architecture diagram: any `src/` or `frontend/` file add/rename → `python tools/generate_system_diagram.py` and commit the regenerated `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` (CI freshness test). This design doc itself needs no regeneration.
  - Python commands per `.claude/CLAUDE.md`: `pytest -m "not slow"` for the fast loop; always `-v` with output to a log file (per the user's global rule); `npm test` for frontend.

## 16. Phased implementation plan

Estimates are **relative**, not token counts. Rule of thumb for the Pro 5-hour window: *light* ≈ under about a tenth of a session; *moderate* ≈ a quarter to a third; *heavy* ≈ most of a session or more. **Check `/usage` as each phase executes and compare to these estimates**, then rescope the next step if a phase ran heavier.

Large files: follow the "Reading Large Files" table in `.claude/CLAUDE.md`. In particular `financial_trends_reporter/live_snapshot.py` (~1,000+ lines) and `src/ytd_tracking.py` are read by `Grep` first, then `Read` with `offset`/`limit`; never read `dashboard.js`, `dashboard_decomp_row_model.js`, `workbook_builder.py` linearly (none should be needed).

### Phase 1 — Ledger data model, schema bump, manual entry, holdings-import diff
Ships alone: a "Sales ledger" page in the Planner with manual entry and the import-time "N lots look sold" panel; nothing else changes.

| Step | Work | Model / effort | Usage |
|---|---|---|---|
| 1.1 | `realized_sales`, `sale_candidates`, `realized_adjustments` tables; `SCHEMA_V17_DDL`; repository class (pattern: `monarch_repo.py`); rebuild demo seed; fix pinned-version tests. Resolve the open storage questions (revision snapshots, Trends read path). | Sonnet, medium | Moderate. Context driven by `plan_store.py`/`datasets.py` reads (grep-and-slice) and a few test-fix loops over schema-version tests. |
| 1.2 | Pure helpers: `holding_period(purchase, sale)`, `ledger row` validation, lot allocation (no I/O). TDD. | Sonnet, medium | Light. Small new files, fast tests. |
| 1.3 | Holdings diff in `preview_holdings_import` (disappeared/reduced lots, transfer and split hints), returned in the preview; `holdings_service` writes `sale_candidates` on commit. | Sonnet, high (touches an existing, tested contract) | Moderate. `import_preview.py` is mid-sized; risk is breaking `import_preview_v1` consumers (grep for callers first). |
| 1.4 | Manual entry form + CSV import + ledger list; UI in a **new module** (ratchet). | Sonnet, medium | Moderate. UI plumbing and an e2e test; keep scope to one table and one form. |
Files likely touched: `src/stores/plan_store.py`, new `src/stores/sales_repo.py`, `src/import_preview.py`, `src/server_services/holdings_service.py`, a new service + route, `tools/build_demo_seed.py` output, `src/reference/demo_seed.rpx`, new frontend module, tests. Regenerate the architecture diagram.
Verify: fast pytest loop; import a holdings file with one lot removed and see one candidate; golden master `measure` shows zero delta (nothing reads the ledger yet).
**Flag:** step 1.1 is the first schema bump to a shared store — scope down by shipping the three tables empty with no consumers; do not touch the revisions mechanism unless the open question demands it.

### Phase 2 — Monarch Sell matching, the unmatched queue, lot confirmation and undo
Ships alone: the queue and confirm/undo flow; ledger rows now exist but nothing consumes them.

| Step | Work | Model / effort | Usage |
|---|---|---|---|
| 2.1 | Sell-row extractor + regex parser; idempotent queue loader keyed on `Monarch Id`; match suggestions against holdings events. Count parseable vs bare in a test on a synthetic fixture. | Sonnet, medium | Light-moderate. Grep `ytd_tracking.py` for the existing row helpers; avoid reading it whole. |
| 2.1b | Broker activity CSV parser (Fidelity first): find the header past leading blank lines, stop before the footer, combine same-day fills, ask which Planner account the file is for, key rows without an id, dedupe against Monarch rows (broker row wins), record the export date range. Fixtures are synthetic or obfuscated, never the original. | Sonnet, medium | Light-moderate. The format is simple; the cost is matching and idempotency tests. |
| 2.2 | Lot-selection panel: candidate lots, FIFO/HIFO/loss-first aids (read-only chips filling a draft), allocation validation, Confirm, Undo, dismiss, bulk review list. | Opus for the design of the state machine, Sonnet to build; high | **Heavy-ish.** UI + service + undo semantics + e2e; test-fix loops. Scope down: ship single-sale confirm/undo first, bulk review as a follow-up. |
| 2.3 | Reconciliation hint `unmatched_sale` (Planner reconcile page count) — Trends side waits for Phase 4. | Sonnet, low | Light. |
Files: new `src/sales_matching.py`, `src/ytd_tracking.py` (extractor only; grep to the relevant region), sales service/routes, new frontend module, tests.
Verify: run against a copy of the real YTD file in a scratch dir (never committed); confirm and undo restores holdings; re-import is idempotent.

### Phase 3 — Tax netting, carryforward, wash-sale flags, projection seeding (heaviest)
Ship in two releases: **3a** year-to-date netting + wash flags + Planner "realized this year" panel (no projection change); **3b** seeding the projection.

| Step | Work | Model / effort | Usage |
|---|---|---|---|
| 3a.1 | `src/realized_tax.py`: netting, $3,000 limit, carryforward, NIIT/state hooks calling existing `after_tax`/NIIT code. Worked-example tests. | Opus, high | Moderate. Small file, but correctness reasoning and a few reference reads (`after_tax.py` slices, `CAPITAL_GAINS_IN_AGI.md`). |
| 3a.2 | Wash-sale detector (window search across holdings lots + Monarch Buy rows + broker activity CSV buys and reinvestments, security-master groups), flags on ledger rows. | Sonnet, high | Moderate. Reuse groupings from `tlh.py`; read `load_security_master` only. |
| 3a.3 | Planner panel: tax-year summary, wash warnings, carryforward entry form. | Sonnet, medium | Moderate. |
| 3b.1 | Seed `cap_loss_carryforward` and year-1 realized gain into the engine behind the empty-ledger guard. | Opus, high | **Heavy.** `deterministic_engine.py` is very large; Grep `cap_loss_carryforward`, `sale_gain_in_agi`, `create_initial_year_state` and read only those slices (offset/limit). Golden-master loop is the cost driver: run `measure` once, not repeatedly. |
| 3b.2 | Non-empty-ledger fixture, new pin via `regen --reason`, hand-check one delta. | Opus, high | Moderate-heavy; **do not enter a regenerate-run-regenerate loop.** |
Files: new `src/realized_tax.py`, `src/wash_sales.py`, `src/projection_stages/year_state.py`, `deterministic_engine.py` (small hunk), config assembly in `src/parsing/client_sections.py` or the plan config builder, tests, golden-master changelog.
Verify: zero-delta `measure` with empty ledger; one worked non-empty case matches a hand calculation.
**Flags:** 3b.1 is the single most expensive step; scope down by adding the year-1 gain only to the existing investment-tax stage inputs (no new stage), and by deferring short/long split of the carryforward.

### Phase 4 — Trends: sold lots in returns, Realized view, daily log, percent-view handling
Ships alone: sold-lot returns plus the Realized view.

| Step | Work | Model / effort | Usage |
|---|---|---|---|
| 4.1 | Read ledger into Trends inputs; sold-lot rows in `_positions`; extend baseline-price symbols; Modified Dietz tests (three cases); replace the caveat note. | Opus, high | **Heavy-ish.** `live_snapshot.py` is large; Grep `_positions|_summarize|baseline_prices` and read slices. Highest risk is the cash-flow double count with `_checking_net_flows`. |
| 4.2 | Group By totals include sold rows (`live_groups.js` slices; vm-sandbox tests, no source grep). | Sonnet, medium | Moderate. |
| 4.3 | Realized view (route, payload, new frontend module, scope-aware, `$|%` toggle). | Sonnet, medium | Moderate. |
| 4.4 | Daily log fields in `trends_log`/`trends_job`; old entries read as "no data". | Sonnet, low | Light. |
| 4.5 | Percent-view handling and leak-guard tests; `unmatched_sale` hint on the Trends reconcile card; tax line "realized this year". | Sonnet, high (fail-closed rules) | Moderate. |
Files: `financial_trends_reporter/live_snapshot.py`, `trends_log.py`, `trends_job.py`, `percent_view.py`, `frontend/live_snapshot.js`, `live_groups.js`, new `frontend/realized.js`, tests.
Verify: preview server; compare a hand-computed return for a sample portfolio; percent-mode payload has no dollar leaks.
**Flag:** keep 4.1 small by testing the math in a pure function before wiring to the page.

### Phase 5 — 1099-B import and difference report
Ships alone: year-end correction flow.

| Step | Work | Model / effort | Usage |
|---|---|---|---|
| 5.1 | **5a:** parsers for E*Trade and Vanguard (samples in hand; E*Trade first, lot-level; Vanguard second, with "Various" summary lines, the CORRECTED flag, blank symbols and redemptions). **5b:** Fidelity, only once its sample arrives (about February 2027); until then a generic CSV import with user-mapped columns. PDF-to-CSV extraction with a check-before-apply preview and control totals; tests use obfuscated or synthetic fixtures; column map; preview in `import_preview_v1` style. | Sonnet, medium | Moderate. Brokers are known; the PDF step adds test-fix loops, so build CSV first and PDF extraction second. |
| 5.2 | Matching to ledger rows (lot-level, and many-to-one for aggregated lines), apply official numbers with audit, supersede earlier imports when a corrected statement arrives, difference report (UI + CSV export), unreported/unmatched lines. | Sonnet, high | Moderate-heavy: matching rules and many edge cases; test-fix loops. Scope down: exact-match first, fuzzy suggestions later. |
| 5.3 | Import column 1g wash-sale adjustments (display only). | Sonnet, low | Light. |

### Totals and sequencing
Phases 1, 2, 4 are each roughly one to two sessions of work; 3 is the heaviest (about two to three, with 3b the dominant share); 5 is about one session. Recommended order: 1 → 2 → 3a → 4 → 3b → 5, because Trends value (4) does not need the projection seeding (3b). Each phase is a separate PR (docs follow `Docs-only` rule: this document's PR does not wait for CI).

### Per-phase user-visible shipping
1: manual ledger + import detection. 2: queue and confirmation. 3a: realized-this-year tax panel and wash warnings. 4: returns include sales; Realized view. 3b: the projection reflects actual realized gains and the carryforward. 5: 1099-B correction.
