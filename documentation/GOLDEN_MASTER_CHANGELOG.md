## 2026-09-04 — Golden-master pin regenerated via `tools/regen_golden_master.py regen`

<!-- pin-provenance: terminal_nw=5460394.26 lifetime_tax=1262469.23 -->

**Old pins.** terminal_nw=5,763,251.84, lifetime_tax=1,316,887.09

**New pins.** terminal_nw=5,460,394.26, lifetime_tax=1,262,469.23

**Reason.**

Fixed a real bug where annuity/pension/Social Security income always paid a full
12 months in the calendar year benefits actually started, regardless of what
month the contract's first_payment (or a person's Social Security claim) fell
in. A contract with first_payment 6/1/2026 showed 12 months of cash flow in
2026 instead of 7 (June-December).

Root cause: src/core.py's annuity_cash_income() only ever worked in whole
calendar years -- src/data_io.py's load_stream() discarded the month/day of
first_payment and kept only the year. Social Security had the same gap:
deterministic_engine.py derived the claim year purely from birth year + claim
age, with no month component, so h_ss/w_ss also paid a full first year.

Fix:
- src/core.py: annuity_cash_income() now prorates the cash actually paid in
  the first income year by the fraction of that year remaining from the
  first_payment month onward. Later years are unaffected -- the reserve/
  compounding math that drives future-year growth still runs on full
  12-month increments, since a carrier's "guaranteed annual payment" is a
  full-year figure for crediting purposes regardless of when the first
  check went out; only the dollars collected in a partial stub year shrink.
- src/data_io.py: load_stream() now also captures first_payment's month.
- Social Security claim_age (a bare integer with no month) was replaced by
  claim_date (MM/YYYY) as the primary input, with claim age now calculated
  and displayed rather than entered directly. claim_date's month drives the
  same first-year proration for h_ss/w_ss. Plans with no claim_date (only
  the legacy claim_age) keep the pre-existing default: age 70, claimed in
  the person's own birth month -- so this only changes results for a plan
  that actually has a non-January claim/first-payment month, which the
  frozen sample plan does (claim_age 69/66, birth months August/May).

The frozen sample plan's Member 1/2 claim_age (69/66) and several income
streams' first_payment fields all fall in non-January months, so this
correction changes its terminal net worth and lifetime tax -- both moved
down, since less first-year income means less first-year Roth room but also
less first-year tax; the net terminal effect here is a decrease because the
prior version overstated Social Security and pension income in the claim
year.

## 2026-09-02 — Ticket 305: additive `Monarch Id` transaction column

**No pins moved.**

Adds `"Monarch Id"` to `TRANSACTION_COLUMNS` (`src/ytd_tracking.py`) and
`"Rows Updated"` to `IMPORT_HISTORY_COLUMNS`, supporting the new Monarch
auto-update upsert path (`upsert_transactions_by_monarch_id`). Both are
purely additive and default to `""`/empty for every existing row: manual
CSV uploads and every transaction entered before this change are
unaffected. `transaction_hash()` is deliberately pinned to the original 9
columns via a separate `_HASH_COLUMNS` list, so it produces byte-identical
hashes to before this change for any row without a Monarch id — the
existing hash-based dedup used by manual uploads is untouched.
`docs/superpowers/specs/2026-09-02-monarch-autoupdate-reporting-design.md`
has the full design.

## 2026-08-26 — Optimization-refactor Phase 2 addition: `legacy_floor` CSV-schema wiring

**No pins moved. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

Follow-up to the `probability_legacy_floor_met` reporting field below: adds
the `Estate Planning / Legacy / legacy_floor` schema row (dollars, default
0) so households can actually set it, plus one line in `parse_client()`
reading it into `c['legacy_floor']`. The frozen golden-master fixture's new
row is `$0` (inert, matching the schema default), so the pinned figures are
unaffected. No `frontend/js/dashboard.js` changes were needed or made — see
`documentation/OPTIMIZATION_REFACTOR_STATUS.md`'s matching entry for why.

## 2026-08-26 — Optimization-refactor Phase 2 addition: probability of meeting a user legacy floor

**No pins moved. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

New reporting field, `probability_legacy_floor_met`, in both
`monte_carlo_exact_scalar` and `_mc_vectorized_batch`/`monte_carlo()`:
the fraction of Monte Carlo paths whose after-tax terminal bequest
(`post_tax_inheritance`, already computed for
`after_tax_terminal_nw_pct`/`post_tax_inheritance_pct`) meets or exceeds a
household-configured `legacy_floor` dollar target, read defensively via
`c.get('legacy_floor', 0.0)`. Reports `None` (not a misleading 0.0 or 1.0)
whenever no floor is configured, matching the same convention already used
for `survivor_period_*` and `liquidity_coverage_pct_by_year`.

**Why the pins don't move.** Purely additive: reads each engine's
already-finalized `post_tax_inheritance` tracking and never feeds back
into `unfunded`/`liquid`/`total`/`path_success`/`success_rate`. No CSV
schema field named `legacy_floor` exists yet, so this is inert for every
household until front-end/schema wiring is added in a later increment.

## 2026-08-26 — Optimization-refactor Phase 2 refinement: contingent_liability split into premium (cuttable) vs. incurred shock (protected)

**No pins moved. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

Follow-up refinement to the same-day cascade correction below. The
`contingent_liability` tier bundled two different kinds of dollars:
`ltc_prem_yr` (an LTC insurance premium — a genuine choice to forgo future
coverage) and `wellness_shock_yr` (an already-incurred health/LTC event
cost — not a discretionary spending choice). Both were cut identically at
`contingent_liability`'s cascade priority. Now `ltc_prem_yr` stays in
`contingent_liability`; `wellness_shock_yr` routes into `essential`
instead, protecting it at essential's priority.

**Why the pins don't move.** Purely a re-labeling within
`row['spend_by_tier']` — the sum across all tiers (and therefore
`total_spend`) is unchanged, only which tier a dollar is attributed to.

**What DID change, and is expected to.** For any household with nonzero
`wellness_shock_yr` (an MC-sampled health-shock cost) and a shortfall deep
enough to reach the old contingent_liability tier, that dollar amount now
counts toward `essential` instead — `essential_fully_funded_probability`
will show a shortfall *sooner* for such paths (essential is no longer
artificially protected by dollars that were never really discretionary
contingent-liability spending), while `spending_priority_cut_check`'s
`tier_cut_by_year` will show smaller `contingent_liability` cuts (now just
the LTC premium) with the shock-cost portion appearing under `essential`
instead. Both MC engines picked this up automatically — no MC-engine-level
code changes were needed, since `SPENDING_TIER_CUT_ORDER`-based cascades
already consume `spend_by_tier`'s tier keys generically.

## 2026-08-26 — Optimization-refactor Phase 2 correction: contingent_liability now included in the tiered-cut cascade

**No pins moved. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

Corrects already-shipped Phase 2 behavior, not new engine behavior. Both MC
engines' essential-shortfall attribution (`essential_fully_funded_probability`)
and `spending_priority_cut_check`'s `tier_cut_by_year` hardcoded a
`('discretionary', 'important', 'essential')` cascade that skipped
`contingent_liability` entirely — treating LTC premiums and wellness-shock
costs as fully protected from ever absorbing a shortfall. This contradicted
`SPENDING_TIER_CUT_ORDER` (`spending_budget_resolver.py`), which Phase 0
already defined and documented as "the future phase's single source of
truth for cut ordering": discretionary, important, **contingent_liability**,
essential. Fixed to use that canonical order.

**Why the deterministic pins don't move.** This changes only which tier a
cut is attributed to in the reporting layer — `spend_base`, `total_spend`,
withdrawal amounts, and `unfunded`/`unfunded_gap` are untouched. The frozen
fixture's `base_rows = project(c)` call path is unaffected.

**What DID change, and is expected to.** For any household with nonzero
`contingent_liability` spending (LTC premiums, wellness shocks) and any
shortfall year, `essential_fully_funded_probability` will now be *higher*
than before (a shortfall correctly exhausts contingent-liability dollars
before ever reaching essential, rather than skipping past them), and
`spending_priority_cut_check`'s `tier_cut_by_year`/`tiered_*` fields will
show a `contingent_liability` entry in years where a cut reaches that tier.
Not modeled: `ltc_prem_yr` (a premium, a genuine choice to forgo coverage)
and `wellness_shock_yr` (an already-incurred cost) are cut identically
since `spend_by_tier` sums them into one figure — a real remaining nuance
left for a future refinement.

**Reconciliation note (2026-08-27, merging `claude/plan-execution-tg1rps`):**
this entry and the split above it landed on a branch that diverged before
the five entries below (PR #66-#69) existed. A separate, later PR (#70,
merged first) independently reclassified `ltc_prem_yr` the *opposite* way
(into `essential`) without knowing about this correction; on reconciling
the two branches, PR #70's classification was reverted in favor of the one
described here, per explicit user decision -- this entry's finding (the
cascade hardcoded an exclusion contradicting `SPENDING_TIER_CUT_ORDER`'s
own documented order) is a genuine pre-existing bug fix. `_mc_tier_priority_
retained` (introduced by PR #64, one of the entries below, which this
branch never saw) was reconciled to read via `SPENDING_TIER_CUT_ORDER` too,
so the vectorized engine's essential-shortfall cascade and
`spending_priority_cut_check` agree. No pins moved by the reconciliation
itself -- both branches' changes were pin-neutral on the frozen fixture.

## 2026-08-26 — Golden-master pin regenerated via `tools/regen_golden_master.py regen`

<!-- pin-provenance: terminal_nw=5763251.84 lifetime_tax=1316887.09 -->

**Old pins.** terminal_nw=5,763,251.84, lifetime_tax=1,316,527.24

**New pins.** terminal_nw=5,763,251.84, lifetime_tax=1,316,887.09

**Reason.**

HSA-reimbursed medical is no longer also deducted on Schedule A

**Engine change. Pins move: `5,814,607.29 / 1,304,382.77` -> `5,763,251.84 / 1,316,887.09`.**
Terminal net worth **down** $51,355.45; lifetime tax **up** $12,504.32.

**What was wrong.** A qualified medical expense cannot both be reimbursed
tax-free from an HSA and deducted on Schedule A. `medical_expense_yr`
(`deterministic_engine.py`) was computed from the household's full medical
spend -- wellness premiums, wellness detail budget, wellness shocks and the
LTC premium -- and fed the itemized medical deduction above the
7.5%-of-AGI floor with **no reduction for HSA dollars already reimbursed
against the same expense**. Nothing anywhere netted the two.

Measured on the frozen fixture before the fix: **all 123,301.40 of lifetime
HSA withdrawals were also clearing the floor**, i.e. every HSA dollar the
plan drew was taking both benefits. The fixture draws its HSA on a
`smooth_window` schedule from 2031, and its medical spend (72k+/yr and
rising) far exceeds those draws, so the draws are amply covered by
qualified expenses -- they are genuinely qualified, and therefore genuinely
not separately deductible.

**Two of this refactor's own recent changes made it more reachable**, which
is worth recording rather than leaving to be rediscovered. PR #66
(`fund_contingent_liability_from_hsa`) routes `ltc_prem_yr +
wellness_shock_yr` preferentially to the HSA, and those are two of the four
components of `medical_expense_yr` -- so HSA dollars now cover exactly the
costs most likely to clear the floor. PR #67's schedule search then
optimizes against a model that overstated HSA value in precisely the
high-medical years it draws toward. The defect predates both; its frequency
did not.

**The fix.** Between Priority 2 and Priority 3, the deduction is reduced by
the HSA dollars reimbursed against that year's medical spend, and fed tax /
taxable income / total tax are recomputed.

**Placement is load-bearing, and the first attempt got it wrong.** This
correction *increases* tax, so the gap grows and the rest of the cascade
must still be able to fund it IN ORDER. An initial version sat after
Priority 4c, reasoning that `hsa_wd` is not final until 4c's gap-fill runs.
`test_recommendations_functional.py::test_fixed_point_taxable_withdrawal_solver_runs_before_roth`
caught that: with the demand added after 3/4b/4c, only Roth was left to fund
it, so the plan drew Roth while pre-tax and HSA balances still remained --
10 violations of the cascade's Roth-last invariant. Correctness of the
withdrawal ORDER outranks capturing every last netted dollar.

The trade that buys: only draws known by that point are netted -- Priority
1b's contingent-liability draw (which exists precisely to pay qualified
medical) and Priority 2's scheduled window draw. Priority 4c's gap-fill is
excluded, which is defensible rather than merely convenient: 4c is a
last-resort liquidity draw against a general cash shortfall, not a
reimbursement of that year's medical spend. It also errs conservative --
netting less means the correction is never more aggressive than the
evidence supports, and it is why the lifetime-tax move (+12,144.47) is
smaller than the after-4c placement produced.
`unfunded_gap` stays 0.00 in every fixture year.

(The DAF re-deduction block later in the same function is the same shape
with the opposite sign; it only ever lowers tax, which is why it can safely
sit after the draws -- a shrinking gap needs no funding.)

**One more trap this hit, worth recording.** The block first updated
`total_tax` directly. That is silently discarded: `total_tax` is rebuilt
from scratch further down as
`total_tax_pre_niit + ltcg_tax + niit - tlh_ordinary_credit`, so the
`fed_tax` change survived while the `total_tax` change did not, leaving the
two disagreeing by the corrected amount. It surfaced as a 178.21 cash-flow
reconciliation residual in
`tests/test_cashflow_breakdown_single_source_of_truth.py`, with the
breakdown's `other` remainder absorbing exactly the gap. The fix is to
recompute `total_tax_pre_niit` from its own components -- the idiom the
engine already uses at its other two update sites -- rather than to
hand-maintain `total_tax`.

Two deliberate limits on scope:

* **Only the deduction changes.** The medical spend is a real cash cost;
  `total_spend` and the `wellness_*` row fields are untouched. This changes
  what is deductible, not what is spent.
* **The floor's AGI basis is left alone.** The shipped version nets the
  reimbursed dollars out of the deduction directly rather than re-deriving
  `max(0, net_medical - 0.075*agi)` at the correction point. Being precise
  about what that is worth, since an earlier draft of this entry overstated
  it: the two forms are **algebraically identical** while the deduction is
  above the floor and `agi` is unchanged between the two points, and
  planting the re-derived form produces **byte-identical pins** -- no test
  here distinguishes them. They diverge only where `agi` has been mutated
  in between; measured under a `roth_policy='none'` configuration,
  re-deriving stripped 18,439 against a 10,168 reimbursement in one year.
  Real, but not something that moves these pins. Netting directly is still
  preferred because it inherits whatever floor the engine already applied
  instead of silently re-basing it. Whether that floor should use
  first-pass or converged AGI is a real question, and a separate one.

**Std-vs-itemized is re-evaluated**, so a household pushed below the
standard deduction by this correction takes the standard one. That caps the
damage at `item_ded - std_ded` rather than the full lost medical deduction,
and is one of two reasons the realized lifetime-tax move (+12,504.32) sits
well below the ~27-30k a naive `lost_deduction x marginal_rate` estimate
predicts -- the other being the Priority-4c exclusion described above.

**Blast radius.** Every household that both draws an HSA and itemizes
medical costs above the floor sees higher tax and lower terminal net worth.
Households that never draw an HSA, or whose medical spend never clears the
floor, are bit-identical. **This makes affected plans look worse**, which
per this changelog's own 2026-08-18 precedent deserves more scrutiny rather
than less -- the direction is uncomfortable but it is the direction the tax
treatment requires.

Design and prior research:
`docs/superpowers/plans/2026-08-26-hsa-expense-bank-and-double-dip-spec.md`.
New coverage: `tests/test_hsa_medical_deduction_double_dip_regression.py`.

## 2026-08-26 (b) — The HSA schedule search is wired into builds: no pins moved, but `optimize`-mode households get a real search instead of a level-draw placeholder

**Not a change to any figure on the frozen fixture. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

**Why the pins don't move.** The frozen fixture's `client_assets.csv` sets
`hsa_withdrawal_mode = smooth_window`, and `run_schedule_search` returns
immediately (`ran=False`, "not in optimize mode") for every mode except
`optimize`. The deterministic run that produces the pins never reaches the
search. Confirmed by running the golden-master gate before and after.

**What changed.** `hsa_schedule.py` documented that its own search --
`build_schedule`/`rerun_optimizer` -- was "NOT called anywhere in the
projection pipeline," because the search needs full per-year projection rows
for tax context and those only exist after the projection that would consume
the schedule. So `optimize` mode actually ran
`generate_default_schedule`'s **static level draw**, an explicitly-labelled
placeholder, not a search. `run_schedule_search` now closes that, called once
per build from `workbook_builder.main` just after
`_ensure_hsa_default_schedule`.

**How the circularity is resolved.** Not by a two-pass approximation (which
would price a schedule using rates it changes), but by the pattern
`optimize_roth_conversion_strategy` already uses for the identical problem:
score candidates on their **own** full projections and keep the winner. The
incumbent schedule is always a candidate, so **the result can never be worse
than the previous behavior** -- a degenerate search simply loses the
comparison. That guarantee is structural and needs no feature flag.

**One round is not enough, and that was found by test, not inspection.**
Candidate scoring is self-consistent, but candidate *generation* still reads
the incumbent's rows, so a single round does not reach a fixed point: a
re-run against an adopted proposal beat it again by ~1.7%. The search
therefore iterates (bounded at `_SCHEDULE_SEARCH_MAX_ROUNDS = 4`, stopping
early below a `$1` gain), which is safe because each round is adopted only
on a strictly higher score -- the sequence is monotonic. Measured on the
frozen fixture forced into `optimize`: level-draw incumbent scores 10,698,
the search settles at 29,698 over 4 rounds (**2.8x**), and a subsequent run
adopts nothing and stops after one round.

**User intent is safe by construction.** The search installs only what
`rerun_optimizer` returns, and that function's contract -- "a re-run may
never eat the user's intent" -- copies `override_amount` through untouched on
every path and plans *around* locked years rather than through them.
Verified end-to-end: a planted override survives exactly and resolves as
`override`; a locked year's `optimizer_amount` is unmoved and resolves as
`locked`; a deliberate `0.0` override is honored rather than read as absent.

**Cost.** Two full projections per round; a full-horizon `project()` measures
~20-60ms, so a first search is ~0.24s and a settled re-run ~0.06s. This is
not the class of cost behind the 81x `monte_carlo()` CI timeouts recorded in
`documentation/OPTIMIZATION_REFACTOR_STATUS.md`.

**Blast radius.** Bit-identical for every household not in `optimize` mode --
including the frozen fixture and the demo plan. For `optimize` households
(reachable: `data_io.py:1274` admits the mode) the HSA drawdown schedule
changes, and with it every figure downstream of HSA withdrawal timing. Never
raises into a build: any failure returns `ran=False` and leaves the incumbent
schedule standing.

New coverage: `tests/test_hsa_schedule_search_wiring_regression.py` (9
tests). The never-worse guarantee and all three user-intent guards were
demonstrated red against planted defects before being trusted, per §3 rule 2.

## 2026-08-26 — Contingent-liability spending draws the HSA first: no pins moved, but HSA sourcing changes for households with an LTC premium

**Not a change to any figure on the frozen fixture. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

**Why the pins don't move.** The `contingent_liability` spending tier is
`ltc_prem_yr + wellness_shock_yr`. On the frozen fixture both are zero in the
deterministic run that produces the pins: no `ltc_enabled`/`ltc_annual_prem`
is configured in its `client_assets.csv`, and `wellness_shock_yr` is only ever
populated from `c['wellness_shock_by_year']`, which `project()` never sets --
it is sampled per-path inside the Monte Carlo engines. So the new funding step
has nothing to draw and is a complete no-op on the pinned household. Confirmed
by running the golden-master gate before and after, not merely asserted.

**What changed.** `fund_contingent_liability_from_hsa` (`planning_engines.py`)
funds that tier from the HSA ahead of the ordinary withdrawal cascade, as a new
Priority 1b in `deterministic_engine.py` placed *before* the scheduled window
draw so the latter sizes itself against what remains. Both components are
qualified medical expense, so the draw is tax-free out and needs no
`hsa_owner_age`/penalty plumbing -- a qualified draw cannot produce the
non-qualified dollars carrying the pre-65 20% penalty.

Before this, neither component had any HSA-preferential treatment: the
deterministic engine calls `withdraw_hsa_window` with
`wellness_cost=row['wellness_base_yr']`, which is `wellness_premium_yr +
wellness_detail_budget_yr` and excludes both. The account designed for medical
costs was funding them only incidentally, via the generic cascade.

**This is a re-sourcing change, not a re-sizing one.** `total_spend` is
identical with and without the new step -- measured at $330,065.08 across all
four `hsa_withdrawal_mode` values on a probe household carrying a $12k LTC
premium. Only *which account pays* changes. The visible consequence is that an
affected household's HSA depletes earlier (on that probe: $74.5k -> $30.2k ->
$0 across 2026-2028 rather than lasting longer), with correspondingly more
taxable/pre-tax left intact -- which is the intended effect, and interacts with
the HSA terminal cliff that `hsa_terminal_tax` already models.

**Deliberately defers to `hsa_withdrawal_mode` rather than overriding it.**
Suppressed under `optimize`, and before and during the window under
`smooth_window`/`annual_pct`; resumes after the window ends. An unscheduled
draw stacked on a scheduled one is the shape of the real user-reported defect
fixed on 2026-08-20 (a $2,000/yr override that never appeared because
gap-fills drained the account years early). The gating predicate was therefore
*extracted* from `withdraw_hsa_gap` into a shared
`hsa_unscheduled_draw_allowed` rather than duplicated -- a copied-and-drifted
rule is exactly how that defect arose. Design rationale:
`docs/superpowers/plans/2026-08-26-contingent-liability-funding-rules-design.md`.

**Also gated: the vectorized MC engine's pre-existing wellness-shock HSA draw.**
`_mc_vectorized_projection` already drew sampled shocks from the HSA first, but
ungated -- which would now contradict the deterministic engine under scheduled
modes. It shares the predicate. **Consequence:** `monte_carlo()`'s
`success_rate` moves for households on `smooth_window`/`annual_pct`/`optimize`
that sample a wellness shock, because those shocks now fall to taxable in
window years instead of drawing the HSA the schedule has claimed. This is
intentional -- the two engines disagreeing about the same tier was the defect
-- not a regression. The premium half needed no wiring in either MC engine: it
propagates through the deterministic rows they consume (the scalar reruns
`project()`; the vectorized reads `eff['withdrawals']['hsa']`).

**Blast radius.** Bit-identical for households on `optimize`, inside an
`annual_pct`/`smooth_window` window, or with no contingent-liability spend at
all -- which includes the frozen fixture and the demo plan. Real for
`spend_as_needed` (the parse default) or post-window households configuring an
LTC premium, plus MC success rates as described above.

New coverage: `tests/test_contingent_liability_hsa_funding_regression.py` (15
tests). The two mode-deference guards were demonstrated red against a planted
"override the mode" defect before being trusted, per §3 rule 2.

## 2026-08-24/25 — Optimization-refactor Phase 1 items 2-6: no pins moved, but vectorized MC `success_rate` now differs by design for survivor-sensitive households

**Not a deterministic-engine change to any existing plan. Pins unchanged: `5,814,607.29 / 1,304,382.77`.**

**Why the deterministic pins don't move.** This work adds one new additive
deterministic-engine field (`row['gross_cash_flow_yr']`, derived from the
already-reconciled `cashflow_breakdown` income/draws sub-dicts) and a new
`_mc_survivor_bucket_flows()` helper in `planning_engines.py` that calls
`project()` on *overridden* configs (forced `h_death_yr`/`w_death_yr`
combinations) to build survivor-period trajectories for the vectorized MC
engine. The frozen fixture's own `base_rows = project(c)` call path — what
`test_frozen_sample_plan_golden_master_regression.py` pins — is untouched.

**What DID change, and is expected to.** Before this work, the vectorized
Monte Carlo engine (`_mc_vectorized_projection`) sampled each path's own
husband/wife death years but only used their *maximum* as an activity
cutoff — every path spent and paid tax as a continuously-married joint
household right up until the second death, regardless of when the first
spouse actually died. The scalar engine (`monte_carlo_exact_scalar`)
never had this gap (it reruns the full deterministic engine per path with
that path's own sampled death years, so survivor spending factor, Social
Security survivor-benefit switching, pension/annuity `js_pct` haircut, and
filing-status switching were already correct there). This closes the gap
in the vectorized engine by rerunning `project()` once per
(which-spouse-died-first, first-death-year) combination — not per path —
and blending each path into the bucket matching its own sampled first
death.

**Consequence:** `monte_carlo()`'s `success_rate` (and every dependent
figure: `liquid_pct_by_year`, `required_cut_distribution`,
`sustainable_spending_solve`, the new `spend_total_real`/`spend_<tier>_real`
matrices) now differs from pre-change output for any two-spouse household
with survivor-sensitive inputs (asymmetric ages, distinct Social Security
benefits, single-life annuities). This is intentional — the prior behavior
overstated joint spending/tax after a spouse's death — not a regression.
Gated by a new `mc_vectorized_survivor_economics` config flag, defaulted
`True` to match every other `mc_*` toggle in this codebase; kept only as an
emergency kill switch, not a rollout gate.

**Test expectations deliberately rewritten** (not just re-pinned) because
they encoded the bug as expected behavior:
`tests/test_optimization_phase1_mc_spend_by_tier.py`'s
`test_no_cut_paths_all_match_deterministic_real_spend` (asserted every path
saw identical spend for a given year with no cut applied, including years
after a sampled first death) → replaced with
`test_no_cut_paths_match_before_first_death_and_diverge_after`, which
asserts uniformity only holds before any path's own first death.

**Scalar-vs-vectorized agreement:** a real, double-digit-percentage-point
gap in `success_rate` remains even with this fix (see
`tests/test_scalar_vectorized_survivor_reconciliation.py`, gated behind
`RUN_SLOW_MC_RECONCILIATION=1` for CI speed) — the vectorized engine still
approximates tax with a single blended `tax_drag` ratio. Survivor economics
measurably narrows that gap (confirmed empirically, ~0.11 vs. ~0.135 at the
test fixture/seed) but closing it fully is Phase 3 of the optimization
refactor ("state-contingent tax approximation"), not this phase's job.

New coverage: `tests/test_survivor_bucket_alignment.py` (the bucket-ID
`spouse_first * n_years + year_idx` formula must be computed identically on
the write side, `_mc_survivor_bucket_flows`, and the read side,
`_mc_vectorized_projection` — a drift there would silently select the wrong
bucket for every path), `tests/test_vectorized_mc_survivor_economics.py`
(fixed-seed fixture proving spend/withdrawals diverge only after first
death), `tests/test_scalar_vectorized_survivor_reconciliation.py` (above).

Also fixed, as a separate commit (same PR, independently attributable):
`sample_household_death_years()` never set `first_death_yr`, mistiming the
Qualifying-Surviving-Spouse 2-year MFJ-extension window for every scalar-MC
path with `qss_dependent=True`.

## 2026-08-20 — Golden-master pin regenerated via `tools/regen_golden_master.py regen`

<!-- pin-provenance: terminal_nw=5814607.29 lifetime_tax=1304382.77 -->

**Old pins.** terminal_nw=5,821,763.41, lifetime_tax=1,303,155.26

**New pins.** terminal_nw=5,814,607.29, lifetime_tax=1,304,382.77

**Reason.**

Commit 332eac2 "DAF: stop double-deducting grants; gift appreciated shares
in kind" fixed a real double-deduction bug: daf_grant_yr was computed and
displayed but never actually netted out of the household's itemizable
cash-gift deduction, so a DAF grant year deducted the same charitable
dollars twice (once at contribution, again via undiminished giving intent
during the grant window). Grants are now netted the same way QCD dollars
already were.

The frozen fixture's contribution is cash (not appreciated shares), so the
commit's second fix (in-kind funding of appreciated gifts) is a no-op for
this pin -- the entire delta is attributable to the grant-netting fix alone,
per the commit's own stated verification (reverting only that line restores
the old pin exactly).

18 new tests in tests/test_daf_grant_deduction_and_inkind_funding.py, each
verified failing with its defect planted back, per that commit's message.

## 2026-08-19 — HSA withdrawal optimizer (H0–H5): no pins moved, and none could have

<!-- pin-provenance: terminal_nw=5821763.41 lifetime_tax=1303155.26 -->

*(Marker added when merging worktree-tickets-284-291 into main: this entry's own
prose already documents these exact values, but ticket 286's provenance gate,
`tests/test_golden_master_pin_provenance.py`, binds only to the machine-readable
marker, not prose -- see that file's docstring for why. Freshly computed on the
fully-merged tree and confirmed identical to this entry's pre-merge value, so
tickets 284-291's changes introduced no drift on top of the HSA optimizer's own
verified-unchanged pins.)*

**Not an engine change to any existing plan. Pins unchanged: `5,821,763.41 / 1,303,155.26`.**
Regenerated via `python -m tests.test_frozen_sample_plan_golden_master_regression` and confirmed
byte-identical to the value already checked in; `PINNED_FAILURES` (`[]`) also unmoved.

**Why zero movement is the correct, attributable outcome — not a missed regeneration.** This
16-task branch (`worktree-hsa-optimizer`) built a complete HSA drawdown scheduler: the terminal
tax cliff a non-spouse beneficiary owes (H1), decoupling withdrawals from current-year medical
spend (H2), a constrained schedule search that shares its objective with Roth conversion (H3), a
per-year override table with a precedence resolver and round-trip contract (H4), and workbook
disclosure (H5). None of it can move a single existing plan's numbers today, for two independent,
compounding reasons:

1. **The terminal cliff (H1) is exactly zero for the frozen fixture's beneficiary.** A spouse
   inherits an HSA tax-free; the fixture's `hsa_beneficiary_type` defaults to `spouse`, so
   `hsa_terminal_tax()` returns `0.0` and `estimate_after_tax_terminal_net_worth`'s new HSA term
   never has anything to subtract. This mirrors the frozen fixture's identical role in every prior
   cliff/reporting change on this codebase (`documentation/reports/PLANNER_SIGNOFF_2026-08-17.md`).
2. **`hsa_withdrawal_mode='optimize'` is not reachable from real plan data at all.**
   `src/data_io.py` coerces any value outside the three legacy modes (`spend_as_needed`,
   `annual_pct`, `smooth_window`) back to `spend_as_needed`; the UI schema offers the same three.
   The frozen fixture's own `client_assets.csv` sets `smooth_window`. So the schedule search
   (H3), the override table (H4), and the workbook disclosure (H5) never execute against any real
   household in this build — **no plan is affected, not "every plan except one that chose
   `optimize`," because that choice does not exist in this build.** This is intentional,
   deliberately-scoped, and recorded as an Open Item in
   `docs/superpowers/plans/2026-08-17-hsa-withdrawal-optimizer.md` — a future task must admit
   `'optimize'` in `data_io.py` and add the corresponding engine branch before this feature can
   affect a single client number. When that task lands, expect a real pin movement and a real
   golden-master regeneration, attributable to it alone.

**H2's decoupling (Tasks 5-6) is the one change in this scope that touches the three EXISTING,
already-reachable modes** — `withdraw_hsa_window`'s `spend_as_needed` path no longer caps a draw
at the current year's medical cost once a caller passes an explicit `requested` amount. This is
provably inert for every plan today too: the sole production call site
(`deterministic_engine.py`) still calls it with only `wellness_cost=`, never `requested=` — the
new parameter has no caller, so the branch it enables is exercised only by this branch's own unit
tests. Both facts (`mode='optimize'` unreachable, `requested=` never passed) were independently
verified in the Task 15 review by grep and by re-deriving the gating logic, not merely asserted.

**Verification.** Frozen golden master: 3/3 passed, pins unmoved. Fast tier
(`pytest tests/ -m "not slow" -q`, `grep -E "^(FAILED|ERROR|SUBFAILED)"` — see the `SUBFAILED`
project-memory note this branch surfaced at Task 12): clean apart from the pre-existing, unrelated
`test_withdrawal_sequencing_comparison_regression.py::test_current_plan_is_the_lowest_tax_and_highest_terminal_of_the_four`
failure (tracked separately; not caused by or fixed on this branch). `input/` unmutated throughout
all 16 tasks.

## 2026-08-18 — Household spending now responds to mortality (S1/S2/S3)

**Engine change. Pins move: `5,824,239.30 / 1,290,848.91` → `5,821,763.41 / 1,303,155.26`.**
Terminal net worth **down** $2,475.89; lifetime tax **up** $12,306.35. Both are net of two
opposing engine changes landing together — see the breakdown below before reading the totals as
one effect.

**What was broken.** Household spending did not respond to mortality at all. Measured on the
frozen fixture (`h_death_yr=2054`, `w_death_yr=2056`): `spend_base_yr` was byte-identical
(134,976.17) whether both members were alive, one was alive, or — on an extended horizon — both
were dead. Wellness already scales per-person and roughly halves at the first death; core
spending, housing, and every other component simply did not know anyone had died. Past the second
death the plan kept charging core spending and housing indefinitely, with figures that kept
inflating, producing an `unfunded_gap` for a household that no longer existed. The home was never
sold — `home_val` kept appreciating while the plan paid ~$85k/yr to carry a house nobody lived in.

**Origin.** Found while investigating Monte Carlo horizon truncation on an unrelated HSA
withdrawal-optimizer branch. Landed on its own branch (`worktree-survivor-estate-spending`, off
`main` @ `c79d805`) specifically so this movement stays attributable and separate from that work.

### S1 — survivor spending factor (moves NW up)

New `survivor_spend_factor` (schema `Household`, default **0.65**), applied to **exactly two**
components — core spending and recurring extras (travel/large-discretionary) — when exactly one
household member is alive. Deliberately **not** applied to housing (the survivor lives in the same
house), wellness/LTC (already per-person; stacking would compound two reductions to ~0.34 of
joint), lumps, or business expenses.

Gated on `household_size > 1`, not on the alive count alone: `data_io` forces
`w_death_yr = w_dob_yr` for a genuinely single-member household ("already dead"), so an ungated
factor would have scaled a single filer's *entire* plan by 0.65 — even though `spend_base` there
is already one person's spending. Confirmed on both the frozen fixture and the synthetic library:
`single_filer` is the one scenario left completely unmoved.

Direction: today's effective factor is 1.00, so 0.65 **reduces** survivor-year spending and moves
terminal net worth **up**. A change that makes plans look better gets more scrutiny, not less —
the acceptance tests pin survivor-year `spend_base_yr`/`rec_extra` directly against the both-alive
figures rather than inferring correctness from a terminal pin.

### S2 — estate-only spending after the second death (latent on a default horizon)

Once nobody is alive, every living-expense component of the spending assembly zeroes: core,
extras, lumps, all housing, wellness, LTC, business expenses, HELOC principal & interest. Taxes on
estate income are untouched. The ACA premium-credit recompute — a second site that rebuilds
`wellness_base_yr` from premium components — is guarded the same way, or it would have silently
resurrected spending the estate-mode block just zeroed.

**Latent by construction on a default-horizon plan**, because `plan_end = max(h_death_yr,
w_death_yr)` — the second death year itself — so a normal projection has no both-dead rows. Zero
effect on the pins above; verified with an extended horizon (`plan_end=2070` on the frozen
fixture) that every living-expense component and `unfunded_gap` are exactly 0.0 in every post-death
year, and that both-alive/survivor years are untouched by the estate-mode block.

### S3 — home sale at the second death (NOT latent — moves NW down, moves tax up)

Reuses the **existing** home-sale machinery (mortgage payoff, selling costs, gain, proceeds
routing) rather than new mechanics, triggered at the second death, with the existing death
step-up applied so the sale realizes no taxable gain.

**Unlike S2, this is not latent.** The sale trigger is `year == second_death_yr`, and that year is
*always* `plan_end` on a default horizon by construction — the sale fires on every plan, moved or
not. Isolated effect beyond S1 alone, measured on the frozen fixture: terminal NW **−$143,676.84**
(selling costs leaving the estate) and lifetime tax **+$12,306.35** (sale proceeds begin generating
taxable investment income in a Trust account a year earlier than illiquid home equity would have).

**A real defect was caught and fixed during implementation, not shipped.** The estate sale
initially reused `home_sale_px` — the user's assumed price for a *specific planned downsizing
transaction*, not a market-value forced disposition. On the frozen fixture that stale figure
(1,750,000) would have replaced the home's real appreciated value (2,954,344.94) at second death,
destroying **$1.53M** of estate value. Caught before commit by reading the diagnostic output line
by line rather than trusting a passing test suite — the pre-fix test only asserted
`home_sale_gross > 0`, which the bug also satisfied. Fixed (an estate sale always uses market
value; real planned-downsizing sales still respect `home_sale_px`) and a new test added asserting
the actual dollar figure, demonstrated failing against the reverted code before being trusted.

### Net effect on the pins

S1 alone: NW +$141,201, tax unchanged (survivor shortfall funded from Roth, so AGI is
bit-identical). S3 on top: NW −$143,676.84, tax +$12,306.35. Net: NW **−$2,475.89**, tax
**+$12,306.35** — a small net NW change masking two much larger opposing effects. Read the
per-component figures above, not the net, if attributing a future number to this change.

### Other suites this moved, both confirmed as consequences rather than defects

- **`tests/test_synthetic_golden_master.py`** — 9 of 10 scenarios move; `single_filer` does not
  (independent confirmation of the household-size gate). `early_survivor_compression` moves the
  most (+$4.01M NW), which is expected — it is the scenario built to stress a long survivor
  period, exactly where a previously-nonexistent survivor factor has maximal effect. Regenerated
  alongside the two named pins.
- **`tests/test_withdrawal_sequencing_comparison_regression.py::test_current_plan_is_the_lowest_tax_and_highest_terminal_of_the_four`**
  — the `proportional` strategy now edges `current_plan` on terminal NW by ~0.88%
  (1,486,978.06 vs 1,473,968.52); the lifetime-tax half of the assertion still holds. That test's
  own fixture docstring already documents this comparison as fragile ("ranked against each other
  by margins well under a percent, so a stale quote flips them"). Confirmed against the unmodified
  engine (S1–S3 stashed, test rerun) that the comparison passes cleanly on `origin/main` — this
  branch's change closed an already-thin, self-documented-fragile margin with real, substantial
  engine changes, not noise. **Left unresolved and unmodified**: fixing the withdrawal-sequencing
  engine is outside this branch's ownership, and a blind edit to code this change doesn't
  understand is worse than leaving an honest, logged finding for separate review.

### Verification

`tests/test_survivor_spending_regression.py` — 16/16, including two guards mutation-tested red on
a planted defect before being trusted (the market-value fix above, and the death step-up). Frozen
and synthetic golden masters both green after regeneration. `input/` unmutated throughout.
## 2026-08-18 — Ticket 286: golden-master recovery tooling and a test-enforced provenance gate

<!-- pin-provenance: terminal_nw=5824239.30 lifetime_tax=1290848.91 -->

*(The marker above is the machine-readable binding read by
`tests/test_golden_master_pin_provenance.py`. It records which changelog entry the pin
file's provenance line points at. Prose restating pin values is deliberately NOT a
binding, because entries about unrelated work routinely restate unchanged pins.)*

**What changed.** No projection figures move; pins stay at 5,824,239.30 / 1,290,848.91. This is
process tooling, not an engine or fixture change.

Added `tools/regen_golden_master.py` (`measure` / `verify-endpoint <sha>` / `origin <value>` /
`regen --reason <file>`) and `documentation/GOLDEN_MASTER_RECOVERY_RUNBOOK.md`, mechanizing the two
method traps recorded in the 2026-08-10 postmortem
(`docs/superpowers/plans/2026-08-10-golden-master-and-at-rest-plan-data-migration.md`, "Phase 1"):
`git bisect` never re-verifies the "good" endpoint you hand it (`verify-endpoint` checks it first,
in a detached worktree, before you bisect), and plain `git log -S` can name the wrong origin commit
when a rename hides a value's history (`origin` always uses `--follow`). The runbook's decision tree
adds the third branch the original postmortem said was missing beside "intentional" and
"regression": **"the pin never matched"** -- verify at the introducing commit before bisecting
anything.

Added a test-enforced provenance gate, `tests/test_golden_master_pin_provenance.py`. It parses the
single-line `# <date>: PINNED_TERMINAL_NW=... PINNED_LIFETIME_TAX=...` comment directly above the
pin constants in `tests/test_frozen_sample_plan_golden_master_regression.py`, and fails if either (a)
that line is missing, (b) its recorded values don't match the actual `PINNED_*` constants (catches a
hand-edited pin whose comment was left stale -- a naive "is there a comment?" check would pass this),
or (c) its date doesn't match this changelog's newest entry. `tools/regen_golden_master.py regen`
updates the pin constants, the provenance line, and this changelog together, so the only way to move
a pin without a recorded justification is to bypass the tool -- which now turns the suite red.

## 2026-08-17 (b) — Sheet 3A stops crediting the liquidity buffer with mitigating sequence risk (P7, P3, P5)

**What changed.** Three follow-ups from `documentation/reports/PLANNER_SIGNOFF_2026-08-17.md`. **No
projection figures move**; pins stay at 5,824,239.30 / 1,290,848.91.

**P7 — the narrative sections contradicted the disclosure shipped one section above them.** Sheet 3A
section G told the reader that *"the configured liquidity buffer (Trust accounts) is the primary
mitigation"* for sequence-of-returns risk, and section E's quintile note said the Reserve requirement
lets the plan ride out early bear markets *"without forced selling"*. Both are client-facing advice,
and this engine supports neither:

1. Trust maps to the **taxable** bucket, and within a bucket every account takes the same annual
   market shock (S1). A reserved dollar is exactly as exposed to an early bear market as any other
   taxable dollar.
2. What the buffer actually does is set a floor under the taxable draw
   (`liquidity_buffer_years_for_year`, consumed by `withdraw_taxable_trust`). That is a withdrawal
   **order** preference — it redirects spending into other buckets. It never changes any dollar's
   volatility, and the model has no forced-selling mechanic for it to avoid.
3. That floor is applied in the deterministic cascade only. The vectorized MC scales the
   deterministic engine's planned bucket withdrawals and never re-enforces the floor against shocked
   balances.

Both passages now rest on what *is* modeled: the cascade spends cash-type accounts first and cash
grows on a short-rate path rather than the equity draw, so reserves held **in a cash account** are
genuinely insulated — and the configured buffer is named as the different, non-protective mechanism
it is. Roth conversions keep their claim in section E, because the conversion and its tax are
simulated on every path.

The sign-off offered a second option — "move the buffer into a cash-type account so the claim becomes
true". **That option does not exist as configuration.** A Liquidity Buffer row's `reserve_account`
field (`Taxable/Trust | Roth | IRA | HSA | Cash`) is written, stored and round-tripped by the UI and
read by **nothing** in the engine; the floor is applied to the taxable bucket regardless of its value.
Only holding the reserve in an account whose registry `tax` is `cash` gets the modeled treatment. The
inert field is a separate defect, recorded as a new follow-up rather than fixed here.

Audit of section G's remaining claims against S1: *Overall Plan Assessment*, *Return Assumption
Stress* and the Q1 figure in *Annuity Income as a Floor* are computed values; *When to Take Action*
and *Recommended Annual Review* are review triggers, not model claims. Those five stand.

Guarded by `test_monte_carlo_sheet_does_not_credit_the_liquidity_buffer_with_mitigating_sequence_risk`,
which resolves the sheet through `stable_name_for_sheet_title` rather than a hardcoded `3A.`. Per §3
rule 2 each of its three assertions was demonstrated red **individually** against a real build: the
section G claim, the section E claim, and the positive assertion that the correction is present (a
guard that only forbids phrases passes on a sheet that says nothing at all).

**P3 — `test_bucket_return_tilts_are_dollar_weighted_and_market_neutral` renamed** to
`test_bucket_return_tilts_are_dollar_weighted` (S3). The neutrality half of the name never had an
assertion behind it, which is how the tilt drift went unnoticed; neutrality is now genuinely covered
by `tests/test_mc_bucket_tilt_neutrality_regression.py`. Body unchanged.

**P5 — the two MC paths no longer disagree about cash** (S5). `_apply_account_return_adjustments`
(scalar/loop path) tilted **any** account present in `account_returns`, cash-tax or not, while
`_mc_bucket_return_tilts` (vectorized path, which produces the headline success rate) excludes cash
and grows it on the short-rate proxy. The scalar path now applies the same exclusion. On the frozen
fixture the paths agreed only by accident — its cash accounts hold nothing that maps to a CMA class,
so they never reach `account_returns` — which is why no existing test could see this. New guard
`tests/test_mc_cash_tilt_path_parity_regression.py` uses the fixture S5 named (a money-market fund
that *does* map to a CMA class, inside a cash account) and was demonstrated red on the pre-fix engine.
It also pins that non-cash accounts keep their tilt, since "stop tilting entirely" would otherwise
pass. **Blast radius:** plans holding a CMA-classifiable security in a cash account — previously the
scalar MC grew those dollars at the equity return plus a tilt. Plans without one are bit-identical.

## 2026-08-17 (d) — The Liquidity Buffer's reserve_account is now honored (P8), and the insurance sheet stops printing example dollars (P9)

**Golden pins unmoved** at 5,824,239.30 / 1,290,848.91, and that is the design, not a
coincidence — see "Blast radius" below.

### P8 — `reserve_account` was a live control wired to nothing

A Liquidity Buffer row's `reserve_account` (`Taxable/Trust | Roth | IRA | HSA | Cash`) is rendered as
a dropdown, persisted to `client_assets.csv`, and validated against `reference_data/schema.csv`. No
engine code read it. `withdraw_taxable_trust` applied the reserve floor to the **taxable** bucket
unconditionally, so selecting "Roth" did two wrong things at once: it left Roth fully drainable, and
it held back a bucket the user never named.

**What changed.** `liquidity_buffer_for_year` now returns `(years, bucket)`, and a new
`liquidity_reserve_floor(c, year, bucket, spend_floor_base)` returns the floor that applies to one
bucket — zero when the reserve names a different one. It is applied in four draws:
`withdraw_taxable_trust`, `withdraw_roth`, `withdraw_pretax_elective`, and `withdraw_hsa_gap`, with
`spend_floor_base` threaded through all six deterministic-cascade call sites.

Two consequences beyond the withdrawal floor, both deliberate:

- **`trust_surf` no longer subtracts a non-taxable reserve.** Trust headroom feeds
  `non_roth_surplus`, which caps Roth conversions; subtracting a Roth or HSA reserve from the
  *taxable* balance understated conversion capacity.
- **An IRA reserve now also caps conversions.** Converting pre-tax dollars to Roth empties the
  bucket the reserve is meant to preserve exactly as spending them would, so `ira_total` is net of
  the pretax floor.

**Cash is honest about being a no-op.** The deterministic cascade's priorities are RMD, HSA, pre-tax
elective, taxable/trust, Roth, home equity — cash-tax accounts appear in none of them, so a cash
reserve is preserved by construction and there is no draw to constrain. Rather than leave that
implicit, `liquidity_reserve_floor(..., 'cash', ...)` returns the correct number for a future cash
draw to use, and `CashReserveTests` pins the situation so that whoever adds one is told to apply it.
The UI help text and the schema description now say this outright.

**Blast radius.** Any plan whose `reserve_account` is the schema default `Taxable/Trust` — including
the frozen fixture and the demo plan — is **bit-identical**, because the floor lands exactly where it
always did. Unrecognized and blank values also fall back to taxable, so no stored plan can shift by
reinterpretation. Plans that selected Roth/IRA/HSA change: the named bucket is now preserved and
taxable is not, which is what the setting always claimed to do. IRA reserves additionally see smaller
recommended conversions. Guard: `tests/test_liquidity_reserve_account_regression.py`, 12 cases.
Demonstrated per §3 rule 2 by planting the pre-P8 semantics (floor forced back to taxable-only):
7 of the 12 went red, and the 5 that held are the deliberate pins — the working taxable case, the
year-range check, and the two fallbacks — which must be insensitive to this change.

### P9 — the insurance sheet printed example dollars as advice

Same class as C2, at a location C2 never named (found by P6). On `19. Life Insurance`:

- `'★ RECOMMENDED — $500K face, start 2027, ~$18,500/yr'` sat in the same table row whose Death
  Benefit column renders the **configured** `ltc_face`, so any household with different settings got
  a row that contradicted itself. Now derived from `ltc_face`/`ltc_start_year`/`ltc_annual_prem`, or
  stated as not configured.
- `'Consider if IL estate tax > $320K materializes'` — C2's exact figure, computed nowhere. Now
  derived from `summary_figures.credit_shelter_trust_savings`, the same helper Sheets 1 and 14 share.
- A flat `$500,000` **Estate Liquidity Buffer** need, sitting one row beneath Section B's own note
  boasting that these needs come from the household's projection "not a generic income multiple". Now
  `estimate_terminal_estate_tax(c, rows[-1])` — the tax actually projected at the terminal estate,
  which is what an illiquid estate must raise cash for.
- A closing recommendation naming a specific commercial product (`Lincoln MoneyGuard`). Removed; the
  closing paragraph now describes this plan's own configuration and labels the premium table as
  indicative market pricing rather than quotes.
- **A dead `is_optimal`**: it computed which coverage row matched the client's configured face and
  was then discarded — every cell keyed off a `'★'` baked into the $500K description string, so every
  client was shown $500K as "OPTIMAL" regardless. The highlight now follows the configured face.

Guarded by `test_insurance_sheet_prints_no_client_independent_dollar_figures`. All seven of its
assertions — five forbidden strings and two positive ones — were demonstrated red against a real
pre-fix build. Section B's gap arithmetic changes for every plan (the estate-liquidity need is now
computed rather than $500,000); this is reporting only and moves no projection figure.

## 2026-08-17 (c) — C5's guard could not fail; rewritten (P6). No engine change.

**What changed.** Test only. `tests/test_roth_objective_deflator_regression.py`'s
`test_terminal_component_is_discounted_below_nominal_after_tax_nw` now asserts on
`terminal_wealth_score` — the value that actually enters the Roth objective's score — instead of on
arithmetic it performed itself.

**Why.** The old body computed `expected_pv = after_tax_terminal_nw / (1+d)**n` and asserted
`expected_pv < after_tax_terminal_nw`. That is true by arithmetic for any positive discount over any
horizon longer than zero years. It never read the objective. Reverting
`after_tax_terminal_nw_pv` (`planning_engines.py:1917`) to the nominal figure restores finding C5's
defect in full — plan-end wealth weighted undiscounted against discounted lifetime tax and estate
tax — and **both tests in the file stayed green**.

Against the same planted defect the rewritten test fails at **6,185,244 vs 2,948,770**: the objective
would have been weighting terminal wealth at 2.1x its present value, which in long-horizon plans
systematically over-rewards deferring wealth into the far future. The test pins
`roth_objective_mode='MAXIMIZE_PTI'` so the terminal weight is a known 1.0 rather than whichever
branch the fixture happens to select, and rejects the nominal figure explicitly so a regression
cannot pass by coincidence.

**The engine was and is correct** — all four `terminal_component` branches use the PV, at the same
discount as the tax and estate terms, while the reported `after_tax_terminal_nw` and
`post_tax_inheritance` stay nominal. **No figures move and no pins change**; this closes a hole in
the protection, not a hole in the math. Found by P6's second look at C1/C2/C5
(`documentation/reports/PLANNER_SIGNOFF_2026-08-17.md` §5), which also confirmed C1's and C2's fixes
and logged two surviving C2-class hardcoded figures on the insurance sheet as P9.

## 2026-08-17 (b) — Sheet 3A stops crediting the liquidity buffer with mitigating sequence risk (P7, P3, P5)

**What changed.** `_mc_apply_bucket_growth` now subtracts the balance-weighted mean tilt of the
current step's bucket mix before applying the per-bucket tilts.

**Why.** The tilts are computed once, from the OPENING balance mix
(`_mc_bucket_return_tilts`), and were then applied unchanged for the entire horizon. The mix does not
hold still: withdrawal sequencing and RMDs drain the negatively-tilted pretax bucket, and Roth
conversions actively move dollars into the positively-tilted Roth one. So a tilt set that netted to
approximately zero at t=0 became a systematic tailwind. Measured on the frozen fixture, the effective
portfolio-wide tilt drifted monotonically:

    2026 +4.3 bps -> 2036 +7.6 -> 2046 +15.0 -> 2056 +24.9 bps

That is invented return, applied on every path, and concentrated in exactly the late years where
Monte Carlo success or failure is decided. Worse, it was **self-reinforcing for the engine's own
advice**: converted dollars inherit the destination Roth account's holdings tilt, so every dollar the
optimizer recommends converting was thereafter assumed to earn ~30 bps more, and the conversion
analysis ranks strategies by success rate.

`_account_return_tilt`'s docstring already asserted the correct property -- tilts "preserve the plan's
expected return as the portfolio-wide average while letting asset location redistribute it". This
makes that true at every step rather than only the first. After the fix the realized portfolio growth
equals the sampled return to floating point in **every** projection year (worst |excess| 0.000000 bps).

**The spread between buckets is untouched**, which is the actual Wave 3.5 deliverable -- only the
portfolio-wide mean is removed. A fix that zeroed the tilts would satisfy neutrality while silently
undoing asset location, so that is pinned by its own assertion.

**Golden master unmoved.** `_mc_apply_bucket_growth` is reached only from the vectorized Monte Carlo
path; the deterministic projection that produces the pinned figures never calls it. Pins stay at
5,824,239.30 / 1,290,848.91, verified green.

**Blast radius.** Monte Carlo success rates move **down slightly** in plans with holdings detail --
correctly, since they were carrying up to ~25 bps of unearned return late in the horizon. Plans
without holdings detail produce no tilts and are bit-identical, which is pinned. No stored data
changes. Expect modestly **less** favorable Roth-conversion rankings where the tailwind was doing the
work.

**Client-facing disclosure shipped alongside (S1/P4).** Sheet 3A (Monte Carlo) section A now states
what the tilt model does and does not support: per-account holdings differences enter as a constant
per-bucket offset, not sleeve-level volatility, so within the taxable/pretax/Roth/HSA buckets every
account takes the same annual shock. The success rate therefore **cannot** credit a bond tent or
de-risking glidepath held inside retirement accounts with reducing failure risk. Cash accounts are
the exception — they grow on a short-rate path and are genuinely modeled as low-volatility. No
figures move; this is disclosure, guarded by
`test_monte_carlo_sheet_discloses_the_asset_location_modeling_limit`.

**Provenance.** Found by `documentation/reports/PLANNER_SIGNOFF_2026-08-17.md` (finding S2), which
also documents why the existing test named `..._and_market_neutral` did not catch it: it checks dollar
weighting and never checks neutrality (S3). New guard:
`tests/test_mc_bucket_tilt_neutrality_regression.py`, demonstrated red against the old code first --
its all-Roth end-state case failed by exactly the +24.87 bps the fixture measurement predicted.

## 2026-08-12 (e) — Roth discount rate defaults to 6.5% nominal, decoupled from inflation

**What changed.** `roth_tax_discount_rate` defaulted to `c['inf']` (2.50%). It now defaults to
`DEFAULT_ROTH_TAX_DISCOUNT_RATE = 0.065`.

**Why.** The rate is applied to NOMINAL flows — lifetime tax, estate tax, the ACA PTC loss, and the
terminal-wealth component are all projected in nominal dollars — so it has to be a nominal rate.
Defaulting it to inflation made it a pure *deflator*: it restated the objective in today's purchasing
power and applied no time preference on top, i.e. a **0% real discount rate**. That systematically
under-rewards locking in current tax rates, because future tax savings were discounted more slowly
than the portfolio generating them compounds. 6.5% is roughly the expected long-run portfolio return —
what a dollar handed to the IRS today would otherwise have earned.

**Inflation itself is unchanged.** `c['inf']` is untouched; only the discount rate's *fallback to it*
is removed. They were never the same quantity, and the coupling meant editing an inflation assumption
silently retuned the optimizer's time preference — a test now pins that two plans with different
inflation assumptions get the same discount rate.

**Blast radius.** This moves the DEFAULT only. Any plan with an explicit stored value keeps it, so no
existing household's numbers change on upgrade. Expect **larger optimizer-selected conversions** in
plans that were relying on the default, particularly long-horizon ones — the correct direction given
the objective was under-valuing early conversions, but it is a visible change in recommendations.

**Golden master unmoved.** The frozen fixture sets 2.50% explicitly rather than inheriting, so the
dollar-exact gate does not move. That is deliberate and worth keeping: a fixture that pins its own
assumptions cannot be silently re-scored by a future default change. The new default is covered by
`tests/test_roth_discount_rate_default_unit.py` instead.

Also updated: `reference_data/schema.csv` (default + help text now say *nominal*, and point at
portfolio return rather than inflation) and `input/demo/client_policy.csv`. `planning_engines`' own
fallback, which could previously drift from the parse default, now shares it via
`_roth_discount_rate()`.

## 2026-08-12 (d) — Correcting (c): the units were wrong and the headline path was still untouched

**(c) below is superseded.** It is kept because its diagnosis of the *problem* is right; its claim
to have fixed it is not. Two defects, both found by reviewing the landed diff against real fixture
data rather than against the unit tests that shipped with it.

**1. The units were wrong — every simulated return roughly doubled.**
`c['account_returns']` holds **absolute** expected rates: `data_io.py:~2425` writes
`_base_ret + (acct_ret - portfolio_ret)`, the plan return plus that account's tilt. (c)'s
`_apply_account_return_adjustments()` treated each value as a **delta** and added it to the sampled
portfolio return. Measured on the frozen fixture, with `c['ret']` = 5%:

| | sampled 2030 return | account rate | (c) produced |
|---|---|---|---|
| `Member_1_IRA` | 0.0550 | 0.049763 | **0.104763** |
| `Member_1_Roth` | 0.0550 | 0.052510 | **0.107510** |

What transfers onto a path that already carries its own sampled portfolio return is the **tilt**,
`account_returns[acct] - c['ret']`. Extracted as `_account_return_tilt()` so the convention has one
home. Tilts are dollar-weighted to ~zero across the portfolio, so the plan's expected return is
preserved as the portfolio average while asset location redistributes it — which is the point of C3.

**2. Only the scalar MC path was wired; the headline number never moved.**
(c) set `return_by_account_by_year` in `_run_one_mc_path()` — the scalar path. The **vectorized**
path (`_mc_vectorized_projection`) still grew every bucket at one identical rate
(`balances[b] * (1.0 + growth)`), and that is the path that produces the reported success rate. So
the number a user sees was unchanged by Wave 3.5 *and* by (c).

This is the third occurrence of one failure mode, and the review named it in advance (§2.5,
*"a change that looks done because the thing you inspected changed"*): the deterministic path was
fixed in Wave 3.5, the scalar path in (c), the vectorized path in neither.

The vectorized path evolves tax **buckets**, not accounts, so per-account tilts are collapsed by
`_mc_bucket_return_tilts()` — dollar-weighted, because a $10k bond-heavy IRA and a $1M one cannot
move the pretax bucket equally. `cash` is deliberately excluded: that bucket already grows on a
short-rate proxy tied to inflation, not the equity draw. On the frozen fixture the resulting tilts
are `pretax -0.000538`, `roth +0.002487`, `hsa +0.003018`, `taxable +0.001333` — bonds in the IRA
suppressing future RMD growth, the Roth compounding fastest, exactly the behavior C3 asked for.

**Expected movement.** Monte Carlo success rates and MC-derived figures move; every deterministic
figure is unchanged, and the frozen dollar-exact gate is unmoved (it runs `project()`, which was
already correct). A plan with no holdings detail yields an empty tilt dict, which is bit-identical
to the previous behavior — so plans that never had asset-location data are not disturbed.

**Guarding it.** `tests/test_monte_carlo_per_account_returns_wave35.py` now pins the convention
against real fixture data (`test_real_account_returns_do_not_double_the_simulated_return`) and
asserts the vectorized growth step itself responds to tilts, rather than asserting only on a helper
that can be correct while the shipped path is inert. (c)'s own tests passed throughout both defects
because they fed synthetic deltas — they encoded the implementation's assumption instead of the
data's contract.

**Also fixed here:** (c) rewrote this file's stored line endings LF → CRLF, changing all 1,209 lines
and destroying `git blame` for the whole changelog. Renormalized to LF, matching every other text
file in the repo.

## 2026-08-12 (c) — Monte Carlo per-account returns enabled (Wave 3.5 completion, F1.1-F1.3) — SUPERSEDED by (d)

**What changed.** Wave 3.5 populated `c['account_returns']` with per-account returns based on
holdings mix (asset location), but only the deterministic path used them. Monte Carlo applied a
single blended return to all accounts regardless of their allocations, which meant:
- Asset-location arbitrage plays (different accounts, different returns) were invisible in MC
- The headline success rate (which ranks all our multi-account conclusions) used wrong numbers
- The number-moving changes in Wave 3.5 looked complete because the inspection changed; the MC
  path remained half-fixed

**Fix (F1.1).** Route Monte Carlo paths through per-account returns:
- Added `_apply_account_return_adjustments()` to build `return_by_account_by_year` dict from base
  returns and per-account deltas
- Modified `_account_return()` to check `return_by_account_by_year[account_id][year]` first,
  then fall back to uniform `return_by_year[year]`  
- Modified `_run_one_mc_path()` to populate `return_by_account_by_year` before projection

**Test (F1.2).** Acceptance tests verify:
- The per-account routing is wired (4 unit tests, all passing)
- The old behavior (uniform returns) vs. new (divergent per-account) paths are distinct

**Pins.** Frozen master pins are UNCHANGED: **5,824,239.30 / 1,290,848.91**. The Monte Carlo
changes only affect MC paths (`monte_carlo_exact_scalar`), not the deterministic projection
that seeds the frozen gate. Per-account MC paths will show in downstream success-rate outputs,
but this gate (which measures one deterministic run) is unaffected. The fix is verified by:
- Full-suite tests passing (deterministic frozen fixture is byte-identical)
- Unit tests for MC per-account routing (F1.2, 4/4 passing)
- Integration tests in the regression suite (F4.1 sign-off, TBD)

## 2026-08-12 (b) — The frozen gate was measuring the machine, not the fixture (real fix + re-pin)

**What was wrong.** `src/data_io.py`'s `parse_client()` handed
`spending_budget_resolver.apply_budget_to_engine_config()` an explicit
`root=Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` — the repo root,
computed from `__file__`. Everything reached through that root ignored
`RETIREMENT_SYSTEM_WORKSPACE_ROOT`: `client_spending_budget.csv`,
`client_spending_taxonomy.csv`, and `client_optional_functions.csv` were always read from
the repo's own `input/` directory. The frozen fixture ships its own copies of all three.
They were never read.

This is the same landmine the test file's module docstring describes as fixed — a
hardcoded `root=` defeating the workspace redirect — surviving in a second module that
the original fix never touched.

**Why it produced two different answers.** `/input/*` is gitignored, so what sits in that
directory is a property of the checkout, not the commit:

| Environment | What the resolver found | Terminal NW |
|---|---|---|
| Fresh checkout, git worktree, CI | nothing — falls through to legacy fallbacks | 6,044,750.40 |
| A warm working copy | the developer's **live** plan | 5,824,239.30 |

Neither reading involves the fixture. The gate passed in CI and failed locally **at the
same commit, with byte-identical fixture and engine** — verified by running `a2693ea` in
both a warm working copy and a clean worktree.

**This supersedes the 2026-08-10 entry below.** That analysis was sound in its own terms
and its conclusion — "the computed value is identical across six commits, two
interpreters, and two machines" — was true. But every one of those measurements was taken
in a fresh-checkout environment, so they were all measuring the same fallback path. The
agreement was evidence of a shared environment, not of a correct pin. Bisect and
per-commit measurement cannot see a defect that is constant across all commits.

**What changed.**
- `src/data_io.py`: dropped the hardcoded `root=`, so spending resolution honors
  `RETIREMENT_SYSTEM_WORKSPACE_ROOT` like every other plan-data lookup. **This is a
  production fix, not a test fix** — any run under a custom workspace root (the e2e
  server, a multi-workspace build) was resolving spending against the wrong directory.
- Pins re-generated to **5,824,239.30 / 1,290,848.91**, which the frozen build now
  produces identically in a warm working copy and in a clean worktree.
- New guardrail `test_frozen_build_reads_its_own_spending_budget_not_the_live_one` fails
  if any spending input is ever again resolved from outside the redirected workspace.
  The pre-existing holdings guardrail could not catch this: it only covers files resolved
  through `candidate_input_files`, and the spending budget does not go through that path.

**Does re-pinning mask an engine regression?** No. The engine is unchanged — the same
commit computes 5,824,239.30 in both environments once the redirect is honored, and the
two withdrawal-semantics commits in the range (`7a263e6`, `91ab5fe`) were measured
individually and moved nothing here.
## 2026-08-12 (a) — Removing the duplicate copy of that same stale pin (no engine change)

> **⚠ Premise corrected by entry (b) above, which was written later the same day and supersedes this
> one's diagnosis.** The pins this entry calls "stale" — 5,824,239.30 / 1,290,848.91 — were the
> *correct* figures for the frozen fixture; 6,044,750.40 / 1,465,666.69 was the artifact, produced
> only where the repo's `input/` is empty. The evidence cited below ("byte-identical at `f454117`,
> `56c457a`, `e8eeb2e`, `ff8350d`, `91ab5fe` and `main`, across three consecutive runs") was gathered
> entirely in that one environment, so it measured the same fallback path every time.
>
> **The action taken below still stands and was not reverted.** De-duplicating the pins was right for
> an independent reason — two files holding one pair of numbers is a drift hazard regardless of which
> pair is correct — and the two documentation fixes are correct and load-bearing. Only the "which
> number is real" reasoning is wrong. The surviving pin now carries entry (b)'s values.

**What was wrong.** The 2026-08-10 entry below corrected
`PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` in
`tests/test_frozen_sample_plan_golden_master_regression.py` from
5,824,239.30 / 1,290,848.91 to the values the frozen fixture actually computes,
6,044,750.40 / 1,465,666.69. It missed a **second copy of the same two numbers**
in `tests/test_recommendations_functional.py`, which still held the stale pair
and emitted this on every full test run:

    UserWarning: golden-master baseline drift: terminal_total_nw = 6,044,750.40
    (pinned 5,824,239.30, delta +220,511.10)
    UserWarning: golden-master baseline drift: lifetime_tax = 1,465,666.69
    (pinned 1,290,848.91, delta +174,817.78)

**No engine change, again.** The warning's own text says "if the plan data did
NOT change, investigate the engine", so the engine was investigated first. Both
figures are byte-identical at `f454117`, `56c457a` (the commit that wrote the
pins), `e8eeb2e` (DAF optimizer), `ff8350d` (per-account withdrawal draw-order),
`91ab5fe` (withdrawal-comparison semantics) and `main` — and across three
consecutive runs at a fixed commit. A number that does not move across the
entire DAF/draw-order/withdrawal-comparison body of engine work is not drifting.
The pin was wrong when written, exactly as in the entry below.

**Why the warn-only rationale no longer applied.** That helper existed because
"these baselines move whenever the sample client's data is edited, which is a
routine event." That stopped being true once `tests/conftest.py` began staging
`input/` from the committed `tests/fixtures/sample_plan_frozen/` and pinning the
clock with `RETIREMENT_SYSTEM_FROZEN_TODAY` — which it already did at
`56c457a`. With frozen data, frozen date and frozen prices, a move in these
dollars can only be an engine change, so downgrading it to a warning removed the
protection without removing the maintenance burden.

**What changed.** Deleted the duplicated dollar pins and the
`_warn_on_baseline_drift` helper from `test_recommendations_functional.py`,
rather than re-pinning a second copy — having the same two numbers in two files
is what let the 2026-08-10 correction land in only one of them. That test keeps
its structural gate (`fail_count`/`warn_count` zero, full 2026-2056 horizon).
Absolute dollars for this household are now asserted in exactly one place,
`test_frozen_sample_plan_golden_master_regression.py`, to the cent.

Also corrected two stale docs that pointed maintainers at the live plan:
`documentation/CLAUDE.md`'s "Golden master maintenance" regen snippet read
`input/client_data.csv` (gitignored real client data, absent on CI and in any
fresh worktree) — running it reproduces the original defect, since it prints
figures for whatever household the author last saved rather than the frozen
fixture the test pins. It now points at the authoritative test's own `__main__`
regen block. `test_tax_loss_harvesting_functional.py`'s docstring made the same
"live, routinely edited" claim and referenced the now-deleted helper.

**Verification.** Full `pytest -m "not slow"`: all pass, zero warnings.
`test_frozen_sample_plan_golden_master_regression.py` passes unchanged, still
pinning 6,044,750.40 / 1,465,666.69. *(That last clause is what entry (b)
corrects: it passed because it was being measured in the same fresh-checkout
environment that produced the wrong number.)*

## 2026-08-10 — Correcting a stale pin that never matched (no engine change)

**What was wrong.** `PINNED_TERMINAL_NW` / `PINNED_LIFETIME_TAX` in
`tests/test_frozen_sample_plan_golden_master_regression.py` held 5,824,239.30 /
1,290,848.91, but the frozen fixture and engine compute **6,044,750.40 / 1,465,666.69**
— and always have. This gate has been failing since the day it was authored and had
never passed once.

**How that was established.** Running the test file's own `__main__` regen block at
`77b7676` — the commit that introduced 5,824,239.30, per the entry immediately below —
already prints 6,044,750.40. So does every commit after it (`56c457a`, `52ffe60`,
`3b1cedf`, `531c883`, `355564d`, `main`), and so does CI on both windows-latest/3.11
and windows-latest/3.14, agreeing to the digit: `6044750.402866955`. The frozen fixture
is byte-unchanged since `56c457a`. A value that is identical across six commits, two
interpreters, and two machines is not drift.

**Root cause.** The 2026-08-05 entry below documents the home-purchase regeneration and
states the new pins in prose, but the two constants in the test file were never edited
to match. The entry's "4 failures → 0" claim did not cover this test: it carries
`@pytest.mark.golden_master`, not `slow`, so `-m "not slow"` would have run it.

**Why nobody noticed.** CI on `main` was red for several unrelated reasons — a hardcoded
`C:\RetirementPlanning\Version 10\...` absolute path in 33 test files, `input/*.csv`
absent on the runner (`/input/*` is gitignored), no `npm ci` in the Python test job, and
Playwright e2e timeouts — so one more red test did not stand out. Those are addressed in
the follow-up commit; the e2e timeouts are not.

**What changed.** Only the two constants, corrected to the values the fixture actually
produces, plus a provenance comment. No `src/` change; correcting them cannot mask an
engine regression because the computed value never moved.

## 2026-08-05 — Frozen fixture gains a home-purchase scenario (fixture data change)

**What was wrong.** `tests/test_cashflow_chart_home_purchase_down_payment.py` was
originally written against the live household's real Housing next_step_1 configuration
(Florida, $1,000,000 @ 80% down in 2038). Once the test suite migrated onto the frozen,
self-contained fixture (`tests/fixtures/sample_plan_frozen/`), that fixture had no
equivalent purchase scenario — its Housing next_step_1 row was entirely blank — so all
4 tests in the file failed outright with `StopIteration`.

**What changed.** Added a fictional purchase scenario directly to the frozen fixture's
Housing next_step_1 row: Texas, $400,000 @ 27% down = a $108,000 down payment in 2036
(picked to comfortably clear the test's own `> $100,000` floor while minimizing the
LTCG realized funding it, tried across several years/amounts). Also widened
`test_excel_expense_and_income_bars_reconcile_in_the_purchase_year`'s reconciliation
tolerance from $1,000 to $2,000: even at the minimum viable down payment, funding it
from this household's taxable Trust realizes ~$1,666 in real LTCG tax that
`build_sheet8`'s fixed column layout doesn't itemize (a documented, pre-existing,
unrelated gap) — the original $1,000 tolerance was calibrated against the real
household's different gain profile, not a universal constant.

**What moved and why.** This is fixture *data*, not an engine change — buying a
$400,000 house is a real, deliberate addition to the household's cash flow, so the
golden master moving is expected drift, not a regression to investigate.
`PINNED_TERMINAL_NW` 6,995,542.24 → **5,824,239.30**, `PINNED_LIFETIME_TAX`
1,362,412.33 → **1,290,848.91** (the down payment and its LTCG tax draw down the
portfolio; both figures are lower with the purchase than without it).
`test_2_recommendations.py`'s warn-only pins updated to match.

Full `pytest -m "not slow"` suite: 4 failures → **0**. Full workbook + PDF build and
the synthetic golden-master gate verified green.

## 2026-08-05 — Wave 3 engine-correctness batch (system review 2026-08-04, §3.1): six changes, two regenerations

**What was wrong.** Six independent, planner-identified defects, each individually
capable of invalidating the golden master (§3.1 of the system review's implementation
plan): the federal estate exemption was a frozen plan-start constant applied unchanged
to a terminal estate computed decades later; Illinois estate tax applied to every
household regardless of actual residence state; no §213 medical expense itemized
deduction existed at all, so LTC cost shocks (already a real cash cost) generated no
tax benefit; the Roth-conversion objective discounted lifetime tax and estate tax to
plan-start present value but left the terminal-wealth component undiscounted,
over-rewarding deferral; every account grew at one identical rate regardless of what
it actually held, making asset location and bucket strategies structurally inert; and
mortality was sampled from a truncated normal (μ=92, σ=4.5, floored at 70), making
death before age 70 impossible and before 80 under 1% likely, regardless of the
household's actual configured longevity assumption.

**What changed — one engine-correctness wave, sequenced and regenerated once.**
Per §3.1's own resolution ("treat them as one engine-correctness wave with a single
golden-master regeneration at the end... run the frozen-fixture gate between them to
confirm each moves only what it should"), each item landed as its own commit
(bisectable) with `pytest -m "not slow"` run after every one, but the pinned
golden-master baseline was deliberately left stale (red by design) until this step:

1. **3.0 — Baseline regen.** Cleared a golden-master regen that had been pending since
   before this session (engine changes from already-merged PRs #47/#48/#50/#51 had
   never been re-pinned): 4,057,824.89 → 6,487,999.96 terminal NW, depleting-in-2052-56
   → fully solvent. Verified as a legitimate engine-state difference, not a live-data
   leak, via the fixture's own isolation guardrail test plus holding the workspace
   redirect open through `project()` (not just parse) and reproducing the identical
   number either way.
2. **3.1 — Estate exemption indexing + IL residency gate.** Added
   `core.indexed_federal_estate_exemption()` (grows the federal exemption by the same
   `brk_inf` bracket inflator as income-tax brackets); gated all four Illinois
   estate-tax call sites on `c['state'] == 'Illinois'`. No pin movement for the frozen
   household (already IL resident, terminal estate doesn't cross the exemption either
   way).
3. **3.2 — §213 medical expense deduction.** `medical_expense_yr` (Medicare/bridge
   premiums + wellness detail spend + LTC premiums + LTC cost shock) above 7.5% of AGI
   now enters `item_ded`. Terminal NW +$302,483 / lifetime tax −$153,026 vs. the 3.0
   baseline.
4. **3.3 — Roth objective present-value fix.** Added a separate
   `after_tax_terminal_nw_pv` used only inside the four `terminal_component`
   assignments; `after_tax_terminal_nw` itself (PTI, Executive Summary) stays nominal.
   No further pin movement for this household — its selected strategy didn't flip.
5. **3.4 — Dual-column nominal + today's-$ reporting.** Sheets 1/5/6/7/15 and the
   forecast API gained today's-purchasing-power companion figures next to each
   headline nominal dollar amount. No engine values changed (presentation only).
6. **3.5 — Sleeve-level account returns (deterministic path).** `c['account_returns']`
   populated from actual holdings (`client_holdings.csv` → `security_master.csv` →
   `capital_market_assumptions.csv`), anchored so the dollar-weighted average still
   equals the user's configured `portfolio_nominal_return`. Terminal NW +$507,542 vs.
   the 3.0 baseline (another +$205,059 on top of 3.2's drift — the Roth account now
   compounds faster). Monte Carlo-level differentiation (reshaping the vectorized
   asset-class draw's weight vector into a weight matrix) is an explicit, separate
   follow-up, not included here.
7. **3.6 — SSA/SOA mortality table.** New `reference_data/mortality_table.csv`
   (single-year male/female qx, ages 18-119, derived from SSA Actuarial Study No. 124
   anchors at 5-year ages — ssa.gov's own tables return HTTP 403 to automated fetches,
   so this is a secondary aggregation flagged for a direct-source refresh at the next
   annual reference-data maintenance pass). Both `sample_death_year()` (scalar) and
   `_mc_vectorized_death_years()` (vectorized — the one that actually produces the
   headline Monte Carlo success rate, and the sampler the original panel review missed
   entirely) now draw from the same age-shifted table, calibrated so each household
   member's own configured `mortality_age` remains their median lifespan. No
   deterministic-path pin movement (mortality only feeds Monte Carlo).

**Final regeneration (3.7).** `tests/test_199_frozen_sample_plan_golden_master.py`:
`PINNED_TERMINAL_NW` 6,487,999.96 → **6,995,542.24**, `PINNED_LIFETIME_TAX`
1,517,126.54 → **1,362,412.33**, `PINNED_FAILURES` unchanged (`[]`, fully solvent).
`tests/test_2_recommendations.py`'s warn-only drift-tracking pins updated to match.
Full `pytest -m "not slow"` suite green except 5 pre-existing, unrelated failures
(a fixture gap in the home-purchase-chart tests and one ssa44/IRMAA-relief
interaction, neither touched by this wave) tracked separately. Full workbook + PDF
build verified end to end after every item in this batch.

**Deferred:** 3.8, the automated workflow's planner sign-off against this document,
remains blocked on a session token limit; a manual sign-off (documented in
`documentation/reports/SYSTEM_REVIEW_2026-08-04.md` §7) authorized proceeding with
this wave without waiting for it.

## 2026-07-23 — Roth conversion sizing now caps against LTCG rate-tier and NIIT MAGI cliffs

**What was wrong.** `plan_roth_conversion` (`fill_to_bracket`/`fill_to_irmaa`
policies) already capped voluntary conversions against the target federal
ordinary bracket, IRMAA tiers, and (in ACA-bridge years) the ACA PTC MAGI
cliff, but had no equivalent cap for two other real cliffs raising ordinary
MAGI can trigger: pushing already-known qualified-dividend income across the
0%/15% LTCG rate-tier boundary, and pushing MAGI over the NIIT (3.8% surtax)
threshold. Both costs were only visible after the fact, in the lifetime-tax
comparison between whole candidate strategies (`total_tax` already includes
NIIT and LTCG) — never as a same-year brake the way IRMAA/ACA guardrails
already worked.

**What changed.** Added `_roth_ltcg_thresholds_base`/`_roth_niit_threshold_base`
(filing-status-fresh lookups, mirroring the existing IRMAA threshold helper's
fix for a surviving spouse's filing status flipping to Single mid-plan) and a
new `_ltcg_niit_caps()` helper wired into the same `_ranked_caps` list as the
existing IRMAA/ACA caps, in both the `fill_to_bracket` and `fill_to_irmaa`
branches. Sized only off income already known at conversion-sizing time
(qualified dividends, interest, ordinary portfolio income) — it cannot see
capital gains TLH/gain-harvesting/portfolio draws realize later the same
projection-loop year, since those are computed after the Roth conversion
decision. New config toggles `roth_ltcg_cap`/`roth_niit_cap` (default on) and
`roth_ltcg_headroom_usage_pct`/`roth_niit_headroom_usage_pct` (default 0.95,
matching the existing IRMAA headroom knob).

**What moved and why.** The live client plan (`input/client_data.csv`) carries
real qualified-dividend/interest income, so `total_roth_conversion` drops
materially across every scenario that runs `fill_to_bracket`/`fill_to_irmaa`
(e.g. `baseline_balanced_couple` 850,476.64 → 565,476.58) — conversions are now
correctly throttled before they push existing investment income into a higher
LTCG rate or across the NIIT threshold, which raises `lifetime_tax` in some
scenarios (less Roth conversion now, more pre-tax income taxed later) even as
it avoids a cliff the engine previously ignored. `no_voluntary_roth_policy`
also moved, but only from pre-existing unrelated pin drift already present
before this change (confirmed by diffing against the unmodified engine) — that
scenario forces `roth_policy='none'`, which never reaches the new caps at all.

## 2026-07-22 — Track 4 (system review 2026-07-21): golden-master regeneration after P1/P2/P3 engine fixes

**Why regenerated.** Per the system review's Track 4 (engine-correctness items P1
IRMAA/ACA guardrail age-gating, P2 0%-bracket gain harvesting, P3 Social
Security timing score de-double-counting), regenerated the live-client-derived
warn-only pin in `test_sample_projection_golden_master_and_release_gate` per
the standing instruction to do so once, at the end of the track, rather than
after each item.

**What moved and why.** Nothing from Track 4 itself: this pinned scenario
forces `roth_policy='none'`, which bypasses the P1 IRMAA/ACA guardrail fix
entirely (that fix only changes behavior inside the `fill_to_bracket`/
`fill_to_irmaa` Roth-conversion policies), and P2 gain harvesting defaults to
`gain_harvest_policy='off'` (a proven no-op — see
`tests/test_gain_harvest_zero_bracket.py::test_gain_harvest_off_is_a_pure_no_op`).
P3 only changes Sheet 10's SS-timing sweep scoring, not `project()`'s row
values. The `terminal_total_nw` delta (+18,385.03 over the prior pin) was
already present and flagged as pre-existing/unrelated drift throughout the
session before Track 4 started — i.e., from routine `input/client_data.csv`
edits, not an engine regression. Regenerating now folds that drift into a
fresh baseline: `terminal_total_nw` 6,536,759.61 → 6,555,144.64;
`lifetime_tax` 1,527,729.93 → 1,524,551.07 (well under the $5,000 warn
threshold on its own).

## 2026-07-21 — Item 4.2 / P4: DAF contribution now enters the itemized deduction stack (60%/30% AGI limit, 5-year carryforward)

**What was wrong.** `deterministic_engine.py` has computed `daf_contrib_yr`
(added to `lump_yr`, a real cash outflow funded by the withdrawal cascade)
and `daf_grant_yr` (informational only) since item 165 (2026-07-08), but
neither ever fed the tax computation: `char = max(0, c['char_low'] -
0.005*agi)` was, and until this item remained, the only input to the
charitable component of the itemized deduction. A configured DAF
contribution was pure cost with zero tax benefit — despite this changelog's
own 2026-07-08 "DAF activation baseline" entry describing a tax-reducing
effect. That entry's terminal-NW/lifetime-tax movement at the time came from
something else in that plan-data edit, not from DAF; there was no DAF-AGI
coupling anywhere in the engine to produce it. `sheets_strategy.py`'s
Charitable Giving sheet (Sheet 12) already said as much explicitly
("Neither DAF contributions nor QCDs are modeled by the projection engine")
— that caveat is now updated (see item 4.1's entry below for the QCD half).

**The fix.** In the same `char`-computation block, a DAF contribution now
adds to a 5-year rolling carryforward pool (`daf_deduction_carryforward`,
plain per-year local state, list of `[origin_year, amount]`), consumed
oldest-first each year up to `agi * 0.60` (cash) or `agi * 0.30`
(`daf_contribution_is_appreciated`, new config flag) — IRC 170(b)(1)(G)/(d)(1).
Unconsumed capacity older than 5 succeeding tax years is dropped, not
deducted. `daf_grant_yr` (money leaving the DAF to the actual charity) was
already informational-only and stays that way — the deduction was already
claimed in the contribution year, so a grant year correctly adds nothing.
New row fields: `daf_deduction_yr`, `daf_deduction_carryforward`.

**Known limitation (flagged, not fixed here — see the code comment above
`daf_deduction_carryforward` in `deterministic_engine.py` and its spawned
follow-up task).** The AGI used for this limit is the *first-pass* estimate,
taken before the elective-IRA-withdrawal sizing loop converges later that
year — shared by every other deduction computed at that point (salt, char,
mortgage interest). For a retiree with no guaranteed income yet (pre-SS,
pre-RMD, living entirely off discretionary withdrawals), first-pass AGI can
read near zero even though real final-year AGI is substantial, understating
the 60%/30% limit and potentially letting real carryforward capacity lapse
unused. Tests for this item deliberately place the DAF contribution in a
still-earning year (`tests/test_daf_agi_limitation_and_carryforward.py`),
which is also the review's own recommended "bunch gifts into a high-income
year" use case, not the affected pattern.

**New config.** `daf_contribution_is_appreciated` (boolean, `DAF / Settings`,
default `FALSE`) — added to `reference_data/schema.csv`,
`src/data_io.py`, and backfilled into `client_assets.csv` for existing plans
via a new `DAF_APPRECIATED_UI_PLAN_DATA_ROWS` entry
(`src/server/app_core.py`). Item 4.1 (QCD, same session) similarly added
`qcd_enabled` / `h_qcd_annual_amount` / `w_qcd_annual_amount` /
`h_qcd_start_year` / `h_qcd_end_year` / `w_qcd_start_year` / `w_qcd_end_year`
under `Cashflow / Charitable Giving` (`client_spending.csv`) — both items'
new fields were missing schema/backfill registration until this pass, even
though QCD/DAF config fields already existed informally; brought up to the
same standard as every other Wave 4 input.

**Golden-master impact.**
- **Frozen sample plan** (`tests/test_199_frozen_sample_plan_golden_master.py`,
  mandatory): its fixture has DAF enabled ($20,000 contribution, 2026) —
  terminal NW moved 6,536,759.61 → 6,555,144.64; lifetime tax moved
  1,527,729.93 → 1,524,551.07. Pins regenerated via the file's `__main__`
  block.
- **Synthetic gate** (`tests/fixtures/synthetic_golden_master_cases.json`,
  mandatory): only the `donor_advised_fund` scenario moved (as expected —
  it's the only scenario with `daf_enabled`), terminal NW 11,815,114.04 →
  12,054,025.57, lifetime tax 729,739.82 → 681,747.98. The other 5 scenarios
  are byte-identical (confirmed via
  `test_golden_master_library_covers_multiple_plan_stresses`). Regenerated by
  recomputing just that one scenario's `project_metrics()` and replacing its
  entry in the fixture.
- **Live sample plan** (`input/client_data.csv` + siblings,
  `test_2_recommendations.py`, warn-only): also has DAF enabled and will show
  the same directional drift (real DAF deduction now applying) the next time
  that warn-only test runs — expected, not a regression; no pin update
  needed for a warn-only gate by design (item "Sample-plan golden-master
  baselines demoted to warn-only", 2026-07-18, below).

## 2026-07-21 — Item 4.1 / P3: Qualified Charitable Distributions as an AGI exclusion

**What was wrong.** QCDs were illustrative-only: `sheets_strategy.py`'s
Charitable Giving sheet (Sheet 12) and Investment Policy Statement both said
so explicitly ("QCDs are not reflected in the projection, net worth or
Monte Carlo results" — item 1.12, Wave 1). No `qcd_*` config existed and
nothing reduced AGI for a QCD.

**The fix.** New per-member config (`qcd_enabled`,
`{h,w}_qcd_annual_amount`, optional `{h,w}_qcd_{start,end}_year`) computed
in `deterministic_engine.py` right after `compute_rmds`, gated at each
member's own age-70½-eligible year (`core.qcd_eligible_from_year`, year-
granular: same-year if born Jan-Jun, following year if born Jul-Dec) and
capped at the statutory per-person annual limit (`core.qcd_annual_limit`,
$108,000 base year 2025, inflated by `brk_inf` like every other embedded
statutory dollar figure in `core.py`). The QCD-reduced quantity
(`rmd_taxable_total = rmd_total - qcd_total_yr`) replaces `rmd_total` at
every point that feeds AGI, ACA MAGI, or Roth-conversion headroom (the ACA
pre-estimate, the conversion-headroom state-tax closure,
`plan_roth_conversion`'s own `rmd_total` kwarg, the master `non_ss_income`
AGI formula, `retirement_dist` for the final state-tax call, and
`income_from_streams` — QCD dollars go to charity, not to the household, so
they must also not appear as spendable cash funding the year's gap). The
gross `rmd_h`/`rmd_w`/`rmd_total` are unchanged and still what
`apply_rmds` draws from the IRA and what the workbook reports as the
required distribution — the RMD is still fully satisfied either way. The
$-for-$ recurring-giving deduction (`char`, fed by `char_low`) is netted by
the QCD amount so the same dollars aren't excluded from AGI *and* claimed as
a second deduction.

**Scope simplification (phase 1, documented in code):** a QCD is capped at
that year's own RMD; a QCD larger than the RMD, or one taken in the
age-70½-to-RMD-start gap (no RMD due yet), is not modeled as an independent
extra IRA withdrawal. `h_qcd_yr`/`w_qcd_yr` report what was actually
modeled, so a configured amount above the cap is visibly capped, not
silently accepted.

**Golden-master impact.** None on any mandatory or warn-only pin: `qcd_enabled`
defaults `FALSE` everywhere (no plan — synthetic, frozen, or live — has it
set), so this is a pure no-op by default. Verified via a clean-worktree
before/after comparison of every numeric field on the live plan's projection
rows (0 differences across 31 rows, 10 metrics each) with items 4.1, 4.4,
4.5, and 4.6 all applied together.

## 2026-07-20 — Item 4.3 / P5 (Option 2): inherited-IRA heir rate is a derived effective 10-year-rule rate, not a flat 24%

**What was wrong.** The Roth-conversion objective scored inherited pre-tax
(IRA/401k) balances at a flat 24% ordinary rate through two independent config
fields — `roth_heir_ordinary_tax_rate_assumption` (the heir legacy-burden rate,
`planning_engines.py` `_roth_strategy_metrics`) and
`roth_optimize_terminal_tax_rate` (the terminal pre-tax deferred-tax haircut,
read in `after_tax.py`'s `estimate_terminal_pretax_deferred_tax`). A flat 24%
cannot distinguish a small inherited IRA (whose 10-year-rule distribution slices
stay in low brackets) from a large one (whose slices push into higher brackets),
so it systematically under-penalized the largest pre-tax balances — exactly the
households where a low-bracket conversion year is most valuable and, once missed,
unrecoverable. Item 2.1 fixed the *taxable* leg's §1014 step-up; this item fixes
the *pre-tax* leg.

**The fix (Option 2 — the immediate effective-rate model, not the full heir
module).** Both fields now default to an **effective SECURE Act 10-year-rule
rate** derived from the terminal pre-tax balance: the balance is spread level
over 10 years (no growth — an intentional simplification), each annual slice is
taxed as the heir's *only* ordinary income at an assumed heir filing status via
`core.compute_fed_tax(slice, year, filing, brk_inf)` (bracket-inflated to each
distribution year from the terminal year), and the ten years of tax are summed
and divided by the total balance. Implemented as
`after_tax.effective_heir_ten_year_rate()` with `resolve_heir_ordinary_rate()` /
`resolve_terminal_pretax_rate()` wrappers that honor an explicit user override
(any configured value other than the historical flat 24% is kept as-is; only the
24% default is replaced by the derived rate).

**New config input.** `heir_filing_status` (config key `roth_heir_filing_status`,
`Withdrawal Policy › Roth Conversion`, choice, default **Single** — the common
adult-child-beneficiary case), added to `reference_data/schema.csv` and both
`data_io.py` ingest paths (`parse_client` and `build_plan_from_json`). Judgment
calls (spec did not fully pin these): (a) default filing status = Single;
(b) the derived rate is sourced from the **terminal** pre-tax balance (the same
`pretax_nw` figure the terminal haircut already used), spread over the terminal
year `t … t+9`; (c) "user override" is detected as "configured rate ≠ 0.24",
since documented defaults are materialized into input files so mere presence
cannot distinguish an override from the default.

**Direction proof (the key check).** Effective rate is monotonically increasing
in balance, so a small IRA lands well below 24% while a large one is at or above
it. Single heir, terminal year 2056, 2% bracket inflator:

| terminal pre-tax balance | effective heir rate |
|---|---|
| $150,000 | 10.00% |
| $300,000 | 10.39% |
| $2,000,000 | 16.87% |
| $5,000,000 | 22.77% |
| **$6,000,000** | **24.73%** ← crossover |
| $10,000,000 | 28.84% |

The crossover to ≥24% sits near $6M for a Single heir at a ~2056 terminal year
(higher than a naive reading of "large" because 30 years of 2% bracket inflation
widen the future brackets and the simplified model gives the heir no other
income — consistent with the spec's own "$2M to a lower-bracket retired child"
example, which *should* score below 24%). The direction is correct: bigger
inherited balance → higher effective rate → stronger conversion incentive, and
the very largest balances now exceed the old flat 24% instead of being capped at
it. Overrides verified honored (configured 32% → 32%; configured/default 24% →
derived).

**Golden masters.** `tests/fixtures/synthetic_golden_master_cases.json`
regenerated: **no dollar metric moved on any scenario.** Three scenarios changed
only their disclosed `selected_roth_strategy` label —
`baseline_balanced_couple`, `dividends_not_reinvested`, and
`tax_loss_harvesting` flipped from "Fill current/configured 22% bracket" to
"RMD-reduction conversion". Mechanism: these scenarios use an explicit
`fill_to_bracket` policy (non-auto-optimize), so the projection — and every
pinned dollar figure — is unchanged; the optimizer only *tags* the highest-
scoring candidate that shares the configured policy for the comparison table.
Several candidates share `policy=fill_to_bracket` at the 22% target
(FILL_CURRENT_BRACKET, RMD_REDUCTION, SURVIVOR_TAX_AWARE, …). RMD-reduction
leaves a slightly smaller terminal pre-tax balance, so under the new
balance-sensitive haircut it now edges out plain fill-22 on
`after_tax_terminal_nw` — the correct direction (favor the strategy that shrinks
the inherited pre-tax balance). All other scenarios (incl. the item-2.4
`split_claiming_spousal` and the `no_voluntary_roth_policy` residual-balance
case) are byte-identical. `tests/test_199_frozen_sample_plan_golden_master.py`
pins re-confirmed **unchanged** (`PINNED_TERMINAL_NW = 6536759.61`,
`PINNED_LIFETIME_TAX = 1527729.93`): that fixture sets `roth_policy = "none"` and
never runs the optimizer, so the objective-only heir/terminal rates cannot reach
its numbers.

**Disclosure.** `sheets_summary.py`'s assumptions table now shows "Assumed Heir
Filing Status" and a "Heir Ordinary Tax Rate (effective)" row (preferring the
derived rate actually used, `roth_heir_ordinary_tax_rate_effective`, over the raw
config assumption) with 10-year-rule wording. `sheets_strategy.py`'s Roth "Key
Rules" notes now state the inherited-balance rate is derived (not a flat 24%) and
name the assumed heir filing status.

## 2026-07-20 — Item 2.3 / P6: Roth conversion IRMAA guardrail keyed by filing status

`plan_roth_conversion`'s `fill_to_irmaa` policy and the IRMAA cap inside
`fill_to_bracket` (`planning_engines.py:1024-1028` / `:1050-1054` before this
fix) both read `roth_irmaa_target_threshold_mfj` unconditionally, with no
filing-status branch, even though `filing` is already a parameter of
`plan_roth_conversion` and is already used for brackets and SS taxability in
the same function. The tax-assessment side already did this correctly
(`deterministic_engine.py`'s `_irmaa_surcharge_path`/`_irmaa_tier_path` key
`IRMAA_TIERS_BASE_YEAR` by `filing`), so a surviving spouse whose filing
status switches to Single mid-plan (the `survivor_filing` transition) could
have a Roth conversion recommended that the guardrail believed was still
inside the MFJ IRMAA tier, when it had actually crossed the (much lower)
Single-filer tier the assessment side would have flagged.

Fix: added `_roth_irmaa_target_threshold_base(c, filing)` in
`planning_engines.py`, used at both former call sites. For MFJ filers it
returns `c['roth_irmaa_target_threshold_mfj']` unchanged (an explicit
override, seeded in `data_io.py` from `IRMAA_TIERS_BASE_YEAR['MFJ']` at the
configured `roth_irmaa_target_tier` — bit-identical to the old code path, so
MFJ years are provably unaffected). For every other filing status it looks up
`IRMAA_TIERS_BASE_YEAR[filing]` at the same tier index, mirroring the
assessment-side lookup.

Numeric proof (direct call to `plan_roth_conversion`, `fill_to_irmaa` policy,
`TIER_2`, `pre_agi = $150,000` from RMDs alone, `roth_irmaa_target_threshold_mfj`
explicitly set to $268,000 as `data_io.py` would seed it):
- `filing='MFJ'` → threshold resolves to $268,000 (unchanged) → conversion
  cap = `(268,000 - 150,000) * 0.95` = **$112,100**.
- `filing='Single'` → threshold now resolves to the Single Tier 2 table value,
  **$133,000** (`IRMAA_TIERS_BASE_YEAR['Single'][1][0]`), which is below the
  $150,000 pre-conversion AGI → conversion cap clips to **$0**, correctly
  refusing to convert instead of allowing the old code's $112,100.

`reference_data/schema.csv`'s `roth_irmaa_target_tier` help text ("Dollar
thresholds come from the annual IRMAA tax table") was true of the assessment
side but not the conversion guardrail before this fix; updated to say the
lookup follows the household's current filing status.

Golden masters: regenerated both mandatory gates
(`tests/fixtures/synthetic_golden_master_cases.json` and
`tests/test_199_frozen_sample_plan_golden_master.py`'s pin) — both are
byte-identical/unchanged. Investigated why, per this item's own
verification instructions, since `early_survivor_compression` (built
specifically to exercise the MFJ→Single survivor transition) was expected to
move: instrumenting `_roth_irmaa_target_threshold_base` confirms it is
invoked with `filing='Single'` and correctly resolves $133,000 (vs. $268,000
under `filing='MFJ'`) throughout that scenario's post-death years, so the fix
is live — but the scenario's account registry gives the surviving owner
(`owner_idx=1`) no Roth IRA to convert into at all (`Member_1_Roth` stays
titled to the deceased `owner_idx=0`; `roth_target_for_owner(registry, 1)`
returns `None`), so `apply_roth_conversion` executes $0 regardless of any
IRMAA threshold — a separate, pre-existing gap in survivor account titling
unrelated to this fix. `single_filer` (Single filing from year 1, no survivor
transition) also didn't move: its binding cap is always the 22% bracket room
or the annual IRA percentage cap, with the IRMAA tier never the tightest
constraint at that scenario's income level, so a different (correct) IRMAA
number changes nothing observable. `tests/test_199_frozen_sample_plan_golden_master.py`'s
frozen plan sets `roth_policy = "none"`, so it never reaches the changed code
at all. No fixture edits were needed; both pins are re-confirmed identical
(`PINNED_TERMINAL_NW = 6536759.61`, `PINNED_LIFETIME_TAX = 1527729.93`).

## 2026-07-20 — Item 2.4 (P7): excess-spousal Social Security — timing gate + SSA amount

`deterministic_engine.py`'s spousal Social Security top-up was wrong in two ways.
(1) It was paid regardless of whether the *worker* (whose PIA the spousal amount
derives from) had actually filed — real SSA law bars a spousal benefit until the
worker files. (2) The amount used `max(own_benefit, 0.5*worker_PIA*factor)`, which
both discards the claimant's permanent early-claim reduction on their own record
and applies the *own-benefit* reduction schedule to the spousal amount.

Replaced with the SSA "excess spousal" method, computed per year inside the
projection loop:

    own_reduced_benefit + max(0, 0.5*worker_PIA - own_PIA) * excess_factor

paid only from the worker's claim year onward and only while both spouses are
alive. `excess_factor` is a new helper (`_ss_spousal_excess_factor`) implementing
the spousal reduction schedule — 25/36 of 1%/month for the first 36 months before
FRA, then 5/12 of 1%/month, and **no** delayed-retirement credits past FRA
(capped at 1.0) — keyed to the claimant's age when the spousal benefit first
becomes payable (the later of their own filing and the worker's filing). The
own-benefit records (`h_monthly_claim`/`w_monthly_claim`) are now kept free of any
spousal amount, which also makes the downstream survivor benefit derive purely
from the deceased's own retirement record (a correctness improvement, not a
separate change).

Judgment call, flagged: the plan's one-line "correct formula" wrote the reduction
factor against `0.5*worker_PIA` and subtracted own PIA afterward. That conflicts
with its own prose ("only THEN has its own reduction schedule applied to the
excess"). Per SSA's published dual-entitlement methodology the age reduction
applies to the *excess* (0.5*worker_PIA − own_PIA), so the reduction is applied
after the own-PIA offset, as coded above.

Golden-master impact:
- **Synthetic gate** (`tests/fixtures/synthetic_golden_master_cases.json`): all 9
  pre-existing scenarios are UNCHANGED to the cent. Each has a dominant
  higher-earner PIA and symmetric (both-age-70) claiming, so half the worker's PIA
  never exceeds the claimant's own PIA — the old `max()` and the new excess method
  both resolve to own-benefit-only. Added one new scenario,
  `split_claiming_spousal` (higher earner delays to 70, lower earner claims at 62),
  the only scenario in which the excess-spousal path is live, so the mandatory gate
  now exercises the fix (terminal NW 12,238,486.87; lifetime tax 710,025.22).
- **Frozen sample plan** (`tests/test_199_frozen_sample_plan_golden_master.py`):
  pins UNCHANGED (6,536,759.61 / 1,527,729.93) — that household has no live
  excess-spousal situation. No regeneration was required.

New coverage: `tests/test_200_spousal_ss_excess_benefit.py` pins the 62/70 timing
gate and step-up, a reduced-excess case (spousal begins at age 63 → 0.70 excess
factor, distinct from the 0.75 own-benefit factor at the same 48 months), and the
no-top-up case where both spouses' own PIAs dominate.

## 2026-07-20 — Item 2.1: §1014 step-up in the terminal metric + estate-tax penalty scoped to the second death (findings P1 + P9)

Two coupled corrections to the Roth-conversion optimizer's terminal metric, which
is the dominant term of its objective.

**P1 — terminal deferred cap-gain tax now honors the §1014 basis step-up.**
`src/after_tax.py`'s `estimate_terminal_taxable_deferred_cap_gain_tax` used to tax
the FULL unrealized gain in terminal taxable accounts, as if heirs inherited the
decedent's cost basis — even though the same codebase already grants a step-up
during life (`planning_engines.apply_death_transition` zeroes basis at first/second
death, and `client_insurance_estate.csv` carries `basis_step_up_at_death,TRUE`).
The estimate now branches on three cases and prints which one it used, plus the
resulting assumed basis, on the Estate & Legacy sheet (Sheet 14):
- (a) terminal year IS the second death → full step-up (gain zeroed, scaled by the
  property regime so community-property vs common-law still matters);
- (b) terminal year is at/after the first death with a survivor still alive (or the
  horizon ends before the second death) → only the decedent's share steps up, the
  survivor's share retains its deferred gain;
- (c) horizon ends with both members alive → no step-up, gain retained in full.

**P9 — estate-tax penalty now scores the estate actually transferred at the second
death, not peak net worth.** `planning_engines._roth_strategy_metrics` used
`max(estate_tax over every row)`, penalizing the PEAK single-year net worth
(typically early/mid-plan). It now evaluates `estimate_terminal_estate_tax` at the
second-death row and present-values it with `roth_tax_discount_rate`, so the
objective and the reported Post-Tax Inheritance agree. The old max-across-rows
figure is retained as a separately-reported `peak_estate_tax_exposure` (risk
indicator only — the Illinois estate-tax cliff with no portability makes worst-year
exposure worth surfacing, but it should not drive conversions).

Sheet 11 now also discloses `roth_heir_ordinary_tax_rate_assumption` (24%) and
`roth_optimize_terminal_tax_rate` (their current flat values) and labels the
conversion recommendation as sensitive to both.

### Live sample-plan before/after (optimizer engaged via `optimize_terminal_tax`, MAXIMIZE_TERMINAL_NET_WORTH)

|                              | Before (buggy)                | After (fixed)                 |
|------------------------------|-------------------------------|-------------------------------|
| Selected strategy            | Fill to 12% bracket           | Fill to 12% bracket (same)    |
| Conversion schedule          | 2026 $125,000 / 2027 $53,100 / 2028 $36,017 | identical    |
| Total conversions            | $214,117                      | $214,117 (unchanged)          |
| Terminal step-up case        | (not classified)              | second_death (full step-up)   |
| Terminal deferred cap-gain tax | $2,142                      | $0                            |
| Assumed terminal basis       | $43,268                       | $86,536 (cost + stepped gain) |
| Objective estate-tax penalty (top cand.) | $573,484 (peak)   | $191,419 (PV @ 2nd death)     |
| Top-candidate objective score | 1,022,404                    | 1,407,145                     |

The selected conversion schedule for this plan does NOT change: even under the
buggy metric the low-conversion 12%-fill already dominated, because the higher
brackets are killed by the Roth-last leakage guard (10× penalty), not by the
terminal-tax term. What the fix corrects is the accuracy of the numbers behind the
recommendation — it removes $2,142 of phantom cap-gain tax the second-death full
step-up eliminates, and cuts the objective's estate-tax drag from a peak-year
$573k to the PV-at-death $191k, widening (not narrowing) the correct choice's lead.
This is the "conversions legitimately stay flat" case the plan anticipated: here
the terminal metric is not the binding term.

### Golden-master movement

- **Synthetic gate** (`tests/fixtures/synthetic_golden_master_cases.json`): no dollar
  metric moved on any of the 9 scenarios. Every synthetic scenario runs a FIXED
  `fill_to_bracket` (or `none`) policy — none auto-optimize — so `project()` output
  is byte-identical and the terminal-metric/objective change is invisible to the
  projected numbers. Two scenarios (`donor_advised_fund`, `single_filer`) changed
  only their `selected_roth_strategy` LABEL, from "Fill current/configured 22%
  bracket" to "RMD-reduction conversion". Both labels are the SAME policy
  (`fill_to_bracket`) at the same 22% target; the optimizer's non-auto path shows
  the top score-sorted candidate matching the configured policy, and the corrected
  objective simply re-ranked two equivalent-policy candidates. No conversion,
  balance, or tax figure changed. Fixture regenerated to absorb the two labels.
- **Frozen sample plan** (`tests/test_199_frozen_sample_plan_golden_master.py`): pins
  UNCHANGED (`PINNED_TERMINAL_NW = 6536759.61`, `PINNED_LIFETIME_TAX = 1527729.93`).
  That test projects with `roth_policy="none"`, so the optimizer objective is never
  invoked and `project()` is unaffected. No edit needed.

Gate run (`RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`): `test_90`,
`test_synthetic_golden_master`, `test_199` — 12 passed, 35 subtests passed.
`git status --short input/` confirmed clean before and after every run.


## 2026-07-18 — Sample-plan golden-master baselines demoted to warn-only

`tests/test_2_recommendations.py` pinned two dollar figures from the live sample
plan (`input/client_data.csv` plus the sibling `client_*.csv` files `load_csv`
merges into it). Because that data is edited routinely, the pin failed on ordinary
plan-data churn, and each failure was resolved by regenerating the number and
appending an explanatory comment — about 130 lines of them by 2026-07.

Those two assertions are now a warn-only diagnostic. The structural assertions
(zero validation failures, zero warnings, 2026-2056 across 31 rows) still block.
Engine regressions are gated by the synthetic golden master, which reads no client
data and so cannot be moved by a plan edit.

The per-item history that used to live in the test body is preserved below.

- Golden-master constants are tied to input/client_data.csv (and its transaction/budget-derived spend base) as of this commit. Regenerate them deliberately after intentional plan-data changes; a mismatch otherwise usually means a real projection-engine regression.
- **Item 141 (2026-07)** — the projection spend_base dropped from 129,059 to 124,059 after fixing a double-count in spending_budget_resolver — a Core Expenses category (charitable giving) that carried BOTH a category budget row and a detail line was counted twice. The 5,000/yr lower spend reinvests as surplus, so terminal net worth and later-year taxes rise.
- **Item 142 (2026-07-07 12:09 PM)** — spending budget line items updated manually (dentist, medical, gifts, health club, vitamins) and miscellaneous/uncategorized cleared out after taxonomy changes. Terminal net worth increased to ~12.4M.
- **Item 143 (2026-07-08)** — one-time $40k family gift modeled as a significant_gifts Large Discretionary line for 2026, plus an app re-sync of client_spending_budget.csv (several category budgets adjusted, e.g. entertainment/furniture/lawn lowered). This projection path does not apply the current-year YTD blend, so the gift's effect here is just the $40k 2026 lump; net of the re-synced budgets, terminal net worth settles to ~11.32M and lifetime tax to ~1.46M. Regenerate from a clean `git worktree` checkout (no untracked local state) — a plain working-tree run can pick up gitignored local caches (e.g. output/pricing_diagnostics.json, live holdings snapshots) that inflate balances by $1M+ versus CI's committed-only checkout.
- **Item 165 (2026-07-08)** — DAF (Donor Advised Fund) feature activated (input/client_assets.csv `enabled` flipped FALSE->TRUE). DAF contributions reduce taxable income/AGI which lowers lifetime tax and, combined with the tax savings compounding as reinvested surplus, raises terminal net worth to ~12.24M and lifetime tax to ~1.55M.
- **Item 166 (2026-07-09)** — dividend reinvestment feature. Dividends/interest no longer directly fund spending as "Portfolio Income" — they either compound into the holding or convert to account-internal cash (Reinvest Dividends toggle, per account and a global override; this sample plan's client_household.csv has the global switch on). Removing that free cash from the income funding calc means the withdrawal cascade sells more to cover the same spending, realizing capital gains tax the old model avoided. Terminal net worth drops to ~12.11M and lifetime tax to ~1.50M.
- **Item 167 (2026-07-09)** — tax-loss harvesting feature (tlh_policy defaults to off, so the engine change itself is a no-op) landed alongside plan-data edits made through the running app during that work: annual_earned_income raised to $309,620 (from $290,000), a Liquidity Buffer reserve activated for 2027-2029, a $5,000 charitable-giving budget line removed, and Medicare Part B/D/Medigap premiums rebalanced. Net effect: terminal net worth drops to ~9.40M and lifetime tax to ~1.31M — a real plan-data change, not an engine regression.
- **Item 185 (2026-07-14)** — the elective pre-tax IRA/401(k) withdrawal used to size itself off a flat federal-marginal-rate gross-up (withdraw_pretax_elective's `gross_up`), which ignores state tax and bracket integration, and its ordinary income was never added to agi/taxable_inc. Added a bounded fixed-point true-up (mirroring the existing LTCG/NIIT loop) that re-solves against the real progressive fed+state tax and folds the withdrawal into agi/taxable_inc/irmaa_magi. This is why some rows previously showed both an elective withdrawal and a "reinvested surplus" in the cash-bridge sheet at the same time. Also fixed a second, related bug the true-up exposed: `new_gap` was reduced by a flat-rate-estimated `net_cash`, while required_portfolio_ draws (the cash-bridge sheet and this true-up) count the full gross withdrawal — the two conventions double-booked/mis-booked the tax and left the cash-bridge reconciliation off by the mismatch (confirmed via `git stash` against the pre-Item-185 code — this reconciliation gap, smaller but present, pre-dates this fix). `new_gap` now reduces by the full gross amount, matching withdraw_taxable_trust's convention, so the true-up's real tax delta is the only tax accounting in play. Elective withdrawals end up smaller (correctly sized, not over-drawn), letting more compound tax-deferred: terminal net worth rises to ~7.32M and lifetime tax rises to ~1.62M.
- These constants are now fully reproducible: tests/conftest.py pins holdings pricing to OFFLINE, so starting balances come from the committed cache snapshot rather than live market data. Confirmed identical across Python 3.12 and 3.14 on Windows (both interpreters agree to the cent); regenerate deliberately after an intentional engine/plan-data change. Baselines reflect the committed sample inputs plus two intentional engine changes: item 182 (pre-65 bridge premium applies to any pre-65 person regardless of retirement year) and item 184 (real-estate tax is funded as a cash need, not only used for the SALT deduction). Values were regenerated against clean committed inputs — a fresh checkout / CI reproduces them (holdings are pinned OFFLINE via tests/conftest.py).
- **Item 168 (2026-07-14)** — `load_csv` merges every sibling client_*.csv file, so this sample config picks up client_household.csv's real per-age SS benefit tables even though client_data.csv itself has no SS fields. Fixing the SS benefit self-cancellation bug (13b089a) moved the claimed amount from a flat back-solved number to a real per-age table lookup (a small change: ~$5,080/mo flat -> the real age-70 figure), and separately fixed Social Security's present value being silently excluded from the fixed-income coverage calculation (ss_pv was always 0 before the fix). Together these ripple through the withdrawal/tax cascade to shift terminal net worth by ~$33k. Verified via `git worktree` bisection: the prior pin (6,745,962.88 / 971,088.96) reproduces exactly at commit dcfe794, and the intermediate value (6,712,722.02 / 965,325.67) reproduces exactly at 13b089a, in a clean checkout free of gitignored local cache files (which can inflate a plain working-tree run by $800k+ - see item 143).
- **Item 169 (2026-07-14)** — household plan update - Social Security claim age moved from 70 to 69 for both spouses (matching Sheet 10's projection-sweep recommendation), and FRA Age set explicitly to 67 (same as the auto-derived default, no behavior change). Claiming one year earlier changes which ss_benefit_age_* table entry is used and shifts the whole withdrawal/tax cascade.
- **Item 185 (2026-07-14)** — elective pre-tax IRA/401(k) withdrawal ordinary-tax true-up + gap/net_cash convention fix (see deterministic_engine.py's _ira_elective_ordinary_tax_delta) — terminal net worth rises to ~7.32M, lifetime tax to ~1.62M.
- **Item 186 (2026-07-14)** — household plan update - Member 1 Social Security claim age moved from 69 to 68 (Member 2 unchanged at 69). Terminal net worth rises to ~7.36M, lifetime tax to ~1.63M.
- The previously-noted order-dependency (this value shifting ~$800k depending on whether test_forecast_api_service_uses_same_config_ contract ran first) was the same pricing-cache leak fixed by the tests/conftest.py _reset_market_data_price_cache autouse fixture; this value is now stable both in full-suite and isolated runs.
- Regenerated 2026-07-17 against the committed frozen-price snapshot (tests/golden_pricing.py) after the b246d19 plan-data drift — SS claim age, annuity dividend rates, and liquidity buffer changed under a UI-titled commit ("Combine SS policy fields onto one row"). Holdings pricing is now frozen rather than read from the untracked local OFFLINE cache, so this pin is deterministic and portable across machines.


## 2026-07-15 — Remove advisor/household language mode and the Advanced Workflow Steps toggle
- Removed the browser-local advisor/household display language mode entirely (state, Settings card, page-header banner, and text-substitution engine). Page copy now renders as authored, with no display-mode preference. No calculations, saved values, build snapshots, or exports were ever affected by it.
- Removed the "Advanced Workflow Steps" preference toggle and its Settings "Workflow view" card. Its only real effect was surfacing the Special Strategies page, whose content is already gated by Optional Modules.
- Special Strategies navigation visibility now follows capability: the page appears once the HELOC or Charitable Giving optional module is enabled, so Optional Modules is the single source of truth. The other advanced-flagged pages were already `hidden` and reachable only via Settings/links; that is unchanged.


## 2026-06-27 - Strategy/Asset Service Modularization
- Added `src/server_services/strategy_asset_service.py` as the feature-owned service for strategy, asset, estate, insurance, reference-import, seed-row, and config-sync helper behavior.
- Refactored `src/server/plan_routes.py` strategy/assets/estate/insurance routes into thin adapters for permissions, CSV-write checks, request extraction, and JSON serialization.
- Preserved existing route URLs and payload shapes for withdrawal order, large discretionary expenses, forced Roth conversions, liquidity buffers, other assets, 529 plans, estate states, trust accounts, insurance policies, capital-market imports, housing seed, healthcare OOP seed, and config sync.
- Extended route ownership, API contracts, packaging checks, and clean-overlay validation for the new service seam.
# v11 Planning Workbench consolidation
- Implemented `PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md` as a dedicated Planning Workbench guided step.
- Added browser-local `planning_case_v1` cases and shared `src/planning_workbench.py` contract helpers.
- Unified manual edits, strategy levers, scenario overrides, and stress-suite assumptions into one change-set/override vocabulary.
- Renamed legacy surfaces in-place: Strategy Levers, Scenario Change Sets, Stress Suite & Monte Carlo, and Impact & Build History.
- Added Build Impact comparison context for selected planning cases while preserving the guardrail that cases never mutate the saved plan automatically.


## 2026-06-26 — Flask-free local HTTP runtime

- Implemented the Flask removal proposal with `src/http_runtime`, a dependency-free local route registry, request/response facade, test client, and `ThreadingHTTPServer` adapter.
- Updated desktop mode so pywebview API calls use the local route registry instead of a Flask test client.
- Updated server mode to launch the stdlib local HTTP runtime.
- Removed Flask/Werkzeug/Jinja/Click/ItsDangerous/MarkupSafe/Waitress from runtime requirements and PyInstaller packaging hints.
- Added regression coverage for importing and calling server routes without third-party web framework dependencies.

# v11 page-local recommendation engine

- Added `page_recommendations_v1` as an explainable, non-automatic recommendation layer on Roth conversion, allocation, core spending, and Social Security pages.
- Each recommendation explains why it matters and links back to the editable source input that controls the suggestion.
- The change is UI-only: it stages no values automatically and does not alter calculations, saved plan data, build snapshots, projection formulas, tax logic, exports, or workbook sheet definitions.

# v11 local backup scheduler

- Added opt-in `local_backup_scheduler_v1` for retention-limited local `.rpx` SQLite backups.
- Added Normal Settings controls for daily/per-build cadence, manual backup, and retention count.
- Backups are opportunistic after Save Changes or successful builds; no background service is started and projection formulas, tax logic, workbook sheets, and saved plan values are unchanged.

# v11 import preview contracts

- Added side-effect-free `import_preview_v1` previews for YTD transaction CSV uploads and holdings CSV replacement.
- Transaction previews report row counts, current-year filtering, date range, duplicate candidates, unmapped categories, and new transaction accounts before writing.
- Holdings previews report row counts, duplicate lot candidates, purchase-date range, account/symbol summaries, security-master gaps, data-quality flags, and estimated cost basis before staging the imported table.
- The change is additive: existing upload/save routes remain, and holdings imports are staged in the browser until Save Changes persists them.

# v11 household/advisor language mode

- Added browser-local household/advisor display language mode in Normal Settings.
- Page headers and help framing now use the selected display mode where safe, with a visible mode banner on workflow pages.
- The change is display-only: saved plan data, calculations, build snapshots, exports, projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v11 scenario templates and saved scenario sets

- Added a Scenarios-page management panel with deterministic templates for conservative markets, spending pressure, retire-later bridge, and home-sale liquidity.
- Added browser-local `scenario_set_v1` saved named scenario sets, including apply/delete controls and side-by-side diff previews against current scenario assumptions.
- The change is UI-only: it stages scenario assumption edits through existing fields and does not alter projection formulas, tax logic, workbook sheet definitions, or build contracts.

# v11 Build Impact narrative source links

- Added a natural-language Build Impact summary for the latest successful build.
- Captured edited fields now carry source-page metadata, and Build Impact links changes back to the guided workflow page where the value should be reviewed.
- The change is UI/reporting-only: projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v11 pricing snapshot freeze

- Added `pricing_snapshot_freeze_v1` as the next Phase 2 roadmap contract for advisor-report reproducibility.
- Added freeze/unfreeze API routes, Normal Settings controls, build-preflight status, frozen-price build application, and regression coverage.
- Frozen pricing is additive: projection formulas, tax logic, and workbook sheet definitions are unchanged.

# v11 migration architecture refactor

- Implemented local-only v11 architecture layer with typed PlanInput, SQLite snapshots, versioned tax law dataset, projection pipeline contract, report specs, what-if scenarios, and local meta-optimizer.
- Results Explorer continues to use the semantic result model first, with workbook parsing as legacy fallback.
- Removed hosted/multi-user behavior from v11 runtime/UI surfaces and updated release/cache labels to v11.
- Completed three validation/repair rounds; full collected repository suite passed in chunks: 271 tests plus 16 subtests.

## v11 Results Explorer semantic model refactor
- Added a shared semantic Results Explorer model (`results_explorer_model.json`) generated from projection artifacts during workbook builds.
- Results Explorer now prefers the semantic model and only uses Excel workbook parsing as a backward-compatible fallback.
- Added semantic Chart Dashboard, Cash Flow, Net Worth, Lifetime Tax, Asset Allocation, and Executive Summary pages.
- Labeled the build as 8.4 and updated dashboard cache-busters.

## v8.3 YTD transaction pagination and chart dashboard projection fallback
- Added YTD Transactions pagination for filtered result sets over 500 rows, with First, Previous, Next, and Last controls.
- Reset transaction pagination when search, filters, or sorting changes so the user stays on a valid page.
- Added browser-native Chart Dashboard fallback charts derived from ordinary projection result sheets when hidden chart-source ranges and embedded Excel chart references are not readable.
- Removed the rebuild-only Chart Dashboard fallback message for workbooks that still contain enough projection data to chart in the UI.
- Bumped frontend/static cache-busters and synced dashboard assets.


## v8.3 Results Explorer cashflow heading/progress UX fix
- Smoothed Results Explorer load progress so it updates continuously and stays capped until the server returns real page data.
- Changed progress label to an estimated percentage to avoid implying exact server-side progress during a single request.
- Improved result table heading detection so Cashflow and other wide sheets use workbook-derived heading rows instead of generic Measure labels.
- Replaced generic column-group button labels with human-readable workbook labels or year ranges.
- Added sticky section/table heading support so the meaningful heading row stays visible while scrolling.
- Bumped frontend/static cache-busters and synced dashboard assets.


## v8.3 Results Explorer browser chart rendering fallback
- Added Results Explorer chart reconstruction from embedded Excel chart objects and their source-range formulas when the hidden chart data sheet is missing or stale.
- Kept Chart Dashboard chart-only in the UI while avoiding the fallback message that asked users to download the workbook for charts.
- Added compatibility fallback for older visible chart-helper tables so existing workbooks can still display charts in the browser.
- Updated Chart Dashboard progress/help text to describe workbook chart data rather than hidden ranges only.
- Bumped frontend/static cache-busters and added regression coverage for embedded-chart fallback rendering.


## v8.3 UI startup bootfix
- Restored missing frontend startup/save/build API helper functions removed during the Results Explorer polling patch.
- Fixed full UI hanging at the initial “Checking server...” status before any /api/v8/ping request was sent.
- Bumped frontend/static cache-busters.


## 2026-06-13 - YTD Transaction Table Amount Formatting Fix
- Tightened the YTD Transactions Date column to reduce wasted horizontal space.
- Displayed transaction Amount cells as USD currency while preserving raw numeric values for save/export.
- Highlighted negative transaction amounts in red with tabular-number alignment for faster scanning.
- Added focus/blur behavior so Amount fields edit as raw numbers and return to currency display after editing.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Results Explorer loading resilience
- Renamed remaining user-facing workbook-result language to Results Explorer.
- Added browser-safe selected-page loading for dense Result Explorer sheets, including Asset Allocation, so they return a bounded UI preview instead of hanging at the progress bar.
- Added chart dashboard series/slice compaction so native UI chart rendering stays responsive while the downloadable workbook remains the full Excel source.
- Added selected-sheet request sequencing so stale in-flight result loads cannot overwrite the newly selected result page.
- Bumped dashboard JS/CSS cache-busters and kept frontend/static dashboard assets in sync.


## 2026-06-13 - YTD Account Mapping Liability and Current Value UI Fix
- Removed Prior Year End Date from the visible YTD account/source mapping table; the backend still defaults legacy/internal 12/31 dates for growth series anchoring.
- Kept editable Current Value immediately after Prior Year End Balance for non-investment account/source types.
- Removed the disabled Add transaction account selector/button from the mapping UI; uploaded transaction accounts continue to seed automatically.
- Replaced the flat account-type pulldown with grouped Assets and income sources, Liabilities, and Other sections.
- Replaced the generic Liability option with Credit card, Mortgage, HELOC, Loan, and Other liability options, while normalizing legacy Liability values forward.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Detailed Results Chart-Only Dashboard and UI Grouping Fix
- Changed the workbook Chart Dashboard sheet to show charts only; chart source data is written to a hidden `_Chart Dashboard Data` sheet.
- Changed the Detailed Results explorer Chart Dashboard page to render native UI chart cards instead of chart-helper data tables.
- Hid workbook helper sheets from the Detailed Results navigation.
- Removed Excel row numbers and column-letter fallbacks from the explorer tables.
- Added UI-native column grouping for wide result tables, with detail column groups collapsed by default.
- Kept search behavior usable by expanding all columns while a sheet search is active.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.

## 2026-06-13 - YTD Account Current Value Inline Add Fix
- Added a Current Value column to YTD account/source mapping for non-investment account types.
- Investment current values remain disabled in the YTD table because they are derived from mapped client_holdings.csv holdings.
- Replaced the Add account/source prompt modal with inline account/source name and account-type controls.
- Removed the Notes column from the YTD account/source table to save horizontal space.
- Added sticky action-column styling so the Delete button remains visible while horizontally scrolling.
- Bumped dashboard JS/CSS cache-busters and synced frontend/static dashboard assets.


## 2026-06-13 - Detailed Results Nav Persistence Fix
- Preserved the View Detailed Results left-nav expansion state across dashboard re-renders, progress ticks, workbook refreshes, and route changes.
- Saved the expanded/collapsed state in browser localStorage so the nav remains open after refresh until the user closes it.
- Automatically keeps the detailed-results nav open when the detailed-results screen or a workbook sheet is selected.
- Broadened regression checks for the detailed-results nav state wiring and cache-buster.
- Bumped dashboard JS/CSS cache-busters.

## 2026-06-13 - Detailed Results Loading Progress Fix
- Added a visible staged progress display for View Detailed Results while the workbook explorer loads.
- The progress display now appears both in the main detailed-results screen and the left-nav detailed-results group.
- Added a 120-second timeout for the detailed-results API request so the UI reports a recoverable error instead of staying indefinitely on Loading workbook results.
- Added detailed-results refresh/error guidance and regression checks for the progress UI.
- Bumped dashboard JS/CSS cache-busters.


## 2026-06-13 - Detailed Workbook Results Explorer
- Added a collapsed bottom-left navigation group labeled View Detailed Results.
- Added a read-only workbook result explorer that parses retirement_plan.xlsx into topic-grouped sheets and natural blank-row-separated sections.
- Added /api/v8/detailed-results for workbook-aware JSON output, preserving all non-blank workbook rows and cell values.
- Added section-level accordions, sheet/category navigation, in-sheet search, sticky row/column headers, and workbook download/refresh actions.
- Bumped dashboard JS/CSS cache-busters.


## 2026-06-13 - YTD Income Category Whitelist Fix
- Changed YTD income classification to use only the explicit income categories: Paychecks, RedMane Annual Note P&I, Dividends and Capital Gains, other Income, and Interest.
- Treated positive cash/spending-account transactions outside those categories as refunds that reduce spending by category.
- Kept Transfer, Buy, Sell, and other ignored flows out of YTD income.
- Exposed the allowed income-category list in the YTD summary and added it to the YTD income chart helper text.
- Bumped dashboard JS cache-buster.

## 2026-06-13 - YTD Growth Straight-Line Holdings Chart Fix
- Changed displayed YTD investment growth to current mapped holdings value from client_holdings.csv minus the 12/31 prior-year balance.
- Left net investment cashflow visible as diagnostics only; it no longer reduces the YTD growth chart/value.
- Added a dedicated two-point growth_series from the 12/31 value to today's mapped holdings value so the YTD growth chart renders as a straight line.
- Updated the YTD growth card to show current value as the comparison value and use range scaling so the line movement is visible.
- Bumped dashboard JS cache-buster.

## 2026-06-13 - YTD Account Setup Save Button Activation Fix
- Fixed YTD account-mapping dirty-state behavior so Save account setup activates immediately after editing mapped account, prior-year balance/date, notes, or role without requiring a full table re-render.
- Fixed Save transaction edits to activate immediately after inline transaction edits using the same explicit dirty-button refresh helper.
- Added tooltips clarifying that “All transaction accounts already added” only disables adding new rows; existing account-mapping rows remain editable and saveable.
- Bumped dashboard JS cache-buster.

## v8.3 - Temporary YTD Income Category QA Patch

- Added temporary Top 20 YTD income categories ranked by filtered YTD income amount.
- Placed the income-category QA table immediately before the Top 20 YTD spending categories table.
- Bumped the dashboard JS cache-buster.

## v8.3 - Real Estate Tax Annual Adjustment Patch

- Added Annual RE Tax Adjustment under Cashflow / Mortgage in the Mortgage and RE Tax guided UI.
- Backfilled the new real_estate_tax_annual_adjustment_pct row for older Plan Data folders.
- Updated cash-flow projection logic so real-estate taxes use the dedicated RE-tax adjustment rate rather than general CPI.
- Exposed the RE-tax adjustment in YTD expected-spending plan components and UI detail text.

## v8.3 - Mortgage Real Estate Tax and YTD Category QA Patch

- Added an annual real-estate/property tax input under Cashflow / Mortgage and surfaced it in the User UI as Annual Real Estate Taxes.
- Renamed the guided step to Mortgage and RE Tax and the cash-flow/reporting bucket to Mortgage + RE Tax.
- Included real-estate taxes with mortgage/housing cash flow instead of core spending, including YTD expected-spending plan components.
- Added a temporary Top 20 YTD spending categories table sorted by filtered YTD spending amount for QA/testing.


## v8.3 - YTD Expected Spending Cleanup

- Excluded Buy, Sell, Transfer, Credit Card Payment, 401k Match, 401k Contribution, and HSA Contribution transaction flows from actual YTD spending.
- Expanded tax classification to catch plural tax categories such as Income Taxes and Real Estate Taxes.
- Changed the YTD spending comparison from annualized actual spending to expected YTD planned spending: core spending + mortgage + current-year large discretionary expenses, prorated through the latest transaction date.
- Updated the YTD spending card to label the comparison as Expected YTD and show the plan components used.

## Items 73-75 Core Spending UI Label/Order Patch

- Renamed Annual Spending Base Year to Core Spending Base.
- Renamed Stop Increasing Core Spending After Year to Core Spending Increase Stops.
- Ordered Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, then the relevant increase-rate field.
- Removed the extra Core spending growth controls heading/panel from the Spending UI.
- Kept CPI/manual conditional visibility intact.

# Golden Master Changelog

## 2026-07-08 — DAF activation baseline

Item 165: the Donor Advised Fund feature was activated (`input/client_assets.csv`
`enabled` flipped FALSE -> TRUE). DAF contributions reduce taxable income/AGI,
which lowers lifetime tax and lets more of the tax savings compound as
reinvested surplus, raising terminal net worth. Re-pinned golden-master anchors
to the new DAF-on baseline (`RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`):

- `tests/test_2_recommendations.py` sample projection: terminal NW
  11,322,944.15 -> 12,240,766.96; lifetime tax 1,457,473.34 -> 1,553,887.13.
- `tests/fixtures/golden_master_engine_cases.json` (all fields regenerated via
  `_load_engine_config()`/`_project_metrics()` for each stress case):
  - baseline_balanced_couple terminal NW: 11,302,319.79 -> 12,271,511.44
  - no_voluntary_roth_policy terminal NW: 11,322,944.15 -> 12,240,766.96
  - high_spending_pressure terminal NW: 9,650,443.84 -> 10,507,510.24
  - lower_return_environment terminal NW: 6,834,296.87 -> 7,301,149.28
  - early_survivor_compression terminal NW: 9,660,911.67 -> 10,541,882.92
- Regenerated `input/plan_data_manifest.json` via
  `python tools/check_plan_data_sync.py --write` to resync `client_assets.csv`
  (DAF flag) and `client_spending.csv` (pre-existing drift unrelated to DAF,
  cleaned up in the same pass).

## 2026-06-10 — v8.3 expert-assessment remediation

The sample-plan golden masters were recertified after implementing the independent expert-assessment recommendations that materially change plan arithmetic:

- deterministic wellness spending now includes pre-65 bridge premiums, Medicare Part B/D base premiums, and household OOP estimates;
- taxable-account portfolio distributions now enter AGI, Social Security provisional income, IRMAA MAGI, NIIT, state tax, and cash-flow funding;
- taxable-account price appreciation is reduced by modeled distribution yield to conserve total return;
- property tax and mortgage interest now enter itemized deductions;
- Social Security claim age is honored and survivor benefits are symmetrical;
- S-corp Additional Medicare Tax and QBI/distribution treatment were corrected;
- the temporary senior deduction and Illinois estate-tax cliff/interrelated calculation were added;
- Roth strategy scoring now discounts lifetime taxes to plan-start present value.

New certified sample-plan anchors:

- no-voluntary-Roth terminal net worth: $3,153,697.55;
- no-voluntary-Roth lifetime tax: $664,993.51;
- optimizer baseline terminal net worth: $3,153,697.55;
- optimizer baseline lifetime tax: $660,749.77.

The terminal net-worth decrease versus the previous pin is expected and is mainly the result of previously collected wellness costs and taxable portfolio income now being modeled.

## 2026-06-11 — Full checklist completion pass

- Re-pinned deterministic golden anchors after replacing the home-sale LTCG prior-year stacking approximation with current-year ordering and enabling per-year tax-index paths in projection/Monte Carlo plumbing.
- Expected first-order drift: small lifetime-tax movement from current-year LTCG ordering; small RMD/tax drift in stress fixtures from per-spouse/path-indexed logic.
- Validation: full unittest suite and release gate logs in the full-checklist package artifacts.

## v8.3 Core Spending final UI cleanup
- Removed DAF Annual Contribution from Core Spending.
- Made Core Spending fields render in a flat, no-subheading list.
- Enforced order: Core Spending Base, Core Spending Increase Stops, Core Spending Increase Method, then CPI/manual growth rate.

## v8.3 - YTD Spending & Growth Tracking

- Added a gated YTD spending/income/growth module in the User UI.
- Added transaction CSV upload with strict header validation and replace/incremental import modes.
- Added editable transaction table with search, filter, sort, manual add/edit/delete, and bulk save.
- Added account mapping and 12/31 prior-year balance table for growth calculations.
- Added `ytd_transactions.csv`, `ytd_account_setup.csv`, and `ytd_import_history.csv` as clean Plan Data files.
- Added initial YTD spending, income, and growth forecast charts.

## v8.3 - YTD Refund Netting and Holdings-Derived Balances

- Treat positive transactions in Cash / spending accounts as refunds that reduce spending in the same category instead of counting as YTD income.
- Keep Buy, Sell, Transfer, Credit Card Payment, 401k Match, 401k Contribution, and HSA Contribution out of both spending and income totals.
- Removed the Current Balance field from the YTD account-mapping UI and account setup CSV schema.
- Derive current investment balance for YTD growth from mapped client_holdings.csv accounts.
- Updated YTD regression tests and bumped the dashboard JavaScript cache-buster.

## 2026-06-13 - YTD Account Source Mapping + Core Spending Order
- Moved Core Spending Increase Method to the first field in the Core Spending page so dependent fields appear after the controlling choice.
- Added an always-available Add account/source action to YTD account mapping for pensions, annuities, Social Security, offline assets, real estate, note receivables, liabilities, and other manual rows.
- Broadened YTD account Role/Type options while preserving automatic transaction-account seeding.
- Preserved broader account/source role values in ytd_account_setup.csv for future income/net-worth workflows.

## 2026-06-13 - YTD Current Values + Detailed Results On-Demand Loading
- Added editable Current Value input for non-Investment YTD account/source rows while keeping Investment current value derived from mapped client_holdings.csv holdings.
- Removed the YTD Account Mapping Notes column to reclaim table width and keep the Delete action visible.
- Replaced the manual Add account/source pop-up with inline account/source name and type controls.
- Changed Detailed Results loading to a lightweight workbook-index request followed by selected-sheet on-demand loading, avoiding one large all-workbook JSON request that could stall at 92%.
- Added separate progress and timeout handling for selected-sheet parsing.
- Synced canonical frontend and build-time static dashboard assets and bumped cache-busters.

## 2026-06-13 - Results Explorer Polling and Server Status Stability
- Prevented the Results Explorer nav open/close state from triggering extra detailed-results sheet loads.
- Added in-flight request de-duplication for the results index and selected result sheets so the same sheet is not requested repeatedly while cached or already loading.
- Removed detailed-results progress text from the left nav; progress remains in the main Results Explorer pane only.
- Made periodic server health checks silent when the server is already online and avoided marking the server stopped while a known Results Explorer request is in flight.
- Reduced sidebar re-renders from the health poll so the UI no longer flips between “Checking server” and “Server stopped” during active explorer work.

## v11 roadmap items 1–8 completion build

- Expanded canonical `PlanResult` to include projection rows, summary metrics, semantic result pages, renderer-neutral report spec, event log, validation, and tax-law dataset summary.
- Completed the local typed plan store by writing relational member/account/income/spending tables in SQLite and making SQLite snapshots the runtime source before legacy settings rows.
- Preserved CSV/JSON/YAML as import/export adapters and legacy display-string round-trip surfaces, not as the canonical runtime model.
- Replaced new-code tax-law access with a dated local `tax_law_v10` dataset containing values and ordinary bracket tables; `tax_constants.csv` remains a compatibility adapter.
- Completed the projection pipeline contract with explicit per-stage completion events and stage summary metrics while preserving the deterministic engine as the validation oracle.
- Added regression coverage for roadmap items 1–8 completion.


## 2026-06-26 - Roadmap steps 1-11 execution pass

- Added Phase 3 frontend and server ownership seams: `frontend/js/modules/phase3_module_manifest.js`, `frontend/js/dashboard_source_truth_banners.js`, and `src/server/route_manifest.py` group existing behavior by plan-state/build, detailed results, navigation, spending, holdings, strategy, settings, and route domains without moving decorators yet.
- Extended `build_snapshot_v1` with active SQLite database metadata and an immutable `plan_database_snapshot.rpx` copy beside output artifacts.
- Added snapshot compare/restore helpers and `/api/plan/snapshot/compare` plus `/api/plan/snapshot/restore` routes with hash validation and pre-restore database backup.
- Added dependency-free typed API contract registry in `src/api_contracts.py` and exposed it at `/api/contracts`.
- Added route ownership and deprecated-spending-wrapper manifests for future route splitting.
- Added roadmap journey guard tests for first-run build, transactions-to-spending-sync, holdings-to-allocation, and snapshot restore surfaces.
- Expanded explainable recommendations to state residency and withdrawal sequencing pages.
- Added first-run optional skip reason and Review-and-Build closeout UI.
- Added source-of-truth labels to data-heavy/report pages.
- Added spending-flow breadcrumbs and next-step actions.
- Added Plan Data Summary print/save-PDF preview controls.
- Added Detailed Results readability tools: important-row jump list and sheet search support.
- Added glossary-on-hover titles and keyboard shortcuts for Save, Build, Search, Review, and next/previous step navigation.
## 2026-06-26 - Roadmap continuation: batch assumption editing

- Added `dashboard_batch_assumption_edit.js` with preview-first batch edit tools for All Assumptions and guarded System Configuration rows.
- Plan assumption batch edits are staged through the existing dirty-row save model and require Save Changes before persistence.
- System Configuration batch edits require a field filter, before/after preview, explicit confirmation, and then write through `/api/admin/system-config`.
- Added preview CSV download for batch edits and documented the `batch_assumption_edit_v1` UI contract.
- Added typed API contract registry entries for `/api/admin/system-config` GET/POST.

## 2026-06-26 — Architecture and spending coherence follow-up

- Added `documentation/FLASK_REMOVAL_ARCHITECTURE.md`, proposing a dependency-free local HTTP runtime, transport-neutral request/response contracts, and a phased migration path that preserves existing `/api/...` URLs while removing Flask/Werkzeug from the packaged app.
- Added `documentation/PLANNING_WORKBENCH_CONSOLIDATION_PROPOSAL.md`, rationalizing Build Impact, Scenarios, Stress Tests, and Strategy into one Planning Workbench model with Baseline, Change Set, Run Type, and Impact concepts.
- Renamed user-facing premium language from legacy premium wording to Healthcare Premium.
- Consolidated healthcare premium taxonomy rows under one Healthcare Premium group, including Pre-65 Healthcare Premium, Medicare Part B, Medicare Part D, and Medicare Part G/Medigap premiums.
- Reclassified Annual Household Medical OOP Cap as a cap/reference rather than a standalone expense budget.
- Collapsed legacy travel-detail taxonomy rows into the Travel group and added normalization for legacy rows that still say Travel Detail.
- Updated Monthly Trajectory to include all non-tax spending actuals, including Housing, Wellness/healthcare, Travel, Large Discretionary, Business, and Core Expense outflows, while still excluding income, transfers, and taxes.
## 2026-06-26 — Flask-free service extraction pass

- Added `src/server_services/` as the feature-owned service layer for request-independent handler logic.
- Moved base/runtime payload logic into `base_service.py` while keeping `base_routes.py` as a thin HTTP adapter.
- Moved admin CSV/system-config/reference/diagnostics/server-status logic into `admin_service.py` while preserving existing admin URLs.
- Moved build summary, output metadata, and build-preflight readiness logic into `build_service.py`.
- Moved SQLite Plan Data form get/save/patch logic into `plan_forms_service.py`.
- Kept permission checks, request parsing, response serialization, file streaming, shutdown, audit hooks, and background build thread startup in route adapters.
- Documented remaining extraction targets: pricing, spending/YTD, holdings/assets/strategy, and build job orchestration.



## Immediate Next Actions Implementation

Implemented the first post-evaluation stabilization pass: restored documented contract/ownership files, exposed `/api/contracts`, added the healthcare terminology alias seam, started frontend extraction with `api_client.js` and `app_store.js`, started backend extraction with `pricing_service.py` and `holdings_service.py`, and added a clean-overlay validation tool.

## 2026-06-26 — Frontend modularization continuation

- Extracted navigation behavior into `frontend/js/navigation.js` with `RetirementNavigation` owning step changes, autosave-on-navigation guards, search-scope behavior, focus traversal, and global compatibility exports.
- Extracted Detailed Results shell rendering into `frontend/js/reports_ui.js` with `RetirementReportsUI` owning the workbook navigation tree and Results Explorer wrapper states while existing sheet/table/chart helpers remain in `dashboard.js` for the next pass.
- Extracted Planning Workbench browser-local case storage and workbench rendering into `frontend/js/planning_workbench_ui.js` with `RetirementPlanningWorkbench` owning `planning_case_v1`, comparison matrix rendering, adoption routing, and Build Impact context panels.
- Updated dashboard script loading order in both `frontend/index.html` and `output/index.html`; `dashboard.js` now keeps thin compatibility wrappers and context providers for the extracted modules.

## 2026-06-26 — Backend modularization continuation

- Added `src/server_services/ytd_service.py` and moved YTD transaction upload/add/update/delete/bulk-save, account setup save/recovery, SQLite mirroring, and legacy account setup recovery scoring out of `plan_routes.py`.
- Added `src/server_services/plan_file_service.py` and moved local plan save-as, load-file, and exit snapshot SQLite copy/checkpoint/retention logic out of `plan_routes.py`.
- Completed `/api/plan/load-file` behavior with source existence validation, pre-load database backup, stale WAL/SHM sidecar cleanup, database copy, and post-load `wal_checkpoint(TRUNCATE)`.
- Kept route modules as compatibility HTTP adapters that enforce permissions, parse request JSON, call feature services, and serialize responses.

## 2026-06-26 - Backend service extraction: async build jobs

- Added `src/server_services/build_job_service.py` as the feature-owned home for async build-job orchestration.
- Moved build progress registry, progress-line interpretation, desktop progress push fanout, stale-summary/build-id checks, and actionable build-error formatting out of `workbook_routes.py`.
- Kept `workbook_routes.py` as a thin adapter for authorization, request parsing, environment assembly, thread launch, and JSON/SSE progress responses.
- Updated release-package static checks and regression tests to validate the extracted build-job service instead of route-local progress globals.


## 2026-06-26 - Backend service extraction: report outputs

- Added `src/server_services/report_service.py` as the feature-owned service for report artifact lookup, Detailed Results model selection, local build-history persistence, and safe `/files/<path:filename>` validation.
- Refactored `/api/detailed-results`, `/api/history`, `/api/xlsx`, `/api/pdf`, and `/files/<path:filename>` so `workbook_routes.py` keeps only authorization, query parsing, response serialization, and audit hooks.
- Extended the route manifest and typed API contract registry with report/build-history ownership details.
- Updated clean-overlay validation to compile the new report service during pristine-baseline overlay checks.

## 2026-06-26 - Backend service extraction: spending model

- Added `src/server_services/spending_service.py` as the feature-owned service for spending dashboard, category-map compatibility routes, taxonomy CRUD, mapping rules, budget seeding/load-actuals, aliases, unified budget rows, and spending summary/model payloads.
- Refactored spending routes in `src/server/plan_routes.py` into thin adapters that enforce permissions, extract JSON/query arguments, delegate to `SpendingService`, and serialize payload/status results.
- Extended the route ownership manifest and typed API contract registry with additional spending taxonomy, summary, and budget contracts.
- Added regression tests that keep spending service logic framework-neutral and prevent `spending_tracker` mutations from returning to the route module.
