# Phase 6 — Expanded Stress Scenarios — Spec

Last item named in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s "Not
done" list. Phase 3 (tax NPV/ELTR) and Phase 5 (adaptive guardrails) are
now implemented; Phase 4 (LCV feasibility gate) has a spec but no
implementation. This is the final phase in the sequence.

**Spec/research only — no code in this document.** Mechanical grounding
delegated to an Explore subagent; the design analysis below is original.

## The scoping problem this spec exists to solve

As with Phases 3-5, the "Final Optimization Implementation Plan —
Revised" this refactor tracks against does not exist in this repository.
All that survives is the phase name: *"expanded stress scenarios."*
Unlike Phase 3 (which had `gross_cash_flow_yr` sitting inert, explicitly
built "for" it) or Phase 5 (which had no anchor at all, resolved purely
by product sign-off), Phase 6 sits in between: there is a real, working
stress-scenario system already in the codebase, but it is a fixed,
hardcoded list with no mechanism for "expansion" built in anywhere. This
spec's job is to identify what "expanded" can plausibly mean against that
existing, inextensible system, and to name the strongest concrete
candidate(s) for a genuinely new scenario category.

## What exists today (verified against the code)

### `sheets_stress.py` — five bespoke, hardcoded stress sheets

Each of the five stress sheets is its own single-purpose, hardcoded
re-run of the deterministic engine under one perturbation, not a shared
"run N stress scenarios" framework:

- **Sheet 16 "Scenario Analysis"** — ten hardcoded scenarios (e.g. market
  crash at retirement, extended longevity, high inflation, LTC event),
  each a named tuple of `(label, mutate_fn)` baked directly into the
  sheet-building code. Adding an eleventh scenario means editing this
  list in place; there is no config surface, registry, or catalog entry
  that drives it.
- **Sheets 17/18** — LTC stress and survivor stress, each its own bespoke
  tuple-list pattern, structurally similar to Sheet 16 but not sharing
  code with it.
- RMD-audit and other remaining stress sheets follow the same one-off
  shape: a single hardcoded re-run, not a parameterized "scenario," with
  no way to add a new one without writing a new sheet function from
  scratch.

### `run_scenario(base_config, overrides=None, mutate=None)` — the one reusable primitive

`planning_engines.py:2166-2192` is a small, already-used "build one
variant of the plan and project it" helper: it takes a base config,
applies either a dict of field overrides or an arbitrary `mutate`
callback, and returns the resulting `project()` rows. Roughly ten
existing call sites across the codebase already use it (Roth-strategy
candidate scoring, some of the Sheet 16 scenarios, elsewhere). This is
the one piece of real, reusable "expansion" scaffolding that exists —
everything else in the stress-sheet code is bespoke per-sheet logic that
happens to call `project()` directly rather than through this shared
entry point.

### Divorce/QDRO — a registered module stub with zero implementation

`module_catalog.py:392-397` has a full catalog entry for a
"Divorce/QDRO" module — a name, description, and category slot exist in
the module-gating system — but its `sheet=None`: it is registered as an
optional module a user could nominally toggle, yet there is no sheet, no
projection logic, and no stress scenario anywhere that implements it.
This is the single strongest candidate for a genuinely **new** stress
category, as opposed to an extension of an existing one, because the
catalog scaffolding already anticipates it and nothing else does.

### Other candidates surfaced by research, each with a different degree of existing scaffolding

- **Social Security benefit cut exposure** — no existing stress row;
  would be a new scenario applying a haircut to modeled SS benefits
  (e.g. the commonly-cited ~2033 trust-fund depletion scenario), fits
  naturally as an eleventh Sheet 16 row via `run_scenario` overriding the
  SS benefit multiplier, but the multiplier/override point itself doesn't
  yet exist as a single config knob — would need to be added.
- **Healthcare-cost shock as its own deterministic re-run** — partial
  scaffolding exists (`wellness_shock_matrix` already models per-path
  healthcare cost variance inside the MC engines), but no equivalent
  single hardcoded "healthcare cost X% higher, from year Y" stress
  scenario exists in `sheets_stress.py` the way market-crash/inflation
  scenarios do.
- **Inflation shock** — Sheet 16 already has a "high inflation" scenario;
  "expansion" here would mean a differently-shaped shock (e.g. a sharp
  temporary spike rather than a sustained higher rate), not a new
  category.
- **Market-crash-at-retirement** — already exists as a Sheet 16 scenario;
  same as above, only a variant would be new.
- **Tax-law-change scenario** — no scaffolding at all; would require
  deciding which specific tax-law change to model (bracket reversion,
  RMD-age change, etc.), a product decision with no natural anchor in the
  code today, closer in shape to Phase 5's "no existing mechanism" case
  than Phase 3's "inert but built-for-this" case.

### Nothing generalizes the list itself

No config-driven scenario registry exists (unlike, say,
`module_catalog.py`'s pattern for optional modules). Adding any new
scenario — whether a genuinely new category like Divorce/QDRO or a
variant of an existing one like a different inflation-shock shape — means
hand-editing the relevant sheet's hardcoded tuple list today, regardless
of which option below is chosen. Building a genuine registry/framework
first (so that "expansion" becomes a data problem, not a code-editing
problem, for every future addition) is itself one of the design choices
this spec needs to put to the user, not something to assume.

## Options

**Option A — Add specific new scenario(s) to the existing hardcoded
lists, no framework change (recommended minimal scope).** Pick one or
more of the candidates above (Divorce/QDRO is the strongest genuinely-new
one; SS benefit cut is the strongest well-anchored variant) and implement
each as a new hardcoded row in the appropriate sheet, following the exact
shape of the existing ten Sheet-16 scenarios (a label plus a
`run_scenario` call with either an override dict or a `mutate` callback).
Lowest risk, smallest diff, consistent with this refactor's Phase 1/2
precedent of extending an existing pattern rather than replacing it.
Downside: each future scenario addition still requires the same amount of
hand-editing as today — "expanded" happens once, at this phase, not as an
ongoing capability.

**Option B — Build a lightweight scenario registry first, then populate
it.** Generalize Sheet 16's ten-tuple list (and ideally Sheets 17/18 too)
into a single declarative registry — e.g. a list of `{name, description,
mutate_or_overrides}` entries somewhere central — that the sheet-building
code iterates over, so adding a scenario in the future is a data change,
not a new code path per sheet. Then add the same new scenario(s) as
Option A on top of that registry. Larger diff, touches code the existing
stress sheets already depend on (real regression risk to a working
feature), but directly addresses "expanded" as an ongoing property of the
system rather than a one-time addition — arguably the more literal
reading of "expanded stress scenarios" as a phase name, since Option A
alone doesn't change the system's capacity to expand, only its current
contents.

**Option C — Implement Divorce/QDRO as a full module (not just a stress
scenario).** Since `module_catalog.py` already has the stub with
`sheet=None`, treat Phase 6 as the point where that module gets a real
sheet and projection logic (asset division, QDRO-based retirement-account
splits, alimony/support cash flows) rather than a single stress-scenario
row. This is a materially larger undertaking than either A or B — it is
building a new plan feature, not adding a stress test — and has no
existing precedent in this refactor's scope (every other phase has been
MC-engine reporting or shadow simulation, not a new deterministic-engine
domain feature). Plausible only if "expanded stress scenarios" was always
intended to include qualitatively new life-event modules, not just more
rows in `sheets_stress.py`.

## Recommendation

**Option A**, scoped specifically to Divorce/QDRO as a stress scenario
(not a full module — that's Option C's much larger scope) plus SS benefit
cut exposure as a second scenario. This mirrors Phase 3's Option A
precedent: extend an existing, working pattern (`run_scenario` +
Sheet-16-style hardcoded rows) with new, well-motivated content, rather
than rebuilding the mechanism (Option B) or expanding scope into a new
plan feature (Option C) without a specific signal that either was
intended. Option B is a legitimate alternative if the product intent
behind "expanded" is read as "make future expansion cheap," but that is a
architecture investment this refactor hasn't needed to make for any prior
phase and should be a deliberate choice, not a default.

## Open questions

1. **Which new scenario(s), specifically?** Divorce/QDRO and SS-benefit-cut
   are the two strongest candidates surfaced by research, but this is a
   product/financial-planning decision (which stress scenarios a planner
   actually wants to show clients), not an engineering one — needs
   explicit sign-off before implementation, same as Phase 5's rule
   specifics.
2. **Framework vs. content — Option A, B, or C?** As laid out above; this
   determines whether Phase 6 is a small, contained diff or a larger
   architectural change.
3. **For Divorce/QDRO specifically: stress scenario or full module?**
   The catalog stub already implies "module" was the original intent for
   *some* future work, but nothing says that future work is Phase 6
   specifically rather than a separate, later effort. Recommend scoping
   Phase 6 to a stress-scenario-shaped approximation (e.g., a one-time
   asset split plus ongoing alimony cash flow, modeled via `run_scenario`
   overrides) and leaving a "real" Divorce/QDRO module as explicitly
   out of scope / a future item, unless the user wants Option C's larger
   scope instead.
4. **Does a new scenario belong in Sheet 16 specifically, or does it need
   its own new sheet** (like Sheets 17/18 for LTC/survivor)? Depends on
   whether the new scenario needs sheet-specific detail (e.g. a
   before/after asset-split table for Divorce/QDRO) beyond what Sheet
   16's existing summary-row format supports.
