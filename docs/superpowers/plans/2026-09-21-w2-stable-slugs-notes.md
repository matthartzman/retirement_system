# W2 — Stable slugs: what was built, and the judgment calls

> Execution record for **W2** of
> `docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md` §4,
> implementing #329 P2 (`docs/superpowers/specs/2026-09-19-optimizer-stress-test-rationalization-design.md`
> §3.2, "Stable identifiers").

## What landed

- **`slug` on `SheetSpec`**, a required (no-default) field: `_spec()` now takes
  `slug` as a keyword-only argument, so a new `SHEET_REGISTRY` entry cannot be
  added without picking one — the same "fails at import, not silently" pattern
  W1 used for `domain`. All 42 entries got one (`roth_conversion`,
  `housing_comparison`, … — the spec's own two examples, confirming the
  naming convention).
- **`validate()` gained a fifth guard**: every slug is non-blank and unique
  across `SHEET_REGISTRY`.
- **`FINAL_SHEET_RENAMES` is dual-keyed.** `compute_final_sheet_renames`
  (`workbook_common.py`) now writes the same computed final title under both
  the sheet's stable (legacy build-time) name and its slug, so
  `FINAL_SHEET_RENAMES[slug]` resolves correctly at build time regardless of
  which letter this build's module set assigned — the literal fix for the
  spec's §1.1 "shifting-letters" defect (an external ticket that says
  `roth_conversion` stays correct; one that says `2J` does not).
- **`sheet_num_label_replacements()`'s resolution now routes through the
  slug** explicitly (`_SHEET_SLUGS.get(stable)` then
  `FINAL_SHEET_RENAMES[slug]`), naming the intended single source of truth in
  the code, not just leaving it true by coincidence.
- **A latent bug caught and fixed before it shipped**: `apply_template_layout`
  built `final_to_stable = {final: stable for stable, final in
  FINAL_SHEET_RENAMES.items()}` — inverting the *whole* dict. Once
  `FINAL_SHEET_RENAMES` is dual-keyed, that comprehension has two entries per
  sheet sharing the same `final` value (the stable-name entry and the
  slug entry), so the second one iterated silently clobbers the first,
  and the map ends up returning a **slug** where every caller needs the
  **stable name** — `TEMPLATE_LAYOUT.get(stable_key)` would have missed on
  every sheet, silently dropping all pinned column widths/row heights.
  Fixed by restricting the inversion to real `SHEET_REGISTRY` keys, the same
  pattern used in `_replace_text_refs`. Caught by re-reading every
  `FINAL_SHEET_RENAMES` consumer after the dual-keying change, not by a
  failing test — worth flagging because it is exactly the kind of
  full-workbook-only failure mode §7.6 of the master plan warns costs the
  most to find late.

## Judgment call 1 — dual-key, don't re-key

The spec's literal text is "every cross-reference … resolve display text
through `FINAL_SHEET_RENAMES[slug]`." The most literal reading — re-key the
global so slug becomes the *only* key — was rejected:

- `workbook_format_config.py`'s `apply_overrides`/`apply_alignments` resolve
  **persisted, on-disk** `workbook_format_overrides.json` /
  `workbook_format_alignments.json` entries, which are keyed by stable name
  (`#209/#210/#212/#228`'s own design note says so explicitly). Re-keying
  `FINAL_SHEET_RENAMES` to slug-only would silently stop every saved
  column-width/alignment override from applying — a user-data regression, not
  a refactor.
- `workbook_builder.py` has ~8 call sites keyed by stable name
  (`FINAL_SHEET_RENAMES.get('Plan Data', …)`,
  `FINAL_SHEET_RENAMES.get(stable_name, stable_name)`, …) and `dashboard.py`
  has one more. None of these are "cross-reference text" in the sense the
  spec is fixing (external tickets citing a letter) — they are internal
  plumbing that already uses the correct stable identity.

Dual-keying gets the literal ask — `FINAL_SHEET_RENAMES[slug]` genuinely
resolves, addressably, at build time — without moving or breaking anything
that already worked. The cost is one review-worthy sharp edge (see the
template-layout bug above and Judgment call 2 below), which is now fixed and
documented at both edit sites for the next person who adds a consumer.

## Judgment call 2 — `_replace_text_refs` searches stable names only, not slugs

The spec names `_replace_text_refs` directly as something that should route
through the slug. It does, for the **value** side (what a matched reference
gets rewritten to) — but the **search** side (what substring the whole-workbook
text pass hunts for) deliberately stays restricted to `SHEET_REGISTRY`'s
stable-name keys, not the dual-keyed dict's slug half.

Reason: stable names are long, punctuated, and Title Case
(`'11B. Tax Capacity'`) — there is no realistic existing cell text that
contains one as an accidental substring. Slugs are short snake_case fragments
(`tax_capacity`, `pc_umbrella`, `social_security`) chosen to *look like* an
ordinary internal identifier, because several sheets' own QC-check names and
internal dict keys already are exactly that shape
(`sheets_protection.py`'s `'pc_umbrella'`, `sheets_summary_builder.py`'s
`'social_security'`, `sheets_allocation_helpers.py`'s
`'asset_location_strength'`, …). Adding slugs to the blind substring-replace
set risked rewriting a fragment of unrelated existing text mid-sentence the
first time a QC description or debug label happened to contain one. Restricting
the search set to actual dict keys removes that risk entirely while leaving
`FINAL_SHEET_RENAMES[slug]` fully usable by any code that wants to resolve a
slug directly (rather than search for one in prose).

## Judgment call 3 — `module_catalog.py` is in scope despite the plan's file list

The master plan's W2 entry lists `workbook_common.py`, `workbook_builder.py`,
and `_replace_text_refs`'s call sites. `SheetSpec`, `_spec()`, and
`SHEET_REGISTRY` all live in `module_catalog.py` (moved there in the
system-review "sheet-identity-scattered-across-five-tables" finding, per W1's
notes) — there is no version of "add `slug` to `SheetSpec`" that avoids
editing it. Treated as implied scope, the same way W0/W1 treated the plan's
file lists as indicative rather than exhaustive.

## Judgment call 4 — `workbook_builder.py` needed no edits

Under the dual-key design, every existing `workbook_builder.py` call site
keeps working unchanged — they all key by stable name, which is untouched.
The plan listed the file because a naive re-keying implementation would have
had to touch it; this implementation doesn't. Recorded rather than silently
skipped, since "files touched" not matching the plan's list is worth a reader
knowing was a deliberate scope call, not an oversight.

## Judgment call 5 — slugs are hand-typed, not derived from `display`

Slug values are written directly at each `SHEET_REGISTRY` entry rather than
mechanically slugified from the `display` field. `display` can be reworded in
a future workstream (W3 regroups sections; a display title could change for
clarity) without that silently reslugging a sheet and breaking whatever
external reference used the old value — the whole point of the field is that
it *doesn't* move when other things do.

## Verification

- `pytest -m "not slow"` — full fast suite, green (includes
  `tests/test_module_catalog.py` and `tests/test_sheet_table_consistency.py`,
  both updated-shape-aware and green with the new `slug` field).
- Targeted: `tests/test_workbook_format_config_regression.py`,
  `tests/test_workbook_five_area_tabs_functional.py`,
  `tests/test_workbook_numbered_section_tabs_functional.py`,
  `tests/test_workbook_common_explicit_all_regression.py`,
  `tests/test_workbook_account_label_binding_functional.py`,
  `tests/test_workbook_section_divider_no_unsupported_args_functional.py`,
  `tests/test_before_after_zero_rows_and_layout_functional.py`,
  `tests/test_workbook_system_cleanup_and_widths_functional.py` — green.
- Representative-configuration build:
  `tests/test_housing_trajectory_comparison_sheet_functional.py::test_full_workbook_build_succeeds_with_the_module_on_and_off`
  (`@pytest.mark.slow`, `@pytest.mark.parametrize("enabled", [True, False])`)
  — a real subprocess build of the workbook with the module toggled both
  ways, the closest existing test to the plan's "Done: a workbook built with
  a different module set carries correct cross-references."

No behavior change to any built workbook: `FINAL_SHEET_RENAMES` gained keys,
it lost none, and every existing lookup path resolves to the identical value
it did before this workstream.
