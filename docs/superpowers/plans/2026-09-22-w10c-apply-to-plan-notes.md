# W10c — apply-to-plan: execution notes

Master plan: `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4, W10c.
Spec: `docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md` §4.2–§4.6 (#329 P6).
Precedent: W10a (`2026-09-22-w10a-roth-result-panel-notes.md`), W10b (`2026-09-22-w10b-disclosure-badges-notes.md`).

Four commits, landed and pushed one at a time as each sub-piece was proven —
the plan flags this workstream as Heavy and the branch has a history of
sessions hitting rate limits mid-work.

1. `3a456ca` — core machinery.
2. `bef5e59` — Social Security, the **scalar adoption** shape, end to end.
3. `3a13593` — Housing, the **structural adoption** shape.
4. `75133dd` — Asset Allocation, §4.3's **policy adoption / schedule freeze** pair.

The plan's scoping instruction ("cover one patch shape — scalar adoption,
Social Security — before the structural one") is why 2 precedes 3 and why they
are separate commits rather than one. Commit 4 is the two named actions the
plan lists as W10c deliverables, taken only once the patch contract had been
proven twice.

---

## The contract, and why the new file is small

§4.2's whole point is that apply-to-plan is a *reuse* problem, not a new
subsystem. An optimizer result becomes appliable by emitting an **optimizer
patch**: a list of items in `planning_workbench_ui.js`'s existing
`overrideFromRow()` shape. Apply = build a Planning Case with
`source: "optimizer"` and hand it to the existing `promotePlanningCase()`.

What that buys, none of which is written in this workstream:

- the confirmation dialog, the `before → after` list and `editValue()` staging
  (`promotePlanningCase`, `dashboard.js`);
- the Unified Comparison Matrix, the Decision panel and the Saved Cases list,
  which pick an optimizer case up unchanged **because it is the same record
  type** — no branch, no second renderer;
- un-apply, which is the reverse patch and needs no storage of its own.

`frontend/js/dashboard_decomp_optimizer_apply.js` is therefore about 470 lines
for the entire mechanism: the applied-state computation, the reverse patch, the
case record, the action strip and a small registry.

**The enum gains exactly one value.** `normalizeSource` accepts `"optimizer"`,
not one value per optimizer — §4.2 rejected that explicitly as the same
hand-maintained-list failure #329 §3.1 exists to remove. Which optimizer
produced a case lives in the record's `optimizer_id` / `provenance_note`.

One judgment call beyond the spec: `overridesForSource('optimizer')` returns
`[]` rather than taking the existing manual fallthrough. An optimizer case's
overrides come from its patch; nothing on the page can be scraped for one, and
the fallthrough would have labelled whatever the user happened to be editing as
optimizer output. Tested.

---

## §4.6, the rule most likely to rot

> Resist storing an `applied: true` flag. … **"Applied" is computed.**

There is no boolean anywhere in this diff, client or server. Three tests pin
it, and they are the reason the tests exist rather than assertions about markup:

- the same patch object yields `applied` against one set of rows and
  `not_applied` against another (a stored flag could not produce both);
- a stray `applied: true` on a patch item changes nothing;
- `test_no_applied_flag_is_ever_written_server_side` asserts the payload
  carries no key named `applied` or `*_applied`.

The three states are `not_applied` (no row matches), `applied` (all match) and
`diverged` (some match, some do not). Advisory items — those with no
`row_index` — take no part in the comparison, so a Housing patch whose ZIP has
nowhere to go does not sit permanently at `diverged`.

### Comparison: two deliberate tolerances, and two escape hatches

`sameValue()` is tolerant in exactly two ways — whitespace and numeric equality
across formats — and strict otherwise. A lenient comparator reporting "applied"
for a plan that is not is the single failure §4.6 exists to prevent, so
loosening it globally was rejected twice. Instead an optimizer whose rows need
a different comparison declares it:

- **`liveValueOf`** on the descriptor, and **`compareAfter`** on an item, for
  the case where the stored text and the thing the optimizer chose are not the
  same quantity. Social Security is the worked example (below).
- **`liveStorageValueForRowIndex`**, for formatted rows. This one was a real
  bug found while writing the Allocation tests: the plan file holds `"35%"` and
  `"$400,000"`, while `storageValueForInput()` — which every `editValue()`
  write goes through — normalizes those to `"35"` and `"400000"`. A patch whose
  `afterRaw` is the normalized form (as it must be, so the write is exact)
  compared *unequal against a row already holding exactly that value*, so an
  applied plan read "not applied". Both sides now go through the same
  normalizer. Housing and Allocation declare it; Social Security does not need
  it, because a claim date is plain text.

---

## The three patch shapes

### Scalar adoption — Social Security (`bef5e59`)

The design's simplest case: one claim age per person, one existing row each.
The result had no path to the browser, so this adds one, following W10a's
precedent exactly: `build_sheet10()` already computes the sweep and hands it to
Sheet 1, and `social_security_timing_payload()` projects that same dict onto
`plan_summary.json` beside `roth_strategy_result`. Nothing re-runs a sweep, and
`ss_sweep` is a local in the same function that assembles `summary_data`, so
the projection needs no new state on `c` — which is why the golden master does
not move.

Three things here would have been quietly wrong, each with a test:

1. **The age → `claim_date` conversion.** The row holds a date; the sweep chose
   an age. `ssClaimDateForAge()` mirrors `src/data_io.py`'s
   `_ss_claim_from_date_or_age()` exactly — `(dob_yr + age, dob_month)` — and a
   test round-trips every age 62–70 back through `ssClaimAgeFromDate` to prove
   applying the recommendation writes *the age it recommended*. Any other month
   silently applies a different age for anyone whose claim month precedes their
   birth month.
2. **A blank `claim_date` is not "unset"** — the engine reads it as age 70. So
   this optimizer declares `liveValueOf` + `compareAfter` and the comparison
   runs on the claim **age**. Without it, a plan already doing exactly what the
   sweep recommends reads "not applied". The same choice makes a user-refined
   month at the same age read as applied, which is correct: the sweep varies
   whole ages only and has no opinion about the month.
3. **Rows that cannot be written.** No Member 2 (single-person household) and
   no date of birth both emit *no item*. An item `editValue()` would reject
   makes the strip claim a change it cannot make and pins the state to
   `diverged` permanently.

`build_sheet10()` now also returns `h_current`/`w_current`/`h_label`/`w_label`,
so the payload reports the configured pair without a second definition of "the
configured claim age". Its `current` key could not serve: the coarse-then-refine
pass legitimately never scores the configured pair, and `current` is then
`None`.

**A bug the tests found:** `Number(null)` is `0` and finite, so a missing
recommendation became a claim date in the person's *birth year* rather than
being skipped. Fixed with an explicit null/blank guard ahead of the numeric one.

### Structural adoption — Housing (`3a13593`)

The only optimizer whose answer does not map onto one obvious row. §4.3's
resolution is implemented as written: `row_index` items for the Housing rows
that exist, advisory items for the rest.

Writes `Other Assets/Home home_sale_year` (year 0 for "keep", which is how that
row already spells no planned sale) and, per move onto `Housing/next_step_N`,
the type, start year, state and price-or-rent.

Does **not** write, deliberately:

- **the estimated cost rows.** `editValue()`'s existing housing hook
  (`reestimateHousingCostsOnValueChange`) already re-scales insurance,
  utilities and maintenance when the price or rent changes — the desired
  behavior, already implemented. Writing them here would double-apply the same
  ratio. The honest caveat is in the strip's own copy: because it is a ratio,
  undoing a price change restores the price exactly and the estimates to within
  rounding.
- **the down payment and mortgage rate.** Writing this patch against the real
  payload found that `src/housing/results.py`'s `_format_move` reports only
  `purchase_price` and `monthly_pi_payment` for a buy; the search's own
  `down_payment_pct`/`mortgage_rate_pct` are request inputs it never echoes
  back. The first draft patched them from keys that do not exist — dead code
  that would have silently written nothing. They are now an advisory item
  naming the P&I the search actually assumed, because those two rows are what
  the engine computes P&I from, so applying a price without them means the
  plan's payment can differ from the one the optimizer scored.
- **the ZIP and city.** The Housing step is keyed by state, area type and
  population. Advisory, not dropped — the state row alone does not say which
  town won.

Two translations that would have been quietly wrong: the optimizer's action
vocabulary is `"buy"`/`"rent"` while the plan row's is `"purchase"`/`"rent"`;
and `afterRaw` goes through `storageValueForInput`, per the formatted-row
finding above.

**A bug the tests found:** the strip's patch is rebuilt at click time from the
retained payload, so a re-render drawing a *different* payload than the last run
would have applied the stale one. The strip now binds the retained payload to
whatever result it is rendering, making "the strip applies the result on
screen" true by construction. `loadAll()` clears it on a plan switch, beside
W10a's Roth cache reset.

### Policy adoption / schedule freeze — Asset Allocation (`75133dd`)

§4.3's two named actions, wired where both halves are ordinary plan rows.
Policy adoption sets the mode row to a computed mode; schedule freeze sets it
to `user_target` and writes the optimizer's computed percentages into the
`target_pct` rows. Policy adoption is primary and default, deliberately: it is
what plans already do, so naming the behavior changes nobody's numbers — W10b's
§4.7 disclosure is what makes that honest.

**Two bugs the tests found:**

- A plan already on `max_sharpe` *is* letting the plan optimize. Targeting the
  default mode made the computed state read "not applied" for a plan doing
  exactly what the button asks. `allocationLiveModeTarget()` keeps whichever
  computed mode is live.
- Freezing with no preview loaded wrote `user_target` plus a table of zeros:
  `activeOptimizerUsedTarget()` legitimately returns 0 for every class before
  the preview runs. That patch is one the app then refuses to save, and a bare
  mode switch would leave the stale hand-entered targets driving the plan — the
  opposite of the button's promise. The guard is the same 100% total
  `allocationTotalHtml()` already enforces; below it nothing is offered and the
  strip says why.

---

## Deliberately not done

- **Roth Conversion and HSA Drawdown's pair.** Their policy-adoption half is
  the same one-row shape, but schedule freeze writes a year-by-year
  forced-conversion schedule that lives in its own table rather than in
  `row_index` rows, and W10a's payload deliberately carries no per-year series.
  Offering the pair there today means one real button and one that cannot
  deliver. The patch contract is now proven on all three shapes, so this is a
  payload question for the session that adds those result panels — which the
  master plan already schedules one per session, explicitly not batched.
- **Per-row apply on Housing.** The strip applies the starred rank-1 option and
  says so. A per-row affordance needs a per-row applied state; out of scope
  here.
- **Trade-list export** (§4.3's action-optimizer case) and the **stress →
  protection bridge**. Neither is an optimizer patch; both are their own work.
- **Server-side Planning Cases.** §4.6 decided to keep `localStorage` and *say
  so*. Every strip states that the applied values become ordinary plan data
  while the provenance note and the undo affordance are browser-local and lost
  on a cache clear. A test asserts that copy exists and that no string says
  "permanent", "forever" or "audit trail".

---

## The test-fix cycle the plan predicted

The plan warned this workstream "writes plan data, so it invites a test-fix
cycle". It did, and every round was the test finding a real defect rather than
the test needing adjustment. In order:

1. The action strip's registry id landed inside a JS string inside a
   double-quoted HTML attribute; `escJs()` alone (the pattern the existing
   planning-case buttons use for generated `case_id`s) does not close the
   attribute hole. Both interpolations now run `escJs` then `esc`.
2. `Number(null) === 0` turning a missing SS recommendation into a birth-year
   claim date.
3. The `social_security_timing_result` slow test's own workbook assertions,
   twice: the summary sheet is not in the first `.xlsx` `glob()` returns, and
   Sheet 1 prints one combined `"<nick> <age> / <nick> <age>"` headline rather
   than numeric cells. Both were the test being wrong about the artifact, and
   both are now read the way the workbook actually writes them — the build
   itself and every payload assertion passed on the first run.
4. The Housing strip applying a stale payload after a re-render.
5. Formatted rows comparing unequal to themselves.
6. The zero-target allocation freeze.

Two environment notes for the next session:

- `optimizer_apply.js` was renamed to `dashboard_decomp_optimizer_apply.js`.
  That is the size ratchet's own extraction pattern, and it is also what puts
  the file in `load_dashboard.mjs`'s shared sandbox — which the Social Security
  and Housing tests need. Safe here, unlike
  `dashboard_source_truth_banners.js` (W10b's recorded finding), because
  nothing in it monkey-patches `renderMain` or touches the DOM at load.
- A top-level `const` in that shared sandbox is lexical and never lands on the
  sandbox global the way a `function` declaration does. An exported constant is
  only reachable through its file's own `window` bridge — the same reason the
  loader's own notes say to set `sandbox.window.rows`.

---

## Verification

- `tools/regen_golden_master.py measure` — **exact match, `+0.00` on both
  pins**, run after the Python changes landed. Expected and required: this
  workstream writes plan data only through a *user action*, and the
  golden-master fixtures never invoke apply, so a delta would have meant
  something applies a patch by default.
- `pytest -m "not slow and not nightly" -n auto --dist loadfile` (CI's own
  invocation) — green.
- `tests/test_social_security_apply_payload_functional.py` — 14 fast + 1 slow.
  The slow one is a real subprocess `tools/build_workbook.py` build that reads
  `plan_summary.json` back and cross-checks the payload's recommended ages
  against Sheet 1's own "Recommended … Claim Age" headline: both are
  projections of the same `best`, and a disagreement would mean the panel
  offered to apply something the workbook does not recommend. It passes.
- `tests/frontend/optimizer_apply.test.mjs` (45), `social_security_apply.test.mjs`
  (26), `housing_apply.test.mjs` (28), `allocation_apply.test.mjs` (22).
- W10a's `roth_optimizer_result_panel.test.mjs` (13) still passes unchanged
  after its `/api/summary` cache/fetch pair was generalized into one keyed
  reader that Social Security reuses.
- `npm test` — 607/608. The one failure is `js_codemod_parser_offsets.test.mjs`,
  which imports `jscodeshift`; `node_modules` is absent in this container, and
  it fails identically on a clean tree. Same pre-existing environment failure
  W6/W8b/W9/W10a/W10b all record.
- `DASHBOARD_JS_MAX_LINES` **unchanged at 7,201** — `dashboard.js` is not
  touched by any of the four commits. `TOTAL_JS_MAX_LINES` raised in four
  steps, each measured with no slack, each in the commit that earned it:
  34,188 → 34,657 → 34,866 → 35,121 → 35,317.
