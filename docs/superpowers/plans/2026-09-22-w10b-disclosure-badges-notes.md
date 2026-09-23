# W10b — Live-optimizer disclosure badges: what was built, and the judgment calls

> Execution record for **W10b** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> §4 (the W10 workstream), implementing #329 P5b / §4.7 (spec
> `docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md`
> §4.7, §4.1, §4.3, §5). Requires W9 — landed on this branch. Follows W10a
> (the Roth result panel), landed immediately before this session started.

## Scope, as the plan states it

> **W10b — §4.7 disclosure badges.** Row-level badge for values that are live
> optimizer output, plus a section banner stating the plan re-optimizes every
> build. Built on `dashboard_source_truth_banners.js`, not a parallel
> indicator system. **Separate commit, so a stalled apply path does not block
> work with standalone value.**

W10c (apply-to-plan) is a separate, later session. Nothing here anticipates
it: no Planning Case, no `source: "optimizer"` patch, no working "Lock in
this schedule" apply action (see judgment call 3).

## Judgment call 1 — which rows count as "live optimizer output"

§4.7's own text: *"Any row whose current value is live optimizer output
carries a marker... without it, a number on screen is indistinguishable from
one you typed."* Read literally, this asks for a badge on a **number** that
looks user-entered but isn't. Checked what that would actually be for every
optimizer named in §4.3 as capable of "policy adoption (mode switch)" — Roth
Conversion, HSA Drawdown, Asset Allocation — by reading the engine code each
mode switch drives:

- **`optimize_roth_conversion_strategy()`** (`src/planning_engines.py`): when
  `roth_conversion_policy` is an auto-optimize spelling, the winning
  candidate's overrides (`roth_target_rate`, `roth_fixed_amount`, ...) are
  applied to the **in-memory config dict `c`** — never written back to a
  `client_policy.csv` row. The dashboard reads rows from the plan's saved
  CSVs; nothing there changes.
- Asset Allocation's actual target mix, in every mode other than
  `user_target`, is computed by `allocation_optimizer.py` and never lands in
  a `target_pct` row either — `dashboard_decomp_row_model.js` already has a
  `rowBuildUsageState()` entry for `target_pct` marking it **inactive**
  ("saved user target percentages are reference-only") when a computed mode
  is selected. That is the mirror-image disclosure — "this saved value is
  not what's running" — and it already exists, for Asset Allocation only.
- HSA Drawdown's `optimize` mode is the same shape as Roth's: no separate
  output row.

**Conclusion: there is no plan row today, for any of the three, whose
*current stored value* is literally optimizer output.** The literal reading
of §4.7 has no target to badge until W10c's apply-to-plan writes a row from
an accepted patch — at which point §4.6's *applied*/*diverged* states (which
this design explicitly maps onto the badge) become meaningful, and that
machinery does not exist yet.

**Decided: badge the mode/policy row itself**, when its value is an
optimize-family spelling. This is the one row every one of the three
optimizers has, it is the fact a reader can actually see and act on ("this
switch is on 'optimize'"), and it is the row whose value *causes* the
section's real output to be optimizer-computed every build — which is
exactly the behavior §4.1a names as the thing nothing today discloses:

> Setting `roth_policy='optimize'` makes `optimize_roth_conversion_strategy()`
> run *inside* the build and mutate `c` with the winning candidate. ...
> Nothing in the UI says so.

Naming the mode switch, not a nonexistent output row, is the accurate
disclosure of that exact sentence. The alternative — badging the auxiliary
strategy fields shown under each optimizer's "optimizing" branch (e.g.
Roth's `roth_target_bracket_rate`, `roth_fixed_annual_amount`) — was
rejected: whether the engine's candidate sweep treats those as hints,
floors, or ignores them outright while auto-optimizing is a genuine
ambiguity in `optimize_roth_conversion_strategy()`'s own candidate-matching
logic (see its comment on near-duplicate specs "sharing the exact same
policy and target_rate"), and guessing at it in a UI-only workstream would
be exactly the kind of second, drifting copy of engine behavior #329/#330
exist to prevent.

## Judgment call 2 — scope is the three mode-switch optimizers, not all of Optimize

§4.3 names four apply shapes: **policy adoption (mode switch)** — Roth
Conversion, HSA Drawdown, Asset Allocation; **scalar adoption** — Social
Security, Withdrawal Sequencing; **structural adoption** — Housing; **trade
list export** — Harvesting. Only the first shape has an ongoing,
build-to-build "the plan keeps re-optimizing this" behavior; the other three
either have no mode switch at all (a scalar/structural change is adopted
once, by hand, not silently re-derived) or, for Harvesting, produce no
plan-state change whatsoever (export only). Charitable Giving is a plan flag
(W6), not an optimizer with a live/frozen distinction. So the badge/banner
pair is out of scope for those five by construction, not by omission — there
is nothing in §4.7's "silently self-optimizing" framing that applies to them.

## Judgment call 3 — the banner's action is "jump to the mode row," not "Lock in this schedule"

§4.7: *"...offers the switch to 'Lock in this schedule.'"* That literal
wording is §4.3/§4.4's **apply-to-plan** affordance — a Planning Case patch
through `promotePlanningCase()`, which is W10c's heavy work and does not
exist yet. Two options: ship a banner with no action, or ship a banner whose
action claims to do something it can't.

**Decided: the banner's button jumps to (and focuses) the same mode/policy
row the badge marks**, labeled "Change to a fixed strategy" rather than
"Lock in this schedule." This is not a placeholder — switching the mode
field away from an optimize spelling (to e.g. `fill_to_bracket` for Roth, a
fixed `smooth_window`/`annual_pct` schedule for HSA, `user_target` for Asset
Allocation) is the actual, already-working mechanism that stops a section
from re-optimizing today; W10c's contribution will be writing the *chosen
candidate's values* into that fixed state automatically, not inventing the
"stop optimizing" concept. Labeling today's real, working affordance
honestly was preferred over reusing tomorrow's label on a button that can't
yet do what it says.

## Judgment call 4 — one definition of "is this optimizing," reused, not duplicated

Each optimizer's own input renderer already computes exactly the
classification the disclosure needs:

- `renderRothConversion()` had an inline `policyIsOptimizer` const. Lifted
  out to an exported `rothPolicyIsOptimizer(policy)` in
  `dashboard_decomp_allocation_optimizer.js`, called from both
  `renderRothConversion()` (unchanged behavior) and the banner file.
- `allocationModeIsComputed(mode)` was already exported and already takes
  its value as a parameter — reused directly, no change.
- HSA had no standalone accessor (the mode was computed inline inside
  `hsaWithdrawalPolicyBlock()`, scoped to its own pre-filtered row list).
  Added `hsaWithdrawalModeValue()` to `dashboard_decomp_strategy_workspace.js`,
  mirroring `rothPolicyValue()`/`irmaaModeValue()`'s existing no-argument
  accessor pattern exactly. `hsaWithdrawalPolicyBlock()` itself is
  untouched — the new function is an addition, not a refactor of working
  code, so there is zero behavior risk to the existing HSA panel.

Three names, each with one owner, each read by exactly the two places that
need the same fact. Declaring a fourth, banner-local copy of any of these
checks would be the identical hand-maintained-twin failure #329/#330's own
language names repeatedly.

## Judgment call 5 — the test sandbox: isolate this file rather than widen the shared one

`tests/frontend/load_dashboard.mjs`'s shared sandbox deliberately loads only
`dashboard.js` and `dashboard_decomp_*.js` — `dashboard_source_truth_banners.js`
was never in that set, and no test file covered it before this workstream
(grepped for `RPDashboardRoadmap11`/`source_truth_banners` across
`tests/frontend/*.mjs`: zero hits).

**First attempt: added it to the shared loader's file set.** `npm test`
immediately surfaced four unrelated failing suites
(`allocation_preview_strategy_optimize.test.mjs`,
`renderBuildImpactAfterBuild`, a Monarch auto-update-card suite, a residency
schedule suite), all with the same root cause: this file's tail code
monkey-patches the shared sandbox's `renderMain` (`renderMain = function ()
{ oldRenderMain(); applyEnhancements(); }`), and `applyEnhancements()` calls
`decorateGlossary(mainPane())`, which needs `root.querySelectorAll` — a
method the shared loader's intentionally minimal `document` stub
(`getElementById: stubElement` returning a plain object with no DOM methods)
does not provide. Every other test that calls (now-patched) `renderMain()`
anywhere in its own flow inherited a decoration pass it was never written
to survive.

**Reverted, and loaded this file in its own isolated `vm` context instead**
(`tests/frontend/live_optimizer_disclosure.test.mjs`'s own
`loadBannersSandbox()`), evaluated alone with a purpose-built minimal stub.
Safe because the file's own top-level code only reaches outside itself
through `try { ... } catch (_e) {}`-guarded reads of `renderMain`/
`showStepHelp` (both absent standalone, both swallowed) and
`installShortcuts()`'s `document.addEventListener` call (stubbed); the
`setTimeout` stub never invokes its callback, so `applyEnhancements()` is
never triggered during load, matching `load_dashboard.mjs`'s own stub
exactly for the same reason. `load_dashboard.mjs` itself is unchanged from
before this workstream.

**Consequence for coverage**: `liveOptimizerRowBadges()`/
`liveOptimizerSectionBanners()` (the DOM-writing wiring) are not directly
exercised by any test, matching this file's own pre-existing pattern —
`insertAfterPaneHead()`, `decorateGlossary()`, `addStaleAdvisorNotice()` etc.
had no direct test coverage before this workstream either. What's covered
are the two pieces that are pure: the live-mode classification (via the
real, shared `loadDashboardSandbox()`, since `rothPolicyIsOptimizer`/
`allocationModeIsComputed`/`hsaWithdrawalModeValue` live in the
already-included decomp files) and the two markup builders
`liveOptimizerBadgeHtml()`/`liveOptimizerBannerHtml()`, split out from the
DOM-insertion functions the same way `sourceTruthHtml()` is already split
from `insertAfterPaneHead()` — 13 cases, including HTML-escaping of an
untrusted title and both the "jump button present" and "no dead jump
button" branches of `liveOptimizerBannerHtml()`.

## What this does not do

- **No calculation changes.** Nothing in `src/` changed. Both
  `rothPolicyIsOptimizer()`/`hsaWithdrawalModeValue()` extractions are pure
  code moves (the first literally lifts an existing const out one level;
  the second reads the same row the existing inline code already found).
- **No apply, pin, or "Lock in this schedule" action.** That is W10c's.
- **Hides nothing.** The global no-hidden-data-behind-a-switch invariant is
  untouched: this workstream adds a badge and a banner, both purely
  additive DOM insertions after existing content; no row, field, or section
  becomes less visible than before.
- **No new module toggle, catalog field, or `gate_kind`.** This is a
  frontend-only disclosure over existing `client_policy.csv` mode/policy
  rows — nothing in `src/module_catalog.py` needed a change.

## Verification

- `tools/regen_golden_master.py measure` — exact match, `terminal_nw +0.00`,
  `lifetime_tax +0.00`. Expected: zero Python files changed by this
  workstream.
- `pytest -m "not slow and not nightly" -n auto --dist loadfile` — green.
- `npm test` — 508/510. The 2 failures are in
  `tests/frontend/js_codemod_parser_offsets.test.mjs`, the same
  jscodeshift-offset environment difference W6/W8b/W9/W10a's notes all
  record; this workstream touches no `.mjs`/`jscodeshift`-adjacent tooling.
- `tests/frontend/live_optimizer_disclosure.test.mjs` — 13/13 new cases.
- `node tools/js_codemod/census.mjs --check` — no drift (the new
  window-bridge entries in `dashboard_decomp_allocation_optimizer.js` and
  `dashboard_decomp_strategy_workspace.js` match what the codemod already
  generates for a named-export addition).
- Manual read of the rendered banner/badge HTML (via the isolated sandbox's
  `liveOptimizerBadgeHtml`/`liveOptimizerBannerHtml` output) against the
  three optimizer titles, confirming escaping and the jump-button row index.

### Frontend size ratchet

`DASHBOARD_JS_MAX_LINES` **unchanged at 7,201** — `dashboard.js` is not
touched. `TOTAL_JS_MAX_LINES` raised 33,997 → 34,188, the measured total
with no slack: genuine new code in `dashboard_source_truth_banners.js` (the
disclosure registry, the two DOM-writing functions, the two pure markup
builders) plus the two small named-export extractions, per that ceiling's
own contract.

## Consequences for later workstreams

- **W10c** (apply-to-plan) can replace this workstream's "Change to a fixed
  strategy" jump-to-row button with the real "Lock in this schedule" patch
  action once `promotePlanningCase()` has an optimizer patch to apply — the
  banner's structure (one button slot per live optimizer, keyed by mode row)
  is already shaped for that swap. When it lands, W10c should also revisit
  whether a *written* row (post-apply) needs the badge too, per §4.6's
  *applied*/*diverged* states — genuinely out of scope here, since no row is
  ever written by an optimizer yet.
- **W11** (Planning Levers retirement) depends on this workstream
  specifically, per the master plan. The row badge is the "where each dial
  position came from" half of what Planning Levers' retirement needs to
  replace, for the three mode-switch optimizers; the remaining optimizers'
  provenance (scalar/structural adoptions) is not part of what W10b covers
  and should be checked before Planning Levers is actually deleted.
- Whoever next adds a fourth mode-switch optimizer (none exist today, but
  the shape recurs) should add one entry to `LIVE_OPTIMIZER_MODES` in
  `dashboard_source_truth_banners.js`, reusing whatever classification
  predicate that optimizer's own input renderer already computes — not a
  new copy of the "is this optimizing" check.
