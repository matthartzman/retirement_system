# Monte Carlo headline vs exact scalar engine (WI-036)

Follow-up to `MC_PARITY_MEASUREMENT_WI009.md`, which was a spot measurement on one
household shape at n=200. This study uses n=1000 paired paths per cell, several
seeds, all three Roth regimes (including the shipped default
`optimize_terminal_tax`) and eight household shapes. Same sampled paths go to the
vectorized replay headline and to the exact scalar engine (`project()` per path),
so the signed gap carries no sampling noise. Gap is vectorized minus scalar
success rate, in percentage points; a positive gap means the headline is
optimistic.

Harness: `tests/paired_path_harness.py`. Study driver:
`tools/measure_mc_paired_path.py` (about 0.3 s of scalar time per path; the
study below took roughly one hour on four cores). Households are the synthetic
golden-master shapes, so nothing here depends on client data. The `pressure:S:A`
shapes are the thin-portfolio household with balances at S times the standard
set and A of core annual spending: between comfortably solvent and depleted.

## Results

| Household shape | Roth regime | Seeds | Scalar success | Vectorized success | Signed gap (pp) | Path agreement |
|---|---|---|---|---|---|---|
| baseline_balanced_couple | none | 11,5,3 | 1.00-1.00 | 0.99-1.00 | -0.3 to +0.0 | 99.7-100.0% |
| baseline_balanced_couple | fill_to_bracket | 11,5,3 | 1.00-1.00 | 0.98-0.99 | -1.5 to -0.6 | 98.5-99.4% |
| baseline_balanced_couple | optimize_terminal_tax | 11,5,3 | 1.00-1.00 | 0.99-1.00 | -0.3 to +0.0 | 99.7-100.0% |
| single_filer | none | 11,5,3 | 1.00-1.00 | 0.99-0.99 | -0.6 to -0.4 | 99.4-99.6% |
| single_filer | fill_to_bracket | 11,5,3 | 1.00-1.00 | 0.98-0.98 | -1.5 to -1.4 | 98.5-98.6% |
| single_filer | optimize_terminal_tax | 11,5,3 | 1.00-1.00 | 0.99-0.99 | -1.0 to -0.7 | 99.0-99.3% |
| early_survivor_compression | none | 11,5,3 | 1.00-1.00 | 1.00-1.00 | +0.0 to +0.2 | 99.8-100.0% |
| early_survivor_compression | fill_to_bracket | 11,5,3 | 1.00-1.00 | 1.00-1.00 | +0.0 to +0.2 | 99.8-100.0% |
| early_survivor_compression | optimize_terminal_tax | 11,5,3 | 1.00-1.00 | 1.00-1.00 | +0.0 to +0.2 | 99.8-100.0% |
| split_claiming_spousal | none | 11,5,3 | 1.00-1.00 | 0.99-0.99 | -0.6 to -0.1 | 99.4-99.9% |
| split_claiming_spousal | fill_to_bracket | 11,5,3 | 1.00-1.00 | 0.98-0.99 | -1.7 to -0.7 | 98.3-99.3% |
| split_claiming_spousal | optimize_terminal_tax | 11,5,3 | 1.00-1.00 | 0.99-0.99 | -0.6 to -0.3 | 99.4-99.7% |
| depletion_thin_portfolio | none | 11,5,3 | 0.05-0.07 | 0.69-0.71 | +63.2 to +64.5 | 35.5-36.8% |
| depletion_thin_portfolio | fill_to_bracket | 11,5,3 | 0.05-0.07 | 0.69-0.71 | +63.1 to +64.6 | 35.4-36.9% |
| depletion_thin_portfolio | optimize_terminal_tax | 11,5,3 | 0.05-0.07 | 0.69-0.71 | +63.2 to +64.5 | 35.5-36.8% |
| pressure:0.7:150000 | none | 11,5 | 0.70-0.71 | 0.77-0.78 | +6.4 to +7.6 | 92.4-93.6% |
| pressure:0.7:150000 | fill_to_bracket | 11,5 | 0.69-0.69 | 0.76-0.77 | +7.3 to +8.4 | 91.0-92.1% |
| pressure:0.7:150000 | optimize_terminal_tax | 11,5 | 0.70-0.71 | 0.77-0.78 | +6.4 to +7.6 | 92.4-93.6% |
| pressure:0.6:150000 | none | 11,5 | 0.52-0.52 | 0.73-0.74 | +21.2 to +22.0 | 78.0-78.6% |
| pressure:0.6:150000 | fill_to_bracket | 11,5 | 0.50-0.51 | 0.73-0.74 | +21.6 to +23.6 | 76.2-78.0% |
| pressure:0.6:150000 | optimize_terminal_tax | 11,5 | 0.52-0.52 | 0.73-0.74 | +21.2 to +22.0 | 78.0-78.6% |
| pressure:0.8:175000 | none | 11,5 | 0.58-0.60 | 0.74-0.76 | +14.8 to +17.0 | 83.0-85.2% |
| pressure:0.8:175000 | fill_to_bracket | 11,5 | 0.57-0.58 | 0.74-0.75 | +16.6 to +18.3 | 81.3-83.4% |
| pressure:0.8:175000 | optimize_terminal_tax | 11,5 | 0.58-0.60 | 0.74-0.76 | +14.8 to +17.0 | 83.0-85.2% |

## What the measurement shows

1. **Funded households: the disclosed tolerance holds, in all three regimes.**
   For the four comfortable shapes (baseline couple, single filer, early
   survivor, split claiming) the signed gap is between -1.7 and +0.2 pp and path
   agreement is at least 98.3%. The shipped default regime
   (`optimize_terminal_tax`) behaves like `none` on these households; the
   optimizer converts on the baseline and split-claiming shapes and the gap is
   still within -0.6 pp. These shapes sit at 100% scalar success, so they show
   that the engines agree when nothing is at risk, not that the gap is small
   near a decision boundary.
2. **Households whose base plan runs into shortfall: the headline is
   optimistic, well beyond the +/-5 pp label.** The gap grows with the pressure:
   +6.4 to +8.4 pp (scalar success 0.69-0.71), +14.8 to +18.3 pp (0.57-0.60),
   +21.2 to +23.6 pp (0.50-0.52), and +63 to +65 pp for the depleted household
   (scalar 0.05-0.07, headline 0.69-0.71). The headline responds far less to shortfall than the exact engine does (it
   stays between 0.69 and 0.86 across these households). The regime makes no
   material difference.
3. **Likely mechanism (not proven here).** The replay allocation re-uses the
   deterministic engine's per-bucket draws. When the deterministic base plan is
   itself unfunded in some years, those draws are capped at what the base plan
   could fund, so a sampled path is not asked to fund the full spending need and
   shows as a success.
4. **The `TOLERANCE_BOUNDED` ("+/-5pp") KPI label is therefore wrong for these
   households.** The label is applied by policy
   (`MC_PARITY_DEMONSTRATED_POLICIES`), not by plan shape. For the thin-portfolio
   household the app reports 68% success with that label while the exact engine
   fails nearly every path.

Not measured: the tier-shadow secondary figure (already removed from the tile),
the frozen sample plan at n=1000 (n=200 results in the WI-009 note stand), and
any household with large annuity, rental or equity-compensation income.

## Test coverage added

`tests/test_mc_headline_paired_path_default_tier_regression.py` runs in the
default tier at n=40: the funded household under all three regimes (gap within
6 pp, agreement at least 90%) and the pressure household pinned to the measured
optimistic band (+8 to +45 pp), so the known limitation cannot worsen unnoticed
and a repair forces the bound to be updated. The n=200 nightly test now imports
the shared harness.

## Repair: disclosure guard (option 1, implemented)

Owner chose option 1 on 2026-10-21. `monte_carlo` now sets
`mc_base_plan_shortfall` when any deterministic base row has an unfunded gap
above $1, and in that case reports `mc_approximation_status =
BASE_PLAN_SHORTFALL` and `model_risk_rating = APPROXIMATE_VECTORIZED_MC` instead
of `TOLERANCE_BOUNDED`. The KPI tile then reads "(optimistic: your plan projects
a shortfall)" with a tooltip calling the figure an upper bound, and the
governance label says the same. No success rate, pin or projection number moves;
funded plans keep the "+/-5pp" label.

## Still open (not implemented)

The headline number itself remains optimistic for plans in shortfall. Fixing the
number is options 2 and 3 below; both move headline MC, sustainable-spend and
claim-age results and need an owner decision. The default-tier test pins the
measured optimistic band so a repair must update it.

2. **Funded-as-asked replay for shortfall plans:** make replay fund the full
   sampled spending need on years where the base plan was short, then re-run this
   study.
3. **Scalar engine of record** for any displayed headline when the base plan has
   a shortfall (slower; removes the parity question for those plans).
