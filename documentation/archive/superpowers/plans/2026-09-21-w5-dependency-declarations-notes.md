# W5 — Dependency declarations: what was built, and the judgment calls

> Execution record for **W5** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4,
> implementing #330 P4 (`docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
> §3.4, "Dependency chains: what exists, what is missing").

## What landed

Three commits, each green on `pytest -m "not slow"` before the next started.

1. **`degrades_without` and `engine_participation` on `OutputModule`**, with
   three new `validate()` guards, `soft_dependents()` / `engine_participants()`
   accessors, and both directions of the relation served on the config
   payload's `module_taxonomy`.
2. **The reverse-direction warning on the switch** —
   `moduleOffImpactWarning()` in `dashboard_decomp_row_model.js`, rendered by
   `renderOptionalFunctions()`.
3. **The call-site enforcement test** —
   `tests/test_module_toggle_call_site_enforcement.py`, ten sites swept and
   classified.

**V1's `build_impact` wiring was correctly dropped.** W0 already established
that a toggle change raises the staleness notice today through the generic
plan-data dirty-tracking path (`dirty`/`lastBuildOk` unsaved,
`build_preflight_payload()`'s DB-vs-artifact mtime comparison saved). Not
re-investigated; not re-wired.

## The sweep: ten sites, four verdicts

The plan asked for "~10 sites today", and that is what the sweep found. They do
not all mean the same thing, which is the whole reason the workstream exists:

| Site | Toggle | Verdict |
|---|---|---|
| `module_catalog._base_enabled` | *(the mapping)* | accessor |
| `module_catalog.module_status` | *(every optional key)* | accessor |
| `workbook_builder.main` | `market_luck_stress_test` | own gate (`run_mc`) |
| `workbook_builder.main` | *(loop over `OPTIONAL_MODULE_SHEETS`)* | own gate |
| `sheets_summary_builder.build_sheet1` | `market_luck_stress_test` | soft → `executive_summary` |
| `sheets_summary_builder.build_sheet1` | `social_security_timing` | soft → `executive_summary` |
| `sheets_projection_charts.build_sheet8` | `market_luck_stress_test` | soft → `charts_dashboard` |
| `workbook_builder.build_sheet27_planning_levers` | `market_luck_stress_test` | soft → `planning_levers_echo` |
| `spending_tracker._insurance_policy_premium_sum` | `existing_life_insurance` | soft → `cash_flow` |
| `deterministic_engine.run_deterministic_projection_stage` | `equity_compensation`, `disability_income_insurance` | engine |
| `after_tax.business_taxable_estate_value` | `business_succession` | engine |

The spec named four relationships it expected to find (§3.4 items 1–4). All
four are here, plus one the spec did not name: **`planning_levers_echo` is a
third consumer of the Monte Carlo toggle**, alongside Exec Summary and Charts.
Its "Current model anchor" block keeps the Monte Carlo success *row* — the
lever formulas below it reference fixed anchor cells B6/B8/B9/B10, so the row
must not shift — and writes `"Not run (module off)"` into it instead of a
figure. That is soft degradation by any reading, and it means the spec's own
example sentence is one clause short of what the code actually does.

## Judgment call 1 — a soft dependency carries the phrase, not just the key

The spec writes the field as `degrades_without: Tuple[str, ...]`. It is
implemented as a tuple of `(module_key, what_is_lost)` pairs, built by a
`_soft()` helper mirroring the file's existing `_in()` convention.

The reason is the spec's own worked example. It calls the reverse warning
*"the single highest-value thing this field buys"* and writes it out in full:

> Turning Monte Carlo off also removes the success-probability headline from
> Executive Summary and the fan chart from Charts.

That sentence is not renderable from a tuple of keys. From keys alone the best
available is *"Turning Monte Carlo off also affects Executive Summary and
Charts"* — which names the blast radius but not the loss, and so does not
answer the question the spec says the user is asking. The alternative, a
parallel `Dict[str, str]` of phrases beside the tuple, is two tables to keep in
sync: precisely the hand-maintained twin #329 exists to end. Putting the phrase
inside the declaration makes drift impossible, and `validate()` rejects a blank
one, so the field cannot be half-populated.

Cost: one non-literal reading of the spec's type signature, and every consumer
unpacks a pair. W4 (the Plan Features page, whose §5.1 off-impact line reads
the same reverse map) gets the richer data for free.

## Judgment call 2 — `business_succession` is engine participation, not soft degradation

The first pass declared `estate_legacy_plan.degrades_without =
("business_succession",)`, reasoning that with Business Succession off,
`after_tax.business_taxable_estate_value()` returns `0.0` and the Estate &
Legacy sheet's estate-tax base silently omits an illiquid business interest the
household actually holds.

**That was wrong, and the enforcement test's reverse assertion caught it** —
`test_every_soft_declaration_is_backed_by_a_swept_call_site` reported the
declaration as "declared but never read", because the only call site is in
`after_tax.py`, which is the tax layer, not `estate_legacy_plan`'s builder.

Chasing it down settled the substantive question too. `degrades_without` means
output that is *removed* — "this module shows less because X is off". With
Business Succession off, every section of the Estate sheet still renders; one
number inside it is smaller. A figure changing is engine participation, which
`business_succession` now declares, and which is the accurate statement.
Conflating the two would have made the off-impact warning cry wolf about a
change the user cannot see, and would have been wrong three times over: the
same figure flows into `life_insurance_need` (sheet 19's estate-liquidity need)
and `executive_summary` (the CST and QTIP materiality blocks) as well, so the
"declare it on the consumer" reading would have put the same soft dependency on
three modules to describe one arithmetic change.

Recorded rather than quietly fixed, because the near-miss is the argument for
the reverse assertions existing at all.

By the same line, `cash_flow.degrades_without = ("existing_life_insurance",)`
**was** kept: the spec names it directly (§3.4 item 3, the cross-package case),
and the mechanism is a real substitution — an Auto policy's actual premium
supersedes the typed `auto_insurance` budget line, or does not.

## Judgment call 3 — the enforcement sweep parses, it does not grep

The plan says to "grep `src/` for `module_enabled(` and raw `c['opt']` reads".
The test greps for exactly those two things, but over an AST rather than over
lines, for two reasons:

1. **A line grep finds text that is not code.** `module_enabled` appears inside
   the comment explaining it; `c['opt']` appears inside four docstrings. Six
   phantom sites in `module_catalog.py` alone, all of them prose — and W5's own
   commit added another, since the new field's comment names the bypass it
   describes.
2. **The parse tree yields the enclosing function name**, which is what lets a
   site be keyed by `(file, function, toggle)`. Line numbers churn on every
   edit above them; function names do not. `workbook_builder.py` reads the
   Monte Carlo toggle twice with two different verdicts, so file-plus-key is
   not enough to tell them apart and function name is exactly enough.

Two smaller calls inside that:

- **`.get('opt')` counts as a raw `c['opt']` read.** The spec says
  `deterministic_engine.py` "reads `c['opt']` directly"; in the source that is
  spelled `c.get('opt')`. Matching only the subscript form would have missed
  the single site §3.4 item 4 is entirely about.
- **Writes are excluded by context, not by exemption.** `data_io.py`'s
  `c['opt'] = {...}` is the loader that populates the toggles. It drops out
  because the sweep only accepts `ast.Load` subscripts, so if it ever starts
  *reading* one it reappears on its own — an exemption list would have hidden
  that.

## Judgment call 4 — the sweep runs per test, the judgement does not

The plan's scoping note asks for the findings to be written "into the test as a
fixture list so the sweep happens once rather than once per run".

`DECLARED_SITES` **is** that fixture: which module consumes each site and under
which verdict was decided once, by hand, and is recorded there with a sentence
of reasoning per site. Nothing re-derives it.

What does run per test is the mechanical half — `ast.parse` over ~90 files,
well under a second — and it is what makes the fixture enforcing rather than
decorative. A frozen list cannot notice the eleventh call site, and noticing
the eleventh call site is the entire point of the exercise; the spec's own
justification is that "without it the new field drifts exactly like
`section`/`letter_prefix` did". Reading the note as "do not re-grep at runtime"
would have produced a test that passes forever regardless of what `src/` does.

## Judgment call 5 — the warning helper is not in `dashboard.js`

`dashboard.js` was 7,287 lines against a 7,293-line ratchet: six lines of
headroom, and the ratchet may only move down. `moduleOffImpactWarning()` is
therefore in `dashboard_decomp_row_model.js` (the shared-core hub that already
owns `moduleGates`/`moduleStatus` payload wiring), and `dashboard.js` spends
five of its six lines on the call and the markup. It now has one.

Consequences worth knowing:

- The taxonomy payload is **module-private** in `row_model.js`.
  `moduleOffImpactWarning()` is its only reader, so unlike `moduleStatus` and
  `moduleGates` it needs no `window` accessor — and `dashboard.js` gains no new
  top-level binding, so the codemod census and its bridge block are untouched.
- The helper takes the taxonomy as a **defaulted parameter** rather than
  closing over module state. A module-scoped `let` is a lexical binding that
  the frontend tests' `vm` sandbox cannot reach from outside, so the closed-over
  version was untestable through `load_dashboard.mjs`; the parameter makes it a
  pure function, which is what that loader is documented to target.
- The line is rendered **only while the module is on**. Off, it would restate a
  fact the user can already see rather than warn about a consequence.
- `TOTAL_JS_MAX_LINES` raised 33,311 → 33,348, the measured size with no slack,
  per that ceiling's own contract for genuine new code (33,311 was already set
  that way). `DASHBOARD_JS_MAX_LINES` untouched.

## Verification

- `pytest -m "not slow and not nightly" -n auto --dist loadfile` — the CI
  invocation, green.
- `npm test` — 458 frontend tests. The five new
  `module_off_impact_warning.test.mjs` cases pass. **Two pre-existing failures
  in `js_codemod_parser_offsets.test.mjs`** (jscodeshift offset behaviour on
  CRLF/LF sources) are environmental, not W5's: confirmed by `git stash`-ing
  the whole branch delta and re-running, which fails identically. That test
  pins third-party parser behaviour and nothing in this workstream touches
  `tools/js_codemod/` or `package.json`.
- **One pre-existing red found and fixed in passing.**
  `test_dashboard_js_module_bridge_regression.py`'s three codemod-`--check`
  tests fail whenever the census test has already run in the same session,
  because that test regenerates `tools/js_codemod/census_report.json` and the
  committed copy was stale: it was missing `BUILD_HISTORY_SCHEMA_VERSION` and
  the `dashboard_decomp_build_lifecycle.js` references, from commits that
  predate this workstream. Confirmed not W5's by `git stash`-ing the entire
  branch delta and reproducing it identically on a clean tree. Regenerated in
  its own commit, since a purely mechanical refresh of a generated artifact is
  a smaller thing to carry than a branch that goes red on CI's own
  `-n auto --dist loadfile` invocation. No W5 code is involved: W5 adds no
  top-level binding to `dashboard.js`, so the census's `dashboard.js` half is
  byte-identical either way.
- Targeted: `tests/test_module_catalog.py`,
  `tests/test_module_toggle_call_site_enforcement.py`,
  `tests/test_config_service_extraction_functional.py`,
  `tests/test_frontend_size_ratchet.py`.

No workbook output changes: W5 adds declarations, a UI line and a test. No
builder reads the new fields, and no gate decision moved.

## Consequences for later workstreams

- **W7 (engine gate fix)** replaces `deterministic_engine.py`'s raw `c['opt']`
  read with `module_enabled()` and regenerates the golden masters.
  `engine_participation` survives that unchanged — it declares *which* modules
  move the projection, and W7 changes only *how* the engine asks.
  `test_engine_participants_are_the_modules_the_engine_reads` is written to
  survive it; `DECLARED_SITES`' entry for that site will need its verdict kept
  at `engine` but its key re-read as a `module_enabled(` literal rather than a
  raw `opt` mapping, which will move it from the `keys_read` fixture column into
  the sweep's own output. That is a two-line fixture edit, and the test's
  failure message says so.
- **W4 (Plan Features page)** reads the same `module_taxonomy` payload. Its
  §5.1 off-impact line is the *forward* direction of what W5 rendered in
  reverse, and `degrades_without` already carries the phrase it needs. W4 also
  touches `renderOptionalFunctions()`; this workstream landed first by
  arrangement, so W4 rebases onto a version of that function that already has
  the off-impact line in it.
- **`degrades_without` is not transitive and must not become so.** Soft
  degradation does not compose: Exec Summary saying less does not make whatever
  reads Exec Summary say less. `soft_dependents()` is deliberately a single-hop
  lookup, unlike `prerequisite_outputs()`.
