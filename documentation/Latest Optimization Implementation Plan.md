# Final Optimization Implementation Plan

**Status:** Design and implementation plan — revised for robust policy selection and adaptive execution.

---

## 1. Executive Decision

Replace static terminal-net-worth optimization with a **constrained, multi-objective, robust policy selection framework**. The framework must protect essential lifetime spending and liquidity first; among feasible candidate policies, it evaluates choices based on their **risk-adjusted, after-tax Lifetime Consumption-and-Transfer Value (LCV)**, tested across a broad range of market, tax, and longevity states.

The optimization object is not a static cash-flow plan, but a **complete state-contingent policy**—including pre-committed adaptive spending, conversion, and withdrawal rules.

LCV represents the present value of economic utility delivered to the household and intended recipients:

$$LCV = PV(\text{after-tax household consumption}) + PV(\text{lifetime gifts/charity}) + PV(\text{after-tax bequests})$$

A plan with the largest projected terminal balance is not automatically best. It may underfund lifetime consumption, defer taxes inefficiently, create survivor-period bracket compression, or leave heirs tax-inefficient assets. Conversely, a policy that deliberately consumes assets can be superior if it protects essential spending and satisfies transfer goals.

The recommended decision sequence is:

1. Define adaptive candidate policies (spending guardrails, conversion bands, sequence response rules).


2. Model household spending, contingent liabilities, taxes, withdrawals, survivorship, and transfers across stochastic paths and stress scenarios.


3. Apply hard feasibility gates to eliminate policies that fail essential spending protection, joint liquidity/essential bounds, or required transfer floors.


4. Evaluate remaining policies using downside-sensitive LCV across varying risk preferences and discount rates.


5. Perform sensitivity, threshold-crossing, and ranking-robustness testing across alternative tax, longevity, and return regimes.


6. Require exact tax and estate engine validation for finalists and threshold-sensitive edge cases.


7. Select the **simplest policy whose advantage remains robust**, using tax NPV, effective tax rates, and operational simplicity as diagnostic tie-breakers.



---

## 2. System Capability Baseline

The current system possesses detailed deterministic tax, withdrawal, and estate machinery. The core task is to upgrade the stochastic layer so it emits complete, state-contingent household policy outcomes.

| Capability | Location | State |
| --- | --- | --- |
| Ordinary, qualified-dividend, and LTCG split | `deterministic_engine.py`, `core.py` | Complete

 |
| Federal and Illinois income tax | `core.state_income_tax`, `illinois_estate_tax` | Complete

 |
| RMDs and pre-tax depletion | `deterministic_engine.py`, Sheet 20 RMD Audit | Complete

 |
| Roth conversions and conversion-funding source | `planning_engines.py:1871+`, Sheet 11 | Complete

 |
| Social Security taxation and IRMAA guardrails | `planning_engines.py:1372+` | Complete

 |
| QCD, charitable, and deduction interaction | Sheet 12 Charitable Giving | Complete

 |
| Asset location and withdrawal order | `src/allocation_policy.py`, Sheet 24 | Complete

 |
| Death-year basis step-up | `after_tax.py:298-345` | Complete

 |
| Estate tax, indexed exemption, and IL no-portability | `after_tax.py:517+` | Complete

 |
| Inherited-IRA 10-year schedules by beneficiary | `after_tax.py:89-130`, Sheet 14 | Complete

 |
| Per-person longevity sampling | `_mc_vectorized_sample_death_ages` | Complete

 |
| Deterministic survivor-spending adjustment | `deterministic_engine.py:301-314, 1100` | Deterministic only

 |
| P50/P90 legacy output | `terminal_total_nw` percentiles | Complete

 |
| Required-cut sizing on failing paths | `_mc_required_cut_distribution` | Partial

 |
| Sustainable-spending solve at success thresholds | `sustainable_spending_solve` | Partial

 |
| Essential/discretionary floor check | `essential_discretionary_floor_check` | Post-hoc only

 |
| Stress scenarios | Sheets 15–18, `run_scenario()` | Complete/partial

 |

---

## 3. Corrected Structural Gaps

### Gap A — Monte Carlo Emits Balances, Not Realized Spending

`_mc_vectorized_projection` returns path account matrices but historically omitted realized annual spending by tier. Without tracking realized spending, LCV cannot be calculated, and severe mid-plan lifestyle cuts remain hidden behind terminal wealth percentiles.

### Gap B — Missing First-Death Survivor Economics

Sampling death ages without executing the survivor transition within Monte Carlo paths understates risk. Post-first-death dynamics—loss of Social Security/pension income, transition to single filing brackets, accelerated RMD concentration, and survivor spending adjustments—must be modeled dynamically per path.

### Gap C — Conflation of Discretionary Cuts and Contingent Liabilities

Treating long-term care (LTC) or major medical shocks as ordinary discretionary spending distorts baseline consumption logic. Contingent health liabilities must be isolated as dynamic, state-contingent liabilities rather than budget cuts.

### Gap D — Double-Counting and Static LCV Targets

Without explicit reconciliation rules, LCV calculations risk double-counting funds transferred between pre-tax accounts, taxable consumption, and eventual bequests. Furthermore, treating tax NPV as a primary objective can artificially favor plans that minimize tax at the expense of lifetime consumption quality. Tax NPV is reclassified strictly as a diagnostic metric.

### Gap E — Evaluating Static Plans Before Adaptive Policy Architecture

Ranking static projection paths before embedding adaptive spending, withdrawal, and conversion guardrails measures theoretical artifacts rather than executable policies. Adaptive rules must execute inside the simulation loop prior to policy ranking.

---

## 4. Target Decision & Policy Architecture

### 4.1 Feasibility Gate & Failure Metrics

Every candidate policy undergoes explicit feasibility validation (`plan_feasibility(policy, mc_result)`). Rather than relying on a binary "success rate," feasibility evaluates joint failures and duration metrics:

| Constraint | Evaluation Standard |
| --- | --- |
| **Essential Spending Protection** | $P(\text{essential fully funded}) \ge \text{threshold}$<br> |
| **Joint Liquidity/Essential Failure** | Zero occurrences where liquid reserves fall below floor *and* essential spending is unfunded

 |
| **Cumulative Shortfall Sizing** | Maximum total dollar shortfall across all tiers must not exceed policy risk tolerance

 |
| **Shortfall Duration** | Consecutive years of essential spending cuts limited to threshold (e.g., $\le 2$ years)

 |
| **Required Transfer Goal** | Probability of net after-tax legacy meeting user floor

 |
| **Governance Readiness** | Document, beneficiary, and insurance validation in `governance.py`<br> |

### 4.2 Primary Ranking Metric: Risk-Adjusted LCV

Feasible policies are scored using Certainty-Equivalent LCV ($CE\text{-}LCV$), incorporating spending-tier priorities and risk aversion:

$$CE\text{-}LCV = CE(PV(\text{essential})) + w_I \cdot CE(PV(\text{important})) + w_C \cdot CE(PV(\text{contingent})) + w_T \cdot CE(PV(\text{transfers}))$$

**LCV Reconciliation & Double-Counting Controls:**

* *Consumption:* Sum of actual net after-tax dollars spent on household baseline/discretionary needs.


* *Transfers:* Net after-tax dollars received by third parties or heirs.


* *Exclusion:* Internal transfers (e.g., IRA to taxable bank account) are tracked strictly as cash flow and excluded from LCV to prevent double counting.


* *Pre-Tax Adjustments:* Bequests of pre-tax accounts (Traditional IRA) are net of projected heir income tax taxes before inclusion in legacy LCV.



### 4.3 Tax Diagnostics & Validation Requirements

Tax metrics serve as diagnostic indicators rather than primary optimization goals:

* **Plan-Scope Tax NPV:** Discounted present value of all federal, state, and surcharge taxes across the plan horizon.


* **Discounted Effective Lifetime Tax Rate (ELTR):** Tax NPV divided by the present value of gross external cash flow.


* **Survivor Tax Concentration:** Measures bracket compression and IRMAA impact post-first-death.


* **Exact Engine Validation:** Stochastic runs utilize high-speed state-contingent approximations. Finalist policies and threshold-sensitive edge cases (e.g., IRMAA cliffs, estate tax boundaries) **must** be re-run through the exact, full deterministic tax and estate engine (`core.py`, `after_tax.py`) for final validation.



### 4.4 Dashboard & Residual Wealth Reporting

* **Residual Wealth (P5/P50/P90):** Ending wealth percentiles are explicitly labeled **Residual Wealth**, representing unconsumed surplus rather than an active liquidity reserve.


* **Ranking-Robustness Matrix:** Displays policy rank across varying discount rates (e.g., 2%, 4%, 6%), risk aversion levels, and tax regime shifts.


* **Threshold-Crossing Analysis:** Identifies precise asset or income levels where estate tax, IRMAA, or ACA subsidy cliff crossings occur.



---

## 5. Revised Implementation Roadmap

```
Phase 0: Spending & Contingent Taxonomy
   │
   ▼
Phase 1: Stochastic Path Engine (Spending, Cash Flow, First Death)
   │
   ▼
Phase 2: Tiered Cut Logic, Failure Metrics & Residual Reporting
   │
   ▼
Phase 3: Tax Diagnostics & State-Contingent Approximations
   │
   ▼
Phase 4: Adaptive Policy Engine (Guardrails & Dynamic Rules)
   │
   ▼
Phase 5: Policy Feasibility, LCV Scoring & Robustness Testing
   │
   ▼
Phase 6: Stress Scenarios & Threshold-Crossing Analysis

```

### Phase 0 — Spending & Contingent Taxonomy

Classify expenses into explicit buckets in `spending_budget_resolver.py`:

* `essential`: Core housing, utilities, basic food, medical baseline, required taxes.


* `important`: Travel, dining, leisure, discretionary gifting.


* `contingent`: Long-term care events, acute medical shocks, capital home repairs.



### Phase 1 — Dynamic Path Engine Upgrade

Enhance vectorized and scalar Monte Carlo engines to track path-level real spending (`spend_essential_real`, etc.), gross cash flow, and exact first-death transition timing (`first_death_years = np.minimum(h, w)`). Apply survivor tax status, income reductions, and adjusted spending tiers dynamically post-first-death.

### Phase 2 — Tiered Execution, Shortfall Tracking & Dashboard

Re-engineer withdrawal logic to enforce spending reductions in priority order: `contingent` $\rightarrow$ `important` $\rightarrow$ `essential`. Compute joint liquidity/spending failures, cumulative shortfall dollars, and consecutive cut durations. Re-label terminal wealth metrics as **Residual Wealth**.

### Phase 3 — Tax Diagnostics & Approximations

Build state-contingent tax approximations into Monte Carlo paths (tracking filing status, coarse tax brackets, RMDs, and IRMAA thresholds). Compute Tax NPV and ELTR diagnostics.

### Phase 4 — Adaptive Policy Implementation (Moved Ahead of Ranking)

Embed dynamic guardrails directly inside Monte Carlo recursions:

* Portfolio-value and withdrawal-rate bands driving automatic tier reductions or restorations.


* Dynamic Roth conversion rules conditioned on bracket availability, IRMAA thresholds, and taxable liquidity.


* Rules must operate dynamically per path before policy scoring occurs.



### Phase 5 — Feasibility Gate, LCV Reconciliation & Robustness Engine

Build the `score_feasible_policy` module:

1. Filter out candidate policies failing hard joint liquidity, essential shortfall, or duration limits.


2. Apply double-counting controls to isolate after-tax consumption and net beneficiary transfers.


3. Run ranking-robustness matrices across varied risk aversion parameters, discount rates, and tax regimes.


4. Run top candidate policies through full exact tax/estate engine validation.



### Phase 6 — Stress Scenarios & Threshold-Crossing Analysis

Execute sequence-of-returns shock, prolonged LTC event, tax law expiration, and estate exemption sunset scenarios via `run_scenario()`. Map threshold-crossing boundaries for estate tax and income-based surcharges.

---

## 6. What Not to Do

| Deferred / Excluded Item | Rationale |
| --- | --- |
| **Exact tax engine on all MC paths** | Computationally prohibitive; state-contingent approximation handles path search, exact engine validates finalists.

 |
| **Using Tax NPV as an optimizer target** | Minimizing tax NPV can suppress lifetime consumption quality; keep tax NPV strictly diagnostic.

 |
| **Ranking static cash-flow plans** | Static plans fail to reflect real-world adaptations; evaluate complete adaptive policies instead.

 |
| **P5 wealth as an active reserve** | Residual wealth at death cannot cushion mid-plan liquidity shocks; treat liquidity floors separately.

 |

---

## 7. Testing, Reconciliation, & Governance Controls

* **Golden Master Protection:** Freeze live pricing (`RETIREMENT_SYSTEM_DISABLE_LIVE_PRICE_PROVIDERS=1`) and audit `input/` before test execution.


* **Dual-Engine Synchronization:** Ensure all spending, dynamic guardrail, and survivor updates are mirrored identically across both scalar (`monte_carlo_exact_scalar`) and vectorized engines.


* **Accounting Reconciliation Audit:** Implement automated checks asserting that $\text{Total Assets}_{t} + \text{Inflows}_t - \text{Outflows}_t - \text{Taxes}_t = \text{Total Assets}_{t+1}$ and verifying zero double-counting between consumption and transfer LCV terms.


* **Robustness Sign-Off:** Require that the winning policy maintains top-tier ranking across at least 80% of parameter sensitivity variations.



---

## 8. Final Decision Rule

The framework should select the optimal policy based on the following standard:

> Select the simplest adaptive policy whose risk-adjusted LCV advantage remains robust across varying risk preferences, discount rates, and tax regimes, while guaranteeing essential spending protection, maintaining joint liquidity bounds, and satisfying the household's transfer objectives.
> 
> 

Terminal wealth is reported as **Residual Wealth**. Tax NPV and ELTR serve as diagnostic explanations. Mathematical score maximization under a single set of static assumptions is explicitly rejected in favor of **demonstrated policy robustness**.