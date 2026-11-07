# Standard cash and credit-card balances, and Art shown apart from Start-up — design and plan

Status: approved

Date: 2026-11-07. Requests and decisions are the user's, from chat the same day (section 1); the rest are marked
as the designer's calls.

## 1. Requests and decisions

**A. Checking and credit cards need stored balances, not today's value held flat.** Today the forecast keeps the
checking accounts at today's balance (Business $10,561 + Family $76,288 = $86,849) and the credit-card
liabilities at today's balance ($6,571) for every year. The user's decision:

- The plan stores, for **all checking accounts together** and for **all credit cards together**, a *standard
  balance* used for every year **except the current one**. The current year keeps today's actual balances.
- Each of the two has its **own annual percent change**, applied year over year (they can differ, and can be
  negative).

**B. Art is shown apart from Start-up.** *Start-up Equity* and *Art & Collectibles* (Masterworks) become separate
lines, but both stay inside **Other Assets** for net worth (the existing Σ Other). The user also wants Masterworks'
**sale date set to 2035** (a data change to the live plan, section 5).

Why: on 2026-11-06 the Net Worth line "Startup Equity" showed $74,700 for 2026 = Start-up Equity $66,600 plus
Masterworks $8,100, and $5,314 (Masterworks only) after the 2030 start-up sale, which read as the start-up still
being held.

## 2. Goals, non-goals, anti-goals

**Goals**

- Four new inputs (section 3.1) the user can set in the UI.
- Forecast years after the current one use the standard balances grown by their own percent; the money moves
  between the accounts and the investments, so net worth only changes through taxes and returns.
- Net Worth, balance-sheet and tax-reporter lines show Start-up and Art separately; totals are unchanged.

**Non-goals**

- Per-account standard balances (the inputs are totals; accounts are scaled in proportion).
- A seasonal or monthly cash pattern, or the Monarch balance history (a possible later source for the standard
  values).
- Credit-card interest and payment behavior (the existing liability path is untouched).

**Anti-goals**

- A plan with all four new inputs blank changes any number. Blank = today's behavior (balances held flat).
- Money created or lost by a change in the standard balance: net worth moves only by the plan's own returns and taxes.
- The Net Worth sheet no longer footing to TOTAL NW.

## 3. Design

### 3.1 Inputs (section "Cashflow", subsection "Cash Tracking", beside `cash_pair_status_tax`)

| Label | Units | Blank means |
|---|---|---|
| `checking_standard_balance` | USD | hold today's balance (no change) |
| `checking_annual_change_pct` | pct | 0% |
| `credit_card_standard_balance` | USD | hold today's balance (no change) |
| `credit_card_annual_change_pct` | pct | 0% |

New plans get the rows from `src/server/app_core.py` backfill (as the Note 8949 rows do); existing plans get them
blank. Help text says what "standard" means and that the current year keeps today's balances.

### 3.2 Balances by year (designer's call on the base year)

- **Plan start year:** today's actual balances: the sum of the `cash`-tax accounts, and the sum of the
  `credit_card` liabilities.
- **First year after plan start:** the standard balance.
- **Each later year:** the previous year's balance × (1 + that item's percent).
- A blank standard balance holds today's balance, and the percent then applies to it from the first year after plan
  start on.
- **Spread over accounts and cards:** each account (card) keeps its share of today's total. A card with a payoff
  date is left out of the scaling and the total (it is paying itself off).

### 3.3 Where the money goes (designer's call)

A change in a year's balance is a transfer, so no money is created or lost:

| Change | What the engine does |
|---|---|
| Checking falls by D | D is deposited into the first taxable account (as the Other Asset sale proceeds are). |
| Checking rises by D | D is added to the year's cash need, funded by the usual withdrawal order. |
| Credit-card balance rises by D | D is deposited into the first taxable account (spending moves onto the card). |
| Credit-card balance falls by D | D is added to the year's cash need (the card is paid down). |

Each year's transfer is shown as one cash-flow line, "Working balance change", and as a deposit tagged
"Working balance change" on the receiving account.

### 3.4 Art apart from Start-up

- `other_asset_tax` gains `is_collectible(item)`: type Art or Collectible.
- `other_asset_sale_tax.held_value_split(c, year)` returns (start-up and other, art and collectibles).
- Row fields: `startup_val` = start-up and other only; new `art_val` = art and collectibles. Net worth still adds
  both (the engine's `other_nw` is unchanged).
- Net Worth sheet: one new column "Art & Collectibles" before Σ Other, shown only when the plan has art (as
  Rental Equity is). Balance-sheet and tax-reporter Other Assets lists get an "Art & Collectibles" line.

## 4. Implementation plan

Check `/usage` after each phase against these. Relative, not token counts.

| Phase | Work | Model / effort | Usage vs a 5-hour Pro session | What drives context |
|---|---|---|---|---|
| 1 Art split | helper, `art_val` row field, NW sheet column, two report lines, unit tests, workbook footing test | Sonnet / medium | Light–moderate | `sheets_projection_net_worth.py` by region (column map at lines 44–72); never read `deterministic_engine.py` whole |
| 2 Balance inputs and engine | rows + backfill + parser, `projection_stages/working_balances.py`, engine hook, cash-flow line, tests incl. blank = unchanged | Opus / high | **Heavy** | `deterministic_engine.py` (read only the hook region); golden measure |
| 3 Verify and live plan | fast gates, golden measure + phase golden, set Masterworks sale date 2035 in the live plan, rerun, screenshot | Sonnet / low | Moderate | test-loop time; run pytest in the background into a log |

**Flagged as expensive:** Phase 2's engine hook (the transfer must not double count with the withdrawal cascade),
and golden drift (expect none, since blank inputs change nothing; a delta is a bug, never re-record).

Phases run in order: 2 needs nothing from 1, but both touch the Net Worth sheet's rows, so one session does both.

### Tasks (test first)

1. **Art split.** Failing tests: Masterworks-like item goes to `art_val` and a start-up item to `startup_val`
   each year; `startup_val + art_val` equals the old `startup_val`; total NW unchanged; Net Worth sheet columns
   foot with and without art. Then implement 3.4.
2. **Inputs.** Failing tests for the four rows (added for new plans, backfilled blank, parsed to `c`), then
   implement.
3. **Balances by year.** Failing tests: plan-start year equals today's totals; year +1 equals the standard
   balance; later years compound at each item's own percent; blank inputs give flat balances; shares are
   preserved per account.
4. **Transfers.** Failing tests for the four rows of 3.3: net worth does not move by the transfer (checking −D,
   taxable +D); cash need rises by D when checking rises; cash-flow lines sum to total.
5. **Gates and live data.** `tools/regen_golden_master.py measure` (zero delta), `pytest
   tests/test_phase_golden_equality_regression.py`, `python tools/fast_gates.py`, diagram regen. Set
   Masterworks' `sell_date` to 12/31/2035 through the store; rerun and print `art_val`, `startup_val`, checking
   and card balances for 2026–2037.

## 5. Decisions after review

- **Live-plan values (user, 2026-11-07):** standard checking balance **$10,000** and standard credit-card balance
  **$10,000** (so they net out), annual change **0%** for each. The build enters them into the live plan through
  the store, after the code lands; the code default stays blank.
- The base-year call in 3.2 and the transfer destination in 3.3 stand as designed (the user approved the design).
