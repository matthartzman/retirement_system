# Retirement Planner — Live App Review Addendum

Follow-up to `retirement_system_design_critique.md` and `retirement_system_ui_implementation_plan.md`. That critique was code-only; this pass clicked through the actual running app (`START_APP.bat`, pywebview build) across People & Income, Spending, Assets & Protection, Strategy, Reports & Review, and Settings. It confirms two of the original findings directly in the UI and surfaces one new issue that's more urgent than anything in the original critique.

## New finding — stale/zero KPI values on Distribution Strategy (highest priority)

On **Strategy → Distribution Strategy**, both the **Levers** tab and the **Roth Conversion** tab show a KPI strip with:

- Current Terminal NW: **$0**
- Post-Tax Inheritance (PTI): **$0**
- Lifetime Taxes: **—**
- Current Success Rate: **40%**

The same plan, viewed on **Reports & Review → Impact & Build History**, shows Terminal Net Worth of **$6,288,862**, Lifetime Taxes of **$1,441,537**, and a Probability of Success of **69.2%** (or 70.8% pre-change). Core annual spending ($154,158) and earned income ($309,620) do match correctly across pages — so this isn't a wholesale data problem, it's specifically the Terminal NW / PTI / Success Rate trio on this one KPI strip that isn't wired to the actual computed results.

This matters more than the CSS/label issues in the original critique because it's a trust problem: a user glancing at the Distribution Strategy page would reasonably conclude their plan has $0 net worth and a coin-flip success rate, when the real numbers are far better. Recommend treating this as a P0 bug — find wherever this KPI strip's data source is bound (likely a `planning_workbench_ui.js` or `dashboard_decomp_build_lifecycle.js` component that reads a snapshot instead of the latest build) and fix it to pull from the same source as the Impact page. Also worth deciding whether "Lifetime Taxes: —" (em-dash for missing) vs. "$0" (literal zero) is the intended way to represent "not yet computed" — right now the same underlying "no fresh data" state is shown two different ways on one screen.

## Confirmed from the original code critique

- **No real `<label>` elements**: on Household & People, clicking directly on the "FULL NAME" column header text does not move focus into the adjacent input. Visually it reads as a label; it isn't wired as one. This reproduces the code-level finding live, in the actual DOM behavior, not just in source.
- **Badge/tag capitalization inconsistency**: status badges are uppercase everywhere (OK, READY, OPTIONAL, LATEST, BUILD) except the recommendation-card tag, which renders lowercase **"info"** — seen on both SS/Pensions & Annuities and Spending Model pages, so it's a sitewide component, not a one-off typo.

## New minor findings from this pass

- **Auto-generated label casing**: "Ytd Remainder Earned Income Override" on Work Income — every other field on that page is properly title-cased ("Earned Income Start Year," "Annual Earned Income"); this one reads like an un-humanized variable name (`ytd_remainder...`) where "YTD" should be capitalized as an acronym.
- **Inconsistent save-model messaging**: most pages show a blue "SAVE CHANGES — Edits are staged locally until you click Save Changes" banner, but Spending Model and Actual Spending show a green "AUTO-SAVE ON NAVIGATION" banner instead, and confirmed it does fire an "Auto-saved." toast on navigation. Two genuinely different save behaviors exist in the app (manual-staged vs. auto-on-navigate), and a user who's only seen the blue banner elsewhere could reasonably not notice the switch. Worth a pass to make the distinction more visually obvious (not just banner color) or unify the behavior.
- **Internal identifier leaking into UI**: Settings → Field Finder's "Batch edit assumptions" panel displays the literal string `batch_assumption_edit_v1` in a plain text bar above the controls — reads like a leftover feature-flag/version tag rather than user-facing copy.
- **Non-linear step numbering confirmed live**: clicking the "Transactions" quick-nav button from Spending Model (step 5) jumps to "Actual Spending (This Year)" (step 9) directly — validates the code review's finding that the guided-step numbering doesn't match actual click-through order once cross-links are used. Not necessarily wrong, but reinforces that the step list promises more linearity than the app delivers.

## What looked solid (no issues found)

Investment Holdings' lot-table (account/symbol/date/shares/price/lot-type/actions) rendered cleanly and consistently. SS/Pensions & Annuities' per-person income-stream cards were uniform with good unit hints (PCT, years). The Results explorer (32-sheet workbook viewer with column grouping/expand-collapse) was clean and readable at density. The Levers impact-ranking tables (ranked by TNW lift / success lift) were well-organized. Devtools (F12) are disabled in this build, so deeper contrast/computed-style verification still isn't possible without enabling them or exporting a page to a real browser.

## Recommended plan update

Insert a **Phase 0** ahead of the existing Phase 1 in the implementation plan: investigate and fix the Distribution Strategy KPI strip before anything else, since it's the only finding in either pass that actively misrepresents the plan's financial outcome to the user. Everything else here can slot into the existing Phase 4 (consistency/debt) alongside the inline-style and duplicated-markup cleanup.

## Post-implementation update (this session)

Phase 0 was investigated and fixed: `planningLeverBase()` in `dashboard.js` only read in-memory session variables (`lastBuildCompare`/`lastBuildSummary`), which reset to null on every app launch. Fixed to fall back to persisted `buildHistory` (localStorage), and further fixed `currentKpi()` to recognize the `inheritable_nw` key that the persisted history actually uses for terminal net worth (mirroring the alias already used by `planning_workbench_ui.js`'s `metricSummary()`). Live re-verification confirmed Lifetime Taxes now resolves correctly ($1,441,537). One remaining gap found during verification: `mc_success` in the persisted build history is stored as a raw fraction (e.g. 0.7) while the display path expects a whole-number percent (69.2) — a units mismatch not yet fixed, flagged for follow-up since it needs live devtools access (disabled in this build) to confirm the exact source safely.

Phase 3 (nav redirect visibility) was investigated and found to be a non-issue: the redirect-source step IDs are all `hidden:true` and never appear in the visible nav, and every actual click-through already uses accurate, descriptive labels. No change was made.

Phase 1 (CSS tokens) and Phase 4.4–4.6 (badge casing, YTD label, leaked internal ID) were all fixed and verified via the frontend test suite (54/54 passing) and targeted Python tests.
