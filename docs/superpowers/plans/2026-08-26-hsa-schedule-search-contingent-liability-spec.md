# HSA Schedule Search & Contingent-Liability Awareness — Spec

Next increment after PR #66 (contingent-liability spending draws the HSA
first). **Spec/research only — no code in this document.**

PR #66 deliberately left one thing open: under `hsa_withdrawal_mode='optimize'`
the contingent-liability draw is suppressed, on the reasoning that CL need
belongs *inside* the schedule decision rather than bolted on after it. That
PR's docs record a hook for it — `score_year` already receives a projection
row carrying Phase 0's `spend_by_tier`, so "the signal needs no new plumbing."

**This spec's main finding is that the hook is real but the motivation behind
it is weaker than PR #66 stated, and the naive integration would fight the
tax model rather than help it.** That claim was mine, made before reading
`score_year`; the research below is what it looks like once actually checked.
Recording it here so nobody implements the confident version.

## What was verified

### 1. `score_year` prices tax efficiency, not spending purpose

`src/hsa_schedule.py:318`. The score of drawing `amount` in a year is:

```
(displacement + irmaa_cliff) * pv_factor
```

* **displacement** = `amount × effective_marginal_rate` (× a compression
  premium for Single/QSS filings) — the tax avoided on the alternative
  dollar the HSA draw displaces.
* **cliff** = the IRMAA tier step the draw avoids crossing.
* **pv_factor** = shared `roth_tax_discount_rate` discounting.

Nothing here asks what the money is *spent on*. And that is defensible in
this model: the HSA draw's tax-free-out treatment does not vary by year, so
"which year to draw" genuinely is a pure question of which taxable dollar is
displaced.

### 2. A contingent-liability year is a LOW marginal-rate year, not a high one

`deterministic_engine.py:1876`:

```python
medical_expense_yr = wellness_premium_yr + wellness_detail_budget_yr + wellness_shock_yr + ltc_prem_yr
medical_ded = max(0.0, medical_expense_yr - 0.075 * max(0.0, agi))
```

Both contingent-liability components already generate an itemized medical
deduction above the 7.5%-of-AGI floor. So a big LTC/shock year has *lower*
taxable income and, other things equal, a *lower* `effective_marginal_rate`
— which makes `score_year`'s displacement term **smaller**, not larger.

**Consequence:** adding a positive "there is contingent-liability spend this
year" term to `score_year` would push draws toward exactly the years the tax
model has already priced as the least valuable ones to draw in. The two
signals point in opposite directions, and the tax one is the one with an
actual mechanism behind it. A naive implementation of PR #66's suggested
hook would therefore make schedules worse, not better, while looking
principled.

### 3. The real gap is per-year qualified-expense capacity, and it is
pre-existing

The genuine reason a planner wants HSA dollars drawn in a medical year is
that a draw is tax-free *only* against qualified expenses (pre-65; after 65
a non-qualified draw is ordinary income without the 20% penalty). That is a
**per-year capacity constraint**.

This model does not represent it. `hsa_available_to_draw`
(`planning_engines.py:915`) bounds a draw by three things — balances, the HSA
liquidity-reserve floor, and `c['hsa_expense_bank']`. That bank is a **single
lifetime scalar**, parsed once (`data_io.py:2309`) and defaulting to `None`
meaning *unlimited*:

> "A bank of None means unlimited, which is the default: most households have
> far more unreimbursed receipts than they realize, and the constraint only
> binds once someone actually enters a figure."

So in this build, a tax-free HSA draw is permitted in a year with no
qualified expense at all, bounded only by a lifetime figure most households
leave blank. **The per-year tax-free-capacity question the CL-awareness idea
was really reaching for is not modeled anywhere** — and that gap predates
PR #66 and is independent of it.

### 4. The search is still unwired, for a structural reason

`hsa_schedule.py`'s module docstring: `rerun_optimizer`/`build_schedule` are
never called from the projection pipeline, because they need full per-year
projection rows for tax context (`score_year`'s `row`), which only exist
*after* a projection runs — and that projection is what would consume the
schedule. Wiring needs a real two-pass sequence (baseline run → build
schedule → real run). `generate_default_schedule` is a static level-draw
placeholder, explicitly "NOT that search algorithm."

`score_year` also carries its own documented gap: the discount term prices
impatience but never credits the tax-free compounding a *retained* dollar
earns, so scoring equal nominal amounts across years front-loads the
schedule. The docstring measures it — a joint 2028 year at 22% scoring
~1939.65 against a survivor 2048 year at 32% scoring ~880.75 for the same
fixed amount, "a 2.2x gap in the wrong direction." The caller must pass each
year's actual grown amount.

## Options

**Option A — Wire the two-pass search; add no CL term** (recommended).
Deliver what is actually missing and well-founded: make `optimize` mode run
a real search instead of a static level-draw placeholder. Scope: a baseline
projection for tax context, `build_schedule`/`rerun_optimizer`, then the
real projection consuming the result; plus honoring `score_year`'s
grown-amount contract, since passing constant nominal amounts is a known
front-loading defect with a measured magnitude. CL need enters only through
the tax context it already produces (the medical deduction moves the
marginal rate, and `score_year` reads that) — which is the *correct*
mechanism, and is already wired.

**Option B — Model per-year qualified-expense capacity.** Replace the
lifetime `hsa_expense_bank` scalar with a per-year qualified-expense figure
(which `medical_expense_yr` already computes), bounding tax-free draws
year-by-year. This is the change that would make CL-awareness genuinely
load-bearing, and it is the honest version of PR #66's intent. But it is a
schema + `data_io` + engine change that would move numbers for any household
that currently draws HSA tax-free in a low-medical year — potentially many —
and it interacts with the post-65 rule (where non-qualified draws become
merely taxable, not penalized). Larger and riskier than Option A; deserves
its own increment and its own blast-radius analysis.

**Option C — Add a CL term to `score_year`.** What PR #66 suggested. **Not
recommended**, per finding 2: it double-counts a signal the medical
deduction already transmits, and transmits it with the wrong sign.

## Recommendation

**Option A**, and explicitly drop the "CL need becomes a scoring input" idea
from the roadmap in favor of Option B as the real successor. Concretely:

1. Correct the note PR #66 left in `OPTIMIZATION_REFACTOR_STATUS.md` and in
   the 2026-08-26 design doc, both of which currently point a future
   implementer at Option C. Leaving an incorrect hook documented is worse
   than leaving nothing.
2. Wire the two-pass sequence for `optimize` mode, with a feature gate so a
   failed/degenerate search falls back to `generate_default_schedule` rather
   than producing an unfunded plan.
3. Honor `score_year`'s grown-amount contract; add a regression pinning the
   H3.5(a) property its docstring names — the optimizer must beat
   `smooth_window` by weighting survivor years — since that is precisely
   what a constant-nominal caller silently fails.
4. Blast radius to establish before implementing: `optimize` **is** reachable
   (`data_io.py:1274`), so unlike the 2026-08-19 changelog's stale claim this
   is not a zero-household change. The frozen fixture uses `smooth_window`,
   so golden-master pins should not move — to be confirmed, not assumed.

## Open questions

1. **Two-pass convergence.** The baseline run's tax context differs from the
   final run's (the schedule changes AGI, which changes marginal rates,
   which would change the schedule). Is one pass enough, or does this need
   iteration to a fixed point — and if one pass, what bounds the error? The
   Roth optimizer faces the same shape of problem; worth checking how it
   resolves this before inventing a second answer.
2. **Cost.** A baseline projection per build is real work, and the Phase 1
   items 4-6 lesson in `OPTIMIZATION_REFACTOR_STATUS.md` is that an 81×
   `monte_carlo()` sweep caused genuine CI timeouts. Measure before wiring,
   and run an `-m slow` pass.
3. **Does Option B belong first?** If per-year capacity is the real
   constraint, a search built without it may optimize against a model that
   permits draws it shouldn't. Sequencing A→B means A's schedules get
   re-derived once B lands. Worth deciding deliberately rather than by
   default.
