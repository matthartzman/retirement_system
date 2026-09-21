# W1 — Catalog foundation: what was built, and the two judgment calls

> Execution record for **W1** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4.
> Merges #329 phase 1 with #330 phases 1–2 into one pass over
> `src/module_catalog.py`, as §1 of that plan requires.

## What landed

- **`domain` on all 40 modules**, plus the three newly-catalogued ones, using
  #330 §4.2's ten categories verbatim. W0/V2 confirmed the owned-vs-needed
  protection split, so no value in that table moved.
- **Three missing `CATALOG` entries**: `hsa_drawdown`, `tax_capacity` and
  `current_vs_proposed`. All three had a sheet and a builder but no module
  record, so nothing could classify, gate or place them.
- **Both catalog↔registry joins fixed.** `scorp_vs_llc.sheet` and
  `plan_data_ref.sheet` named strings that are not `SHEET_REGISTRY` keys, so
  the join silently produced nothing for them.
- **The five section/letter contradictions.** `31`–`33` (3D–3F) kept their
  letters and moved section; Tax Capacity moved to Reports; Planning Levers
  moved to the System group it already physically sat in.
- **The missing `housing_trajectory_comparison` toggle row**, set `TRUE`
  because `module_enabled` defaults an absent key to enabled — a `FALSE` row
  would have turned the module off and moved golden masters, and W1 is
  behavior-neutral by contract.
- **`module_taxonomy` on the config payload** (#330 phase 2), so W4's page has
  one source for both axes.
- **Four guards**, three at import and one in the suite (see below).

## Judgment call 1 — `kind` gains three members, not two

#329 §3.1 says `kind` gains `COMPARISON` and `PROTECTION`. Adding only those
two leaves the invariant unsatisfiable, because §3.2 also moves **Tax Capacity
into Reports** while §2 classifies it as a *Worksheet* — and the only existing
kind for a worksheet is `REFERENCE`, whose other four sheets live in System.
One kind cannot imply two different groups, so the derivation §3.1 is building
toward would have had to carry a hand-written exception for exactly the sheet
the invariant was introduced to catch.

`WORKSHEET` is therefore a third new member, separate from `REFERENCE`:

- **Worksheet** — restates or consolidates figures computed elsewhere. Plan
  content a reader acts on. Belongs with Reports. *(Tax Capacity, Current vs
  Proposed.)*
- **Reference** — documents how the run was produced. Belongs with System.
  *(Plan Data, Assumptions, Methodology, Glossary.)*

This is #329 §2's own six-way vocabulary, which already names Worksheet as a
distinct definition; only §3.1's count of new members assumed it could share
`REFERENCE`. #330 corroborates the split independently: its §4.2 puts Tax
Capacity in the **Taxes** domain while Methodology and Glossary sit in Reports
& Documentation. Two specs separating the same two things on two different axes
is the signal.

With the third member the map is total and functional, and it catches exactly
the five violations #329 named and nothing else — which is the evidence that it
is the right map rather than a map fitted to pass.

## Judgment call 2 — the fourth guard lives in the test suite

The plan asks for four `validate()` assertions "all at import time". Three are
there. The fourth — every `optional=True` module has a toggle row in the
default plan — reads `input/demo/client_optional_functions.csv`, and
`module_catalog`'s first stated design constraint is that it imports nothing
beyond the stdlib so it can be validated without the reporting stack. Making
import-time validity depend on a CSV on disk would trade a real guard for a new
failure mode in every consumer that does not ship `input/demo/`.

It is `test_every_optional_module_has_a_toggle_row` in
`tests/test_module_catalog.py`, and it checks both directions: an optional
module with no row (silently always-on, which is how Housing Comparison shipped
"optional" while being impossible to turn off) and a row naming no module.

## Consequences W3 should expect

- **`KIND_LETTER_PREFIX` is the map W3 edits.** The regrouping *is* moving
  `COMPARISON` to its own `'3'` and `PROTECTION` into the renamed `'4. Risks'`
  in that table, then deleting the hand-typed `section`/`letter_prefix` fields
  the assertion currently compares against.
- **Letters shifted once already.** Pulling Planning Levers and Tax Capacity
  out of group `2` pulled every letter after Estate & Legacy up by one. Three
  test files pinned those letters and were updated; the two subprocess build
  tests confirm the real workbook now produces the predicted strip.
- **`tab=` was stale on eight modules** and is corrected, but it remains
  documentation — the real label is computed per build. W3 removes the field
  when cross-references resolve through W2's slug.
- **`v5_code` was deliberately not touched.** It is vestigial: its only
  consumer ignores it (`for name, _ in V5_LAYOUT`). The invariant covers
  `section` and `letter_prefix` only, and moving a third field for tidiness
  would have put unreviewable churn in a behavior-neutral commit.
