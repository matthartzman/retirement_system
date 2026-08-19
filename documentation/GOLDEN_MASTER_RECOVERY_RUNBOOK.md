# Golden-Master Recovery Runbook

Ticket 286. What to do when `tests/test_frozen_sample_plan_golden_master_regression.py::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact`
fails — i.e. `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` no longer match what
the frozen fixture computes.

This process exists because a prior investigation
(`docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`,
"Phase 1") reached a **confidently wrong** conclusion using tools that looked
rigorous — `git bisect`, `git log -S` — and it took a second investigation two
days later to find the real answer. Follow this runbook in order; it is built
specifically to route around both traps that cost time there.

## 0. Environment invariants (check these before anything else)

- **Interpreter**: use `py -3.14`, not plain `python` (that's 3.12 here and
  lacks pytest in this environment).
- **Price-provider env var is REQUIRED**:
  `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`. Without it, live price
  providers make dollar figures drift between runs on the same commit, and
  you will chase a phantom that has nothing to do with the code. Every
  subcommand of `tools/regen_golden_master.py` sets this internally, but any
  manual `pytest`/`python -m` invocation you run by hand must set it too.
- **The test suite mutates `input/`.** Run `git status --porcelain` before
  attributing any delta to the engine — if `input/*.csv` shows as modified
  after a test run, that run rewrote live plan data, not the frozen fixture,
  and the resulting numbers are not evidence of anything about the pin.
- **Run `git status --porcelain` on the whole repo before you start**, and
  keep it clean throughout. `verify-endpoint` (below) refuses to run against
  a dirty tree for exactly this reason: it measures a specific commit in a
  detached worktree, and a dirty main tree makes it ambiguous whether a
  result reflects that commit or your uncommitted changes.

## 1. Measure first — before you form a theory

```
py -3.14 tools/regen_golden_master.py measure
```

Read-only, always safe. Prints the currently-computed values, the pinned
values, and the delta. If the delta is zero, there is nothing to recover —
whatever failed you locally was environment (missing env var, dirty
`input/`), not the pin.

## 2. Decision tree — three leaves, not two

Do not jump straight to "which commit changed the engine." There are three
possible explanations, and picking the wrong one first is what produced the
2026-08-10 postmortem's wrong answer.

```
                    measure shows a nonzero delta
                                |
        was the frozen fixture itself deliberately changed?
           (tests/fixtures/sample_plan_frozen/*.csv, or
            FROZEN_TODAY, or the frozen holdings prices)
                     /                              \
                   yes                                no
                    |                                  |
        LEAF A: intentional evolution      does the pin reproduce at the
        -> regen with --reason              commit that ORIGINALLY set it?
                                              (verify-endpoint <origin sha>,
                                               found via `origin <value>`)
                                                  /                \
                                                yes                  no
                                                 |                    |
                                    LEAF B: unintended         LEAF C: the pin
                                    regression somewhere        never matched --
                                    between the origin           it was stale from
                                    commit and now.               the moment it
                                    -> STOP. Do NOT regen.         was written.
                                    Bisect to find the culprit    -> correct the
                                    (Section 4), open a fix.       constant, say so
                                    Regenerating here would        in the regen
                                    bake the bug into the          --reason text,
                                    baseline.                      and note in the
                                                                    changelog entry
                                                                    that this is a
                                                                    correction, not
                                                                    an engine change.
```

**Leaf A — intentional evolution.** You changed `tests/fixtures/sample_plan_frozen/`
on purpose (new scenario, corrected input), or a deliberate engine/tax-law
constant changed and you can name it. Go straight to Section 3.

**Leaf B — unintended regression.** The fixture did not change, the pin held
at some commit in the past, and it does not hold now. Something broke.
**Do not regenerate.** Regenerating here launders the bug into the new
baseline and the regression ships silently. Bisect (Section 4) to find the
culprit, then fix the culprit — the pin only moves once the fix is confirmed
correct on its own terms.

**Leaf C — the pin never matched.** This is the branch the original
2026-08-10 postmortem's decision tree was missing entirely, and it is checked
**before** any bisecting: run the regen block at the commit that introduced
the pin (`origin <value>` finds it; `verify-endpoint <that sha>` measures
it). If it already disagreed with its own recorded value at the moment it was
written, no amount of bisecting the commits since will explain anything —
you would be bisecting a range that was never good at either end, exactly
what happened in Section 4's own history (see the "premise was wrong" note in
`docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`).
Fix: correct the constant, and write in the changelog entry that this is a
correction of a stale pin, not a description of any engine change.

## 3. Leaf A / Leaf C — regenerate with provenance

```
# write a real justification first, e.g. to a scratch file:
#   - what changed (fixture edit, or the specific commit/constant)
#   - why the new number is right
#   - old value -> new value
py -3.14 tools/regen_golden_master.py regen --reason path/to/reason.txt
```

This is the **only** supported way to move the pin. It:

1. Refuses without `--reason`, and refuses if the reason file is empty, too
   short, or a recognizable placeholder ("TODO", "n/a", etc.) — see
   `tools/regen_golden_master.py`'s `_validate_reason`.
2. Recomputes the values by invoking the test file's own `__main__` regen
   block (never a separate reimplementation of the measurement).
3. Rewrites `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` **and** the
   machine-checked provenance line directly above them (dated today, bound to
   the new values) in one edit.
4. Prepends a dated entry to `documentation/GOLDEN_MASTER_CHANGELOG.md`.

**This is enforced, not just polite.** `tests/test_golden_master_pin_provenance.py`
fails the suite if the pin constants and the provenance line's recorded values
ever disagree, or if the provenance date doesn't match the changelog's newest
entry — so hand-editing the two constants directly (bypassing this tool)
turns the suite red rather than silently succeeding. See that file's
docstring for the three specific checks and the defect-planting evidence in
`.superpowers/sdd/task-4-report.md`.

## 4. Leaf B — bisecting for a real regression

**Measure the "good" endpoint before you bisect against it.** `git bisect`
never re-tests the endpoint you hand it as good — if that commit was already
bad, the entire search range is bad and bisect will hand back a plausible-looking
but meaningless answer. This is exactly what happened in the 2026-08-10
postmortem: the "good" endpoint (`531c883`) was itself already producing the
wrong number, so the bisect result (`355564d`) was noise.

```
# 1. Find a candidate good endpoint (an older commit you believe still held
#    the pin) and verify it BEFORE trusting it as bisect's "good":
py -3.14 tools/regen_golden_master.py verify-endpoint <candidate-good-sha>
# Only proceed if this prints "PIN HELD". If it says "PIN DID NOT HOLD",
# that commit is not a valid bisect endpoint -- go further back and
# verify again. Do not guess; verify.

# 2. Bisect for real, using the verified-good sha:
git bisect start main <verified-good-sha>
git bisect run bash -c '
  RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest \
    "tests/test_frozen_sample_plan_golden_master_regression.py::FrozenSamplePlanGoldenMasterTests::test_frozen_plan_dollar_figures_are_exact" \
    -q >/dev/null 2>&1
'
git bisect reset
git status --porcelain   # must be clean; the run may have mutated input/
```

3. Read the culprit commit and decide whether the change is a real
   regression (stop, fix it, do not regen here) or was in fact intentional
   after all (re-read Section 2 — you may be looking at Leaf A, not Leaf B).

## 5. Trap #2 — finding the pin's true origin commit

`git log -S<value>` can name the **wrong** origin commit if a file rename
happened somewhere in the value's history: a rename makes the value look
"newly added" in the rename commit even though it existed before, and plain
`-S` (without `--follow`) stops looking past the rename. This happened in the
2026-08-10 investigation: a rename in `56c457a` made `git log -S` miss the
value's real origin.

```
py -3.14 tools/regen_golden_master.py origin 5824239.30
```

This always runs `git log --follow -S<value>` against the pin file, so
renames in the file's history do not truncate the result.

## 6. After any leaf: confirm the gate is green and provenance is consistent

```
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest \
  tests/test_frozen_sample_plan_golden_master_regression.py \
  tests/test_golden_master_pin_provenance.py -q -p no:randomly
```

Both files must pass. If the provenance test fails, you (or a colleague)
edited a pin constant by hand — go back to Section 3 and use the tool.

## See also

- `tools/regen_golden_master.py` — the tool this runbook drives.
- `tests/test_golden_master_pin_provenance.py` — the test-enforced gate.
- `documentation/GOLDEN_MASTER_CHANGELOG.md` — the record of every pin move
  and why.
- `documentation/CLAUDE.md`, "Golden master maintenance" — links back here.
- `docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`,
  "Phase 1" — the postmortem this runbook is built to prevent repeating.
