# Phase 3 — Tax NPV / ELTR State-Contingent Tax Modeling — Spec

Next item named in `documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s "Not
done" list, and the last one before Phases 4-6 (LCV feasibility gate,
adaptive guardrails, expanded stress scenarios), all of which the doc
itself calls "entirely unimplemented."

**Spec/research only — no code in this document.** Mechanical grounding
delegated to an Explore subagent; the design analysis below is original.

## The scoping problem this spec exists to solve

Unlike every prior increment in this refactor, there is **no surviving
detailed source** for what Phase 3 was supposed to contain. The "Final
Optimization Implementation Plan — Revised" this whole refactor tracks
against is referenced by name in `OPTIMIZATION_REFACTOR_STATUS.md`'s
opening paragraph but does not exist anywhere in this repository — it was
apparently never committed, and the in-session planning notes that would
have expanded on it do not survive between sessions (the status doc says
as much of itself: "the in-session planning notes Claude Code keeps
locally do not survive a new session or container"). All that survives is
one line: *"tax NPV / ELTR state-contingent tax modeling"* (ELTR =
"effective lifetime tax rate," confirmed via a code comment). This spec's
job is to reconstruct a defensible, minimal-risk Phase 3 from that one
line plus whatever raw material already exists in the code — not to guess
at a larger design nobody can verify against the lost source.

## What exists today (verified against the code)

### A working, PV-discounted lifetime-tax objective already exists — scoped to one candidate at a time

`_roth_strategy_metrics` (`src/planning_engines.py:2298+`) is the
Roth-conversion optimizer's scoring function. It already:

- Computes `lifetime_tax` as a PV-discounted sum (`planning_engines.py:2328`):
  `sum(total_tax / (1+discount)**(year - plan_start) for r in rows)`, using
  `discount = _roth_discount_rate(c)` (line 2327, config knob
  `roth_tax_discount_rate`, default 6.5%, plumbed through `data_io.py`).
- Separately tracks `lifetime_tax_nominal` (undiscounted) alongside it.
- Discounts `after_tax_terminal_nw` to `after_tax_terminal_nw_pv`
  (2336-2345), with a comment documenting a previously-fixed bug where
  terminal wealth was left nominal while tax was already PV'd — i.e. this
  code has already paid down the "don't mix nominal and PV'd terms" tax
  once.
- Builds further PV/exposure terms via `_disc(row)`, `_pv_avg(field)`, and
  `_peak(field)` helper closures (2367-2440+) for legacy/estate/
  survivor-risk exposure, combined into a final weighted `score`.

This is real, live, tested machinery — but it operates on exactly **one**
deterministic row set per Roth-strategy candidate. It is not a reusable
NPV utility (the discounting math is inlined as closures inside this one
function), not surfaced to any report as an "ELTR" figure, and not
computed per-MC-path — it has no notion of "state" at all beyond whichever
single scenario is being scored.

### `gross_cash_flow_yr` was built for this and is currently inert

`deterministic_engine.py:2990-2999`'s own comment: *"Optimization-refactor
Phase 1 item 2: gross external cash flow, for ELTR (effective lifetime tax
rate) and tax-NPV reporting."* Both MC engines already propagate it into
`gross_cash_flow_real`/`gross_cash_flow_real_pct_by_year` (Phase 1 items
2-3, `planning_engines.py:3311` and `:3802` on). But nothing downstream
ever reads those fields to compute a ratio, an NPV, or anything else —
they sit in MC output unused. This is raw material Phase 1 explicitly
pre-built for Phase 3, never consumed.

### Nothing else exists

No general-purpose PV/NPV utility function exists anywhere in `src/`
(`annuity_pv` discounts annuity income for asset-allocation purposes;
`_terminal_pv` in `sheets_stress.py` is a CPI deflator, not a tax-NPV
calc — neither is reusable for this). No "state-contingent" framing exists
anywhere except this status doc's own one-line mention of itself. Phases
4-6 (LCV feasibility gate, adaptive guardrails, expanded stress scenarios)
have zero scaffolding at all — `sheets_stress.py`'s five stress sheets are
each a hardcoded, single-scenario re-run pattern (LTC stress, survivor
stress, RMD audit, etc.), not a generic "run N scenarios and gate on
feasibility" framework.

## What "Phase 3" most plausibly means

Reading the one surviving line against the code that already exists
(rather than against a lost document), the most defensible interpretation
is: **generalize the PV-discounted lifetime-tax pattern that already lives
inside the Roth optimizer into a reusable metric, and report it across the
Monte Carlo distribution** (the "state-contingent" half — a single
deterministic ELTR number is not state-contingent; a distribution across
sampled paths, the same pattern every Phase 2 metric in this refactor
already uses, is). Concretely:

- **`tax_npv`**: `total_tax` (or `tax_total_real`, already computed by both
  MC engines) discounted to plan-start PV, per path.
- **`effective_lifetime_tax_rate` (ELTR)**: `tax_npv / gross_cash_flow_npv`
  — the PV of lifetime tax paid divided by the PV of lifetime gross cash
  flow (income + draws), per path. This finally gives `gross_cash_flow_yr`
  a consumer, closing the gap Phase 1 explicitly anticipated.
- Reported as a **distribution across MC paths** (percentiles, mirroring
  `after_tax_terminal_nw_pct`/`cut_years_pct`/etc.), not a single number —
  this is what "state-contingent" can honestly mean given what the engines
  already produce: different sampled-return/inflation/death-year paths are
  the "states."

This is explicitly a **narrower** reading than "state-contingent tax
_modeling_" could imply in the abstract (e.g., an active decision layer
that changes withdrawal/conversion behavior based on realized tax state
year-to-year — a much larger undertaking with no existing scaffolding at
all, closer in shape to Phases 4-6). The narrower reading is preferred
because it is the one actually grounded in code that exists today, follows
the same "reporting-only, reuse an existing computation, extend to a
distribution across paths" pattern this refactor has used for every Phase 1/2
increment, and does not require reconstructing an active decision-model
design from a single lost sentence.

## Options

**Option A — Reporting-only ELTR/tax-NPV distribution (recommended
scope).** Extract a small `discount_series_to_pv(rows_or_arrays, field,
discount_rate, plan_start)` helper (generalizing the inlined closure
pattern already proven correct in `_roth_strategy_metrics`), and add
`tax_npv`/`effective_lifetime_tax_rate` to both MC engines' per-path output
and percentile summaries — the same shape as every Phase 2 metric already
shipped (`after_tax_terminal_nw_pct`, `liquidity_coverage_pct_by_year`,
etc.). Purely additive: never feeds back into `unfunded`/`liquid`/`total`/
`path_success`/`success_rate`, matching this refactor's established
precedent of separating "close a correctness gap" / "add reporting" from
"change decision logic." Which discount rate to use is an open question
below.

**Option B — Extract the Roth-optimizer's full PV machinery into a shared
module first.** Same end state as Option A, but as a larger prerequisite
step: pull ALL of `_roth_strategy_metrics`'s PV logic (not just the tax
term) into a standalone, tested module other callers can use, then build
ELTR on top of it. Cleaner architecture, but touches code the Roth
optimizer already depends on for its own scoring — real regression risk to
an existing, working feature for a benefit (reusability beyond this one
new metric) that isn't yet needed by anything else.

**Option C — An active state-contingent tax-decision layer.** Read "tax
NPV / ELTR state-contingent tax modeling" as originally intended to mean a
policy that changes plan decisions (e.g., Roth conversion pacing,
withdrawal source) based on each path's own realized tax trajectory, not
just a reported metric. This is plausible given the phase title's use of
"modeling" rather than "reporting," but has zero existing scaffolding,
would need its own product/design decision on what "responds to tax state"
even means operationally, and is a materially larger and riskier
undertaking than anything shipped in this refactor to date. Given the
governing document that would resolve this ambiguity no longer exists,
building Option C now would mean guessing at a lost design rather than
implementing a known one.

## Recommendation

**Option A.** It is the interpretation best supported by what Phase 1
explicitly pre-built (`gross_cash_flow_yr`, sitting inert, built
specifically "for ELTR ... reporting" per its own comment) and by what
already works and is tested (`_roth_strategy_metrics`'s PV-discounting).
It follows the exact "reporting-only extension of an existing computation,
across the MC distribution" pattern that every Phase 1/2 increment in this
refactor used, which is also the pattern the "Genuinely redirecting
withdrawal requests" spec (2026-08-27) explicitly contrasted itself
against as the *safe* option (its own "Option A" there, cascade-consistent
reporting, vs. "Option B," a real policy change) — Phase 3's Option A here
plays the same safe role.

## Open questions

1. **Which discount rate?** `_roth_strategy_metrics` uses
   `roth_tax_discount_rate` (default 6.5%), a Roth-optimizer-specific
   config knob. Reusing it for a general-purpose ELTR metric conflates two
   different config surfaces (a Roth-optimizer tuning parameter vs. a
   plan-wide reporting assumption) — should ELTR get its own discount-rate
   config field, or is reusing the existing one acceptable? This is a
   product/naming decision, not an engineering one.
2. **Denominator choice for ELTR.** Gross cash flow (income + draws,
   `gross_cash_flow_yr`'s existing definition) vs. total spend
   (`total_spend`) vs. AGI-like taxable income — each produces a
   differently-scaled "effective rate" and each is a defensible reading of
   "effective lifetime tax rate" as a term of art. `gross_cash_flow_yr`'s
   own Phase-1 comment ties it to this metric by name, so it's the
   strongest textual precedent, but should be confirmed rather than
   assumed.
3. **Does ELTR belong in the deterministic engine, both MC engines, or
   only one?** Every prior Phase 2 metric landed in both MC engines
   together (with the deterministic engine sometimes also getting a
   single-path equivalent, e.g. `spend_by_tier`). Should Phase 3 follow
   that same both-engines-together precedent, or is a narrower first slice
   (vectorized only, scalar as an explicit follow-up — the same
   deferred-parity precedent used for HSA-engine parity and initially
   proposed, then overridden, for the tier-redirection spec) more
   appropriate given Phase 3's own novelty?
4. **Should Option C's "active tax-decision layer" reading be explicitly
   ruled out**, or does it remain a legitimate future Phase 3-adjacent item
   once Option A's reporting exists and a concrete consumer (e.g., "should
   the plan prefer more Roth conversion in years where ELTR would drop")
   makes the case for it? Recommend treating Option C as out of scope for
   this increment and re-opening it only if a specific decision-quality
   problem surfaces that Option A's reporting alone can't explain.
