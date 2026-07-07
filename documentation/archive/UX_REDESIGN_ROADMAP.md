# UX Redesign — Design Document & Implementation Roadmap

Generated: 2026-06-29  
Status: **Approved for implementation**

---

## Vision

The system should feel less like a collection of tools and more like a guided planning workspace. Each screen should answer three questions without searching:

1. **What is this for?** — title + one plain-language purpose sentence
2. **What needs attention?** — status indicator + any warnings or missing fields
3. **What should I do next?** — primary action button + contextual next-step prompt

---

## Design Principles

- **Progressive disclosure.** Advanced features exist but are hidden behind a toggle. Power users reveal depth; casual users never see it. Nothing is removed.
- **Build is always accessible.** Never more than two clicks from any screen.
- **No technical vocabulary on user-facing screens.** API, schema, backend, payload, SQLite, CSV, JSON, adapter, route never appear in titles, descriptions, or button labels.
- **Every section has a completion state.** ✓ complete · ● has data · ○ not started — always visible.
- **One vocabulary everywhere.** See Canonical Vocabulary section.

---

## Canonical Vocabulary

These terms apply to every nav label, page title, button, help text, and error message in the system. No exceptions.

| Term | Definition | Replaces |
|---|---|---|
| **Plan** | The saved working plan (data + settings) | "working copy," "active configuration," "client data" |
| **Plan Data Folder** | Import/export CSV files on disk | "input files," "CSV," "backend data," "client_data" |
| **Build** | Generate current reports from the plan | "run," "rebuild," "compute," "process," "generate" |
| **Reports** | Generated workbook and all output files | "output," "detailed results," "workbook," "results" |
| **Comparison** | Scenario, workbench, or impact analysis | "stress test view," "planning workbench diff," "what-if" |
| **Member 1 / Member 2** | Plan participants | "Husband/Wife," "H/W," "Spouse 1/2" (already migrated) |

**Never use on any user-facing screen:** API, schema, adapter, route, payload, backend, SQLite, CSV, JSON, YTD, IRMAA (as a bare label), MAGI (as a bare label).

**Preserve with context:** RMD (with expanded form on first use), HELOC (with expanded form), Roth (proper noun), Monte Carlo (Reports/advanced only, define on first use), Legacy (in estate/wealth-transfer copy — meaningful domain vocabulary), QDRO (with "Divorce Planning" as the primary label), COLA (in help text only).

---

## Current State

- **Navigation:** ~58 page entries across multiple groups. Many pages are near-duplicates or sub-topics that belong together.
- **Known nav issues:** Duplicate "Annuity death benefits" entry in Other Assets. "Spending Analysis" appears in both Spending and Reports groups. Planning Workbench requires a loaded plan before entry.
- **Page header consistency:** Most pages lack a standardized purpose sentence and status indicator. Some use technical descriptions.
- **Reports:** Six separate pages (Reports, Detailed Results, Build Impact, Build History, Downloads, Plan Data Report) with overlapping roles and no single entry point.
- **Strategy:** Ten pages covering related decisions with no consolidation into decision-type groups.
- **Spending:** Import, assign, review, and sync steps exist but are not presented as a guided sequence.
- **Settings:** Advanced maintenance tools (CSV utilities, diagnostics, assumptions tables) sit alongside user-facing settings with no separation.

---

## Target Navigation Architecture (post Phase 3)

~22 visible pages vs. ~58 today. All depth preserved inside tabs and collapsible advanced sections.

```
Plan Status (home)             checklist, health summary, Next Best Action panel
  Profile (3 pages)
    ├─ Household & People
    ├─ Retirement Timing
    └─ Income & Social Security
  Accounts (2 pages)
    ├─ Investment Holdings
    └─ Account Balances
  Spending (4 pages — guided sequence)
    ├─ Spending Model
    ├─ Wellness & Medical
    ├─ Lifestyle Spending       (merges: Housing, Travel, Large Items)
    └─ Actual Spending          (guided: Import → Assign → Review → Sync)
  Assets & Protection (3 pages)
    ├─ Other Assets & Notes
    ├─ Insurance & Estate
    └─ Annuity & Special Income
  Strategy (4 pages + persistent Workbench)
    ├─ [header button] Planning Workbench (Compare & Decide)
    ├─ Distribution Strategy    (tabs: Levers · Roth · Withdrawal Order)
    ├─ Investment Strategy      (tabs: Allocation & Location · Policy Settings)
    ├─ Timing & Tax             (sections: SS Timing · State Residency)
    └─ Special Strategies       (advanced/collapsed: HELOC · Charitable)
  Reports & Review (1 tabbed workspace)
    └─ tabs: Preflight | Build | Impact | Results | Downloads | Plan Data Review
  Settings
    ├─ Normal Settings
    └─ Advanced Maintenance     (collapsed by default)
```

---

## Phase 1 — Low-Risk Usability Cleanup

**Goal:** Visible, safe improvements with zero behavior changes. Users feel the app is cleaner and clearer.  
**Scope:** String replacements, CSS visibility toggles, template additions. No logic changes, no new routes, no engine changes.  
**Effort:** 2–3 sprints

---

### 1.1 Vocabulary & Label Renames

**Files:** `frontend/js/dashboard.js` — `STEPS` array `title` fields and any inline strings.

Rename the following `title` values in the `STEPS` array:

| Current label | New label |
|---|---|
| YTD Transactions | Actual Spending (This Year) |
| HELOC Strategy | Home Equity Line |
| Entity & Charitable Giving | Charitable Giving |
| Accounts Setup *(in Other Assets group)* | Account Details |
| Detailed Results | Results |
| Build Impact | Impact |
| Plan Data Report | Plan Data Review |
| Divorce/QDRO *(or equivalent)* | Divorce Planning |
| Monte Carlo *(standalone entry)* | Probability Analysis |

Search for each old title before changing — some may appear in test assertions.  
Run after: `grep -r "old_title" tests/` before each rename.

---

### 1.2 Jargon Pass — All User-Facing Strings

**Files:** `frontend/js/dashboard.js`, `frontend/js/spending_dashboard.js`, `frontend/index.html`

Audit every string visible to the user. Remove or replace:

- "API" / "api" in labels → "service" or remove
- "schema" → "format" or remove
- "backend" → "system" or remove
- "SQLite" → remove (never user-facing)
- "CSV" → "file" or "Plan Data" depending on context
- "JSON" → remove (never user-facing)
- "payload" → remove
- "route" → remove
- "YTD" (standalone) → "This year" or "Year to date"
- "IRMAA" (bare label) → "Medicare income surcharge (IRMAA)"
- "MAGI" (bare label) → "Modified adjusted gross income (MAGI)"

The Advisor/Household mode toggle already partially controls acronym display. Ensure decode happens consistently in household mode for RMD, IRMAA, MAGI, PDIA on first use.

---

### 1.3 Standardize Every Page Header

**Files:** `frontend/js/dashboard.js` — each per-step render function

Every page gets a consistent header block:

```
[Title]                                   [Status: ✓ Complete | ● In Progress | ○ Not Started]
One plain-language sentence describing what this page is for.
                                          [Primary action button]
```

The status indicator uses existing field completion data already computed by `dashboard.js`. The primary action button should be the most likely "what's next" for that page — not always Save. Add a `pageHeader(title, purposeSentence, statusFn, primaryAction)` helper function to avoid repetition.

Priority pages that currently lack a purpose sentence or have technical descriptions:

- All Assumptions / Economic Assumptions
- Plan Data Summary / Plan Data Review  
- Allocation Policy Settings
- Withdrawal Sequencing
- Spending Analysis

Acceptance: no page title, subtitle, or button label contains API, schema, backend, payload, SQLite, CSV, JSON, adapter, or route.

---

### 1.4 Collapse Advanced-Only Pages

**Files:** `frontend/js/dashboard.js` — `STEPS` array

Add a boolean `advanced: true` flag to each step that should be hidden from normal users. In the nav renderer, skip steps with `advanced: true` unless `showAdvanced` mode is active.

Add a "Show advanced" toggle at the bottom of the nav. Also reveal advanced steps automatically in Advisor mode.

Pages to mark `advanced: true` by default:

- Allocation Policy Settings
- All Assumptions / Economic Assumptions
- System Configuration *(move to Settings in Phase 5)*
- Special Strategies (HELOC, Charitable Giving)

Content is unchanged — the steps still exist and still work. Only their default visibility changes.

---

### 1.5 Fix Known Navigation Issues

**File:** `frontend/js/dashboard.js` — `STEPS` array

1. **Remove duplicate "Annuity death benefits" entry.** Search the `STEPS` array for the duplicate and remove one. Verify the remaining entry has the correct render function attached.

2. **Remove "Spending Analysis" from the Spending nav group.** Its canonical home is Reports. Delete the STEP entry in the Spending group. The page and route remain — this only removes it from the spending nav section.

3. **Allow Planning Workbench entry without a loaded plan.** The Workbench currently guards on `hasPlan`. Add an empty state ("No plan loaded — open or create a plan to begin comparing") rather than blocking entry entirely.

---

### 1.6 "Suggested Next" Prompts

**File:** `frontend/js/dashboard.js` — end of each section render function

Add a static nudge line at the bottom of each page pointing to the most logical next step. This is a plain `div` with a right-facing link — not dynamic, not computed, just a hardcoded string per page.

Example pattern:
```js
function renderHousehold(rs) {
  // ... existing render ...
  return html + suggestedNext('Retirement Timing');
}
```

The `suggestedNext(stepTitle)` helper resolves the step ID from the title and renders:
```html
<div class="suggested-next">Suggested next: <a href="#">Retirement Timing →</a></div>
```

Suggested mappings (not exhaustive):

| Current page | Suggested next |
|---|---|
| Household & People | Retirement Timing |
| Retirement Timing | Income & Social Security |
| Income & Social Security | Investment Holdings |
| Investment Holdings | Account Balances |
| Account Balances | Spending Model |
| Spending Model | Actual Spending (This Year) |
| Distribution Strategy | Investment Strategy |
| Investment Strategy | Timing & Tax |

---

### 1.7 YTD Spending Alert Badge

**Files:** `frontend/js/spending_dashboard.js`, `frontend/js/dashboard.js`, CSS

When actual spending diverges >3% from the spending model projection (the divergence rate is already computed by `spending_dashboard.js`), surface a small amber badge on the "Actual Spending" nav item.

Implementation:
1. `spending_dashboard.js` exposes `getSpendingDivergencePct()` returning the current rate.
2. Nav renderer checks this value when building the "Actual Spending" step label.
3. If `abs(divergence) > 0.03`, append `<span class="nav-badge nav-badge--warn">!</span>` to the label.

No new API calls required — uses data already fetched by the spending dashboard.

---

### 1.8 "Plan Ready to Build" Signal

**Files:** `frontend/js/dashboard.js` — header area render

Add a persistent indicator in the app header (or immediately below) showing build readiness:

- **Green "Ready to build"** — all minimum required fields are populated and no blocking warnings exist.
- **Amber "Needs attention (N items)"** — one or more required fields are missing or have warnings. Clicking opens a modal or scrolls to a preflight summary.

Use the existing field completion/validation data already available in the config rows. Define a `minBuildReadiness()` function that checks a fixed list of required fields (Household members, at least one retirement year, at least one account balance, at least one income source).

When the plan is green, the Build button in the header becomes prominently active. When amber, the Build button is visible but carries a warning icon.

---

### 1.9 Field-Level Tooltips on Key Inputs

**Files:** `frontend/js/dashboard.js`, CSS

Add small `?` icon buttons with one-sentence popover text on numerically non-obvious fields. Implement a `tooltip(text)` helper that returns the icon + popover markup.

Priority fields and suggested text:

| Field label | Tooltip text |
|---|---|
| Portfolio nominal return | "Historical average: 6–7%. Conservative planners use 5–6%." |
| General inflation | "Recent 10-year average: ~3%. The default 2.5% is a long-term assumption." |
| Mortality / plan-end age | "The plan runs until this age. Longer is more conservative." |
| SS monthly benefit (age 70) | "Enter the age-70 monthly amount from your SSA statement." |
| Real estate appreciation | "National average: 3–4%. Local markets vary significantly." |
| State income tax rate | "Enter your effective rate, not the marginal bracket rate." |

The tooltip does not replace the right-sidebar help panel — it supplements it for inline quick reference.

CSS: `.field-tooltip` with a `::after` popover, positioned relative to the `?` icon. Use `z-index` high enough to avoid overlap with the sidebar.

---

### Phase 1 Definition of Done

- [ ] All renamed nav labels active; no old labels visible in normal (non-Advisor) mode
- [ ] Zero pages contain API/schema/backend/payload/SQLite/CSV/JSON/adapter/route in any user-visible string
- [ ] Every page has a title, one purpose sentence, a status indicator, and a primary action button
- [ ] Advanced pages are hidden by default; "Show advanced" toggle reveals them
- [ ] Duplicate "Annuity death benefits" nav entry removed
- [ ] "Suggested next" prompt appears at the bottom of all section pages listed above
- [ ] YTD spending badge appears when divergence >3%
- [ ] "Plan ready" signal appears in header; Build button activates green state
- [ ] Tooltip component working on all priority fields listed above
- [ ] `pytest tests/ --tb=short -q` passes 550/550

---

## Phase 2 — Reports & Review Consolidation

**Goal:** Replace ~6 separate pages (Reports, Detailed Results, Build Impact, Build History, Downloads, Plan Data Report) with one unified tabbed workspace. Users have one place for anything related to outputs.  
**Effort:** 2–3 sprints

---

### 2.1 New Reports & Review STEP

**File:** `frontend/js/dashboard.js`

Add one new STEP entry with `id: 'reports_and_review'`, `group: 'Reports & Review'`, `title: 'Reports & Review'`. Render function is a tabbed container (see 2.2–2.7).

Position it where the current "Reports" group starts in the STEPS array. Keep existing individual page STEPs in the array but mark them `hidden: true` (they remain routable for direct links but do not appear in the nav).

---

### 2.2 Tab Container Component

**File:** `frontend/js/dashboard.js`

Implement a `renderTabbedWorkspace(tabs, activeTab, onTabChange)` helper. Tabs are: `['Preflight', 'Build', 'Impact', 'Results', 'Downloads', 'Plan Data Review']`.

Active tab persists in `localStorage` under key `reports_active_tab`. Default tab on first visit: `'Preflight'`.

Tab CSS: consistent with existing nav style. Active tab has a bottom border highlight. Tab labels use canonical vocabulary (no "Detailed," no "Workbook").

---

### 2.3 Preflight Tab

**File:** `frontend/js/dashboard.js` — `renderReportsPreflight()`

Answers "Is my plan complete enough to build?" — a checklist grouped by section:

```
Profile
  ✓  Household & People        complete
  ✓  Retirement Timing         complete
  ⚠  Income & Social Security  Member 2 monthly benefit is $0

Accounts
  ○  Investment Holdings       no holdings entered
  ✓  Account Balances          8 accounts

Spending
  ✓  Spending Model            complete

──────────────────────────────────────────────
Plan is ready to build with 1 warning.    [Build Now]
```

Status icons: ✓ (complete, green) · ⚠ (warning, amber) · ○ (not started, gray) · ✗ (error, red, blocks build).

"Build Now" routes to the Build tab and triggers a build. Errors block the button; warnings do not.

Data: uses config rows already in `rows` array, same data as the 1.8 readiness signal.

---

### 2.4 Build Tab

**File:** `frontend/js/dashboard.js` — `renderReportsBuild()`

Consolidates existing build controls. Contents:

- Build button (large, primary).
- Progress bar showing named step (not a bare percentage): "Saving account data… 18%", "Running projection… 54%", "Writing workbook… 87%".
- Last build summary: date/time, duration, result (success/warnings/errors).
- Build event log (collapsible, last 20 events, most recent first).

Named build steps come from the existing `/api/build/status` polling response. If the step name is not provided, fall back to the existing percentage. Add a `step_label` field to the build status response in `src/server/workbook_routes.py` to support this.

---

### 2.5 Impact Tab

**File:** `frontend/js/dashboard.js` — `renderReportsImpact()`

Shows before/after comparison of key metrics since the last build, whenever any plan data has changed since that build.

Metric delta table format:
```
Metric                    Last build      With these changes    Change
Terminal net worth        $9,976,067      $10,740,907           +$764,840  ▲ 7.7%
Lifetime taxes            $1,355,577      $2,279,489            +$923,912  ▲ 68.1%
First RMD year            2037            2036                  -1 year
Total Roth conversions    $1,343,867      $0                    -$1,343,867
```

If no plan changes have been made since the last build: "No changes since last build — Impact will appear after you modify the plan."

If no build has been run yet: "Build reports to see impact."

Source data: delta between `last_build_snapshot` (stored in SQLite on each successful build) and the current config rows. The snapshot schema should match `golden_master_engine_cases.json` key set.

Replaces and deprecates: the standalone "Build Impact" page STEP.

---

### 2.6 Results, Downloads, Plan Data Review Tabs

**Files:** `frontend/js/dashboard.js` — content migration

- **Results tab:** Move render logic from the "Detailed Results" render function. No content changes. Update internal references from `renderDetailedResults()` to `renderReportsResults()`.
- **Downloads tab:** Move render logic from "Download Reports." No content changes.
- **Plan Data Review tab:** Move render logic from "Plan Data Report." No content changes. Rename "Plan Data Report" → "Plan Data Review" in any internal strings.

---

### 2.7 Redirect Old Routes

**Files:** `frontend/js/dashboard.js` — step navigation handler

For 2 sprints after Phase 2 ships, navigating directly to the old step IDs (`detailed_results`, `build_impact`, `download_reports`, `plan_data_report`) redirects to `reports_and_review` with the appropriate tab pre-selected.

In the step navigation handler, add:
```js
const REPORTS_REDIRECTS = {
  'detailed_results':  'Results',
  'build_impact':      'Impact',
  'download_reports':  'Downloads',
  'plan_data_report':  'Plan Data Review',
};
if (REPORTS_REDIRECTS[targetStepId]) {
  navigateTo('reports_and_review', { tab: REPORTS_REDIRECTS[targetStepId] });
  return;
}
```

Remove the redirect map and the hidden `STEP` entries in Phase 3.

---

### Phase 2 Definition of Done

- [ ] Single "Reports & Review" entry in nav with 6 working tabs
- [ ] Preflight tab shows completion checklist with live field data
- [ ] Build tab shows named progress steps (not bare percentage)
- [ ] Impact tab shows delta table after any plan change since last build
- [ ] Old step IDs redirect correctly for 2-sprint window
- [ ] `pytest tests/ --tb=short -q` passes 550/550

---

## Phase 3 — Planning Workbench as Strategy Hub

**Goal:** Reduce Strategy group from ~10 pages to 5. Make Planning Workbench the single comparison surface. Remove duplication with Reports (Impact tab).  
**Effort:** 3–4 sprints

---

### 3.1 Move Workbench to Persistent Header Button

**File:** `frontend/js/dashboard.js` — header render, `STEPS` array

Remove the Workbench from the Strategy nav group. Add a "Compare & Decide" button to the persistent app header (visible on all pages). Clicking opens the Workbench overlay or navigates to the Workbench page, whichever pattern matches existing implementation.

The Workbench STEP entry remains in `STEPS` but moves `group` to `null` (header-level item). The nav renderer skips `group: null` items in the left nav sidebar.

---

### 3.2 Workbench — Inline Lever Editing

**File:** `frontend/js/dashboard.js` — Planning Workbench render function

Add a collapsible side panel to the Workbench for editing lever values inline, without navigating away to "Strategy Levers." The side panel renders the same field rows as the Strategy Levers page, filtered to lever-type fields.

The Strategy Levers page remains accessible as a source-editing page (for the full field view) but the Workbench becomes the controller for comparison. Add a "← Back to Strategy Levers" link in the side panel.

---

### 3.3 Workbench — Scenario Library Tab

**File:** `frontend/js/dashboard.js` — Planning Workbench render function

Add a "Scenarios" tab inside the Workbench. Move the "Scenario Change Sets" page content into this tab. Named scenarios are saved, named, compared within the same comparison matrix as existing Workbench cases.

Mark the standalone "Scenario Change Sets" STEP as `hidden: true` in the nav (keep the route for existing deep links for one release cycle, then remove).

---

### 3.4 Workbench — Stress & Probability Tab

**File:** `frontend/js/dashboard.js` — Planning Workbench render function

Add a "Stress & Probability" tab inside the Workbench. Consolidate:

- Stress Suite selector (existing content)
- Survivor / early death stress (existing content)
- Long-term care stress (existing content)
- Monte Carlo / Probability Analysis results

Results from stress runs and Monte Carlo appear as rows in the existing comparison matrix:
```
                          Terminal NW    Lifetime Tax    Notes
Baseline (last build)     $9,976,067     $1,355,577
Scenario: Retire Early    $8,812,000     $1,198,000
Stress: 2000–2002 crash   $6,440,000     $1,021,000
Probability (10th pct)    $5,200,000     —              10% of paths end below this
Probability (50th pct)    $9,800,000     —              median path
```

Standalone stress and Monte Carlo STEP entries: mark `hidden: true` after this tab ships.

---

### 3.5 Strategy Group Consolidation

**Files:** `frontend/js/dashboard.js` — `STEPS` array and render functions

Replace the current 10 Strategy pages with 4 consolidated pages. Add tab containers within each page using the `renderTabbedWorkspace()` helper from Phase 2.

**Distribution Strategy** (3 tabs)
- Tab 1: Strategy Levers ← existing content from "Strategy Levers" page
- Tab 2: Roth Conversion ← existing content from "Roth Conversion" page
- Tab 3: Withdrawal Order ← existing content from "Withdrawal Sequencing" page

Rationale: all three are distribution decisions (when to take money, from where, in what form).

**Investment Strategy** (2 tabs)
- Tab 1: Allocation & Location ← existing "Asset Allocation & Location" content
- Tab 2: Policy Settings ← existing "Allocation Policy Settings" content (currently advanced)

Rationale: policy settings are the fine-tuning for the allocation decision made in tab 1.

**Timing & Tax** (2 sections, single scroll)
- Section 1: Social Security Timing ← existing content
- Section 2: State Residency ← existing content

Rationale: both are "when and where" optimization questions, not deep enough to warrant separate nav entries.

**Special Strategies** (advanced, collapsed by default)
- Home Equity Line ← existing "HELOC Strategy" content
- Charitable Giving ← existing "Entity & Charitable Giving" content

Mark `advanced: true` in STEPS. Visible only when "Show advanced" is on.

Old standalone page STEPs (Social Security Timing, State Residency, Roth Conversion, Withdrawal Sequencing, Allocation Policy Settings, Scenario Change Sets): mark `hidden: true` for one release, then remove.

---

### Phase 3 Definition of Done

- [ ] "Compare & Decide" button visible in header on all pages; navigates to Workbench
- [ ] Workbench has inline lever editing side panel
- [ ] Workbench has Scenarios tab with saved scenario library
- [ ] Workbench has Stress & Probability tab; Monte Carlo appears in comparison matrix
- [ ] Strategy nav shows 4 pages (Distribution, Investment, Timing & Tax, Special Strategies)
- [ ] Each consolidated page has a working tab container
- [ ] Old standalone pages hidden; deep links redirect or warn
- [ ] `pytest tests/ --tb=short -q` passes 550/550

---

## Phase 4 — Spending Workflow Refinement

**Goal:** The Spending section becomes a guided sequence. Users clearly know the four steps and their position in them.  
**Effort:** 2–3 sprints

---

### 4.1 Guided Step Indicator

**Files:** `frontend/js/dashboard.js`, `frontend/js/spending_dashboard.js`, CSS

All four "Actual Spending" steps share a visual progress ribbon at the top:

```
Step 1           Step 2            Step 3                Step 4
Import           Assign            Review vs Plan        Sync to Plan
Transactions     Categories
──────────────── ─────────────────────────────────────────────────────
● Done           ▶ In progress     ○ Not started         ○ Not started
```

Implement a `renderSpendingStepIndicator(currentStep, completionState)` helper. Call it at the top of each of the four spending sub-page render functions.

`completionState` is derived from:
- Step 1 (Import): `transactions.length > 0`
- Step 2 (Assign): `unassignedCount === 0`
- Step 3 (Review): user has viewed the review page (localStorage flag)
- Step 4 (Sync): `lastSyncDate` is set in config

---

### 4.2 Step Completion Conditions

**Files:** `frontend/js/spending_dashboard.js`

At the bottom of each step page, add a "You're done here when:" condition in a subtle box:

- Step 1: "Done when: at least one transaction file has been imported."
- Step 2: "Done when: all transactions are assigned a spending category."
- Step 3: "Done when: you have reviewed the YTD rate vs. your spending model."
- Step 4: "Done when: you have synced actuals to the plan and rebuilt."

Steps 2–4 are optional. If no transactions have been imported, steps 2–4 show an empty state: "No transactions imported. You can still build reports using your spending model. [Import Transactions →]"

---

### 4.3 Auto-Advance Prompts

**File:** `frontend/js/spending_dashboard.js`

When a step's completion condition becomes true, show a prompt (not forced navigation):

```
Step complete. Ready to: Assign Categories →    [Continue] [Stay here]
```

This replaces the "Suggested next" prompt for spending pages with a smarter, completion-aware version. The static "Suggested next" from Phase 1 is suppressed for these pages.

---

### 4.4 Lifestyle Spending Page Consolidation

**File:** `frontend/js/dashboard.js` — `STEPS` array and render functions

Merge "Housing Costs," "Travel," and "Large Items / One-Time Spending" into one page: **Lifestyle Spending**. These have the same field-entry pattern (amount, frequency, year range) and are all non-essential non-recurring costs.

Use the existing section-based layout within the page — three collapsible sections (Housing, Travel, Large Items) within one STEP entry.

Old standalone STEPs (Housing Costs, Travel, Large Items): mark `hidden: true`, route to new combined page.

---

### Phase 4 Definition of Done

- [ ] Step indicator appears at top of all four Actual Spending sub-pages
- [ ] Completion conditions shown at bottom of each step
- [ ] Auto-advance prompt appears when step completion condition is met
- [ ] "Lifestyle Spending" page combines housing, travel, and large items
- [ ] Steps 2–4 show appropriate empty state when no transactions imported
- [ ] `pytest tests/ --tb=short -q` passes 550/550

---

## Phase 5 — Deeper Simplification & Enhancements

**Goal:** Complete the transformation from "collection of tools" to "guided planning workspace." Add features that close the remaining guidance gaps.  
**Effort:** 4–6 sprints

---

### 5.1 Plan Status Home Screen

**Files:** `frontend/js/dashboard.js` — home render function, `STEPS` array

Replace the "Start" page with a **Plan Status** dashboard. This becomes the default landing screen for a loaded plan.

Layout (top to bottom):
1. **Plan health summary** — four key metrics from last build, or "not yet built" prompts:
   - Starting portfolio (year 1 total NW)
   - Projected final portfolio (terminal NW)
   - Depletion risk (first year terminal NW goes below $0, or "None projected")
   - Tax efficiency score (lifetime tax as % of lifetime income, relative to a benchmark)
2. **Setup checklist** — section completion by group (Profile ✓, Accounts ●, Spending ○ …)
3. **Next Best Action panel** (see 5.2)
4. **Last build info** — date, duration, result, with a "Rebuild" shortcut button

When no plan is loaded, show an onboarding card: "Open an existing plan or start a new one to begin."

---

### 5.2 Persistent Next Best Action Panel

**File:** `frontend/js/dashboard.js` — NBA panel component, plan state machine

A context-aware panel that surfaces one clear action based on current plan state. Appears on the home screen and optionally as a compact strip in the header on all other pages.

State priority order (first matching state wins):

| Condition | Message | Action |
|---|---|---|
| No plan loaded | "Open or create a plan to get started." | [Open Plan] |
| Required fields missing | "Complete [Section]: [specific field label] is empty." | [Go to Section] |
| Unsaved changes in section | "Save your changes to [Section]." | [Save] |
| YTD spending diverges >5% | "Review actual spending — [N]% above projection." | [Review Spending] |
| Plan stale (>30 days since last build) | "Rebuild reports — last build was [N] days ago." | [Build Now] |
| Plan complete, not yet built | "Your plan is ready to build." | [Build Now] |
| Build in progress | "Building… [step label] — [N]%" | [View Progress] |
| Build complete, not reviewed | "Reports ready. Review your results." | [View Results] |
| Reports reviewed | "Reports downloaded? All done." | [Download Workbook] |

State is derived from: `rows` config data (field completeness), `dirty_count` (unsaved changes), `lastBuildDate` (localStorage/DB), spending divergence (from `spending_dashboard.js`), build status polling.

The NBA panel on the home screen is the full card with icon and descriptive text. The header strip is a compact one-liner (text + button only, visible only when state is actionable).

---

### 5.3 Quick-Impact Sliders

**Files:** `frontend/js/dashboard.js` — Workbench or Plan Status page

Interactive sliders for the three most-adjusted variables, showing approximate impact on terminal NW without rebuilding. Uses sensitivity data from the last build.

**Variables:**
- Annual spending (steps: ±$5,000; range: ±$50,000 from current)
- Portfolio return (steps: ±0.25%; range: ±2% from current)
- Retirement age (steps: ±1 year; range: ±5 years from current)

**Display:**
```
Annual Spending     ──────────●────── $142,000/yr    (current: $132,000)
                    "Increasing spending by $10,000/year
                     reduces projected final portfolio by approximately $180,000."
```

**Implementation prerequisite:** The build output must include a `sensitivity_deltas` object in the API response from `/api/build/results`:
```json
{
  "sensitivity_deltas": {
    "spending_per_10k":  { "terminal_nw_delta": -180000 },
    "return_per_25bps":  { "terminal_nw_delta": 95000 },
    "retire_per_year":   { "terminal_nw_delta": 210000 }
  }
}
```

Add this to `src/projection_pipeline.py` by computing first-order sensitivities from the existing MC sensitivity simulation runs already in the engine (`mc_sensitivity_sims`).

---

### 5.4 Simplified Settings Split

**Files:** `frontend/js/dashboard.js` — Settings render functions, `STEPS` array

**Normal Settings** (default visible):
- Market data source (Live / Cached / Offline)
- Plan backup & export (manual backup, restore from file)
- Plan Data folder location
- Report output path and format settings
- Display preferences (Household / Advisor mode)

**Advanced Maintenance** (collapsed by default, same page or modal):
- Plan Data folder CSV tools (import, export, validation)
- Economic assumptions tables (currently "All Assumptions")
- Tax constants and reference data
- Diagnostics and build audit trail
- Optimizer and allocation system settings
- Governance and data source dates

Implementation: one "Settings" STEP in the nav. The page has two sections. Advanced section has a "Show Advanced Maintenance" toggle that expands the section. On Advisor mode, it expands by default.

---

### 5.5 "Explain This Result" — Contextual Narrative

**Files:** `frontend/js/dashboard.js` — Results tab render, `src/detailed_results.py`

Clicking any significant value in the Results table opens a popover with a plain-English explanation of what drove that number.

Example: clicking year 2036 tax value of $142,000:
> "2036 is your first RMD year. Member 1's required minimum distribution from their traditional IRA ($57,053) added to your other income pushed you into the 22% bracket for the year, resulting in higher federal income tax."

**Implementation:**
- `src/projection_pipeline.py` already tags rows with event flags (rmd_year, first_conversion_year, etc.).
- Expose a `/api/results/explain-row?year=2036` route in `src/server/workbook_routes.py` that returns a structured explanation object `{ year, event_type, primary_driver, plain_text }`.
- The Results tab render function attaches a click handler to each row's tax and NW cells; the click fires the explain route and renders the popover.

---

### 5.6 Recent Changes Log

**Files:** `frontend/js/dashboard.js`, `src/server/app_core.py`, SQLite

Show the last N field changes with timestamps and before/after values. Allow single-field undo within the current session.

**Implementation:**
- On each field save, append to `localStorage` key `recent_changes` (array, capped at 50 entries): `{ field_id, label, old_value, new_value, timestamp, step_id }`.
- Add a "Recent changes" panel accessible from the header or Settings page.
- Undo restores the old value via the existing field save route, no special API needed.
- Clear the log on "Save & Exit" (the log is session-scoped, not persisted across sessions).

---

### 5.7 Scenario-to-Plan Promotion

**Files:** `frontend/js/dashboard.js` — Planning Workbench render

From the Workbench comparison matrix, promote any saved scenario case to the active plan.

Flow:
1. User clicks "Promote to Plan" on a comparison row.
2. Modal shows a before/after table of all field values that differ from the current plan.
3. User confirms. System applies the scenario's override fields to the active plan data.
4. Confirmation: "Scenario 'Retire Early' applied to plan. Rebuild reports to see updated projections. [Build Now]"

Uses existing scenario override field structure. The promotion writes the overrides back to the config rows using the standard field-save route.

---

### 5.8 Closeout Checklist

**Files:** `frontend/js/dashboard.js` — Reports & Review workspace, or standalone modal

A gated "Plan is final" flow for when a user has completed their planning cycle. Gives a clear "done" state.

Checklist:
```
□  All required sections complete
□  Results reviewed (visited Results tab)
□  Workbook downloaded
□  Key assumptions confirmed (plan start year, mortality age, return assumptions)
□  Notes saved (optional free-text "rationale" field)
```

When all boxes are checked, show a "Mark plan as final" button. This sets a `plan_finalized` flag in the DB and shows a "Final ✓" badge in the header. The flag does not lock editing — it's a marker, not a gate. Clearing the flag (or making any field change) removes the badge.

---

### Phase 5 Definition of Done

- [ ] Plan Status home screen with health summary, checklist, and NBA panel
- [ ] NBA panel correctly identifies and surfaces the highest-priority action based on plan state
- [ ] Quick-impact sliders work against last-build sensitivity data
- [ ] Settings page has Normal / Advanced Maintenance split
- [ ] "Explain this result" popover appears on Results tab row click
- [ ] Recent changes log populated on each field save; single-field undo works
- [ ] Scenario promotion flow tested end-to-end
- [ ] Closeout checklist modal renders and persists finalized flag
- [ ] `pytest tests/ --tb=short -q` passes 550/550

---

## Cross-Cutting Technical Notes

### Dashboard.js `STEPS` array changes

Every Phase 1–5 nav change involves editing the `STEPS` array in `dashboard.js`. Before making any `STEPS` change:

1. `grep -r "step_id_being_changed" tests/` — confirm no test assertions reference the old ID.
2. If tests reference it: update tests first, then rename.
3. After any STEPS change, manually verify: nav renders correctly in both Household and Advisor modes; direct navigation to old IDs either redirects or falls through to the default page gracefully.

### Test suite maintenance

After any page title, step ID, route URL, or JS function rename:
- Run `grep -r "old_string" tests/` before committing.
- Update test assertions in the same session as the code change.
- After any `input/client_*.csv` or `input/client_data.json` change: regenerate golden master values (see `documentation/CLAUDE.md`).
- After any `STEPS` group structure change: re-run `tests/test_90_v10_architecture.py` which checks nav structure.

### Route additions (Phase 2 Build tab, Phase 5 Explain)

New API routes go in the appropriate `src/server/` file. Follow the existing pattern: `from .app_core import *` at the top, register the route on `app`, keep business logic in a service function under `src/server_services/`. Add the new route to `src/api_contracts.py` registry.

### Sensitivity data (Phase 5 Sliders)

The `mc_sensitivity_sims` config value already runs abbreviated sensitivity simulations. Exposing the delta data requires:
1. Collecting per-variable deltas in `src/projection_pipeline.py` after the sensitivity sim loop.
2. Attaching to the build result payload in `src/server/workbook_routes.py`.
3. Caching in `local_state/retirement_system_v10.db` under a `sensitivity_deltas` key so the sliders work without a rebuild.

---

## Open Questions

| # | Question | Owner | Target phase |
|---|---|---|---|
| 1 | Should the NBA panel appear on every page (compact header strip) or only on the home screen? | UX | Phase 5 |
| 2 | What is the "stale build" threshold for the NBA panel? 30 days? 7 days? | UX | Phase 5 |
| 3 | Quick-impact sliders: show on Plan Status home screen or inside the Workbench? | UX | Phase 5 |
| 4 | Should the Closeout checklist be gated (can't close without completing) or advisory-only? | UX | Phase 5 |
| 5 | For the Impact tab delta table: should last-build snapshot be stored in SQLite or derived from a saved result file? | Engineering | Phase 2 |
| 6 | "Explain this result" popover: LLM-generated narrative or template-driven? Template is faster to ship; LLM is richer. | Engineering | Phase 5 |
