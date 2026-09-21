# H2/A1-A4 anchor-flow implementation notes

Decisions made while implementing #331 A1-A4
(`docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
§4 "H2", against
`docs/superpowers/specs/2026-09-19-housing-optimizer-anchor-flow-and-timing-design.md`
§5) where the spec left a genuine choice open. Recorded here rather than
resolved in a review round, following the H1/W0-W3 pattern.

## A1 -- the per-anchor quota

### `per_anchor_quota` is a reservation count, not a survivor count

Every other funnel key counts what survived a stage, and
`test_zip_screen_funnel_unit.py` asserts the counts are monotonically
non-increasing. The quota stage does not filter -- it reorders promotion --
so "what survived it" is just `near_family` again, which reports nothing.
The count reported is instead **how many of the shortlist's slots the
reserved pass claimed**, which is the diagnostic the stage exists to
provide. It is therefore the one stage whose count can read lower than the
stage after it.

The monotonicity assertion is unaffected: it covers single-anchor
`run_screen`, whose funnel is untouched (the quota lives only in
`run_multi_anchor_screen`, per §5.2), and no equivalent assertion exists on
the multi-anchor funnel.

### The shortlist cap floors at the anchor count, in the screen

§5.2's closing line puts `max(default_preview_size, len(anchors))` at the
preview layer. §1.1, though, names the too-small cap itself as part of the
defect ("the default `shortlist_size` is 4 ... and up to 5 anchors are
accepted, so the shortlist can be numerically too small to represent every
anchor even in principle"), and §5.1 is explicit that the quota belongs in
`screen.py` precisely so headless callers (`tools/housing_lab.py`,
`optimize_housing_from_request`) inherit the guarantee rather than a
UI-only fix.

A floor applied only in `api.py` would leave a direct `run_multi_anchor_screen`
caller able to ask for 2 slots across 5 anchors and get the silent discard
back. So `_promote_with_anchor_quota` floors the cap at `len(anchor_zips)`
itself, and `parse_move_search` states the same floor at its own layer. A
caller asking for zero still gets zero.

### The promoted set is re-sorted into score order

§5.2 specifies the two passes and says "score order within each pass is
unchanged", but not what order the combined result is returned in. Returning
it in fill order (reserved first, in declared anchor order) would put a
low-scoring reserved ZIP ahead of higher-scoring ones for every consumer --
display, `_resolve_screened_locations`, and the optimizer's tie-breaks --
even when the quota changed nothing.

The shortlist is therefore re-sorted by `(-nss, distance_miles, zcta)` before
being returned, so when the natural top-N already covered every anchor the
output is byte-identical to the pre-quota one. The quota changes
*membership*, never presentation order; `quota_reserved` (and the
"covers {anchor}" badge it drives) is what makes the reserved rows visible.

## A2 -- `selected_zips` on the wire

### An empty screen is not a stale selection

Both leave the requested ZIP out of `all_passing`, so `select_screened_zips`
alone cannot tell them apart -- but they are different problems with
different remedies, and §5.5 resolves only the second. `optimize_housing_from_request`
already had a 200-with-message path for a screen that returns nothing
("Widen the radius, lower the minimum quality score, or add anchors"), and
`test_zip_screen_optimizer_integration.py` pins it.

Emptiness is therefore checked first (`_selected_locations`): a screen with
no candidates keeps its own message, and the §5.5 stale-selection rejection
is reserved for the case it was written for -- a screen that *has*
candidates but does not contain one the client asked for. Naming an
arbitrary ZIP as stale when the funnel is empty would send the user back to
re-pick from a list with no rows.

### `promoted` reflects the selection; `per_anchor_quota` still describes the preview

In the optimize response, `zip_screens.move{n}.shortlist` and its funnel's
`promoted` count are narrowed to what the user actually selected, so the
results page never shows a shortlist that differs from what ran.
`per_anchor_quota` is deliberately *not* narrowed: it is a fact about the
preview the user chose from, not about the choice they made.

### `all_passing` ships only on the preview endpoint

§5.3 lets the user tick ZIPs the quota did not promote, so the selection
table needs the whole passing set. The optimize response has no reader for
it and would carry a few hundred rows twice per move, so `screen_payload`
gained an `include_all_passing` flag that only `zip_screen_from_request`
sets.

### A double-tick is not a second candidate

`parse_selected_zips` de-duplicates while preserving order. A client that
sends the same ZIP twice asked for one search of it, and the 1-10 bound is
counted after de-duplication.

## Deliberately inverted tests

Each of these pinned behaviour this change removes on purpose. They are
updated with the reason in-place, not deleted.

| Test | Was | Now |
|---|---|---|
| `test_zip_screen_api_contract.py::test_shortlist_size_is_clamped_to_two_through_five` | request-side `shortlist_size` clamped to 2-5 | the key is ignored outright (§5.4); a stale client cannot shrink the preview it is choosing from |
