# Housing Location Search — catalog entry + off-semantics: what was built, and the judgment calls

> Follow-up item flagged since W8b and reconfirmed by W9, described by both as
> "W1-shaped" work: genuinely new catalog territory, not a numbered master-plan
> workstream. Closes the gap named in
> `docs/superpowers/plans/2026-09-22-w8b-newly-optional-medium-risk-notes.md`
> ("Housing Location Search") and
> `docs/superpowers/plans/2026-09-22-w9-ui-section-registry-notes.md` (which
> confirmed it was out of W9's own scope).

## The gap, restated

`src/housing/` — the ZIP/city location search behind `/api/housing/optimize`
and `/api/housing/zip-screen`, "Where to live" in #329 §1.4's naming — had **no
`OutputModule` in `CATALOG` at all**. The only housing entry was
`housing_trajectory_comparison` ("When to move", Sheet 38, a different engine
entirely: it sweeps `next_housing_steps` timing, not location). #330 §3.2 lists
"Housing 'Where to live'" among the twelve newly-optional candidates with the
off-semantics *"The UI panel is hidden; `src/housing/` is not invoked"* — a
sentence describing behavior that could not exist, because there was no switch
to implement it with.

W8b found this while verifying `housing_trajectory_comparison`'s own off state
and explicitly declined to fold the fix into that pass: "Making that one
optional is not a toggle row; it is a W1-shaped catalog addition ... plus
UI-panel gating, and panel/nav gating is W9's and W12's subject, not W8b's."
W9's own triage line: "a new catalog entry plus UI-panel gating ... not W8b's."
Neither W12 (off-state rendering) nor W13 (left-nav realignment), which landed
on this branch since, touched it either — both were scoped to modules that
already had catalog records.

## Reading `src/housing/` first

Per the task brief's own instruction, and #330's own history of docstrings
being wrong about behavior (W11's Sheet 27 finding), the code was read before
any catalog field was chosen:

- **What it does.** `src/housing/__init__.py`'s package docstring: a
  two-stage search. `zip_screen/` narrows every ZCTA within a chosen radius of
  1–5 user-given anchor ZIPs down to a scored shortlist (`screen.py`,
  `quality.py`'s Neighborhood Stability Score); `optimizer.py` then generates
  candidates from that shortlist (`candidates.py`/`search.py`), runs each
  through the real deterministic engine and Monte Carlo
  (`plan_variant._run_engine` → `planning_engines.run_scenario`/
  `monte_carlo`), filters (`constraints.py`: no-dual-ownership,
  family-presence), scores (`scoring.py`: `net_worth` / `lifetime_cost` /
  `mc_success_rate`), and ranks (`results.py`).
- **What it is not.** `api.py`'s `validate_request` explicitly *rejects* a
  manual candidate list ("Manual candidate locations are no longer
  supported"). The user supplies a search region (anchors + radius per move)
  and windows, not a set of named alternatives to be scored. This is the fact
  that decided `kind` below.
- **Where its inputs live.** Entirely in browser-local storage
  (`HOUSING_OPT_STORAGE_KEY` in `dashboard_decomp_housing_optimizer.js`) —
  anchor ZIPs, radii, quality floor, budget bounds, per-move acquisition
  windows, objective, search mode. Nothing in any plan CSV. This decided
  `sheet=None` below.
- **How it touches the engine.** `plan_variant._run_engine` calls
  `planning_engines.run_scenario`, which deep-copies the base config before
  `_apply_candidate` mutates the copy. The saved plan's own projection never
  changes from running (or not running) this search. This decided
  `engine_participation=False`.
- **Whether it reads Monte Carlo's own gate.** `optimizer.py`'s
  `mc_success_rate` objective calls `_pe.monte_carlo(...)` directly; nowhere
  in `src/housing/` does `market_luck_stress_test` or `module_enabled(...,
  'market_luck_stress_test')` appear. This decided "no `degrades_without`",
  confirmed as a test rather than assumed (W5's rule: an unobservable
  declaration is worse than none).
- **What the endpoints do today.** `src/server/plan_routes.py`'s
  `housing_optimize`/`housing_zip_screen` load the active plan config and call
  straight into `src/housing/` with no gate at all — confirming #330's
  off-semantics described a real, current absence, not a hypothetical.
- **The frontend panel.** `renderHousingOptimizePanelHtml()` renders
  unconditionally inside `renderStrategyOptimize()`'s "Next Housing Move"
  section (`gate: null`), a self-contained wizard (H2, PR #133) that persists
  its own form state to `localStorage` and never touches plan rows except
  through the separate "apply to plan" patch strip.

## Judgment call 1 — `kind`: OPTIMIZATION, not COMPARISON

Both housing engines answer #329 §1.4's honest split — a *location* search and
a *schedule* search. The live alternative to OPTIMIZATION was COMPARISON,
since the sibling `housing_trajectory_comparison` carries "Comparison" in its
display name and W1's own §3.1 vocabulary distinguishes COMPARISON ("of the
alternatives I named, which scores better?") from OPTIMIZATION ("what
controllable lever should I change, and by how much?").

The code settles it: a COMPARISON scores alternatives the *user supplies*.
`api.validate_request` rejects a manual candidate list outright — the v2
request carries a search region, not named alternatives, and candidates are
*generated* (`candidates.generate_candidates`/`search.generate_move1_
candidates_narrowed`) then filtered/scored/ranked. That is OPTIMIZATION's
question verbatim: where and when to move are levers the household controls.
The sibling module is OPTIMIZATION for the identical reason despite its
display name — checked directly rather than assumed, since the two entries
needed to agree or the domain-sharing judgment below would rest on a
mismatched kind.

## Judgment call 2 — `domain`: Housing & Property, matching the sibling

`housing_trajectory_comparison.domain == HOUSING_PROPERTY`. #330 §4.1's axes
are independent (kind and domain never derive from each other), and the two
housing engines share nothing on the `kind` axis with each other's neighbors —
they *do* share the part of life they concern. Confirmed by reading the field,
not assumed from the name: `HOUSING_PROPERTY` is exactly the domain #330 §4.2
would assign to a location search on its own terms (a housing decision), so
there was no tension to resolve here, unlike W1's Tax Capacity case.

## Judgment call 3 — `sheet=None`, and why it stays that way

The task brief asked whether this should follow Divorce/QDRO's *pre-W9*
`sheet=None` shape (a temporary gap later closed) or is genuinely sheet-less.
Reading `src/housing/` answers this directly: there is no plan-CSV surface for
the search's inputs to be built from. A workbook sheet is built from the saved
plan; every field this search reads (anchors, radii, windows, objective) is
form state in `localStorage`, never persisted to a CSV row. Building a sheet
would first require *inventing* a plan-input surface for those parameters —
a real feature, not a catalog record — and nothing in #330's task language or
#329's engine-naming asked for that. `spending_tracker_ytd` is the existing
precedent for a `sheet=None` module that is not a placeholder: it owns no
sheet of its own either, for a structurally similar reason (its output lives
in other modules' sheets). Documented in the catalog entry itself so a future
reader does not treat this as an oversight the way Divorce/QDRO's was.

## Judgment call 4 — the gate mechanism: `optional=True` + toggle row, not `gate_kind`

The task brief flagged this as open: `optional=True` with a toggle row, or a
`gate_kind`-based mechanism given the module is "UI-only"? `gate_kind` has
exactly two members (`GATE_MODULE_TOGGLE`, `GATE_PLAN_FLAG`), and
`GATE_PLAN_FLAG` is for a feature switched by an *ordinary plan row that other
rows nest under* (HELOC, Hybrid LTC, DAF/QCD) — the switch lives where its
data is. This search has no plan data to nest a switch under; its parameters
are browser-local. `GATE_MODULE_TOGGLE` (a `client_optional_functions.csv`
row) is the mechanism for a feature switched independently of any plan field,
which is exactly this shape — the same reasoning that gives
`spending_tracker_ytd` (also parameter-heavy, also no natural plan-row home
for its switch) a toggle rather than a flag. So: `optional=True`, a normal
`client_optional_functions.csv` row, default `TRUE` (behavior-neutral, per
W1's contract — the module was unconditionally on before this commit, and
stays on by default after it).

## Judgment call 5 — the off-state: Collapsed-with-a-note, and where the gate attaches

#330 §3.2's off-semantics: *"The UI panel is hidden; `src/housing/` is not
invoked."* Two readings were available for the UI half: **Hidden** (the
section vanishes from the list entirely, like Divorce/QDRO when its module is
off) or **Collapsed-with-a-note** (W12/§5.2's generalized `featureGatedNote()`
state — the section stays in place, collapsed, with an inline "Turn on"
switch).

Chose Collapsed-with-a-note. Divorce/QDRO's Hidden treatment
(`renderStrategyStress()` filters the section out of the array entirely) is
explicitly reserved in that file's own comment for a section that "should not
appear at all — not even as a collapsed 'enable it here' stub" — a stress test
whose presence would misleadingly suggest the household is protected. Housing
Location Search is the opposite case: a household that came to the Optimize
screen looking for a location search needs to be told *where the switch is*,
not shown nothing where that section used to be. This also matches every
other Optimize-screen section with a `gate` (Roth Conversion before W13,
Charitable Giving, Harvesting's siblings) — none of them are Hidden, and there
is no stated reason this one should be the exception. Implemented by giving
the "Next Housing Move" section's `gate:` field the new module key instead of
`null`; `strategySection()`/`featureGatedNote()` (both pre-existing, W12) need
no change — they already resolve any `module_toggle` key generically through
`planModuleTaxonomy()`/`moduleGates.step_gates`.

`dashboard_step="housing_location_search"` is a Strategy-screen *section*
id, not a `STEPS` nav-step id — the panel owns no input page of its own to
hide. Every existing `dashboard_step` value before this change was also a
real `STEPS` entry (`roth_conversion`, `divorce_options`, …), so the field's
doc comment in `module_catalog.py` was widened to say "gated UI surface"
rather than "nav step", with the reasoning for why one map still serves both
readers (`visibleSteps()` filters the `STEPS` array; an id absent from it is
simply inert there).

## Judgment call 6 — the endpoint gate: shared helper, not per-route duplication

#330 §3.2's other half — "`src/housing/` is not invoked" — has to be enforced
server-side, because a hidden panel does not stop a direct POST. Both
`/api/housing/optimize` and `/api/housing/zip-screen` needed the same check,
so it is one helper (`_housing_search_config_or_disabled`) called at the top
of each route, checked before the `from ..housing import ...` line (verified
by `test_the_gate_precedes_the_import_of_the_search` — an import after the
check would still load and run the package on a disabled module).

**Deliberately not applied** to `/api/housing/zip-lookup`, `/api/housing/
top-cities`, `/api/housing/state-estimate`, or `/api/housing/seed`. The first
two are reference/estimate helpers the *always-on* "Home & Housing" input
page calls directly (`dashboard_decomp_housing_scenarios.js`); gating them
would take ordinary plan-input functionality away from a page this switch
does not own — the shape the no-hidden-data invariant exists to forbid, from
the endpoint side rather than the row side. `state-estimate`/`seed` are
likewise Home & Housing input helpers, unrelated to the search. #330 §3.2
names the two search endpoints specifically, and those are the two gated.

## The no-hidden-data invariant, checked rather than assumed

The global constraint (W12's invariant, `featureGatedNote()`) requires that no
switch may hide a row holding user-entered data. This module needed no
`featureGatedNote()` retained-row count wiring for that reason: it owns **no
plan rows at all**. Its inputs are browser-local form state (survives a toggle
flip untouched — `localStorage` is not plan data and this switch never
touches it), and the household's actual housing plan (current home, sale
year, next housing steps, rent) lives on the always-on "Home & Housing" page
(`assets_home_cash` / the Housing budget section), which this module's gate
does not — and must not — reach. Confirmed directly:
`test_the_home_and_housing_input_page_is_not_gated_by_this_switch` (Python)
and the "no-hidden-data: the switch owns no plan rows to hide" suite
(frontend) assert neither `assets_home_cash` nor the housing input page is in
`step_gate_map()`/`section_gate_map()`, and that `featureGatedNote()` reports
zero retained rows for this key (there are none to retain).

## Verification

- `validate()`'s import-time assertions: pass (module import succeeds, which
  runs `validate()` at the bottom of `module_catalog.py`).
- `tests/test_module_catalog.py`,
  `tests/test_module_catalog_prereq_gating.py`,
  `tests/test_optional_module_gating.py`,
  `tests/test_strategy_workspace_module_gating.py`,
  `tests/test_module_toggle_call_site_enforcement.py` (extended with the new
  server-side toggle-read site, `OWN_GATE` verdict) — all green, confirming no
  new contradiction against the five categories W1 found latent in this file.
- New `tests/test_housing_location_search_catalog.py` (20 tests): the catalog
  record's shape, both engines sharing a domain while differing in kind
  correctly, `sheet=None`'s consequences (absent from
  `OPTIONAL_MODULE_SHEETS`), `engine_participation=False` and no
  `degrades_without` (both checked against the actual source, not just the
  declaration), the toggle row's presence and default, both off-semantics
  halves (UI section gate, both endpoints' gate-before-import), and the
  ungated reference endpoints.
- New `tests/frontend/housing_location_search_gating.test.mjs` (7 tests):
  `stepGatedByOptionalModule()` resolving the new key, the
  Collapsed-with-a-note off-state (panel body not built while off, built
  normally while on), the inline "Turn on" switch, and the no-hidden-data
  invariant on the Home & Housing page.
- `tests/test_frontend_size_ratchet.py`: `TOTAL_JS_MAX_LINES` raised
  35,621 → 35,624 (three explanatory comment lines beside the now-gated
  section; the gate assignment itself is net zero). No `dashboard.js` growth.
- Full `pytest -m "not slow"`, full `npm test`, and
  `tools/regen_golden_master.py measure` — see PR #132's body for the final
  run's pass counts; the golden master shows zero delta because the module
  defaults to its pre-existing always-on behavior and the frozen sample plan
  has no housing_location_search-dependent fixture data.

## What this does not do

No calculation change to the search's engine calls — `plan_variant.py`,
`optimizer.py`, `scoring.py` are untouched. No change to `housing_trajectory_
comparison` or Sheet 38. No new plan-input page or CSV field for the search's
own parameters (they remain browser-local, per the `sheet=None` judgment
above) — that would be a feature addition beyond what #330 §3.2 and W8b/W9
asked for.
