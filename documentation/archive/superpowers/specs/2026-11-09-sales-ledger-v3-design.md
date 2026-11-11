# Investment Sales Ledger v3: simplify the page (item 378)

Status: implemented (merged to main as PR #418 on 2026-11-09); open items are in BACKLOG.md

Date: 2026-11-09. Mockup: `documentation/future/superpowers/mockups/sales-ledger-v3.html` (the two
"Option B" views, plus "Where the cash section goes"; Option A there is the rejected alternative, though
its Sales and Tax year tabs are the ones used here).
Builds on the merged 2026-11-03 redesign (`2026-11-03-sales-ledger-redesign-design.md`, PR #389 follow-ups).

## Why

The 11-03 redesign split the page into four tabs, but every tab still holds items that belong
somewhere else, controls that do nothing, and internal names. Matt's review (item 378) and a walk of
the live plan on 2026-11-09 found:

- The two tabs disagree on the same number. Sales ledger says short-term net is +$11,848 (it counts
  IRA/Roth/HSA sales), and Tax year says $15,726 (taxable only).
- Year-end reconciliation (cash in investment, withdrawals by pairing, plan vs reported, closed years,
  floor-feed verification) sits inside a page that is about sales and lots.
- Controls that do nothing or mean nothing: Density, "More views", "managed" chips that look like
  buttons, managed-account checkboxes, and a Dismiss button that doesn't work (a bug).
- Internal names (`Member_1_Trust`, `Business_Checking`) appear in wash notes and account lists.
- The Record-a-sale form asks for an account type the account already sets, says "Record a sale"
  three times, squashes the Account dropdown, and claims IRA gains are left blank when the table
  shows them.
- One sale shows as up to 5 rows (one per lot). There are 74 rows for about 30 real sales.

Success: the page answers three questions without any reconciliation noise. What needs fixing? What
did I sell? What tax does it cause in the chosen year? Every number on the Sales and Tax year tabs
agrees.

## Goals

1. One **Year** control and one **Taxable accounts only** switch at the top that drive every ledger tab.
2. The ledger has three tabs, each with one job: **To fix** holds decisions, **Sales** is the record,
   **Tax year** is the result (and takes in the 1099-B).
3. **Investment Holdings owns "what I own and how I got it"**: Positions, plus a new **Activity** tab
   (the transaction log, which writes the holdings) and a new **Import** tab (broker activity files,
   which feed the log). This also fixes today's dead end: log-managed rows are read-only on Holdings
   with "edit them in the log" (`frontend/js/dashboard_decomp_holdings.js:414`), but the log is on
   another page.
4. Remove what does nothing or belongs elsewhere (list below).
5. Show friendly account names everywhere. Never list a bank account where only investment accounts apply.
6. Fix three data defects found during the review (section "Defects").

## Non-goals

- App-wide row density. It's a future item: record it in the backlog and don't build it here.
- Engine changes beyond what the wash-sale basis adjustment causes. The ledger's tax estimate and the
  basis of replacement lots *do* change (section "Wash sales"). Fixture plans with no wash sales must
  not move a golden master.
- Option A (four ledger tabs, with the log and imports kept on the ledger) was recommended first. Matt
  chose B on 2026-11-09.
- Redesigning Year-End Transition beyond hosting the moved cash material.
- Changing the Holdings Positions table itself (grouping, columns, auto-save, cash editor).

## Anti-goals (a failure even if it works)

- Sales and Tax year show different totals for the same Year and switch.
- Removing the managed-account control changes whose holdings get written for existing plans.
- A wash review is lost on the next "Check for wash sales" scan or on re-recording a sale.
- Fixing a sale's lots turns into hunting: every ledger item that needs a log edit must deep-link to
  Holdings › Activity already filtered, with a way back.
- A full account number appears anywhere (last 4 only, per standing rule).

## Decisions (Matt, 2026-11-09)

| Question | Decision |
|---|---|
| Layout | **Option B.** The ledger has three tabs (To fix, Sales, Tax year). The transaction log and the broker activity import move to Investment Holdings as Activity and Import tabs |
| Cash in investment material | Moves to **Year-End Transition** |
| Managed-account checkboxes | **Removed.** Matt keeps no investment account by hand. Every investment account the log has rows for is managed. Bank accounts are never managed |
| Sales rows | **One row per sale**, which opens to its lots |
| Year scope | **Filters everything**: queue, history finds, wash flags, and on Holdings the Activity log and import history (each with its own Year, since Holdings has no page-wide year). "All years" stays |
| Taxable-only switch | On by default. Applies to Sales and Tax year (Tax year is taxable-only by nature; the switch is shown but locked on there with a tooltip) |
| Wash flag removal | Became a **Review** with three outcomes, in To fix. Matt chose the full wash-sale treatment ("all of it now"): proportional disallowance, basis add-back, 1099-B tie, open-window warning |
| 1099-B | File only. No paste box. Taxable accounts only |
| Sales CSV import | Removed |

## The Sales Ledger, tab by tab

### Header (all tabs)

- **Year** (`slYear`, replaces "Sale year"): it lists "All years" plus only the years that have ledger
  or log rows. No future years. The default is the current calendar year if it has data,
  otherwise the latest year with data. The value is persisted as today.
- **Taxable accounts only**: a checkbox, on by default and persisted. The caption next to it names
  the accounts it covers (friendly names).
- **Voided rows (n)**: a link that replaces the "Show voided" checkbox and toggles them on Sales.
- Removed: Density, the "Sale year" label, "More views".
- Every heading or label that shows a year takes it from Year. "All years" reads "(all years)". The
  carryforward label reads "carried in from {Year−1}".

### To fix (replaces "Fix lots & transactions")

A short to-do list. Anything that needs a log edit links to **Holdings › Activity**, already filtered,
with "← Back to Sales Ledger".

1. **A status line** instead of three collapsed sections that each say "all fine": "No sales waiting
   for lots", "Log agrees with holdings", "1099-B: …". Each turns into a full section only when it has
   something to show. **Sales waiting for lots** stays here (the queue confirm is a ledger action).
   **Log differs from holdings** shows the accounts and links to Holdings › Activity.
2. **Holding-period check** (new). Warn when sales for the Year use lots whose purchase date came from
   backfill ("lot with no purchase on file"), with a count and a Review link that opens Holdings ›
   Activity filtered to those opening lots.
3. **Found in broker history**: today's rows. Treasury-bill rows say "counted as interest income".
   The button is relabelled **Got it, hide** and must actually work (see Defects).
   - A **show hidden (n)** checkbox in the card header lists hidden rows greyed out, with the date
     each was hidden and an **Unhide** button. The count follows the Year. It needs a
     `/api/sales/history/undismiss` route and a `hidden` listing, since today `history_sales`
     keeps only a set of dismissed keys. Store the hidden date alongside each key.
   - When nothing is visible but some rows are hidden, the card collapses to its title and keeps
     the "show hidden (n)" control. It never disappears entirely.
4. **Wash sales**: moved here from Tax year. Each replacement line links to that lot in Holdings ›
   Positions. One card per *sale* (lots grouped). The rules and
   amounts are in section "Wash sales"; the card shows:
   - Sold at a loss: symbol, account, date, shares, proceeds, loss, and the lot count.
   - Replacement purchases: one line per buy that counts, with account, date, shares, value and
     "(dividend reinvest)" when it was one. Each line says where its share of the loss goes: "adds
     $0.66 to the cost of this lot" for a taxable account, or **"lost permanently"** (in red) for an
     IRA, Roth or HSA.
   - The amount line: "Disallowed $0.66 of $121.36 · $120.70 still deductible".
   - A **Review** control with three outcomes: **Wash sale** (the default), **Broker already reported
     it**, and **Not a wash sale** (needs a reason). A "Reviewed (n)" link lists past choices with Undo.
5. **Open wash windows** (prevention): for each loss sale less than 31 days old, one line naming the
   household accounts that hold the same fund and have reinvested it in the last 12 months, with the
   date the window closes: "Turn off reinvest for VTI in Pat's IRA, Pat's Roth until 12-06." Each line
   goes away on its own when the window closes.
The transaction log leaves the ledger (see "Investment Holdings").

### Sales

- KPI strip: number of sales, short-term net, long-term net, fees. It honours Year and Taxable-only,
  and matches Tax year exactly when Taxable-only is on.
- **＋ Record sales** is the only entry point (no summary, heading and button saying the same thing).
  It opens a compact **entry grid** (Matt, 2026-11-09: "one with column headings and ability to add
  rows"):
  - Column headings: Account (friendly name plus tax type in brackets), Symbol, Sale date, Shares,
    Proceeds, Fees, Lots, Gain, ✕. **One row per sale.** "＋ Add row" adds another, and Enter in the
    last field of the last row does the same. Several sales can be entered and saved together.
  - **Lots** shows the match state as a chip: "2 lots ✓" when the shares match, or "0 / 200 · pick"
    when they don't.
  - **The lot chooser**: ▸ on a row opens its chooser directly under it, and only one is open at a
    time. When the account has a transaction log, the chooser lists that account's **open lots of
    the symbol** as of the sale date, with columns ☐, Bought, Open shares, Cost / share, Sell
    shares, Basis, Gain, Term, and a Selected total row (shares n / n, basis, gain, term or
    "Mixed").
    - Ticking a lot sells all its open shares. Typing a smaller number in Sell shares sells part of
      it.
    - **Fill** buttons (FIFO, Highest cost, Losses first, Clear) tick lots in that order, the same
      methods the brokerage import offers. The default is the import's lot method.
    - When the account has no log, or a lot isn't in it, the chooser becomes blank rows (Bought,
      Shares, Basis) with "＋ add lot".
    - The chooser reads the existing open-lots view (`src/transactions.py` `open_lots`), which
      already applies wash basis add-backs once phase 3 lands.
  - The Gain column is live. For IRA, Roth and HSA accounts it reads "not taxable". A taxable loss
    row with a replacement buy already in the log within 30 days shows a "wash?" chip.
  - **Save n sales** stays disabled until every row's shares are matched. It saves one ledger row
    per lot, as today, and links them to the chosen log lots (`txn_lot`), as queue confirms do.
  - The Account type field is removed: the tax class comes from the account.
- An empty lot chooser ("no open lots of ITOT in Matt's Trust on that date") links to Holdings ›
  Activity for that account and symbol, to add the missing buy.
- **Table**: one row per sale. Group rows by (account, symbol, sale date, source sale id); if a
  source id exists, use it. Columns: ▸, date, account, symbol (+ "wash?" chip), shares, proceeds,
  basis, gain, term ("Mixed" when lots differ). ▸ opens the lot rows.
- Row actions (Matt, 2026-11-09: **one lot at a time**). Edit and Void stay per lot, using today's
  `replace_sale` / `void_sale` calls. They sit in a ⋯ menu on each **lot row**. The **sale row's** ⋯
  menu has only **Send back to queue**, which already acts on the whole order
  (`src/sales_confirm.py:335`). An action that doesn't apply is greyed out with a reason. Buttons no
  longer appear and disappear by row. No new endpoint is needed.

### Tax year

- The heading is "Tax year {Year}". With "All years" the tab shows "Pick a year" instead of totals.
- KPIs, the netting table, the tax estimate and carryforward-in are the same as today.
- The status line gives the 1099-B state, a link to the wash flags in To fix, and the year-end steps
  count linking to Year-End Transition.
- **Broker 1099-B** (moved from the old Import tab): a collapsed card, "Import a 1099-B", that opens
  automatically when the Year's taxable accounts have no 1099-B and it's after January 31 of the
  following year. Fields: file drop or choose (no paste box), Broker, Account (**taxable accounts
  only**), Preview. The "1 Source / 2 Preview / 3 Apply" step labels are removed; the preview and
  apply steps themselves are unchanged. The tie report (including the wash block) shows here.
- Interest and dividends: as today, with the year taken from Year.
- **Fund types**: a two-column table with one `<select>` per symbol instead of 9 radio buttons per
  symbol.
- The wash-sale cards move to To fix. Tax year keeps a **"Wash-sale losses disallowed"** line in the
  netting table that lowers the loss before netting, so the estimated tax reflects it. It is split into
  "deferred into replacement lots" and "lost permanently (IRA/Roth/HSA repurchase)", with a link to
  the cards.

### Removed from the ledger

- The Import tab. Broker activity goes to Holdings › Import, and the 1099-B goes to Tax year.
- The Sales CSV import (frontend, route and service functions) and the 1099-B paste textarea. The
  server's text parser stays for file content.

## Investment Holdings (Option B)

The sidebar step and its place in the sidebar are unchanged, so the recorded navigation baseline
stays as it is. The sidebar description becomes "Each investment you own, one row per purchase, and
the activity behind it." The page gets a tab bar, **Positions | Activity | Import**, using the same
`workspace-tabs` pattern as the ledger. The tab is remembered and deep-linkable
(`#holdings/activity?account=…&symbol=…&type=…&source=backfill&year=…`).

### Positions

- Today's grouped table, **unchanged**: grouping chips, columns, Sold positions row, totals,
  auto-save of table edits, the "Edit cash in investment accounts" editor, and read-only rows for
  log-managed accounts.
- A **"Log agrees with holdings"** status in the toolbar (or "Log differs for n accounts → Activity").
- Lot-row markers (new):
  - **incl. $x wash**: the cost includes a disallowed wash loss. The tooltip names the sale it came
    from and the purchase date the holding period now counts from. It links to the wash card in
    Sales Ledger › To fix.
  - **date not on file**: the purchase date came from backfill. A **Fix date** button opens that
    opening row in Activity's edit dialog.
- **History** on a lot row opens Activity filtered to that account and symbol.
- The read-only note for managed rows changes from "edit them in the log" to an **Edit in Activity**
  link.

### Activity (the transaction log, moved from the ledger)

- One view: the Edit log / History & held lots switch is removed, and the held-lots filter is
  dropped because Positions covers it.
- Toolbar: **Year** (its own control; it defaults to the ledger's Year when arriving by deep link),
  Account, Symbol, Type, **Show cash opening rows (n)** (off by default; hides `opening` rows on
  symbol CASH), **＋ Add transaction**, **⇄ Transfer**.
- Void moves inside the Edit dialog. The managed chips, the "Edit…" checklist and its explanation
  are removed.
- A sale row links to its sale in Sales Ledger › Sales.
- One line under the toolbar: "Changes here save immediately." This is unlike the Positions table,
  which saves when you leave the page; the page's auto-save banner names only Positions.
- A deep link from the ledger shows "← Back to Sales Ledger" above the toolbar.

### Import (broker activity, moved from the ledger)

- **Brokerage activity** card: file drop or choose, Broker (detect), Account (from the file, or an
  investment account; never a bank account), Lot method, Preview. The step labels are removed and
  preview/apply are unchanged.
- **Import history**: filtered by its own Year to imports whose date range overlaps it, with
  reverted imports hidden behind "show reverted (n)".

### Year-End Transition (receives the cash material)

The "Cash in investment" section and its three sub-blocks leave the ledger. On Year-End Transition,
for the closing year:

- **Investment cash agrees with the broker**: per-account balance vs cash lot. Matching rows are
  collapsed behind "n of n match". The account names are plain text (no unexplained links). The
  "Reinvest dividends default" setting moves to Plan Features.
- **Withdrawals: actual vs plan**: today's pairing and plan-vs-reported rows, with accounts that are
  $0 on both sides hidden. The excess-contribution note stays.
- **One-time: verify accounts for the tax feed**: floor-feed verification. Shown expanded until every
  account is verified, then one collapsed line.
- **Closed years**: one collapsed list. Each closed year opens to its reported table and its Reopen
  button. Years with nothing reported are left out (today 2024 is all zeros).

## Wash sales (added 2026-11-09, Matt: "all of it now")

Today `src/wash_sales.py` flags a loss sale when the household buys the same symbol in any account
within 30 days, and nothing more. It's flag only: the Tax year tab shows the whole loss ("$731.22 …
may overstate") and changes nothing. The rules below follow the IRS treatment Matt supplied
(reinvests count as purchases; the window is the sale day ± 30 calendar days; it applies across
spouse and retirement accounts; disallowance is proportional; the basis is added back except in IRAs).
Matt's CPA should confirm rule W1 before release.

### Rules

- **W1. Shares sold in the same sale are not replacements.** A buy inside the window whose shares are
  among the lots sold in the same sale (same grouping key: account + symbol + sale date) is excluded.
  Today only the sold lot's own purchase is excluded. On 2026 data this drops the VGSH and VTEB
  flags, whose "replacement" reinvests were sold on 4-01 in the same sale.
- **W2. Replacement shares are matched oldest first.** For each loss sale (grouped), the qualifying
  buys are sorted by date, and each buy's shares can serve as replacements for only one loss sale.
  Earlier loss sales claim them first. Replacement shares used = min(shares sold, shares bought that
  are still unclaimed).
- **W3. Proportional disallowance.** Disallowed = loss × replacement shares used ÷ shares sold. It is
  spread across the sale's lots by their share of the loss, and across the replacement buys in W2
  order. The rest of the loss stays deductible.
- **W4. Where the disallowed loss goes.**
  - Replacement in a **taxable** account: the amount is added to the cost of those replacement shares,
    and their holding period starts on the original lot's purchase date (tacking).
  - Replacement in an **IRA, Roth or HSA**: the amount is lost permanently, with no basis add-back.
- **W5. Chains.** A replacement lot carrying an add-back that is later sold at a loss inside a new
  window is processed again with its adjusted cost. Process all sales in sale-date order.
- **W6. Substantially identical** stays the same symbol plus `identical_groups` (no change to the
  current definition).

### Review outcomes (replaces "Not a wash sale" / `cleared_by_user`)

These are stored in a new `wash_reviews` table keyed by the sale grouping key: outcome, reason,
broker amount, user and timestamp. Keying it to the sale rather than to ledger rows means a review
survives Send back to queue and re-recording.

| Outcome | Effect |
|---|---|
| *(none)* / **Wash sale** | W1–W5 apply. "Wash sale" just records that the user looked. |
| **Broker already reported it** | Used when the broker's 1099-B shows a wash adjustment for this sale. The broker's `wash_disallowed` is used in place of ours for this sale (no double count). Our basis add-back is kept only for replacements in *other* accounts, since the broker adjusts the replacement lot in its own account. Set automatically by 1099-B apply (see 1099-B tie). |
| **Not a wash sale** | Needs a reason: "not substantially identical", "replacement shares were sold in this sale" (for anything W1 misses), or "other: …". Nothing is disallowed or added back. |

`plan_flag_updates` and the `wash_flagged` count skip reviewed-as-not sales. The `wash_flag` column
keeps its current values for display. Its CHECK constraint is untouched.

### Basis add-back on replacement lots (W4)

- It's stored as **wash adjustment** records, not by editing log rows: `(adjustment_id, from sale key,
  replacement txn_id, shares, amount, tacked_purchase_date)`. A Void or Edit of either side
  recomputes them.
- `open_lots` and the holdings materialize step apply them, so Investment Holdings shows the adjusted
  cost per share and the tacked purchase date on those shares. The log rows themselves are unchanged
  (the broker's raw trade stays visible). An adjusted lot shows an "incl. $0.66 wash adjustment"
  marker.
- When the replacement shares are later sold, the add-back goes into that sale's basis, pro rata by
  shares taken from the adjusted lot. Term uses the tacked date.
- **Engine impact:** plans with adjustments get slightly different holdings cost, and so a different
  unrealized-gain tax estimate. Fixture plans have no wash sales. Run
  `tools/regen_golden_master.py measure` and `pytest tests/test_phase_golden_equality_regression.py`
  to prove no golden moves. Any move is a defect, not a regen.

### 1099-B tie

- On 1099-B apply, a row with `wash_disallowed > 0` sets the sale's review to **Broker already
  reported it** (unless the user already set an outcome) and stores the broker amount.
- The tie report gets a "Wash sales" block per account showing broker-reported against computed
  same-account amounts, and computed cross-account amounts listed as "not on any 1099-B: your
  return must include these". This is the main reason the feature is worth having: brokers never
  see the spouse or IRA side.

### Open-window warning (prevention)

- Shown in To fix (item 5) and as a strip alert when any window is open.
- An account counts as "reinvesting" a fund when the log has a `reinvest` row for that symbol (or an
  identical-group symbol) in the last 12 months. The app can't see broker DRIP settings, so it says
  "has reinvested" and never "has reinvest on".
- When an account holds the fund but has no recent reinvest, it's listed separately: "Also holds VTI:
  Matt's 401k (no recent reinvest; check contributions)". The 401k case covers payroll purchases.

### What the numbers become on 2026 data (for the builder to check)

The 9 lot flags become 4 sales. W1 removes VGSH and VTEB. MUB 4-01: about 0.86 + 0.41 replacement
shares out of 160.848 → roughly $1 disallowed. MUB 4-16: a small amount. Total disallowed is about
$1–2, against $731.22 shown today. The builder should recompute and record the exact figures in the
plan's test fixture.

## Defects to fix in this work

1. **History Dismiss doesn't stick for T-bill rows.** `src/history_sales.py` `_items()` checks
   `dismissed` for sales but not for the Treasury loop. Check the key against `dismissed` in the
   Treasury loop as well, and add a unit test.
2. **Bank accounts in the log.** The log created `opening` CASH rows for Business_Checking and
   Family_Checking (2026-11-02 backfill), and both appear in every account dropdown on the page.
   Investment-account lists must exclude bank accounts. The backfill must skip accounts that aren't
   investment accounts. Existing rows are voided by a one-time cleanup that the user confirms (not
   silently).
3. **The Record-a-sale note is wrong.** It says gain is blank for pre-tax/Roth/HSA, but the table
   shows it. The table shows "—" with a "not taxable" tooltip for those accounts. Their gain is
   still stored.
4. **Lot edits have nowhere to go from Holdings.** Managed rows on Holdings say "edit them in the
   log", but the log is on another page. Option B's Activity tab fixes this.

## Constraints

- `frontend/js` total line ceiling (`test_frontend_size_ratchet`): the work must net-remove lines.
  Moving the cash panel, deleting Density, the CSV import, the log modes and the radio grid should
  more than pay for the additions. Never raise the ceiling.
- New tests must not assert string literals against frontend source (`test_freeze_frontend_source_grep`).
  Use the Node vm sandbox (`tests/frontend/load_dashboard.mjs`) or API responses.
- The existing frontend tests that pin today's structure will need updating and are expected to
  change: `sales_ledger_page`, `sales_ledger_ui`, `sales_ledger_followups`, `cash_investment_panel`,
  `transactions_log_panel`, `broker_import_panel`, `sales_1099b_panel`, `year_end_page`, and the
  Holdings page tests (find them with `grep -rln holdings tests/frontend`).
- Moving the log and import panels to Holdings changes which page mounts them, not their files. Keep
  `dashboard_decomp_transactions_log.js` and `dashboard_decomp_broker_import.js` as modules; Holdings
  imports them.
- The deep-link format must survive a page reload.
- Any file added, moved or deleted under `frontend/` or `src/` means regenerating the system diagram
  (`python tools/generate_system_diagram.py`).
- Golden masters must not move (fixture plans have no wash sales). See "Basis add-back".
- Run `python tools/fast_gates.py` before every push.
- Account names come from `src/person_labels.py` `display_account` (server) and the existing
  frontend label helper. Never construct names in new code.

## Data and API notes for the builder

- Wash states today: `none`, `possible`, `confirmed_by_user` (`src/wash_sales.py` `plan_flag_updates`
  skips `confirmed_by_user`). Reviews live in `wash_reviews` (section "Wash sales"), not in a new flag
  value. Detection's `matches` already carries the buy side. Extend it with `txn_id`, value and the
  W2 shares used, and expose it per sale with friendly names.
- Managed accounts: `transaction_accounts` table (`src/stores/transactions_repo.py`). Removing the
  UI must not unmanage anything. New investment accounts that get log rows become managed
  automatically. Bank accounts are never managed. Remove `Business_Checking` and `Family_Checking`
  from the table if they're in it.
- Year list: build it server-side from ledger, log and import dates, or client-side from data already
  loaded. Builder's choice.

## Settled after the builder check (2026-11-09)

Answered from the code (evidence as file:line on 2026-11-09 main):

- **Defect 1.** The T-bill loop at `src/history_sales.py:130-136` never checks `dismissed`; the trades
  loop does (line 120). `dismiss()` (line 172) already accepts the `account|symbol|date|interest` key,
  so only `_items` changes.
- **The Taxable-only filter must equal Tax year's**: `status=="confirmed"`, `tax_class=="taxable"`,
  `gain is not None`, and the sale-date year (`src/sales_tax_year.py:75-77`).
- **Backfilled lots** are `source="backfill"`, `type="opening"` (`src/transactions.py:240,323,357`).
  Managed-account sales carry `txn_lot` in `lot_key` (`src/sales_confirm.py:249`), which the
  holding-period check joins through.
- **Import history year filter**: `broker_imports.date_from` / `date_to` (`src/stores/broker_repo.py:92-93`).
- **Investment-account definition**: `plan_accounts` (`src/broker_import.py:166-169`) admits any
  holdings account with "_" in its name, which is how Business_Checking gets in. Use the Role
  `Investment` from `ytd_account_setup` (`src/ytd_tracking.py:233`) instead; `src/cash_accounts.py:33`
  already treats a missing Role as cash.
- **Sales CSV**: `/api/sales/import/{preview,commit}` (`src/server/plan_routes.py:1110-1126`) and
  `preview_csv` / `commit_csv` in `src/sales_service.py` are used only by the ledger page and its own
  tests. Remove all of them.
- **Bank-account cleanup order**: if Business_Checking or Family_Checking are in
  `transaction_accounts`, unmanage them *before* voiding their opening CASH rows. Otherwise
  `materialize_managed` wipes their CASH holdings.

Claude's calls:

- **Managed accounts.** Today all 8 investment accounts are managed and the two checking accounts
  aren't. Nothing is migrated. When a new investment account gets log rows, it's turned on through
  the existing `set_managed` path (`src/transactions.py:484-503`) only when its log matches its
  holdings. If they don't match, the account appears under the existing Log health item ("Log differs
  from holdings for X") with a **Manage this account** action that shows the differences before it
  overwrites anything. Holdings are never rewritten silently.
- **Sale grouping key** = account + symbol + sale date, computed on the client. Two separate orders
  of the same symbol on the same day in one account show as one row, with their lots underneath.
  That's accepted: no schema migration.
- **Wash reviews** are stored in a new `wash_reviews` table keyed by that grouping key, instead of as
  a new `wash_flag` value. That way they survive Send back to queue and re-recording (the new rows get
  new `sale_id`s), and the `wash_flag` CHECK constraint (`src/stores/sales_repo.py:24,54`) needs no
  table rebuild.
- **The Sales KPIs show realized gains before carryforward** (`totals.st_gain` / `lt_gain`), labelled
  "realized". Tax year shows both the realized and the after-carryforward figures, so the two tabs
  agree on the realized line.

## Left to the builder

- Exact CSS. Reuse the existing `slSection`, `workspace-tabs` and button classes, and match the
  mockup's layout rather than its styling.
- Whether the sale grouping key is computed on the server or the client.
- How the status-line items expand into full sections.

## Calls I made (Claude), for Matt to check

- Taxable-only is shown but locked on for Tax year, because tax is taxable-only by definition.
- Option B details: Holdings' Activity and Import tabs each have their own Year (defaulting to the
  ledger's Year on a deep link). The 1099-B card sits in Tax year and opens itself after Jan 31.
  "Sales waiting for lots" stays on the ledger. Managed rows on Positions stay read-only, with an
  "Edit in Activity" link.
- The holding-period check is new and not in Matt's list. It's included because all 74 sales read as
  short-term.
- "Reinvest dividends default" moves to Plan Features rather than Year-End.
- "All years" on Tax year shows "pick a year" rather than a multi-year total.
- The term shows "Mixed" when one sale's lots differ in term.
- Sales CSV route: removed only if nothing else calls it, otherwise just unlinked.
- Wash: replacement shares are claimed oldest first across loss sales (W2). Later sales of an
  adjusted lot take the add-back pro rata (no share-level identification). "Reinvesting" means a
  reinvest row in the last 12 months. Basis add-backs are separate adjustment records, never edits
  to log rows.

## Suggested delivery order (for the plan)

1. Ledger cleanup and the defects (frontend-heavy; no data changes). The ledger becomes three tabs;
   the cash material moves to Year-End.
1b. Holdings tabs: mount Activity and Import on Holdings, add deep links and lot markers (the wash
   marker waits for phase 3). It can ship with 1 or right after it, but the log must never be
   missing from both pages between releases.
2. Wash rules W1–W3, the review table, cards and the Tax year line (`wash_sales.py`,
   `sales_tax_year.py`, a new store table).
3. Basis add-back W4–W5 through lots and holdings, plus the golden-master proof.
4. 1099-B wash tie.
5. The open-window warning.

Each phase can ship on its own. Phases 3 and 4 depend on 2.
