# Hybrid LTC soft dependency — what was built, and the judgment calls

> Small, scoped follow-up deferred by W9 (`docs/superpowers/plans/
> 2026-09-22-w9-ui-section-registry-notes.md`) and confirmed by W12
> (`docs/superpowers/plans/2026-09-22-w12-off-state-rendering-notes.md`), not
> a numbered master-plan workstream. W9's own words: the item "needs a *new*
> catalog field mapping `gate_ref` to its parsed config key, plus a parallel
> sweep test for plan-flag reads... W5-shaped dependency-declaration work,
> not UI registry work."

## Scope

Declare the soft dependency between `hybrid_ltc_policy` (a `gate_kind
="plan_flag"` module, W6) and the module whose output it shapes, following
W5's exact `_soft()` pattern (`docs/superpowers/plans/
2026-09-21-w5-dependency-declarations-notes.md`), and extend the call-site
enforcement sweep (`tests/test_module_toggle_call_site_enforcement.py`) to
recognize a plan-flag read as a third pattern alongside `module_enabled(`
and raw `c['opt']` reads.

## Judgment call 1 — the dependent is `life_insurance_need`, not `long_term_care_stress`

Both W9's triage and W12's confirmation name the item as `long_term_care_stress
→ degrades_without`. That is shorthand for "the Hybrid LTC stress-test area,"
not a verified claim about which catalog module's builder actually reads the
flag — and it does not survive reading the code.

`build_sheet17` (`src/reporting/sheets_stress.py`, "17. LTC Stress Test",
owned by `long_term_care_stress`) never reads `ltc_enabled` at all. Its
closing recommendation line ("Consider a Hybrid Life/LTC policy to cap
open-ended risk. No LTC policy is currently in force...") is static text,
unconditional on the plan flag — itself a pre-existing minor inaccuracy
(it always says "not in force" even when one is configured), but out of
scope here: no calculation or copy change beyond what this workstream adds.

The actual "configured-policy column" the task brief points at — grepped
directly in `sheets_stress.py` rather than assumed from a module name — is
in `build_sheet19` ("19. Life Insurance", owned by `life_insurance_need`,
already `optional=True`). Section D's Hybrid Life/LTC verdict cell and the
closing paragraph name this plan's actual configured policy (face, premium,
start year) only while the flag is on:

```python
_hybrid_verdict = (
    f'Configured: ${opt_face:,.0f} face, start {opt_start}, ~${opt_prem:,.0f}/yr'
    if opt_enabled else
    'Not currently configured — see Section C for the coverage levels compared'
)
```

and the equivalent branch in the closing paragraph. Section C's four-tier
coverage-option comparison table is unaffected either way — it is an
illustrative market comparison, not this household's data, and its
"← configured for this plan" marker is driven by `ltc_face` matching a
listed tier regardless of the enabled flag (a plan can type in a face value
without turning the flag on, same as every other plan-flag field).

So: `degrades_without` lands on `life_insurance_need`, not
`long_term_care_stress`. This is exactly the kind of near-miss W5's own
Judgment call 2 (`business_succession`, caught by the reverse assertion)
warns about — the difference here is it was caught by reading the builder
before declaring, rather than by the test after.

## Judgment call 2 — the sweep needs a named accessor, not a literal-key match

The obvious literal reading of "recognize a plan-flag read as a third
pattern" is: match any `c.get('<key>', ...)` or `c['<key>']` where `<key>`
is a plan flag's `gate_config_key`. Implemented and then discarded.

Extending the sweep that way and re-running it surfaced four hits, not one:

| Site | What it actually does |
| --- | --- |
| `sheets_stress.py:build_sheet19` | The intended site — Section D's verdict/closing text |
| `spending_and_rmd.py:apply_spending_and_rmd` | Adds `ltc_prem_yr` to the actual projected cash need — moves the projection |
| `sheets_projection_cashflow.py:build_sheet6` | Drops the LTC premium column from Cash Flow Projection when nothing is configured |
| `sheets_current_vs_proposed.py:_proposed_changes` | A recommendation-engine row: "consider Hybrid LTC" |
| `sheets_summary_builder.py:build_sheet1` | The same recommendation-nudge pattern, on Executive Summary |

The first three are real, and two of them are *additional* genuine
relationships (see Judgment call 3). The last two are not soft dependencies
at all, and forcing them into `degrades_without` would have been a
modelling error worse than not sweeping them: both rows are conditioned on
`not c.get('ltc_enabled')` — they *appear* (as a "you might want to
consider this" nudge) precisely while the flag is **off**, and disappear
once it is **on**. `degrades_without`'s field contract is one-directional
("this shows less because X is off"); a phrase describing this relationship
would read backwards ("Turning Hybrid LTC off also removes the recommendation
to consider Hybrid LTC" is false — turning it off is what makes the row
appear). `cst_enabled`/`qtip_enabled`/`daf_amount` are read the identical
way, in the identical two files, and were never swept — they happen not to
be any catalog module's `gate_config_key`. A blanket literal-key match would
have swept `ltc_enabled` into the same bucket purely by coincidence of
choosing to add the field, not because the read is actually gate-shaped.

**Resolution:** `module_catalog.plan_flag_enabled(c, key)`, a new accessor
with the same `(c, '<literal key>')` shape as `module_enabled(c, '<key>')`,
resolving the module's `gate_config_key` internally. The sweep matches calls
to this named accessor exactly the way it already matches `module_enabled(`
— by name, not by guessing at literals — so only call sites this workstream
actually converts get swept. `sheets_stress.py`'s `build_sheet19` is the only
site converted (`opt_enabled = plan_flag_enabled(c, 'hybrid_ltc_policy')`,
replacing `c.get('ltc_enabled', False)` — behaviorally identical, since
`hybrid_ltc_policy.gate_config_key == 'ltc_enabled'`). The other three raw
reads are untouched: they existed before this workstream, are not new call
sites it introduces, and (per the recommendation-nudge pair above) two of
them would be actively mis-declared if swept. `plan_flag_enabled` is
re-exported from `workbook_common.py` alongside `module_enabled`, the same
route every other sheet builder already uses to reach it.

This mirrors why `module_enabled(` and `c['opt']` were safe generic patterns
in W5 and a bare `gate_config_key` literal is not: the first two are
*structural* — `module_enabled()` is the one accessor, `c['opt']` is the one
toggle-storage mapping — while a plan flag's parsed value is an ordinary
config-dict entry, syntactically indistinguishable from any other typed
input field until a call site deliberately routes through a named accessor.

## Judgment call 3 — `spending_and_rmd.py` and `sheets_projection_cashflow.py` are left as future scope, not silently dropped

Because the sweep now only matches the named accessor, and only one call
site was converted to use it, the two other genuine relationships found in
the process (`apply_spending_and_rmd`'s premium affecting the actual
projection — an `engine_participation` candidate; `build_sheet6`'s LTC
premium column disappearing from Cash Flow Projection — a second `soft`
target on `cash_flow`) are **not** declared here. Declaring either would
require converting those call sites to `plan_flag_enabled()` too, which is
additional scope beyond "the configured-policy column" the task brief named,
and beyond what W9/W12 scoped ("this deferred item," singular). Recorded
here, in the same spirit as W9's own triage table, so the next workstream
that touches `hybrid_ltc_policy`'s `degrades_without`/`engine_participation`
does not have to rediscover them:

- `spending_and_rmd.py:apply_spending_and_rmd` reads `c.get('ltc_enabled',
  False)` (gated further by `ltc_annual_prem > 0` and `year >=
  ltc_start_year`) to add the premium to `row['ltc_prem_yr']`, which flows
  into the household's actual spending need. This is engine participation
  in the same sense as `equity_compensation`/`disability_income_insurance`.
- `sheets_projection_cashflow.py:build_sheet6` reads the same flag (plus a
  positive premium) to decide whether to include an LTC-premium column in
  the Cash Flow Projection detail; `cash_flow` already declares one soft
  dependency (`existing_life_insurance`) and could take a second.

Left as raw `c.get('ltc_enabled', ...)` reads, unswept, exactly as they were
before this workstream — no behavior change, and no aspirational
declaration either.

## Judgment call 4 — `validate()`'s degrades_without guard needed a plan-flag exception

`hybrid_ltc_policy` is `gate_kind=GATE_PLAN_FLAG`, and W6's own guard
requires `not m.optional` for any plan flag (`optional=True` +
`gate_kind=GATE_PLAN_FLAG` is exactly the DAF double-gate #330 Q2 removed).
W5's existing guard on `degrades_without`'s target read `assert
CATALOG[dep].optional` ("a core module has no toggle, so nothing can degrade
without it") — which would reject `hybrid_ltc_policy` as a target purely
because it is a plan flag, even though a plan flag has a real switch (a
plan-data row, just not a CSV toggle). Extended to `assert CATALOG[dep]
.optional or CATALOG[dep].gate_kind == GATE_PLAN_FLAG`. Confirmed this was
not already permitted — the task brief's own caution to "read `validate()`
carefully rather than assuming" was warranted; before this change,
`mc.validate()` raised on the new declaration.

A second, smaller guard was added for `gate_config_key` itself: it is
meaningful only alongside `gate_ref`/`gate_enable_label`, so it inherits
their `gate_kind == GATE_PLAN_FLAG` requirement rather than a third copy of
the same check.

## Verification

- **Deliberately broke the call site once**, per the task's own instruction
  and W5's precedent: renamed the declared site's function to a wrong name
  in `DECLARED_SITES` and reran `test_the_sweep_finds_exactly_the_declared_
  call_sites`. It failed immediately, reporting `sheets_stress.py
  :build_sheet19() reads hybrid_ltc_policy` as an undeclared site — proof
  the sweep is real, not a fixture pass-through. Reverted.
- `mc.validate()` — passes with the extended guard.
- `pytest tests/test_module_toggle_call_site_enforcement.py
  tests/test_module_catalog.py` — green (46 tests before this workstream's
  additions to the file; still green after).
- `pytest tests/test_life_insurance_capital_needs_regression.py
  tests/test_optional_module_gating.py
  tests/test_module_catalog_prereq_gating.py` — green (25 tests).
- Full `pytest -m "not slow"`, `npm test`, and
  `tools/regen_golden_master.py measure` run before the final push (see
  PR #132's own updated verification note for this item).

## A mid-task correction worth recording: the branch had moved

Partway through, a check against PR #132 showed `## W12`/`## W13` sections
already landed in the PR body, while this session's local checkout was still
sitting at the W10c commit — the origin branch had moved forward
(W11/W12/W13 landed) after this session's container was created. Stashed the
in-progress diff (`git stash push -u`), fast-forwarded local `HEAD` onto
`origin/claude/master-implementation-plan-2tv0km` (a clean fast-forward, no
rebase needed), and popped the stash back on top — it auto-merged cleanly
against the newer `module_catalog.py`/`workbook_common.py` with no
conflicts. Re-ran `validate()` and the full targeted test list again
afterward to confirm nothing about W11–W13 changed the analysis above (the
real W12 notes doc, read at that point, restates the same triage as W9's
copy verbatim in substance). No content from before the fast-forward was
lost or overwritten.

## Global constraints, confirmed

- No calculation changes: the one code change (`sheets_stress.py`'s
  `opt_enabled` line) reads through a new accessor to the exact same
  underlying key, with identical `bool(c.get('ltc_enabled', False))`
  semantics. `tools/regen_golden_master.py measure` shows zero delta.
- This is a declaration/enforcement addition only — a new field, a new
  accessor function, one call-site rewire, one catalog declaration, one
  sweep pattern, one `validate()` guard extension.
