# W4 — Plan Features page: what was built, and the judgment calls

> Execution record for **W4** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4,
> implementing #330 P3 + Q7 (`docs/superpowers/specs/2026-09-19-modular-feature-nav-design.md`
> §5.1, §5.4, and Q7). Runs after W5, which had to land first to avoid a
> same-file collision in `renderOptionalFunctions()`.

## What landed

Every item in the plan's scope line:

- **Regrouped by `domain`**, in the catalog's own `DOMAINS` order, with
  collapsible groups and an "N of M on" count per group.
- **Kind filter chips derived from `CATALOG.kind`** — only kinds actually
  present among the toggle rows get a chip.
- **Per-row**: name, kind badge, plain-language demand hint, description,
  auto-enable badge (already existed), off-impact line (delivered by W5 — see
  below), and the "Off · N items entered" indicator.
- **Renamed "Plan Features"**, across the step title, the page help, and the
  four cross-references elsewhere in the app that linked to "Optional Modules".
- **#330 Q7's read-only env-override disclosure**, both as a page banner and a
  per-row badge, with the switch replaced by a static state marker on a forced
  module.

## The constraint that shaped the whole workstream

`dashboard.js` was at **7,292 lines against a 7,293-line ratchet** that may
only ever move down (`tests/test_frontend_size_ratchet.py`). W5 had spent five
of its six remaining lines. W4 adds a page, so there was no version of this
workstream that edited `renderOptionalFunctions()` in place.

So the page was **extracted** to `frontend/js/dashboard_decomp_plan_features.js`
first, as its own step, and `DASHBOARD_JS_MAX_LINES` **lowered** 7,293 → 7,246
in the same commit. This is the ratchet's own prescribed path, not a
workaround: its docstring says "a change that adds lines to dashboard.js must
take lines out of it somewhere else, or move the new code into its own module
-- which is the point." `dashboard_decomp_workbook_formatting.js`, the other
extracted Settings page, is the precedent the new module follows down to its
position in `index.html`.

Extraction had one mechanical consequence worth recording: `renderOptionalFunctions`
is in dashboard.js's **generated** window bridge, so removing it meant
re-running `tools/js_codemod/census.mjs` and then
`tools/js_codemod/convert_dashboard.mjs` (no `--check`) rather than hand-editing
the bridge — the census is the codemod's input, so refreshing it first is
load-bearing and doing them in the other order silently regenerates the old
list. `--check` passes after.

## Judgment call 1 — the "N items entered" indicator only appears where the data location is declared

§5.4 asks a module that is off but holds data to say so — *"Off · 4 policies
entered."* Only some modules can answer that. `csv_sections` and
`dashboard_step` are populated, per W1's own notes, "only for modules that
actually gate dashboard input visibility today — most Optimization/Stress/
Diagnostics modules gate a workbook *sheet*, not an input page, and have
neither."

Three options, and the reason for the one chosen:

1. **Show the count only where `csv_sections`/`dashboard_step` declares a
   location; show nothing elsewhere.** ← chosen.
2. Add a new catalog field naming each optional module's data location. This is
   really `gate_ref`, which **W6** introduces for the plan-flag unification;
   inventing a parallel field in W4 would give W6 a twin to reconcile.
3. Infer from `requires_inputs`. It names input *modules* and elements
   (`("insurance_estate", ("grants",))`), not CSV rows, so any mapping to rows
   would be a guess — and a wrong count on a data-retention guarantee is worse
   than no count.

The indicator is therefore honest but partial, and the gap closes on its own
when W6 lands `gate_ref`. Recorded here so the partial coverage reads as a
decision rather than an oversight.

A related detail inside the counter: **an off toggle is not entered data.** A
module's own switch row lives in the section it gates, so counting every
non-blank row would have every module reporting "Off · 1 item entered" — the
indicator would be noise on every row it appeared on. `enteredRowCount()`
therefore skips `NO`/`FALSE`/`0`.

## Judgment call 2 — the off-impact line was already built, by W5

§5.1 lists "an off-impact line derived from reverse `degrades_without`" as a
W4 row element. W5 already built exactly that (`moduleOffImpactWarning()`),
because the same field's reverse direction is what its own scope called for.
W4 reuses it rather than building a second renderer of the same relation.

One thing W4 did change: W5 kept `moduleTaxonomy` module-private in
`dashboard_decomp_row_model.js`, on the stated grounds that
`moduleOffImpactWarning()` was its only reader. The Plan Features page is the
second reader — it groups by `domain` and filters by `kind`, both in that same
payload — so row_model gained a `planModuleTaxonomy()` getter. A getter, not a
window accessor on the binding, so row_model stays the only writer.

## Judgment call 3 — a forced module renders its state, not a switch

Q7 says disclose. It does not say what the toggle should do meanwhile, and the
obvious reading — leave the switch live, add a note — is wrong: writing the
toggle would save a value the build then ignores, which is precisely the
"switch page disagrees with what the build did" disagreement Q7 exists to end.
So a forced row renders a static `ON`/`OFF` marker with `aria-disabled`, plus a
badge naming the variable.

The disclosure names the **variable**, not just the fact. "Forced on" is not
actionable; "Forced on by `RETIREMENT_SYSTEM_FORCE_ALL_MODULES`" tells the
reader where to go and turn it off.

`force_override()` mirrors `_base_enabled`'s precedence step for step, and a
test pins the two against each other across every optional module rather than
asserting each separately — a disclosure that named a different winner than the
gate actually used would be worse than showing nothing.

## Judgment call 4 — an uncatalogued toggle renders under "Other" rather than disappearing

Grouping by `domain` raises the question of what to do with a
`client_optional_functions.csv` row whose module has no `CATALOG` entry. The
page puts it in an "Other" group, sorted last.

Hiding it would have been easy and wrong: a switch that exists in the CSV but
not the catalog is exactly the registry drift this page should surface. W1
found three such modules (`hsa_drawdown`, `tax_capacity`,
`current_vs_proposed`) and a missing toggle row for a fourth; the page should
make the next one visible, not swallow it. `test_module_catalog.py`'s
`test_every_optional_module_has_a_toggle_row` is the enforcement half; this is
the disclosure half.

## Judgment call 5 — the page's decision logic is pure functions

Everything that decides *what* the page says — `planFeatureGroups`,
`planFeatureKinds`, `envOverrideNotice`, `enteredRowCount`, `demandHint` —
takes its data as a parameter. Only `renderOptionalFunctions()` reads shared
mutable state.

This is not stylistic. A module-scoped `let` is a lexical binding that the
frontend tests' `vm` sandbox cannot reach from outside (W5 hit this and solved
it the same way), so a helper that closes over page state is a helper that
cannot be tested. Fifteen cases in `tests/frontend/plan_features.test.mjs`
exist because the logic was written to be reachable.

Two things the sandbox does force on the tests, both already conventions here:
cross-realm arrays need `Array.from` before `assert.deepEqual` (the reason is
documented at length in `strategy_screen_rows_aggregate.test.mjs`, and the same
note is repeated in the new file), and the render shell itself is not unit
tested — it assembles strings these functions return.

## A correctness detail: two escaping layers, in order

Domain names go into an `onclick` attribute, and two of them carry `&` —
`Estate & Legacy`, `Family & Business`. `escJs` alone (the convention
`renderStrategyTabs` uses, whose own tab names happen to have no `&`) escapes
the JS-literal layer but not the HTML-attribute layer. The page uses
`esc(escJs(x))`: `escJs` makes a safe JS string literal, `esc` makes that safe
as an attribute value, and the HTML parser undoes `esc` first, handing JS
exactly the literal `escJs` built.

## Deliberately NOT in this workstream

- **§5.3's `gate_kind` / `gate_ref` plan-flag unification** (HELOC, Hybrid LTC,
  DAF, QCD) is **W6**, not W4, and nothing here anticipates its shape.
- **§5.2's three off-states** (Hidden / Collapsed-with-a-note / Disabled in
  place) and the no-hidden-data invariant are **W12**.
- **§5.5's Active Features view** is part of #329's Planning Levers retirement
  gate (**W11**).
- **W13** may not share a session with W4 per the plan's §7.6 guard; nothing in
  this commit reaches toward it.

## Verification

- `pytest tests/ -m "not slow and not nightly" -n auto --dist loadfile` — CI's
  own invocation.
- `npm test` — 478 frontend tests, of which 15 are the new
  `plan_features.test.mjs`. The two failures in
  `js_codemod_parser_offsets.test.mjs` are the known pre-existing
  jscodeshift-version issue recorded in W5's notes; they do not reproduce on
  CI's `frontend-tests` job.
- `node tools/js_codemod/convert_dashboard.mjs --check` — dashboard.js matches
  the regenerated bridge.
- No Python behavior changed beyond `module_status()` gaining two keys: the
  page is frontend, and the catalog change is additive and read-only.
