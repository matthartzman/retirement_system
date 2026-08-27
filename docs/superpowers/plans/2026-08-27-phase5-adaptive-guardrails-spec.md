# Phase 5 — Adaptive Policy Guardrails — Spec

Next item in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s "Not done"
list, after Phase 4 (LCV feasibility gate and scoring, PR #76, awaiting
review). Phase 6 (expanded stress scenarios) remains after this one.

**Spec/research only — no code in this document.** Mechanical grounding
delegated to an Explore subagent; the design analysis below is original.

## This phase is a different shape than Phases 3 and 4

Phases 3 and 4's spec's both found the same reassuring pattern: every
dollar figure a reporting-only "Option A" slice would need already
existed somewhere in the codebase, just uncombined or unconsumed. **Phase
5 does not have that luxury.** The research pass for this spec confirms:
no year-by-year, state-contingent spending-adjustment mechanism exists
anywhere in this codebase, live or dead. "Adaptive policy guardrails" — a
term of art in retirement planning (Guyton-Klinger decision rules, or
similar "spend more after good years, cut back after bad ones" dynamic
withdrawal strategies) as against a single static withdrawal rate — would
be **genuinely new sequential decision logic**, not a combination of
existing fields. Even a reporting-only slice here costs meaningfully more
than Phases 3-4's did, and this spec says so plainly rather than
understating it to fit the prior pattern.

## What exists today (verified against the code)

### The one visible "guardrail" reference is a static, illustrative placeholder

`workbook_builder.py:451-461` builds a "sensitivity levers" table; one row
is literally labeled `'Dynamic spending guardrail'`:

```python
('Success', 'Dynamic spending guardrail', 'Spending Categories', 10, '% cut in bad markets',
 '=$B$8*(D{r}/100)*$B$10*0.25', '=MIN(0.30,MAX(-0.30,D{r}*0.006))',
 'Flexing discretionary spending after poor markets is often high impact.')
```

This is an Excel formula string estimating a hypothetical Δ-terminal-wealth
and Δ-success-rate as a linear function of one static input cell (default
`10`, "% cut in bad markets") — the same shape as the table's other nine
rows (e.g. "Work longer / retire later"). It reads no live withdrawal,
portfolio-performance, or year-index data from the actual projection.
**Nothing computes this row's inputs from a real simulated policy** — it's
a planner's back-of-envelope estimate, not a modeled feature.

### Every existing spending-cut mechanism is a single static scalar, applied uniformly across an entire path

- `spend_cut_frac` (`planning_engines.py:4303-4342`): "per-path uniform
  reduction (0..1)" per its own docstring — `cut_mult` is fixed once per
  path (line 4342) and applied identically to every year of that path.
- `_mc_required_cut_distribution` (`planning_engines.py:4878-4936`):
  binary-searches "the smallest **uniform** spending cut" per failing
  path — one scalar, not a year-by-year rule.
- `sustainable_spending_solve` (`planning_engines.py:5107+`): bisects "a
  single **uniform** cut" against the overall batch success rate for each
  of several confidence targets (95/85/75%) — again one number applied
  across the whole plan.
- `spending_priority_cut_check`/`essential_discretionary_floor_check`
  (`planning_engines.py:4951-5019`): take an already-solved uniform
  `cut_frac` and redistribute that FIXED dollar amount across tiers for
  reporting — explicitly "never changes which accounts fund withdrawals"
  (its own comment). No re-evaluation per year.

**None of these re-evaluate spending within a single path/year as
portfolio performance unfolds.** A "cut" today is a single number, decided
once, before the year loop runs — the opposite of what an adaptive
guardrail is.

### The deterministic engine has no balance-vs-threshold spend-adjustment logic

The only "floor" concept in the withdrawal machinery is
`liquidity_reserve_floor`/`spend_floor_base` (`planning_engines.py:1425`,
`hsa_schedule.py:916,939`), which gates **which account bucket** may be
drawn from this year — it does not change **how much** the household
spends. No code anywhere checks "is the portfolio down X% from where it
started" and adjusts the year's spending target in response.

### `hsa_schedule.py`'s bounded-iteration search is a different shape, not reusable for this

`build_schedule`/`rerun_optimizer` (the pattern that wired the HSA
schedule search into builds, see the status doc's earlier entry) solves a
**whole schedule at once** from a closed-form gradient, then re-solves
from scratch when inputs change. It is not a sequential process that
reacts to intermediate realized state year by year — structurally the
wrong shape for a guardrail rule, which is inherently sequential (each
year's decision depends on that path's own realized state through that
year). Its "respect locked/pinned values across a bounded re-solve"
convention may still be a useful pattern to borrow, but the core mechanism
doesn't transfer.

### No precedent anywhere for a later year's spend depending on an earlier year's realized portfolio value

The MC vectorized engine's survivor-bucket logic (Phase 1 items 4-6) is
the only place a later year's flows depend on an earlier, path-specific
event — but that event is an exogenously *sampled* mortality date, not a
portfolio-performance outcome. Ordinary balance depletion (accounts
running low, forcing smaller draws) is not the same thing as a guardrail
*rule* — a rule is an explicit policy ("if down >X%, cut Y%"), not an
emergent consequence of running out of money.

## What "adaptive policy guardrails" most plausibly means

The strongest, most standard reading in retirement-planning practice is a
**Guyton-Klinger-style decision-rule framework**: a small set of rules
evaluated once per year, per path, comparing that year's realized state
(typically the current withdrawal rate implied by portfolio value) against
bands, and adjusting the *next* year's spending target — e.g. a
"capital-preservation rule" (cut spending if the effective withdrawal rate
rises too far above the initial rate) and a "prosperity rule" (raise
spending if it falls too far below). This is explicitly what "adaptive"
distinguishes from "static" in the withdrawal-strategy literature, and
matches the sole placeholder's own label ("% cut in bad markets").

## Options

**Option A — Reporting-only shadow simulation of ONE guardrail rule
(recommended scope, with a caveat).** Build a genuinely new, sequential
year-by-year evaluation — mirroring the "parallel reconstruction" pattern
already proven in `_mc_scalar_tier_bucket_reconstruction` (a shadow
tracker that reads real per-path state without touching the real
withdrawal decision) — that computes what a specific, named guardrail rule
(e.g. a simplified Guyton-Klinger capital-preservation/prosperity pair)
WOULD have produced for that path, reported as a new metric (e.g.
`guardrail_adjusted_spend_real`, `probability_guardrail_triggered`)
alongside the existing static-cut figures. Never changes the real
withdrawal cascade, `unfunded`, `liquid`, `total`, `path_success`, or
`success_rate`. **The caveat**: unlike Phases 3-4's Option A, this is
real new sequential-simulation code in both MC engines (the scalar engine
already reruns `project()` per path so has less new machinery to build;
the vectorized engine needs an actual per-year loop with cross-year
state — the exact kind of order-dependent, per-path work vectorization
exists to avoid, the same complexity class the tier-priority-redirection
spec flagged for its own Option A).

**Option B — Wire the guardrail into the real withdrawal decision.** Make
`spend_cut_frac`-equivalent logic genuinely dynamic: each year's spending
target depends on that path's own realized portfolio value through that
year, not a single pre-solved scalar. This is the literal fulfillment of
"adaptive," but changes real simulated outcomes for every MC-based
feature that currently assumes a static cut — a materially larger change
than anything in this refactor to date, including the tier-priority
redirection work, and requires the same kind of real financial-planning
sign-off that increment needed (twice) before any code.

**Option C — Defer.** Given the total absence of scaffolding (unlike
Phases 3-4, this is not "generalize what exists" but "build the first
sequential decision-rule engine this codebase has ever had"), and that
even Option A here is a bigger, riskier undertaking than any single
increment landed so far in this refactor, treat Phase 5 as its own
dedicated project rather than a same-shaped follow-on — do the product
design work (which specific rule set? what bands? configurable per
household or fixed?) as a standalone conversation before committing to
Option A's engineering cost.

## Recommendation

Given the pattern this refactor has followed twice already
(tier-priority redirection, and implicitly Phase 3/4's own recommendations)
of preferring the smallest safe slice, **Option A** is the directionally
right choice — but this spec explicitly recommends pausing for a
product/financial-planning decision on **the exact rule** (Open question 1
below) before writing any code, more insistently than Phase 3/4's specs
did, because there is no existing implementation to anchor the formula
the way `_roth_strategy_metrics`/`gross_cash_flow_yr` anchored Phase 3, or
`essential_fully_funded_probability` anchors Phase 4's feasibility gate.
Guessing at Guyton-Klinger's specific parameters (initial rate, band
widths, cut/raise percentages) without that sign-off risks building
"a" guardrail nobody asked for rather than the one intended.

## Open questions

1. **Which specific guardrail rule?** Full Guyton-Klinger (four rules:
   capital-preservation, prosperity, withdrawal, portfolio-management) is
   the standard reference but has real parameters (typically ±20% bands,
   10%/increase and matching decrease) that are genuine financial-planning
   choices, not engineering defaults. A simplified single-rule version
   ("cut spending by X% if portfolio value falls more than Y% below the
   plan's own trajectory") is a smaller, more tractable first slice — is
   that acceptable, or does "adaptive policy guardrails" require the full
   rule set?
2. **Configurable per household, or a fixed default?** Every other
   discount-rate/threshold config in this refactor (`roth_tax_discount_
   rate`, `mc_success_liquid_floor`) is user-configurable via the CSV
   schema. Should guardrail bands be too, and if so, is that CSV-schema
   wiring in scope for this increment or a explicit follow-on (the same
   "backend field ready, no CSV/UI wiring yet" pattern several earlier
   Phase 2 metrics used)?
3. **Scalar-engine parity from the start, or deferred?** The tier-priority
   redirection increment discovered mid-implementation that the scalar
   engine had no independent withdrawal mechanism and needed a whole new
   parallel-reconstruction approach — the same discovery would very likely
   repeat here, since a guardrail is inherently a withdrawal-decision
   feature. Should this spec's own Option A budget for that scalar-engine
   cost up front (given it's now a known, documented pattern), rather than
   discovering it again mid-implementation?
4. **What does "triggered" mean for reporting purposes?** A per-path
   count of guardrail-triggered years, a probability across the batch, or
   just the resulting shadow spend trajectory itself (letting the
   consumer compute triggering separately)? Affects what new fields Option
   A actually needs to add.
