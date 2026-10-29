# Financial Trends — Recent Projections view (design)

Date: 2026-10-29
Status: design approved 2026-10-29; implementation plan: `2026-10-29-trends-recent-projections-plan.md`

## 1. Intent

The plan's year-by-year Net Worth and Cash Flow projections live only in the
Excel workbook, where Cash Flow still spreads across ~30 columns even with every
outline group collapsed. Recent Projections brings the next few years of both
tables into the Financial Trends reporter as a third view, beside Trends and
Live Snapshot, laid out so the fully collapsed view fits on screen with no
horizontal scroll and every group opens on demand.

Success: you open Financial Trends, click **Recent Projections**, and see
2026–2030 net worth by liquidity bucket (or cash flow from need to funding) in
one screen. You can tell when the workbook was built and whether it is stale,
and you can drill into any group without opening Excel.

### Goals
- A third button on the existing view toggle: `Trends | Live Snapshot | Recent Projections`.
- Two tables, switched with an NW / CF toggle: Net Worth and Cash Flow, with the
  same numbers the workbook's `1D. Net Worth` and `1E. Cash Flow` sheets show.
- A year-count field (default 5) for a window that starts at the current calendar year.
- Groups start collapsed and the Year column is frozen. The fully collapsed view
  of either table fits a normal desktop width with no horizontal scroll.
- The workbook build date, its age, and a staleness flag are always visible.

### Non-goals
- No editing of plan inputs and no rebuilding from this page. It only reads.
- No other workbook sheets (Balance Sheet, Taxes, and so on).
- No charts. Trends already covers the charted view.

### Anti-goals (failure even if it "works")
- Numbers that differ from the workbook's for the same build.
- Silently stale projections: a build older than the plan inputs must be visible.
- Leaking dollar amounts to a percent-only viewer (see §6).
- A collapsed view that still needs a horizontal scroll on a desktop screen.

## 2. Decisions (user, 2026-10-29)

| Topic | Decision |
|---|---|
| Data source | **The build emits a JSON file.** The main build writes a projection-tables JSON next to the workbook, and the reporter reads only that file. |
| Window start | **The current calendar year**, which includes the in-progress year (2026–2030 today). |
| Ages | **In the frozen year cell**, as the year with `64 / 65` in small text under it. There are no separate age columns. |
| Cash Flow collapsed | **Need → funding**, 8 columns: Year, Income ▸, Taxes ▸, Spending ▸, Cash Need ▸, Portfolio Draws ▸, Roth Conv ▸, Net Worth. |
| Net Worth collapsed | **By liquidity**, 6 columns: Year, Investable ▸, Annuities & Pension ▸, Home & Other ▸, Total NW, Δ vs prior year. |
| Build date | **Date, age and flag**: "Workbook built Oct 3, 2026 4:56 PM · 26 days ago". It turns amber when the build is over 30 days old or the plan file changed after the build. |
| Missing JSON | **A rebuild prompt** (an empty state). There is no fallback to reading the .xlsx. |
| Extras | Expand all / Collapse all; the year-count field (1–30, default 5, remembered in this browser); honour the $ / % toggle; remember open groups. |

## 3. Data contract — `projection_tables.json`

**Writer.** The build writes the file to the same output folder as
`retirement_plan.xlsx`, at the same time and from the same `rows` and column
maps that `build_sheet5` / `build_sheet6` use. It must not recompute anything.
The emitter reads the values those builders write, so parity holds by
construction, including the conditional columns (Rental Equity, Rental, Rental
Tax, Rent, LTC).

**Shape** (illustrative):

```json
{
  "schema": "projection_tables/1",
  "build_id": "7aaff05d…",
  "built_at": "2026-10-03T21:56:40Z",
  "plan_path": "…/plan.rpx",
  "owners": ["Matt", "Pat"],
  "tables": {
    "net_worth": {
      "columns": [
        {"key": "PreTax_1", "label": "Matt IRA", "banner": "PRE-TAX (IRA / 401k)", "subtotal": false},
        {"key": "Σ PreTax", "label": "Σ PreTax", "banner": "PRE-TAX (IRA / 401k)", "subtotal": true}
      ],
      "rows": [{"year": 2026, "ages": [64, 65], "values": {"PreTax_1": 1364781.93, "…": 0}}]
    },
    "cash_flow": {"columns": [], "rows": []}
  }
}
```

- `key` is the builder's own semantic column key (`COLS` / `COL` dict keys such
  as `PreTax_1`, `Σ PreTax`, `Mort_PI`, `Σ_Inc`). It never contains an owner's
  name, so the grouping config (§4) stays stable when names or account counts change.
- `label` and `banner` are exactly what the sheet shows in rows 2 and 1.
- All projection years are emitted. The reporter applies the window.
- Totals rows (the sheet's TOTAL and Lifetime rows) are not emitted. The view
  computes its own window total (§5).
- Write the file atomically (temp file, then rename) so the reporter never reads
  half a file.

**Reader.** The reporter adds `GET /api/projections`. It finds the file the same
way the reporter already finds the active plan (`plan_path_for_workspace`), and
caches the parsed file by mtime. It returns the JSON plus `plan_mtime` (for the
staleness flag) and, for percent-only viewers, scaled values (§6). If the file is
missing or its schema is unknown, it returns `{"missing": true}`.

## 4. Grouping

Grouping lives in a single reporter-side config module,
`frontend/projection_groups.js`, which maps semantic keys to a group path. Each
group has a **subtotal column**, which is the only one shown when the group is
collapsed. Groups nest at most two levels.

**When a group opens, its subtotal stays put as the group's first column** and
the detail opens to its right. The column you clicked doesn't move. (This is the
opposite of the workbook, which puts Σ last.)

### 4.1 Net Worth (collapsed: 6 columns)

| Top group (subtotal) | Opens to |
|---|---|
| **Investable** (computed: Σ PreTax + Σ Roth + Σ Trust + HSA + Cash) | Pre-Tax ▸ (per-account) · Roth ▸ (per-account) · Trusts ▸ (per-account) · HSA · Cash |
| **Annuities & Pension** (Σ Ann) | Pension PV · each single/joint annuity PV |
| **Home & Other** (computed: Σ Other − Cash) | Home Equity · Next Housing Equity · Rental Equity (when present) · Startup · Autos · Note |
| **Total NW** | — |
| **Δ vs prior** (computed) | — (blank for the plan's first year) |

Cash moves from the workbook's "Other Assets" into Investable, which matches the
Trends "Liquid Investments and Cash" card. A load-time check requires Investable
+ Annuities & Pension + Home & Other to equal Total NW to the cent. If it
doesn't, a visible warning says so; the numbers are never hidden.

### 4.2 Cash Flow (collapsed: 8 columns)

| Top group (subtotal) | Opens to |
|---|---|
| **Income** (Σ_Inc) | Earned · SS ×2 · Pension · annuities ×4 · Note P+I · RMD Dist · Rental (when present) |
| **Taxes** (Total Taxes) | Fed · State · NIIT · IRMAA · Payroll · LTCG · Rental Tax (when present) · *AGI* · *Taxable Inc* |
| **Spending** (Σ Spend) | Spend Base · Housing ▸ (Mortgage P&I, Property Tax, Utilities, Home Impr, Maintenance, Other, Rent) · Wellness ▸ (Premiums, Medical, Dental, Vision, Rx/OTC, Other, LTC) · Travel · Other · Business · HELOC P&I |
| **Cash Need** (Total Cash Need) | Other Cash Need · Income Funding · Other Funding · Reinvested Surplus · HELOC Draw · *HELOC Bal* |
| **Portfolio Draws** (Σ Cash Draws) | Trust ▸ (per-owner) · HSA · Roth ▸ (per-owner) · IRA ▸ (per-owner RMD + Elective) |
| **Roth Conv** (Roth_Conv) | Per-owner IRA Conv |
| **Net Worth** (NW Check) | — |

Italic columns (*AGI*, *Taxable Inc*, *HELOC Bal*) are context and don't add up
to the subtotal. They are styled muted and right-aligned with a "not part of the
total" tooltip. The per-owner IRA Outflow columns are dropped, because they are
RMD + Elective + Conv, which already appear split across Portfolio Draws and
Roth Conv.

**Unknown keys.** A key that isn't in the config goes into the top group that
matches its workbook banner, and shows up there when that group opens. A
reporter test fails if the build fixture emits a key the config doesn't map, so
new columns get a deliberate home.

## 5. Screen

```
[Trends] [Live Snapshot] [Recent Projections]                         Exit
┌──────────────────────────────────────────────────────────────────────────┐
│ [Net Worth | Cash Flow]   Years [ 5 ]   Expand all · Collapse all        │
│ Workbook built Oct 3, 2026 4:56 PM · 26 days ago   ⚠ plan changed since │
├──────────┬──────────────┬────────────────────┬──────────────┬──────────┬───────────┐
│ Year     │ Investable ▸ │ Annuities & Pens. ▸│ Home & Other▸│ Total NW │ Δ vs prior│
│ 2026     │   2,849,071  │      1,257,077     │  1,581,595   │5,687,743 │     —     │
│  64 / 65 │              │                    │              │          │           │
└──────────┴──────────────┴────────────────────┴──────────────┴──────────┴───────────┘
```

- The Time-scope picker and the custom dates are hidden in this view, as Live
  Snapshot hides what doesn't apply to it. The Exit button stays.
- **Frozen**: the Year column is `position: sticky; left: 0`. The header rows are
  sticky to the top, which matters when the year count is high.
- **Group headers** sit on a top header row as buttons with ▸ / ▾ and
  `aria-expanded`. Keyboard: Tab to a header, then Enter or Space toggles it.
- **Number format**: whole dollars with thousands separators. Below 700 px wide,
  amounts switch to a compact form ($5.69M, $428k) so the collapsed view also fits
  on a phone. Negatives use the existing `.neg` colour.
- **Cash Flow window total**: a bold last row, "N-yr total", sums each flow column
  over the window. Net Worth has no total row, because balances don't add across years.
- **Remembered in this browser** (localStorage, every access in try/catch): the
  last NW/CF choice, the year count, and the open groups per table. With
  "remember open groups", Collapse all also clears the remembered set, so
  "starts collapsed" is always one click away.
- **Empty state** (no JSON): "Recent Projections appear after the plan is rebuilt.
  Rebuild in the Retirement Planner, then refresh." Same card styling as `.live-error`.
- **Window past the plan's end**: show the years that exist plus the note
  "The plan ends in 2061".

## 6. $ / % toggle and access

The existing `money_view.js` convention: % = a percent of **today's** net worth,
and for a percent-only viewer the server divides before sending, so dollars never
reach their browser. Recent Projections must keep the second rule whatever the %
means: `/api/projections` scales every value server-side for percent-only
viewers, just as the other `/api/` routes do.

**Decision (user, 2026-10-29): % means a percent of today's net worth**, the existing
convention. Every cell, Δ included, is divided by the same basis that
`percent_view.scale_basis` gives, so 2030 Total NW reading 108% shows growth.

## 7. What's left to the builder

- Where exactly in `workbook_builder.py` to emit the file (after `build_sheet5/6`,
  before `wb.save`, writing beside `out_path`), and how to surface each builder's
  `COL` map, for example by having `build_sheet5/6` return it.
- How the reporter finds the output folder for the active workspace (follow
  `plan_path_for_workspace`).
- CSS details, as long as they match the existing `.live-table` look and dark mode.
- Whether the regenerated architecture diagram is needed (CLAUDE.md rule). It is
  needed if new `src/` files or imports are added.

## 8. Resolved questions

1. % meaning: a percent of today's net worth (§6).
2. Group mapping in §4: approved as drafted.

## 9. Calls I made (please check)

- The subtotal stays left and the detail opens to the right (§4).
- Cash moves into Investable, and Home & Other is computed (§4.1).
- IRA Outflow columns are dropped; AGI, Taxable Inc and HELOC Bal are shown as
  context (§4.2).
- The Cash Flow window total row; no total row for NW (§5).
- Compact numbers below 700 px (§5).
- Time scope is hidden in this view (§5).
- The build age flag uses the plan file's mtime compared with `built_at` (§2).
