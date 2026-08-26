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

## Follow-up research (resolves all three open questions below)

Done before implementing. Three findings, two of which correct this
document's own earlier claims.

### R1. The house pattern is candidate scoring, not a two-pass approximation

Open question 1 asked how the Roth optimizer resolves the
schedule-depends-on-rows-depends-on-schedule circularity, "before inventing
a second answer." It does not use a two-pass approximation at all.
`optimize_roth_conversion_strategy` (`planning_engines.py:2570`) enumerates
~10-12 **named, parameterized** candidates
(`_roth_strategy_candidate_specs`) and runs a **full `run_scenario` per
candidate**, scoring each on its own projection:

```python
for spec in _roth_strategy_candidate_specs(c):
    c2, rows = run_scenario(base, overrides)   # full projection per candidate
    candidates.append({**spec, **_roth_strategy_metrics(c2, rows)})
candidates.sort(...); best = candidates[0]
```

Every candidate is evaluated on a projection that already has that
candidate's policy in effect, so each score is self-consistent by
construction. **This supersedes the two-pass framing in Option A below**,
which would have scored a schedule against a tax context produced *without*
it.

> **Correction, found during implementation.** This section originally
> concluded "there is no convergence problem." That is half right, and the
> half that is wrong matters. Candidate *scoring* is self-consistent, so an
> adopted schedule is never worse than the incumbent. But candidate
> *generation* still reads the incumbent's rows for tax context, so a single
> round does **not** reach a fixed point: measured on the frozen fixture, a
> re-run against an adopted proposal beat it again by ~1.7% (29,170 →
> 29,680). This was caught by the convergence regression written for the
> implementation, not by inspection.
>
> The fix is bounded iteration, which is safe precisely *because* of the
> scoring property: a round is adopted only when it scores strictly higher,
> so the sequence is monotonic and cannot end below where it started. The
> shipped search iterates up to `_SCHEDULE_SEARCH_MAX_ROUNDS` (4), stopping
> early once a round fails to add `_SCHEDULE_SEARCH_MIN_GAIN` ($1). On the
> frozen fixture it settles in 4 rounds at 29,698 and a subsequent run stops
> after one round having adopted nothing.

### R2. `score_year`'s grown-amount contract is already honored

Recommendation step 3 below ("honor `score_year`'s grown-amount contract")
is **already done** and should not be re-implemented. `schedule_score`
(`hsa_schedule.py:788`) documents and implements it explicitly — it tracks
the balance grow-then-draw and passes each year's *actual grown* amount,
naming this as what closes `score_year`'s documented front-loading gap.
`build_schedule` likewise scores "the increment GROWN to that year, so the
comparison is like-for-like." The 2.2x front-loading defect is a hazard for
a *new* caller, not a live defect in the existing machinery.

So the existing search machinery is more complete than this spec assumed:
`schedule_score`, `build_schedule` (a weight-based allocator with an
anti-back-loading mortality gradient), and `rerun_optimizer` all exist and
are coherent. **What is missing is purely the wiring** — nothing calls them
from the projection pipeline.

### R3. Cost is a non-issue

Open question 2 worried about the per-build cost, citing the 81×
`monte_carlo()` CI-timeout lesson. Measured on the frozen fixture: a
**full-horizon `project()` is ~20-60ms** (31 rows). The 81× incident was
`monte_carlo()`, which is orders of magnitude more expensive; `project()`
is not in that class. The Roth optimizer already spends ~12 full scenarios
per build on the same basis. One or two extra projections for the HSA
schedule is negligible, and no special performance design is needed —
though an `-m slow` pass is still owed before calling it verified.

## Options

**Option A — Wire the search as a scored candidate; add no CL term**
(recommended). Make `optimize` mode run a real search instead of the static
level-draw placeholder. Per R1, structure it the way this codebase already
resolves this exact circularity: build a candidate schedule from a baseline
projection, then **score it against the existing default/level schedule by
running a full scenario for each** and taking the better. That makes the
result never worse than today's placeholder by construction, which is a
stronger guarantee than a one-shot two-pass sequence gives, and it reuses
the established pattern rather than inventing a second one. Per R2, the
grown-amount handling is already correct and needs no work. CL need enters
only through the tax context it already produces (the medical deduction
moves the marginal rate, and `score_year` reads that) — the *correct*
mechanism, already wired.

**Option B — Model per-year qualified-expense capacity.** ⚠️ **Superseded —
do not build as written.** Follow-up research
(`2026-08-26-hsa-expense-bank-and-double-dip-spec.md`) established that a
*cumulative* bank is the correct tax model, not a defect: a qualified
expense can justify a tax-free withdrawal at any later date, which is the
basis of the "shoebox" strategy. A per-year cap would model the wrong rule.
That research also found the real defect underneath — the same medical
dollar can currently take both a tax-free HSA reimbursement and a Schedule A
deduction, because nothing nets HSA draws out of `medical_expense_yr`. See
that spec. Original text follows for the record:

Replace the
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
2. Wire `optimize` mode as a **scored candidate comparison** (per R1), not a
   one-shot two-pass: baseline projection → `build_schedule` → score that
   schedule and the existing default/level schedule by running a full
   scenario for each → keep the better. A degenerate or failing search then
   loses to the placeholder on score rather than needing a separate feature
   gate, so the result is never worse than today's behavior by
   construction.
3. ~~Honor `score_year`'s grown-amount contract~~ — **already done**, see R2.
   Still add a regression pinning the H3.5(a) property `score_year`'s
   docstring names (the optimizer must beat `smooth_window` by weighting
   survivor years), because that property is currently asserted nowhere and
   is what a future constant-nominal caller would silently break.
4. Blast radius to establish before implementing: `optimize` **is** reachable
   (`data_io.py:1274`), so unlike the 2026-08-19 changelog's stale claim this
   is not a zero-household change. The frozen fixture uses `smooth_window`,
   so golden-master pins should not move — to be confirmed, not assumed.

## Open questions

1. ~~**Two-pass convergence.**~~ **Resolved by R1** — the house pattern
   (candidate + full scenario per candidate) makes each score
   self-consistent, so there is no fixed point to chase.
2. ~~**Cost.**~~ **Resolved by R3** — `project()` is ~20-60ms; the 81×
   incident was `monte_carlo()`, a different class of cost. An `-m slow`
   pass is still owed, but no performance design is needed.
3. **Does Option B belong first?** Still open, but **less pressing under the
   R1 architecture**: a schedule built against a model that permits
   over-generous tax-free draws is still *scored* on its own real
   projection and must beat the placeholder to be adopted, so the failure
   mode is a mediocre schedule that loses the comparison, not a silently
   wrong one that ships. Sequencing A→B still means A's schedules get
   re-derived once B lands. Worth deciding deliberately, but it no longer
   blocks A.
