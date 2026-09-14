# Retirement System UI — Implementation Plan

Source: `retirement_system_design_critique.md` (code-level review of `frontend/index.html`, `admin.html`, `css/dashboard.css`, `css/admin.css`, `js/navigation.js`, `js/dashboard.js` and decomp files) plus `retirement_system_live_review_addendum.md` (live click-through of the running app across every guided-step group). This plan sequences every finding from both into actionable work, ordered by risk/effort/user-impact so the highest-stakes fix lands first.

## Guiding principle

`dashboard.js` (16,786 lines) renders nearly the entire app as concatenated HTML strings with no shared component layer. Every phase below is scoped to avoid a rewrite of that file — each item is a targeted, verifiable patch, not a refactor of the rendering architecture. A full componentization of `dashboard.js` is called out separately (Phase 4) as a longer-term option, not a prerequisite for the other fixes.

---

## Phase 0 — Data integrity (fix before anything else)

**0.1 Fix stale/zero KPI values on Distribution Strategy**
Live testing found that **Strategy → Distribution Strategy**, on both the **Levers** tab and the **Roth Conversion** tab, shows a KPI strip with Current Terminal NW **$0**, Post-Tax Inheritance (PTI) **$0**, Lifetime Taxes **—**, and Current Success Rate **40%** — while the same plan on **Reports & Review → Impact & Build History** shows the correct Terminal Net Worth ($6,288,862), Lifetime Taxes ($1,441,537), and Probability of Success (69.2%, 70.8% pre-change) for the identical build. Core annual spending and earned income *do* match correctly across both pages, so this is isolated to the Terminal NW / PTI / Success Rate values on this one KPI strip, not a wholesale data problem.
- Why this is Phase 0, not Phase 1: every other finding in this plan is a cosmetic or accessibility gap; this one actively misrepresents the plan's financial outcome to the user on a page whose entire purpose is to help them make a distribution decision. A user could reasonably read "$0 / 40%" and conclude their plan is failing when it isn't.
- Action: locate the data source feeding this specific KPI strip (likely in `planning_workbench_ui.js` or `dashboard_decomp_build_lifecycle.js` — whichever component renders the Levers/Roth Conversion tabs under Distribution Strategy) and confirm whether it's reading a stale snapshot, an uninitialized default, or a different (unbuilt) baseline than the Impact page. Repoint it at the same computed-results source the Impact page uses.
- Also decide on one consistent "no data yet" representation: right now the same underlying state shows as literal `$0` for two fields and an em-dash (`—`) for a third on the same strip — pick one convention (recommend em-dash/placeholder for "not yet computed," reserving `$0` for an actual zero value) and apply it everywhere this pattern appears.
- Verification: rebuild the plan, then check Terminal NW/PTI/Success Rate on Distribution Strategy (both tabs) against Reports & Review → Impact for the same build timestamp — values must match. Also verify after a fresh plan with no build yet, to confirm the "no data" state renders sensibly rather than as a misleading zero.
- Effort: S–M depending on where the stale reference lives, but blocks nothing else — do this first and independently of Phases 1–4.

---

## Phase 1 — Critical/shipped bugs (fix first, low risk, high confidence)

**1.1 Define the missing CSS custom properties**
`--brand`, `--text`, and `--well` are referenced in `dashboard.css` but never declared in either stylesheet's `:root` block, so the elements using them render with unset/inherited color today.
- Affected: `.plan-kpi-value` (`dashboard.css:619`), 3 more `--text` references (`:627, 630, 647`), 5 `--well` references (`:174, 199, 376, 383, 391-395`).
- Action: for each, decide the intended token — most likely map `--text`→`--ink`, `--brand`→`--accent`, `--well`→a new well/panel-background token consistent with `--bg`. Add the missing declarations to `:root` in `dashboard.css` (mirrored into `admin.css` if those selectors are shared).
- Verification: grep `dashboard.css` for `var(--brand`, `var(--text`, `var(--well` after the fix — zero results should remain undefined; visually confirm the affected elements (KPI value, whichever "well" panels use it) now render with real color in the running app.
- Effort: XS (under an hour). No JS changes required.

**1.2 Reconcile the duplicate accent-color dialect**
The "Build History" block (`dashboard.css:294-309`) uses `var(--accent,#0057b7)` — a different blue than the app's actual `--accent` (`#1f4f8f`) — via a fallback pattern that was never cross-checked against the real token.
- Action: replace the three `var(--x, #hex)` fallback declarations in that block with the real tokens (`var(--accent)`, `var(--border)`→confirm this maps to `--line`/`--line2`, `var(--card-bg)`→confirm maps to `--bg`/panel background). Remove the hardcoded hex fallbacks once confirmed the real tokens exist.
- Verification: visually diff the Build History panel before/after — the blue should now match every other accent-colored element (buttons, active nav state, etc.) in the app.
- Effort: XS. Do this in the same PR as 1.1 since both are token-file cleanup.

---

## Phase 2 — Accessibility & form semantics (foundational, touches every guided step)

**2.1 Add real `<label for="...">` elements to every form input**
Zero `<label>` elements exist anywhere in the codebase. Inputs rely on `aria-label` strings (confirmed at `dashboard.js:6312, 6383, 6401, 7156` and similar) or adjacent `.field-label` divs with no `for`/`id` link — so sighted users can't click a label to focus a field, and screen-reader association is inconsistent.
- Scope: this touches essentially every rendered form field across `dashboard.js` (hundreds of `<input>`/`<select>` calls) and the decomp files that build their own tables/cards (`dashboard_decomp_supplemental_tables.js`, `dashboard_batch_assumption_edit.js`, `planning_workbench_ui.js`, etc.).
- Recommended approach given the file size: **do not hand-edit 16,786 lines directly.** Instead:
  1. Write a small audit script (Python or Node) that scans the frontend JS for `.field-label` div + adjacent input patterns and outputs a checklist of every instance with file:line, so the work is trackable and nothing is missed silently.
  2. Establish one canonical pattern (e.g., a `renderLabeledField(id, labelText, inputHtml)` helper in `dashboard_shared_helpers.js`) that emits a proper `<label for>` + `<input id>` pair, and migrate call sites to it incrementally rather than inlining `<label>` tags ad hoc in 200+ places.
  3. Roll out file-by-file, smallest first (`dashboard_decomp_local_backups.js`, 110 lines) up through the largest (`dashboard.js` last), so each PR is reviewable.
- Verification: re-run the audit script after each file's migration — the checklist count should hit zero for that file. Spot-check with a screen reader (VoiceOver/NVDA) on at least one migrated page per phase.
- Effort: L (multi-week, incremental). This is the largest single item in the plan — track it as its own workstream, not a single PR.

**2.2 Contrast, touch target, and computed-style audit**
The critique couldn't verify actual rendered contrast/sizing from source alone.
- Action: once the app is runnable in this environment (or via a screenshot/live walkthrough), run the `design:accessibility-review` skill against the live UI for a proper WCAG 2.1 AA pass (contrast ratios, touch target sizes, focus states).
- Dependency: best done after Phase 1 (so the undefined-token bug isn't skewing contrast results) and can run in parallel with Phase 2.1.
- Effort: S, but blocked on having a live/rendered instance to audit.

---

## Phase 3 — Navigation integrity

**3.1 Make the redirect/workspace-merge behavior visible**
`navigation.js` silently reroutes nominal steps into consolidated pages: `STEP_REDIRECTS` (`navigation.js:12-24`, e.g. `ss_timing`→`income_retirement`, `roth_conversion`→`distribution_strategy`) and `REPORTS_REDIRECTS` (`navigation.js:6-11`, folding Detailed Results/Build Impact/Downloads/Plan Data Review into one `reports_and_review` tab). Users clicking a specific step land on a merged workspace without warning.
- Two viable fixes — pick one, don't do both (avoid redundant UI):
  - **Option A (recommended, smaller change):** Update the step list itself (`dashboard.js:20-416`) so labels reflect real destinations (e.g., rename "SS Timing" to "Income Workspace" or add a subtitle "→ part of Income Workspace"), removing the mismatch at the source.
  - **Option B (larger change):** Add breadcrumbs in the content pane showing the merge (e.g., "Income Workspace > SS Timing"), preserving the original step names but adding context on arrival.
- Recommend Option A first since it's a data/label change in one place (`dashboard.js:20-416`) rather than new UI, and reassess whether B is still needed after.
- Verification: manually click through every entry in `STEP_REDIRECTS` and `REPORTS_REDIRECTS` and confirm the landing page's visible title/label matches what the nav promised.
- Effort: S.
- **Confirmed live:** clicking the "Transactions" quick-nav button from Spending Model (step 5) jumps straight to "Actual Spending (This Year)" (step 9) — this reproduces the redirect/merge behavior outside of the `STEP_REDIRECTS` table itself, via the in-page quick-nav buttons on Spending Model, Distribution Strategy, etc. When implementing 3.1, make sure the fix (Option A relabeling) also accounts for these quick-nav buttons, not just the left-hand guided-steps list — a user can reach a "different than expected" page through either path.

---

## Phase 4 — Consistency & technical debt (schedule after Phases 1–3, lower urgency)

**4.1 Convert inline `style="..."` overrides to CSS classes**
67+ inline style attributes in `dashboard.js` alone (e.g. `dashboard.js:3162, 7299, 8077, 8347, 9429, 12460`) duplicate intent already expressible via existing classes/tokens.
- Action: audit-script pass (can reuse/extend the Phase 2.1 script) to enumerate every inline `style=` in `dashboard.js` and decomp files, group by repeated pattern (e.g. `color:var(--muted)`, `margin-top:4px`), and add matching utility classes to `dashboard.css` (e.g. `.text-muted`, `.mt-4`) so each instance becomes a class swap, not a rewrite.
- Effort: M. Not urgent — schedule opportunistically alongside Phase 2.1 file-by-file passes since both touch the same call sites.

**4.2 Consolidate duplicated table/card markup**
Lot-table, matrix-table, feature-card, and planning-case-card patterns are independently hand-implemented in `dashboard_decomp_supplemental_tables.js`, `planning_workbench_ui.js`, and `dashboard.js`.
- Action: extract one shared render helper per pattern into `dashboard_shared_helpers.js` (which already exists and is the natural home), starting with whichever pattern appears in the most places (table wrapper looks like the best first candidate). Migrate call sites one file at a time.
- Effort: M, ongoing. Treat as debt paydown rather than a blocking fix — no user-visible bug today, but risk of visual drift grows the longer it's left.

**4.3 (Longer-term, optional) Componentize `dashboard.js`**
The decomp files were extracted "byte-for-byte identical, no logic changed" from the monolith — a cosmetic split, not real modularization. If the team wants to invest beyond bug fixes, breaking `dashboard.js` into real modules (ES modules or a lightweight component layer) would make Phases 2 and 4 permanently easier to enforce going forward instead of being one-time cleanup passes.
- Not scoped in detail here — flag as a separate architecture decision, not a task to schedule alongside the fixes above.

**4.4 Fix badge/tag capitalization inconsistency**
Status badges are uppercase everywhere (OK, READY, OPTIONAL, LATEST, BUILD), but the recommendation-card tag renders lowercase **"info"** — confirmed live on both the SS/Pensions & Annuities and Spending Model pages, so it's a shared component, not a one-off typo.
- Action: find the shared "info" tag component (likely near the other badge rendering in `dashboard_shared_helpers.js` or wherever `PAGE RECOMMENDATIONS` cards are built) and capitalize it to match the rest, or apply consistent CSS `text-transform: uppercase` at the badge-component level so this class of bug can't recur.
- Effort: XS.

**4.5 Humanize auto-generated field labels**
"Ytd Remainder Earned Income Override" on Work Income reads like an un-humanized variable name (`ytd_remainder_earned_income_override`) where "YTD" should render as the acronym, unlike neighboring hand-written labels ("Earned Income Start Year," "Annual Earned Income").
- Action: find wherever field labels are auto-generated from snake_case field names (likely a shared "humanize" or "titleize" helper) and add an acronym exception list (YTD, IRA, RMD, HSA, HELOC, etc.) so generated labels capitalize known acronyms correctly. Audit for other auto-generated labels with the same issue while in there.
- Effort: XS–S.

**4.6 Remove internal identifier from Field Finder UI**
Settings → Field Finder's "Batch edit assumptions" panel displays the literal string `batch_assumption_edit_v1` in a plain text bar above the controls — reads like a leftover feature-flag/version tag rather than user-facing copy.
- Action: locate this string in `dashboard_batch_assumption_edit.js` and either remove it from the rendered output or replace it with a proper heading/description if it was meant to be user-facing.
- Effort: XS.

**4.7 Reconcile the two save-behavior banners**
Most pages show a blue "SAVE CHANGES — Edits are staged locally until you click Save Changes" banner; Spending Model and Actual Spending show a green "AUTO-SAVE ON NAVIGATION" banner instead (confirmed: it does fire an "Auto-saved." toast on navigation). These are two genuinely different save models in the same app, distinguished only by banner color and text — a user who's only seen the blue banner elsewhere could miss the switch and not realize navigating away already saved (or didn't need "Save Changes" clicked).
- Action: decide whether both save models are intentional; if so, make the distinction more visually obvious than banner color alone (e.g., a distinct icon or a one-line explainer the first time a user hits an auto-save page), or consider unifying to one save behavior across all workflow pages if the split isn't load-bearing.
- Effort: S (decision + copy/UI change), more if unification requires touching save logic per page.

---

## Suggested sequencing

| Phase | Item | Effort | Depends on |
|---|---|---|---|
| 0 | 0.1 Distribution Strategy KPI bug | S–M | — |
| 1 | 1.1 Undefined CSS tokens | XS | — |
| 1 | 1.2 Accent color dialect | XS | — |
| 3 | 3.1 Nav redirect visibility (incl. quick-nav buttons) | S | — |
| 2 | 2.2 Contrast/touch-target audit | S | Phase 1 complete, live instance available |
| 2 | 2.1 Label semantics (audit script → helper → rollout) | L | — |
| 4 | 4.1 Inline style → classes | M | Can run alongside 2.1 |
| 4 | 4.2 Shared table/card helpers | M | — |
| 4 | 4.4 Badge/tag capitalization | XS | — |
| 4 | 4.5 Humanize auto-generated labels | XS–S | — |
| 4 | 4.6 Remove internal ID from Field Finder | XS | — |
| 4 | 4.7 Reconcile save-behavior banners | S+ | Decision on intended save model |
| 4 | 4.3 Componentize dashboard.js | Open-ended | Team decision, not urgent |

Phase 0 is the one item that actively misleads users about their plan's outcome — fix it first and independently, it doesn't block or depend on anything else. Phases 1 and 3 are cheap and independent — bundle them into a single quick PR right after Phase 0. Phase 2.1 is the biggest lift and should be tracked as its own workstream with the audit script as the first deliverable, since it's the only item touching essentially the whole file. The new 4.4–4.7 items are all small and can be picked up opportunistically alongside whichever Phase 4 work is already in flight.

## Verification checklist (before calling any phase done)
- Re-check file line counts against `wc -l` for any file edited, per the known OneDrive sync truncation issue, before and after edits.
- Phase 0: rebuild the plan and confirm Terminal NW / PTI / Success Rate match between Distribution Strategy (Levers and Roth Conversion tabs) and Reports & Review → Impact for the same build; confirm the "no data yet" state (fresh plan, no build) renders as an intentional placeholder rather than a misleading $0.
- Phase 1: grep for the three token names confirms zero undefined references remain; visual confirmation in the running app.
- Phase 2.1: audit script count hits zero per migrated file; screen reader spot-check.
- Phase 2.2: run `design:accessibility-review` against the live app once available.
- Phase 3: manually walk every redirect entry (both the left-nav list and in-page quick-nav buttons) and confirm the landing page's visible label matches what was clicked.
- Phase 4: no functional regression — spot check that migrated table/card patterns render identically to their previous hand-built markup; confirm 4.4–4.6 changes are cosmetic-only with no data/logic impact.
