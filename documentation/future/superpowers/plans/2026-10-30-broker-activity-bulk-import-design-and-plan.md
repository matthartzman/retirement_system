# Brokerage activity bulk import: design and implementation plan

Status: design approved by default. The user skipped the questions ("continue"), so every decision below marked
**Claude's call** can be overridden. It builds on the realized-sales ledger
(`2026-10-28-realized-sales-ledger-design-and-plan.md`) and implements its step 2.1b, which was designed but never
built, plus the lot and income work around it.

## 1. Intent

Bring 2026 up to date from the brokerages' own transaction downloads instead of typing sales, fixing lots by hand
and eyeballing dividends. The importer should also take the same kind of file again later (monthly or quarterly),
adding only what is new. The year-end 1099s are the final check, not the source.

### Goals
- **Sales:** every sell in the file becomes a ledger sale, with same-day fills combined into one order. A sale is
  confirmed against specific holdings lots, either in bulk using a lot method the user picks in the preview, or
  one at a time in the existing queue panel.
- **Lots:** buys and dividend reinvestments add holdings lots. A lot already in the holdings, such as a
  reinvestment entered by hand a day off, is recognized and not added twice. Confirmed sales reduce lots
  through the existing confirm path, so undo still works.
- **Interest and dividends:** stored per row and reconciled against Monarch's "Dividends & Capital Gains" and
  "Interest" rows for the mapped Monarch account(s). The report lists matched rows, broker-only rows and
  Monarch-only rows, with totals by month and for the year.
- **Repeatable:** re-importing an overlapping file adds nothing. Each import records its date range so gaps
  show up.
- **Year end:** the 1099-DIV/1099-INT totals and the 1099-B are compared against what the activity imports built.
  The 1099-B path already exists (E*Trade). The Fidelity 1099 parsers wait for the 2026 forms (about February 2027).

### Non-goals (this effort)
- Brokers other than Fidelity. The parser registry makes the next one a single module, but each needs a real
  sample first. **E*Trade samples are now in hand** (2026-10-30: four "DownloadTxnHistory" CSVs for Matt's 401(k),
  Rollover IRA, Roth IRA and Trust, held outside the repo). Structure only:
  - Line 1 is "All Transactions Activity Types". Line 3 is "Account Activity for <account type> -<last digits> from
    <date> to <date>", which gives the account hint and the export range. Then a `Total:` line.
  - The header is `Activity/Trade Date, Transaction Date, Settlement Date, Activity Type, Description, Symbol, Cusip,
    Quantity #, Price $, Amount $, Commission, Category, Note`. Empty values are `--`. A Bank Deposit Program
    disclaimer follows the data.
  - **Activity Type** gives the kind directly: Sold, Bought, Dividend, Interest Income, Contribution, Transfer,
    Distribution, Service Fee, Redemption, Misc Income, Online Transfer.
  - The E*Trade parser is the next module (`broker_activity/etrade.py`), a follow-up to this PR.
- **Vanguard sample in hand** (2026-10-30: one "OfxDownload.csv" covering all of Pat's accounts). Structure only:
  - The header is on line 1: `Account Number, Trade Date, Settlement Date, Transaction Type, Transaction Description,
    Investment Name, Symbol, Shares, Share Price, Principal Amount, Commissions and Fees, Net Amount, Accrued
    Interest, Account Type`.
  - **One file holds several accounts**, with the account number on every row. Transaction Type values: Dividend,
    Reinvestment, Sell, Buy, Sweep in, Sweep out, Interest, Conversion (incoming/outgoing), Transfer (outgoing),
    Withdrawal, Partnership, Corp Action (Redemption).
  - **Design consequence:** the account choice must work per row, not only per file. The parser emits a per-row
    `account_hint` (`vanguard:<last 4>`). The preview asks for one plan account per distinct hint, using the same
    `broker_account_map`. Commit then runs the per-account steps (lots, orders, income) once per account inside the
    one transaction. The single-account Fidelity and E*Trade files are the one-hint case of the same flow. Built with
    the Vanguard parser, a follow-up to this PR. Redemptions and conversions go to `other` until reviewed.
- Cost basis from the broker. The activity file has none, so basis comes from the holdings lots and the 1099-B
  corrects it.
- Money-market sweep positions as lots (FDRXX, SPAXX and similar). They stay at par in the `CASH` lot, which the
  balance reconcile already keeps current. Their dividends are still income rows.
- Contributions, distributions, transfers, fees and adjustments. They are counted and listed, never turned into
  anything.

### Anti-goals (failure even if it "works")
- Double counting: a re-import, or a file that overlaps lots or sales already entered by hand, creates a second
  lot or a second sale.
- A sale reduces lots the user had already reduced by hand.
- A taxable sale is confirmed against lots the user never saw. The method is chosen in the preview, and the
  preview shows each sale's lots before commit.
- Losing the per-row detail, so a later 1099 difference can't be traced to its rows.

## 2. What exists (verified)

| Need | Where |
|---|---|
| Sales ledger rows, queue, confirm/undo | `src/stores/sales_repo.py` (v17/v18), `src/sales_confirm.py` (`confirm`, `undo`, `suggest_allocation` FIFO/HIFO/lowest_gain) |
| Lots | plan-file dataset `holdings` (`account, symbol, purchase_date, shares, purchase_price, lot_type, note`) |
| 1099-B parse/match/apply | `src/broker_1099b/` (registry pattern), `src/sales_1099b.py` |
| Monarch income rows | plan-file `ytd_transactions` (`Category` "Dividends & Capital Gains", "Interest") |
| Monarch account to plan account | `ytd_account_setup` (`Account` to `Mapped Investment Account`) |
| Tax class of an account | `core._infer_type` by name suffix (HSA, IRA, Roth, ...), as the tax-year panel already does |

The Monarch sell-queue loader (`sales_matching.load_sell_candidates`) is not wired to any route, so the queue is
empty in the real plan file. Broker candidates will be the first real queue rows.

Real-file check (the user's Fidelity HSA export, Jan–Sep 2026, held outside the repo): the holdings lots for
`Member_1_HSA` do **not** reflect the August and September ITOT sales. Two reinvestment lots are dated one day before
Fidelity's run date (06-17 vs 06-18, 09-17 vs 09-18), with a price a few cents different. That is the duplicate-lot
case the matcher must catch. The May SHV sales have no SHV lots left in the holdings, so they cannot be allocated and
must stay in the queue.

## 3. Design

### 3.1 Parser package `src/broker_activity/` (pure)
Mirrors `broker_1099b`: `normalized.py` (row fields, action kinds, helpers), `fidelity.py`, and a registry in
`__init__.py` with `preview_file(broker, text, *, file_name=None)`.

Normalized row: `run_date, settle_date, kind, action, symbol, description, quantity, price, commission, fees,
accrued_interest, amount, line` (1-based line in the file).

`kind` comes from the Action text (Fidelity), checked in this order:

| kind | Fidelity Action starts with / contains |
|---|---|
| `sell` | `YOU SOLD` |
| `buy` | `YOU BOUGHT` |
| `reinvest` | `REINVESTMENT` |
| `dividend` | `DIVIDEND RECEIVED` |
| `interest` | `INTEREST EARNED`, `INTEREST` |
| `cap_gain_short` / `cap_gain_long` | `SHORT-TERM CAP GAIN`, `LONG-TERM CAP GAIN` |
| `foreign_tax` | `FOREIGN TAX PAID` |
| `return_of_capital` | `RETURN OF CAPITAL` |
| `other` | everything else (contributions, distributions, transfers, fees, adjustments) |

A money-market sweep row (symbol in a small known set: FDRXX, SPAXX, FZFXX, SPRXX, FCASH, CORE, or Type `Cash` with
price 1.00 on a reinvest/buy/sell) is `sweep=True`. It makes no lot and no sale. Its dividend is still income.

File rules: find the header line by its column names past any leading blank lines. Stop at the first blank line after
data. Ignore the disclaimer and "Date downloaded" footer. Dates are MM/DD/YYYY. Numbers may be quoted, empty or
negative.

### 3.2 Row identity (idempotency)
No transaction id exists. `row_key = sha1(broker|account|run_date|action|symbol|quantity|amount)#n`, where `n` is the
occurrence count of that tuple within the file, so two identical fills on one day are both kept. Re-importing the
same or an overlapping file matches on `row_key` and adds nothing. **Claude's call:** an occurrence counter is per
file, so a later file that has *more* identical same-day rows than an earlier one adds only the extra ones. That is
the right answer.

### 3.3 Storage (plan schema v19)
- `broker_imports(import_id, broker, account, file_name, date_from, date_to, rows_total, rows_new, imported_at,
  status)`, where status is `applied` or `reverted`.
- `broker_activity(activity_id, import_id, row_key UNIQUE, broker, account, run_date, settle_date, kind, sweep,
  action, symbol, description, quantity, price, commission, fees, accrued_interest, amount, candidate_id, lot_ref)`.
  `lot_ref` is JSON naming the holdings lot this buy/reinvest created or matched (`{"created": true|false, account,
  symbol, purchase_date, purchase_price, lot_type, note}`).
- `sale_candidates` is rebuilt to add source `broker`, state `superseded` (a Monarch sell covered by a broker sale),
  and columns `fees`, `settle_date`, `broker_key` (unique when not null).
- `realized_sales` is rebuilt to add source `broker`. Rows, ids and indexes are preserved. SQLite cannot alter a
  CHECK constraint, so it is copy, drop, rename.
- `broker_account_map(file_pattern PRIMARY KEY, account)` remembers which plan account a file name belongs to.

### 3.4 Import flow (preview, then commit), `src/broker_import.py`
1. **Account.** The file has no account number inside. The user picks the plan account. The default comes from
   `broker_account_map` by file-name pattern: Fidelity `History_for_Account_<digits>.csv` gives the pattern
   `fidelity:<last 4 digits>`. The full number is never stored. The tax class comes from the account (§2).
2. **Preview** (no writes): rows read, new vs already imported, date range and gap warning against earlier imports
   of that account, then three sections:
   - **Lots:** each new buy/reinvest (non-sweep) is *add* or *already present*. Already present means a holdings
     lot of the account and symbol with shares within 0.001 and purchase date within ±3 days. The price difference
     is shown, never applied. **Claude's call:** ±3 days, the same tolerance as the 1099-B and Monarch matchers.
   - **Sales:** new sell rows grouped by (symbol, run date, price) into orders. Shares and proceeds are summed;
     proceeds are the Amount, which is net of fees. For each order, the lot method's proposed allocation is replayed
     in date order over the holdings plus the lots this import adds, so a buy earlier in the file is available to a
     later sale. The status is `ready` (fully covered), `short` (lots hold fewer shares) or `no_lots`.
   - **Income:** new dividend, interest, cap-gain, foreign-tax and return-of-capital rows, totals by kind.
   - **Position check:** per symbol, holdings shares now, net change from new rows, and shares after. A negative
     result is a warning. It usually means the holdings already reflect some of these sales by hand.
3. **Commit** in one plan-file transaction: store the import and rows, add the *add* lots (`note` =
   `"<Broker> <kind> <run date>"`), queue one `broker` candidate per order (fees, settle date, `broker_key` = the
   order's first row key), and mark covered Monarch sell candidates `superseded`. A covered candidate has the same
   mapped account, the same symbol (or a bare row), proceeds within $1 and a date within 3 days. Then, if the user
   ticked **Confirm sales using <method>**, confirm every `ready` order through the same code path as the queue
   panel (`sales_confirm`), using the replayed allocation. `short` and `no_lots` orders stay in the queue.
   - **Claude's call:** bulk confirm is opt-in per import. The default method is **FIFO**, which is Fidelity's
     default lot relief, so the 1099-B will usually agree. HIFO and lowest-gain are offered. This counts as the
     user's confirmation under the "specific lots only" decision, because the preview shows every order's lots
     before commit.
4. **Revert** an import: allowed only while none of its candidates is confirmed and each lot it created still has
   its original shares. It removes those lots, deletes its candidates and rows, restores superseded Monarch
   candidates to `unmatched`, and marks the import `reverted`. Otherwise it is refused with the reason (undo the
   confirmed sales first).

### 3.5 Income reconciliation `src/broker_income.py` (read-only)
For one plan account and year: broker income rows (dividend, interest, cap gains; sweep dividends included) vs
Monarch rows whose Account maps to that plan account in `ytd_account_setup` and whose Category is "Dividends &
Capital Gains" or "Interest". Match one-to-one on amount within $0.01 and date within ±3 days, nearest date first.
Output: matched pairs, broker-only, Monarch-only, totals by month (broker, Monarch, difference) and for the year.
Reinvestment rows are linked to their dividend (same symbol, same date, same amount) for display only.

### 3.6 Year-end validation (Phase 4; Fidelity forms needed)
- **1099-B:** the existing `broker_1099b` matcher and apply flow, plus a Fidelity parser when the sample arrives.
  Ledger rows from broker candidates are `source=broker` and match like any other.
- **1099-DIV / 1099-INT:** enter or parse the box totals per account and year (1a ordinary dividends, 1b qualified,
  2a total capital gain distributions, 7 foreign tax; INT box 1). Compare them to the year's broker income rows by
  kind. A difference names the rows to look at. Qualified vs ordinary cannot be checked from activity rows, so only
  1a/2a/7/INT-1 are compared.

### 3.7 UI
A **Brokerage activity import** panel on the Sales ledger page, in a new frontend module
(`dashboard_decomp_broker_import.js`):
1. Choose the file and the account.
2. The preview shows the lots, sales, income and position check.
3. Choose the bulk-confirm option and commit.
4. An imports list with ranges and revert.

Also an **Income check** table (account and year) showing the §3.5 report.

## 4. Edge cases
- **Split fills** (whole and fractional rows, the same price, one with a fee): combined into one order. Fees summed.
- **Sell with no settle date or price:** the price is derived from amount / shares. A missing quantity is an error
  row, and the import refuses that row only.
- **A reinvestment on the same date as its dividend:** both stored. The lot comes from the reinvest row.
- **Wash sales:** reinvest and buy rows are stored with their dates, so the wash scan can read them later
  (`wash_sales` reads holdings lots today, and the added lots are in the holdings). No change to the scan in this
  effort.
- **Non-taxable account (HSA, IRA, Roth):** sales are confirmed the same way, to keep share counts honest. The gain
  is `None` (existing rule).
- **Partial coverage:** an order whose lots run out stays `short` in the queue, and the user fixes the holdings or
  records it manually. Nothing is guessed.

## 5. Testing
Synthetic fixtures only. The real file is never committed and its account number is never written. Unit tests cover:
parser (layout, footer, quoting, kinds, sweep); row keys (duplicates kept, re-import adds nothing); grouping;
lot-dedupe tolerance; replay allocation with an in-file buy before a sale; position check; commit/revert round-trip;
Monarch superseding; income matching. One functional route test runs preview and commit. Last, run against a copy of
the real plan file and the real export in the scratchpad to check the numbers by hand: 7.484 ITOT shares sold in
Aug–Sep, the two reinvestment lots recognized as already present, and SHV left `no_lots`.

## 6. Implementation plan

Estimates are relative to a 5-hour Pro session: *light* is under about a tenth of a session, *moderate* is a quarter
to a third, *heavy* is most of a session. **Check `/usage` after each phase against these estimates** and rescope if a
phase ran heavier.

| Phase | Work | Model / effort | Usage and drivers |
|---|---|---|---|
| 1 | `broker_activity` package: normalized rows, Fidelity parser, row keys, grouping. TDD. | Sonnet, medium | Light. Small new files; fast unit tests. |
| 2 | Schema v19 (rebuild `sale_candidates`/`realized_sales`, new tables), repo methods, demo seed rebuild, pinned-version test bumps. | Sonnet, high | Moderate. Cost is the version-pin test fixes across about 8 test files (grep `PLAN_SCHEMA_VERSION`/`== 18`, don't read them whole) and the demo seed rebuild. **Flag:** run the plan-store tests alone first, not the whole suite. |
| 3 | `broker_import`: preview (lots, sales, replay allocation, position check), commit, bulk confirm through a refactored `sales_confirm` core, Monarch superseding, revert. | Opus, high | Moderate-heavy. Most of the logic and the test-fix loop. Scope down: build preview and commit first; revert last. |
| 4 | `broker_income` reconciliation. | Sonnet, medium | Light-moderate. |
| 5 | Routes and manifest, frontend panel, diagram regen. | Sonnet, medium | Moderate. `plan_routes.py` is mid-sized: grep the `/api/sales/1099b` block and copy its shape. **Flag:** don't read `dashboard.js`; mount the new module the way `dashboard_decomp_sales_tax.js` is mounted. |
| 6 | Real-file dry run on a scratch copy; fast pytest; `npm test`; golden master `measure` (expected zero delta: nothing the projection reads changes until sales are confirmed in the real plan). | Sonnet, medium | Light-moderate. Run pytest in the background into a log. |
| 7 (Feb 2027) | Fidelity 1099-B parser; 1099-DIV/INT totals entry and comparison. | Sonnet, medium | Moderate; needs the forms. |

Phases 1–6 ship as one PR (`broker-activity-import`). Phase 7 is its own PR when the forms arrive.

## 7. As built (2026-10-30, phases 1–6)

- **Modules:** `src/broker_activity/` (parser package and registry), `src/stores/broker_repo.py` (schema v19 and
  `store.broker`), `src/broker_import.py` (preview, commit, revert), `src/broker_income.py` (income check), and the
  `/api/sales/broker/*` routes. In the frontend, `frontend/js/dashboard_decomp_broker_import.js` is mounted on the
  Sales Ledger page.
- **Ledger convention (Claude's call):** a broker sale's ledger proceeds are the broker Amount, which is net of
  fees, and the ledger `fees` is 0, so gain = Amount - basis. Fees stay on the candidate and the activity rows. This
  matches how the Monarch path already records proceeds, and the 1099-B's net proceeds.
- **Tax class:** `sales_confirm.default_tax_class` now falls back to the Planner's account-name suffix rule (`_hsa`,
  `_ira`, ...) before `taxable`. Before this, a first sale in an HSA defaulted to taxable in the queue panel too.
- **Editing sales (user question during the build):** the ledger table has **Edit** for manual rows. It voids the
  old row and records the corrected one (`POST /api/sales/<id>/replace`). Broker and Monarch rows have **Back to
  queue** (`POST /api/sales/<id>/requeue`), which undoes the confirm, returns the shares to their lots and reopens
  the sale for lot selection. Before this, Undo was reachable only right after a confirm. Rows carrying 1099-B
  numbers stay locked as before.
- **Real-file dry run** (scratch copy of the plan file and the HSA export; figures not recorded): all six buy and
  reinvest rows were recognized as lots already present, including the two dated a day earlier. The August and
  September sales were confirmed FIFO. The SHV sale stays `no_lots` with a negative-position warning. Re-import adds
  nothing.
- **Finding:** the income check showed Monarch holding **two copies of every 2026 transaction** in the HSA account,
  each with its own Monarch Id and a different description format. This looks like two overlapping Monarch
  connections. Every Fidelity dividend matched one copy. The other copies show as Monarch-only. Not changed here;
  the user to resolve it in Monarch.
- **Follow-ups:** Phase 7 (Fidelity 1099-B and 1099-DIV/INT checks, about February 2027).

### 7.1 E*Trade and Vanguard parsers (added 2026-10-30)
- **Modules:** `broker_activity/etrade.py` and `vanguard.py`, registered next to Fidelity. Each parser also has
  `detect(text, file_name)`; `broker_activity.detect_broker` picks the broker from the header, so the API's `broker`
  is optional (empty means detect) and the UI has a broker picker ("Detect from the file" by default).
- **Accounts per file:** a row may carry `account_hint`; a parser may also set `meta["account_hint"]` for the whole file
  (E*Trade: `etrade:<digits>` from line 3, Fidelity: from the file name). `broker_import` maps each distinct hint to a
  plan account (request `accounts` = `{hint: plan account}`; the single `account` still works when the file has one
  hint; else the remembered `broker_account_map`). Row keys use the row's own plan account. Commit runs the per-account
  steps (lots, orders, income, Monarch supersede, bulk confirm) once per account in one transaction and writes **one
  `broker_imports` record per account**, so revert and the coverage warning stay per account. The preview keeps its
  old shape (merged `lots`, `orders`, `position`, `income`, each tagged with `account`) and adds `hints` and `parts`
  (the per-account detail). Commit returns `import_ids` beside `import_id` (the first).
- **E*Trade findings (structure only):** sells have a negative quantity and a positive Amount net of Commission;
  buys a positive quantity and a negative Amount. Bonds and T-bills are quoted per 100 face (quantity is face value,
  price a percent of it), so the parser divides the price by 100 when quantity x price is about 100x the cash moved.
  The Symbol column carries the CUSIP for bonds. `MSPBNA` (Bank Deposit Program) and its interest rows are `sweep`
  rows; their interest is still income. Activity Types Contribution, Distribution, Transfer, Online Transfer,
  Service Fee, Misc Income and **Redemption** are `other` (counted, never acted on). A matured T-bill's Redemption
  therefore leaves its lot open until reviewed; that is the one gap to close if redemptions should relieve lots.
- **Vanguard findings:** Sell has negative shares and a positive Net Amount, already net of fees (principal minus fees);
  Buy and Reinvestment have positive shares and a negative amount. **Sweep in / Sweep out** (the settlement fund,
  VMFXX) are `sweep` buy/sell rows with zero shares, listed under ignored, never lots or sales. VMFXX dividends and
  reinvestments are sweep rows too; the dividends count as income. **Conversion (incoming/outgoing), Transfer
  (outgoing), Withdrawal, Partnership and Corp Action (Redemption)** are `other`: an in-kind Roth conversion moves
  shares between accounts without a sale, so it is not a ledger sale, but its incoming side does not create a lot yet.
- **Real-file dry run** (scratch copy of `plan.rpx`; counts only): all four E*Trade files and the Vanguard file parsed
  with no error rows; every row was accounted for (E*Trade 79 / 116 / 21 / 87 rows, Vanguard 113 / 75 / 49 per
  account); sell shares and proceeds, dividend and interest totals, and buy/reinvest counts per account agreed with
  an independent sum of the raw files; bond prices came out per unit (about 0.99); re-importing each file added
  nothing. Many sells in the E*Trade IRA, Roth and Trust and in Vanguard show `short`/`no_lots` and negative
  position warnings because the holdings do not yet reflect the year's buys; these are for the user to review.
