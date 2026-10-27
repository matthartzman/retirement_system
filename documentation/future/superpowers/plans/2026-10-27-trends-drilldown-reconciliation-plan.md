# Trends: Reconciliation by Account, Holdings Drill-down, Spending Transactions — Implementation Plan

Status: approved (user, 2026-10-27); being implemented in draft PRs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix spending-panel pinning, then add account-level reconciliation with hints, a
class → ticker → account → lot drill-down to the Live Snapshot, and a transactions panel as the
fourth spending level.

**Architecture:** All changes are in the Financial Trends reporter (`financial_trends_reporter/`)
plus one shared helper in `src/spending_tracker.py`. Backend stays pure and unit-tested (`compute`
in `live_snapshot.py`, a new window function in `spending_tracker.py`). Frontend follows the
`live_snapshot.js` pattern: pure HTML builders exported for node tests, and an `init*` function
that takes `doc`/`win`. Three PRs: PR 1 = Task 1; PR 2 = Tasks 2–5; PR 3 = Tasks 6–8.

**Tech Stack:** Python 3.12, Flask, pytest; vanilla ES modules, `node --test`.

**Spec:** `documentation/future/superpowers/plans/2026-10-27-trends-drilldown-reconciliation-design.md`

## Global Constraints

- Existing tests are the contract: extend expected values for added keys, never loosen or delete assertions.
- `spending_hierarchy_window` output must stay byte-identical (it is shared with the planner's Spending Analysis).
- Never regenerate golden masters; `python tools/regen_golden_master.py measure` only, and a delta means stop.
- Per-account flag: `abs(delta_pct) > 0.01` **and** `abs(delta) > 100.0`.
- Flags and hints show an icon or text, not colour alone; expand buttons carry `aria-expanded`.
- Warning copy (exact): `Check the Investment Holdings page in the Retirement Planner for trades or transfers not yet entered.`
- Transactions panel empty text (exact): `Hover a merchant for its transactions.`
- Hover delay before a transactions request: 200 ms.
- Don't read `src/spending_tracker.py` (2,047 lines) or `frontend/js/dashboard*.js` whole. Grep, then read with offset and limit.
- After adding files or routes, run `python tools/generate_system_diagram.py`. Commit `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` only if it changed.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **A ticker held in several accounts, open in both tables at once.** Expand state must not collide across the Asset class and Equity sub-class tables. Test owner: Task 5.
2. **A Monarch account mapped to a holdings account with no liquid lots left** (everything sold). The row shows holdings $0 and flags, with no division error. Test owner: Task 3.
3. **A transactions request for a merchant line that no longer exists** (data updated underneath). The endpoint returns an empty list, and the panel says "No transactions found." rather than erroring. Test owners: Tasks 7 and 8.
4. **Moving the mouse quickly across merchants.** Responses that arrive out of order must not overwrite the panel for the current merchant. Test owner: Task 8.
5. **Changing the date range while a transactions panel is pinned.** The cache clears and the panel empties. Test owner: Task 8.

## Cost guide (per CLAUDE.md)

Relative to a 5-hour Pro session. Check `/usage` after each task against these.

| Task | Model / effort | Usage | What drives context |
|---|---|---|---|
| 1 | Sonnet / medium | Light–moderate | ~100 lines of `index.html` inline script; one new test file |
| 2 | Opus / high | Moderate | `live_snapshot.py` lines 266–560; compute tests |
| 3 | Opus / high | Moderate | same region; hint arithmetic |
| 4 | Sonnet / medium | Light | `live_snapshot.js` (235 lines) |
| 5 | Sonnet / high | Moderate | `liquidTable` rewrite and its tests |
| 6 | Opus / high | **Moderate–heavy** | `spending_tracker.py` lines ~1420–1480 only; planner spending tests |
| 7 | Sonnet / medium | Light | `main.py` lines 175–210 |
| 8 | Sonnet / medium | Moderate | `spending_dock.js`, `charts.js` popup helpers (grep), `index.html` CSS |

Expensive spots: Task 6 (shared code, so keep it to the named region and named tests) and full
`pytest` runs (once per PR, before opening it; otherwise `pytest -m "not slow"` and named files).

---

## PR 1 — Pin fix

### Task 1: Move the spending panels to `spending_dock.js` and fix Pin/Unpin

**Files:**
- Create: `financial_trends_reporter/frontend/spending_dock.js`
- Modify: `financial_trends_reporter/frontend/index.html` (inline script, lines ~525–624: move this logic out; leave an import and an init call)
- Test: `tests/frontend/trends_reporter_spending_dock.test.mjs`

**Interfaces:**
- Produces:
  - `isOutsideClick(target) -> boolean`. False when `target.isConnected === false` (a button removed by a re-render). False when `target.closest("#chartCategories, #spendDock")` is truthy. True otherwise.
  - `initSpendingDock({ doc, win, getModel }) -> { hideAll(): void }`. `getModel()` returns the current `categoryModel`, or null.
  - `index.html` calls `initSpendingDock({ doc: document, win: window, getModel: () => categoryModel })`.

- [ ] **Step 1: Write the failing tests**

```js
import { isOutsideClick } from "../../financial_trends_reporter/frontend/spending_dock.js";
const el = (connected, inside) => ({ isConnected: connected, closest: () => (inside ? {} : null) });
test("a click on a button removed by re-render is not an outside click", () => {
  assert.equal(isOutsideClick(el(false, false)), false);
});
test("a click inside the chart or dock is not outside", () => { assert.equal(isOutsideClick(el(true, true)), false); });
test("a click elsewhere is outside", () => { assert.equal(isOutsideClick(el(true, false)), true); });
test("index.html wires the dock from the module", () => {
  assert.match(html, /import \{[^}]*initSpendingDock[^}]*\} from "\.\/spending_dock\.js"/);
  assert.ok(!html.includes("function pinRow("));   // moved, not duplicated
});
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test tests/frontend/trends_reporter_spending_dock.test.mjs`
Expected: FAIL (the module doesn't exist).

- [ ] **Step 3: Implement `spending_dock.js`**

Move `popRow`/`popCat`/`rowPinned`/`catPinned`, `dockBar`, `showRow`, `showMerchants`, `hideAll` and
all their listeners into `initSpendingDock`, unchanged except:
- the page-wide click listener calls `isOutsideClick(e.target)`;
- `modelRow` reads `getModel()`.

The Escape handler and `fitVertically` move too, if nothing else uses them; grep `index.html` to check.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `npm test`
Expected: all pass, including the existing `trends_reporter_spending_window.test.mjs` text assertions on `index.html`. If one of those pins inline-script text that moved, point it at `spending_dock.js` with the same assertion.

- [ ] **Step 5: Check it in the browser**

Start the Trends app and open the Spending card. Hover a row label, then click **Pin** on the
categories panel: the panel stays open, and its bar reads "Pinned". Click **Unpin**: it stays open,
reads "Preview", and hover replaces it again. Repeat on the merchants panel. Escape and a click
elsewhere still close both.

- [ ] **Step 6: Commit; then open the draft PR**

```bash
git add financial_trends_reporter/frontend/spending_dock.js financial_trends_reporter/frontend/index.html tests/frontend/trends_reporter_spending_dock.test.mjs
git commit -m "Trends spending panels: Pin/Unpin no longer closes the panels; wiring moved to spending_dock.js"
```

---

## PR 2 — Live Snapshot (a, b, c)

Shared fixture: `tests/test_live_snapshot_compute_unit.py` (`LOTS`, `QUOTES`, `ACCOUNTS`, `MONARCH`,
`_compute`, `TODAY = 2026-10-27`, Monarch as of 2026-10-26). Hand-worked numbers for that fixture:

| Holdings account | Value now | Day move | Value at Monarch's date | Monarch | Difference |
|---|---|---|---|---|---|
| Member_1_IRA (ITOT 13,000; IXUS 13,200) | 26,200 | +50 | 26,150 | 26,000 ("IRA - Matt") | +150 (0.58%, not flagged) |
| Member_1_Trust (AVUV 5,000; CASH 1,000) | 6,000 | +50 | 5,950 | 6,000 ("Trust - Matt") | −50 (not flagged) |

The two rows sum to 32,100, which equals the existing total-level `holdings_value`.

### Task 2: Lot fields and account/lot rows in `compute`

**Files:**
- Modify: `financial_trends_reporter/live_snapshot.py` (`_positions` ~327–375, `_summarize` ~378–397)
- Test: `tests/test_live_snapshot_compute_unit.py`

**Interfaces:**
- Produces:
  - Each `_positions` row also carries `purchase_date: str | None` (ISO), `shares: float`, `purchase_price: float` and `reinvested: bool`.
  - Every ticker row in `by_class[*].tickers` and `by_equity_subclass[*].tickers` gains `accounts: list[AccountRow]`, largest current value first.
  - `AccountRow` is the `_summarize` fields with `name` = holdings account, plus `lots: list[LotRow]`, sorted by purchase date, newest first.
  - `LotRow` is the `_summarize` fields of that one lot, plus `purchase_date`, `shares`, `purchase_price` and `reinvested`.
  - `share` and `share_of_gain` are relative to the whole liquid total at every level.

- [ ] **Step 1: Write the failing tests**

```python
def test_ticker_drills_to_account_and_lot():
    itot = _row(_row(_compute()["liquid"]["by_class"], "Equity")["tickers"], "ITOT")
    (acct,) = itot["accounts"]
    assert acct["name"] == "Member_1_IRA" and acct["current"] == pytest.approx(13000)
    (lot,) = acct["lots"]
    assert lot["purchase_date"] == "2025-06-01" and lot["shares"] == 100 and lot["purchase_price"] == 100
    assert lot["start"] == pytest.approx(12000) and lot["current"] == pytest.approx(13000)
    assert lot["reinvested"] is False and lot["share"] == pytest.approx(13000 / 32200)

def test_same_ticker_in_two_accounts_splits():
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "ITOT", "purchase_date": "2026-10-01", "shares": "10", "purchase_price": "125"}]
    itot = _row(_row(_compute(lots=lots)["liquid"]["by_class"], "Equity")["tickers"], "ITOT")
    assert [a["name"] for a in itot["accounts"]] == ["Member_1_IRA", "Member_1_Trust"]
    assert itot["accounts"][1]["lots"][0]["new_money"] == pytest.approx(1250)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_live_snapshot_compute_unit.py -k "drills or two_accounts" -v`
Expected: FAIL with `KeyError: 'accounts'`.

- [ ] **Step 3: Implement**

Extend `_positions` with the four fields. In `_summarize`, when building a ticker row, group its
members by `account` into `AccountRow`s. Each member is one lot, so each becomes a `LotRow`. Give
`_summarize` a `level` parameter, or add a separate helper; your choice. The existing keys must
not change.

- [ ] **Step 4: Run the whole compute and build test files**

Run: `pytest tests/test_live_snapshot_compute_unit.py tests/test_live_snapshot_build_unit.py tests/test_live_snapshot_unit.py -v`
Expected: all PASS. If an existing test compares a whole row, extend its expected value.

- [ ] **Step 5: Commit**

```bash
git add financial_trends_reporter/live_snapshot.py tests/test_live_snapshot_compute_unit.py
git commit -m "Live Snapshot: ticker rows carry per-account and per-lot rows"
```

### Task 3: Reconciliation by account, with hints

**Files:**
- Modify: `financial_trends_reporter/live_snapshot.py` (constants ~266–270; `compute` ~509–518)
- Test: `tests/test_live_snapshot_compute_unit.py`

**Interfaces:**
- Consumes: the `_positions` rows from Task 2 (`account`, `current`, `day`, `symbol`, `purchase_date`, `shares`); `previous_trading_day` (existing).
- Produces:
  - Constant: `RECONCILE_ACCOUNT_FLAG_USD = 100.0`.
  - `reconciliation` keeps every existing key, and gains:
    - `accounts: list[{holdings_account: str, monarch_accounts: list[str], holdings_value: float, monarch_value: float, delta: float, delta_pct: float | None, flag: bool, hints: list[Hint]}]`, sorted by `abs(delta)`, largest first.
    - `unmapped_monarch: list[{name: str, value: float}]`
    - `unmapped_holdings: list[{account: str, value: float}]`
    - `footing: float`, the sum of the account rows' and `unmapped_holdings`' `holdings_value`; it equals `holdings_value`.
    - `monarch_stale: bool`, true when `monarch_as_of < previous_trading_day(today)`.
  - `Hint` is one of:
    - `{kind: "after_balance_date", count: int, value: float}`, for lots with `purchase_date > monarch_as_of`;
    - `{kind: "stale_prices", symbols: list[str]}`;
    - `{kind: "matches_position", symbol: str, shares: float, purchase_date: str | None, value: float}`, where `value` is the lot's or symbol's value at Monarch's date and is within 5% of `abs(delta)`. Name the closest single lot, otherwise the closest symbol total in the account. At most one.
    - `{kind: "direction", higher: "holdings" | "monarch"}`.

    Hints appear only when `flag`, in the order listed.
  - Value at Monarch's date: `current - day` for each lot when Monarch is from an earlier day, the same rule as the total.

- [ ] **Step 1: Write the failing tests**

```python
def test_accounts_reconcile_and_foot_to_total():
    rec = _compute()["reconciliation"]
    ira, trust = rec["accounts"]                      # |150| before |-50|
    assert (ira["holdings_account"], ira["monarch_accounts"]) == ("Member_1_IRA", ["IRA - Matt"])
    assert ira["holdings_value"] == pytest.approx(26150) and ira["delta"] == pytest.approx(150)
    assert ira["flag"] is False and ira["hints"] == []
    assert trust["delta"] == pytest.approx(-50)
    assert rec["footing"] == pytest.approx(rec["holdings_value"]) == pytest.approx(32100)
    assert rec["unmapped_monarch"] == [] and rec["unmapped_holdings"] == [] and rec["monarch_stale"] is False

def test_flag_needs_both_one_percent_and_100_dollars():
    small = {**MONARCH, "by_account": [dict(a, value=5850.0) if a["account"] == "Trust - Matt" else a for a in MONARCH["by_account"]]}
    trust = _row_by(_compute(monarch=small)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["delta"] == pytest.approx(100) and trust["flag"] is False          # 1.7% but not > $100

def test_matches_position_and_direction_hints():
    m = {**MONARCH, "by_account": [dict(a, value=12950.0) if a["account"] == "IRA - Matt" else a for a in MONARCH["by_account"]]}
    ira = _row_by(_compute(monarch=m)["reconciliation"]["accounts"], "Member_1_IRA")
    assert ira["flag"] is True
    assert ira["hints"] == [
        {"kind": "matches_position", "symbol": "IXUS", "shares": 200, "purchase_date": "2025-06-01", "value": pytest.approx(13250)},
        {"kind": "direction", "higher": "holdings"}]

def test_after_balance_date_and_stale_price_hints():
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "AVUV", "purchase_date": "2026-10-27", "shares": "20", "purchase_price": "100"}]
    quotes = {k: v for k, v in QUOTES.items() if k != "AVUV"}                      # AVUV falls back to baseline
    trust = _row_by(_compute(lots=lots, quotes=quotes)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["flag"] is True
    assert trust["hints"][0] == {"kind": "after_balance_date", "count": 1, "value": pytest.approx(1800)}
    assert trust["hints"][1] == {"kind": "stale_prices", "symbols": ["AVUV"]}

def test_lot_bought_on_balance_date_counts_as_included():
    lots = LOTS + [{"account": "Member_1_Trust", "symbol": "AVUV", "purchase_date": "2026-10-26", "shares": "20", "purchase_price": "100"}]
    trust = _row_by(_compute(lots=lots)["reconciliation"]["accounts"], "Member_1_Trust")
    assert all(h["kind"] != "after_balance_date" for h in trust["hints"])

def test_mapped_account_with_no_lots_flags_at_zero():          # Review Focus 2
    lots = [l for l in LOTS if l["account"] != "Member_1_Trust"]
    trust = _row_by(_compute(lots=lots)["reconciliation"]["accounts"], "Member_1_Trust")
    assert trust["holdings_value"] == 0 and trust["delta"] == pytest.approx(-6000) and trust["flag"] is True

def test_unmapped_both_ways_and_two_monarch_accounts_to_one():
    accounts = ACCOUNTS + [{"account": "IRA 2 - Matt", "role": "Investment", "mapped_investment_account": "Member_1_IRA"}]
    monarch = {**MONARCH, "by_account": MONARCH["by_account"] + [
        {"account": "IRA 2 - Matt", "type": "Retirement", "value": 100.0},
        {"account": "Old 401k", "type": "Retirement", "value": 900.0}]}
    lots = LOTS + [{"account": "Member_2_Roth", "symbol": "ITOT", "purchase_date": "2025-06-01", "shares": "1", "purchase_price": "100"}]
    rec = _compute(accounts=accounts, monarch=monarch, lots=lots)["reconciliation"]
    ira = _row_by(rec["accounts"], "Member_1_IRA")
    assert ira["monarch_accounts"] == ["IRA - Matt", "IRA 2 - Matt"] and ira["monarch_value"] == pytest.approx(26100)
    assert rec["unmapped_monarch"] == [{"name": "Old 401k", "value": 900.0}]
    assert rec["unmapped_holdings"] == [{"account": "Member_2_Roth", "value": pytest.approx(129)}]
    assert rec["footing"] == pytest.approx(rec["holdings_value"])

def test_monarch_older_than_previous_session_is_noted():
    assert _compute(monarch={**MONARCH, "latest_date": "2026-10-22"})["reconciliation"]["monarch_stale"] is True
```

`_row_by(rows, account)` is a three-line test helper that matches on `holdings_account`.

> Check the hand arithmetic before trusting the pins:
> - **IXUS:** at Monarch's date it's worth 200 × 66.25 = 13,250. The gap is 26,150 − 12,950 = 13,200, which is within 5%.
> - **After the balance date:** 20 × the AVUV fallback price. With no quote, the price falls back to the 90 baseline, so the value is 1,800.
>
> If a number doesn't come out like this, fix the test's arithmetic, not the formula, and say so in the commit message.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `pytest tests/test_live_snapshot_compute_unit.py -k "reconcil or hint or flag_needs or balance_date or unmapped or no_lots or older" -v`
Expected: the new tests FAIL with `KeyError`; the existing reconciliation tests PASS.

- [ ] **Step 3: Implement the per-account reconciliation in `compute`**

Build `{holdings account → [Monarch names]}` from `accounts` rows whose `mapped_investment_account`
is set. Only Monarch rows of a `MONARCH_LIQUID_TYPES` type take part.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `pytest tests/test_live_snapshot_compute_unit.py tests/test_live_snapshot_build_unit.py tests/test_trends_reporter_live_snapshot_route_functional.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add financial_trends_reporter/live_snapshot.py tests/test_live_snapshot_compute_unit.py
git commit -m "Live Snapshot: reconcile holdings with Monarch account by account, with hints"
```

### Task 4: Warning wording and the "Reconciliation by account" section

**Files:**
- Modify: `financial_trends_reporter/frontend/live_snapshot.js` (`reconciliationHtml` ~102–107, `render` in `initLiveView`)
- Test: `tests/frontend/trends_reporter_live_snapshot.test.mjs`

**Interfaces:**
- Consumes: the `reconciliation` shape from Task 3.
- Produces:
  - `hintText(hint) -> string`, exported, with this exact copy:
    - `after_balance_date`: ``${count} lot(s) bought after Monarch's balance date (${fmtUsd(value)}). Monarch can't include them yet.``
    - `stale_prices`: ``Old prices for ${symbols.join(", ")}.``
    - `matches_position`: ``The gap is close to ${shares} sh ${symbol}${purchase_date ? " bought " + purchase_date : ""} (${fmtUsd(value)}).``
    - `direction` with `higher: "holdings"`: `Holdings are higher: a sale or transfer out may not be entered yet.`
    - `direction` with `higher: "monarch"`: `Holdings are lower: a purchase or transfer in may not be entered yet.`
  - `reconciliationHtml(rec)` returns the summary line, then `<details class="live-section recon-accounts">`, with `open` when any account flags.

- [ ] **Step 1: Write the failing tests**

```js
test("warning names the Investment Holdings page", () => {
  const out = liveViewHtml({ ...DATA, reconciliation: { ...REC, delta_pct: 0.0102, flag: true } });
  assert.match(out, /Check the Investment Holdings page in the Retirement Planner for trades or transfers not yet entered\./);
  assert.ok(!out.includes("client_holdings"));
});
test("by-account section lists rows, opens when flagged, and shows hints", () => {
  const out = liveViewHtml({ ...DATA, reconciliation: REC_FLAGGED });
  assert.match(out, /<details class="live-section recon-accounts" open>/);
  assert.match(out, /Member_1_IRA/);
  assert.match(out, /⚠/);  // flag carries an icon, not just colour
  assert.match(out, /The gap is close to 200 sh IXUS bought 2025-06-01 \(\$13,250\)\./);
  assert.match(out, /Old 401k/);       // unmapped Monarch account listed
});
test("by-account section stays closed when nothing flags", () => {
  assert.match(liveViewHtml({ ...DATA, reconciliation: REC }), /<details class="live-section recon-accounts">/);
});
test("Monarch older than the previous session shows a note", () => {
  assert.match(liveViewHtml({ ...DATA, reconciliation: { ...REC, monarch_stale: true } }), /moves since then aren't backed out/);
});
```

`REC` and `REC_FLAGGED` are fixtures in the shape from Task 3. Copy them from the Task 3 test
outputs.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test tests/frontend/trends_reporter_live_snapshot.test.mjs`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement**

Table columns: Account | Holdings | Monarch | Difference | %.

Then the unmapped lists, with the line:
`Not linked to a holdings account, so not compared. Link them in the Retirement Planner.`

The stale note: ``Monarch balances are from ${monarch_as_of}; moves since then aren't backed out.``

End with a footing row.

The existing `render()` open/closed memory for `details.live-section` covers the 60 s refresh.
Check that it does: it indexes sections by position, so the new section must not shift the
indexes of the existing ones. If it would, key the sections by a `data-section` name instead.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `npm test`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add financial_trends_reporter/frontend/live_snapshot.js tests/frontend/trends_reporter_live_snapshot.test.mjs
git commit -m "Live Snapshot: reconciliation by account section; warning points to Investment Holdings"
```

### Task 5: Four-level holdings table

**Files:**
- Modify: `financial_trends_reporter/frontend/live_snapshot.js` (`liquidTable` ~88–100, `toggleGroup` / `expanded` in `initLiveView`)
- Modify: `financial_trends_reporter/frontend/index.html` (CSS for indentation of `.acct-row`, `.lot-row`; grep `ticker-row`)
- Test: `tests/frontend/trends_reporter_live_snapshot.test.mjs`

**Interfaces:**
- Consumes: `tickers[*].accounts[*].lots[*]` from Task 2.
- Produces:
  - Every row below class level has `data-path` and `data-parent` attributes. A path is `caption/class/symbol/account`, built from the table caption (`Asset class` or `Sub-class`).
  - Expand buttons carry `data-path`.
  - `expanded: Set<path>`. Collapsing a path hides every row whose `data-parent` starts with it.
  - `lotLabel(lot) -> string`, exported. Returns ``${purchase_date} · ${shares} sh @ ${fmtUsd2(purchase_price)}``, plus `" · reinvested"` when `reinvested`. Uses 2-decimal dollars.

- [ ] **Step 1: Write the failing tests**

```js
test("ticker → account → lot rows, hidden until expanded", () => {
  const out = liveViewHtml(DATA_WITH_LOTS);
  assert.match(out, /<button[^>]*aria-expanded="false"[^>]*data-path="Asset class\/Equity\/ITOT"/);
  assert.match(out, /<tr class="acct-row" data-path="Asset class\/Equity\/ITOT\/Member_1_IRA" data-parent="Asset class\/Equity\/ITOT" hidden>/);
  assert.match(out, /<tr class="lot-row" data-parent="Asset class\/Equity\/ITOT\/Member_1_IRA" hidden>/);
});
test("lot label", () => {
  assert.equal(lotLabel({ purchase_date: "2024-03-15", shares: 120, purchase_price: 412.1, reinvested: false }), "2024-03-15 · 120 sh @ $412.10");
  assert.match(lotLabel({ purchase_date: "2026-04-01", shares: 0.5, purchase_price: 50, reinvested: true }), / · reinvested$/);
});
test("same ticker in both tables gets distinct paths", () => {   // Review Focus 1
  const out = liveViewHtml(DATA_WITH_LOTS);
  assert.match(out, /data-path="Asset class\/Equity\/ITOT"/);
  assert.match(out, /data-path="Sub-class\/[^"]+\/ITOT"/);
});
```

The existing assertion `data-group="Equity"` / `class="ticker-row" data-parent="Equity"` pins the
current markup. Update it to the path form in this task. It's a deliberate interface change, so
note it in the commit message.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test tests/frontend/trends_reporter_live_snapshot.test.mjs`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement `liquidTable` and the toggle/expanded logic, plus indentation CSS**

- [ ] **Step 4: Run the tests, then check in the browser**

Run: `npm test`. Expected: all PASS.

Then open Live Snapshot and:
- expand Equity → ITOT → an account: the lots show;
- wait for a 60 s refresh: everything stays open;
- collapse Equity: everything under it hides.

- [ ] **Step 5: Commit; run the full `pytest` once; open the draft PR for PR 2**

```bash
git add financial_trends_reporter/frontend/live_snapshot.js financial_trends_reporter/frontend/index.html tests/frontend/trends_reporter_live_snapshot.test.mjs
git commit -m "Live Snapshot: drill holdings from ticker to account to lot"
```

---

## PR 3 — Spending transactions (e)

### Task 6: Shared spend iterator and `spending_transactions_window`

**Files:**
- Modify: `src/spending_tracker.py` (`spending_hierarchy_window` ~1420–1480 only)
- Test: `tests/test_spending_window_unit.py` (reuse its `_workspace(tmp_path, rows)` and `ROWS`)

**Interfaces:**
- Produces, in `src/spending_tracker.py`:
  - `_iter_window_spend(r, start: date, end: date) -> Iterator[tuple[str, str, str, str, float, dict]]`. Yields `(tracking_type, group, category, merchant, value, txn)` for every transaction the hierarchy counts. This is the body of the current loop, unchanged.
  - `_merchant_lines(merchants: dict[str, float], n: int) -> dict[str, str]`. Maps each merchant to the line it appears on: itself, `"Other merchants"`, or `"Refunds & credits"`. Merchants with `abs(v) <= 0.005` are absent. The hierarchy's top-`n` ranking moves here, so the two callers share it.
  - `spending_transactions_window(root, start: date, end: date, tracking_type: str, group: str, category: str, merchant: str, merchants_per_category: int = 5) -> dict`. Returns `{"transactions": [{"date": iso, "account", "merchant", "amount": round(value, 2), "notes"}], "total": round(sum of raw values, 2)}`, newest first. Returns an empty list and total 0.0 when nothing matches.
- `spending_hierarchy_window` is rewritten on top of both helpers; its output is unchanged.

- [ ] **Step 1: Capture the before state**

Run: `pytest tests/test_spending_window_unit.py tests/test_trends_spending_window_unit.py -v` and `grep -rln "spending_hierarchy\|spending_summary" tests | head`. Then run the planner spending tests that grep finds.

Run: `python tools/regen_golden_master.py measure`, saving the output to a scratch file (`gm_before.txt`).

Expected: everything passes. Keep the measure output.

- [ ] **Step 2: Write the failing invariant test**

```python
def test_every_merchant_line_equals_its_transactions(tmp_path):
    base = _workspace(tmp_path, ROWS_INVARIANT)   # >5 merchants in one category, a net-refund merchant,
                                                  # an Unmapped category, a "(no merchant)" row, spanning Dec-Jan
    start, end = date(2025, 12, 1), date(2026, 1, 31)
    tree = spending_tracker.spending_hierarchy_window(base, start, end)
    seen = 0
    for tt, groups in tree.items():
        for grp, cats in groups.items():
            for cat, lines in cats.items():
                for line, amount in lines.items():
                    got = spending_tracker.spending_transactions_window(base, start, end, tt, grp, cat, line)
                    assert got["total"] == amount, (tt, grp, cat, line)
                    seen += 1
    assert {"Other merchants", "Refunds & credits", "(no merchant)"} <= {l for g in tree.values() for c in g.values() for ls in c.values() for l in ls}
    assert "Unmapped" in tree and seen >= 9

def test_transactions_sorted_newest_first_with_fields(tmp_path):
    got = spending_tracker.spending_transactions_window(_workspace(tmp_path, ROWS_INVARIANT), date(2025, 12, 1), date(2026, 1, 31),
                                                       *KNOWN_LINE)   # a (type, group, category, merchant) with >= 2 rows in the fixture
    dates = [t["date"] for t in got["transactions"]]
    assert len(dates) >= 2 and dates == sorted(dates, reverse=True)
    assert all(set(t) == {"date", "account", "merchant", "amount", "notes"} for t in got["transactions"])

def test_unknown_line_returns_empty(tmp_path):            # Review Focus 3
    got = spending_tracker.spending_transactions_window(_workspace(tmp_path, ROWS), date(2026,1,1), date(2026,12,31), "Core", "Food", "Groceries", "Nobody")
    assert got == {"transactions": [], "total": 0.0}
```

Build `ROWS_INVARIANT` in the same row format as `ROWS`.

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `pytest tests/test_spending_window_unit.py -k "transactions or every_merchant or unknown_line" -v`
Expected: FAIL with `AttributeError: ... spending_transactions_window`.

- [ ] **Step 4: Implement the two helpers and the new function; rewrite `spending_hierarchy_window` on them**

- [ ] **Step 5: Confirm the after state matches the before state**

Run: the same tests as Step 1, plus the new ones. Expected: all PASS.

Run: `python tools/regen_golden_master.py measure` again into `gm_after.txt` and diff the two files.
Expected: no differences. If there are any, stop and investigate. Do not regenerate.

- [ ] **Step 6: Commit**

```bash
git add src/spending_tracker.py tests/test_spending_window_unit.py
git commit -m "Spending: shared window iterator; transactions behind any hierarchy line"
```

### Task 7: `/api/spending/transactions`

**Files:**
- Modify: `financial_trends_reporter/main.py` (next to `/api/spending`, ~178–207)
- Test: `tests/test_trends_reporter_server_functional.py`

**Interfaces:**
- Consumes: `spending_tracker.spending_transactions_window` (Task 6) and `_parse_spending_window` (existing).
- Produces: `GET /api/spending/transactions?from=&to=&type=&group=&category=&merchant=`.
  - Returns 200 with the Task 6 dict.
  - Returns 400 `{"success": false, "error": "type, group, category and merchant are required"}` when any of those four is blank.
  - Uses the same 400 as `/api/spending` for a bad window, and the same 500 shape on an exception.
  - Cached in `spending_cache` under key `("txns", from, to, type, group, category, merchant, mtime)`.

- [ ] **Step 1: Write the failing tests**: a 200 with a `transactions` list, a 400 for a missing `merchant`, and a 200 with an empty list for an unknown merchant. Use the existing app fixture in that file. Monkeypatch `spending_tracker.spending_transactions_window` if the fixture has no transaction data.
- [ ] **Step 2: Run and confirm they fail**: `pytest tests/test_trends_reporter_server_functional.py -k transactions -v`. Expected: 404.
- [ ] **Step 3: Implement the route**
- [ ] **Step 4: Run and confirm they pass**: the same command. Expected: PASS.
- [ ] **Step 5: Run `python tools/generate_system_diagram.py`; stage the diagram if it changed. Commit.**

```bash
git add financial_trends_reporter/main.py tests/test_trends_reporter_server_functional.py
git commit -m "Trends: /api/spending/transactions endpoint"
```

### Task 8: Transactions panel

**Files:**
- Modify: `financial_trends_reporter/frontend/spending_dock.js` (from Task 1)
- Modify: `financial_trends_reporter/frontend/charts.js` (`detailPopupHtml` ~488; add the two helpers below)
- Modify: `financial_trends_reporter/frontend/index.html` (add `<div id="detailPopup3">` to `#spendDock`, its CSS and empty text; pass `getRange` to `initSpendingDock`)
- Test: `tests/frontend/trends_reporter_spending_dock.test.mjs`, `tests/frontend/trends_reporter_spending_window.test.mjs`

**Interfaces:**
- Consumes: the endpoint from Task 7; `latestOnly()` from `charts.js` (existing).
- Produces:
  - `detailPopupHtml(title, detail, maxLines, opts)`. With `opts.indexAttr = "merchant"`, each row gets `data-merchant="${i}"`. Existing calls are unchanged.
  - `transactionsUrl(range, { type, group, category, merchant }) -> string`. All parameters go through `encodeURIComponent`.
  - `transactionsPanelHtml(title, payload) -> string`. Columns are Date | Account | Merchant | Amount. Notes go on a second muted line, cut off with an ellipsis, with the full text in `title`. The panel ends with a Total row. An empty list shows `No transactions found.`
  - `initSpendingDock({ doc, win, getModel, getRange })`. `getRange()` returns `{from, to}`.
  - Inside the dock:
    - State: `merchantPinned`, plus a `Map` cache keyed by `transactionsUrl`.
    - `onRangeChange()` clears the cache and `#detailPopup3`; `index.html` calls it wherever the spending window reloads.
    - Changing category clears `#detailPopup3`.
- Behaviour:
  - Hovering a merchant row starts a 200 ms timer. Leaving the row before it fires cancels it.
  - A click pins the merchant immediately, and the panel bar's Pin/Unpin works as in the other two panels.
  - Only the latest request may draw (`latestOnly`).
- CSS: `#detailPopup3` joins the existing `#detailPopup, #detailPopup2` rules, so it gets `flex: 1 1 0` and `max-height: 36vh` and stacks under 700px. `#detailPopup3:empty::before { content: "Hover a merchant for its transactions."; }`.

- [ ] **Step 1: Write the failing tests**

```js
test("transactionsUrl encodes every part", () => {
  assert.equal(transactionsUrl({ from: "2026-01-01", to: "2026-10-27" }, { type: "Core", group: "Food & Drink", category: "Groceries", merchant: "Trader Joe's" }),
    "/api/spending/transactions?from=2026-01-01&to=2026-10-27&type=Core&group=Food%20%26%20Drink&category=Groceries&merchant=Trader%20Joe's");
});
test("transactions panel rows, notes and total", () => {
  const out = transactionsPanelHtml("Costco", { transactions: [{ date: "2026-10-02", account: "Visa", merchant: "Costco", amount: 1400, notes: "TV" }], total: 1400 });
  assert.match(out, /2026-10-02/); assert.match(out, /Visa/); assert.match(out, /title="TV"/); assert.match(out, /Total[\s\S]*\$1,400/);
});
test("empty panel text", () => { assert.match(transactionsPanelHtml("X", { transactions: [], total: 0 }), /No transactions found\./); });
test("merchant rows carry an index only when asked", () => {
  assert.match(detailPopupHtml("t", [["A", 1]], undefined, { indexAttr: "merchant" }), /data-merchant="0"/);
  assert.ok(!detailPopupHtml("t", [["A", 1]]).includes("data-merchant"));
});
test("index.html has the third panel and its empty text", () => {
  assert.match(html, /id="detailPopup3"/); assert.match(html, /Hover a merchant for its transactions\./);
});
```

In `trends_reporter_spending_dock.test.mjs`, drive `initSpendingDock` with a minimal fake
`doc`/`win`. Stub `win.fetch` with controllable promises and `win.setTimeout` with a manual clock.
Use the same element-stub style as Task 1 (`isConnected`, `closest`, `addEventListener`,
`innerHTML`). Cover:
- **Review Focus 4:** hover merchant A, then B, then resolve A's fetch after B's. The panel shows B.
- **Review Focus 5:** pin a merchant, then call `onRangeChange()`. The panel is empty and the next hover fetches again (the cache missed).
- **Review Focus 3:** a fetch that returns an empty list shows `No transactions found.`
- Passing over a merchant for less than 200 ms makes no fetch.

If faking the DOM grows past about 60 lines, move the decision logic into a pure reducer
(`dockReducer(state, event) -> {state, effects}`) and test that instead. This is your call;
keep the public interface above either way.

- [ ] **Step 2: Run and confirm they fail**: `npm test`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement the helpers in `charts.js`, the dock logic, and the `index.html` markup and CSS**
- [ ] **Step 4: Run and confirm they pass**: `npm test`. Expected: all PASS.
- [ ] **Step 5: Check in the browser**

Open the Spending card. Hover a type, then a category, then a merchant: after a beat the third
panel fills, its total matches the merchant line, and it scrolls on its own. Do the same for
"Other merchants" and "Refunds & credits". Pin and unpin the third panel. Change the time scope:
the third panel empties. Narrow the window below 700px: the three panels stack.

- [ ] **Step 6: Commit; run the full `pytest` and `npm test` once; open the draft PR for PR 3**

```bash
git add financial_trends_reporter/frontend/spending_dock.js financial_trends_reporter/frontend/charts.js financial_trends_reporter/frontend/index.html tests/frontend/trends_reporter_spending_dock.test.mjs tests/frontend/trends_reporter_spending_window.test.mjs
git commit -m "Trends spending: fourth level, a merchant's transactions in a third panel"
```
