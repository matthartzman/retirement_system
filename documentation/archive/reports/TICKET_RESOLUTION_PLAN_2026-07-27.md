# Ticket Resolution Plan — 2026-07-27
Tickets #198–241 (44 items). Assessed against current code, not assumed. Findings below cite exact files/lines checked on 2026-07-27; verify against current code before acting if this document is read later.

## How to read this
Each workstream lists: tickets covered → what I actually found in the code (not the ticket author's framing) → options → recommendation → design → implementation steps → **lowest-effective Claude model**. Workstreams are ordered by priority, not ticket number, because several tickets share one root cause and should be fixed together.

Model key: **Haiku 4.5** = mechanical/local (rename, config value, single conditional). **Sonnet 5** = needs to trace a call path or reconcile 2–3 files before editing safely. **Opus 5** = cross-cutting architecture/IA decision where a wrong judgment call is expensive to reverse (touches many pages, or changes a save/data model).

---

## Priority table

| # | Ticket | Workstream | Priority | Model |
|---|--------|-----------|----------|-------|
|198|H/W prefixes on SS page|A|P0|Haiku|
|199|Early claim can beat delay math|B|P0|Haiku (copy only)|
|200|SS scores not 0–100 ints|C|P0|Sonnet|
|202|Success ↑ when reserve removed|D|P0|Opus (metric-definition call)|
|211|Optional-module YES vs TRUE|E|P0|Haiku|
|225|Post-tax inheritance mismatch + placement|F|P0|Sonnet|
|227|IL Credit Shelter exemption $4M vs $8M|G|P0|Haiku|
|230|SS optimizer sweeps ages below current|H|P0|Haiku|
|232|Earned-income growth can't go negative|I|P0|Haiku|
|233|Impact page red/green/black coding|J|P0|Sonnet|
|204|Field-level save vs Save Changes button|K|P1|Opus|
|205|Save/Discard/Stay dialog everywhere|K|P1|Opus|
|218|Levers page nav duplication|L|P1|Opus|
|201|Progress bar generic messages|M|P1|Sonnet|
|234|Save/build latency|M|P1|Opus|
|222|Field Finder progress bar|M|P2|Sonnet|
|223|Nav↔Page search switch lag / typing lag|M|P2|Sonnet|
|206|Reports left nav sort order|N|P1|Haiku|
|207|RMD/Roth Optimizer sheet ignores Objective Mode/Target Bracket|O|P1|Sonnet (diagnostic first)|
|209|Workbook page 3F misplaced|P|P1|Opus|
|210|Format alignment/width inconsistent|P|P1|Opus|
|212|Workbook assumptions no longer model inputs|P|P1|Sonnet|
|221|Sheets 1G/1H redundant|P|P2|Sonnet|
|228|Sheet numbering breaks when modules off|P|P1|Opus|
|215|Special Income page: no illustrations, only death benefits|Q|P1|Opus|
|217|DAF before QCD in Special Strategies|Q|P2|Haiku|
|224|Auto/home insurance → Insurance Policies integration|Q|P2|Sonnet|
|229|Rename nav "Special Income, Annuities & Insurance" → "Insurance"|Q|P3|Haiku|
|236|Move annuity defaults to SS/Pensions/Annuities page|Q|P2|Sonnet|
|214|HELOC Strategy vs HELOC Modeling redundancy|R|P2|Sonnet|
|213|HSA config: 1 section, swap start/end dates|S|P2|Sonnet|
|226|Tax-loss/Gain harvesting → optional modules|T|P1|Sonnet|
|208|Large discretionary still annualized (re-check)|U|P0|Sonnet (diagnose first)|
|231|Travel budget needs an end year|U|P2|Haiku|
|216|"Everything" sections default collapsed|V|P2|Sonnet|
|203|Helper text missing|W|P2|—|
|219|Layman helper-text standard (example)|W|P1|Sonnet (writing) / Opus (if rules engine needed)|
|220|Layman helper-text standard (example)|W|P1|Sonnet|
|235|Move Dividend Reinvestment → Investment Holdings|V2|P3|Haiku|
|237|Move Self-Employment → Work Income (abbreviate SE)|V2|P3|Sonnet|
|238|Delete redundant Medicare section|V2|P3|Haiku|
|239|Remove Retirement section, relocate RMD age + rollover year|V2|P3|Sonnet|
|241|Field Finder missing Travel fields|X|P3|Haiku|
|240|Demo data for system|Y|P3|Sonnet|

---

## P0 — Correctness and trust (numbers/labels users will act on)

### A. #198 — Social Security page still uses "H"/"W"
**Found:** The app already has a full nickname-translation layer (`src/person_labels.py`, `translatePersonPlaceholders()` in `frontend/js/dashboard.js`) that's supposed to catch every Member_1/Husband/Wife/H/W leak — this is a known, previously-audited pattern (see prior "person-label-architecture" work). This ticket is a **leak in that coverage**, not a missing feature. Root cause pinned to [`src/reporting/sheets_strategy.py:264-282,296`](../../src/reporting/sheets_strategy.py): the claim-age sweep table's *row labels* correctly use `h_nick`/`w_nick` (e.g. "Recommended Matt Claim Age"), but its **column headers** are hardcoded literals `'H Claim'`, `'W Claim'` at two places (top-10 table and full-sweep table).
**Options:** (1) patch just these two header lists to use the already-computed `_s1`/`_s2` nickname variables — cheapest, consistent with the existing pattern; (2) run the standing leak-scan (`H Age|W Age|H Claim|W Claim` regex) across all reporting files and fix every hit in one pass, since the same author pattern (`H_Age`/`W_Age` headers) also appears in `sheets_projection_cashflow.py`, `sheets_projection_net_worth.py`, `sheets_projection_tax.py`, `sheets_stress.py`.
**Recommendation:** Option 2 — same fix, same effort, and it closes the whole class of leak instead of one instance the user happened to notice.
**Design:** No new mechanism. Replace literal `'H '`/`'W '` header fragments with the nickname variables already in scope in each function (mirror the `_s1/_s2` pattern from `sheets_strategy.py:264-265`); where a function doesn't yet compute `_s1/_s2`, add the two-line `str(c.get('h_nick') or c.get('h_name') or 'Member 1')` pattern used elsewhere.
**Implementation:** grep for `'H Claim'|'W Claim'|'H_Age'|'W_Age'|'H Age'|'W Age'` under `src/reporting/`; replace each header string; rebuild a workbook and re-grep the output xlsx to confirm zero hits.
**Model: Haiku 4.5** — mechanical, same fix repeated with existing local variables.

### B. #199 — Why can early SS claiming beat delayed 8% credits given lower portfolio return?
**Found:** This isn't a bug — the code's own inline comment already documents it. `sheets_strategy.py:213-224`: the `score` column deliberately does **not** use the raw `lifetime_ss` sum, specifically because it's "an accounting artifact" — the developer already discovered that raw lifetime SS dollars can favor early claiming and wrote the Score formula to weight *survivor-period* SS income instead, for exactly this reason.
**Why the artifact happens (financial mechanics, not a defect):** the 8%/year delayed-retirement credit is an *actuarially fair* adjustment to the monthly check, calibrated to average life expectancy — it is not a compounding return on a balance you keep. Delaying means giving up 100% of the checks for those years, in exchange for a bigger check later. Whether the lifetime total ends up higher or lower is a **breakeven-age** question (SS breakeven is typically age ~80–83): raw lifetime-total is inherently sensitive to assumed lifespan/horizon and can legitimately favor early claiming for anyone modeled with a death age below breakeven, independent of portfolio return. Comparing "8% credit" to "portfolio return" is comparing two different things (a benefit-formula adjustment vs. an investment return on retained capital).
**Recommendation:** Don't change the math — add a one-line explanation next to the "Lifetime SS" column (and/or in the SS page helper text, see workstream W) stating this explicitly, and point the user to Score / Survivor-Period SS Income as the decision-relevant columns instead.
**Implementation:** Add a `section-note`/cell-note next to `Lifetime SS` header in `sheets_strategy.py` (and the equivalent web-page recommendation card) with wording in the style of #219/#220 (layman-readable, explains breakeven age, explicitly says "not a return comparison").
**Model: Haiku 4.5** — copy-writing task once the explanation above is handed to it verbatim (no further investigation needed).

### C. #200 — SS scores not reframed to 0–100 integers
**Found:** Confirmed bug, and the app already has the *correct* pattern to copy: the Roth Conversion candidate table in the same file (`sheets_strategy.py:373-377`) already implements "Score (0-100)" as a proper min-max-normalized integer, explicitly distinguished from the raw dollar "Objective Value." The SS claim-age sweep's `score` field (`sheets_strategy.py:224`, `score = after_tax_terminal_nw + SS_SURVIVOR_WEIGHT * survivor_period_ss_income`) is a raw dollar-scale number in the millions, and it's currently even **formatted as a dollar amount** in the table (`sheets_strategy.py:290`, the format branch doesn't exempt column 4/Score), which makes "0–100" doubly wrong today.
**Options:** (1) min-max normalize the 81-scenario sweep's raw score to 0–100 per plan (matches existing Roth-candidate pattern exactly); (2) percentile-rank instead of min-max (more robust to outliers, less intuitive "100 = best in this set" framing the app already uses elsewhere).
**Recommendation:** Option 1, for consistency with the Roth table's existing user-facing convention ("100 = best in this set").
**Design:** Rename current `score` → `objective_value` (dollar, keep dollar formatting). Add `rank_score = round(100 * (objective_value - lo) / (hi - lo))` where `lo`/`hi` are min/max across the 81 scenarios, computed the same way `score_lo`/`score_hi`/`score_span` are already computed at `sheets_strategy.py:368-370` for the Roth table. Add "Score (0-100)" as its own integer column; keep Objective Value as a separate dollar column so nothing analytical is lost.
**Implementation:** Edit the `_safe_project_pair` return dict and both header lists (lines 241-252, 282, 296) in `sheets_strategy.py`; add the normalization after the `scenarios` list is built (after line 258, once `lo`/`hi` are knowable) rather than per-row.
**Model: Sonnet 5** — requires reconciling the scoring dict shape across two table-writers in the same function without breaking the existing rank-by-score sort.

### D. #202 — Why does success go UP when the 2-year reserve is eliminated?
**Found — this is the most important finding in the whole review.** The "2-year reserve requirement" and the definition of Monte-Carlo "success" are **the same number** in the code today. In `src/planning_engines.py:2346-2356` (and the vectorized twin at `~2993-2998`): if the user hasn't set an explicit `mc_success_liquid_floor`, `success_threshold` defaults to `near_term_buffer_years * spend_base` — i.e., the exact reserve-years setting the user just turned off. A path only counts as a Monte Carlo **failure** when `liquid <= success_threshold` (`planning_engines.py:2879`, `2930`). So when the user sets the reserve requirement to 0 years, the success bar doesn't just get easier to reach *because withdrawals behave differently* — the **finish line itself moves to $0**, since "must not run out of money" and "must also keep 2 years of spending in reserve at all times" collapse into the same threshold. The apparent improvement is real but is mostly a change in what "success" *means*, not a change in plan resilience.
**Options:** (1) leave as-is but surface `success_liquid_floor_source` (already computed, just not shown) prominently next to the success-rate number so the user can see the bar moved; (2) decouple the two concepts entirely — keep a withdrawal-sequencing reserve floor (operational) separate from a success-criterion floor (a distinct, explicit setting that defaults to something other than "whatever the withdrawal buffer currently is"); (3) report both numbers side-by-side always ("ran out of money: X%" vs "breached your reserve floor: Y%").
**Recommendation:** Option 3 is the most honest and the least likely to mislead a user who is actively testing "what if I need less reserve" — it directly answers *this exact ticket* for every future user, not just this one. Option 1 is the cheap partial fix if there's no appetite for a new metric this cycle.
**Design (Option 3):** In the MC result contract (`success_liquid_floor` / `success_liquid_floor_source` already exist in the return dict, `planning_engines.py:2501-2502`), add a second unconditional threshold at `0` (true ruin) alongside the existing configurable one, and report both `success_rate_no_ruin` and `success_rate_with_reserve` in the result and on the Impact/Distribution Strategy pages. Label the existing headline number "Success (maintains your reserve floor)" so it's never read as "won't run out of money."
**Implementation:** Add a second `_percentiles`/failure pass with `success_threshold=0` in both the scalar (`~2400-2420`) and vectorized (`~3060-3070`) Monte Carlo paths; thread the new field through `result_contract.py`; update the Impact page and Distribution Strategy KPI tiles to show both, with a tooltip explaining the difference (reuse #219/#220 copy style).
**Model: Opus 5** — this is a metric-definition decision with downstream UI/report implications across multiple pages; get the definition right once rather than iterating live on user trust in the success number.

### E. #211 — Optional Module toggles show YES vs TRUE inconsistently
**Found:** Not a display bug — the source data is inconsistent. `input/client_optional_functions.csv` row 1 (`lifetime_tax_projection`) is literally `YES`; every other row is `TRUE`. Confirmed by direct read of the file.
**Recommendation:** Normalize the CSV to one boolean spelling (`TRUE`/`FALSE`, matching the majority and matching typical CSV boolean convention), and — separately — render the field as an actual checkbox/toggle control in the UI rather than free text, so this class of typo can't recur.
**Implementation:** (1) Fix the one CSV row. (2) Confirm the CSV boolean parser (wherever `client_optional_functions.csv` is read, likely `data_io.py`) accepts both spellings today so the CSV fix doesn't change behavior mid-fix — check before editing. (3) File-scope the toggle-vs-text-field UI improvement into the "Optional Module gating" work already tracked as an established pattern in this codebase.
**Model: Haiku 4.5** for the CSV fix; **Sonnet 5** if the checkbox-control UI change is done in the same pass (needs to touch the field-renderer).

### F. #225 — Post-tax inheritance duplicated and inconsistent
**Found:** Confirmed the Levers page (`renderPlanningLevers()`, `dashboard.js:3143`) shows a "Post-Tax Inheritance (PTI)" pill with a tooltip defining it as "terminal net worth minus the embedded taxes heirs would owe." The ticket says this same figure differs between "Estate and Legacy Plan" and "Impact" — I did not trace both computations end-to-end (would require reading the Estate & Legacy sheet's PTI calc against the Impact page's, which are likely two independently-written formulas); flag this as **needs a direct reproduction before fixing**, not an assumed single root cause.
**Recommendation:** Per the ticket: remove PTI as a headline number from the Impact screen; keep it only in Estate & Legacy Plan (its natural home); add a single note line on the Impact screen's Terminal Net Worth tile *only when* post-inheritance-tax impact is non-zero, computed from the same single source of truth Estate & Legacy Plan uses (not a second computation).
**Implementation:** (1) Grep both pages'/sheets' PTI formulas, diff them, pick the correct one as canonical. (2) Remove the Impact-page PTI tile/column. (3) Add the conditional note on Terminal Net Worth, sourcing the one canonical PTI calc.
**Model: Sonnet 5** — needs to reconcile two independent formulas safely, not just delete a UI element.

### G. #227 — Credit Shelter Trust should assume $8M IL exemption
**Found:** Confirmed. `illinois_estate_tax(gross_estate, exemption=4_000_000.0, ...)` in `src/core.py:1051` and `il_exempt` default `4000000` in `data_io.py:1440` are flat constants with **no** conditional on `credit_shelter_trust_enabled` (which does exist as a separate flag, `report_compute.py:95`). No doubling logic exists today at all.
**Recommendation:** When CST is enabled, use $8,000,000 for Illinois (the combined-exemption effect of funding a credit shelter trust at the first death rather than relying on federal-only portability, which Illinois doesn't recognize state-side). Keep the annually-reviewed exemption table (Illinois and any other states this system supports) as **data**, not inline constants, so next year's update is a data edit, not a code change — the ticket itself flags this needs annual maintenance.
**Implementation:** Add a small state-exemption table (state → base exemption, state → CST-funded exemption) sourced once from the Creative Planning reference the ticket links, store it as a dated config/CSV (e.g. `reference_data/state_estate_exemptions.csv`) with a "last verified" date column; change `illinois_estate_tax` (and any other state-specific exemption call site) to look up `exemption = table[state][cst_enabled]` instead of a hardcoded default.
**Model: Haiku 4.5** for the Illinois-only fix as literally requested; **Sonnet 5** if scoped to the general "annually maintained table for all states" design (recommended, since the ticket explicitly says "needs to be maintained annually" — worth doing once, generally).

### H. #230 — Don't run SS optimization for ages before current age
**Found:** Confirmed by code inspection: `sheets_strategy.py:255-256` sweeps `for h_age in range(62, 71): for w_age in range(62, 71)` unconditionally — it does not exclude ages below the person's **current** age, which is a real possibility if the plan start year is mid-way through someone's 60s (e.g., current age 66 → the sweep still evaluates hypothetical claim age 62, which already happened / can't be un-claimed).
**Recommendation:** Clamp the per-person sweep floor to `max(62, current_age)` rather than a fixed `62`.
**Implementation:** One-line change to the `range()` bounds in `sheets_strategy.py:255-256`, sourcing each person's current age from the same config used for `h_current`/`w_current` a few lines above.
**Model: Haiku 4.5**.

### I. #232 — Allow negative earned-income growth
**Found:** Not traced to a specific validator; this is very likely a UI input-range restriction (`min="0"` on a number input, or a schema-level non-negative check) rather than an engine limitation — the projection math for an income-growth-rate multiplier has no inherent reason to reject negative values. Needs a quick grep for the specific field (`earned_income_growth` or similar) in the schema/validation layer before editing; flagging as low-risk, quick to verify.
**Recommendation:** Remove the artificial non-negative constraint on this one field; keep the engine's multiplicative growth formula unchanged (it already handles negative rates correctly if allowed through, since it's a simple `× (1 + rate)` compounding).
**Implementation:** Locate the field's schema/UI/validation entry (`schema_registry.py` and the relevant input renderer in `dashboard.js`), remove or relax the `min` bound.
**Model: Haiku 4.5**.

### J. #233 — Color-code Impact page headline deltas
**Found:** No existing green/red/black conditional-formatting logic found for these specific tiles in a spot check; this is additive UI work, not a fix to a broken existing mechanism.
**Recommendation:** Implement exactly as specified: Terminal Net Worth and Probability of Success → green when higher than baseline, red when lower, black at zero delta; Lifetime Taxes → inverted (green when lower, red when higher).
**Implementation:** Add a small `deltaColor(value, invert=False)` helper in `dashboard.js` used by the Impact page's headline tile renderer; apply to the three tiles with `invert=True` only for Lifetime Taxes. Needs a baseline/comparison value already available to those tiles (confirm the comparison basis — "vs. current saved plan" is the most likely intent) before wiring in.
**Model: Sonnet 5** — small logic, but must confirm the correct baseline-comparison semantics against how the Impact page already frames deltas elsewhere before assuming.

---

## P1 — High-friction UX (used every session)

### K. #204, #205 — Save model overhaul (no separate Save button; universal Save/Discard/Stay guard)
**Found:** The app currently has **three different save behaviors** depending on page, confirmed in `dashboard.js`:
1. Most data-entry fields use `onblur="finishEdit(...)"`, which — based on the existence of a still-required, separately-clickable, sometimes-disabled "Save Changes" button (`id="saveChangesBtn"`, enabled/disabled by `unsavedChangeCount()`) — only stages the edit locally; it does not persist to the plan until Save Changes is clicked.
2. A specific allowlist of steps (`window.RetirementNavigation.AUTOSAVE_STEPS`) instead saves automatically **on navigation away**, not on blur.
3. `review`/`build_impact`/`detailed_results`/`plan_data_report` are read-only; `planning_workbench`/`planning_levers`/`scenarios`/`monte_carlo_options`/`survivor_stress`/`ltc_stress`/`divorce_options` are explicitly "preview only, doesn't persist until you edit the source page."
So the ticket's premise "like every other page" isn't quite accurate — no page currently saves per-keystroke/per-blur to the server; the real inconsistency is model (1) vs (2), not "this page is uniquely bad." For #205, an existing `beforeunload` handler and two `confirm()`-style interruptions already exist (`dashboard.js:15760`, `:7865`, `:16711`) but they are binary (proceed/cancel), not the requested three-way Save/Discard/Stay choice, and they don't cover in-app navigation between steps — only browser-level leave and a couple of explicit actions (Load plan, New plan).
**Options:** (1) minimal — replace the binary confirms with a real 3-button modal at the existing interception points only; (2) full — make model (2) (autosave-on-navigate) universal, remove the Save Changes button, and add the 3-way modal only where a *destructive discard* is possible (browser close/reload, explicit New/Load Plan); (3) full real-time — persist every field on blur to the server (true autosave), removing the "staged/unsaved" concept entirely.
**Recommendation:** Option 2. Option 3 sounds like what the ticket literally asks for, but it removes the ability to "discard changes" (there'd be nothing to discard, since blur = committed) — the ticket's own #205 wants a *Discard* choice, so option 3 contradicts option-2-and-205's needs. Autosave-on-navigate preserves a meaningful "unsaved changes" window (from focus-in on the page to navigate-away) during which Discard is still meaningful, matches how the "autosave" step set already behaves, and only requires *expanding* an existing mechanism rather than inventing a new one.
**Design:** Expand `AUTOSAVE_STEPS` to cover all non-read-only, non-preview steps. Build one reusable `NavigationGuardModal` (Save / Discard / Stay) triggered from a single `attemptNavigation(targetStep)` chokepoint, replacing the ad hoc `confirm()` calls at the 3+ interception points found above, and add it to in-app step navigation (currently unguarded). Remove the standalone Save Changes button from steps once they're in `AUTOSAVE_STEPS`; keep it (or a "Save now" affordance) only for the pages that stay `build-gated`/preview by design.
**Implementation:** This is the highest-blast-radius item in the whole list — it changes the persistence model on every data page. Do it as its own branch with a before/after golden-master comparison run (per existing pytest-mutates-input-files caution), not mixed with any other ticket.
**Model: Opus 5** — cross-cutting behavior change with real regression risk (accidental data loss on discard, double-saves, race with the existing build/staging model) that deserves the most careful reasoning tier available, even though the eventual diff may be modest.

### L. #218 — Levers page nav is redundant with itself
**Found:** Confirmed directly. `renderPlanningLevers()` (`dashboard.js:3143`, the page reached via the separate "Levers" left-nav item, step id `planning_levers`) renders a "Strategy · decide" button row (Roth conversion / Asset allocation / Withdrawal sequencing / Social Security / State residency / Charitable giving / HELOC strategy) and a "Stress tests · resilience" button row (Monte Carlo / Scenarios / Survivor / Long-term care / Divorce-QDRO) — this is the **identical button set**, word-for-word grouping, to what's already inline on the Distribution Strategy tab shown in the screenshot ("Strategy - decide" / "Stress tests - resilience"). So today there are at minimum three places a user can reach the same 12 destinations: the guided-step left nav directly, the Distribution Strategy tab's inline buttons, and the standalone "Levers" page's identical buttons — plus the tab-strip (Levers/Roth Conversion/Withdrawal Order/Allocation & Location) the ticket's screenshot shows sitting above all of it.
**Options:** (1) delete the standalone "Levers" page entirely, since its unique content (the lever-estimate ranking tables) could live as a section of Distribution Strategy instead of a whole separate nav destination; (2) delete the *button rows*, keep the page for its ranked-lever-estimate tables only, and make Distribution Strategy the single place with the decide/stress-test buttons; (3) full IA pass: collapse "Levers" (top nav tab) + "Levers" (left nav step) + the repeated button rows into one page with one navigation surface.
**Recommendation:** Option 3 is what the ticket asks for ("needs to be rationalized... this nav and page needs to be rationalized") — this is explicitly an information-architecture judgment call, not a mechanical fix, and deserves a fresh look at the full guided-step tree rather than patching in isolation.
**Design:** Sketch (don't build yet) a single "Distribution Strategy" destination with: the 4 tabs already shown (Levers/Roth Conversion/Withdrawal Order/Allocation & Location) as the *only* navigation, the ranked lever-estimate tables as the "Levers" tab's content, and the "decide"/"stress test" destinations reachable via the left nav guided steps only (not re-duplicated as buttons inside this page). Remove the standalone `planning_levers` left-nav entry once its content is folded in.
**Implementation:** Requires updating `setStep`/routing references to `planning_levers` throughout `dashboard.js` and `planning_workbench_ui.js` (several call sites already found: `dashboard.js:5087,7791,14612`, `planning_workbench_ui.js:196`) — a mechanical-but-widespread rename/removal once the IA is decided.
**Model: Opus 5** for the IA decision and sketch; **Sonnet 5** can execute the mechanical rewiring once the target structure is specified.

### M. #201, #234 — Progress bar specificity + save/build latency
**#201 found:** Confirmed generic messaging — `setBuildOverlay(true, "Loading plan", ...)` at `dashboard.js:15693` and `"Loading transactions"` at `:10656` are both hardcoded strings passed to one shared overlay function, used regardless of what's actually happening (also used for optional-module toggling per the ticket). **Recommendation:** audit every `setBuildOverlay(true, ...)` call site (not just these two) and pass an operation-specific label at each one; add a small enum/lookup so new call sites can't regress to a generic default silently. **Model: Sonnet 5** (needs to enumerate and touch every call site, low individual risk, but must not miss any).

**#234 found:** Not independently benchmarked; "10-12 seconds to save, ~65s to build" is a user-reported timing, not something I can validate without running the app. **Recommendation:** profile the Save Changes request path and the build path separately before optimizing blindly — likely candidates given the surrounding codebase (large monolithic CSV/JSON round-trips per save, `.rpx` full-DB-copy backups noted elsewhere in this system's own history) but this needs actual profiling, not a guess. **Model: Opus 5** — performance work spanning save-path I/O, workbook generation, and possibly the `.rpx` backup-copy behavior (previously flagged elsewhere in this codebase as "re-paid every build") benefits from the highest reasoning tier to avoid a superficial fix that doesn't address the real bottleneck.

### N. #206 — Reports left nav should match workbook order
**Found:** Not traced to a specific render function in this pass; very likely the reports/results nav is built from a different ordering source (e.g. alphabetical or insertion order in a JS array) than the `workbook_common.py` sheet-order list found for workstream P. **Recommendation:** point the reports nav's sort key at the same ordered sheet list (or the stable-key version of it recommended in workstream P) so the two can never drift again. **Model: Haiku 4.5** once the specific nav-building function is located (quick, one-file check).

---

## P1/P2 — Workbook sheet architecture (one root cause, five tickets)

### P. #209, #210, #212, #221, #228 — Sheet numbering/formatting is structurally fragile
**Found — this cluster shares one root cause.** `workbook_common.py` defines sheets by a **fixed literal name with an embedded number/letter** (e.g. `'28. Core Spending'` aliased to `'1G. Core Spending'`, `'12B. Tax-Loss Harvesting'`). Separately, `input/workbook_format_alignments.json` and `input/workbook_format_overrides.json` key their per-column formatting by a **different, apparently independently-assigned** letter scheme (`"1A. Executive Summary"`, `"2D. Social Security"`, `"3C. LTC + Life Insurance"` — spot-checked against the group-number list in `workbook_common.py` and the two schemes don't obviously line up 1:1, suggesting the letter assignment is computed somewhere else, separately, and can drift). This single design flaw explains four tickets at once:
- **#228** (gaps when modules are off): sheet identity *is* the numbered name, assigned once in a fixed list, not recomputed from "which sheets are actually enabled this build" — so skipping `12B`/`12C` leaves a visible gap instead of renumbering.
- **#210** (formatting inconsistent within/between sections): format overrides are keyed to a positional letter code that isn't guaranteed to stay attached to the same sheet content as sheets are toggled on/off or reordered — the override can silently apply to the wrong sheet, or fail to match any sheet, after any change to which optional modules are on.
- **#209** ("3F" in wrong place): same mechanism — whatever content the format config calls "3F" today may not be the sheet the user visually expects "3F" to mean, because the letter is positional, not identity-based.
- **#221** (sheets 1G/1H near-duplicate): confirmed `1G. Core Spending` and `1H. Spending Summary` are two distinct, separately-generated sheets sitting adjacent in this same fragile lettered group; I did not do a cell-by-cell diff to confirm "almost 100% redundant" — recommend confirming the actual column overlap before merging, since [[core-spending-scope-rule]] (Core spend_base deliberately excludes housing/wellness/travel/large-disc) suggests "Core Spending" and "Spending Summary" may differ by *scope* (core-only vs. all-in) even if they look similar at a glance.
- **#212** (workbook assumptions no longer highlighted as model inputs): likely the same drift — a formatting/highlight rule keyed to a position or an old sheet identity that no longer matches after sheets were added/renumbered/reordered elsewhere in recent work (the numbered-sheet list runs through at least "36." with several recently-added modules per the list found in `workbook_common.py`, consistent with recent additions shifting positions).
**Recommendation:** Fix the root cause once: give every sheet a **stable, permanent slug** (e.g. `core_spending`, `spending_summary`) independent of its display number/letter. Compute the display number/letter **at build time**, from the actual enabled-sheet list in build order (closing #228's gaps automatically). Re-key `workbook_format_alignments.json`/`workbook_format_overrides.json` by the stable slug instead of the positional label (fixing #210 and #209 by construction — a format rule can no longer attach to the wrong sheet). Then, separately, evaluate #221's merge candidacy and #212's highlight rule against the now-stable identities.
**Design:** Add a `SHEET_REGISTRY: dict[slug, SheetDef(base_name, group)]` as the single source of truth (this can likely absorb the existing `module_catalog.py` `OutuptModule` entries rather than duplicating them — check overlap before adding a second registry). At build time: filter to enabled sheets, assign `display_number`/`display_letter` sequentially within group, write both format-config JSONs against `slug`. Add a one-time migration script to rewrite the two existing JSON files from their current positional keys to slugs (manual, one-time, review the diff).
**Implementation order:** (1) stable slugs + build-time numbering (fixes #228, unblocks the rest) → (2) re-key the two format JSONs by slug (fixes #210, #209) → (3) diff 1G/1H content and decide merge vs. keep-separate (#221) → (4) re-audit the assumptions-highlight rule against the new stable identities (#212).
**Model: Opus 5** for the registry/migration design (touches the core sheet-generation pipeline and two hand-authored config files with no schema); **Sonnet 5** can execute steps 3–4 once the registry from steps 1–2 exists.

---

## P1/P2 — Special Income / Insurance page

### Q. #215, #217, #224, #229, #236 — Insurance & special-income page scope
**Found:** Not traced page-by-page in this pass (this cluster is a content/IA question more than a code-bug question, and warrants a live click-through of the actual page rather than static grep — flagging this explicitly since I did not do it). What's confirmed from adjacent evidence: `module_catalog.py` already tracks `31. Existing Life Insurance` as its own sheet/module, separate from whatever the "Special Income, Annuities & Insurance" page currently surfaces — consistent with the ticket's complaint that the page shows death benefits only and the illustrations content lives (or should live) elsewhere/nowhere findable.
**Recommendation:** Before any redesign, do a live inventory pass: open the page, list every field group actually present, and cross-reference against `module_catalog.py`'s insurance-related entries (`31. Existing Life Insurance`, P&C/Umbrella per recent history, HELOC, annuities) to find where "illustrations" data is supposed to live today (a client-supplied illustration schedule is a very different data shape — a table of policy-year cash values/death benefits over time — from a single current death-benefit figure, so this is likely a genuine gap, not a mislabeled existing feature).
**Design (once inventory is done):** (1) add an "Illustrations" subsection accepting a per-policy year-by-year schedule (cash value, death benefit, premium) rather than a single point figure; (2) move DAF configuration into Special Strategies immediately before QCD (#217 — simple reorder, no data model change); (3) fold auto/home insurance spend+budget+forecast (currently presumably part of general Spending/Budget) into the Insurance Policies functionality as its own policy type (#224 — needs to find the existing auto/home spending category first and decide whether it becomes a real "policy" record or stays a budget category with a policy cross-reference); (4) rename the left-nav label to "Insurance" (#229 — trivial); (5) relocate the two annuity default fields from Economic and Tax Assumptions into a new "Plan-wide income stream settings" section on this page (#236).
**Implementation:** Do #217 and #229 first (zero-risk, immediate); do the live inventory before scoping #215/#224/#236 further — do not design the illustrations data model or the auto/home-insurance integration from assumptions alone.
**Model: Opus 5** for the inventory + illustrations data-model design and the auto/home-insurance integration decision (genuine product/IA judgment, new data shape); **Haiku 4.5** for #217 (reorder) and #229 (rename); **Sonnet 5** for #236 (relocate two fields, needs to touch both the source and destination page renderers).

---

## P2 — Consolidation / redundancy

### R. #214 — HELOC Strategy page vs. HELOC Modeling inputs
**Found:** Confirmed both exist as distinct destinations — `heloc_strategy` step id appears in the Levers "Strategy · decide" button row (`dashboard.js:3143`) as its own destination, and the ticket separately names "HELOC Modeling inputs on Special Income, Annuities & Insurance page" (also referenced obliquely in the codebase: `dashboard.js:440` comment "HELOC isn't a client_optional_functions.csv toggle"). Did not diff the two field sets to confirm full redundancy.
**Recommendation:** Live inventory both locations' fields first; the likely shape (common in this codebase's pattern of "strategy pages" vs. "input pages," per the Distribution Strategy screenshot's own "Levers preserve the existing source pages" framing) is that one holds the raw HELOC terms/balance (an input) and the other holds strategy/decision levers (draw policy, payoff timing) — if so, the fix is presentation (link one to the other, don't duplicate the same fields) rather than deleting a whole page.
**Model: Sonnet 5** — needs the field-level diff before deciding merge-vs-link.

### S. #213 — HSA configuration: one collapsible section, swap start/end dates
**Found:** Not located precisely in this pass (would need to find all 3 current HSA sections in the input pages).
**Recommendation:** Straightforward consolidation once located: combine into one `<details>` section; swap the displayed order of "withdrawal start date" and "withdrawal end date" fields (currently apparently reversed from the expected reading order).
**Model: Sonnet 5** — needs to locate and merge 3 existing sections without dropping any field.

---

## P1 — Optional modules

### T. #226 — Tax-Loss/Gain Harvesting should be optional modules
**Found:** Confirmed precisely. In `src/module_catalog.py:245-256`, `tax_loss_harvesting` and `gain_harvesting` are the **only** two OPTIMIZATION-category modules in that list **without** `optional=True` (compare to `retirement_strategy`, `what_if_analysis`, `charitable_giving` immediately above/below them, which do have it) — meaning they currently always compute/show regardless of the `client_optional_functions.csv` toggle state, unlike every sibling module.
**Recommendation:** Add `optional=True` to both entries; add the two corresponding toggle rows to `client_optional_functions.csv`; verify the existing optional-module gating machinery (already built and tested per this codebase's own established pattern — compute-skip, sheet-drop, nav/PDF-hide) picks them up with no further code changes, since that's exactly what it's designed to do.
**Implementation:** Two-line change in `module_catalog.py`; add two CSV rows; run the existing optional-module test suite (`FORCE_ENABLE`/`FORCE_DISABLE`/`FORCE_ALL_MODULES` env knobs already exist for this per established test patterns) toggling these two specifically.
**Model: Sonnet 5** — low code risk, but should verify against the existing gating tests rather than assume the generic mechanism covers these two without a check.

---

## P0/P2 — Spending

### U. #208, #231 — Annualization and Travel end year
**#208 found — do not assume already-fixed.** A prior fix (documented) explicitly resolved LD-lump annualization **within the YTD actual/budget current-year blend** (`ytd_projection_blend.py`, `_DISCRETIONARY_FLOOR_TRACKING_TYPES` now `("Travel",)` only). But the ticket resurfaces this as still-open, which means either (a) the user is describing a different annualization path — most likely the **multi-year projection's own inflation/growth escalation** applied to a Large Discretionary budget line across future years, which is a separate mechanism from the current-year YTD blend the prior fix addressed — or (b) a genuine regression. **Do not re-apply the same fix; reproduce first.**
**Recommendation:** First step is diagnostic, not a code change: build a plan with a one-time Large Discretionary line (`one_time_year` set) and confirm whether it appears in years other than its designated year anywhere in the projection output (not just the current-year actual/budget comparison the prior fix covered).
**#231 found:** No evidence of an existing end-year field for Travel group budgets (the category schedule fields seen in `dashboard.js:13355` show `start_year`/`end_year` per *line-item detail row*, but the ticket asks for this at the *group* level) — straightforward additive field once confirmed absent at the group level.
**Model: Sonnet 5** for #208 (diagnostic + fix once root cause is confirmed, since it's provably not the same bug as last time); **Haiku 4.5** for #231 (additive field, existing pattern to copy from the line-item version).

---

## P2 — Collapse defaults & helper text

### V. #216 — "Everything" sections default collapsed
**Found:** Not located precisely (would need to find every page's `<details>`/collapsible-section usage and check current `open` defaults). Likely mechanical once found — probably several near-identical `<details open>` occurrences to flip.
**Model: Sonnet 5** — needs a full sweep of `<details` usage across the page renderers to avoid missing instances (a plain find-replace on `open` is risky without confirming each is actually the "Everything" pattern the ticket means).

### W. #203, #219, #220 — Helper text standard
**#203:** "Might be ok" per the ticket itself — no action unless #219/#220's new standard reveals specific fields that need it; track as a checklist output of #219/#220's rollout rather than its own task.
**#219/#220 found:** These are literally reference examples of a documentation/copy standard the user wants applied broadly — not a code bug. **Recommendation:** treat as a content project: (1) inventory every "non-intuitive" field across the input pages (a real list, not a guess); (2) write copy in this exact style (plain-language, states the mechanism, states the guardrail, ends with a bottom-line) for each; (3) implement the superscript-`i` tooltip UI pattern once (a reusable component), then pour content into it. Building the reusable tooltip component is the only part with UI-implementation risk; writing 20–40 field explanations is a volume task well within a cheaper model once the style is set (the two examples given are the style guide).
**Model: Sonnet 5** for the reusable tooltip/superscript-i component (one-time UI build); **Haiku 4.5** for each subsequent field's copy, using #219/#220 verbatim as the few-shot style example.

---

## P3 — Assumptions-page decomposition

### V2. #235, #237, #238, #239 — Move fields out of Economic and Tax Assumptions
Straightforward relocations once each source/destination pair is confirmed to exist as described:
- **#235** Dividend Reinvestment → Investment Holdings: **Haiku 4.5**.
- **#237** Self-Employment info → Work Income's SE section (abbreviate SE, not Se, throughout — note as a copy-wide find/replace, not just this one section): **Sonnet 5** (the abbreviation rule should be applied everywhere "Self Employment"/"Se" appears, not just the moved section, so it's a small sweep, not a single edit).
- **#238** Delete redundant Medicare section: confirm nothing reads fields from this section before deleting (a section can look redundant in the UI while a field is still consumed by the engine) — **Haiku 4.5** for the deletion once that check is clean, but the check itself should happen first.
- **#239** Remove Retirement section, move RMD start ages to the Household and People table, move 401k Rollover year to Work Income's Retirement Contributions section: **Sonnet 5** — two different destinations for two different fields, verify both destination sections already exist in the form the ticket assumes before moving.

---

## P3 — Misc

### X. #241 — Field Finder missing Travel fields
**Recommendation:** Diagnose why (an indexing/inclusion-list gap, most likely — Field Finder presumably builds its index from a fixed field-category list that never picked up Travel's fields when that category was added). **Model: Sonnet 5** — needs to find the Field Finder index-building code first.

### Y. #240 — Demo data for the system
**Found:** No existing demo-data generator found in `tools/` or `src/` (only a test file with "demographic" in its name, unrelated). This is a net-new deliverable.
**Recommendation:** Generate a complete, internally-consistent, clearly-fictional input dataset (all `input/client_*.csv/json/yaml` files) representative of a realistic-but-simple household, sized to exercise the optional modules worth demoing without needing every module on. Keep it as a checked-in fixture (e.g. `input/demo/`) with a loader/switch, not a one-off script output.
**Model: Sonnet 5** — needs to touch every input file schema coherently (cross-file consistency, e.g. ages/dates/account balances must agree across files) — a good fit for a single well-scoped agent run, not Haiku (too many cross-file constraints to hold reliably) and not Opus (no architectural judgment call, just correct, consistent data).

---

## What I did not verify (be aware before treating any of the above as final)
- #199's math explanation is sound financial reasoning grounded in the code's own comments, not a live reproduction of what the user specifically saw on screen — confirm it matches their actual observation before publishing the copy.
- #207 (RMD/Roth Optimizer ignoring Objective Mode/Target Bracket): I traced the data plumbing and it *appears* wired correctly end-to-end (`roth_objective_mode` config → `planning_engines.py` optimizer → `result_contract.py` → sheet display) — I could not reproduce the reported bug from static reading. **First implementation step must be live reproduction** (toggle Objective Mode on a real plan, rebuild, confirm the sheet does or doesn't change) before writing any fix, since the code path found gives no obvious reason for the reported staleness.
- #215/#224/#217/#236 (Special Income page) and #214 (HELOC) and #213 (HSA) all need a live page inventory I did not do (static grep isn't reliable for "what fields are currently on this rendered page" versus "what the render function is capable of showing").
- #206 (reports nav order) and #241 (Field Finder Travel gap) — the specific render/index functions were not located in this pass.
- Timing claims in #234 and #222/#223 are user-reported and not benchmarked here.
