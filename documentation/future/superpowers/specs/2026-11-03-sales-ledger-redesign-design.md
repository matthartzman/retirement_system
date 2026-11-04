# Sales Ledger page redesign — design (v2, after peer review)

Date: 2026-11-03 · Page: nav step `sales_ledger` ("Investment Sales Ledger", group *Reports & Review*; step id unchanged, so no nav change)
Status: approved

Acceptance: Matt accepted the design on 2026-11-03 (v2.1, after four peer reviews and three resolved questions).

## 1. Intent and why
The page is where lot/transaction data is maintained and sales are reviewed; every realized-gain figure rests on it. It grew by accretion: ten independently written panels concatenated into one column (`slBodyHtml()`, `frontend/js/dashboard_decomp_sales_ledger.js`). Goal: same capabilities, organised by workflow, compact, scannable.

**Matt's decisions:** default view = fix lot/transaction data · tabs + collapsible sections · Transaction log, Transactions, Cash-in-investment stay on this page · tab/section state remembered.

## 2. Findings (live page, 1400px viewport, 2026 data)
| # | Observation |
|---|---|
| F1 | ~5,400px tall (≈6 screens); 13 headed panels, 6 tables, 48 controls. |
| F2 | **The ledger table is last** (y≈5,076), under everything else. |
| F3 | Transaction log ≈3,580px (66% of page): managed list, add form, transfer form, then an unbounded newest-first table of every row (no filters today). |
| F4 | Idle panels cost space: empty queue ≈90px, idle 1099-B form ≈205px, descriptive paragraphs everywhere. |
| F5 | Inconsistent hierarchy: duplicate `<h2>` under the step title; only 3 of 13 sections collapse, two with `<h3>` inside `<summary>`. |
| F6 | **Hidden coupling:** Year/"Show voided" sit above the bottom table but Year also drives the Realized-gains panel at the top. |
| F7 | No overview of what needs attention (drift, wash flags, queue, unstarted log). |
| F8 | Three "bring data in" flows with different layouts at y 532, 762, 4,893. |
| F9 | Inconsistent controls (bare `<button>`, `class="error"` vs `.btn`/`field-error`). |
| **F10** | **Existing bug found in review:** any ledger load repaints the whole page (`slPaint`), wiping a half-filled "Record a sale" form, the CSV box (so `slImportPreview` → `slPaint` empties `#slCsv` before `slImportCommit` reads it), and sibling panels' previews/chosen files. |

## 3. Goals / non-goals / anti-goals
**Goals:** (1) default view serves fixing data; ledger/tax one click away; (2) every section collapsible with a one-line summary, state remembered; (3) order by likely usage; (4) default tab ≤ ~2 screens at 1400×900 **with the queue review panel closed**; (5) one alert strip + alert markers on tab labels; (6) one consistent look; (7) fix F10.
**Non-goals:** no change to existing server APIs, data model or tax logic (one scoped exception: new read-only *steps* added to the existing Year-End Transition checklist, §4.2 Tab 3); no other page's layout touched; no bulk actions (Bulk review was removed in #384); no new financial features beyond the confirmations in §4.6.
**Anti-goals:** (a) **an alert is never hideable** — a collapsed section always shows its alert in its summary row, and a new/changed alert re-opens it; (b) no loss of in-progress work (chosen file, drafts, previews, CSV text) on tab switch, collapse, or ledger reload; (c) don't break the panel-text tests, phone-layout regression, size ratchet, script-order guard, diagram-freshness test.

## 4. Proposed layout

### 4.1 Frame
```
Investment Sales Ledger
[ Sale year: 2026 ▾ (All years) ] [ ] Show voided (N hidden)                        [ Density: Comfortable | Compact ]
NEEDS ATTENTION (nav, alerts only; one 28px line, absent when clear):
  ● 3 sales waiting · ● Log differs from holdings (2 accts) · ⚠ Wash check: stale · ● 1099-B: 1 acct not tied · ● Log not started …
[ Fix lots & transactions ③ ]  [ Sales ledger ]  [ Tax year ⚠1 ]  [ Import ]       ← sticky; counts/markers on labels
```
- **Strip = alerts only, counted across ALL years** (queue, drift, wash flags, 1099-B untied, unpaired cash, log-not-started, carryforward unsaved, import errors). Each item is a real link: switches tab, opens the section, moves focus to its summary. All-clear shows nothing but a text line "No open items" — and **never** says "reconciles" while any check is unrun (wash check "never run/stale" is itself an amber item). Last-import dates live on the Import tab, not the strip.
- **Year control** is labelled **"Sale year"**, offers "All years" for the ledger, and each tab states its own scope in its title ("Tax year 2026 · sales dated 1/1–12/31"). Dimmed (via `disabled`/`aria-disabled`, not just styling) on tabs it doesn't affect. Other year filters (log filters) are labelled "Filter year".
- Duplicate `<h2>Sales Ledger</h2>` removed.
- Deep links: `#sales_ledger?tab=import&sec=queue` (tab + optional section); also used by the strip and by the post-action navigation below.

### 4.2 Tabs (left→right = likely usage; default = first)
**Tab 1 — Fix lots & transactions** *(default)*
1. **Sales waiting for lots** — open when count>0; when 0 a single 32px row "Nothing waiting". Queue review panel gets its own `max-height` and internal scroll.
2. **Log health** — *drift only* (capped at ~5 rows + "show all"; each drift row links to and filters the offending log row). If the log is not started: a non-collapsible prompt with the Start button (with confirm, §4.6).
3. **Transaction log** — header carries a **"Managed accounts (3)" chip row** (config, not health; each account shows a "managed" chip also in the add/transfer forms and Cash section). Order inside: toolbar/drawers **above** entries — `+ Add transaction` and `+ Transfer` drawers side by side (≥1100px); **Edit** opens the drawer, scrolls to it and focuses the first field; Esc cancels. Then filters (account, symbol, year, type — **new, client-side**; the log has none today) and **paginated entries (25 at a time, "Show 25 more" moves focus to first new row)**. Pagination only — no inner scroll box (avoids nested scroll traps).
   **Merged with the former read-only Transactions panel (Matt's decision, Phase 3):** the section has a mode toggle **"Edit log | History & held lots"** and *one* shared filter bar. *Edit log* = entries with Edit/Void/Note + the drawers; *History & held lots* = the former Transactions view (Amount, Remaining, linked sale, Held-lots) — all of its columns/views are preserved. Filters/mode persist when switching. One count badge, one place to look.
4. **— More views —** divider, then collapsed by default: **Cash in investment accounts** (badge: unpaired count).

**Tab 2 — Sales ledger** — toolbar: totals left ("12 sales · ST net … · LT net …"; non-taxable accounts excluded and labelled "tax-deferred — no gain reported"), `+ Record a sale`, filters right; **ledger table first** (sticky header with opaque bg, scroll region with `role=region` + label + `tabindex=0`); Record-a-sale drawer (4-col grid, opens on Edit). **Void now confirms**, naming the amount ("Remove −$X from 2026 totals?"). "Back to queue" switches to tab 1 and opens the review (replaces the wrong "pick the lots again above" text).

**Tab 3 — Tax year** — scope title; 4 tiles (ST net · LT net · Estimated tax · Carryforward out); two columns (netting & tax | carryforward inputs); **1099-B reconcile status row** ("1099-B for acct ····1234: ties / N lines differ", link to Import) and "as of last 1099-B apply"; *Wash sales* (open when flagged>0; **shows "never run / stale" amber state**; labelled "this app's accounts only"); and a **one-line "Year-end" status link** ("Year-end steps: 4 of 9 open → Year-End Transition") — **the Year-End Transition page is the single home of the year-end checklist** (it already exists: nav step `year_end`, server-derived in `src/year_end.py`, steps link to the screens that do them). This page does *not* carry its own copy. Today that checklist covers only cash-year closing (capture plan year, final broker files, resolve cash rows, confirm CASH balances, close cash year, personal numbers). Phase 5 extends it with the tax-filing steps in filing order — *clear the waiting queue, resolve log drift, run the wash check, apply & tie 1099-B per account, confirm carryforward* — each linking back to the matching tab/section here. Their state is derived server-side from the same services the strip uses, so the two can never disagree.

**Tab 4 — Import** — Broker activity (+ Imports history), Broker 1099-B, Sales CSV; shared **Source → Preview → Apply** skeleton and message area; one-line collapsed summaries ("Last import 10/28 · 21 imports"). **Once a preview exists its diff, change list and control-total status stay expanded; Apply stays disabled until the diff has been viewed and totals tie.** Post-apply CTA: "Review changed lots / re-run wash check" / "N sales waiting → Fix lots".

### 4.3 Section pattern (`sl-sec`)
`<details>` + summary: chevron (aria-hidden) · title · **text badges** ("3 waiting", "warning: drift 2") · right-aligned one-line state. Level 1 tab → level 2 `sl-sec` → level 3 `sl-sub` heading. Section titles keep real heading semantics (heading element wrapping/adjacent to the summary text, not flattened in a summary). Summary hit area ≥24px (44px on coarse pointers).
**Alert rule:** a section with an active alert shows it in red/amber in its summary row regardless of open state. Per section we persist `{open, lastAlertCount}`; when an alert appears or its count changes, any stored "closed" is cleared and the section opens (no focus move; announced via the live region). Stays open until the alert clears or the user collapses it at the *current* count.

### 4.4 Whitespace rules
Section padding 10/14px, gap 8px; comfortable rows ≈28px / compact 24px (**compact disabled on coarse pointers**); auto-fit form grids (`minmax(150px,1fr)`); one-line hints with ⓘ for long text; empty states are one row; anything >15 rows is paginated or scroll-contained (never both).

### 4.5 Remembering state
`localStorage["salesLedger.ui.v1"] = { tab, sections:{key:{open,lastAlertCount}}, density }`; try/catch everywhere; works with storage off/corrupt. **Written only from the user's own summary click/keydown handler** — never from `ontoggle` (browsers fire `toggle` for programmatic/innerHTML opens, which would record auto-opens as user choices), and no repaint from a toggle handler. Existing `ciOpen`/`trOpen`/`biImportsOpen` stay the source of truth for those three panels in early phases, mirrored into the store.

### 4.6 New confirmations (small behaviour additions — flagged for Matt)
Void a sale (names the $ effect); Start the transaction log ("holdings will now be written by the log"); Turn off a managed account ("holdings freeze at their last state; the log stops updating them"). Existing confirms (transaction void, 1099-B "replace earlier import") are unchanged.

## 5. Order rationale
Fix (frequent) → Ledger (review) → Tax year (periodic, filing-time checklist) → Import (episodic; its result links into Fix). Lifecycle order Import→Fix→Ledger→Tax was rejected as default; the post-import CTA covers it.

## 6. How it gets built (my calls)
- Vanilla ES modules; no framework. CSS under `.sl-` in `dashboard.css`, existing tokens. New module `frontend/js/dashboard_decomp_sales_ledger_ui.js` (tab bar, section helper, UI store, strip, live region), loaded **before** `dashboard_decomp_sales_ledger.js` in `index.html`, consumed via `window.*` guards like the other modules.
- **Tabs:** built to the ARIA tabs pattern (the `renderStrategyTabs` precedent lacks it): ids, `aria-controls`, `role=tabpanel` + `aria-labelledby`, roving `tabindex`, ←/→/Home/End, `aria-label` on the tablist, `:focus-visible` styling. **Switching toggles `hidden` directly — never `renderMain`/full re-render** (that would reset file inputs). Add `.sl-tab[hidden]{display:none!important}` (no global `[hidden]` rule exists).
- **All four tabs stay mounted**, so drafts/previews/chosen files survive. The page root stays a `.field-list` and tab containers stay its direct children (phone-layout test depends on `.field-list>*`).
- **Scoped repaint (fixes F10):** split into sub-roots — header, record-sale form, CSV box, list. Loads repaint **only the list root**. Form draft and CSV text live in module variables. Repaint helper saves/restores focus (by id/`data-key`) and scroll positions.
- **Strip/summary data:** each panel exports a small summary getter and calls a `notify` after its `*Paint`; strip, tab markers and section badges render from those summaries (they never fetch). One always-mounted `aria-live=polite` region (alerts `role=alert`) for announcements; panel `role=status` messages are mirrored there because repainted regions aren't announced. Messages/errors surface on the tab where the user acted; hidden-tab messages also raise a marker on the tab label.
- **Panels are wrapped, not rewritten, in early phases** (existing `<details ontoggle>` in Cash/Transactions/Imports and their h3s stay) to keep tests green; panels take over their own summary text in later phases.
- **No id may appear twice across mounted tabs** (e.g. header Year vs `slYear`; side-by-side drawers vs `tlAcct`/`tlType`); a test enforces it. Real `<label>`s on the transaction filters.
- Phone (≤720): tab bar scrolls horizontally, strip wraps, single column; breakpoints tested at ≥1100, 721–1099, ≤720; no page-level horizontal scroll at 320px / 200% zoom (only `rc-scroll` regions). `prefers-reduced-motion` respected.

## 7. Constraints (hard failures if missed)
- Tests that assert on panel markup — treat as contract: `tests/frontend/transactions_panel.test.mjs` (`^<details ontoggle…Transactions…(2)`, `^<details open`), `broker_import_panel.test.mjs` (`<details\s+ontoggle`, `<details open`), `sales_ledger_page.test.mjs` (ids `slAccount slDate slClass slSymbol slShares slProceeds slFees slBasis slPurchase slCsv`; `renderSalesLedger()` contains `id="stRoot"`; its `document` stub only has `getElementById` — scoped paint must not call `querySelector`), `transactions_log_panel.test.mjs` (`tlHtml()` strings incl. "The log and the holdings differ", "agrees with the holdings", `data-managed=…`, "Start the transaction log"; `tlHtml(log, form, xfer, edit)` signature), `sales_queue_panel.test.mjs` (stubs `els={sqRoot}`), plus `test_sales_ledger_phone_layout_regression.py`.
- `tests/test_frontend_size_ratchet.py`: `TOTAL_JS_MAX_LINES = 42_609` over all `frontend/js/*.js` → every phase that adds lines raises the ceiling with a dated comment.
- `wi015_script_order_wrapper_guard.test.mjs`: new script ⇒ count 65→66 and `FROZEN_SCRIPT_ORDER` entry in the same commit; bump `?v=` on every touched script.
- Regenerate `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md`. Account numbers: last 4 only. Never read `dashboard.js` linearly (no change to it is expected).
- Run pytest with `-v` to a log file in the background.

## 8. Phases (each shippable; estimates relative to a 5-hour Pro session — check `/usage` as you go)
| Phase | Scope | Model/effort | Usage |
|---|---|---|---|
| **P1 Frame** | Tab bar (ARIA, `hidden` tabs, deep links, persistence of tab only), header Sale year/voided with scope labels, **sub-root scoped repaint + draft preservation (fixes F10)**, panels placed into tabs **untouched**, new module + guard/ratchet bookkeeping, tests: ledger load preserves form, CSV text, chosen broker file; id-uniqueness test | Sonnet · medium-high | **Moderate–heavy** (highest regression risk; 6 test files + 2 guards) |
| **P2 Signals** | Summary getters + notify in ~6 panels; strip; tab markers; live region; `sl-sec` wrappers with alert/persist rules (§4.3, 4.5); cross-tab navigation ("Back to queue") | Sonnet · medium | Moderate |
| **P3 Fix tab** | Log health (drift only), managed chip row, drawers above entries + side by side, new filters + pagination, **merge Transactions into the log (mode toggle + shared filter bar; keep every Transactions column/view; decouple `tlPost`→`trLoad`; keep `trHtml`/`tlHtml` tests green or update them deliberately)**, "More views" divider (Cash), empty-state one-liners, new confirms | Sonnet · medium-high | **Moderate–heavy** (merge is the coupling risk; do it as its own commit inside the phase, after the rest of P3 is green) |
| **P4 Ledger tab** | Toolbar, drawer form, sticky/keyboard-accessible table, non-taxable chips, sale-void confirm, voided count | Sonnet · medium | Moderate (carries form-state work) |
| **P5 Tax tab + Year-End steps** | Tiles, two columns, 1099-B status row, wash stale state, "Year-end steps" link row; **extend `src/year_end.py` + its tests with the five tax-filing steps** (single-checklist decision) | Sonnet · medium | Moderate (small Python + page tests; check `year_end` tests and `year_end_page.test.mjs`) |
| **P6 Import tab** | Shared skeleton, diff-stays-open + Apply gating, CTAs (broker_import 15 KB, 1099b 13 KB) | Sonnet · medium | Moderate |
| **P7 Polish** | Density toggle (off on touch), phone + 721–1099 pass, axe run, a11y matrix, help-registry text, diagram regen, full test run | Sonnet · medium | Moderate (test loops → log files, no blind loops) |

Budget risks: P1, P3 (merge) and P7. Scope-down: ship P1+P2 first — reorder, tabs, alerts and the F10 fix, with panels untouched.
QA matrix to verify against (P7): viewports 320/375/720/721/1099/1100/1400, 200% zoom; keyboard-only (tab order, arrows, Enter/Space, focus survives repaint); NVDA+Firefox / VoiceOver spot checks; states: empty, loading, API error, 488 and 5,000 rows, each alert alone and combined, alert appearing while collapsed / while typing; voided rows; storage disabled/corrupt; chosen file/draft/preview survive tab switch; forced-colors, reduced motion, touch targets.

## 9. Decisions (all resolved by Matt, 2026-11-03)
1. **Year-end checklist — include, but as a single point.** Resolved as: the existing **Year-End Transition** page is the one checklist; it is extended (Phase 5) with the tax-filing steps; the Sales Ledger page only links to it. *Why not a checklist on this page:* a second copy would drift from the existing one and the existing one already owns step state server-side.
2. **Confirmations — add all three** (void a sale, start log, turn off managed).
3. **Merge Transactions into the Transaction log — in Phase 3.** (Not deferred.)
Open for Matt: none. (One implication to confirm when reading: the Year-End page is outside this page, so Phase 5 touches `src/year_end.py` and the Year-End step list.)

## 10. What changed after review
UX: alerts can't be hidden (persisted `lastAlertCount`); alert markers on tab labels; strip is alerts-only; strip fed by panel summaries; cross-tab navigation/messages; Add/Edit drawers above entries; managed = chip row, Log health = drift only; "log not started" state; "Filter year" labels; "More views" divider; deep links; sticky tabs; merge deferred; 2-screen target qualified.
Feasibility: P1 redefined (panels untouched; scoped repaint into sub-roots; fixes F10); signals split into P2; wrap-don't-rewrite; ontoggle trap; `[hidden]` CSS; no re-render on tab switch; size ratchet + script-order bookkeeping; factual corrections (log panel is small; no `dashboard.js` change); P1/P4 effort re-rated.
Domain: "Sale year" scope + All years; strip counts all years; wash-check staleness; 1099-B diff stays open and Apply gated; 1099-B status on Tax tab; year-end checklist; confirmations; non-taxable chips; drift→row links; managed chips.
A11y/QA: full ARIA tabs; live region; focus/scroll restore on repaint; heading semantics; real-link strip; unique ids + test; keyboard-accessible scroll regions; compact off on touch; 721–1099 breakpoint; reduced motion; QA matrix. (Text-token contrast already passes AA.)

**v2.1 (after Matt's answers):** year-end checklist consolidated into the existing Year-End Transition page (no duplicate on this page); Transactions merged into the log in Phase 3 (P8 removed); sales-ledger tax-filing steps added to `src/year_end.py` in Phase 5.
