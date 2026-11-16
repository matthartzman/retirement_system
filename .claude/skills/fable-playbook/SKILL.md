---
name: fable-playbook
description: Use at the start of any non-trivial task (feature, bug fix, refactor, design spec, implementation plan, investigation) to plan it, break it into steps, design the software, and check the result before reporting it done. Written for Claude Opus and Claude Sonnet.
---

# Fable Playbook

How to plan a task, split it into steps, design software, and check your own work.
The project `CLAUDE.md` files and the user's direct instructions outrank this file;
where they are more specific (test commands, golden masters, file naming, large-file
rules), follow them.

The short version: **understand before planning, plan before editing, verify before
claiming.** Most bad outcomes come from skipping one of those three, not from lack of
skill in the editing itself.

## 1. Understand the request

Do this before any plan exists.

1. **State the goal in one sentence, including how "done" will be observed.**
   "The reconciliation page shows the manual-adjustment row, and
   `pytest tests/test_x.py` passes." If you cannot write that sentence, you do not
   understand the task yet. Keep reading or ask.
2. **Separate what was asked from what you are assuming.** List the assumptions.
   Settle each one by reading the code, a test, or a doc. Ask the user only about
   things that are theirs to decide: scope, a trade-off between real alternatives,
   anything destructive or outward-facing. Ask one question, with your
   recommendation, and carry on with whatever does not depend on the answer.
3. **Size the task, and match the ceremony to the size.**
   - *Trivial* (one obvious edit): do it, check it, report.
   - *Small* (a few files, one concern): a task list of 3 to 7 steps, no document.
   - *Large* (new behaviour across layers, data-shape changes, anything multi-session):
     a written design first, then an implementation plan, each confirmed by the user.
4. **Locate before you read, read before you think.** Grep for the name, then read
   the region. Find four things:
   - where the behaviour lives,
   - who calls it (grep every usage, not just the first),
   - which tests already pin it,
   - how the repo already solves the same kind of problem.

   Stop exploring when you can name the files you will change and the check that
   will prove the change works. Exploring past that point is procrastination;
   stopping short of it is guessing.

Never rely on memory for a file path, function name, flag, or API signature. Grep
for it. An invented name costs more than the search would have.

## 2. Plan

1. **Work backwards from the end state.** What must be true at the end? What must be
   true just before that? The steps fall out of this better than from "what do I do
   first".
2. **Find the riskiest unknown and settle it first.** If the plan depends on "this
   function is only called from two places" or "the stored file always has this
   key", check that before building on it. A five-minute experiment beats an hour of
   reasoning about what the code probably does.
3. **For anything non-obvious, name two or three approaches, pick one, and give the
   reason in a line.** Default to the smallest change that follows the pattern the
   repo already uses. Do not present a survey; recommend.
4. **Write down what is out of scope.** Things you noticed but will not fix go in the
   final report, not in the diff.
5. **Decide each step's check before starting the step.** A step with no way to tell
   whether it worked is not a step yet.

## 3. Break it into steps

A good step:

- leaves the system working (tests pass at the end of it),
- has one concern,
- is proven by one command or one observation,
- is small enough that its diff can be read in a couple of minutes.

Ordering rules:

- **Risk first**, then dependencies.
- **Data shape and interfaces before the code that consumes them.**
- **One thin slice end to end before widening.** Get a single case through storage,
  server, and UI, then add the rest. This surfaces integration problems while the
  plan is still cheap to change.
- **Keep structural changes (move, rename, extract) separate from behaviour
  changes.** A move that also changes logic cannot be reviewed.
- **Test with or before the code,** never "tests at the end".
- Mark which steps are independent of each other; those can be parallelised or
  reordered if one is blocked.

While executing:

- Keep the task list current, with exactly one step in progress.
- **When a step surprises you, stop and re-plan.** A surprise means the model of the
  system you planned against is wrong, so the remaining steps are suspect too.
- **Two failed fixes for the same problem means stop fixing.** Go back to diagnosis:
  reproduce, read the actual error, trace the data, form one hypothesis, test it.
  Do not stack a third guess on top.
- Do not widen scope mid-step. Note it and move on.

## 4. Design software

Use this for anything sized *large*, and in miniature for everything else.

**Start from data, not from code.**
- What data exists, who owns it, and what shape crosses each boundary (file, API,
  function, UI state)?
- One source of truth for each fact. Derive the rest; do not store a copy that can
  drift.
- What happens to data that already exists? Old plan files, saved state, and
  recorded baselines must still load. If the shape changes, the design includes the
  migration and the fallback.

**Fit the system that is there.**
- Find the existing seam for this kind of change and use it, even if you would have
  drawn it differently. Consistency is worth more than a locally better pattern.
- Read `documentation/reference/CLAUDE.md` and the system design spec before
  touching server, plan-file storage, the build subprocess, or frontend nav.
- Check for an enforcing test (size ratchets, allowlists, naming rules, source-grep
  freezes) before choosing where code goes. Those are constraints on the design,
  not obstacles to route around.

**Design the failure cases, not just the happy path.** For each boundary ask: empty?
missing? malformed? very large? two at once? half-finished? stale? Decide what the
user sees in each case. Validate at the boundary, then trust the data inside it.

**Keep it small.**
- Build what the request needs. No speculative options, flags, or layers.
- Do not abstract until the third real use.
- Separate pure logic from I/O so the logic can be tested without a server, a file,
  or a browser.
- If a unit cannot be described in one sentence without "and", split it.

**Numbers are right or wrong, not roughly right.** This is a financial planning
system. For any change to a rate, tax, rule, or projection, work one representative
case by hand and compare. A plausible-looking total proves nothing.

**A design document contains:** the problem; goals and non-goals; the current state
with file references; the options considered and the one chosen, with the reason;
data shapes and interfaces; error and edge-case behaviour; migration and
backward-compatibility; test strategy; open questions. Put a `Status:` line in the
first 20 lines and follow the naming rule in the project `CLAUDE.md`.

## 5. Write an implementation plan

Write it so that a model with none of your context could execute it correctly.

Each task states:

- the exact files to create or change (paths verified by search, not recalled),
- what changes, concretely enough that there is one obvious implementation,
- the test to write and what it asserts,
- the command to run and the result that means success,
- the commit boundary.

No placeholders: "add appropriate error handling", "update tests as needed", and
"similar to task 3" are not instructions.

Per the project `CLAUDE.md`, each phase also carries a recommended model and effort,
a relative usage estimate (light, moderate, heavy against a 5-hour session), what
drives its context size, and a flag on any step likely to be disproportionately
expensive with a way to scope it down. Estimate in sessions, not calendar weeks:
plans in this repo have historically been over-estimated several-fold. Include the
note to check `/usage` against the estimates as the plan runs.

Before handing the plan over, check it against the design: every requirement maps to
a task, and every task maps to a requirement.

## 6. Check your own work

Treat "it should work" as an untested hypothesis.

1. **Bugs: reproduce first.** Write the failing test, watch it fail *for the right
   reason*, fix, watch it pass. A test you never saw fail has not been shown to test
   anything.
2. **Ask of each new test: would this fail if the code were wrong?** If not, it is
   decoration.
3. **Run narrow, then wide.** The single test, then the file, then
   `pytest -m "not slow"`, then `npm test` if frontend changed, then
   `python tools/fast_gates.py` before any push. Follow the pytest logging rule in
   the user's `CLAUDE.md`.
4. **Exercise the real thing, not only the tests.** If a change is visible in the
   browser, open the preview and look: console errors, network responses, the page
   content. If it changes engine output, run the phase golden test locally, because
   PR CI does not.
5. **Read your whole diff before reporting.** `git diff`, top to bottom. Look for
   debug leftovers, unrelated edits, a file you meant to change and did not, and
   anything you were about to claim that the diff does not actually show.
6. **Re-read the original request and tick off each item.** Requirements get lost
   between the first message and the last step.
7. **Grep the callers again.** Everything that used what you changed still works
   with the new shape.
8. **Never make a check pass by weakening the check.** Do not loosen an assertion,
   raise a ratchet ceiling, extend an allowlist, skip a test, or regenerate a golden
   master to get green. First decide whether the code or the test is wrong, with
   evidence. For goldens, `measure` first and hand-verify one delta.
9. **A subagent's report is a claim.** Check its diff or output before repeating its
   conclusion.

## 7. Report

Lead with the outcome. Then:

- what changed, with file links,
- what you verified and how (the command and its result, seen in this session),
- what you did **not** verify, and why,
- anything you noticed and left alone,
- any decision that is now the user's.

If tests fail, say so and show the output. If a step was skipped, say so. Say "done"
plainly when it is done and verified, and never before.

## Failure patterns to watch for in yourself

| Pattern | Do this instead |
|---|---|
| Acting on the first plausible reading of the request | Write the one-sentence goal and its done-check first |
| Patching the symptom where the error appears | Trace back to where the bad value was produced |
| Stopping at the first green test | Run the wider suite and look at the real behaviour |
| "This is probably fine" about an unread caller | Grep it and read it |
| Recalling a path, name, or signature | Search for it |
| A third attempt at the same fix | Stop; rebuild the diagnosis from evidence |
| Tidying nearby code while you are in there | Leave it; mention it in the report |
| A long silent stretch of work | One-line status at each step change |
| Saying "passes" from memory of an earlier run | Re-run after the last edit, then say it |
| Going round in circles | Say you are stuck, what you tried, and what you would try next |
