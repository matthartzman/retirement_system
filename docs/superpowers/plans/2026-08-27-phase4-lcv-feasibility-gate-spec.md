# Phase 4 — LCV Feasibility Gate and Scoring — Spec

Next item in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s "Not done"
list, following Phase 3 (tax NPV / ELTR, PR #75). Phases 5-6 (adaptive
policy guardrails, expanded stress scenarios) remain after this one.

**Spec/research only — no code in this document.** Mechanical grounding
delegated to an Explore subagent; the design analysis below is original.

## The scoping problem, again

As with Phase 3, the "Final Optimization Implementation Plan — Revised"
that would have described Phase 4 in detail was never committed to this
repo. All that survives is the status doc's own framing: the refactor
aims at *"replacing terminal-net-worth-only optimization with a Lifetime
Consumption-and-Transfer Value / LCV framing"* (intro) and the "Not done"
line *"LCV feasibility gate and scoring."* LCV = **Lifetime
Consumption-and-Transfer Value** — a term of art in retirement-planning
literature (e.g. Milevsky-style lifetime utility models) meaning a
composite of (a) the present value of what the household actually gets to
*spend* over its lifetime and (b) the present value of what it *leaves
behind* (bequest/transfer), as against optimizing for bequest alone. A
**feasibility gate** conceptually means: before comparing candidates by
their LCV score, first confirm the candidate actually meets the
household's non-negotiable needs — otherwise a strategy that starves
essential spending to inflate its terminal-wealth score could win on LCV
alone, exactly the failure mode "terminal-net-worth-only optimization"
describes.

## What exists today (verified against the code)

### Every dollar-figure ingredient for LCV already exists, in both MC engines

Phase 1-3 of this refactor built exactly the fields an LCV composite would
need, already per-path and percentile-summarized in both
`_mc_vectorized_projection`/`_mc_vectorized_batch` and
`monte_carlo_exact_scalar`:

- **Consumption**: `spend_total_real` / `spend_{tier}_real` (Phase 1) —
  real, plan-start-dollar per-path lifetime spending.
- **Tax** (a lifetime cost, not consumption or transfer):
  `tax_npv`/`effective_lifetime_tax_rate` (Phase 3, this refactor's most
  recent increment).
- **Transfer**: `after_tax_terminal_nw_pct`/`post_tax_inheritance_pct`
  (Phase 2) — after-tax terminal wealth/inheritance, already PV-adjacent
  (a terminal-year dollar figure, not yet discounted to plan-start PV the
  way `tax_npv` is).

No new MC-engine computation is needed to build a composite score from
these — this is squarely a **combination** of existing outputs, unlike
Phase 3 which had to add a genuinely new PV-discounted field
(`gross_cash_flow_yr` was inert; `tax_npv` didn't exist).

### `sustainable_spending_solve` already has a `feasible` boolean — narrowly scoped

`sustainable_spending_solve` (`planning_engines.py:5107-5187`) bisects a
single uniform `spend_cut_frac` to hit each of several target success
rates (default `(0.95, 0.85, 0.75)`), and **already returns
`feasible: bool` per target** — `False` when even the maximum modeled cut
(`cut_cap=0.90`) can't reach that target success rate. This is real,
working feasibility logic — but it answers "can spending be cut enough to
hit a success-rate target," not "does this candidate strategy meet the
household's essential needs," which is the narrower, more defensible
reading of what an LCV feasibility gate should mean.

### The only existing "go/no-go" reporting gate is a flat success-rate threshold

`sheets_stress.py:129-130`: `suc >= 0.85` flags "Plan Funding Success
Rate" (and `>= 0.80` for the CI-low bound) — presumably drives cell
coloring. Line 454 buckets into "strong / moderate / marginal" at the same
threshold family. This is real precedent for a boolean/tiered gate concept
in this codebase, but it gates on the SAME flat success-rate figure
`path_success`/`success_rate` already compute — it has no notion of tiered
essential-vs-discretionary funding, LCV, or transfer value at all.

### Every existing candidate-scoring function is terminal-wealth/tax-only, never consumption-aware

- **Roth conversion optimizer** (`_roth_strategy_metrics`,
  `planning_engines.py:2298+`): a weighted sum of PV'd terminal wealth and
  PV'd lifetime tax (`roth_optimize_terminal_weight`/
  `roth_optimize_tax_weight`), plus legacy/estate-risk terms. No
  consumption term.
- **Social Security claim-age sweep** (`sheets_strategy.py:272-342`):
  `after_tax_terminal_nw + weight * survivor_period_ss_income`, sorted and
  rescaled to a 0-100 `rank_score`. MC `success_rate` is computed per
  candidate but its own comment says explicitly it must NOT feed the
  score (informational only). No consumption term either.
- Asset-allocation optimizers in `optimization.py` (Sharpe/real-loss-aware
  weighting) are a different problem (portfolio construction, not
  candidate-strategy selection) and out of scope here.

So the "terminal-net-worth-only optimization" this refactor set out to
replace is real and current: every actual decision-making scoring function
in this codebase today optimizes principally for terminal wealth (plus a
tax penalty), with lifetime consumption reported nowhere in any of them —
exactly the gap Phase 4's LCV framing names.

### No multi-objective, Pareto, or feasibility-gate framework exists anywhere else

Confirmed again (repo-wide grep, zero hits beyond this status doc's own
self-reference): no `pareto`, `multi-objective`, `feasibility gate`
concept exists in `src/` or `docs/superpowers/plans/*.md`. The only
"feasibility" hit anywhere is `schedule_feasibility`
(`hsa_schedule.py:1199-1231`), an HSA-drawdown-schedule-specific balance
check, unrelated to plan-level feasibility.

## The real design question: reporting a score, or replacing a decision?

Exactly the same shape of question the tier-priority-redirection spec
(2026-08-27) and this refactor's own precedent (PR #64 → later Option B)
have already faced twice:

**Reading A — LCV as a new reporting metric, feasibility as a new
reporting flag.** Compute an `lcv_score` (or similar) per path/percentile
in both MC engines from fields that already exist — e.g. `spend_total_real`
PV'd + terminal transfer PV'd, some household-configurable weighting
between them — and a `feasibility_gate_met: bool` (e.g.
`essential_fully_funded_probability >= <threshold>`, reusing the Phase 2
metric that already exists for exactly this purpose). Neither changes what
any existing optimizer picks. This is Phase 3's Option A shape again:
safe, additive, no decision-logic change.

**Reading B — LCV/feasibility as the actual selection criterion.** Replace
or augment the Roth optimizer's and/or SS claim-age sweep's terminal-wealth-
dominant scoring with an LCV-based one, gated by feasibility (an infeasible
candidate is excluded from ranking entirely, not just scored low). This is
the literal fulfillment of "replacing terminal-net-worth-only
optimization" — but it changes what two already-shipped, tested optimizers
actually recommend to a real household, a materially bigger and more
consequential change than anything Reading A does, and (per the "Not
done" item's own wording — "gate AND scoring," not "gate OR scoring")
plausibly closer to what was originally intended.

## Options

**Option A — Reporting-only LCV/feasibility metrics (recommended scope).**
Add `lcv_score`-family fields (exact formula TBD, see open questions) and
`feasibility_gate_met` to both MC engines' output, following the exact
precedent of every Phase 1-3 metric: reads already-finalized per-path
output, never feeds back into `unfunded`/`liquid`/`total`/`path_success`/
`success_rate`, and does not change what the Roth optimizer or SS
claim-age sweep pick. Smallest, safest slice; matches this refactor's
established incremental discipline.

**Option B — Wire the feasibility gate into existing candidate scoring.**
Add a real gate to `_roth_strategy_metrics` and/or the SS claim-age sweep:
a candidate whose `essential_fully_funded_probability` (or similar) falls
below a threshold is excluded from ranking, or its score is set to
`-infinity`, regardless of how favorable its terminal-wealth/tax numbers
are. Narrower and more defensible than replacing the scoring formula
itself (Option C) — the existing scoring stays as-is, but a bad-for-the-
household winner can no longer surface. Still touches two live, tested,
shipped features.

**Option C — Replace terminal-wealth-dominant scoring with LCV-based
scoring.** The literal reading of "replacing terminal-net-worth-only
optimization with a...LCV framing." Requires deciding real
financial-planning weights (how much does a dollar of lifetime consumption
matter relative to a dollar of bequest — this is a genuine utility-function
design question, not an engineering one) and would change real
recommendations two already-shipped optimizers make today. The biggest,
riskiest option, and the one most likely to need product/financial-planning
sign-off before any code, per this refactor's own repeated precedent of
separating "add a reporting capability" from "change what the plan actually
recommends."

## Recommendation

**Option A first**, exactly as Phase 3 recommended Option A over B/C
there. It closes the largest, safest piece of the gap (LCV and
feasibility become visible/reportable at all, using fields that already
exist) without touching either live optimizer's actual recommendation —
and it produces the concrete artifact (a working feasibility flag and LCV
figure) that would make Option B or C's cost/benefit debate concrete
rather than abstract, the same way Phase 3's reporting slice will make a
future ELTR-aware decision layer (its own "Option C," explicitly deferred)
easier to evaluate than building it speculatively now.

## Open questions

1. **What is the LCV formula, exactly?** "PV of consumption plus PV of
   transfer" is directionally right but underspecified: same discount
   rate as `tax_npv` (`roth_tax_discount_rate`)? Equal weighting between
   consumption and transfer, or a household-configurable split (e.g. "how
   much do you value leaving money behind vs. spending it")? Does
   `spend_total_real` (already real/plan-start-dollar, NOT yet PV'd the
   way `tax_npv` is) need an additional PV-discounting pass to combine
   with `after_tax_terminal_nw` on a like-for-like basis? This is the
   central product/financial-planning decision this spec cannot resolve
   alone.
2. **What defines the feasibility gate specifically?** Reusing
   `essential_fully_funded_probability >= <threshold>` (Phase 2, already
   exists) is the strongest existing precedent, but what threshold (100%?
   95%? household-configurable?), and should `contingent_liability` be
   included in the gate given its own established priority just below
   essential (`SPENDING_TIER_CUT_ORDER`)?
3. **Does Option A alone satisfy the "Not done" item's intent**, or was
   "gate AND scoring" always pointing at Option B/C — i.e., a gate that
   actually excludes candidates, not just reports whether they'd pass one?
   Same class of ambiguity the tier-redirection spec flagged for its own
   "Not done" wording; only a fresh product decision can resolve it.
4. **If Option B is chosen later, which optimizer(s) get the gate first?**
   The Roth optimizer and the SS claim-age sweep are architecturally
   different (one direct scoring function, one a sorted/rescaled sweep
   over projected scenarios) — gating both in the same pass doubles the
   blast radius of what is already the more consequential option.
