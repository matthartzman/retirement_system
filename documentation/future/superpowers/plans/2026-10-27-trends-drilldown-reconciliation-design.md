# Financial Trends — reconciliation by account, holdings drill-down, and spending transactions (design)

Date: 2026-10-27
Status: approved (user, 2026-10-27); implementation in draft PRs #286 and #288 and a third for (e)

Five requests on the Financial Trends reporter (`financial_trends_reporter/`), one design:

| # | Request | Where |
|---|---|---|
| a | Reconciliation warning points to the planner's Investment Holdings page | Live Snapshot |
| b | Say which part of the holdings disagrees with Monarch | Live Snapshot |
| c | Drill below a ticker: ticker → account → lot | Live Snapshot |
| d | Pin/Unpin on the spending breakdown panels doesn't work | Trends, Spending card |
| e | A fourth spending level: a merchant's transactions, in a third panel | Trends, Spending card |

## 1. Intent

The Live Snapshot already tells the user that the holdings file and Monarch disagree, but
not where, so the user has to open both and hunt. The Spending card stops at merchants, so
"what was that $1,400 at Costco?" still means leaving the page. The goal is that both
questions get answered in place, down to the row that explains them.

Success:
- When the reconciliation flags, the user can see which account is off, by how much, and
  the most likely reason, without leaving Financial Trends.
- Any ticker can be opened down to the individual lots that make it up, per account.
- Any merchant line, including "Other merchants" and "Refunds & credits", can be opened to
  the transactions behind it, and those transactions add up exactly to the line.
- Pin/Unpin keeps a panel open.

### Goals
- Account-level reconciliation of liquid holdings against Monarch, with hints.
- Four-level holdings table: asset class → ticker → account → lot.
- Transactions panel as the fourth spending level.
- Fix the pin bug.

### Non-goals
- Holding-by-holding comparison with Monarch. Monarch's holdings aren't imported (only account
  balances), and the user chose account-level matching with hints (2026-10-27).
- A link from the warning into the Retirement Planner. The warning names the page; it stays a
  plain message in Financial Trends (user, 2026-10-27).
- Editing holdings, mappings or transactions from Financial Trends.
- Prior-year transactions in the transactions panel.

### Anti-goals (failure even if it "works")
- A transactions list that doesn't sum to the merchant line it was opened from.
- A hint that states a guess as a fact. Hints say "may", and show the numbers that prompted them.
- Any change to Spending Analysis totals in the planner from the shared-code refactor (§6.2).
- Trends view behaviour changing in any way other than d and e.

## 2. Decisions

From the user (2026-10-27):
1. (b) Account-level reconciliation with hints is enough.
2. (e) The transactions panel takes one third of the bottom panel: the bottom panel becomes
   three equal columns, categories | merchants | transactions.
3. (c) Drill path is asset class → ticker → account → lot, inside the existing tables.
4. (a) Keep the warning in Financial Trends; no link to the planner.
5. (d) ships first, as its own PR.

Designer's calls (the user may overrule any of these):
6. Delivery in three PRs: d; then a + b + c (all Live Snapshot); then e.
7. Lot rows reuse the table's existing 10 columns (§4.2). No new columns.
8. Transactions preview on merchant hover after a short pause, are cached, and pin on click,
   the same pattern as the two levels above.
9. A per-account flag needs both more than 1% and more than $100 apart, so small accounts
   don't flag on rounding.
10. The spending panel wiring moves out of the inline script in `index.html` into its own module,
    so it can be tested (§5.2).

## 3. Current state (verified 2026-10-27)

- Reconciliation compares two grand totals: every lot's value against the sum of every Monarch
  account of type Retirement, Investment or HSA (`live_snapshot.py` `compute`, `_monarch_sections`;
  `MONARCH_LIQUID_TYPES`, `RECONCILE_FLAG_PCT = 0.01`). When Monarch's latest balance is from an
  earlier day, the holdings side is backed off by today's move so like is compared with like.
- Warning text: `live_snapshot.js` `reconciliationHtml`. The current source reads "vs. imported
  balances"; the user saw "vs. Monarch" on screen, so the running app may be older than #280.
- Monarch account → holdings account mapping already exists: `inputs["accounts"]` (the latest log
  entry's `holdings.by_account`) has `account` (Monarch name), `role`, and
  `mapped_investment_account` (holdings account name). `_checking_net_flows` already uses it.
- `_positions` builds one row per lot with account, symbol, current, start, new_money, weighted,
  basis, day. `_summarize` rolls those into class rows with a `tickers` list; the lot detail is
  thrown away after that.
- The holdings table renders class rows with an expand button and hidden ticker rows
  (`liquidTable`). The same function draws the Asset class table and the Equity by sub-class table.
- Spending card panels: `#spendDock` holds `#detailPopup` (categories) and `#detailPopup2`
  (merchants), `flex: 1 1 0` each, `max-height: 36vh`, stacked under 700px wide. Wiring is the
  inline script in `frontend/index.html` around lines 525–624.
- Merchant lines come from `spending_tracker.spending_hierarchy_window` (`src/spending_tracker.py`,
  shared with the planner's Spending Analysis). Per category it keeps the top 5 merchants, rolls
  the rest of the positive ones into "Other merchants", and nets merchants whose refunds exceed their
  purchases into one "Refunds & credits" line.
- Pin bug, root cause: clicking Pin/Unpin in a panel's bar runs the dock click handler, which
  redraws that panel (`innerHTML`), removing the clicked button from the page. The click then
  reaches the page-wide "click outside closes everything" handler; `closest("#spendDock")` on a
  removed element is null, so it treats the click as outside and calls `hideAll()`. Clicking a
  category to pin it works because that row isn't redrawn.

## 4. Live Snapshot (a, b, c)

### 4.1 Reconciliation by account (a, b)

**Backend** (`live_snapshot.py`, pure, in `compute`):

- Group lots by holdings account. For each Monarch liquid-type account, find its holdings account
  through `mapped_investment_account`. Several Monarch accounts mapped to one holdings account are
  summed against it.
- Per matched account: holdings value (backed off by the account's own day move when Monarch is
  from an earlier day, same rule as the total), Monarch value, $ difference (holdings − Monarch),
  % difference (of Monarch), and `flag` (both > 1% and > $100).
- Two more groups, listed but not compared: Monarch liquid accounts with no mapping, and holdings
  accounts no Monarch account maps to. Their values still count in the totals as today.
- Mapping coverage, measured 2026-10-27 (counts only): 10 active Monarch accounts of a liquid type;
  8 have a mapping in the latest log entry (keyed by Monarch display name, which is what
  `monarch.by_account` uses); 2 Retirement accounts have none. The mapping's `role` is the planner's
  role ("Investment"), not Monarch's type, so Retirement and HSA accounts are covered. Unmapped
  accounts are shown rather than guessed at. No name matching (designer's call). The mapping comes
  from the latest log entry, so an account added since the last 5 pm job shows as unmapped until
  the next one.
- Back-off: each account's holdings value is backed off by the sum of its lots' `day` values,
  using exactly the rule the total uses, so the account rows plus the unmapped-holdings rows add up
  to the total's holdings value. The section ends with a footing line showing that sum. If Monarch's
  as-of date is earlier than the previous trading day, one note says so ("Monarch balances are from
  <date>; moves since then aren't backed out"). Accounts still compare and flag (designer's call).
- The existing total-level `reconciliation` object stays (the tests pin it) and gains an
  `accounts` list plus `unmapped_monarch` and `unmapped_holdings` lists.

**Hints**, computed for flagged accounts only. Each is shown only when its condition holds:
1. *Bought after Monarch's balance date.* Lots in the account with a purchase date strictly after
   Monarch's as-of date: count and value. Monarch can't include these yet. Lots bought on the as-of
   date itself are treated as included (designer's call).
2. *Old prices.* Symbols in the account that are priced from a fallback (`stale`).
3. *Matches one position.* A single lot, or a single symbol's total in that account, whose value is
   within 5% of the gap: name it ("the gap is close to 15 sh VTI bought 2026-10-20, $4,112").
4. *Direction.* Holdings higher than Monarch: "a sale or transfer out may not be entered yet."
   Holdings lower: "a purchase or transfer in may not be entered yet."

Hints are ordered 1–4 and each one shows its numbers.

**Frontend** (`live_snapshot.js`):

- The summary line keeps its form, with the new wording when flagged:
  "Holdings file $X vs. imported balances $Y (date): N% apart. Check the Investment Holdings page in
  the Retirement Planner for trades or transfers not yet entered."
- Under it, a collapsible "Reconciliation by account" section: one row per matched account
  (account, holdings, Monarch, $ difference, % difference), largest absolute $ difference first,
  flagged rows marked with an icon as well as colour, and their hints underneath. Then the two
  unmapped lists, if not empty, with one line explaining that unmapped accounts can't be compared.
- The section opens by default when any account is flagged and stays as the user leaves it across
  the 60-second refresh (same mechanism as the other `details` sections).

### 4.2 Drill-down to account and lot (c)

**Backend:** `_summarize(..., with_tickers=True)` gives each ticker an `accounts` list (one
`_summarize` row per account holding that ticker), and each account row a `lots` list. A lot row
has the same fields as other rows (start, new_money, current, share, day, day_pct, market_gain,
return_pct, share_of_gain, annualized_pct) plus `purchase_date`, `shares`, `purchase_price`,
`reinvested`. Share and share-of-gain stay relative to the whole liquid total at every level, as
they are now for tickers.

**Frontend:** `liquidTable` goes from two levels to four. Ticker rows get an expand button for their
accounts; account rows get one for their lots. Lot rows reuse the 10 columns; their label reads
"2024-03-15 · 120 sh @ $412.10" (plus "reinvested" when it is). Indentation shows depth.
Expanded state survives the 60-second refresh, keyed by the full path (class/ticker/account), so
the same ticker open under Equity and under a sub-class doesn't collide. Collapsing a level
collapses everything under it. Both tables (Asset class, Equity by sub-class) get the same
drill-down, since they share `liquidTable`.

The new keys are added alongside the existing ones; nothing existing is renamed or removed. If an
existing test compares a whole row, extend its expected value. Don't gate the payload.

Payload: the lot list now ships with every 60-second poll. Expected to be a few hundred rows, which
is fine. If it turns out large, the builder may trim lot rows to the fields above.

## 5. Spending card (d, e)

### 5.1 Pin fix (d)

The "click outside" handler ignores clicks whose target is no longer in the page
(`!e.target.isConnected`), in addition to clicks inside the chart or the panels. A regression test
covers clicking Pin, then Unpin, on both panels: the panels stay open and the state changes.

### 5.2 Wiring moves to a module

The panel logic (hover, pin, close, Escape, outside-click) moves from the inline script into
`financial_trends_reporter/frontend/spending_dock.js`, written like `live_snapshot.js`: pure helpers
exported for tests and an init function that takes `document`/`window`. That makes d testable and
gives e somewhere to live. Ideally this happens in the d PR. If that makes the d PR too big, d can
ship as the one-line fix plus a test, with the move done at the start of the e PR.

### 5.3 Transactions panel (e)

**Layout:** `#spendDock` gets a third panel, `#detailPopup3`. All three are `flex: 1 1 0`, so each
takes a third of the width, scrolls on its own, and keeps `max-height: 36vh`. Under 700px wide the
three stack, as the two do now. Empty text: "Hover a merchant for its transactions."

**Behaviour:** this follows the existing two levels.
- Hovering a merchant line in the merchants panel shows its transactions after about 200 ms
  (no request while the pointer is just passing over).
- Clicking a merchant pins it; Pin/Unpin/Close in the panel's bar work as in the other panels.
- Changing category clears the transactions panel; changing tracking type clears both.
- The Total row has no categories, so the fourth level is only reached from a tracking-type row,
  as now.
- Results are cached per (date range, type, group, category, merchant); changing the date range
  clears the cache.

**Content:** a list sorted newest first with columns Date, Account, Merchant, Amount, plus the
transaction's notes when present (one line, cut off with an ellipsis, full text on hover). Spending
is positive and refunds negative, the same sign as the merchant line. The panel ends with a Total
equal to the merchant line. The Merchant column matters for "Other merchants" and "Refunds &
credits", which cover several merchants.

**Endpoint:** `GET /api/spending/transactions?from=&to=&type=&group=&category=&merchant=`, with the
same date-range validation and error format as `/api/spending`, and cached the same way (by window
and the plan file's mtime).

**Backend:** the per-transaction loop in `spending_hierarchy_window` (date filter, transfer filter,
alias resolution, taxonomy lookup, Unmapped bucket, sign rule) moves into one helper that yields
each counted transaction with its (type, group, category, merchant, value).
`spending_hierarchy_window` and a new `spending_transactions_window` both use it, so the two can't
drift apart. To answer for "Other merchants" or "Refunds & credits", `spending_transactions_window`
repeats the same top-5 and negative-net split over the same window.

Matching follows the hierarchy exactly (designer's calls):
- Category is matched by label within (type, group), so two categories sharing a label merge, as
  they already do in the hierarchy.
- "Unmapped" and "(no merchant)" are ordinary keys.
- The top-5 ranking is the same shared code, not a copy, so ties break the same way.
- The panel Total is `round(sum of raw values, 2)`, which is what the hierarchy leaf already is.
  Individual rows show their own amounts.

**Invariant test:** for a fixture window, every leaf of the hierarchy equals the sum of the
transactions the new function returns for it, to the cent, including both synthetic lines, an
Unmapped category, and a window spanning two years.

## 6. Constraints

1. The existing tests are the interface contract: `tests/frontend/trends_reporter_live_snapshot.test.mjs`,
   `trends_reporter_spending_window.test.mjs`, `tests/test_live_snapshot_*`,
   `tests/test_spending_window_unit.py`, `tests/test_trends_spending_window_unit.py`. Extend them;
   don't loosen them.
2. `src/spending_tracker.py` is shared with the planner. The refactor must leave
   `spending_hierarchy_window` output byte-identical: run its existing tests and the planner's
   Spending Analysis tests before and after.
3. If the planner's golden masters touch spending, run `tools/regen_golden_master.py measure`
   before and after; never regenerate.
4. Adding `spending_dock.js` and a route: run `python tools/generate_system_diagram.py` and commit
   the diagram if it changes (CI checks freshness).
5. Accessibility as in the existing views: expand buttons with `aria-expanded`, flags carry an icon
   or text and not just colour, and the panels can be pinned from the keyboard (Enter/Space).

## 7. Left to the builder

- Exact names of new fields, functions and CSS classes.
- The hover delay (about 200 ms) and the exact indentation of the drill levels.
- Whether lot rows show cost basis in the label or in a tooltip, if the label gets too long.
- Test file layout for the new module and endpoint.

## 8. Delivery and expected cost

Check `/usage` as each PR completes and compare against these estimates. They are relative
(light / moderate / heavy against a 5-hour Pro session), not token counts.

| PR | Contents | Model / effort | Usage | Context driver |
|---|---|---|---|---|
| 1 | d: pin fix + test (+ move to `spending_dock.js`, §5.2) | Sonnet, medium | Light (moderate with the move) | ~100 lines of `index.html` inline script; one frontend test file |
| 2a | b + c backend: per-account reconciliation, hints, account/lot rows in `compute` | Opus, high | Moderate | `live_snapshot.py` (677 lines, readable in parts); compute unit tests |
| 2b | a + b + c frontend: wording, by-account section, four-level table | Sonnet, high | Moderate | `live_snapshot.js` (235 lines); its test file |
| 3a | e backend: shared helper, `spending_transactions_window`, endpoint, invariant test | Opus, high | **Moderate–heavy** | `spending_tracker.py` is 2,047 lines; shared with the planner |
| 3b | e frontend: third panel, hover/pin, fetch + cache | Sonnet, medium | Moderate | `spending_dock.js`, `index.html` CSS, `charts.js` popup helpers (grep, don't read whole) |

Likely to be expensive, and how to keep them small:
- **3a**: don't read `spending_tracker.py` whole. Grep `spending_hierarchy_window`,
  `_resolve_alias`, `load_transactions_extended`, `_shared_ytd_class`, and read only those
  regions. Run the planner tests that touch spending by name rather than the whole suite.
- **Test loops**: use `pytest -m "not slow"` and the named test files above; run the full
  `pytest` once per PR, before opening it.
- **Golden masters (constraint 3)**: `measure` only. A diff means stop and investigate; don't loop.
