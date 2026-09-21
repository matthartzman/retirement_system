# H1/B5 golden-master findings

Ticket #331 B5 (`docs/superpowers/plans/2026-09-19-optimizers-modules-housing-master-plan.md`
§4 H1, and `docs/superpowers/specs/2026-09-19-housing-optimizer-anchor-flow-and-timing-design.md`
§6.6) calls for regenerating the housing optimizer's golden-master fixture(s)
after the valuation-as-of-move-year fix lands, hand-verifying one delta
before batch-regenerating the rest.

## What "golden master" turned out to mean here

There is no separate housing-optimizer golden-master JSON fixture (nothing
analogous to `tests/fixtures/golden_master_engine_cases.json` or the
`PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX` pins `tools/regen_golden_master.py`
manages). Two things were checked to establish this rather than assume it:

1. **The frozen sample plan carries no housing step.**
   `tests/fixtures/sample_plan_frozen/client_data.csv` has no `Housing`
   section rows at all, so `plan_variant`/`housing_comparison` never touch it
   for that fixture. `py tools/regen_golden_master.py measure` confirms this
   directly: `terminal_nw`/`lifetime_tax` delta is `+0.00` against the
   pinned values with this branch's changes applied. The engine-level golden
   master (the one `regen_golden_master.py` actually manages) is untouched by
   this PR, and no `regen --reason` run is needed or appropriate.

2. **No housing-optimizer test file pins literal dollar/rank figures
   computed from a future-dated move.** `test_housing_optimizer_integration.py`
   and siblings run the real engine against frozen holdings prices
   (`FROZEN_GOLDEN_MASTER_PRICES`) and a frozen "today", but their
   assertions are structural (acquisition years, key presence, relative
   comparisons) rather than pinned absolute dollar amounts for a
   future-year move. The full existing housing/zip-screen test suite passes
   unmodified except for the handful of unit tests that called
   `_purchase_price_for_location`/`_effective_mortgage_rate`/
   `_estimate_for_location` directly with the OLD (pre-B1) positional
   signature -- those were updated to pass explicit, neutral
   (`home_appr=0.0, inflation_general=0.0`) valuation-timing arguments so
   their existing assertions keep testing tier selection, not escalation
   (escalation itself is covered by the new
   `tests/test_housing_valuation_timing_unit.py`).

## What was hand-verified instead

Since there is no fixture file to regenerate, the plan's "regenerate one
representative fixture, hand-verify its delta against a spreadsheet check of
`(1 + home_appr) ** years_out`, then batch the rest" instruction was
satisfied by:

- `tests/test_housing_valuation_timing_unit.py::test_tier2_est_price_escalates_by_home_appr_over_years_out`
  and `::test_apply_candidate_reads_home_appr_and_inf_from_the_config_not_a_default`
  assert the exact `(1 + home_appr) ** years_out` figure by hand for both the
  `est_price` tier and the full `_apply_candidate` path.
- `tests/test_housing_valuation_timing_unit.py::test_budget_bounds_deflated_once_for_a_future_reference_year`
  hand-computes the deflated bound the same way and confirms a ZIP that would
  have been wrongly excluded by an unadjusted (today's-dollars) budget now
  passes.
- The direction matches the design's stated bias reversal: a future-dated
  candidate's cost basis now grows with `years_out`, so a later move no
  longer buys a today's-priced house for free -- recommendations comparing a
  near move against a far one should shift toward the near move, not away
  from it, consistent with §6.6.

## Conclusion

No golden-master regeneration command was run because there is nothing for
`tools/regen_golden_master.py` to regenerate for this change, and no other
fixture file needed batch-updating. The PR description states the recompute
explicitly per the plan's requirement, even though no fixture diff
accompanies it -- there is no unreviewed-drift risk to call out beyond what
the new unit tests already pin by hand.
