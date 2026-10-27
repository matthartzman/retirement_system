# Financial Trends: Live Snapshot, October 2026

Companion Financial Trends reporter only. No projection or build result moves; the golden masters are
unchanged. Design and plan: `documentation/future/superpowers/plans/2026-10-27-live-snapshot-design.md`.

## What you see

- **Trends | Live Snapshot switch** in the toolbar. The page remembers your choice. Live Snapshot hides the
  Time scope pulldown and the four trend cards.
- **Headline:** after-tax net worth, with liquid holdings' change today and this year.
- **Index strip and status:** chips for the S&P 500, Dow and Nasdaq, and a status line ("Market open ·
  Delayed ~15 min", "Market closed", or the tickers whose prices are old).
- **Liquid investments** by asset class (Equity, Fixed Income, Commodities, Cash) and by equity sub-class
  (US Total, International, Small-Cap Value). Each row expands to its tickers.
  - Columns: Start (12/31), Bought since, Current, Share, Day $, Day %, Market gain, Return %, Share of gain,
    Annualized.
  - Changes show ▲/▼ as well as colour.
  - Annualized is compounded and hidden for the first 90 days of the year.
- **Monarch check:** the holdings file's value compared with the latest Monarch investment balances, flagged
  when more than 1% apart.
- **Totals band:** liquid investments, checking, non-liquid assets, debt, net assets, estimated tax and
  after-tax net worth, plus assets by kind.
- **Collapsed sections:** Non-liquid assets (each with its tax treatment), Estimated tax and Debt.
- **Refresh:** prices update every 60 seconds only while the view is shown, the tab is in front and the
  market is in pre-market, regular or after-hours trading. **Refresh now** fetches at once. If an update
  fails, the last good values stay up with a message.

## How the numbers are made

- **Prices:** `market_data.quote_details()` asks Yahoo first, because only Yahoo gives a previous close. The
  other providers are fallbacks (price only), then the cache, marked stale.
- **Start values:** prior year-end closes come from, in order, `data/baseline_prices_<year>.json`, a stored
  price snapshot taken between that close and the next open, then Yahoo daily history.
- **Returns (Modified Dietz over the current lots):** lots held at 12/31 start at that close; lots bought
  since are new money weighted by time invested; reinvested dividends are gain. Statement balances plus
  checking flows could not be used: IRA-to-annuity moves never pass through checking. Net transfers from
  checking are shown for information only.
- **Non-liquid, checking and debt:** from the latest Monarch balances by type.
  - Annuity/Pension accounts and notes are Fixed Income, and real estate is Real Estate.
  - Other assets (startup equity, vehicles, art) are Alternatives.
  - Loans and credit cards are debt, and Cash accounts are checking.
  - Holdings in `*_Checking` accounts are left out of liquid so checking is not counted twice.
- **Estimated tax:**
  - Taxed in full as ordinary income: pre-tax holdings, the IRA-funded joint annuities and the pension.
  - Taxed only above their premium: the after-tax single-life annuities.
  - Ordinary income uses an assumed rate, 25% by default; taxable-account unrealized gains use the plan's
    LTCG rate.
  - `financial_trends_reporter/data/live_snapshot_settings.json` can set `pre_tax_rate`, `ltcg_rate`,
    `annuity_basis` (premium per Monarch account name) and `non_liquid_tax` (per-account override). An
    annuity with no premium set is listed and not taxed.

## New endpoints and files

- `GET /api/live-snapshot` (`?refresh=1` refetches at most once every 10 seconds; quotes are shared for
  30 seconds across tabs; other inputs are cached 10 minutes and cleared by a successful update).
- `GET /live_snapshot.js` serves the view's own module (`financial_trends_reporter/frontend/live_snapshot.js`).
- `financial_trends_reporter/live_snapshot.py`: NYSE calendar (static 2025-2027 holidays and early closes;
  add the next year each December), quote cache, baseline prices, the computation and the endpoint body.
- `src/market_data.py`: `quote_details()` and `daily_closes()`. `src/portfolio_analytics.py`:
  `snapshot_prices_between()`.
