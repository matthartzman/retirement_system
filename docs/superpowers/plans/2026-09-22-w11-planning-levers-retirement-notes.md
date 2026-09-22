# W11 — Planning Levers retirement: blocked, not landed

> Execution record for **W11** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
> (#329 §3.2 gate). Requires W10b — landed on this branch.

## Scope, as the plan states it

> Scope: retire `planning_levers_echo`; the Plan Features "Active Features"
> view plus W10b's row badges together replace what the sheet showed — what
> the plan is doing, and where each dial position came from.
> Done: confirmed nothing else depends on it as the sole lever-provenance view.

The task brief's own verification instruction: *"grep the whole repo for
every reference to `planning_levers_echo` and the Planning Levers sheet, and
confirm each one is either (a) redundant with Plan Features + W10b's badges,
or (b) something that needs to move first. Do not remove something still
load-bearing — if you find a dependency the plan didn't anticipate, stop and
document it in the notes doc rather than forcing the removal."*

**Outcome: (b). The premise the whole retirement chain rests on does not
match what the code does. Nothing was removed.**

## What every upstream document says the sheet is

Every document that discusses this retirement — `module_catalog.py`'s own
docstring, `documentation/reference/FUNCTIONAL_SPEC.md`, both #329/#330
specs, and this branch's own W0/W1/W5/W9/W10b notes — describes Sheet 27
identically, as a **static restatement of the household's current lever
settings**, with no calculation of its own:

- `src/module_catalog.py:805`: `"Restates the chosen dial positions with
  their source."`
- `documentation/reference/FUNCTIONAL_SPEC.md:55-59`: *"Planning Levers —
  the dials the household actually controls: Roth conversion policy,
  withdrawal sequencing, asset-allocation targets and mode, Social Security
  claiming age, state residency choice, giving strategy, forced
  conversions. Levers are inputs, not results — they are **restated (never
  computed)** on the workbook's Planning Levers page."*
- `docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md:347-350`:
  *"Planning Levers is retired. It is `kind=REFERENCE` and, by its own
  docstring, restates chosen dial positions with their source. ⚠ Before
  deletion, confirm nothing else depends on it as the only provenance view
  for lever sources..."*
- `docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md:630-632` and
  §5.5's proposed replacement: the Plan Features "Active Features" view for
  "what are my current settings" plus #329's row badges for provenance.
- This branch's own `docs/superpowers/plans/2026-09-21-w0-preflight-findings.md:94-98`
  and `2026-09-21-w5-dependency-declarations-notes.md:49-55` — W5 read parts
  of `build_sheet27_planning_levers` closely enough to correctly declare its
  `degrades_without` on `market_luck_stress_test`, but did not question
  whether "restates chosen dial positions" describes the function it was
  reading.

Every one of these repeats or builds on the same claim, traced back to the
`module_catalog.py` docstring. None of them appears to have read the
function body against that claim before this workstream.

## What the code actually does

`build_sheet27_planning_levers()` (`src/reporting/workbook_builder.py:407-506`)
opens with its own docstring, unchanged by this workstream:

> *"Interactive planning levers / sensitivity dashboard. This is a screening
> worksheet, not a replacement for rebuilding the model. Input cells let the
> user test practical levers and formulas estimate directional impact on
> terminal net worth and Monte Carlo success."*

The sheet it builds:

1. **A "Current model anchor" block** (rows 5-10): five read-only figures —
   terminal net worth, Monte Carlo success (or "Not run (module off)"),
   core spending, earned income, remaining plan years — pulled from the
   projection's own output (`rows`, `mc_data`) and generic plan config
   (`c.get('spend_base', ...)`, `c.get('earned', ...)`). This part *is* a
   restatement, but of **projection results**, not of lever settings.
2. **A ten-row lever table** (rows 12+, `specs` at line 454) — hardcoded,
   client-independent entries: "Reduce recurring/core spending," "Work
   longer / retire later," "Cut or delay large discretionary spending,"
   "Preserve annual S-Corp tax advantage," "Roth/tax optimization savings,"
   "Improve return without raising volatility," "Dedicated liquidity
   reserve," "Home-equity backstop," "Dynamic spending guardrail," "LTC /
   catastrophic-care protection." Each row has a yellow **editable** "Test
   Amount" cell (`input_style(ws, ccell)`, defaulted to a fixed literal —
   `10000`, `25000`, `50000`, `250000`, ... — never read from any client
   file) and two Excel formulas that compute an **estimated** directional Δ
   TNW and Δ success from whatever the user types into that cell, plus
   `RANK.EQ` formulas ranking the ten levers against each other.
3. **A "HOW TO USE" block** (row `last+3` onward) instructing the reader:
   *"1. Change a yellow test amount to screen sensitivity. 2. If the lever
   looks material, change the actual Plan Data or Optimizer input in the UI.
   3. Rebuild outputs and compare measured Δ TNW and Δ success in Build
   Impact."*

None of the ten lever rows corresponds to an entry in FUNCTIONAL_SPEC.md's
own list of "the dials the household actually controls" (Roth conversion
policy, withdrawal sequencing, asset-allocation targets/mode, SS claiming
age, state residency, giving strategy, forced conversions). The sheet does
not read `client_policy.csv`, `target_allocation.csv`, or
`asset_class_optimizer_controls.csv` at all — despite the catalog entry's
own `requires_inputs=(_in("planning_levers"),)` declaring a dependency on
exactly those three files (`module_catalog.py:808`). Contrast every real
consumer of the `planning_levers` input category, each of which names the
*specific field* it reads (`_in("planning_levers", "roth_policy", ...)`,
`_in("planning_levers", "hsa_withdrawal_mode")`, `_in("planning_levers",
"targets", "controls")`, `_in("planning_levers", "claiming_age")`, etc.) —
`planning_levers_echo` is the only one that names the category with no
field, and grepping the function body confirms why: it reads none of them.

**Sheet 27 is a what-if scenario screening tool, not a provenance display.**
Its own docstring says so in as many words ("screening worksheet... test
practical levers... estimate directional impact"), and its actual content —
hardcoded generic levers with editable test amounts and estimator formulas —
matches that docstring, not the catalog's.

## Why this blocks the retirement

The plan's entire justification for retiring this sheet is that two other
mechanisms now show the same thing it shows:

- **Plan Features "Active Features" view** — "what is the plan doing" (which
  modules/settings are currently on).
- **W10b's row badges** — "where each dial position came from" (whether a
  currently-displayed value is live optimizer output), for the three
  mode-switch optimizers (Roth Conversion, HSA Drawdown, Asset Allocation).

Both are real, and both do replace a *provenance echo*, if one existed. But
Sheet 27 is not that. It is an interactive "screen a hypothetical change
before touching real plan data" calculator. Neither Plan Features (a
read-only on/off registry) nor W10b's badges (a disclosure that a value is
live-optimizer-derived) let a user type a test spending cut into a cell and
see an estimated directional effect on terminal net worth and probability of
success, ranked against nine other hypothetical levers. **Nothing else in
the system does what this sheet does.** Deleting it on the stated rationale
would remove real, working functionality with no replacement — precisely the
"dependency the plan didn't anticipate" the task brief asked me to stop for.

This also means the workstream's own "Done" condition as written — "confirm
nothing else depends on it as the sole lever-provenance view" — cannot
usefully be evaluated, because the premise (it *is* a lever-provenance view)
does not hold. There is no provenance view here to be sole or redundant.

## What was and was not verified

- **Full repo grep for `planning_levers_echo`** (10 files) and **`Planning
  Levers`** (32 files) — done; results are the file lists above. Beyond the
  code discrepancy this notes doc exists to flag, nothing else changed
  meaning: the dashboard also has an unrelated, same-named **input page**
  ("the Planning Levers page" in `frontend/js/dashboard.js:574,6497` — where
  `client_policy.csv`/`target_allocation.csv`/`asset_class_optimizer_controls.csv`
  are actually edited) that W11 was never scoped to touch and this notes doc
  does not touch either; it is a different thing from the workbook's Sheet 27
  reference module and stays exactly as is.
- **`degrades_without` correctness** (W5) — still accurate as declared: the
  Monte Carlo success row genuinely does show "Not run (module off)" with
  `market_luck_stress_test` off, and the row position is genuinely fixed
  because the lever formulas below it reference `$B$8`/`$B$9`/`$B$10` (the
  anchor block's own cells) by absolute address. No change needed there
  regardless of this finding.
- **No code, catalog, test, or workbook change was made.** This notes doc is
  the only file this workstream adds. `planning_levers_echo`'s catalog
  entry, `SHEET_REGISTRY`'s `'27. Planning Levers'` entry,
  `build_sheet27_planning_levers()`, and every test that references either
  are all untouched.
- **No golden-master regen needed.** Zero Python files changed;
  `tools/regen_golden_master.py measure` would be `+0.00` on both pins by
  construction, so it was not run (nothing to compare against).
- **No `pytest`/`npm test` run for this workstream specifically.** The diff
  is one new markdown file with no code, catalog, or test changes, so there
  is nothing for either suite to regress. (PR #132's most recent landed
  workstream, W10c, already has both green on this branch head.)

## What should happen next

This is a product decision, not an engineering one, and it's outside a
"sonnet · low · light" workstream's scope to make unilaterally:

1. **If the sensitivity-screening tool is meant to stay** (the likely
   answer, given it is real, used functionality with no replacement) — the
   catalog entry's `kind=REFERENCE` and its docstring are both wrong and
   should be corrected in a small follow-up (recatalog as e.g.
   `DIAGNOSTICS`/`OPTIMIZATION`-adjacent "worksheet," matching the
   `tax_capacity` precedent the specs already use for "derives nothing new... a
   consolidated view" sheets that are real but not provenance echoes), so
   the next person who reads the catalog isn't misled the way every
   document in this chain was.
2. **If someone still wants a literal lever-provenance echo** — that is a
   *new* sheet to design and build, not a rename of this one; Sheet 27's
   current content would need to move somewhere (or be kept alongside it)
   rather than be overwritten, since deleting it would still delete the
   screening tool.
3. Either way, **#329 §3.2's retirement gate, and this master plan's W11
   entry, should be marked resolved-as-"do not retire"** rather than
   reattempted by a future session working from the same stale docstring —
   that is what this notes doc and the PR body's W11 section are for.

## Consequences for later workstreams

- **W12** (off-state rendering) and **W13** (left-nav realignment) do not
  depend on this outcome — neither names `planning_levers_echo` in its own
  scope line, and Sheet 27 has no `dashboard_step` to realign.
- Nothing downstream was blocked by leaving this sheet in place: it was
  never on the critical path for W12/W13, only for closing out #329 §3.2's
  own open item.
