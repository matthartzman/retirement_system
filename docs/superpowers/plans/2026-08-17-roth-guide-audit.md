# Roth Conversion Modeling Guide vs. Implementation — Audit

Ticket 289. Walks `documentation/roth_conversion_modeling_guide.md` clause by
clause against `src/`, verifying semantics — not just that a similarly-named
key exists — per the task brief's own warning: "A `roth_tax_discount_rate`
that discounts the wrong side of the equation is a gap wearing the right
name."

## §1 — Conceptual Framework & Tax Rate Arbitrage

**§1A/§1B — Tax rate arbitrage delta, tax discount rate.** Present, and
semantically correct. `src/planning_engines.py:44-61` (`_roth_discount_rate`)
defaults to `DEFAULT_ROTH_TAX_DISCOUNT_RATE = 0.065` (6.5% nominal) —
matching the guide's §1C rule almost exactly ("6.5%–7.0% Nominal... Set equal
to expected long-term portfolio return"). Verified this is a **deliberate,
tested decoupling from the inflation assumption**
(`tests/test_roth_discount_rate_default_unit.py`): the guide's own rationale
for why the rate must equal portfolio growth, not inflation, is "discounting
future tax savings at a rate higher than portfolio growth would artificially
underestimate Roth value" — precisely the bug the code's docstring says it
used to have (`c['inf']` as the old fallback) and was fixed to avoid. Real
match, not name-matching.

**§1C — Discount rate rules of thumb by bracket.** Partially present as a
*mechanism* (the plan can set `roth_tax_discount_rate` explicitly per
household), but the guide's specific bracket-conditioned table (10–12% → 0%
haircut; 22–24% → 5–10%; 32%+ → 10%+) is **not encoded as a lookup or a
recommendation surfaced to the planner anywhere** — it lives only in this
document. This is a helper-text gap, not an engine gap: the number the guide
recommends is a *starting point for the planner to set*, and nothing in the
UI currently explains the rule that would help them set it. Addressed in
Step 8.2 below.

## §2 — Model Parameter Recommendations

**Tax Discount Rate** — see §1B above.

**Optimize Lifetime Tax Rate (bracket-fill ceiling)** — Present.
`roth_target_bracket_rate`, `roth_headroom_usage_pct` exist and are read at
`src/planning_engines.py` inside `plan_roth_conversion`
(confirmed via `target_rate = float(c.get("roth_target_rate",
c.get("roth_brk", 0.24)) or 0.24)` at line ~1510 and the bracket-strategy
branch in the frontend row model). Default ceiling (0.24) matches the
guide's baseline-profile recommendation exactly.

**Optimize Terminal Rate** — Present.
`roth_optimize_terminal_weight` / `roth_optimize_lifetime_tax_weight` exist
and are the two knobs the guide's "0.50 Weight (Moderate Priority)"
recommendation maps onto directly.

## §3 — Heir Tax Mechanics & SECURE Act

**Present.** `src/after_tax.py`'s heir mechanics model the income-tax-free
treatment of Roth distributions and the estate-tax inclusion the guide
describes. The SECURE Act 10-year non-spouse rule and the spousal-rollover
exemption are both modeled as heir-category-conditioned distribution
schedules. Not re-derived from first principles for this audit (out of scope
for a helper-text ticket to re-verify tax-law mechanics already covered by
`tests/test_after_tax_cap_gain_estate_functional.py` and sibling suites), but
the guide's specific claims (100% income-tax-free to heirs, 5-year Roth
funding rule, spouse vs. non-spouse vs. eligible-designated-beneficiary
timelines) each have a corresponding modeled branch, not a placeholder.

## §4 — Influential Model Variables

**Var 1 — Conversion tax payment source.** **GAP, confirmed.**
`grep -rn "conv_tax_source\|tax_payment_source\|withhold_from_ira\|taxable_cash" src/*.py`
returns nothing. The guide calls this a "Critical Multiplier" — the largest
single unmodeled lever in the document. Design deferred to Step 8.3 (below,
NOT executed).

**Var 2 — IRMAA bumpers.** Present.
`roth_irmaa_target_tier`, `_roth_irmaa_target_threshold_base`
(`planning_engines.py:1396+`) implement tier-bracketed MAGI thresholds with
an explicit 2-year-lookback framing in the surrounding code comments —
matches the guide's "map exact IRMAA tier brackets... establish bumpers"
recommendation.

**Var 3 — State income tax / residency arbitrage.** Present as a mechanism
(state tax rules are read into the conversion tax calculation), but **the
guide's own §4 Var 3 prose names Illinois, Florida, Texas, Nevada, Washington,
California, New York explicitly as if fixed examples** — this is itself an
instance of the same hardcoded-state-assumption pattern ticket 291 addresses
elsewhere in the codebase, just in documentation rather than code. Flagged
for the helper-text pass: the guide text itself should eventually be
reviewed for the same reason, though rewriting `documentation/roth_conversion_modeling_guide.md`'s
own prose is outside this ticket's stated scope (helper text lives in the
UI/schema, not in that reference document).

**Var 4 — Surviving-spouse single-filer compression.** Present. The survivor
stress module models the post-first-death filing-status change and its
bracket-compression effect; this is the same mechanism
`test_state_bracket_inflation.py` and the survivor-stress test suite already
pin.

**Var 5 — Social Security tax torpedo.** Present. Provisional income and the
0/50/85% SS taxability thresholds are computed in the core tax engine and
feed the same MAGI/AGI figures the Roth objective optimizes against — the
guide's "model conversions in the gap years... to shrink pre-tax balances
before SS begins" strategy is exactly what the bracket-fill optimizer does
when Social Security claim age is later than the conversion window.

**Var 6 — Asset location / sequence-of-returns.** **GAP, confirmed.**
`grep -rn "convert_equity\|conversion_asset\|sleeve" src/planning_engines.py`
returns nothing — no conversion-time sleeve selection anywhere in `src/`.
Compounding limitation for any future implementation of this gap
(documented in Step 8.3, not fixed here): per this repo's own memory
(`mc-models-location-not-sleeve-variance`), the Monte Carlo engine models
account **location**, not **in-account sleeve variance** — so even a
correctly-implemented asset-location-aware conversion may not move the
success rate at all, bounding how much value this feature could honestly
claim before it's built.

## §5 — Summary Implementation Checklist

All six checklist items map onto the sections audited above; no new claims.

## Summary table (verified, supersedes the brief's grep-only pass)

| Guide requirement | Symbol / file | Status |
|---|---|---|
| Tax discount rate (§1B/§2) | `_roth_discount_rate`, `roth_tax_discount_rate` (`planning_engines.py:44`) | Present, semantically verified |
| Discount-rate-by-bracket table (§1C) | — | Helper-text gap (Step 8.2) |
| Bracket-fill ceiling (§2) | `roth_target_bracket_rate`, `roth_headroom_usage_pct` | Present |
| Terminal vs. lifetime weighting (§2) | `roth_optimize_terminal_weight`, `roth_optimize_lifetime_tax_weight` | Present |
| Heir mechanics / SECURE 10-year (§3) | `after_tax.py` heir branches | Present |
| Conversion tax payment source (§4 Var 1) | — | **GAP — engine** |
| IRMAA bumpers (§4 Var 2) | `roth_irmaa_target_tier`, `_roth_irmaa_target_threshold_base` | Present |
| State residency arbitrage (§4 Var 3) | state tax engine | Present (mechanism); guide's own prose is IL-example-hardcoded |
| Survivor compression (§4 Var 4) | survivor stress module | Present |
| SS tax torpedo (§4 Var 5) | provisional income in tax engine | Present |
| Asset-location-aware conversion (§4 Var 6) | — | **GAP — engine**, and bounded by the MC location-not-sleeve-variance limitation even if built |

## Deliverables from this audit

1. Helper text for tax discount rate (§1C rule), target bracket rate, IRMAA
   target tier, terminal/lifetime weighting — Step 8.2, executed.
2. UI + workbook disclosure of the two confirmed gaps — Step 8.2, executed.
3. Design (not implementation) for both gaps — Step 8.3,
   `docs/superpowers/plans/2026-08-17-roth-conversion-gap-design.md`, NOT executed.
