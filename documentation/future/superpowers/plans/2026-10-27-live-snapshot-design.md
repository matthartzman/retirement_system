# Financial Trends — Live Snapshot view (design + implementation plan)

Date: 2026-10-27 · Status: design approved in chat, awaiting plan sign-off

## 1. Intent

Bring the user's hand-kept Excel "Net Worth" sheet into the Financial Trends
reporter as a second view that values liquid holdings at live (delayed) market
prices, shows today's and year-to-date movement by asset class, and rolls up
to an after-tax, after-debt net worth. A toggle switches between the existing
charts ("Trends") and the new view ("Live Snapshot").

Success: opening Live Snapshot during market hours answers "what am I worth
right now, what moved today, and how is the year going net of what I put in"
without opening Excel, and the numbers agree with the spreadsheet's to within
the differences this design deliberately introduces (§4.4).

### Goals
- Live liquid-asset valuation from `client_holdings.csv` shares × live price.
- Day $/% (vs previous close) and since-year-start figures per asset class and
  per equity sub-class, with ticker drill-down.
- Full balance-sheet roll-up: liquid + non-liquid − estimated tax − debt.
- Index strip (S&P 500, Dow, Nasdaq) with day %.
- A toggle on the Financial Trends page; Trends behaviour unchanged.

### Non-goals
- No trading, no order entry, no brokerage connections.
- No intraday history or intraday charts; the existing 5 pm snapshot job stays
  the only thing written to the log.
- No editing of non-liquid values in this view (it links to where they're edited).

### Anti-goals (failure even if it "works")
- Silent stale or wrong numbers: every figure must show its as-of time, and a
  stale price or a holdings file that disagrees with Monarch must be visible.
- Hammering price providers (multiple tabs, background tabs, after hours).
- Contributions presented as investment gains.

## 2. Decisions (user, 2026-10-27)

| Topic | Decision |
|---|---|
| Holdings source | `client_holdings.csv` shares × live price, **plus a Monarch reconciliation line** |
| Return method | **Net of contributions** — market gain separated from net flows; Modified Dietz return |
| Scope of v1 | **Full sheet** — liquid, non-liquid, estimated tax liability, debt, after-tax net worth |
| Refresh | **Every 60 s during market hours** while the view is visible; pause after hours/weekends; Refresh-now button |

### Calls made by Claude (override any of these)
- Toggle is a two-option segmented control "Trends | Live Snapshot" in the
  existing `#scopeBar`; the last choice is kept in `localStorage` (try/catch).
  The Time scope picker is hidden while Live Snapshot is shown.
- Baseline ("Start Value") = prior calendar year-end close (12/31). Fixed, not
  tied to the Time scope picker (v2 candidate).
- Groupings: (a) asset class — Equity, Fixed Income, Commodities, Cash;
  (b) equity sub-class — US Total, International, Small-Cap Value (and any other
  canonical class present). Each row expands to its tickers.
- Labels: "Contrib" → "Share of gain"; "% NLA" → "% of non-liquid";
  "% NA" → "% of net worth". Up/down shown with ▲/▼ as well as colour.
- Annualized return is compounded, `(1+r)^(365/days)−1`, and hidden for the first
  90 days of the year.
- Non-liquid, tax and debt sections are collapsed by default.
- Index symbols: `^GSPC`, `^DJI`, `^IXIC`.

## 3. Current state (what is reused)

| Need | Existing code |
|---|---|
| Quotes, provider chain, cache | `src/market_data.py` (`quotes()`, Yahoo chart/FMP/AV/Stooq/Nasdaq) |
| Shares | `input/client_holdings.csv` (account, symbol, purchase_date, shares, purchase_price, lot_type) |
| Symbol → asset class | `src/allocation_policy.canonical_asset_class()` + ETF reference data used by `sheets_allocation_helpers` |
| Non-liquid, mortgage | `trends_metrics._plan_assets_and_mortgage()`, `_other_asset_items_totals()`, `_net_worth_from_account_setup()` (annuity/pension) |
| Net flows | `ytd.ytd_summary(...)["investment_balance"]["daily_flows_by_account"]` (already in each snapshot as `investment_flows_daily`) |
| Monarch latest balances | `balance_series.snapshot_summary(balances_db)` |
| Price history | `portfolio_analytics.snapshot_prices` (writes snapshots), `tools/refresh_prices.py` |
| Server / page | `financial_trends_reporter/main.py` (`create_app`), `frontend/index.html`, `frontend/charts.js` |

## 4. Design

### 4.1 Data flow

```
Browser (Live Snapshot visible, tab focused, market open)
   │  every 60 s  GET /api/live-snapshot
   ▼
main.py route ──► live_snapshot.build(base_dir, balances_db, now)
                    ├─ holdings lots (client_holdings.csv)  ─┐
                    ├─ LiveQuoteCache (30 s TTL, one lock) ──┤─► per-symbol value, day Δ
                    │     └─ market_data.quote_details()     │
                    ├─ baseline prices (year-end, cached on disk forever)
                    ├─ YTD net flows (ytd summary, cached 10 min)
                    ├─ plan assets / mortgage / annuity (cached 10 min)
                    ├─ Monarch latest investment balance (reconciliation)
                    └─ tax estimate
                  ► JSON (§4.3)
```

### 4.2 New backend pieces

1. **`market_data.quote_details(symbols) -> {sym: {price, previous_close, as_of, source, delayed}}`**
   in `src/market_data.py`. Primary: Yahoo chart endpoint `meta.regularMarketPrice`,
   `meta.chartPreviousClose`/`previousClose`, `meta.regularMarketTime`. Fallback:
   existing `quote()` for price, previous close taken from the latest stored price
   snapshot dated before today. Never raises; a symbol without a price returns
   `price=None` and the caller marks it stale. Index symbols use the same path.
2. **`financial_trends_reporter/live_snapshot.py`** (new, target < 300 lines):
   - `LiveQuoteCache` — module-level, 30 s TTL, single lock so concurrent tabs share one fetch.
   - `market_status(now)` — open/closed/pre/post from NYSE hours (America/New_York,
     weekends; holidays from a small static list for the current year, v1).
   - `baseline_prices(year)` — year-end closes; looks in stored price snapshots first,
     then fetches Yahoo chart `range` history for the missing symbols once; persists to
     `financial_trends_reporter/data/baseline_prices_<year>.json`.
   - Lot valuation: shares × price per lot; lots with `purchase_date` after 12/31 have
     baseline value 0 (their cost enters via flows, see 4.4).
   - Grouping by canonical asset class and equity sub-class; tickers as children.
   - Tax estimate (4.5), non-liquid, debt, roll-ups.
   - `build(...)` returns the JSON in 4.3.
3. **Route `GET /api/live-snapshot`** in `main.py`, same origin check as the other
   `/api/*` routes. Optional `?refresh=1` bypasses the 30 s cache (Refresh-now button),
   rate-limited to once per 10 s server-side.

### 4.3 Response shape (abridged)

```json
{
  "as_of": "2026-10-27T15:18:04Z", "market": "open", "delayed_minutes": 15,
  "indices": [{"symbol":"^GSPC","label":"S&P 500","day_pct":0.0072}],
  "baseline_date": "2025-12-31", "year_fraction": 0.82,
  "liquid": {
    "start": 2493023, "current": 2786792, "day": 16090, "day_pct": 0.0058,
    "net_flows": 0, "market_gain": 293769, "return_pct": 0.1178, "annualized_pct": 0.145,
    "by_class": [{"name":"Equity","start":..,"current":..,"share":0.88,"day":..,"day_pct":..,
                  "market_gain":..,"return_pct":..,"share_of_gain":..,"annualized_pct":..,
                  "tickers":[{"symbol":"ITOT", "...": "..."}]}],
    "by_equity_subclass": [ ... ],
    "stale_symbols": [], "unclassified_symbols": []
  },
  "reconciliation": {"holdings_value": 2786792, "monarch_value": 2775100, "monarch_as_of": "2026-10-26", "delta_pct": 0.0042, "flag": false},
  "non_liquid": {"rows":[{"name":"Annuity/Pension","kind":"Fixed Income","value":..,"source":"account setup","as_of":".."}], "total": ..},
  "tax": {"pre_tax_balance":..,"pre_tax_rate":..,"unrealized_ltcg":..,"ltcg_rate":..,"total": -754075},
  "debt": {"rows":[{"name":"Mortgage","value":..},{"name":"Credit cards","value":..}], "total": ..},
  "totals": {"net_assets": .., "after_tax_net_worth": .., "by_kind": {"Equity":..,"Fixed Income":..}}
}
```

### 4.4 Return method (net of contributions)

**Revised in step 3 (2026-10-27).** The first approach — 12/31 statement balances plus the
checking flows ledger — gave −22% on real data: about $1.2M moved from the IRAs into the
annuities this year without passing through checking, so the ledger cannot see it. Returns are
now Modified Dietz **over the current lots**, at every level (total, class, ticker):

- A lot held at 12/31 contributes `shares × 12/31 close` to `start`.
- A lot bought since is `new_money = shares × purchase price` on its purchase date, weighted
  `w = (today − purchase date) / (today − 12/31)`.
- A reinvested-dividend lot (`lot_type` starting "reinvest") is neither: all of it is gain.
- `market_gain = current − start − new_money`; `return_pct = market_gain / (start + Σ new_money × w)`.
- Robust to trades and transfers between accounts; blind to gains on lots sold during the year
  (they leave the holdings table). Lots re-dated by a transfer count as bought on the new date.
- `checking_net_flows` (from the flows ledger) is shown for information only.
- Displayed columns: Start (12/31) · Bought since · Current · Share · Day $ · Day % ·
  Market gain · Return % · Share of gain · Annualized.
- Known, intended difference from the spreadsheet: its Total $ includes contributions.

### 4.5 Estimated tax liability

- Pre-tax holdings accounts (`src.core` account-type inference): balance × pre-tax rate.
  The plan has no such rate, so it defaults to 25% (`live_snapshot_settings.json` in the
  reporter's data folder overrides it). Annuities and pension are not taxed in v1.
- Taxable accounts: Σ max(0, shares × price − shares × purchase_price) × LTCG rate from
  the plan's Rebalancing › Tax-aware Trades `ltcg_rate` (default 15%).
- Non-liquid, checking and debt rows come from the latest Monarch balances by account type
  (Annuity/Pension and notes → Fixed Income, Real estate, other → Alternatives; Loan and
  Credit card → debt; Cash → checking). Holdings in `*_Checking` accounts are excluded from
  liquid so checking is not counted twice.
- Roth/HSA: 0. Shown as one line with a hover breakdown and "estimate" label.

### 4.6 Front end

- `index.html`: segmented toggle in `#scopeBar`; new `<section id="liveView" hidden>`;
  the existing `.grid` of cards becomes the Trends view. The toggle swaps `hidden`,
  hides the Time scope controls in Live mode, and persists the choice.
- New `frontend/live_snapshot.js` (served like `charts.js`): fetch, render, poll.
  Poll loop: runs only when Live is visible **and** `document.visibilityState === "visible"`
  **and** `market` is `open`/`pre`/`post`; 60 s interval; Refresh-now button.
- Layout (desktop): header strip (net worth, timestamp + "Delayed ~15 min" or
  "Market closed", index chips) → Liquid table by class → Equity sub-class table →
  reconciliation line → collapsible Non-liquid, Tax, Debt → totals band.
  Tables use the existing card styles; numeric columns right-aligned, tabular figures.
  On narrow widths the table keeps Name · Current · Day % · Return % and the rest
  move into the expanded row.
- States: loading skeleton; partial prices (stale symbols listed, values from cache
  with their time); no holdings file (message + link); provider total failure
  (last good values greyed with time).
- Reconciliation flag when |delta| > 1 % (constant, revisit after use).

## 5. Implementation plan

Branch: `live-snapshot` off `main`. TDD per step: tests first, then code.
Check `/usage` after each step against the estimates below; the estimates are
relative, not token counts.

| # | Step | Files | Model / effort | Usage | Context drivers |
|---|---|---|---|---|---|
| 1 | `quote_details()` + tests with mocked HTTP | `src/market_data.py` (1,861 lines — **grep only**, read the Yahoo chart parser region ~L700–760 and `quotes()` ~L1272–1360), `tests/test_market_data_module.py` | Sonnet 5.5 / medium | Moderate | Large module; read by region only |
| 2 | Market hours, quote cache, baseline prices (+ disk cache) | `financial_trends_reporter/live_snapshot.py` (new), `tests/test_live_snapshot_unit.py` (new) | Sonnet 5.5 / medium | Light–moderate | New small files |
| 3 | Valuation, grouping, Modified Dietz, tax estimate, non-liquid/debt roll-up | `live_snapshot.py`, reads `trends_metrics.py` (317), `allocation_policy.py` (grep `canonical_asset_class`, tax-type helpers) | Opus 5.5 / high | **Moderate–heavy** | Financial correctness; fixture design; tax-type lookup may need a search |
| 4 | `/api/live-snapshot` route + origin check + refresh rate limit | `main.py` (402), `tests/test_trends_reporter_server_functional.py` | Sonnet 5.5 / low | Light | Small files |
| 5 | Toggle + Live view render + poll loop | `frontend/index.html` (829 — grep `#scopeBar`/`.grid`), `frontend/live_snapshot.js` (new), `tests/frontend/live_snapshot.test.mjs` (new) | Sonnet 5.5 / medium | Moderate | index.html size; render tests |
| 6 | Browser verification with the real data (market open and closed), reconcile against the Excel sheet by hand for one class | — | Sonnet 5.5 / medium | Moderate | Screenshots; keep to 2–3 |
| 7 | Docs: FUNCTIONAL_SPEC section, release note, README feature currency | `documentation/reference/FUNCTIONAL_SPEC.md` (grep "Financial Trends"), release_notes | Haiku 5.5 / low | Light | Currency regression tests must pass |

Total: **moderate-to-heavy share of one 5-hour Pro session** (roughly a third to a half),
dominated by steps 3 and 5.

### Expensive-step flags and how to keep them scoped
- **Step 1 — `market_data.py`**: never read whole; grep `chartPreviousClose`, `def quotes`.
- **Step 3 — tax types**: grep `acct_tax`/`tax_type` in `src/` with `-l` first; read one
  definition site only. Use a hand-built fixture (5 lots, 3 accounts, 2 flows) so the
  Modified Dietz numbers can be checked on paper — avoids test-fix loops.
- **Step 5 — `index.html`**: grep anchors; do not read the 829 lines linearly. Keep all
  new logic in `live_snapshot.js` so `index.html` changes are a few lines.
- **Step 6** — limit to a fixed checklist; no open-ended visual polishing loops.
- Test runs: `pytest tests/test_live_snapshot_unit.py tests/test_market_data_module.py -q`
  during the loop; `pytest -m "not slow"` + `npm test` once at the end.

### Not affected
- No golden masters change (no projection code touched).
- `tools/generate_system_diagram.py` does not cover `financial_trends_reporter/`; adding a
  function to `src/market_data.py` adds no file or import edge, so no diagram regen. If
  step 3 imports a new `src/` module into the reporter, run the generator anyway.

## 6. Open items for v2
- Baseline follows the Time scope picker (needs historical closes per date).
- Class-level flow allocation by historical mix.
- Full exchange holiday calendar.
- Optional intraday sparkline from the 60 s polls (in memory only).
