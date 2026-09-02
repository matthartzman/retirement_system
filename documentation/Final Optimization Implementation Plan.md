# Final Optimization Implementation Plan

**Status:** Design and implementation plan — no changes in this document have been executed.

## 1. Executive decision

Replace terminal-net-worth optimization with a **constrained, multi-objective, state-contingent planning framework**. The framework must protect essential lifetime spending and liquidity first; among feasible plans, it should maximize **risk-adjusted, after-tax Lifetime Consumption-and-Transfer Value (LCV)**.

LCV is the present value of value delivered to the household and intended recipients:

\[
LCV = PV(\text{after-tax household consumption}) + PV(\text{lifetime gifts/charity}) + PV(\text{after-tax bequests})
\]

A plan with the largest projected terminal balance is not automatically best. It may underfund lifetime consumption, defer taxes inefficiently, create survivor-period bracket compression, or leave heirs tax-inefficient assets. Conversely, a plan that deliberately consumes assets can be superior if it protects essential spending and satisfies the household’s transfer goals.

The recommended decision sequence is:

1. Model household spending, taxes, withdrawals, survivorship, and transfers by scenario and Monte Carlo path.
2. Eliminate plans that fail hard household safety, liquidity, governance, or required-transfer constraints.
3. Rank remaining plans by downside-sensitive LCV.
4. Use tax NPV, effective tax rates, flexibility, implementation simplicity, and legacy quality to explain close choices and break ties.
5. Present a pre-committed adaptive spending and conversion policy, not merely a retrospective failure calculation.

---

## 2. What the system already does

The current system is mature. Much of the core deterministic tax, withdrawal, estate, and planning machinery is already present.

| Capability | Location | State |
|---|---|---|
| Ordinary, qualified-dividend, and long-term-capital-gain income split | `deterministic_engine.py`, `core.py` | Complete |
| Federal and Illinois income tax | `core.state_income_tax`, `illinois_estate_tax` | Complete |
| RMDs and pre-tax depletion | `deterministic_engine.py`, Sheet 20 RMD Audit | Complete |
| Roth conversions and conversion-funding source | `planning_engines.py:1871+`, Sheet 11 | Complete |
| Social Security taxation and IRMAA guardrails | `planning_engines.py:1372+` | Complete |
| QCD, charitable, and deduction interaction | Sheet 12 Charitable Giving | Complete |
| Asset location and withdrawal order | `src/allocation_policy.py`, Sheet 24 | Complete |
| Death-year basis step-up | `after_tax.py:298-345` | Complete |
| Estate tax, indexed exemption, and Illinois no-portability | `after_tax.py:517+` | Complete |
| Inherited-IRA 10-year schedules by beneficiary | `after_tax.py:89-130`, Sheet 14 | Complete |
| Per-person longevity sampling | `_mc_vectorized_sample_death_ages` | Complete |
| Deterministic survivor-spending adjustment | `deterministic_engine.py:301-314, 1100` | Deterministic only |
| P50/P90 legacy output | `terminal_total_nw` percentiles | Complete |
| Required-cut sizing on failing paths | `_mc_required_cut_distribution` | Partial |
| Sustainable-spending solve at success thresholds | `sustainable_spending_solve` | Partial |
| Essential/discretionary floor check | `essential_discretionary_floor_check` | Post-hoc only |
| Stress scenarios | Sheets 15–18, `run_scenario()` | Complete/partial |
| Multi-component Roth objective | `planning_engines.py:2184` | Partial |

The deterministic engine is already detailed enough to anchor tax, estate, and transfer logic. The primary rework is not replacement of those calculations; it is making the stochastic layer emit the household outcomes needed to make a consumption- and transfer-centered decision.

---

## 3. Material gaps

### Gap A — Monte Carlo emits balances, not realized spending

`_mc_vectorized_projection` returns per-path account and funding matrices such as `pretax`, `roth`, `taxable`, `hsa`, `cash`, `liquid`, `total`, and `unfunded`. It does not return realized spending by year or tier.

Consequences:

- P5/P10 real annual spending cannot be calculated.
- Probability that essential spending is fully funded cannot be calculated.
- Probability, depth, and duration of actual spending cuts cannot be calculated.
- LCV cannot be reliably calculated because its principal component is after-tax lifetime consumption.
- A terminal wealth percentile can be mistaken for household welfare even when the path involved severe lifestyle reductions.

### Gap B — Monte Carlo samples first death but does not apply survivor economics

`_mc_vectorized_death_years` returns household and spouse death timing, yet the projection uses only the maximum death year as an activity cutoff. It does not apply the first-death transition within each path.

The missing path-level effects are material:

- Survivor spending adjustment.
- Loss of a Social Security or pension payment.
- Joint-to-single filing-status bracket compression.
- Survivor-period RMD and ordinary-income concentration.
- Survivor-period consumption, liquidity, and tax-risk reporting.

### Gap C — Essential spending is a label rather than a modeled constraint

The existing essential/discretionary check reclassifies a calculated uniform cut after the fact. It does not direct withdrawals or constrain optimization. `cut_mult` applies a uniform change to all spending-funded withdrawals, and contingent spending is not part of the taxonomy.

### Gap D — Objectives focus on wealth at death

Current objectives include several thoughtful wealth terms—after-tax terminal net worth, lifetime tax, legacy, estate tax, survivor tax risk, ACA premium-tax-credit effects, and liquidity tie-breakers. However, they still evaluate deterministic terminal wealth rather than lifetime after-tax consumption and transfer value across stochastic paths.

### Gap E — Tax comparison does not fully express timing and future burden

Lifetime nominal taxes are not an apples-to-apples comparison of an early Roth-conversion tax payment and a later RMD tax payment. The model needs plan-scope **net present value of taxes**, clear effective-tax-rate reporting, and specific identification of survivor-period tax exposure.

### Gap F — No adaptive spending policy runs inside simulation

Existing spending-cut calculations are diagnostics. Guardrails exist for Roth conversions, but no pre-committed withdrawal-rate band, ratchet, cut trigger, or recovery rule is applied within the Monte Carlo recursion.

---

## 4. Target decision framework

### 4.1 Hard feasibility gate

Evaluate every candidate plan through `plan_feasibility(case, mc_result) -> {passed, violations[]}` before it is scored. A plan that fails a hard constraint is presented as infeasible or requires a documented exception; it is not allowed to win by compensating for unacceptable risk elsewhere.

Default hard constraints should be household configurable:

| Constraint | Recommended test |
|---|---|
| Essential spending protection | `P(essential fully funded)` at or above household threshold |
| Downside liquidity | Liquidity coverage at or above the required floor at a specified percentile/path threshold |
| Essential shortfall severity | Maximum permitted essential-spending reduction and duration |
| Required transfer goal | Probability of after-tax legacy/charitable transfer meeting user floor, when applicable |
| Governance readiness | Existing document, beneficiary, insurance, and other checks in `governance.py` |

Use separate settings for a household whose primary objective is lifetime lifestyle versus one for which a legacy or charitable floor is non-negotiable.

### 4.2 Primary score: risk-adjusted LCV

Report two LCV values for each feasible plan:

- **Expected LCV:** probability-weighted expected present value of after-tax consumption, lifetime gifts/charity, and after-tax bequests.
- **Certainty-equivalent LCV:** a downside-sensitive LCV used for ranking. It applies tier weights and a CRRA-style risk-aversion preset so that a plan with the same expected value but more severe spending risk ranks lower.

Use spending tiers to ensure the model treats a reduction in medication, housing, or basic care more seriously than a reduction in travel or discretionary gifting. Do not attempt to estimate an academically precise household risk-aversion coefficient. Expose simple presets such as conservative, balanced, and growth-oriented.

A practical structure is:

\[
CE\text{-}LCV = CE(PV(\text{essential consumption})) + w_I \cdot CE(PV(\text{important consumption})) + w_C \cdot CE(PV(\text{contingent consumption})) + w_T \cdot CE(PV(\text{transfers}))
\]

where the essential tier has the strongest shortfall penalty and transfer weighting is household configurable. This is a ranking implementation, not a claim that one universal utility function can describe every household.

### 4.3 Tax reporting and tax decision metrics

Calculate and display the following for every candidate plan:

| Measure | Definition and purpose |
|---|---|
| NPV of plan-scope taxes | Present value of income, capital-gains, and applicable state taxes from the current year through plan end; makes early Roth-conversion tax comparable with later RMD tax |
| Nominal plan-scope taxes | Cash-flow visibility and intuitive total-tax reporting |
| Nominal ELTR | Total plan-scope taxes divided by total plan-scope gross external cash flow |
| Discounted ELTR | NPV of plan-scope taxes divided by PV of plan-scope gross external cash flow |
| Marginal conversion tax rate | Incremental tax cost of the next conversion tranche, including ordinary tax, capital-gain interaction, IRMAA/ACA effects where applicable |
| Survivor-period tax burden | Taxes, taxable income, filing status, RMDs, and surcharge exposure after first death |
| Estate/heir tax estimate | Estate, inheritance, and inherited-account tax impact reported separately from annual household ELTR |

Define “future” as the full scope of the plan, including the current year, as requested. Do not automatically blend estate and heir taxes into household ELTR; report them separately and include them in after-tax transfer value within LCV. This avoids obscuring the distinction between household operating tax burden and transfer-level tax friction.

ELTR is a useful communication metric, not a standalone optimizer objective. It can conceal timing, taxable-income concentration, and marginal-rate effects if viewed alone.

### 4.4 Layered risk dashboard

Do not replace one imperfect metric with another. Retain `success_rate`, but define it clearly and present it alongside spending, liquidity, tax, and transfer outcomes.

| Category | Required outcome |
|---|---|
| Essential security | Probability essential spending is fully funded; P5/P10 essential real spending; worst essential shortfall and duration |
| Total lifestyle | P5/P10 real annual total spending; probability of any cut; cut depth and longest cut duration |
| Liquidity | Percentiles of `liquid / required_liquidity_floor`; frequency and duration of reserve breach |
| Legacy and transfer | P5/P50/P90 after-tax terminal transfer value; probability of meeting legacy floor; estate/heir tax at selected percentiles |
| Terminal wealth | P5/P50/P90 ending wealth, clearly labeled as residual wealth rather than lifetime welfare |
| Familiar planning measure | Retained success rate, with its exact failure condition documented |
| Survivor state | All material spending, tax, liquidity, and transfer outcomes conditioned on post-first-death years |

The **5th-percentile ending wealth** measure should be added and highlighted as a downside reserve/legacy indicator. It must not replace the probability of essential-spending funding or the spending-cut distribution, because a household can end with wealth after enduring poor mid-plan consumption—or consume intentionally while ending with less wealth.

### 4.5 Tie-breaks and explanation layer

For feasible plans with materially similar certainty-equivalent LCV, rank or explain differences using:

1. NPV of plan-scope taxes.
2. Marginal and survivor-period tax exposure.
3. Probability and quality of meeting transfer goals.
4. Flexibility: fraction of spending that is important or contingent rather than essential.
5. Implementation simplicity, operational burden, and governance readiness.
6. Stability under sequence, tax-law, longevity, long-term-care, and survivor stress scenarios.

---

## 5. Implementation roadmap

### Phase 0 — Spending-tier taxonomy

Create a configurable spending taxonomy above the existing category structure:

- `essential`: core spending, housing, insurance, baseline transportation, core health care, required taxes.
- `important`: travel, dining, hobbies, gifts, family support, home projects, and other quality-of-life spending.
- `contingent`: long-term care, major medical needs, home modifications, and other irregular or shock-driven costs.

Implement a `SPENDING_TIERS` registry in `spending_budget_resolver.py`, keyed to existing spending categories and overrideable through the same CSV/database configuration path used for other user settings. Emit `row['spend_by_tier']` from the deterministic engine.

**Acceptance criteria:** No change to golden-master results in this phase. The output is a new classification layer only. Maintain the current core-spending scope rule; tiers sit above existing buckets rather than redefining `spend_base`.

### Phase 1 — Per-path spending, transfers, and survivor state

Enhance `_mc_vectorized_projection` and `monte_carlo_exact_scalar` in parallel.

1. Emit real, plan-start-dollar matrices for `spend_real`, `spend_essential_real`, `spend_important_real`, and `spend_contingent_real`.
2. Emit path/year tax and gross-cash-flow fields sufficient to calculate tax NPV and ELTR.
3. Emit realized lifetime-gift/charitable-transfer values where relevant.
4. Thread `first_death_years = np.minimum(h, w)` into the recursion.
5. After first death, apply survivor spending factors by tier, remove decedent-specific Social Security/pension income, and switch to survivor filing-status tax logic or a targeted state-contingent approximation.
6. Preserve final-death and estate handoff logic for transfer calculations.

**Acceptance criteria:**

- Scalar and vectorized engines agree within defined tolerances on selected fixed-seed fixtures.
- Deterministic survivor cases reconcile with corresponding path-level survivor behavior.
- A fixture proves that spending, benefit, and filing-status changes occur after first death.
- All values are consistently reported in real plan-start dollars where labeled real.

### Phase 2 — Tiered cuts, risk dashboard, and P5 terminal outcomes

Replace uniform `cut_mult` behavior with a declared spending-priority policy:

1. Reduce `contingent` spending first.
2. Reduce `important` spending next.
3. Reduce `essential` spending only if higher tiers cannot absorb the required adjustment.
4. Record attempted, planned, and realized spending; a cut must be observable rather than inferred after the fact.

Compute and display the layered risk dashboard in Sheet 15 and dashboard tiles. Avoid creating a separate sheet unless reporting constraints require it.

Add:

- P5/P10 real spending by tier and total.
- Probability essential spending is fully funded.
- Probability of any cut, worst cut depth, and longest consecutive cut duration.
- Liquidity coverage distribution.
- P5/P50/P90 terminal wealth.
- P5/P50/P90 after-tax transfer/legacy value and probability of meeting a user legacy floor.
- Separate survivor-period dashboard rows.
- Retained and clearly defined `success_rate`.

**Acceptance criteria:** A deliberately underfunded fixture cuts contingent, then important, then essential spending in order. Separate fixtures prove dashboard measures move in the expected direction when initial assets, spending, liquidity, or sequence risk change.

### Phase 3 — Tax NPV, ELTR, and targeted stochastic tax approximation

Use the detailed deterministic tax engine as the ground truth and retain it for deterministic plans, stress scenarios, and finalists. Avoid an immediate full exact tax-engine run across every Monte Carlo path.

Instead, upgrade the MC `tax_drag` approach to be state contingent:

- Joint versus survivor filing status.
- Coarse taxable-income/RMD/withdrawal brackets.
- Pre-tax withdrawal and conversion amounts.
- Social Security taxation and surcharge thresholds where material.
- State-tax treatment.

Calculate plan-scope nominal taxes, tax NPV, nominal ELTR, discounted ELTR, marginal conversion tax rates, and survivor-period tax measures.

**Acceptance criteria:** For a selected set of representative paths, approximate MC tax outputs reconcile to exact deterministic-tax reruns within documented materiality tolerances. A test case demonstrates why identical nominal taxes paid in different years produce different tax NPV.

### Phase 4 — Feasibility gate and LCV comparison service

Implement the decision service in separable components:

- `plan_feasibility(case, mc_result)` returns a passed/failed result and explicit violations.
- `lc v_components(case, mc_result)` or an equivalently named implementation returns consumption, transfer, tax, and risk-adjustment components.
- `score_feasible_plan(case, mc_result)` returns expected LCV, certainty-equivalent LCV, supporting metrics, and tie-break evidence.

Use a valid code identifier such as `lcv_components`; the spacing above is conceptual only.

Expose configurable presets for:

- Risk sensitivity / CRRA-like curvature.
- Tier weights.
- Required essential-funding probability.
- Liquidity floor and percentile test.
- Maximum allowable essential cut and duration.
- Legacy/charitable floor and required probability, if applicable.

Wire the output into Planning Cases so saved alternatives can be ranked and compared. Provide a concise explanation: “infeasible,” “higher risk-adjusted LCV,” “similar LCV but lower tax NPV,” or “similar economic outcome but simpler implementation.”

**Acceptance criteria:** A fixture that violates every hard constraint fails. A plan with higher expected LCV but unacceptable essential-spending risk is rejected. A pair of feasible plans with similar expected value but different downside spending produces the intended certainty-equivalent ranking.

### Phase 5 — Adaptive spending and conversion guardrails

Implement a policy object evaluated inside both Monte Carlo engines. The policy should include configurable:

- Withdrawal-rate or portfolio-value bands.
- Important-spending cut trigger.
- Contingent-spending suspension/reduction rule.
- Essential-spending last-resort protection rule.
- Raise/ratchet condition after recovery.
- Conversion guardrails for tax brackets, IRMAA, ACA premium-tax-credit exposure, and liquidity funding.

The policy should be explicit enough to hand to a household or advisor as an operating rule, not merely a model artifact.

**Acceptance criteria:** Tests prove a portfolio drawdown triggers a pre-specified tiered adjustment and a later recovery permits the defined restoration. Report outcomes both with and without guardrails to make the trade-off visible.

### Phase 6 — Missing sensitivity scenarios

Use the existing `run_scenario(overrides)` harness to add:

- Front-loaded poor-return sequence risk over the first 5–10 years.
- Tax-rate/bracket increase scenario.
- Reduced federal estate-exemption scenario.
- Existing long-term-care, inflation, survivor, and home-sale scenarios expressed through the new spending/tax/LCV outputs.

For households near estate-tax, inherited-IRA, IRMAA, ACA, or bracket cliffs, produce targeted deterministic scenarios around those thresholds instead of relying on broad percentile reporting alone.

---

## 6. What not to do initially

| Deferred item | Rationale |
|---|---|
| Full exact tax engine on every Monte Carlo path | High cost. Targeted filing-status and bracket-aware approximation captures the key survivor/RMD concern. Escalate only if a household is demonstrably bracket-sensitive at the margin. |
| Academically calibrated household utility function | Not necessary. Spending tiers, transparent risk presets, and documented scenario weighting are practical and auditable. |
| Per-path estate-tax engine | Run deterministic estate calculations at selected P5/P10/P50/P90 wealth states and targeted threshold scenarios. Estate calculations are nonlinear but do not need to burden every path initially. |
| Nesting the full new score inside allocation optimization | The current allocation optimizer is already risk-aware. First use LCV to compare planning cases; revisit allocation-objective rewiring only if it changes recommendations materially. |
| Replacing success rate | Keep it as a familiar, documented metric. Place it beside the richer spending and liquidity outcomes. |
| Stochastic tax-law process | Use discrete, intelligible tax-law scenarios rather than an uncalibrated random process. |
| Treating reserve reporting as reserve protection | Report liquidity coverage first. Making `reserve_account` economically protective requires a separate investment-policy design decision. |

---

## 7. Testing, governance, and delivery controls

### Required controls

- Freeze live pricing with `RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1` before regenerating golden masters.
- Check `git status` on `input/` after every test run because the suite can mutate inputs.
- Apply every Phase 1, 2, and 5 change to both `monte_carlo_exact_scalar` and the vectorized engine.
- Create at least one intentionally violating fixture for every new feasibility constraint or guardrail; confirm it fails before considering the feature complete.
- Document definitions, discount rate, nominal/real basis, inclusions/exclusions, and period scope for every dashboard metric.
- Preserve a traceable audit record showing which policy parameters, tax assumptions, mortality assumptions, and scenario settings generated every comparison.

### Definition standards

- **Plan scope:** current year through the end of the modeled household/transfer horizon.
- **Real spending:** deflated to plan-start dollars using each path’s sampled inflation index.
- **Tax NPV:** discounted to plan-start dollars using the plan’s documented real or nominal discount-rate convention; do not mix conventions in the same report.
- **Gross external cash flow:** explicitly define inclusions and exclude internal account transfers to prevent ELTR distortion.
- **After-tax transfer value:** account value net of applicable estate tax, projected beneficiary income tax, and relevant transfer friction under the selected estate assumptions.

---

## 8. Recommended delivery sequence

### Budget-constrained stopping point

Complete Phases 0 through 2 first. This establishes spending tiers, path-level spending, survivor-state behavior, protected spending priorities, and the risk dashboard. It delivers the largest practical improvement because it makes lifestyle risk observable and makes essential-spending protection a simulated property rather than a reporting label.

### Recommended full sequence

1. Phase 0 — taxonomy.
2. Phase 1 — path-level spending, cash flow, transfers, and survivor state.
3. Phase 2 — tiered cuts and dashboard.
4. Phase 3 — tax NPV, ELTR, and state-contingent tax approximation.
5. Phase 4 — feasibility gate and risk-adjusted LCV ranking.
6. Phase 5 — adaptive guardrails.
7. Phase 6 — expanded stress scenarios.
8. Golden-master regeneration, reconciliation, changelog, and advisor/reporting review after each behavior-changing phase.

Phases 0–2 are foundational. Phases 3–4 establish the requested LCV and tax-comparison decision architecture. Phases 5–6 turn the framework into an actionable ongoing policy and test its durability under specific adverse conditions.

---

## 9. Final recommendation

The implemented system should answer this question:

> Which feasible plan delivers the greatest risk-adjusted, after-tax lifetime consumption and transfer value while protecting essential spending, maintaining liquidity, managing tax timing, and meeting the household’s stated legacy goals?

Use terminal wealth as an important supporting outcome, especially P5/P50/P90 after-tax legacy value, but not as the principal definition of success. Use success probability as a retained orientation metric, but never in isolation. Use tax NPV and ELTR to explain tax efficiency, while keeping marginal tax and survivor-period tax risk visible. Most importantly, incorporate the household’s pre-committed adaptive spending and conversion rules into the simulation so that the recommended plan is operational, not merely statistically attractive.
