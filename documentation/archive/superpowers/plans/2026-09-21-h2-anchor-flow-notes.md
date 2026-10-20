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

## A3 -- the two-step panel

### The screen derives the move-year price, because the client cannot

§5.3 requires the estimated-price column to show move-year dollars with
today's as secondary text, under a header naming the reference year
("Estimated price -- as of 2041, midpoint of 2036-2046"). §5.5 is equally
firm that **no rate travels on the wire**.

Those two only reconcile one way: the escalation happens server-side.
`ScreenedZip` gains `est_price_move_year` and `est_price_reference_year`,
computed in `run_screen` from the *same* `years_out`/rate that deflates the
budget bounds -- hoisted into one pair of locals so the two can never be
computed from different rates. Deflating the bound and escalating the
estimate are two views of one comparison.

Without this the header would be labelling a today's-dollars number with a
future year, which is exactly the class of quiet mislabelling the
reference-year disclosure exists to prevent.

### The rules keep one order; only the message's destination splits

§5.3 makes anchor count and the year-window rules step-1 rules and leaves
the rest on step 2, but `validate_request`'s contract is that client and
server "never disagree about which rule fired first". Splitting
`validateHousingOptForm` into two independently-evaluated halves would have
broken that.

Instead `housingOptFirstViolation()` keeps the single ordered rule list and
returns `{step, message}`. `validateHousingOptForm()` is unchanged in
meaning and still returns the first message. `step` decides only which
validation box the message lands in. The Run button stays disabled while
*any* rule fails, so the split cannot smuggle an invalid request through,
and Continue is blocked only by step-1 rules -- a step-2 rule the user
cannot see yet must not trap them on step 1.

Two rules the spec does not place explicitly:

- **"With no dual ownership, move 1 cannot be bought before the home is
  sold"** is a step-1 rule. Its constraint comes from the sale window on
  step 2, but the remedy the message names ("raise the move-1 latest year")
  is a step-1 field, and the message belongs where the user can act.
- **"Concurrent mode is only available with Full grid search mode"** is a
  step-2 rule: both `search_mode` and the Move-2 mode row live there.

### "Move 2 -- mode" stays on step 2, unlike the rest of move 2

§5.3's tables put move 2's where/when/what rows on step 1 and its
Concurrent/Anchor-count row on step 2, which reads as an inconsistency until
you notice it is the right cut: concurrency and the anchored strategy's
branching factor are costing questions, not location ones. The one
checkbox governs blocks in both steps, so `toggleHousingOptMove2Fields` and
the hydration pass each reveal two containers rather than one.

### `per_anchor_quota` is not rendered as a funnel arrow

The funnel readout is a chain of survivor counts. Splicing
`-> 2 ->` into it would read as a drop to two candidates, which is not what
the stage does. It renders as a trailing clause instead -- "... 4 sent to
the optimizer (2 reserved to cover your anchors)" -- and is omitted entirely
when the key is absent, as it is on a single-anchor screen.

### The selection is remembered; the table it was picked from is not

§9.6's rule is that nothing derived from a run is persisted. The screen
payload is a run result, so it is not saved, but the selected ZIPs are the
user's own input and are. A returning user therefore gets their ZIPs back
(the step-1 gate and step-2 chips are correct on first paint, and Continue
is re-enabled at render time rather than waiting for an input event) but has
to press *Find candidate locations* again to see the table. Anything that
no longer screens is caught by A2's stale-selection rejection.

The panel always reopens on step 1 for the same reason: landing a returning
user on step 2 would show them a "Selected locations" summary for a
selection whose table is not on screen.

### A fresh screen replaces the selection outright

Pressing *Find candidate locations* again re-seeds the selection from the
quota's promotions rather than intersecting with what was ticked before.
The previous ZIPs were chosen under different filters -- carrying them
forward is precisely the stale selection A2 rejects.

### The memo fingerprint excludes `selected_zips`

`housingOptMoveSearchBody` now carries the selection, but the screen request
strips it before fingerprinting: it is the answer the call produces, not an
input to it, and leaving it in would invalidate the memo on every tick.

### Three ordering constraints in the panel file are now load-bearing

`tests/test_zip_screen_*_functional.py` read the panel JS as text with fixed
character windows and split delimiters. Three consequences shaped the code
rather than the tests:

1. The row builders are **defined** Where, What, When even though they now
   **render** Where, When, What, because the "what" row's block is delimited
   by the "when" one's definition.
2. `renderHousingZipShortlistHtml`, `housingZipRowHtml` and
   `housingZipFunnelText` must stay adjacent and compact -- the column
   tokens are asserted within 3,000 characters of the first and the funnel
   tokens within 4,000. The new helpers were placed *before* the renderer,
   the long explanatory comments were lifted out of the two function bodies
   into a block above them, and `housingZipRowHtml` hoists its score, price
   and distance cells to the top so those tokens land early. (Measured after
   the change: the furthest asserted token sits at 3,712.)
3. Both moves' step-1 rows are written out call by call
   (`housingOptMoveWhereRowHtml(1)`, `...(2)`, and so on) rather than through
   a shared wrapper, because the tests assert those literal call sites as
   proof the two moves cannot drift apart.

## A4 -- frontend tests

### A3's own tests caught a real bug: the memo was defeated

`findHousingOptCandidates` passed `{ force: true }` to every
`previewHousingZipShortlist` call, unconditionally bypassing OQ-6's
client-side memo -- the exact button it exists for. Writing the "a second,
unchanged Find is a no-op" test surfaced this immediately (2 requests where
1 was expected). Fixed in the same commit as the test: the loop no longer
forces, and the memo's own fingerprint check decides whether a request is
needed. `test_frontend_size_ratchet.py`'s `TOTAL_JS_MAX_LINES` absorbs the
five-line fix and its comment.

### Screen fixtures must respect the promoted/all_passing split themselves

An early version of the test file's `screenPayload()` fixture put a
non-promoted row in `shortlist` as well as `all_passing`. That contradicts
what `api.py`'s `screen_payload(include_all_passing=True)` actually sends
(only promoted rows appear in `shortlist`; `all_passing` carries a
`promoted` flag per row) and it silently made the "seeds the selection from
the quota's promotions" test pass for the wrong reason -- the un-promoted
row leaked into the initial selection regardless of whether the seeding
logic used `shortlist` or something looser. Worth calling out because nothing
in the panel code would have caught a fixture this wrong; only re-reading it
against the real contract did.

## Deliberately inverted tests

Each of these pinned behaviour this change removes on purpose. They are
updated with the reason in-place, not deleted.

| Test | Was | Now |
|---|---|---|
| `test_zip_screen_api_contract.py::test_shortlist_size_is_clamped_to_two_through_five` | request-side `shortlist_size` clamped to 2-5 | the key is ignored outright (§5.4); a stale client cannot shrink the preview it is choosing from |
| `test_zip_screen_panel_functional.py::test_shortlist_size_control_exists` (`:72`, flagged in the master plan) | the `${p}ShortlistSize` select exists | asserted as an *absence*, so re-adding the control has to be argued for again |
| `test_housing_optimizer_panel_functional.py`'s `FULL_CONTENT_KEYS` | `housingOptMove{n}ShortlistSize` needs full four-section help | `...SelectedZips` does; the help obligation moves with the decision rather than being dropped |
| `housing_optimize_panel.test.mjs::global constraints and objective come before the move sections` | objective/presence precede move 1 | the moves come first -- they are step 1 now (§5.3) |
| `housing_optimize_panel.test.mjs::a Purchase assumptions section sits between Current home and Move 1` | assumptions sit before move 1 | assumptions are a step-2 section, after the moves; their position *within* step 2 is still pinned |
| `housing_optimize_request.test.mjs::the run button is disabled while the form is invalid` | a move-1 year rule writes to `housingOptValidation` | it writes to `housingOptStep1Validation`; the Run button being disabled by a rule on the *other* step is asserted unchanged, and a companion test covers a step-2 rule |

## Pre-existing failures, not caused by this change

`tests/frontend/js_codemod_parser_offsets.test.mjs` fails two assertions
("jscodeshift offsets") on this branch **and on a clean checkout of the same
base** -- a jscodeshift version difference in the container, unrelated to
housing. Verified by stashing the branch's changes and re-running. Left
alone rather than worked around here.
