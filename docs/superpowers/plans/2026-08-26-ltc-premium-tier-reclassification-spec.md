# Reclassify `ltc_prem_yr` Out of `contingent_liability` Into `essential` — Spec

Next increment after the HSA expense-bank accumulation/enforcement work.
**Spec/research only — no code in this document.**

Named in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s "Not done" list:

> **Reclassifying `ltc_prem_yr`** out of `contingent_liability` into
> `essential` — it is a scheduled premium, not a shock, and is tiered as
> contingent only because it *hedges* a contingent liability. Taxonomy
> correctness only; would shift `spend_by_tier` percentages that the Phase 2
> dashboard metrics read, so it needs its own regression coverage.

## What's wrong today

`contingent_liability` (`spending_budget_resolver.py:37`) is defined as
"irregular, shock-driven costs" — LTC, a medical emergency, a home
modification. `deterministic_engine.py:1774` puts two very different things
in it:

```python
_tier_add('contingent_liability', ltc_prem_yr + wellness_shock_yr)
```

- `wellness_shock_yr` — a sampled, irregular LTC/major-medical cost shock.
  Genuinely shock-driven; belongs in this tier by the tier's own definition.
- `ltc_prem_yr` — an LTC **insurance premium**. A scheduled, recurring,
  known-in-advance cost exactly like a mortgage payment or a Medicare
  premium (both of which are tiered `essential`, `deterministic_engine.py:
  1765`/wellness-essential split above). It is in `contingent_liability`
  only because it *hedges* a contingent liability, not because paying it is
  itself contingent — the same logic would put homeowner's insurance
  premiums in a "home damage" tier instead of `essential`, which the
  taxonomy does not do (`ho_insurance` is an explicit `essential`
  `default_category_id`, `spending_budget_resolver.py:59`).

This is a taxonomy-correctness defect, not a dollar-total defect: both
consumers of `spend_by_tier` are explicitly documented as purely additive/
reporting-layer computations that never change `total_spend_need`,
withdrawals, or taxes (`deterministic_engine.py:1742-1743`,
`planning_engines.py:4578-4582`). **No golden-master pin should move.**

## Where it actually matters: cut-priority treatment, not just labeling

`spend_by_tier` has two consumers, and both treat `contingent_liability`
specially — not just for display:

1. **`spending_priority_cut_check`** (`planning_engines.py:4562`) —
   deterministic-engine reporting. Explicitly excludes
   `contingent_liability` from `total_cuttable`
   (`planning_engines.py:4610`): those dollars are never counted as
   available to absorb a cut, so they're neither inflated nor deflated by
   the tier-priority redistribution. `ltc_prem_yr` dollars currently get
   this treatment.
2. **`_mc_tier_priority_retained`**-style redistribution (vectorized MC,
   `planning_engines.py:3995`) — same exclusion, vectorized. `cuttable =
   [t for t in ('discretionary', 'important', 'essential') if t in
   tier_scaled]` (`planning_engines.py:4010`) — note `essential` **is**
   cuttable here, just last in priority order (`cut_priority=3`,
   `spending_budget_resolver.py:52`). `contingent_liability` isn't lower
   priority than essential — it is outside the cuttable pool entirely,
   receiving the old flat/uniform cut fraction instead of benefiting from
   priority protection.

So moving `ltc_prem_yr` into `essential` doesn't just relabel a dashboard
percentage — it moves those dollars from "always cut at the flat uniform
rate" into "cut last, after discretionary and important are exhausted."
That is the **correct** behavior for a premium (protect it like other fixed
costs), and is a second, independent reason this is a real behavior change
worth its own regression coverage, not a cosmetic rename.

## Blast radius

- `row['spend_by_tier']['essential']` increases, `row['spend_by_tier']
  ['contingent_liability']` decreases (by `ltc_prem_yr`) for every household
  with a nonzero `ltc_annual_prem` in a year LTC coverage is active. A
  household with no LTC premium configured is bit-identical.
- `contingent_liability` does not disappear as a tier — `wellness_shock_yr`
  still populates it in shock years.
- MC cut-statistics reporting (`test_mc_cut_statistics_regression.py`,
  `test_mc_tier_priority_cut_regression.py`) and the Phase 2 dashboard's
  essential-shortfall/cut-attribution metrics
  (`test_spending_priority_cut_check_regression.py`,
  `test_essential_fully_funded_probability_regression.py`) will shift for
  any scenario that samples a cut in a year with an LTC premium — because
  those dollars now participate in priority redistribution instead of being
  excluded. **No total dollar/success-rate metric changes** — both
  consumers guarantee the combined total across tiers is unchanged bit-for-
  bit (`planning_engines.py:4001-4003`); only per-tier attribution moves.
- `test_spending_tier_taxonomy.py` and
  `test_contingent_liability_hsa_funding_regression.py` reference the
  current classification directly and need review — the latter's HSA
  funding logic (`fund_contingent_liability_from_hsa`) reads
  `ltc_prem_yr`/`wellness_shock_yr` as explicit function arguments, not via
  `spend_by_tier`, so **HSA funding behavior (Priority 1b, and the new bank
  enforcement) is unaffected** — this is purely the tier-attribution
  registry, a separate code path.
- Golden-master pins (`PINNED_TERMINAL_NW`/`PINNED_LIFETIME_TAX`): not
  expected to move — neither consumer changes a dollar total. Should be
  confirmed empirically (run the golden-master regen script's diff-only
  check) rather than assumed, the same discipline applied to every prior
  change in this refactor.

## Option

**Single option, no real alternative design**: move the `ltc_prem_yr` term
from the `_tier_add('contingent_liability', ...)` call to the existing
`_tier_add('essential', ...)` call at `deterministic_engine.py:1765`
(alongside `mort_yr`, `re_tax_yr`, etc.):

```python
_tier_add('essential', mort_yr + re_tax_yr + rent_yr + housing_operating_yr
           + heloc_interest_yr + heloc_repayment_principal_yr + ltc_prem_yr)
...
_tier_add('contingent_liability', wellness_shock_yr)
```

No config, no new field, no gating — this is a straightforward correction
in the same spirit as the double-dip fix (PR #68): the taxonomy currently
encodes the wrong rule, and there is a clear right answer. Unlike the
double-dip fix, this one is not expected to move golden-master pins, since
both consumers are dollar-total-preserving by construction — that should
lower the review bar relative to a pin-moving change, but the empirical
check should still run before claiming it, not be assumed from the
docstrings alone.

## Steps

1. Make the one-line move in `deterministic_engine.py`.
2. Run the golden-master regen script's check mode (or `python -m
   tests.test_frozen_sample_plan_golden_master_regression`) to confirm pins
   are bit-identical, per the "identical values mean the pin was wrong, not
   the engine" discipline — but here identical is the expected, correct
   outcome, not a red flag.
3. Update/extend regression coverage:
   - `test_spending_tier_taxonomy.py`: assert `ltc_prem_yr` classifies as
     `essential`, not `contingent_liability`.
   - A new or extended test asserting a household with a nonzero LTC
     premium and a sampled MC cut has those premium dollars **excluded**
     from `contingent_liability`'s flat-cut share and **included** in
     `essential`'s last-priority-protected share — the actual behavior
     change, not just the label.
   - Sweep `test_mc_cut_statistics_regression.py`,
     `test_mc_tier_priority_cut_regression.py`,
     `test_spending_priority_cut_check_regression.py`,
     `test_essential_fully_funded_probability_regression.py` for any
     hardcoded tier-dollar expectations that assumed the old
     classification; update with the reason recorded (mirroring how this
     refactor's other pin/attribution moves are documented).
4. No `tools/regen_golden_master.py regen` run expected (no pin move) — but
   only skip it after step 2's empirical check confirms that, not on the
   docstring's say-so.

## Open questions

1. **Does any dashboard sheet hardcode "LTC premium" as belonging to a
   "Contingent Liability" display bucket** (as opposed to reading
   `spend_by_tier` live)? Grep `sheets_projection_*.py` for `ltc_prem_yr`
   alongside `contingent_liability`/tier-label strings before assuming the
   reporting layer picks this up automatically — the deterministic engine's
   own `row['ltc_prem_yr']` field is unchanged and several sheets read it
   directly rather than through `spend_by_tier`
   (`sheets_projection_cashflow.py`), which is correct and unaffected, but
   worth confirming nothing separately duplicates the old tier assumption.
2. **Should the wellness-shock scaling block above it also be revisited?**
   `_wellness_essential_raw`/`wellness_other_yr` already split wellness
   spend into essential vs. important by category; this change treats
   `ltc_prem_yr` as a standalone essential addend rather than folding it
   into that split, which is correct since `ltc_prem_yr` isn't part of the
   wellness-detail-budget raw components it scales — just confirming the
   two blocks don't need to interact.
