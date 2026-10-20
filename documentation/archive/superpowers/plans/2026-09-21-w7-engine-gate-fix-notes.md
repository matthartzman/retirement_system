# W7 — Engine gate fix: execution notes

Implements the master plan's W7 (`docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
§4, "W7 — Engine gate fix · golden regen #1"), #330 F3. Requires W5 (landed;
see `2026-09-21-w5-dependency-declarations-notes.md`, which declared
`engine_participation` on exactly the two modules this workstream touches so
the fix would be checkable rather than aspirational).

## The fix

`src/projection_stages/deterministic_engine.py` read `equity_compensation`
and `disability_income_insurance` as a raw `c['opt']` lookup instead of
calling `module_enabled()` like every other call site in the codebase. That
raw read skipped two things the accessor does:

* the `RETIREMENT_SYSTEM_FORCE_*` env overrides, and
* `effective_enabled_modules()`'s prerequisite auto-selection (plus the
  default-on treatment of a key absent from `c['opt']` entirely).

Either gap produces the same class of defect: a module the *sheets* treat as
on while the *engine* still models it as off — a sheet built from a
projection that excludes its own subject. Reachable in ordinary use, not
only under `FORCE_ALL_MODULES`, per the plan's own rationale.

```python
# before
_opt = c.get('opt') or {}
_equity_on = bool(_opt.get('equity_compensation')) and bool(c.get('equity_comp'))
_disability_on = bool(_opt.get('disability_income_insurance'))

# after
_equity_on = module_enabled(c, 'equity_compensation') and bool(c.get('equity_comp'))
_disability_on = module_enabled(c, 'disability_income_insurance')
```

`equity_compensation` keeps its existing `AND` against a non-empty
`c['equity_comp']` — the gate change doesn't let the toggle alone conjure
grants a plan doesn't have.

## Hand-verification (done before any regen, per the plan's own instruction)

The plan requires verifying a representative fixture's delta by hand before
batch-regenerating, specifically checking it against what actual engine
participation should change rather than trusting that *something* changed.
Three things were checked directly, in a scratch script against real fixture
configs (not by inspection):

1. **The frozen sample plan** (`tests/fixtures/sample_plan_frozen/`, the
   mandatory dollar-exact gate) sets both toggles explicitly `FALSE` in
   `client_optional_functions.csv`. Neither module is anyone's prerequisite
   (`prerequisite_outputs()` sweep: empty for both), so
   `effective_enabled_modules()` never pulls them in, and `module_enabled()`
   returns `False` for both — identical to the old raw read. **Zero delta
   predicted and confirmed** (`tools/regen_golden_master.py measure`, exact
   match, both pins).

2. **The ten synthetic scenarios** (`tests/synthetic_plans.py`, feeding both
   `test_synthetic_golden_master.py` and
   `test_deterministic_engine_full_row_snapshot_regression.py`) carry **no
   `opt` map at all**. `module_enabled()` defaults an absent key to enabled
   (documented contract: "always-on core sheets are never dropped"), so
   `disability_income_insurance` flips `False → True` on every one of them.
   `equity_compensation` is saved by its `equity_comp`-payload guard (no
   scenario has grants), so it stays `False` in practice despite the same
   gate change.

3. **Whether the `disability_income_insurance` flip can move a number.**
   `income.py`'s DI block is itself double-guarded: it only pays a benefit
   when `c['disability']['simulate_year']` is truthy *and* at least one
   policy is configured. Checked every fixture's `disability` payload
   directly: all ten synthetic scenarios and the frozen sample plan have
   `simulate_year=0`. (The frozen plan does carry one DI policy and two
   equity grants — its immunity comes from the explicit `FALSE` toggles, a
   different reason than the synthetic scenarios' immunity, worth keeping
   distinct rather than conflating as "no fixture is affected".) No current
   fixture can show a DI-benefit delta regardless of which way the gate
   reads.

**Conclusion reached before touching any fixture:** the fix is behaviorally
inert against every golden-master family that exists today. Measuring
afterward should show, and did show, an exact zero delta everywhere.

## Golden-master measurement (after the fix, before considering a regen)

```
$ python3 tools/regen_golden_master.py measure
Computed: terminal_nw=5,438,505.25  lifetime_tax=1,255,734.10
Pinned:   terminal_nw=5,438,505.25  lifetime_tax=1,255,734.10
Delta:    terminal_nw=+0.00  lifetime_tax=+0.00
MATCH -- the pin holds at the current worktree state.
```

`tests/test_synthetic_golden_master.py` and
`tests/test_deterministic_engine_full_row_snapshot_regression.py` both pass
unchanged (9/9) — no fixture JSON needed updating.

## Judgment call: no golden-master regen commit was made

The master plan's global ordering rule calls W7 "golden regen #1" and says
"the golden diff is the deliverable... nothing else in the commit." With a
measured delta of exactly zero across all three families, there is no diff
to be the deliverable, and `regen --reason "..."` would only rewrite the
same two pins to the same values — a commit with no observable content,
existing solely to say a script was run.

This mirrors H1/B5's own precedent exactly (see the master plan §6 and PR
#133's summary): H1/B5 also measured a zero delta (the frozen plan carries
no housing step) and did not produce a separate regen commit — it recorded
the finding and relied on hand-verified math (B3) instead. W7 follows the
same shape: this notes doc **is** the "golden regen" artifact for this
workstream, in place of an empty fixture-rewrite commit.

## Judgment call: added a regression test the plan didn't explicitly ask for

Because every existing golden-master fixture is immune to this bug (for two
different reasons — see above), none of them pins the defect W7 fixes. A
change that closes a real bug with a zero-diff verification story is correct
but undemonstrated by anything in the suite.

Added `tests/test_engine_module_gate_agrees_with_sheets_regression.py`,
which constructs the divergence directly rather than waiting for a fixture
that happens to hit it:

* an explicit `FALSE` toggle still gates the engine off (unchanged case),
* an explicit `TRUE` toggle is the control (proves the fixture is live, not
  dead),
* **a plan with no `opt` map at all** — the shape every synthetic scenario
  and every JSON-built plan actually has — now models the DI benefit,
  matching what `module_enabled()` (and therefore the sheets) already say,
* `RETIREMENT_SYSTEM_FORCE_ENABLE_MODULES` now reaches the engine (it did
  not before),
* `RETIREMENT_SYSTEM_FORCE_DISABLE_MODULES` still wins over a force-enable
  (precedence ladder inherited wholesale, not just the part W7 targeted),
* prerequisite auto-selection reaches the engine, exercised by temporarily
  declaring a `requires_outputs` edge onto `disability_income_insurance`
  (nothing declares one today, so this is added for the length of the test
  rather than waited for — the mechanism is generic and this pins it against
  regressing later, independent of which module first uses it).

A second class (`TheGateAloneIsInert`) pins *why* no golden master moved:
asserts no synthetic scenario configures a disability event (so a future
scenario addition that does would fail loudly and point at "re-measure the
golden masters" rather than silently drifting), and asserts the gate is a
byte-identical no-op on a plan with no configured event either way.

Verified against the pre-fix engine by temporarily reverting
`deterministic_engine.py` alone: 4 of the 8 new tests fail without the fix,
8/8 pass with it. This is outside the plan's literal one-line scope
("regenerate golden masters") but stays inside its stated intent (#330 F3:
make the engine/sheet agreement checkable). Flagging it here rather than
silently expanding scope.

## Judgment call: `disability_income_insurance` defaulting to enabled on an
## opt-less plan is a real behavior change, currently inert

Every current fixture is immune only because none configures a simulated
disability event. A **future** plan that adds `disability.simulate_year` /
`policies` without also carrying an explicit `opt` map (any JSON-built plan
that never touched the toggle) would newly model a disability event it
didn't before. This is the intended fix, not a bug — `module_enabled()`'s
default-on-when-absent contract is the same one every other optional module
already gets — but it's the one line of this workstream where "nothing
changes today" and "something will change under a plausible future input"
both being true is worth saying out loud rather than only proving in a test.

## File-overlap checks (two concurrent sessions on this branch)

Two separate pushes landed on `claude/master-implementation-plan-2tv0km`
while this workstream was in progress:

1. The W6 session (plan-flag unification) pushed `45987a5`/`0772663`.
2. A second, independent session (`session_01YBMHYvSu8oaVPZBkiP1rQ5`)
   pushed a "W6 trim" (`30ae09f`) plus a merge of this branch's own W7 push,
   and — reacting to the same CI signal — an identical fix for the
   test-suffix-shape ratchet this workstream's new test file tripped
   (independently renamed the same file onto `_regression.py` the same way).

Both were checked with `git diff <parent> <tip> -- <W7's files>` before
merging, not assumed clean from the task's own file list: neither touched
`src/projection_stages/deterministic_engine.py` or
`tests/test_module_toggle_call_site_enforcement.py`. Both merges were
conflict-free `git merge --no-ff` operations onto this branch. A stale
`tools/js_codemod/census_report.json` from the first W6 push (missing two
JS references W6 itself added, same `node_modules`-absent-in-session-env
root cause the W5 PR hit once already) was found and fixed in its own
commit, separate from W7's actual content, once confirmed genuinely stale
by diffing the committed copy against a fresh `census.mjs` run.

## Verification summary

* `pytest -m "not slow"` — full pass, no failures, on the final merged and
  pushed branch state (re-run after each merge, not just once at the start).
* `tests/test_module_toggle_call_site_enforcement.py` — 13/13 (11 unchanged
  + `_engine_keys()` helper covering both call-site spellings).
* `tests/test_engine_module_gate_agrees_with_sheets_regression.py` — 8/8 new,
  confirmed to fail 4/8 against the pre-fix engine.
* `tools/regen_golden_master.py measure` — exact match, +0.00 on both pins.
* `tests/test_synthetic_golden_master.py` +
  `tests/test_deterministic_engine_full_row_snapshot_regression.py` — 9/9,
  no fixture JSON changed.
