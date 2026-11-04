# Sales Ledger Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single 5,400px Sales Ledger column with four workflow tabs of collapsible, alert-aware sections (default tab = fix lots & transactions), fix the repaint bug that wipes drafts, and consolidate the year-end checklist on the existing Year-End Transition page.

**Architecture:** Vanilla ES modules. One new module owns tab state, the persisted UI store, section shell, alert strip and live region; existing panel modules keep their own roots/loaders and are wrapped, not rewritten, until their own phase. All four tabs stay mounted (`hidden` toggles, never a full re-render). Panels publish small summary objects; the strip/markers/badges render from those and never fetch.

**Tech Stack:** Browser JS (ES modules, no framework), `node --test` frontend tests, Python 3 / pytest backend (`src/year_end.py` only), CSS in `frontend/css/dashboard.css`.

**Spec:** `docs/superpowers/specs/2026-11-03-sales-ledger-redesign-design.md` (v2.1, accepted). Mockup: `docs/superpowers/mockups/sales-ledger-v2.html`.

## Global Constraints
- Step id `sales_ledger` and all existing server APIs/data model/tax logic unchanged; the only backend change is new steps in `src/year_end.py` (Task 14).
- New module: `frontend/js/dashboard_decomp_sales_ledger_ui.js`, loaded **before** `dashboard_decomp_sales_ledger.js` (index.html line 137), consumed via `window.*` guards. Adding it makes the script count **65 → 66** and requires a `FROZEN_SCRIPT_ORDER` entry in `tests/frontend/wi015_script_order_wrapper_guard.test.mjs` in the same commit; bump `?v=` on every touched script tag.
- `tests/test_frontend_size_ratchet.py`: `TOTAL_JS_MAX_LINES = 42_609` — every task that adds lines raises it with a dated comment (`# 2026-11-03 sales-ledger redesign: +N`). `dashboard.js` is not modified.
- Page root stays a `.field-list`; tab containers are its **direct children** (`.field-list>*` rule is asserted by `tests/test_sales_ledger_phone_layout_regression.py`).
- No element id may appear twice across mounted tabs; do not reuse `slYear`, `tlAcct`, `tlType`, `bi*` ids for new controls.
- Tab switching toggles `hidden` directly; never call `renderMain`. Add `.sl-tab[hidden]{display:none!important}`.
- UI state is written **only from the user's summary click/keydown**, never from `ontoggle`; every `localStorage` access in try/catch; storage key `salesLedger.ui.v1`.
- Alert rule: a section with an active alert always shows it in its summary; a new/changed alert count clears a stored "closed" and opens the section (no focus move; announced through the live region).
- Account numbers: last 4 only, in code, tests, fixtures, screenshots.
- Run pytest as `pytest <paths> -v -rfE > <scratchpad>/pytest_<label>.txt 2>&1` (background for long runs); run `npm test` for the frontend suite. Never read `dashboard.js`, `dashboard_decomp_row_model.js` linearly.
- Work on a new branch `sales-ledger-redesign` (from `main`); one PR per phase; regenerate `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md` (`python tools/generate_system_diagram.py`) in the phase that adds the module (Task 1).

## Review Focus
Each is pinned by a test in the named task.
1. Ledger reload while a half-filled "Record a sale" form, pasted CSV text and a chosen broker file exist → none are lost (Task 3).
2. localStorage unavailable or holding corrupt JSON → page renders with defaults, no throw (Task 1).
3. Alert appears while its section is user-collapsed, or while the user is typing in another form → section opens, focus untouched, announcement made (Task 7).
4. 0 rows / 1 row / 5,000 rows in the log; filter yielding none; "Show 25 more" at the end of the list (Task 9).
5. Voided sales, non-taxable (Roth/pre-tax/HSA) rows and "All years" must not corrupt totals or strip counts (Tasks 6, 12).

## File Structure
| File | Responsibility |
|---|---|
| `frontend/js/dashboard_decomp_sales_ledger_ui.js` (new) | UI store, tab model + ARIA tab bar, section shell `slSecHtml`, summary registry, alert strip, live region, deep-link parsing |
| `frontend/js/dashboard_decomp_sales_ledger.js` | Page composition, header, ledger tab, scoped repaint |
| `dashboard_decomp_{sales_queue,sales_tax,broker_import,sales_1099b,cash_investment,transactions,transactions_log}.js` | Panels; each gains `…Summary()` + publish call |
| `frontend/css/dashboard.css` | `.sl-*` styles (tabs, sections, strip, drawers, density, tiles) |
| `src/year_end.py` (+ `frontend/js/dashboard_decomp_year_end.js` only if rendering needs it) | Five tax-filing steps |
| `tests/frontend/sales_ledger_ui.test.mjs` (new) and the existing panel tests | Contracts |

## Phases at a glance (relative to a 5-hour Pro session — compare against `/usage` as you go)
| Phase | Tasks | Model / effort | Usage | What drives cost |
|---|---|---|---|---|
| P1 Frame | 1–4 | Sonnet · medium-high | Moderate–heavy | 7 small panel files + 6 test files read; two guard tests; highest regression risk |
| P2 Signals | 5–7 | Sonnet · medium | Moderate | edits in 7 panels; stubs in tests |
| P3 Fix tab | 8–11 | Sonnet · medium-high | Moderate–heavy | Task 11 (merge) couples two panels + their tests — run alone, own commit |
| P4 Ledger tab | 12 | Sonnet · medium | Moderate | one 213-line file + form-state tests |
| P5 Tax tab + Year-End | 13–14 | Sonnet · medium | Light–moderate | small files; Python year-end tests |
| P6 Import tab | 15 | Sonnet · medium | Moderate | broker_import 15 KB, 1099b 13 KB |
| P7 Polish | 16 | Sonnet · medium | Moderate | full `npm test` + pytest loops → log files, no blind retry loops |
Scope-down: stop after P2 and you already have tabs, alerts and the repaint fix with panels untouched. Flag: P1, Task 11 and P7 are the budget risks.

---

## PHASE 1 — Frame

### Task 1: UI store, tab model, script bookkeeping
**Files:** Create `frontend/js/dashboard_decomp_sales_ledger_ui.js`, `tests/frontend/sales_ledger_ui.test.mjs`. Modify `frontend/index.html` (insert `<script type="module" src="js/dashboard_decomp_sales_ledger_ui.js?v=1">` before line 137 and bump `sales_ledger.js` `?v=5`), `tests/frontend/wi015_script_order_wrapper_guard.test.mjs` (count 66 + `FROZEN_SCRIPT_ORDER` entry), `tests/test_frontend_size_ratchet.py`.
**Interfaces — Produces:**
- `SL_TABS = [["fix","Fix lots & transactions"],["ledger","Sales ledger"],["tax","Tax year"],["import","Import"]]`
- `slUiLoad(storage = globalThis.localStorage) -> {tab:string, sections:Record<string,{open:boolean,lastAlertCount:number}>, density:""|"compact"}` (defaults when missing/corrupt/throws)
- `slUiSave(state, storage)`; `slUiSetTab(state, id)`; `slUiRecordToggle(state, key, open, alertCount) -> state`
- `slParseHash(hash:string) -> {tab:string|null, sec:string|null}` for `#sales_ledger?tab=import&sec=queue`
- `slSecOpen(state, key, defaultOpen:boolean, alertCount:number) -> boolean` implementing the alert rule.
- [ ] **Step 1: Write failing tests** in `sales_ledger_ui.test.mjs`: `slUiLoad` returns defaults `{tab:"fix",sections:{},density:""}` for a storage whose `getItem` throws, returns `"{bad"`, or returns null; round-trips a saved state; `slParseHash("#sales_ledger?tab=import&sec=queue")` → `{tab:"import",sec:"queue"}` and unknown tab → `{tab:null,...}`; `slSecOpen` returns `true` when `alertCount>0` and the stored entry is `{open:false,lastAlertCount:0}` (count changed), returns `false` when the stored entry is `{open:false,lastAlertCount:2}` and `alertCount===2` (user collapsed at the current count), and returns `defaultOpen` when nothing is stored.
- [ ] **Step 2:** `node --test tests/frontend/sales_ledger_ui.test.mjs` → FAIL (module missing).
- [ ] **Step 3:** Implement the functions above (pure; no DOM). Register on `window` with `Object.assign(window, {...})` like sibling modules. Do the index.html/guard/ratchet edits; run `python tools/generate_system_diagram.py`.
- [ ] **Step 4:** `node --test tests/frontend/sales_ledger_ui.test.mjs tests/frontend/wi015_script_order_wrapper_guard.test.mjs` → PASS; `pytest tests/test_frontend_size_ratchet.py tests/test_system_architecture_diagram_freshness_regression.py -v` → PASS.
- [ ] **Step 5:** Commit `feat(sales-ledger): UI store and tab model module`.

### Task 2: ARIA tab bar and hidden tab panels
**Files:** Modify `dashboard_decomp_sales_ledger_ui.js`, `dashboard_decomp_sales_ledger.js`, `frontend/css/dashboard.css`. Test: `sales_ledger_ui.test.mjs`, `sales_ledger_page.test.mjs`.
**Interfaces — Produces:** `slTabBarHtml(active:string, markers:Record<string,{count:number,tone:"bad"|"warn"}>) -> string`; `slTabPanelHtml(id:string, bodyHtml:string, active:string) -> string`; `slSetTab(id:string, {focus?:boolean}) -> void` (toggles `hidden`/`aria-selected`/`tabIndex`, saves state, no re-render); `slTabKeydown(event) -> void` (←/→/Home/End).
- [ ] **Step 1: Failing tests:** `slTabBarHtml("fix",{})` contains `role="tablist"`, `aria-label`, exactly one `tabindex="0"`, each tab `aria-controls="sl-p-<id>"`; `slTabPanelHtml` has `role="tabpanel"`, `aria-labelledby="sl-t-<id>"`, and `hidden` unless active; a marker `{count:3,tone:"bad"}` renders text `3` inside the tab; `slSetTab` with a stub document sets `hidden` only on non-active panels and never calls a re-render hook.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** Implement; CSS: reuse `.workspace-tabs/.workspace-tab` styles, add `.workspace-tab:focus-visible`, `.sl-tab[hidden]{display:none!important}`, sticky bar.
- [ ] **Step 4:** run both test files → PASS. **Step 5:** Commit.

### Task 3: Header + scoped repaint (fixes F10)
**Files:** Modify `dashboard_decomp_sales_ledger.js`. Test: `sales_ledger_page.test.mjs`.
**Interfaces — Produces:** sub-roots `slHeadRoot`, `slFormRoot`, `slCsvRoot`, `slListRoot`; `slPaint()` now repaints **only** `slListRoot` (must use `getElementById`, not `querySelector` — the test `document` stub only has `getElementById`); module drafts `slDraft: Record<string,string>` and `slCsvText: string`; header renders **"Sale year"** (`#slYear`, option "All years") and "Show voided (N hidden)".
- [ ] **Step 1: Failing tests** (Review Focus 1): after `slSetYear`/`loadSalesLedger` completes with a stubbed `api`, `slDraft.slSymbol` and `slCsvText` are unchanged and `slFormRoot`/`slCsvRoot` innerHTML was **not** rewritten; `slImportPreview()` followed by `slImportCommit()` posts the same CSV text (regression of the empty-`#slCsv` bug); the ledger id contract from `sales_ledger_page.test.mjs` (`slAccount slDate slClass slSymbol slShares slProceeds slFees slBasis slPurchase slCsv`) still present once.
- [ ] **Step 2:** run → FAIL. **Step 3:** Implement: split `slBodyHtml()` into the four roots; read/write drafts on `oninput`; `slEdit` opens the form before setting values; header controls live outside the repainted node.
- [ ] **Step 4:** `node --test tests/frontend/sales_ledger_page.test.mjs` → PASS. **Step 5:** Commit.

### Task 4: Place existing panels in tabs, untouched
**Files:** Modify `dashboard_decomp_sales_ledger.js`; Test: `sales_ledger_page.test.mjs` + new id-uniqueness test in `sales_ledger_ui.test.mjs`.
Mapping (panel markup unchanged): **fix** = `renderSalesQueue`, `renderTransactionLog`, `renderCashInvestment`, `renderTransactions`; **ledger** = record-sale form, ledger table (+CSV box stays here until Task 15); **tax** = `renderSalesTaxYear`; **import** = `renderBrokerImport`, `renderSalesBroker1099b`, CSV import.
- [ ] **Step 1: Failing tests:** `renderSalesLedger()` html has four `role="tabpanel"` elements as direct children of the `.field-list` root, still contains `id="stRoot"`; **no id value occurs twice** in the rendered html (regex over `id="…"`); default panel is `fix`; `#sales_ledger?tab=import` opens Import.
- [ ] **Step 2:** FAIL → **Step 3:** compose; wire `slParseHash` on render. **Step 4:** `npm test` (all frontend) + `pytest tests/test_sales_ledger_phone_layout_regression.py -v` → PASS. **Step 5:** Commit; open PR "Sales Ledger P1: frame".

## PHASE 2 — Signals

### Task 5: Panel summaries + publish hook
**Files:** Modify `dashboard_decomp_sales_ledger_ui.js` and the seven panel modules; tests: each panel's existing `.test.mjs` plus `sales_ledger_ui.test.mjs`.
**Interfaces — Produces:** `slPublish(key, summary:{count:number, tone:""|"warn"|"bad", text:string})`, `slOnSummary(cb) -> unsubscribe`, `slSummaries() -> Record<string,summary>`. Panel getters: `sqSummary()` (key `queue`; count = unmatched), `tlSummary()` (keys `health`=drift accounts, `log`), `stSummary()` (keys `wash` incl. `text:"stale"|"never run"`, `cf` unsaved), `bbSummary()` (`b1099` = accounts not tied), `ciSummary()` (`cash` = unpaired), `biSummary()` (`imports`). Each panel's `*Paint` ends with `slPublish(...)` guarded by `window.slPublish`.
- [ ] **Step 1: Failing tests:** for each panel, after painting stub data, `slSummaries()[key]` equals the expected object (e.g. queue with 3 unmatched → `{count:3,tone:"bad",text:"3 waiting"}`); wash with no run → `{tone:"warn",text:"never run"}`; paint without `window.slPublish` defined does not throw.
- [ ] **Step 2–4:** FAIL → implement → panel tests + `npm test` PASS. **Step 5:** Commit.

### Task 6: Alert strip, tab markers, live region
**Interfaces — Produces:** `slStripHtml(summaries) -> string` (`<nav aria-label="Needs attention">`, one `<a href="#sales_ledger?tab=…&sec=…" data-go>` per item with `count>0 || text in {stale,never run}`; text-only badges; empty → `<span>No open items</span>`, **never** contains "reconcile" while any check is unrun); `slMarkers(summaries) -> Record<tab,{count,tone}>`; `slAnnounce(text, assertive=false)` writing to a single always-mounted `<div aria-live="polite">` (alerts: `role=alert`); `slGo(tab, sec)` (switch tab, open section, focus its summary).
- [ ] **Step 1: Failing tests:** strip lists queue/drift/wash/1099-B/cash/log-not-started/carryforward items from fixtures and counts across **all years** (a fixture with a prior-year item still appears); clear state has no "reconcile"; marker counts per tab; `slGo("tax","wash")` opens the section and calls focus on its summary stub.
- [ ] **Step 2–4:** FAIL → implement (re-render strip on `slOnSummary`) → PASS. **Step 5:** Commit.

### Task 7: Section shell and alert/persistence rules
**Interfaces — Produces:** `slSecHtml({key,title,badges:[{text,tone}],state,alertCount=0,open,body}) -> string` (`<details class="sl-sec" data-key>`, heading element + summary text, badges as text, chevron `aria-hidden`); `slOnSummaryClick(key)` (records toggle via `slUiRecordToggle` from the click/keydown handler only). Applied as wrappers around queue, tax, log, cash, imports panels (panel markup inside unchanged; existing inner `<details>` for cash/transactions/imports stay, mirrored to the store).
- [ ] **Step 1: Failing tests** (Review Focus 3): programmatic `open` change fires `toggle` but the store is **not** written; user collapse at count 2 persists `{open:false,lastAlertCount:2}`; later `alertCount` 3 → `slSecOpen` true and announcement made, focus not moved; alert text visible in summary when collapsed; storage disabled → still works; "Collapse all" leaves alert sections open.
- [ ] **Step 2–4:** FAIL → implement → `npm test` PASS. **Step 5:** Commit; fix `slRequeue`'s message to call `slGo("fix","queue")` and open the review (test: after `slRequeue(7)` active tab is `fix`). Open PR "P2: signals".

## PHASE 3 — Fix tab

### Task 8: Log health, managed chips, Start prompt
**Files:** Modify `dashboard_decomp_transactions_log.js`; Test: `transactions_log_panel.test.mjs`.
**Interfaces:** keep `tlHtml(log, form, xfer, edit)` signature and its asserted strings ("The log and the holdings differ", "agrees with the holdings", `data-managed=… checked`, "Start the transaction log"); add `tlHealthHtml(log) -> string` (drift only, ≤5 rows + "Show all", each row a link calling `tlFocusRow(account,symbol,purchase_date)`), `tlManagedChipsHtml(log) -> string`; when `!log.started` the Start prompt is rendered outside any collapsible and `tlSummary()` reports `{tone:"bad",text:"log not started"}`.
- [ ] **Step 1: Failing tests:** 7 drift items render 5 rows + "Show all"; chips show "managed" on managed accounts; not-started renders the Start button with no `<details>` wrapper. **Step 2–4:** FAIL → implement → panel test PASS. **Step 5:** Commit.

### Task 9: Drawers above entries, filters, pagination
**Interfaces — Produces:** `tlFilterRows(rows, {account,symbol,year,type}) -> rows`; `tlPage(rows, shown:number) -> {rows, remaining:number}` (page size 25, initial 8 in tests via arg); state `tlShown`, `tlFilter`; Edit opens the Add/Revise drawer, scrolls to it and focuses its first field; Esc cancels. Filters have real `<label>`s ("Filter year"). No inner scroll box.
- [ ] **Step 1: Failing tests** (Review Focus 4): 0 rows → "No transactions match."; 5,000 rows → first render 25 rows, "Show 25 more" adds 25, button disappears at the end and focus moves to the first new row; filter with no match; `tlEditRow(id)` opens the drawer (drawer open flag true before values are set).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit.

### Task 10: Confirmations (start log, managed off)
**Interfaces:** `tlStart()` and `tlSetManaged(account,false)` call `window.confirm(message)` first; messages: Start — "Starting the log means holdings will now be written by the log."; managed off — "Holdings freeze at their last state and the log stops updating them." Cancel → no API call; managed checkbox reverts.
- [ ] **Step 1–5:** tests with stubbed `confirm` returning false/true asserting no POST / one POST; implement; PASS; commit.

### Task 11: Merge Transactions into the log (own commit, run alone)
**Files:** Modify `dashboard_decomp_transactions_log.js`, `dashboard_decomp_transactions.js`, tests `transactions_panel.test.mjs`, `transactions_log_panel.test.mjs`.
**Interfaces:** mode toggle `tlSetMode("edit"|"history")`; one shared filter state used by `trLoad` and `tlFilterRows`; `trHtml` content (Amount, Remaining, linked-sale, Held-lots view, `trFilter.held`) is preserved and rendered when mode is `history`; `tlPost` no longer calls `window.trLoad` directly — it calls `tlReloadAll()` which refreshes whichever mode is active; after the merged section the Fix tab renders a "More views" divider followed by the collapsed Cash-in-investment section (test: divider text present, Cash section closed by default); the standalone `<details ontoggle="trToggle…">` wrapper is removed **only** in this task, and the two tests that assert it (`transactions_panel.test.mjs` lines asserting `^<details ontoggle="trToggle…` and `^<details open`) are updated deliberately to assert the new section.
- [ ] **Step 1: Failing tests:** history mode renders columns Date, Account, Type, Symbol, Shares, Price, Amount, Remaining, Sale, Source; held-only toggle lists "Lots held"; switching mode keeps account/symbol/year/type filters; a save in edit mode reloads history data once.
- [ ] **Step 2–4:** FAIL → implement → `npm test` + `pytest tests/test_transactions_unit.py tests/test_transactions_managed_unit.py -v` PASS. **Step 5:** Commit; PR "P3: fix tab".

## PHASE 4 — Ledger tab

### Task 12: Toolbar, drawer, sticky table, void confirm
**Files:** Modify `dashboard_decomp_sales_ledger.js`, CSS. Test: `sales_ledger_page.test.mjs`.
**Interfaces:** `slTotalsHtml(t)` keeps current output but excludes non-taxable rows (returned `gain == null`) and prints "tax-deferred — no gain reported" chips via `slGainHtml`; `slVoid(id)` calls `confirm("Remove ${gain} from ${year} totals?")` using the row's gain; `slHiddenVoidCount() -> number` for "(N hidden)"; table inside `<div role="region" aria-label="Sales" tabindex="0" class="rc-scroll">` with opaque sticky `th`; "Record a sale" is a drawer opened by `＋ Record a sale` and by `slEdit`.
- [ ] **Step 1: Failing tests** (Review Focus 5): totals ignore voided and non-taxable rows; "All years" request omits `year`; void with `confirm→false` makes no POST; table region has `tabindex="0"`; existing assertions on `slRowHtml`/`slTableHtml` still pass.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit; PR "P4".

## PHASE 5 — Tax tab and Year-End

### Task 13: Tax tab layout
**Files:** Modify `dashboard_decomp_sales_tax.js`, CSS. Test: `sales_tax_html.test.mjs`, `sales_tax_year_panel.test.mjs`.
**Interfaces:** `stTilesHtml(s) -> string` (ST net, LT net, Estimated tax, Carryforward out); title "Tax year ${year} · sales dated 1/1–12/31"; `st1099bStatusRowHtml(status)`; wash section shows "never run / stale" per `stSummary()`; `stYearEndLinkHtml(openCount,total)` → "Year-end steps: N of M open → Year-End Transition" calling `setStep('year_end')`. Existing `stNettingHtml/stTaxHtml/stCarryforwardHtml/stWashHtml` outputs and their tests stay valid.
- [ ] **Step 1–5:** tests for tiles values/signs and zero-data, stale wash label, link row; implement; PASS; commit.

### Task 14: Year-End Transition gains the tax-filing steps
**Files:** Modify `src/year_end.py`, `tests/test_year_end_checklist_unit.py`, `tests/test_year_end_checklist_functional.py`, `tests/frontend/year_end_page.test.mjs` if step count is asserted.
**Interfaces:** `build(...)` gains keyword `tax_filing: Mapping[str,int|bool|str] | None = None` (keys `queue_waiting:int`, `drift_accounts:int`, `wash_state:"clean"|"flagged"|"stale"|"never"`, `untied_1099b:int`, `carryforward_saved:bool`); five new `_step(...)` entries inserted **after** `final_broker_files` in this order: `clear_sales_queue`, `resolve_log_drift`, `run_wash_check`, `tie_1099b`, `confirm_carryforward`, each `link="sales_ledger"` and state `"na"` when `tax_filing is None`; `service()` gathers the values from the existing sales/transactions/tax-year services.
- [ ] **Step 1: Failing tests:** `test_steps_come_in_the_designed_order_with_links` updated to the new order; one test per new step (open vs done); `tax_filing=None` yields `na` and leaves old steps unchanged.
- [ ] **Step 2:** `pytest tests/test_year_end_checklist_unit.py -v -rfE > <scratchpad>/pytest_ye.txt 2>&1` → FAIL.
- [ ] **Step 3:** Implement. **Check first** how wash staleness is known: if `refresh_wash_flags` records no last-run marker, store `wash.last_run` in `plan_meta` and compare with the ledger's latest change marker; if the marker needs a design decision beyond that, stop and ask Matt.
- [ ] **Step 4:** unit + functional tests + `npm test` PASS. **Step 5:** Commit; PR "P5".

## PHASE 6 — Import tab

### Task 15: Shared Source→Preview→Apply skeleton, diff stays open, Apply gating
**Files:** Modify `dashboard_decomp_broker_import.js`, `dashboard_decomp_sales_1099b.js`, `dashboard_decomp_sales_ledger.js` (CSV import), CSS. Tests: `broker_import_panel.test.mjs`, `sales_1099b_panel.test.mjs`, `sales_ledger_page.test.mjs`.
**Interfaces:** `slStepsHtml(current:1|2|3) -> string`; 1099-B: `bbCanApply(preview, viewed:boolean) -> boolean` true only when the diff has been viewed (`bbMarkViewed()` on first expand/scroll-into-view of the diff) and control totals tie; diff and change list render outside any collapsed container once a preview exists; post-apply CTAs `slNextStepHtml(result)` ("Review changed lots / re-run wash check", "N sales waiting → Fix lots").
- [ ] **Step 1: Failing tests:** Apply disabled until viewed and totals tie; Apply still requires the existing "Replace earlier import" confirm; broker `<details>` assertions (`<details\s+ontoggle`, `<details open` at lines ~179/181) hold or are deliberately updated; CTA shows after apply.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5:** Commit; PR "P6".

## PHASE 7 — Polish

### Task 16: Density, responsive, accessibility, docs, full verification
**Files:** CSS, `dashboard_decomp_sales_ledger_ui.js`, `frontend/js/help_registry.js` ("Sales Ledger" entry text), `tests/test_sales_ledger_phone_layout_regression.py`, `documentation/reference/SYSTEM_ARCHITECTURE_DIAGRAM.md`.
**Interfaces:** `slSetDensity(""|"compact")` (persisted; ignored when `matchMedia("(pointer:coarse)").matches`); `@media(prefers-reduced-motion)` disables chevron transition.
- [ ] **Step 1: Failing tests:** phone-layout regression extended to `.sl-*` containers (no fixed widths; strip/tabs wrap or scroll); compact density not applied on coarse pointer; help text mentions the four tabs.
- [ ] **Step 2–3:** implement; run the QA matrix by hand in the browser pane at 320/375/720/721/1099/1100/1400 and 200% zoom, keyboard-only pass, storage-disabled and corrupt-JSON, 5,000-row log, each alert alone and combined; run axe on each tab.
- [ ] **Step 4:** `npm test` and `pytest -m "not slow" -v -rfE > <scratchpad>/pytest_fast.txt 2>&1` PASS; then full `pytest` in the background to a log; `python tools/generate_system_diagram.py`.
- [ ] **Step 5:** Commit; PR "P7: polish". Check `/usage` against the phase table and note actuals in the PR.

---

## Self-review (spec coverage)
Frame/tabs/order → T1–4; alert strip, markers, live region, alert rule, persistence → T1, 5–7; Fix tab (queue, health, managed chips, drawers, filters, pagination, merge, More views/Cash) → T8–11 (Cash "More views" divider in T11); Ledger tab incl. void confirm, non-taxable, voided count → T12; Tax tab + 1099-B status + wash stale + Year-End link → T13; single year-end checklist → T14; Import skeleton, diff open, Apply gating, CTAs → T15; density, a11y, phone, QA matrix, docs, diagram → T16; confirmations: sale void T12, start/managed T10; F10 → T3; script/ratchet bookkeeping → T1. Deep links → T1/T4. No spec gap found.
