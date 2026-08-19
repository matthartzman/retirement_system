# Roth Conversion Gap Design — Tax Payment Source & Asset-Location-Aware Conversion

Ticket 289, Step 8.3. **Design only — no code in this document, and none was
written for these two features.** Companion to
`docs/superpowers/plans/2026-08-17-roth-guide-audit.md`, which confirmed both
gaps against the engine (`grep -rn "conv_tax_source\|tax_payment_source\|withhold_from_ira\|taxable_cash" src/*.py`
and `grep -rn "convert_equity\|conversion_asset\|sleeve" src/planning_engines.py`
both return nothing).

---

## Gap 1: Conversion Tax Payment Source

### What the guide asks for

§4 Variable 1, called a "Critical Multiplier": whether conversion taxes are
paid from taxable cash (preserving 100% of the converted balance inside the
Roth shield) or withheld from the IRA itself (which both shrinks the
converted amount and, under 59½, can trigger an early-withdrawal penalty on
the withheld portion).

### New plan-data key

`roth_conversion_tax_source`: `taxable_cash` | `withhold_from_ira`.
Section `Withdrawal Policy`, subsection `Roth Conversion` — same location as
the sibling `roth_*` keys already there. Default: `taxable_cash`, matching
the guide's own recommendation ("pay conversion taxes exclusively from cash
or taxable brokerage assets") and preserving today's *implicit* behavior,
since the model currently applies the tax without touching the converted
balance — i.e. today's behavior already matches `taxable_cash` semantics,
just without a name or an alternative.

### Where it enters the cascade

`apply_roth_conversion` (`src/planning_engines.py:1245+`) currently computes
the conversion amount and its tax cost, and (per the existing
`non_roth_surplus` field on the dataclass at that location) already tracks
whether non-Roth cashflow covers the tax without touching the IRA. The
natural integration point is right where that tax cost is realized against
cashflow, inside the same function:

- **`taxable_cash`** (today's implicit behavior): tax draws from the
  household's existing cash/taxable waterfall — no new mechanic, just an
  explicit label on the status quo.
- **`withhold_from_ira`**: the converted amount itself must be reduced by
  the tax withheld, i.e. `net_converted = gross_conversion - tax_on_conversion`,
  and the withheld portion needs to flow through the **existing** early-
  withdrawal-penalty path the engine already has for pre-59½ pre-tax
  distributions (need to locate and confirm that path handles a conversion-
  sourced withdrawal identically to a normal distribution — this is the one
  piece of research this design doc has NOT done, and would need to precede
  implementation, not follow it).

### Interaction with the liquidity-buffer floor

The `taxable_cash` path draws against the same taxable/cash waterfall the
liquidity buffer's `liquidity_buffer_years_for_year` floor already governs
(see this repo's own memory: the buffer sets a floor under the taxable draw
in `withdraw_taxable_trust`). A `taxable_cash`-sourced conversion tax that
would push the taxable draw below that floor needs a defined behavior:
either the floor wins (tax payment deferred/reduced, meaning the conversion
itself may need to shrink to fit) or the tax wins (floor breached for this
year). The guide doesn't address this interaction; it needs an explicit
decision before implementation, not an assumption baked in silently.

### Expected pin movement

**This WILL move the frozen golden-master pins**, because it's a real
behavior change to the engine's cash-flow mechanics, not a data-at-rest
relabeling like ticket 291's key renames. Per T286's tooling
(`tools/regen_golden_master.py regen --reason`), the regeneration would need
a `--reason` file explaining: which commit introduced the change, and why
the new terminal-NW/lifetime-tax figures are the intentional result of
`withhold_from_ira` becoming a real, selectable option rather than an
unavailable one (the default `taxable_cash` case, if it exactly reproduces
today's implicit behavior, should NOT move the pins on its own — if it does,
that's a bug in the implementation, not a legitimate regen, exactly per this
plan's own precedent from ticket 291).

### Files touched (estimate)

- `src/planning_engines.py` — `apply_roth_conversion` (the withholding branch)
- `reference_data/schema.csv` — new key + helper text
- `frontend/js/dashboard_decomp_allocation_optimizer.js` — new control row
- `src/reporting/sheets_strategy.py` — the two disclosure notes added in
  Step 8.2 become conditional (already gated on this key's absence — see
  that commit) and a new row reporting which source was used
- New test file, following this repo's TDD convention: RED test asserting
  `withhold_from_ira` reduces the converted balance and applies the penalty
  path for pre-59½, GREEN once implemented

### Test strategy

Unit tests for the two source modes in isolation (does `withhold_from_ira`
correctly reduce net converted balance, does the pre-59½ penalty apply);
an integration test against a synthetic plan confirming `taxable_cash`
reproduces pre-change golden-master figures exactly (proves the default is
truly behavior-preserving); a golden-master regen for `withhold_from_ira`
itself, since that path is new behavior with no prior pin to preserve.

### Recommendation

**Worth building.** The guide calls this the single largest unmodeled lever,
and unlike Gap 2 below, it has a clean mechanical description (a tax-cost
allocation choice) with no structural blind spot in the underlying engine —
the Monte Carlo location-modeling limitation that bounds Gap 2 does not apply
here, since this changes deterministic cash-flow mechanics the MC vectorized
engine already consumes as planned bucket withdrawals. Recommend prioritizing
this over Gap 2.

---

## Gap 2: Asset-Location-Aware Conversion

### What the guide asks for

§4 Variable 6: convert equity-heavy (high-expected-growth) sleeves first,
leaving fixed income in Traditional accounts, so the highest-growth assets
end up in the Roth's tax-free shield.

### How sleeve-level selection would enter conversion

Today, `plan_roth_conversion` (`planning_engines.py:1454+`) sizes a
**dollar** conversion amount against bracket/IRMAA/balance constraints; it
has no concept of which holdings inside the pre-tax account get moved. Making
it asset-location-aware would require:

1. Per-account holdings-level expected-return data reaching the conversion
   function — today, per-account return differences enter the engine (per
   `_account_return_tilt`, read while researching Gap 1) as a **constant
   per-bucket offset**, not as identified individual sleeves with names/asset
   classes.
2. A selection rule (e.g. "convert the account/sleeve with the highest
   `_account_return_tilt` first") ranking which pre-tax holdings become the
   converted dollars, distinct from which pre-tax ACCOUNT the dollars come
   from (today's engine already supports multi-account pre-tax selection
   order; it's the sleeve-within-account level that's missing).
3. A post-conversion re-balancing question the guide doesn't address: if the
   highest-growth sleeve is converted out of the pre-tax account, does the
   pre-tax account's remaining allocation drift, or does the model assume
   it's rebalanced back to target? This needs a decision before
   implementation.

### The bounding limitation — this must be disclosed honestly

Per this repo's own memory (`mc-models-location-not-sleeve-variance`): the
Monte Carlo engine models account **location** (which tax bucket a dollar
sits in), not **in-account sleeve variance** — every account within a bucket
takes the same annual market shock. This means a correctly-implemented
sleeve-aware conversion could change which sleeve sits in which account, but
the **success rate** — the workbook's primary risk metric — would not move
in response, because the MC engine cannot see sleeve-level composition
differences within a bucket. The deterministic terminal-NW/lifetime-tax
figures WOULD move (those are computed from actual per-account expected
returns), but the risk-adjusted headline number would not reflect the
feature's supposed benefit. A build of this feature that doesn't also
disclose this limitation would repeat the exact pattern the P4 Monte Carlo
disclosure (referenced in Step 8.2) exists to prevent.

### Files touched (estimate)

- `src/planning_engines.py` — sleeve-selection logic inside
  `plan_roth_conversion`/`apply_roth_conversion`
- Holdings-level data plumbing — likely `src/data_io.py`'s account-registry
  parsing, to expose per-holding expected return at the point conversion
  selection happens (currently only reaches the engine as a pre-aggregated
  per-account tilt)
- `reference_data/schema.csv`, frontend control, workbook disclosure (same
  shape as Gap 1)
- A new disclosure specifically about the MC blind spot, distinct from the
  existing P4 note (P4 already covers allocation de-risking generally; this
  would need its own line for conversion-driven sleeve placement)

### Test strategy

Unit test that sleeve selection prefers the highest-tilt holding; an
integration test confirming the deterministic terminal-NW figure moves when
sleeve-aware selection is on vs. off (proving the feature does something);
an explicit test asserting the MC success rate is UNCHANGED between the two
modes (proving the disclosed limitation is real and enforced, not just
narrated) — this last test is the important one and should be written
first, since a successful implementation that quietly makes the MC success
rate move as if it could see sleeve variance would be a silent modeling bug
much worse than the feature not existing.

### Recommendation

**Build only if the deterministic (non-MC) terminal-NW improvement alone
justifies the engineering cost.** The feature cannot honestly claim a
success-rate improvement given the location-not-sleeve-variance limitation
in the current MC engine, and that limitation is a large enough piece of
infrastructure (rewriting the MC engine to model sleeve-level variance
within a bucket) that fixing it is its own project, not a Roth-conversion
feature. Recommend **not building this now**; revisit if/when the MC engine
itself gains sleeve-level variance modeling, at which point this feature's
value proposition changes materially. A design that concludes "don't build
this" is a valid outcome, per the task brief's own framing.

---

## Summary

| Gap | Worth building now? | Primary reason |
|---|---|---|
| Conversion tax payment source | **Yes** | Clean mechanical change, no MC blind spot, guide's own "Critical Multiplier" |
| Asset-location-aware conversion | **No, not yet** | Bounded by the MC engine's location-not-sleeve-variance limitation; the feature's headline benefit (success rate) can't show up until that's fixed separately |
