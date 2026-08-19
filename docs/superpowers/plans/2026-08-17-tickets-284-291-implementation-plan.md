# Tickets 284–291 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to work this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
> **Nothing in this plan has been executed.** It was written 2026-08-17 against `main` @ `83f8e85`.

**Goal:** Close eight tickets spanning UI navigation, keyboard handling, release tooling, migration
plumbing, a documentation-vs-engine audit, a performance defect, and the removal of Illinois as an
implicit assumption.

**Tech stack:** Python 3.14 (`py -3.14`), pytest + unittest, SQLite (stdlib `sqlite3`), vanilla ES
modules in `frontend/js/`, openpyxl workbook reporting.

---

## Global Constraints

Every one of these has bitten this repo before. They are not boilerplate.

- Run all Python with `py -3.14`. Plain `python` is 3.12 here and lacks pytest/openpyxl.
- Set `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` on **every** test run, or golden-master
  dollar figures drift between runs from live pricing.
- The suite mutates tracked files (`input/*.csv`, several `frontend/js/*.js`). After any broad run,
  check `git status` and `git checkout --` unintended changes. Capture pytest output to a **file** —
  a truncated tail hides `FAILED` lines.
- **Plant the defect and watch the guard go red before closing any finding.** This repo has shipped
  five guards that could not fail. A new test that passes on first write is not yet a test.
- Work on a branch off `main`; never commit directly to `main`.
- Running the app from a worktree still writes `local_state/retirement_system_v10.db` in the **main**
  repo. Migration work (T287) must account for that or it will appear to do nothing.

## Decisions taken (2026-08-17, with the user)

All open questions are resolved. **There are no unresolved assumptions in this plan.**

| # | Decision |
|---|---|
| 284 | New buttons navigate to the standalone steps, exactly parallel to Social Security / Charitable Giving. The inline `<details>` embeds are **removed**; Distribution Strategy becomes a hub. |
| 284 | `renderAllocationPolicy()` is **nested under the Asset allocation page** as a collapsible section — not given its own nav entry, not a seventh button. |
| 285 | The **general** focus-restoration fix in `renderMain` — not the surgical one. It fixes every autosave-then-rerender field in the app. |
| 286 | The provenance gate is **test-enforced**: a hand-edited pin with no dated justification turns the suite red. The tool alone is not sufficient. |
| 287 | The at-rest gate extends to CSV **and** the SQLite `plan_snapshots` rows — **all** snapshots, not just the latest. `.rpx` archives keep relying on per-load normalization. |
| 288 | `bump_version.py` **performs** the folder rename itself, not just emit a script. |
| 288 | The reference sweep **excludes** dated reports and archived plans; `--include-history` opts in. |
| 289 | Helper text is executed this pass. The two engine gaps get a written design only — **not executed**, per the ticket. |
| 289 | The two unmodeled levers are disclosed **in the UI and in the workbook**, so the disclosure survives into the client-facing deliverable. |
| 290 | Measure first, then fix. No fix is committed before the profile names the hotspot; the table-fix approach is chosen against the numbers, not pre-committed. |
| 291 | Text + defaults + data-driven state estate tax off `reference_data/state_tax.csv`. |
| 291 | A missing or unsupported `residence_state` **blocks the build** via the existing preflight. No silent default, no warn-and-continue. |
| 291 | Cost-of-living is presented **relative to the household's own state**, with the IL-derived basis disclosed on the sheet. |

## Recommended execution order

284 → 285 → 290 → 286 → 287 → 288 → 291 → 289.

Rationale: 284/285 are self-contained frontend work that warms up the dashboard module layout. 290 is
the same files while they're in context. 286 hardens the golden master **before** 291 moves engine
figures — you want a trustworthy pin regeneration process in place before the first ticket that
legitimately moves the pins. 287 precedes 291 because 291 introduces new plan-data keys that want the
migration path. 289 is last because it is analysis + text, and its design doc benefits from having
seen the Roth surfaces during 291.

---

## File-to-ticket map

| File | Ticket | Change |
|---|---|---|
| `frontend/js/dashboard_decomp_allocation_optimizer.js` | 284 | `renderPlanningLevers` button set; `renderDistributionStrategy` un-embed |
| `frontend/js/navigation.js` | 284 | restore `roth_conversion` / `allocation_assets` nav visibility |
| `frontend/js/dashboard_decomp_workbook_formatting.js` | 285 | Tab handler + focus-preserving save |
| `frontend/js/dashboard.js` | 285, 290 | `renderMain` focus restore; overlay sequencing |
| `frontend/js/dashboard_decomp_row_model.js` | 290 | `loadYtdStatus` yield points |
| `frontend/js/dashboard_decomp_build_lifecycle.js` | 290 | overlay timer |
| `tools/regen_golden_master.py` (new) | 286 | measure/diff/justify/append |
| `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md` (new) | 286 | procedure + known traps |
| `src/plan_data_migration.py` | 287 | DB snapshot migration |
| `src/local_store.py` | 287 | snapshot rewrite helper |
| `tools/bump_version.py` | 288 | folder rename + reference sweep |
| `src/after_tax.py`, `src/core.py`, `src/planning_engines.py`, `src/data_io.py` | 291 | state defaults + estate generalization |
| `src/reporting/sheets_strategy.py`, `sheets_summary_builder.py`, `summary_figures.py`, `sheets_allocation_helpers.py`, `sheets_stress.py` | 291 | state-aware text + COL re-index |
| `src/server_services/strategy_asset_service.py` | 291 | IL rental default |
| `frontend/js/dashboard_decomp_allocation_optimizer.js` | 289 | Roth helper text |
| `docs/superpowers/plans/2026-08-17-roth-conversion-gap-design.md` (new) | 289 | unexecuted design |

---

## Task 1 — Ticket 284: Roth Conversion and Asset Allocation as buttons on Distribution Strategy

**Current state (verified):** `renderDistributionStrategy()`
(`frontend/js/dashboard_decomp_allocation_optimizer.js:937`) renders `renderPlanningLevers(true)`
followed by two `<details class="decide-embed">` blocks containing `renderRothConversion()` and
`renderAllocationRecommendation()` + `renderAllocationPolicy()`. Inside `renderPlanningLevers`,
`decideButtons` is set to `""` when `embedded` is true (line 76–80), so today the Strategy·decide
card shows only Social Security, Charitable giving, and HELOC strategy.

`navigation.js:23-27` maps `roth_conversion`, `withdrawal_strategy`, `allocation_assets`,
`allocation_policy`, and `investment_strategy` onto `distribution_strategy` — that map is what
suppressed their standalone left-nav entries under ticket 286's earlier consolidation.

**Target:** six sibling buttons in the decide card — Roth conversion, Asset allocation & location,
Withdrawal order, Social Security, Charitable giving, HELOC strategy — each a plain
`leverNavButton` that routes via `data-step-id`. No inline editors on the page.

### Step 1.1 — Restore the standalone routes

- [ ] Read `frontend/js/navigation.js:20-30` and determine exactly what the `distribution_strategy`
      alias map governs (left-nav highlight only, or step resolution too). **Do not assume** — the
      alias may be load-bearing for deep links saved in localStorage.
- [ ] Confirm `renderRothConversion` and `renderAllocationRecommendation` still have live
      `activeStep` branches at `dashboard.js:4100` and `dashboard.js:4111`. They do today; the
      branches were never removed, only the nav entries.
- [ ] Decide per the read: if the alias map only suppresses nav entries, remove the
      `roth_conversion` and `allocation_assets` lines. If it also drives routing, leave the map and
      instead ensure `setStep('roth_conversion')` lands on the standalone renderer.

### Step 1.2 — Emit the buttons

- [ ] In `renderPlanningLevers`, delete the `embedded ? "" : …` conditional on `decideButtons` so
      all three decide buttons render in both modes. Rename the Asset allocation label to
      **"Asset allocation & location"** to match the ticket's wording and the removed section title.
- [ ] Remove the now-dead `embedded` copy in the feature-card header ("Roth conversion and asset
      allocation are below…"), replacing it with the plain `<h3>Strategy · decide</h3>`.
- [ ] Assess whether the `embedded` parameter still has any consumer. If `renderPlanningLevers(true)`
      and `renderPlanningLevers()` now produce identical output, **delete the parameter** rather than
      leaving a no-op flag. Check both call sites first (`renderDistributionStrategy` and whatever
      calls it unembedded).

### Step 1.3 — Un-embed

- [ ] Reduce `renderDistributionStrategy()` to the lever hub:
      `<div class="tabbed-workspace strategy-workspace"><div class="workspace-tab-body">${renderPlanningLevers()}</div></div>`.
- [ ] Grep for `decide-embed` and `decide-embed-sub` in `frontend/css/dashboard.css`. If those
      selectors now have no markup, remove them — dead CSS is how this file grew.
- [ ] **Re-home `renderAllocationPolicy()`.** It was only rendered from inside the removed
      `<details class="decide-embed-sub">`, so un-embedding orphans it. **Decision: nest it under the
      Asset allocation page** — append it to the `allocation_assets` branch at `dashboard.js:4111` as
      a collapsible `<details><summary>Allocation policy settings</summary>` section, so policy sits
      next to the allocation it governs.
- [ ] Do **not** give `allocation_policy` its own nav entry and do **not** add a seventh decide
      button. The hub stays at six buttons; ticket 286 shortened this nav deliberately.
- [ ] Guard this specifically: assert the `allocation_assets` render contains the allocation-policy
      section. An orphaned settings page is silent — nothing errors, the page simply becomes
      unreachable — so it needs an explicit test rather than a click-through.

### Step 1.4 — Guard

- [ ] Add to the existing frontend contract suite (see
      `tests/test_planning_workbench_consolidation_regression.py` for the pattern) a test asserting:
      the Distribution Strategy render contains `data-step-id="roth_conversion"` and
      `data-step-id="allocation_assets"`, contains **no** `decide-embed` markup, and exposes exactly
      six decide buttons.
- [ ] **Plant the defect:** revert Step 1.2's edit, confirm the test fails, restore it.
- [ ] Check `tests/fixtures/frontend_source_grep_baseline.json` — this repo pins frontend source
      greps. Removing markup will move that baseline; regenerate it deliberately, not reflexively.

**Verification:**
```bash
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q -k "planning_workbench or frontend or dashboard" > /tmp/t284.txt 2>&1
grep -E "^FAILED|^ERROR" /tmp/t284.txt || echo clean
```
Then run the app and click each of the six buttons. A button that lands on a blank pane means the
Step 1.1 alias read was wrong.

---

## Task 2 — Ticket 285: Tab / Shift+Tab between column-width fields

**Current state (verified):** `wfWidthInputKeydown`
(`frontend/js/dashboard_decomp_workbook_formatting.js:31-48`) already implements the traversal,
including expanding collapsed `<details>`. **The ticket is not "add this" — it is "this does not
work."**

**Root cause (high confidence, must still be confirmed by measurement):**
`renderMain` is a single synchronous `document.getElementById("mainPane").innerHTML = content`
(`dashboard.js:4140`) — it destroys and rebuilds every node in the pane. The sequence on Tab after
editing a value is:

1. `keydown` fires → handler calls `target.focus()` on the *next* input.
2. Focusing the next input blurs the current one → the browser fires `change` on it.
3. `change` → `setWorkbookColWidth(...)` → `renderMain()` **synchronously** at line 151, before the
   `await`.
4. `#mainPane.innerHTML` is replaced. The element the handler just focused no longer exists.
   Focus falls back to `<body>`.
5. The `await api(...)` resolves later and calls `renderMain()` **again** in `finally`, destroying
   focus a second time even if step 4 were fixed.

So Tab traversal works only when the width was **not** edited — which is exactly the case a user
never exercises.

### Step 2.1 — Prove the cause before fixing it

- [ ] Add a Playwright spec alongside `tests/e2e/workbook-format-stale-cache.spec.js`: open Workbook
      Formatting, type a new width into the first column field, press Tab, assert
      `document.activeElement` is the second width input and its text is selected.
- [ ] Run it. **It must fail**, and the failure must show `activeElement` as `body`. If it passes,
      this analysis is wrong and the real cause is elsewhere — stop and re-diagnose before writing
      any fix.

### Step 2.2 — Preserve focus across re-render (general fix)

**Decision: the general fix in `renderMain`, not a surgical patch to `setWorkbookColWidth`.** Before
the `innerHTML` write, capture `document.activeElement`'s stable identity (a `data-focus-key`
attribute the width inputs carry: `` `wf:${sheet}:${col}` ``) plus its selection range. After the
write, re-query by that key and restore focus + selection.

This is deliberately the wider blast radius. Every autosave-then-rerender field in this app has the
same trap armed — the width field is just where a user finally noticed. A surgical fix to one page
leaves the defect in place everywhere else and guarantees this ticket recurs under a different
field's name.

**Because the radius is wide, the risk controls are not optional:**

- Restoration must be a **no-op** when nothing was focused, when the focused node had no
  `data-focus-key`, or when the key no longer resolves after re-render. Any of those must leave
  focus exactly where the browser put it — never force focus somewhere the user did not ask for.
- `focus({ preventScroll: true })`, or the pane will jump on every keystroke-driven save.
- Restoring selection into a node whose **value changed** between renders would clobber a fresh
  server value with a stale caret range. Restore selection only when the value round-trips identical.

- [ ] Add `data-focus-key` to the width `<input>` in `_wfColRowHtml` (line ~249).
- [ ] In `dashboard.js` around line 4140, wrap the `innerHTML` assignment in capture/restore.
- [ ] Remove the second `renderMain()` in `setWorkbookColWidth`'s `finally` **only if** the reconcile
      genuinely needs no repaint. Read what `out.overrides` changes first — the stale-overrides
      banner depends on it.
- [ ] **Regression sweep for the wide radius.** Because this changes focus behavior app-wide,
      manually exercise at least: a Holdings row edit, a spending-taxonomy field, the YTD transaction
      grid, and any `<select>`-driven autosave. Confirm focus lands where it did before on every one
      — the failure mode of a bad restore is focus *stealing*, which is far more annoying than the
      focus *loss* being fixed.
- [ ] Add one non-workbook test to the guard set (e.g. a Holdings field) proving restoration
      generalizes. A test that only covers the width field would pass even if the mechanism were
      hardcoded to that page.

### Step 2.3 — Confirm and extend

- [ ] Re-run the Step 2.1 spec. It must now pass.
- [ ] Add a Shift+Tab case, and a case that Tabs from the **last** field of a collapsed sheet into
      the first field of the next sheet, asserting the target `<details>` opened.
- [ ] Decide explicitly whether the per-column **alignment** control joins the tab order. The ticket
      says column width only; the current handler queries only `.wf-col-width input[type=number]`.
      **Leave alignment out** and note it in the commit message so the omission reads as a decision.

---

## Task 3 — Ticket 290: Actual Spending hangs; progress bar frozen at 0:00

**Symptom (from the ticket):** long locked screen before the progress bar appears; then the spinner
animates but the elapsed timer never leaves 0:00; clicking Spending Model is slow with no progress
bar at all.

**Working hypothesis — the frozen timer is the diagnostic.** `setBuildOverlay`
(`dashboard_decomp_build_lifecycle.js:29-49`) starts `setInterval(refreshBuildOverlayTimer, 1000)`.
A CSS spinner animates on the compositor thread and keeps spinning even when the main thread is
blocked; a `setInterval` callback cannot fire. **A spinning spinner over a frozen 0:00 is a
main-thread block, not a slow server.** If the server were slow, the timer would count up normally.

The pre-overlay lock has a matching explanation: `goToStrategyTab`
(`dashboard.js:3911-3922`) calls `setStep(step)` — which triggers a full synchronous `renderMain()`
of the spending workspace — **and only then** calls `loadYtdStatus(false)`, which is what shows the
overlay. So the expensive render happens before any progress affordance exists. That also explains
the third symptom: Spending Model shows no progress bar because nothing on that path calls
`setBuildOverlay` at all.

**This is a hypothesis with a mechanism, not a conclusion.** Per the user's decision and this repo's
own workbook-speed postmortem (cProfile misattributed the cost; the real wins were elsewhere),
Step 3.1 measures before anything is changed.

### Step 3.1 — Measure (no fixes in this task)

- [ ] Instrument with `performance.mark`/`measure` around four spans, logged to console:
      (a) `api("/api/ytd/status")` wall time, (b) the `renderMain()` inside `setStep`,
      (c) the `renderMain()` after `loadYtdStatus` resolves, (d) the `innerHTML` assignment alone.
- [ ] Reproduce on a realistic transaction history. Record the row count —
      `/api/ytd/status` returns every transaction, and the cost is almost certainly O(rows).
- [ ] Separately time the server handler. Find it with
      `grep -rn "ytd/status" src/server/`. Distinguish "server took 4s" from "server took 200ms and
      the browser spent 4s building a 6,000-row table".
- [ ] Repeat for the Spending Model page (`spending_core` → `renderSpendingModel*`).
- [ ] **Write the numbers into the ticket before proposing a fix.** If the server dominates, Tasks
      3.2/3.3 below are the wrong fix and must be rewritten.

### Step 3.2 — Fix, conditional on 3.1 (client-bound case)

- [ ] **Show the overlay first.** In `goToStrategyTab`, call `showYtdLoadOverlay()` *before*
      `setStep`, and yield (`await new Promise(r => requestAnimationFrame(r))`) so the browser
      actually paints it before the blocking render begins. Painting an overlay you never yield to
      is why the current one appears late.
- [ ] **Let the timer tick.** Break the render into chunks that yield to the event loop, or move the
      elapsed display off `setInterval` onto a `requestAnimationFrame` loop driven by
      `Date.now() - buildOverlayStartedAt`. A frozen 0:00 tells the user the app is dead; a ticking
      counter over the same wait does not.
- [ ] **Cut the render cost.** Most likely the transaction table. **The approach is deliberately not
      pre-committed** — Step 3.1's numbers choose it. The candidates, and what each requires the data
      to show before it is the right answer:
      - *Paginate (first N rows + "show all")* — right if cost scales with row count and planners
        rarely need the whole year on screen at once. Simplest; changes how transactions are scanned.
      - *`DocumentFragment` instead of one template string* — right only if string-building and
        parsing dominate. No UX change. Useless if the cost is layout/reflow.
      - *Virtualize* — right only if histories are large enough that even a yielded render is slow.
        Most new code, in a file that is already large.
      Record which one the numbers selected, and why the others were rejected, in the commit message.
      This repo's workbook-speed postmortem is on record that the guessed hotspot was wrong and that
      one "obvious" optimization actively backfired.
- [ ] Give the Spending Model path the same overlay treatment so symptom three is covered.

### Step 3.3 — Fix, conditional on 3.1 (server-bound case)

- [ ] Profile the `/api/ytd/status` handler with `cProfile`, then confirm against wall-clock — this
      repo has a recorded case of cProfile lying about scipy costs.
- [ ] Likely candidates: re-reading and re-parsing every transaction CSV per request; recomputing the
      YTD blend on every call. Cache keyed on file mtime, or paginate the endpoint.

### Step 3.4 — Guard

- [ ] Add a Playwright test asserting the overlay is visible within 500ms of clicking
      "Actual Spending (YTD)", and that the timer text changes at least once during a load ≥2s.
- [ ] **Plant the defect:** revert the overlay-ordering change and confirm the test goes red.
- [ ] A pure-timing test is flaky by nature. If it cannot be made stable, assert the **ordering**
      instead (overlay node gets `.active` before the pane's `innerHTML` is replaced) via a
      MutationObserver — an ordering assertion is deterministic where a stopwatch is not.

---

## Task 4 — Ticket 286: Golden-master recovery process

**Current state:** pins are green (`PINNED_TERMINAL_NW = 5824239.30`,
`PINNED_LIFETIME_TAX = 1290848.91`, `tests/test_frozen_sample_plan_golden_master_regression.py:172`).
The recovery *procedure* exists only as prose in that file's docstring and as a postmortem inside
`docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`. There is no
tool, and nothing forces a justification to be recorded when a pin moves.

The 2026-08-10 postmortem recorded two method traps that cost real time and produced a **confidently
wrong** answer. Both belong in the tooling, not in someone's memory:

1. `git bisect` never re-tests the "good" endpoint you hand it. The endpoint was already bad, so the
   whole range was bad and the result (`355564d`) was meaningless. **Measure the good endpoint first.**
2. `git log -S <value>` named the wrong origin commit because a file rename made the value look newly
   added. **Use `git log --follow -S`.**

A third branch was missing from the original decision tree and must be first-class in the runbook:
beside "intentional" and "regression" there is **"the pin never matched"** — check by running the
regen block at the commit that introduced the pin, *before* bisecting anything.

### Step 4.1 — `tools/regen_golden_master.py`

- [ ] Read the `__main__` regen block in `tests/test_frozen_sample_plan_golden_master_regression.py`
      and reuse it — do not reimplement the measurement.
- [ ] Subcommands:
      - `measure` — print current computed values and the delta vs. the pins. Read-only, always safe.
      - `verify-endpoint <sha>` — check out `<sha>` in a **detached worktree**, measure, report
        whether the pin held there. This is trap #1, mechanized. It must refuse to run against a
        dirty tree.
      - `origin <value>` — run `git log --follow -S<value>` on the pin file and print candidates.
        Trap #2, mechanized.
      - `regen --reason <file>` — rewrite the two constants, **requiring** a non-empty justification
        file, and append a dated entry to `documentation/GOLDEN_MASTER_CHANGELOG.md`.
- [ ] `regen` must refuse without `--reason`, and must refuse if the reason text is under some
      minimal length or is a placeholder. The whole point is that a pin cannot move silently.
- [ ] Every subcommand sets `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` internally. A
      forgotten env var is how "drift" gets misdiagnosed as an engine change.

### Step 4.2 — Provenance gate (test-enforced)

**Decision: the gate is a test, not just tool etiquette.** A pin hand-edited without a recorded
justification must turn the **suite** red. Tool-only enforcement fails exactly when it matters —
under time pressure, when someone edits the constant directly to get green.

- [ ] Add a test that parses the pin file's provenance comment block and asserts every `PINNED_*`
      constant has a dated entry above it. Then assert the newest date in the comment block matches
      the newest entry in `GOLDEN_MASTER_CHANGELOG.md`.
- [ ] The gate must key on the **value**, not merely the presence of a comment: bind each dated entry
      to the constant value it justifies, so editing `PINNED_TERMINAL_NW` while leaving last month's
      comment untouched still fails. A gate that only checks "is there a comment" is trivially
      satisfied by a stale one — and this repo has shipped that exact shape of non-guard.
- [ ] **Plant the defect, twice:** (a) change a pin by hand with no comment — must go red; (b) change
      a pin by hand while leaving the previous dated comment in place — must **also** go red. If (b)
      passes, the gate is measuring comment existence rather than provenance, and is one of the five
      guards-that-cannot-fail this repo has already shipped. Do not close this task until (b) is red.
- [ ] Make the failure message say what to do — name `tools/regen_golden_master.py regen --reason`
      and the runbook path. A gate that blocks without pointing anywhere gets bypassed.

### Step 4.3 — `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`

- [ ] Write the decision tree with **three** leaves: intentional evolution → regen with reason;
      unintended regression → **stop, do not regen**, open a fix (regenerating bakes the bug into the
      baseline); pin never matched → verify at the introducing commit, correct the constant, and say
      so.
- [ ] Document both traps with the exact commands, and the `measure`-before-`bisect` order.
- [ ] Document the environment invariants: `py -3.14`, the price-provider env var, and that the suite
      mutates `input/` so `git status` must be checked before attributing a delta to the engine.
- [ ] Link it from `documentation/CLAUDE.md` and from the pin file's docstring, or nobody will find it.

---

## Task 5 — Ticket 287: At-rest plan-data migration gate

**Current state (verified):** the gate is real and wired.
`PLAN_DATA_SCHEMA_VERSION = 3` (`src/plan_data_migration.py:26`); `stored_schema_version` /
`needs_migration` / `migrate_plan_data_at_rest` / `run_startup_plan_data_migration` all exist
(lines 247–338); `main.py:139` calls it at boot for both server and desktop modes.

**The gap:** `migrate_plan_data_at_rest` globs `input/*.csv` and rewrites those files only. But the
canonical read surface is the **database** — `config_backend.py:297` reads
`local_store.latest_sectioned_data()`, which returns `plan_snapshots.sectioned_json`
(`local_store.py:195-202`). A store whose CSVs are migrated but whose newest snapshot still holds
legacy keys is migrated in name only; every read still leans on the per-load
`migrate_sectioned_data` normalization the gate was built to retire.

### Step 5.1 — Prove the gap

- [ ] Write a failing test: seed a temp DB with a `plan_snapshots` row whose `sectioned_json`
      contains a legacy key (`husband_name`, or a `wellness_*` Monte Carlo key — v3's transform),
      run `migrate_plan_data_at_rest`, and assert the stored JSON now holds the current key.
- [ ] Run it. It must fail. **If it passes, the gap does not exist as described** — re-read
      `migrate_plan_data_at_rest` before writing any code.

### Step 5.2 — Snapshot rewrite helper in `local_store.py`

- [ ] Add `rewrite_sectioned_snapshots(transform, db_path=None) -> int`, where `transform` takes a
      sectioned dict and returns `(new_dict, changed_count)`. It iterates `plan_snapshots`, applies
      the transform, and `UPDATE`s **only rows that changed**.
- [ ] **Preserve `created_at` and `rowid` ordering.** `latest_sectioned_data` resolves ties by
      `created_at DESC, rowid DESC` (`local_store.py:200`); an `UPDATE` that touches `created_at`
      would silently reorder history and change which snapshot is "latest".
- [ ] Wrap the whole sweep in one transaction. A half-migrated snapshot table is worse than an
      unmigrated one.
- [ ] **Decision: migrate ALL snapshots, not just the latest.** Old snapshots are restorable, and a
      restore that resurrects legacy keys *after* the version has been stamped would defeat the gate
      permanently — the store would report "migrated" while serving legacy shapes. Cost is a one-time
      O(snapshots × rows) sweep.
- [ ] Measure the snapshot table size before the first real run
      (`SELECT COUNT(*) FROM plan_snapshots`) and record it. Per-build backups mean this table grows
      steadily; if the sweep turns out to take more than a few seconds, say so in the ticket rather
      than silently shipping a slow boot. No row cap is being added — but an unbounded sweep on a
      startup path is worth a measured number rather than an assumption.
- [ ] Print progress (or at minimum the final count) when the sweep touches a large table. A boot
      that appears hung is the same defect as ticket 290.

### Step 5.3 — Extend the runner

- [ ] In `migrate_plan_data_at_rest`, after the CSV loop and **before** `set_stored_schema_version`,
      call `rewrite_sectioned_snapshots(migrate_sectioned_data, db_path=db_path)` and fold its count
      into the report as a new `"snapshots"` key. Keep `total_changed` as the sum so existing callers
      (including `main.py:140`'s `if _migration["total_changed"]`) keep working.
- [ ] Honour `dry_run` — it must not write to the DB either. The existing dry-run test only covers
      CSVs; add the DB case.
- [ ] Confirm the failure mode: a DB error must degrade the same way a bad CSV does, leaving the
      version **unstamped** so the migration retries next boot. Never stamp after a partial failure.
- [ ] Re-run 5.1's test. It must now pass.

### Step 5.4 — Idempotence and the worktree trap

- [ ] Add a test that runs the migration twice and asserts the second run reports `skipped: True` and
      performs zero `UPDATE`s.
- [ ] **Worktree caution:** the app writes `local_state/retirement_system_v10.db` in the *main* repo
      even when run from a worktree. When testing the real migration, confirm which DB file was
      actually touched (`ls -l` before/after) rather than assuming the worktree's copy.
- [ ] Back up `local_state/retirement_system_v10.db` before the first real run. `.rpx` per-build
      backups copy the whole DB, so a bad migration is recoverable — but only if you know which
      backup predates it.

### Step 5.5 — Verify against live data

```bash
py -3.14 -c "
from pathlib import Path
from src.plan_data_migration import migrate_plan_data_at_rest
print(migrate_plan_data_at_rest(Path('input'), dry_run=True))
"
```
- [ ] Expect `total_changed: 0` against live data — it is already at v3. A non-zero count means real
      legacy rows survived the F5 migration and the diff must be reviewed before applying.
- [ ] Full suite twice (correctness, then idempotence), per the Global Constraints.

---

## Task 6 — Ticket 288: Version bump renames the Windows folder and its references

**Current state:** `tools/bump_version.py` updates `src/version.py`, `frontend/index.html`,
`system_config.csv`, regenerates the plan-data manifest, and runs `check_version_surfaces.py`.
It knows nothing about the workspace folder name.

**Known folder references** (from a repo sweep, excluding `dist/`, `node_modules/`, and generated
`output/`/`saved_plans/` artifacts):

| File | Form |
|---|---|
| `tools/backup_to_onedrive.py:108` | `Path("Version 10")` — archive prefix |
| `tools/validate_clean_overlay.py:7` | `"Version 10 - ChatpGPT.zip"` in a usage docstring |
| `documentation/CLAUDE.md:42` | prose path `C:\RetirementPlanning\Version 10 - ChatpGPT` |
| `.claude/settings.local.json` | absolute paths |
| `docs/superpowers/plans/*.md`, `documentation/reports/*.md` | historical `cd "C:/RetirementPlanning/Version 10"` commands |

**Decision on sweep scope.** Historical plans and dated review reports are records of what was true
then; rewriting a `cd` command inside a 2026-07-18 report falsifies the record.

- **Swept:** `src/`, `frontend/`, `tools/`, `launchers/`, `.claude/`, `documentation/CLAUDE.md`.
- **Excluded:** `documentation/reports/`, `documentation/archive/`, `docs/superpowers/plans/`,
  `dist/`, `build/`, `node_modules/`, `output/`, `saved_plans/`.
- **`--include-history`** opts the excluded doc roots in, for the case where someone genuinely wants
  every path updated.

State this in the tool's docstring as a decision with its reason, not as a config default — the next
person to read it should understand why a report was skipped rather than assume the sweep missed it.

**The rename itself.** The user chose to have the script perform it. On Windows a process cannot
rename a directory that is its own CWD or that holds an open handle. The design must therefore be:

### Step 6.1 — Reference sweep (safe half, ships independently)

- [ ] Add `--folder-name NEW` (default `Version {new_version}`), and a `sweep_folder_references()`
      that rewrites `Version <old>` → `Version <new>` across the allowlisted roots, skipping binary
      suffixes exactly the way `check_version_surfaces.py:26` does.
- [ ] Note the wrinkle: `documentation/CLAUDE.md` says `Version 10 - ChatpGPT`, not `Version 10`.
      The regex must handle a suffix after the number, or it will silently miss the one file most
      likely to mislead a future reader. Also note `- ChatpGPT` is a typo present in the tree —
      preserve it verbatim; correcting it is a different ticket.
- [ ] Add `--dry-run` printing every file and line that would change. **Make dry-run the default**
      for the sweep and require `--apply`; this touches paths, and a bad regex here breaks launchers.

### Step 6.2 — Preflight

- [ ] Refuse to proceed if: the git tree is dirty; the target folder already exists; a
      `retirement_planner` / `python` process is running out of this tree; or `local_state/*.db` has
      an open handle.
- [ ] Detect handles with `Get-Process | Where-Object {$_.Path -like "$root*"}` plus an attempted
      exclusive open on `local_state/retirement_system_v10.db`. Report **which** process blocks it —
      "rename failed" without a name sends the user hunting.
- [ ] Advise closing editors and the app. A VS Code window with the folder open is the most likely
      blocker and produces a confusing partial failure.

### Step 6.3 — Out-of-process rename

- [ ] Generate a self-deleting PowerShell script in `%TEMP%`, launch it **detached** with
      `subprocess.Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)`, then exit
      the Python process immediately so its CWD handle is released.
- [ ] The PS script: waits for the parent PID to exit (bounded, ~30s); `Move-Item` the folder;
      on failure, prints the error and leaves everything untouched; on success, prints the new path
      and how to relaunch.
- [ ] **Do not attempt rollback of the reference sweep on rename failure.** The sweep is committed to
      git; `git checkout --` is the rollback, and telling the user that is more reliable than a
      half-written undo path. Print that instruction on failure.
- [ ] Re-run `tools/INSTALL_DESKTOP_ICON.py` guidance in the success message — the desktop shortcut
      holds an absolute path and will be dead after the move.

### Step 6.4 — Tests

- [ ] Unit-test `sweep_folder_references()` against a temp tree: allowlisted file rewritten, report
      file untouched, binary skipped, `- ChatpGPT` suffix handled.
- [ ] Unit-test the preflight refusals with fakes. **Do not** integration-test the actual rename in
      CI — it would move the checkout out from under the runner.
- [ ] Manual verification checklist in the docstring: rename, relaunch via `launchers/START_APP.bat`,
      confirm the app boots, confirm `tools/backup_to_onedrive.py` writes under the new prefix.

---

## Task 7 — Ticket 291: Remove Illinois as a hard-coded assumption

**Scope (agreed):** text + defaults + data-driven state estate tax, and cost-of-living presented
relative to the household's own state. A missing or unsupported `residence_state` blocks the build.
Per-state rental assumptions and a 50-state estate expansion are out of scope but must be handled
honestly rather than left silently wrong.

**Inventory — five distinct classes, each needing a different fix.**

**Class 1 — silent `"Illinois"` defaults.** An unset state does not fail; it becomes Illinois.
`src/after_tax.py:455,539`; `src/planning_engines.py:2099`; `src/data_io.py:697,2562`;
`src/core.py:864`; `src/projection_stages/deterministic_engine.py:1570`;
`src/reporting/sheets_strategy.py:700,1099,1112,1347`; `src/reporting/summary_figures.py:84`.

**Class 2 — Illinois-only estate tax modeling.** `src/core.py:1054-1077` implements the pre-2005
federal credit table and the IL cliff. `src/after_tax.py:524-539` and
`sheets_strategy.py:1344-1349` gate the whole estate section on `state == "Illinois"`.
`reference_data/state_tax.csv` already carries `estate` and `estate_exempt` columns for its 13 rows —
the data exists; only the code is hardcoded.

**Class 3 — cost-of-living indexed to Illinois = 1.00.** `src/taxes.py:213` (`STATE_COL_FACTORS`),
`sheets_strategy.py:1096-1126`, `sheets_stress.py:800`. The workbook tells the reader the numbers are
"indexed to Illinois = 1.00", which is meaningless to a Florida household.

**Class 4 — plan-data keys and schema.** `c['il_exempt']` (`data_io.py:1442`) sourced from section
`Estate Planning`, subsection **`Illinois`**. `reference_data/schema.csv:12` defaults
`residence_state` to `Illinois`.

**Class 5 — hardcoded IL literals elsewhere.** `sheets_allocation_helpers.py:186` (`== 'IL'`);
`sheets_strategy.py:65,104,134,1234,1464` (IL prose in strategy sheets);
`src/server_services/strategy_asset_service.py:91` (`"IL"` rental defaults).

### Step 7.1 — Baseline the blast radius first

- [ ] Record the frozen golden-master pins **before** any change. The frozen fixture household is an
      Illinois resident, so a correct implementation should leave the pins **unchanged**. Any
      movement means behavior changed for an IL household, which is a bug in this ticket, not a
      legitimate regen.
- [ ] Read `tests/test_unsupported_state_preflight_regression.py` and
      `tests/test_state_residency_baseline_anchor_regression.py` in full. A preflight for
      unsupported states already exists; this ticket must extend it, not duplicate it.
- [ ] Read `tests/test_illinois_estate_tax_and_aca_ptc_boundaries.py` — it pins IL estate behavior
      and is the guard that must stay green through Class 2's generalization.

### Step 7.2 — Class 1: make the default explicit

- [ ] Introduce a single module-level `DEFAULT_RESIDENCE_STATE` and have `data_io.py:697` be the
      **only** place it is applied. Every downstream `c.get("state", "Illinois")` becomes
      `c["state"]` or `c.get("state", "")`.
- [ ] **Decision: a missing or unsupported `residence_state` BLOCKS the build.** Route to the
      existing unsupported-state preflight; never substitute a state. Silently producing Illinois
      numbers for a Texas household is the exact defect this ticket exists to remove, and a warning
      that a planner skims past still ships wrong numbers to a client.
- [ ] The preflight message must name the field, its current value, and the supported state list, and
      point at the page where residency is set. A block that does not say how to unblock is a bug
      report from the user's side.
- [ ] `src/core.py:864`'s fallback to Illinois rules for unknown states becomes an explicit failure,
      not a labelled fallback. Note the comment at `core.py:839`: a previous version *already*
      silently borrowed IL's 4.95%, and that was fixed once. This is the same known-bad pattern
      living one layer up — do not re-introduce it under a different name.
- [ ] **Migration consideration:** any existing plan with a blank `residence_state` that previously
      built fine will now fail to build. That is intended, but it must fail *legibly*. Check whether
      the demo plan, the frozen fixture, and `tests/synthetic_plans.py` all set the field explicitly
      before landing this — a preflight that breaks the test corpus on contact will get reverted
      rather than fixed.
- [ ] Guard: build a plan with `residence_state` blank and assert the preflight fires. **Plant the
      defect** by restoring one default and confirm the guard goes red.

### Step 7.3 — Class 2: data-drive the state estate tax

- [ ] Extend `reference_data/state_tax.csv` with an `estate_calc` column naming the mechanism
      (`il_credit_table`, `flat_rate`, `none`) so the engine dispatches on data, not on a state name.
- [ ] Refactor `src/core.py:1054-1090` so the IL credit-table calculation becomes one **named
      strategy** behind a dispatcher, keyed off `estate_calc`. Do not delete it — it is correct for
      Illinois and pinned by an existing test.
- [ ] Replace the `state == "Illinois"` gates in `after_tax.py:539`, `planning_engines.py:2099`,
      `sheets_strategy.py:1347`, and `summary_figures.py:84` with a lookup on the row's `estate` flag.
- [ ] For states in the CSV with `estate = FALSE`, the estate section must render an explicit "your
      state does not levy an estate tax" rather than being silently absent. For states **not in the
      CSV at all**, it must say the state is not modeled — never omit silently.
- [ ] Guard: parametrize over IL (tax computed), FL (`estate = FALSE`, explicit no-tax note), and an
      absent state (explicit not-modeled note). Confirm IL's existing boundary test still passes
      **unchanged** — that is the proof the refactor preserved behavior.

### Step 7.4 — Class 3: re-index cost of living

- [ ] **Decision: compute factors relative to the household's own state at render time.** Do **not**
      re-base the table to a national 1.00 — the underlying factors are IL-derived, and a "national"
      label on IL-derived data would be a fiction, which is the same defect this ticket is removing.
- [ ] Divide each state's factor by the household state's factor at render time. Illinois households
      see numerically identical output to today (their divisor is 1.00) — a useful check that the
      transform is arithmetic-only.
- [ ] Update the prose at `sheets_strategy.py:1126` and `sheets_stress.py:800` to read as a direct
      comparison ("about 15% less than <current state>") **and to disclose that the underlying index
      is Illinois-derived**. Both halves are required: the comparison is what the reader needs, and
      the disclosure is what keeps it honest. Dropping the disclosure would relabel an Illinois index
      as neutral, which is exactly the pattern being removed.
- [ ] Record a follow-up ticket to replace `STATE_COL_FACTORS` with a properly sourced regional cost
      index, at which point the disclosure can be dropped. Out of scope here — sourcing that data is
      its own piece of work, not a line item inside a de-hardcoding pass.
- [ ] Guard: for a Florida household, assert no rendered string contains "Illinois" and the basis row
      names Florida.

### Step 7.5 — Class 4: rename the plan-data keys via the T287 gate

- [ ] Rename `il_exempt` → `state_estate_exemption_amount` and section
      `Estate Planning|Illinois` → `Estate Planning|State`.
- [ ] Add both to `_LABEL_RENAMES` in `src/plan_data_migration.py` and bump
      `PLAN_DATA_SCHEMA_VERSION` to 4. **`migrate_rows` semantics are load-bearing: "current key
      wins" — a legacy row colliding with an existing current row is DROPPED, never overwritten.**
      Add a test proving the new renames preserve that.
- [ ] Update `reference_data/schema.csv:12` so `residence_state` has no Illinois default.
- [ ] Sequencing: this depends on T287 landing first, so the DB snapshots get the rename too.
- [ ] Dry-run against live `input/` and confirm the changed-file list matches expectations before
      applying.

### Step 7.6 — Class 5: the remaining literals

- [ ] `sheets_allocation_helpers.py:186` — read what the `== 'IL'` branch does before touching it.
      It may be a legitimate state-specific muni-bond rule, in which case it becomes a data-driven
      lookup, not a deletion.
- [ ] `sheets_strategy.py:65,104,134,1234,1464` — parameterize every IL string on the household's
      state. The S-corp surcharge (line 104/134) and the retirement-income exemption (line 1234) are
      real IL tax rules; they must become conditional on the resolved state, and must render the
      correct rule or none at all for other states.
- [ ] `strategy_asset_service.py:91` — the `"IL"` rental defaults are **out of scope** for
      generalization. Do not leave them silently applied to a Texas property: gate them so a
      non-modeled state returns "no default assumptions available; enter values" rather than Illinois
      numbers. Record the expansion as a follow-up ticket.

### Step 7.7 — Full-tree verification

- [ ] `grep -rin "illinois" src/ frontend/ reference_data/` and triage every remaining hit into:
      legitimate data row, legitimate comment about IL-specific rules, or defect. Zero unexplained
      hits.
- [ ] Frozen golden master **must be unchanged** (the fixture household is IL). If it moved, an
      IL-path behavior changed — find it before regenerating anything.
- [ ] Full suite twice, `git status` checked after each.

---

## Task 8 — Ticket 289: Roth Conversion Modeling Guide vs. implementation

**Deliverables:** (a) a clause-by-clause audit, (b) **executed** helper-text enhancements,
(c) an **unexecuted** design + implementation plan for the two engine gaps.

**Audit, first pass (verified by grep — Step 8.1 must confirm each line):**

| Guide requirement (§) | Implementation | Status |
|---|---|---|
| Tax discount rate (§2) | `_roth_discount_rate`, `roth_tax_discount_rate` (`planning_engines.py:44,57`) | Present |
| Bracket-fill ceiling (§2) | `roth_target_bracket_rate`, `roth_headroom_usage_pct` | Present |
| Terminal vs. lifetime weighting (§2) | `roth_optimize_terminal_weight`, `roth_optimize_lifetime_tax_weight` | Present |
| IRMAA bumpers (§4 Var 2) | `roth_irmaa_target_tier`, `_roth_irmaa_target_threshold_base` (`planning_engines.py:1396`) | Present |
| State tax / residency arbitrage (§4 Var 3) | state rules exist; **guide names Illinois explicitly** | Present — and its §4 example text is itself an instance of ticket 291 |
| Surviving-spouse compression (§4 Var 4) | survivor stress module | Present |
| SS tax torpedo (§4 Var 5) | provisional income in the tax engine | Present |
| SECURE 10-year heir rules (§3) | `after_tax.py` heir mechanics | Present |
| **Conversion tax payment source (§4 Var 1)** | **no `conv_tax_source` / `tax_payment_source` key anywhere in `src/`** | **GAP** |
| **Asset-location-aware conversion (§4 Var 6)** | **no conversion-time sleeve selection anywhere in `src/`** | **GAP** |

The guide calls Var 1 a "Critical Multiplier". It is the largest single unmodeled lever in the doc.

### Step 8.1 — Complete the audit

- [ ] Walk all five guide sections clause by clause. For each, name the implementing symbol and file
      **or** mark it a gap. Do not accept the table above without re-verifying — it is a grep result,
      not a read of the engine.
- [ ] For each "Present" row, check the implementation actually matches the guide's *semantics*, not
      just that a similarly-named key exists. A `roth_tax_discount_rate` that discounts the wrong
      side of the equation is a gap wearing the right name.
- [ ] Write `docs/superpowers/plans/2026-08-17-roth-guide-audit.md`.

### Step 8.2 — Helper text (executed)

- [ ] Enhance the Roth field help across `renderRothRows` /
      `dashboard_decomp_allocation_optimizer.js:753-925` and the corresponding
      `reference_data/schema.csv` notes. Priorities:
      - **Tax discount rate** — the guide's rule that it should equal expected portfolio return
        (~6.5–7.0% nominal / 4.0–5.0% real), and *why* a higher rate understates Roth value.
      - **Target bracket rate** — the 10–12% / 22–24% / 32%+ decision rule from §1C.
      - **IRMAA target tier** — that it is a 2-year-lookback surcharge affecting both spouses.
      - **Terminal vs. lifetime weight** — what trading one for the other actually does.
- [ ] Match the existing voice in this file: plain language, explains the mechanism, no jargon
      without expansion (see the QCD text at `dashboard.js:4481` as the house style).
- [ ] **Disclose the two gaps in the UI *and* in the workbook.** The model does not choose the
      conversion tax payment source and does not convert equity sleeves preferentially. This is the
      same class of disclosure the Monte Carlo sheet got under P4 and the liquidity buffer got under
      P7 — and like those, it belongs where the *client* sees it, not only where the planner does.
- [ ] UI: a note on the Roth page, near the conversion policy controls.
- [ ] Workbook: add the disclosure to the Roth conversion sheet. Find the owning writer with
      `grep -rn "roth" src/reporting/sheets_*.py` and match the surrounding disclosure voice — the
      P4/P7 notes in `sheets_stress.py` are the house style: state what the model *does* do, then
      name the lever it does not have. Never phrase it as a limitation the reader must infer.
- [ ] The workbook disclosure must be phrased so it stays true if the features are later built —
      or, better, be emitted from the same place that would gain the feature flag, so building the
      lever removes the disclosure automatically. A stale disclosure claiming a shipped feature
      doesn't exist is worse than none.
- [ ] Guard: assert the new helper text is present for each named field, that the UI disclosure
      renders, and that the workbook cell exists in a built sheet. Existing helper-text tests and the
      P4/P7 disclosure tests show both patterns.
- [ ] **Plant the defect** on the workbook assertion specifically — a test that greps a sheet for a
      string it also supplies is the classic non-guard. Delete the writer line and confirm red.

### Step 8.3 — Design the two gaps (NOT executed)

Write `docs/superpowers/plans/2026-08-17-roth-conversion-gap-design.md` covering:

- [ ] **Conversion tax payment source.** New plan-data key (`roth_conversion_tax_source`:
      `taxable_cash` | `withhold_from_ira`), where it enters the cascade in `apply_roth_conversion`
      (`planning_engines.py:1245+`), the under-59½ penalty path the guide calls out, and the
      interaction with the liquidity-buffer floor. Include the expected pin movement — **this one
      will move the golden master**, and T286's tooling is what records why.
- [ ] **Asset-location-aware conversion.** How sleeve-level selection would enter conversion, and its
      interaction with the existing allocation optimizer and per-account return modeling. Flag
      honestly that the MC models **location, not in-account sleeve variance** — so a sleeve-aware
      conversion may not show up in the success rate at all, which bounds how much this feature can
      truthfully claim.
- [ ] For each: files touched, test strategy, estimated pin impact, and a recommendation on whether
      it is worth building. A design that concludes "don't build this" is a valid outcome.
- [ ] **Stop at the document.** No code.

---

## Verification — whole plan

```bash
cd "C:/RetirementPlanning/Version 10"
RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1 py -3.14 -m pytest tests/ -q > /tmp/all.txt 2>&1
grep -E "^FAILED|^ERROR" /tmp/all.txt || echo "clean"
git status --porcelain
npx playwright test
```

Run the Python suite **twice** after T287 — the first proves correctness, the second proves the
migration is idempotent and is not re-running on every boot.

---

## Self-review

**Ticket coverage:** 284 ✓ (Steps 1.1–1.4) · 285 ✓ (2.1–2.3) · 286 ✓ (4.1–4.3) · 287 ✓ (5.1–5.5) ·
288 ✓ (6.1–6.4) · 289 ✓ (8.1–8.3) · 290 ✓ (3.1–3.4) · 291 ✓ (7.1–7.7).

**Open assumptions:** none. All nine decisions were resolved with the user on 2026-08-17 and are
recorded in the Decisions table above. What remains open is deliberately open, and is of two kinds
only:

- **Measurement-gated**, by design: T290's fix branch (Steps 3.2 vs 3.3, and which table strategy)
  is chosen by Step 3.1's numbers. Committing to a fix before measuring is the failure this repo's
  workbook-speed postmortem already recorded once.
- **Read-gated**, because guessing would be worse than looking: T284 Step 1.1's `navigation.js` alias
  semantics, T287 Step 5.2's snapshot ordering, T291 Step 7.6's `sheets_allocation_helpers.py:186`
  branch, and T286 Step 4.1's worktree invocation. Each step says what to read and what would
  invalidate the surrounding plan.

**Risk concentrated in three places, worth naming:**

1. **T285's general focus restoration touches every page in the app.** The chosen fix is the right
   one — the trap is armed app-wide, not just on the width field — but its failure mode is focus
   *stealing*, which is more disruptive than the focus *loss* being fixed. Step 2.2's regression
   sweep is the control, and it is not optional.
2. **T291's build-blocking preflight will break any plan with a blank `residence_state`.** Intended,
   but if the test corpus trips it, the change gets reverted rather than fixed. Step 7.2's corpus
   check comes before landing, not after.
3. **T291 must not move the frozen golden-master pins.** The fixture household is an Illinois
   resident, so a correct implementation leaves them untouched. Movement means an IL-path behavior
   changed — that is a bug in this ticket, not a legitimate regeneration, and T286's tooling exists
   precisely so nobody regenerates their way past it.

**Sequencing note:** 286 lands before 291 deliberately. 291 is the first ticket that could
legitimately move a pin, and the provenance gate should exist before that, not after.

**Known gap, deliberately left open:** T286 Step 4.1's `verify-endpoint` subcommand needs a detached
git worktree to measure a historical commit without disturbing the working tree. The exact worktree
invocation is not specified here because this repo has a documented worktree/DB interaction
(a worktree still writes the main repo's `local_state` DB) that must be read before the command is
written, not guessed at.
