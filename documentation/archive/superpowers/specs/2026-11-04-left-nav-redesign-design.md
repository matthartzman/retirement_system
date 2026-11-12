# Left Nav Redesign — Usability Review, Design, and Implementation Plan

Status: implemented (merged to main as PR #390 on 2026-11-04); decisions are in section 9
**Date:** 2026-11-04
**Scope:** left navigation (`STEPS` in `frontend/js/dashboard.js`, `renderSteps()` in `dashboard_decomp_row_model.js`, `navigation.js`), plus a new per-group "Features" popover and a Set up / Maintain flow switch.

## 1. Intent

The nav should answer three questions fast: *where do I go next*, *where is the thing I'm looking for*, and *what could this plan include that I haven't switched on*. Today it is organised by the history of how the app grew, not by what the user is doing. The goals are intuitiveness, ease of use, and fewer clicks. They are not visual restyling.

**Non-goals:** changing page contents, changing the gating rules (`stepGatedByOptionalModule`), changing the workbook's `DOMAINS` order (it drives sheet order and must not move), redesigning the Plan Features page.
**Anti-goals:** a second source of truth for what is enabled; hiding anything the user needs to reach in two clicks or fewer; making the menu longer.

## 2. Current state (observed)

28 pages in 12 groups (`dashboard.js` lines 14–188), gated by 18 module/step gates, with 41 optional module toggles and 5 plan flags (heloc, hybrid_ltc_policy, daf_giving, qcd_giving, qlac).

| Group | Pages |
|---|---|
| Plan Status | 1 |
| Household | 1 |
| Income & Benefits | 2 |
| Spending | 1 |
| Investments & Property | 6 |
| Insurance & Care | 1 |
| Estate & Legacy | 1 |
| Taxes | 3 |
| Family & Business | 1 |
| Strategy | 4 |
| Reports & Review | 4 (+1 hidden) |
| Settings | 5 |

## 3. Usability findings

**a) Grouping**
1. **Seven of twelve headings front a single page** (Plan Status, Household, Spending, Insurance & Care, Estate & Legacy, Family & Business). That is a heading to scan and a click to expand for one destination. The cost is real when every group collapses.
2. **Reports & Review mixes two jobs**: producing results (Build & Results) and recurring upkeep (Actual Spending, Account Reconciliation, Investment Sales Ledger, Year-End Transition). Returning users hunt for their routine tasks in a group named after outputs.
3. **Actual Spending is separated from reconciliation and the ledger**, though all three are used together on a monthly cycle.
4. **Family & Business ("Education & Equity Comp")** is a hub whose rows live on Other Assets. It is assets, not a life domain.
5. **Plan Features (the on/off switchboard) is buried third in Settings**, while the setting it controls shapes the whole menu.
6. **Reserve Requirements** sits in Investments & Property but is a cash-planning concept.

**b) Sequence**
1. Nav order is Spending → Investments, but the app's own guided walk (`SUGGESTED_NEXT`) goes holdings → reserves → spending. The two orderings disagree.
2. Taxes sits before Strategy but Roth Conversion is a strategy lever; the group is a mix of inputs (Account Tax Basis) and analysis.
3. Numbered steps (1…N) imply one fixed order, which is true only on first setup. A returning user does not want numbers.
4. Settings is correctly last, but Plan Features should lead it.

**c) Names**
| Today | Problem | Proposed |
|---|---|---|
| Checking & Savings Accts | abbreviation | Checking & Savings |
| SS, Pensions, & Annuities | punctuation clutter | Social Security & Pensions |
| Other Assets and Liabilities | vague | Other Assets & Debts |
| Reserve Requirements | jargon | Cash Reserves |
| Education & Equity Comp | abbreviation, two topics | 529 & Equity Compensation |
| Workbench | meaningless alone | Planning Workbench (matches module key) |
| Strategy | broad, overlaps "Optimize" | Analyze |
| Build & Results | fine; keep | Build & Results |
| Field Finder | internal term | Find a Field |
| Data & Maintenance | "Maintenance" collides with the new Maintain flow | Data & Backups |
| Investments & Property | misses cash and debts | Accounts & Property |
| Reports & Review | split in two | see section 4 |

## 4. Proposed structure

Twelve headings become **eight** (one pinned link plus seven groups). Page count is unchanged. Group sizes are 2–7, so every expanded group is worth the click.

| # | Group | Pages (in order) |
|---|---|---|
| — | **Plan Status** (pinned link, no heading) | Plan Status |
| 1 | **Household & Cash Flow** | Household & People · Work Income · Social Security & Pensions · Spending Model |
| 2 | **Accounts & Property** | Checking & Savings · Investment Holdings · Rental Properties · Home Equity Line · Other Assets & Debts · Cash Reserves · 529 & Equity Compensation |
| 3 | **Protection & Legacy** | Insurance · Estate Inputs |
| 4 | **Taxes** | Account Tax Basis · Roth Conversion · Charitable Giving |
| 5 | **Analyze** | Optimize · Stress Test · Scenarios · Planning Workbench · Build & Results |
| 6 | **Track & Reconcile** | Actual Spending · Account Reconciliation · Investment Sales Ledger · Year-End Transition |
| 7 | **Settings** | Plan Features · Economic & Tax Assumptions · Find a Field · Workbook Formatting · Data & Backups |

Notes on the choices (my calls unless marked as yours in section 9):
- Household & Cash Flow merges two single-page groups plus Spending; it matches the first things a new user fills in.
- Taxes keeps Account Tax Basis, which was moved there on purpose in #387; first in the group because it is an input feeding the other two.
- Analyze absorbs Build & Results: it is the natural finish of the analysis chain, and it removes a one-page group.
- Track & Reconcile is the home of the recurring routine.
- Find a Field duplicates the nav's "Page" search scope. Keep it for now; a later step can fold it into search.

### 4.1 Set up / Maintain flow switch (your decision)

A two-option segmented control above the menu: **Set up | Maintain**.

| | Set up | Maintain |
|---|---|---|
| Group order | as in section 4 | the Set up order, with **only Track & Reconcile lifted to the top** (one move to learn, not eight; decided after the usability review) |
| Step numbers | shown (1…N) | hidden |
| Default expanded group | first group with required-missing items | Track & Reconcile |
| "Suggested next" footer | the setup chain | Actual Spending → Reconciliation → Sales Ledger → Build & Results |
| Progress bar | % complete | count of items needing attention |

Only emphasis changes (the one lifted group, numbering, defaults, the suggested-next chain). **A page's group and a feature's home are identical in both modes**, so spatial memory and the Features popover never change meaning. No page appears or disappears with the switch (that is the job of Features, below). **My call:** default Set up while any required item is missing, otherwise Maintain; the choice is remembered per browser once the user picks one.

### 4.2 Fewer clicks

- Multiple groups may stay open; the open set is remembered. The active page's group is always open.
- Pinned Plan Status is one click from anywhere.
- In Maintain mode the most common destinations (Track & Reconcile) are first and open, so the monthly routine is zero extra clicks to reach.
- Nav search stays (keeps typed text, per #385).

## 5. Features icon (per top-level heading)

### 5.1 Appearance
A tiny (12–14 px) sliders glyph to the right of each group heading. It carries a dim **count badge of features that are off** in that group (for example, `3`). With nothing off, the glyph shows alone and quiet. The accessible hit area is at least 24×24 px even though the glyph is small. Groups with nothing toggleable (Plan Status, Settings) show no icon. That is my call.

### 5.2 Popover content
Anchored to the icon (bottom sheet in the mobile drawer). Title: "Features in *Group*". Three sections, in this order:

1. **Not enabled** — each row: feature name, one-line help text, on/off switch (off).
2. **Enabled** — each row: name, switch (on); clicking the name opens that page.
3. **Always on** — pages that cannot be switched off, with a lock glyph; clicking opens the page. No switch.

**Row design (usability review):**
- Rows are grouped under host-page sub-headers and sorted by catalog demand band (common first); niche rows sit under a collapsed "More".
- Sheet-only features start **collapsed** under a "Workbook sheets" sub-header.
- Each row says what it adds in plain words: "Adds a page", "Adds a section to Optimize", "Adds a workbook sheet". No "Page/Section/Sheet/Option" jargon. A small topic tag (for example Taxes) shows the domain.
- Plain-language names replace opaque ones (for example "Market-luck stress test" for Monte Carlo); one-line description per row.
- Rows show dependencies ("Needs Roth Conversion") and kept data ("Off · 3 rows kept").
- Turning a feature on shows feedback naming where it went ("Added to Analyze › Optimize. Open").
- The gated-off note on host pages (Optimize, Stress Test) carries the same switch, wired to the same setter.

Footer links: "Open Plan Features" and "Browse all features by topic" (Plan Features already groups by domain, so it is the by-topic route; the popover is the by-location route). Empty sections are omitted. The `Esc` key and outside click close it. Focus returns to the icon.

### 5.3 Behaviour (your decision: hide only, keep data)
Turning a feature off removes its page from the nav and leaves its entered data saved; turning it on restores it. Where a gated page already shows an "Off · N rows kept" state (Rental Properties), the popover row shows the same note. Toggles call the **same setter the Plan Features page uses**, so the two always agree and there is no second state. Dependencies and parent/child rules from the catalog (`parent`, `extra_steps`, any-of gates such as Charitable Giving and Family & Business) are honoured by that setter; the popover only renders its result.

### 5.4 What counts as a "feature", and where each one is listed (sub-feature analysis)

**Finding 1: the catalog's grouping is not where the user finds the feature.** `nav_group` defaults to the catalog `domain` (the part of life a module concerns). Many modules have no page of their own; their inputs live as sections inside another page. Listing them by domain would put the switch in one group and the thing it reveals in another. Example: HSA Drawdown has domain Taxes, but its inputs are a section of **Optimize** (Analyze group); Social Security timing has domain Income & Benefits but is also a section of Optimize.

**Rule (my call): a feature is listed under the group of the page where its inputs appear (its *host page*), with a small topic tag for the domain.** A feature with no inputs at all (a workbook-only output sheet) is listed under the group whose topic it belongs to. Each row has "Open" to jump to the host page, so a user who switches something on can land on it in one click.

**Finding 2: about 20 of the 41 optional modules only add or remove a workbook sheet; they never change a nav page** (Charts, Glossary, Lifetime Taxes, RMD Audit and so on). "Features that might be included underneath" should include them, because they are switchable, but they are a different kind of thing. Each row carries a type tag: **Page**, **Section** (inside a page), **Sheet** (workbook only), or **Option** (a plan-data flag).

**Finding 3: Analyze would carry about 20 rows.** Mitigation: rows are grouped under host-page sub-headers (Optimize, Stress Test, Scenarios, Planning Workbench, Build & Results) inside each of the three sections, and the popover scrolls. If this still feels heavy in review, the fallback is to move the sheet-only rows into one collapsed "Workbook sheets" sub-header.

**Always-on (third section)** is derived, not hand-listed: nav pages with no step gate and no flag gate, plus ungated sections (Asset Allocation inside Optimize, the four Planning Workbench sections). The always-on workbook sheets (Net Worth, Cash Flow, Balance Sheet, Executive Summary, Quality Control and similar, 9 non-optional modules) are not pages, so they are excluded from the popovers; they remain on Plan Features.

**Proposed placement** (verified = I found the UI that hosts it; unverified items are checked in phase 0):

| New group | Host page | Feature (type) | Status |
|---|---|---|---|
| Household & Cash Flow | Work Income | S-Corp vs LLC, Business Succession (Sheet/Section) | unverified |
| Household & Cash Flow | Social Security & Pensions | QLAC (Option) | verified |
| Accounts & Property | Rental Properties | Rental Property Income (Page) | verified |
| Accounts & Property | Home Equity Line | HELOC (Page, plan flag) | verified |
| Accounts & Property | Cash Reserves | Reserve Requirements (Page) | verified |
| Accounts & Property | 529 & Equity Compensation | Education Funding 529, Equity Compensation (Page hub, any-of) | verified |
| Accounts & Property | Other Assets & Debts | LTC/Life Policy (Option) | verified |
| Protection & Legacy | Insurance | Insurance Inputs (Page); Life Insurance Need, Existing Life Insurance, Disability Income, P&C / Umbrella (Section/Sheet) | partly verified |
| Protection & Legacy | Estate Inputs | Estate & Legacy (Page); Special-Needs Planning (Section) | verified |
| Taxes | Roth Conversion | Roth Conversion (Page) | verified |
| Taxes | Charitable Giving | Charitable Giving (Page); DAF Giving, QCD Giving (Option) | verified |
| Taxes | (workbook) | Lifetime Taxes, Tax Capacity, RMD Audit (Sheet) | unverified host |
| Analyze | Optimize | Social Security timing, Withdrawal Sequencing, HSA Drawdown, Tax-Loss Harvesting, Gain Harvesting (Section); Asset Location (Section); Next Housing Move, Housing Comparison, State Residency (Section) | verified except housing trio and Asset Location |
| Analyze | Stress Test | Monte Carlo, Survivor, LTC Stress, Divorce / QDRO (Section) | verified |
| Analyze | Scenarios | What-If / Scenario (Page) | verified |
| Analyze | Planning Workbench | Planning Workbench (Page) | verified |
| Analyze | Build & Results | Charts, Current vs Proposed, Methodology & Re-Run, Glossary (Sheet) | verified by catalog domain only |
| Track & Reconcile | Actual Spending | Spending Summary, Spending Tracker / YTD (Sheet/Section) | verified |
| Track & Reconcile | Account Reconciliation | Account Import (Page), Account Reconciliation (Sheet) | verified |

Consequences for the plan:
- The popover needs a **host-page map**. The step id already exists on most modules (`dashboard_step`, `extra_steps`) and the Optimize/Stress section list is declared in `dashboard_decomp_strategy_workspace.js`. Modules with neither need a small alias table (about 14 entries) kept next to `STEPS`, with a test that fails if a catalog module is unassigned. That test is what keeps the popover from silently dropping a new feature.
- The topic tag comes from the catalog `domain`, so no Python change.
- One page toggling several modules (Family & Business hub, Charitable Giving any-of, Stress Test) keeps its existing any-of rule; the popover shows each module's switch, and the page's visibility follows the existing gate.

### 5.5 Accessibility
Icon is a `<button>` with `aria-expanded`, `aria-haspopup="dialog"` and a label like "Manage features in Taxes, 2 off". Popover is a non-modal dialog. Switches use `role="switch"`. Changes are announced through the existing `navAnnouncer` live region. The badge is never the only signal (count is in the label).

## 6. Data and architecture

- **One source of truth:** the module catalog already declares each module's gate and `nav_group`. `nav_group` defaults to `domain`, and `DOMAINS` drives workbook order, so it must not be edited. Instead the client derives each feature's *nav* group from its `dashboard_step` → `STEPS[].group`, with a small alias table for features that have no step of their own. This avoids touching Python domain data.
- **STEPS** (in `dashboard.js`) gets new `group` values and titles; a new `NAV_GROUP_ORDER` per flow mode replaces implicit array order.
- **New module** `frontend/js/dashboard_decomp_nav_features.js` (icon, popover, derivation). New code goes here, not into `dashboard.js` (7,287 lines, with a size ratchet in `tests/test_frontend_size_ratchet.py`).
- **Flow switch state** in browser storage only (a per-viewer convenience), with a safe fallback when storage is unavailable.
- Needs to be verified in step 1 before building: how `watchNavGroupToggles` currently decides open/closed groups, what `help_registry.js` and the `PLAN_INDEPENDENT_STEPS` list key on (group names or step ids), and which tests assert on current group names.

## 7. Implementation plan

The estimates are relative. Check `/usage` against them as the work proceeds.

| Phase | Work | Model / effort | Usage vs. a 5-hour Pro session | Context drivers |
|---|---|---|---|---|
| 0. Recon | Grep tests, docs, help registry for group names and titles; read `watchNavGroupToggles`, `renderSteps` group loop (~70 lines), `navigation.js` `renderNav`. Produce a rename-impact list. | Sonnet, medium | Light | Grep only; never read `dashboard.js` or the row-model file whole |
| 1. Regroup, reorder, rename | Edit `STEPS` groups/titles, add group order; update the tests and docs that assert old names; update `SUGGESTED_NEXT` to the setup chain | Sonnet, medium | Moderate | Many small edits. **Likely most expensive step:** a test-fix loop over name assertions. Scope it with the phase 0 impact list so each test is fixed once |
| 2. Set up / Maintain switch | Segmented control, per-mode order, number hiding, default expanded group, suggested-next chain, attention count; storage fallback | Sonnet, medium | Moderate | Touches `renderSteps` (find with Grep, read ~120 lines at `offset`) |
| 3. Features popover | Host-page map and unassigned-module test (5.4), derivation of feature→nav group, three-section popover, count badge, switch wired to the Plan Features setter, a11y, mobile sheet; unit tests | Opus, high (design-heavy, easy to get dependency semantics wrong) | Heavy | Catalog gating reading, plan-features module (grep, then targeted reads) |
| 4. Verify | Node tests (`npm test`), `pytest -m "not slow"` with `-v -rfE` to a log file, browser walk-through at desktop and mobile widths with all features on and all off | Sonnet, medium | Moderate | Test-loop iterations; run Python in the background |
| 5. Docs and diagram | Run `python tools/generate_system_diagram.py` (new frontend file), update help text, Nav docs | Sonnet, low | Light | Docs-only parts need no CI wait |

Combined, this is a heavy but not session-ending job if phases are kept separate; do phases 1–2 and 3 in different sessions to keep the context small.

**Risks:** (a) hidden dependence of tests/help on group names (phase 0 answers this); (b) the popover disagreeing with Plan Features if it bypasses the shared setter (design rule in 5.3, plus a test that toggles through both paths); (c) renamed groups invalidating users' remembered open-group state (migrate or ignore stale keys).

## 8. Success criteria

- 8 headings instead of 12; no group with fewer than 2 pages (except pinned Plan Status).
- Any page reachable in two clicks or fewer from the page-load state; Maintain-mode routine pages in one.
- Popover and Plan Features show identical enabled/not-enabled state at all times.
- No change to workbook sheet order or saved data.
- Keyboard-only: icon, popover, toggles, and Esc all work; screen reader reads group, count, and each switch state.

## 9. Decisions and open items

**Decided by you:** free hand on structure; Set up / Maintain switch above the menu; hide-only toggle that keeps data; count badge on the icon; Account Tax Basis stays in Taxes; Actual Spending moves to Track & Reconcile; automatic default flow mode; sub-features included (on the condition that their location was analyzed, which section 5.4 now does).

**My calls to check while reading:** host-page placement rule (5.4); no icon on Plan Status or Settings; type tags (Page / Section / Sheet / Option); sheet-only features included; Find a Field kept for now; default Set up while required items are missing.

**Finalized 2026-11-04 after the usability review:** location (host page) is the home with the by-topic route via Plan Features; Maintain lifts only Track & Reconcile; sheet-only rows start collapsed; rows sorted by demand with a collapsed "More". Approved for implementation by the user.

**Left to the builder:** phase 0 verifies the unverified host assignments in 5.4 and the group-name dependencies in tests and help text; any host that cannot be verified goes under Build & Results as a sheet-only row. The independent reader check was not run.
