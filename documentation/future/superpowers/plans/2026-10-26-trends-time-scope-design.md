# Financial Trends: One Time Scope, Update on Open, Spending by Window

Date: 2026-10-26 · Status: design for approval · Area: `financial_trends_reporter/`

## 1. Intent

The Financial Trends page is a "look at it now" view. Today you have to click **Run now** for fresh
data, the scope buttons drive only two of the four charts, and Spending is fixed at YTD. After
this change the page opens fresh, one scope control drives every chart, and Spending can be
read for any window. All of today's drill-down and comparison detail stays.

### Requests and decisions

| # | Request | Decision |
|---|---|---|
| a | Capitalize the page and chart titles | Title Case on the page `<title>`, the `<h1>`, the card headings, the in-chart SVG titles, and the Accounts ▾ popover titles |
| b | Replace Run now with an update on open | Planner-style **Updating Data** overlay. It is skipped when a run finished in the last 15 minutes (your choice) |
| c | One pulldown instead of the scope buttons | 1 Week · 1 Month · 3 Months · 6 Months · YTD · 1 Year · All Time · Custom. The last choice is remembered (your choice), and a first visit opens on 1 Month |
| d | All four charts use the scope | Investment Net Flows gets a **daily ledger** (your choice), so it buckets like the other charts |
| e | Rename "YTD expenses…" | Card title is **Spending** |
| f | Spending across scopes | **Option A: compute per window on the server** (your choice) |

### Goals
- One scope value (from, to, granularity) feeds all four charts.
- When you open the page, the data is current, or you can see it is being brought up to date.
- Spending keeps its tracking type → category → merchant hover, the refund netting, the
  included taxes, and its two markers. The markers now mean something for any window.

- No chart scrolls horizontally at any scope or card width. The x-axis is compressed to fit and
  its labels are chosen to stay readable (§2.6).

### Non-goals
- No new chart forms. The "spending over time" stacked chart (option C) is out of scope.
- No change to the scheduled weekday job, the Monarch import, account toggles, or the
  passthrough matching rules.
- No change to the main planner's overlay behaviour. The only planner change is a code move.

### Anti-goals (a failure even if it "works")
- At YTD, the Spending card shows different tracking-type, category or merchant totals than it
  does today.
- Reloading the page or changing the scope starts another 30–150 s price refresh.
- Two update runs write the log at the same time.

## 2. Design

### 2.1 Titles (a, e)
| Where | Before | After |
|---|---|---|
| `<title>`, `<h1>`, exit screen | Financial trends | Financial Trends |
| Card | Net worth | Net Worth |
| Card | Investment net flows by account (YTD) / Investment net flows (monthly) | Investment Net Flows (one title for both renderings) |
| Card | YTD expenses by tracking type (latest) | Spending |
| SVG titles | "Net worth", "Net investment contributions by month" | "Net Worth", "Net Investment Contributions" |
| Accounts ▾ popover | "Investment flows" | "Investment Net Flows" |
| Spending popup | "Total - by tracking type" | "Total - By Tracking Type" |

The `.sub` line under the `<h1>` is rewritten to describe the four charts and the shared scope.
It no longer says "YTD expenses…".

### 2.2 Time scope pulldown (c, d)
- `<label>Time scope <select id="scopeSelect">` with these values: `week`, `month`, `3m`, `6m`,
  `ytd`, `1y`, `all`, `custom`. The two date inputs appear only for Custom, as they do today.
  Changing a date re-renders after a 300 ms debounce, because Spending makes a server call.
- A new pure function in `charts.js`, `scopeRange(scope, anchorDate, custom)`, returns
  `{from, to, label, granularity}`:
  - `anchorDate` is the latest data date. That is the newest balance row's date, or today if
    there are no rows.
  - Week and Month go back 7 days and 1 calendar month from the anchor. 3m, 6m and 1y go back
    3, 6 and 12 months. YTD starts on Jan 1. All Time starts on `ALL_TIME_START` (the existing
    note is kept). Custom uses the two inputs.
  - Granularity: week and month → day; 3m and 6m → week; ytd, 1y and all → month. The
    existing "never finer than the data supports" fallbacks are kept, with `6m` added as a
    weekly nominal.
- `filterByTimeframe` and `granularityForTimeframe` are re-expressed on top of `scopeRange`.
  Old keys `quarter` and `12m` are mapped to `3m` and `1y` when reading a saved preference.
- Every chart reads the same `{from, to, granularity}`:
  - Net Worth / Liquid Investments and Cash: unchanged, just driven by the shared range.
  - Investment Net Flows: §2.4.
  - Spending: §2.5.
- The choice is saved in `localStorage["trendsScope_v1"]` as `{scope, from, to}`. Every access
  is wrapped in try/catch, and a missing or failed value falls back to `month`.
- The page shows the period as a plain label ("1 Month · Sep 26 – Oct 26, 2026") next to the
  pulldown. That way the window each card covers is never in doubt.

### 2.3 Update on open (b)
**Shared code with the planner.** `formatElapsed`, `loadPopupRuntimeHistory`,
`recordPopupRuntime` and `averageRuntimeText` move out of
`frontend/js/dashboard_decomp_build_lifecycle.js` into a new pure module,
`frontend/js/runtime_history.js`. They are unchanged, and the localStorage key and 20-run cap
are parameters that default to today's values. The planner re-imports them. The trends server
serves the same file at `GET /shared/runtime_history.js`. Both apps run the same code, and
each keeps its own history, because they are different origins.

**Overlay.** The trends page gets the planner's overlay markup and CSS: spinner, title
"Updating Data", "Elapsed m:ss" detail, an indeterminate bar, and the line
"The average run-time over the last N runs has been m:ss". The popup id is `trends-update`, and
the line appears once two or more runs are recorded, as in the planner. There are no Cancel or
Hide buttons.

**Flow on load**
1. Fetch history, balances and flows. Render immediately from the stored data, behind the
   overlay if a run follows.
2. `GET /api/run-status` returns `{running, last_run_at}`. `last_run_at` is the latest log
   entry's `run_at`, so the 5 pm scheduled job also counts.
3. If `running` is true, show the overlay and poll run-status every 2 s until it finishes. If
   the last run is older than 15 minutes, show the overlay and `POST /api/run-now`.
   Otherwise, skip the run.
4. On success: record the duration, reload the data, re-render, and close the overlay.
5. On failure: close the overlay, keep the charts on their last data, and show an error banner
   with the server's message and a **Try again** button. The SchemaVersionError wording stays.

**Server**
- `run_now` takes a process-wide `threading.Lock`. A second POST while a run is in progress
  waits for that run and returns its result, so it never starts a second run.
- `GET /api/run-status` is new.
- The 15-minute window is a constant, `FRESH_RUN_SECONDS = 900`, and the client gets it from
  run-status.

**Passthrough approve/deny.** There is no Run now button any more, so a saved decision now
starts an update straight away and ignores the 15-minute skip. All the copy that says
"Run now" becomes "the next update" or is removed.

### 2.4 Investment Net Flows on any scope (d)
- In `src/ytd_tracking.py`, add `accumulate_investment_flow_daily` next to the monthly one. It
  is called at the same two sites (lines ~1505 and 1509) under the same rule, and its output is
  `investment_balance.daily_flows_by_account`: `{account: {YYYY-MM-DD: {to_checking, from_checking}}}`.
  The monthly ledger is kept, unchanged.
- `trends_metrics._monthly_investment_flows` gets a daily twin across every imported year, and
  the snapshot logs `investment_flows_daily`. `/api/flows` returns `daily` when it is present.
- The client keeps the same account toggles (`flowIncludedAccounts`). A new
  `flowSeries(daily, included, range)` sums credits and debits into the scope's day, week or
  month buckets, and empty buckets are zero so the line keeps its spacing.
- The summary tiles stop being "YYYY YTD". They show the totals for the selected period and use
  its label, with the same credit, debit and net colours.
- Older logs without `daily` fall back to the monthly series, filtered to the months that
  overlap the range. Logs with neither keep today's per-account YTD bar.

### 2.5 Spending by window (e, f — Option A)
**Engine.** In `src/spending_tracker.py`, add
`spending_hierarchy_window(root, start, end, merchants_per_category=5)`. It is today's
`ytd_spending_hierarchy` body generalized to a date range, with transactions loaded for each
calendar year the range touches. `ytd_spending_hierarchy(root, year, …, through)` becomes a thin
wrapper (`start=Jan 1 of year`, `end=through or Dec 31`), so the mapping, sign, refund and
"Other merchants" rules live in one place. `tools/golden_compare.py` calls
`ytd_spending_hierarchy`, and its output must stay byte-identical.

**Endpoint.** `GET /api/spending?from=YYYY-MM-DD&to=YYYY-MM-DD` returns:
```
{ window: {from, to, days},
  hierarchy,                       # tracking type -> group -> category -> merchants
  prior: {window, by_type, detail} | null,   # same dates one year earlier; null if before any data
  budget: {by_type, by_category},            # prorated to the window (below)
  full_year_budget: {year, by_type, by_category} }  # annual budget of the window's end year
```
- Prior is the same window shifted back one year, using the existing Feb 29 → Feb 28 rule. It
  is `null` when the shifted window starts before the first transaction year. In that case the
  black markers are left off rather than drawn at $0.
- Budget for each segment is that year's annual budget × days in the window that fall in that
  year ÷ days in that year, summed over the years the window touches. Income and transfer
  tracking types are excluded, as they are today.
- The parameters are validated: ISO dates, `from ≤ to`, and nothing beyond today + 1. A bad
  request gets a 400 with a message.
- Results are cached in memory, keyed on `(from, to, transactions-file mtimes)`, and the cache
  is cleared after each run-now.

**Client.**
- The card fetches `/api/spending` for the current range whenever the scope changes. While the
  fetch is in flight it shows "Loading…" inside the card only, and it drops out-of-order
  responses.
- `buildHierarchyRows` gains a third marker. It receives `hierarchy`, `prior.by_type`,
  `budget.by_type`, `prior.detail` and `budget.by_category`, plus `full_year_budget.by_type`
  and `full_year_budget.by_category`. Each row carries `{prior, budget, fullYear}`, the Total
  row sums all three, and the popup bars (`popMarkers`) draw all three.
- **Three markers, on the bars and in both popups:**

  | Marker | Meaning | Light | Dark | Shape |
  |---|---|---|---|---|
  | Same period last year | Same dates one year earlier (was "Prior-year YTD") | ink `#111827` | `#f3f4f6` | solid tick, 2.5 px |
  | Budget for this period | Annual budget prorated to the window | orange `#ea580c` | `#fb923c` | solid tick, 3.5 px |
  | Full-year budget | The end year's whole annual budget (kept from today) | magenta `#c026d3` | `#e879f9` | dashed tick (3/2), 2.5 px |

  - The bars stay blue `#2563eb`. All three markers are chosen to stand apart from blue and from
    each other in both themes. Because each marker also has its own shape, no colour has to
    carry the meaning alone. That matters most for magenta against blue under red-green colour
    blindness.
  - The colours become CSS custom properties (`--mk-prior`, `--mk-period`, `--mk-full`) with
    dark-mode overrides. They replace `PRIOR_COLOR`/`BUDGET_COLOR` and the `.pm-prior`/`.pm-budget`
    classes.
  - The legend lists all three, using a swatch of each marker's shape.
  - The no-JS data table gains a "Full-year budget" column.
  - When a window is at least a full year, the full-year tick is drawn even though it sits
    inside the prorated tick. When the two values are within 1 % of each other, the ticks still
    draw separately, offset by 1 px.
  - **Check:** the phase 5 tests confirm all six colour values are distinct, with each marker
    at least 3:1 against both the bar blue and the card background in each theme.
- If the endpoint fails, the card falls back to the logged YTD snapshot, as today, with a note
  saying it is showing YTD.

**Snapshot.** The snapshot keeps logging the `ytd_expense_*` fields, which the fallback and log
history use. The page just stops reading them first.

### 2.6 No horizontal scrolling: a fitted x-axis with smart labels
Today `lineChartSvg` makes the chart as wide as `points × 36 px` (56 px for flows) and wraps it in
`.chart-scroll`. The y-axis labels are then pinned with a sticky overlay, and the page scrolls
each chart to the right on every render. Because the scope pulldown now sets the number of points,
the chart is instead **always fitted to its card**, and the x-axis labels do the work of keeping
it readable.

**Fit the width**
- `lineChartSvg(points, {width, granularity, …})` draws at the card's measured width. The page
  measures each chart box and re-renders on resize (`ResizeObserver`, debounced to one frame),
  and falls back to 560 px when no width is known (tests, first paint).
- Removed: `.chart-scroll`, `.chart-inner`, the sticky `.chart-yaxis` overlay,
  `pxPerPoint`, `minW`, and `scrollChartsToLatest()`. The y-axis labels are plain SVG text again.
  Points are spaced evenly across the plot, so a 1-year chart simply has tighter points.
- The two bar charts (Spending, and the older flows bar) draw with a `viewBox` and
  `width:100%`, so they also never clip or scroll in a narrow card.
- Dots shrink to r = 2 above 40 points and are hidden above 90. Hover and keyboard targets stay
  one per point, drawn as transparent circles with the same tooltip and arrow-key navigation.
  Net Worth and Liquid Investments keep their rollover.

**Label the x-axis for the scope, not for the data**
`xAxisLabels(points, {granularity, plotWidth, scope})` picks which points get a label and how it
reads. It replaces the "every Nth point" thinning and the `MM-DD` text.

| Granularity | Label text | Which points get a label |
|---|---|---|
| day (1 Week, 1 Month) | `Oct 26` (no year; weekday initial under it when ≤ 14 points, e.g. `M`) | Mondays, plus the newest point |
| week (3 Months, 6 Months) | `Oct 20` (week start) | The first week of each month, plus the newest point |
| month (YTD, 1 Year, All Time) | `Oct` | Every month if they fit, otherwise quarter starts (Jan/Apr/Jul/Oct) |

- **Year context:** a second line shows the year (`2026`) under the first label and under every
  label where the year changes, so `Dec` → `Jan` is never ambiguous. A spread of one year or less
  that stays inside one calendar year shows the year once, in the card's period label instead of
  under the axis.
- **Fit by measurement, not by count:** each candidate label's width is estimated from its
  character count (about 6 px per character at 10 px type, plus 10 px of padding). Candidates are
  kept greedily from the newest point back, and any label that would overlap a kept one is
  dropped. The newest point is always labelled.
- **Narrow cards (< 420 px):** day labels fall back to day-of-month only (`26`), month labels to
  a single letter with the year line, and the target is about three labels.
- **Gridlines:** a faint vertical tick marks every labelled point, so a label can be matched to
  its point without hovering.
- **Tooltips and the screen-reader table keep the full date** (`Mon, Oct 26, 2026`). Only the
  axis text is shortened.
- Investment Net Flows uses the same function. Its months show `Oct` plus the year line.
- The hover tooltips on points say what a point is: a day, a week starting on a date, or a
  month.

## 3. Calls I made (please check while reading)
1. ~~Prorated vs full-year budget~~: **decided (2026-10-26)**. Spending shows both, as two
   markers alongside the same-period-last-year marker (§2.5). The palette and shapes are my
   call, so check that table.
2. **Custom dates are debounced by 300 ms**, and the period label sits next to the pulldown.
3. **An approve/deny triggers an immediate update.**
4. **The run lock makes a second run wait and share the first run's result.** It does not
   return 409.
5. **The update errors banner has Try again.** There is no other manual refresh control. A
   reload within 15 minutes skips the run by design.
6. **The shared module is served by the trends server from `frontend/js/`.** It is not copied,
   so there is one source of truth.

## 4. Implementation plan

Branch `trends-time-scope` off `main`. Use TDD in each phase: change the failing or contract test
first, then the code. Check `/usage` after each phase against the estimate. Stop and re-scope if
a phase runs more than about 1.5× over.

| Phase | Work | Model / effort | Usage (5-h Pro session) | Context drivers |
|---|---|---|---|---|
| 1 | Shared `runtime_history.js`; planner imports it; `/shared/runtime_history.js` route; regenerate system diagram | Sonnet · medium | **Light** | `dashboard_decomp_build_lifecycle.js` lines 1–60 only; one route |
| 2 | Titles (a, e); remove Run now; overlay; `/api/run-status`; run lock; passthrough → auto-update; copy edits | Sonnet · medium | **Light–moderate** | `index.html` (518 lines, one read), `main.py` (290); server functional tests |
| 3 | Scope pulldown, `scopeRange`, saved choice, period label; Net Worth / Holdings wired | Sonnet · medium | **Moderate** | `charts.js` lines 30–110; rewrite of the trends block in `selected_state_aria.test.mjs` and the `runNow` id in the escaping test |
| 3b | Fit-to-width line charts and smart x-axis labels (§2.6); responsive bar charts; remove scroll code | Sonnet · medium–high | **Moderate** | `charts.js` lines 146–220 (`lineChartSvg`), 318–380 (`barChartSvg`), 479–525, 701–705; `index.html` CSS lines 34–37 and the scroll helper at ~150; two tests in `trends_reporter_charts_module_unit.test.mjs` (lines ~205 and ~273) that pin the scroll markup |
| 4 | Daily flows ledger (`ytd_tracking` + snapshot + `/api/flows`) and client bucketing + period tiles | Opus · medium | **Moderate** | `ytd_tracking.py` (1,785 lines): **grep only**, edit ~960–1000, 1460–1510, 1742. Flows tests (3 files) |
| 5 | `spending_hierarchy_window` + wrapper; `/api/spending`; proration; cache; client wiring + marker wording | Opus · high | **Moderate–heavy** ⚠ | `spending_tracker.py` (2,029 lines): **grep only**, edit ~1404–1460. Golden-compare check. Popup code in `charts.js` 233–330 |
| 6 | Docs: release note, remove remaining "Run now" mentions; full `npm test` + `pytest -m "not slow"`, then full `pytest` in background | Sonnet · low | **Light** (tests are wall-clock, not tokens) | Run test output with `-q`; read failures only |

### Phase details

**Phase 1:** Move the four helpers. In the planner, run `npm test` and the existing overlay
tests. Add `tests/frontend/runtime_history.test.mjs`: average text appears only with 2+ runs,
history is capped at 20, and a storage throw is safe. Run `python tools/generate_system_diagram.py`
because a new `frontend/` file is added.

**Phase 2:** Python tests:
- run-status reports `last_run_at` from the log
- two concurrent `run-now` calls invoke the job once
- `/shared/runtime_history.js` serves JS with the right Content-Type
- the origin check still applies

Frontend tests: no `runNow` element, and the overlay opens only when the last run is stale.
Then update `test_trends_reporter_server_functional.py` and every assertion on the
"Run now" text.

**Phase 3:** Unit tests for `scopeRange`: each scope, a month-end anchor (Mar 31 → Feb 28/29),
YTD on Jan 1, Custom with one bound, and the granularity table. Replace the aria-pressed test
with a test that the select change re-renders and saves the choice, and a test that the old
saved keys map to the new ones.

**Phase 3b:** Write the tests first, in `trends_reporter_charts_module_unit.test.mjs`, and replace
the two that pin `chart-scroll` and the sticky y-axis:
- no `chart-scroll`, `chart-inner` or `chart-yaxis` in the output, and the SVG `width` equals the
  width passed in, for 3 to 400 points
- label selection for each granularity: Mondays for day, first week of the month for week,
  months or quarter starts for month, with the newest point always labelled
- no two kept labels overlap, at widths of 320, 480 and 560 px
- the year line appears on the first label and wherever the year changes
- the narrow-card fallback labels
- tooltips and the data table keep the full date, and the arrow-key navigation still works
- bar charts carry a `viewBox` and `width:100%`

Then check by hand in the browser pane at desktop, tablet and phone widths, over every scope, in
light and dark mode. Confirm there is no horizontal scrollbar on the page or on any card.
Resize the window while a chart is showing.

**Phase 4:** Python tests:
- daily totals sum to the monthly ledger for every account and month (the reconciliation guard)
- passthrough exclusions apply to daily too
- the snapshot carries `investment_flows_daily`

JS tests: week, month and day bucketing, zero-fill, the toggle filter, and fallback to monthly
when there is no daily data.

> ⚠ **Golden masters:** adding a key to `ytd_summary` output could touch pinned outputs. Run
> `python tools/regen_golden_master.py measure` first. Expect no delta, because the new key is
> additive. If anything moves, stop: do not regenerate.

**Phase 5 (most expensive):**

> ⚠ Keep the reads of `spending_tracker.py` to the grep-located window. Do not read it whole.

Write the YTD-equivalence test **first**. `spending_hierarchy_window(Jan 1, today)` must equal
`ytd_spending_hierarchy(year)`, and the endpoint's prior data at YTD must equal the snapshot's
`ytd_expense_prior_*`. Run `tools/golden_compare.py` before and after the wrapper refactor, and
compare the output for identity.

Then test:
- a window that crosses a year boundary
- proration that sums correctly across two years
- prior is `null` before the data starts
- a 400 on bad dates
- a cache hit and the cache clearing after a run
- `full_year_budget` is the end year's annual budget
- all three markers render, on the bars and in both popups, with their distinct classes
- the colour-contrast check from §2.5

To keep the cost down, use a small fixture transactions file rather than the real input.

**Phase 6:**
- Add a release note in `documentation/reference/release_notes/`.
- Grep `documentation/` (excluding `archive/`) for "Run now" and "YTD expenses".
- Commit the regenerated `SYSTEM_ARCHITECTURE_DIAGRAM.md` in the same PR.
- Check the page by hand in the browser pane: every scope, the overlay on a stale log, the
  skip on a fresh one, and Spending at YTD matching the pre-change totals.

**Disproportionate-cost risks and how they are scoped**
- **Phase 5's large file:** grep and read in windows, use fixture data, and do one equivalence
  test rather than an exploratory loop.
- **The golden-master loop (phase 4/5):** measure only, and never regenerate as part of this
  work.
- **The full `pytest` (slow subprocess tests):** run it once at the end, in the background, and
  use `-m "not slow"` while iterating.

Overall: **moderate-to-heavy for one 5-hour session**. Phase 3b is self-contained and touches only
chart rendering and the page's CSS, so it can run in parallel with phase 4. Splitting is natural
after phase 3b (one PR for scope, titles, fitted charts and the update on open) and after phases 4–5 (a second PR for flows and
Spending by window).

## Implementation status

Branch `trends-time-scope`.

- Phase 1: shared runtime_history module: `071051ad` (WIP), `2e176a4c`
- Phase 2: titles, update on open, run lock, /api/run-status: `50b4a1ee`
- Phase 3: time scope pulldown, scopeRange, saved choice, period label: `b66a1cfc`
- Phase 3b: fitted line charts and scope-aware x-axis labels: `ca842e4a`
- Phase 4: daily investment flows ledger and scope-aware Investment Net Flows: `ef5aa82f`
- Phase 5: Spending by window with markers: `b34bae45`, `ebb62876`
- Phase 6: release note and final verification: see the "Docs: Trends time scope and Spending by window
  release note" commit.

Known limitations and follow-ups:

1. A Monarch account rename loses its mappings (the key is the casefolded name).
2. All Time flows and Spending start 2025-02-01, so about $522.5k of earlier flow credits are excluded.
3. The 1 Week scope covers 8 days (Oct 19-26 style).
4. Point tooltips in the flows chart show net only.
5. The dark-mode y gridlines in line charts are still #e5e5e5.
