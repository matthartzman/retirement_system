# Module Reframing: Inputs and Outputs

Status: proposal / planning document. No code changes. This reframes the
existing module catalog (workbook sheets + optional-function toggles) around a
single organizing idea: **the system is a set of Inputs that feed a set of
selectable Outputs, and selecting an Output pulls in exactly the Inputs (and
sometimes other Outputs) it needs.**

> **v2 note.** This revision tightens the category definitions around *the
> question each output answers*, introduces the **controllable-vs-exogenous**
> axis that separates Optimization from Stress test, resolves the
> Planning-Levers-vs-Scenarios overlap, and re-checks every assignment against
> the tighter rules. The net change: **five categories, not six** — "Comparison
> / Scenario" is demoted from a category to a *presentation mode*.

Grounded in the current code:

- Optional-module registry: `src/reporting/workbook_common.py`
  (`OPTIONAL_MODULE_SHEETS`, `module_enabled`, `WORKBOOK_SECTION_LAYOUT`).
- Toggle source of truth: `input/client_optional_functions.csv`.
- Nav/UI gating: `frontend/js/dashboard.js` (`optionalFunctionEnabled`).
- Planning Workbench steps: `planning_levers`, `scenarios`,
  `monte_carlo_options`, `build_impact` (see `test_127`).
- Input catalog: `input/client_*.csv`, `reference_data/*`, and the projection
  stage contract in `src/projection_pipeline.py`.

---

## 1. The two top-level categories

### Inputs (always present; some are conditionally required)

Inputs are the plan's facts, assumptions, and **the levers the household
controls**. They never produce a recommendation on their own; they exist to be
consumed. Every Output declares which Input modules — and which specific
elements inside them — it requires.

| Input module | Backing file(s) | Representative elements |
|---|---|---|
| Household & timing | `client_household.csv` | member names/DOBs, retirement ages, survivor state, economic assumptions, SS policy |
| Income | `client_income.csv` | earned income, self-employment, pension/annuity streams, contribution rates |
| Spending | `client_spending.csv`, `client_spending_budget_lines.csv`, `spending_*` | base spending, housing/mortgage, travel, large discretionary, category tree |
| Assets & liquidity | `client_assets.csv` | home, cash reserves, HSA/DAF, liquidity buffers, special assets |
| Liabilities | `client_liabilities.csv` | mortgages, auto, HELOC, student loans (amortized into cash flow) |
| Holdings & lots | `client_holdings.csv`, `security_master.csv` | per-account lots (symbol/shares/basis), tax-aware cost basis |
| **Planning Levers** (control surface) | `client_policy.csv`, `target_allocation.csv`, `asset_class_optimizer_controls.csv` | Roth policy, withdrawal sequencing, allocation targets, SS claiming age, residency choice, giving strategy, forced conversions |
| Insurance & estate | `client_insurance_estate.csv` | life/DI/LTC policies, annuity death benefits, estate inputs, 529, equity comp |
| Business | `client_business.csv` | entity valuation, buy-sell funding, key-person coverage |
| Assumptions (economic/tax) | `reference_data/*`, `tax_law_v10.json` | CMAs, correlations, state tax, tax constants, IRMAA brackets |
| Market pricing | live/cached providers, `security_master.csv` | quotes used to value holdings at plan start |
| YTD actuals | `ytd_transactions.csv`, `ytd_account_setup.csv` | current-year imports for reconciliation |
| Module toggles | `client_optional_functions.csv` | which Outputs are switched on |

> **Planning Levers is an Input, not an Output** (this is the resolution of the
> "levers vs scenarios" overlap — see §3). It is the *control surface* where the
> household sets the dials. Its workbook sheet (`2H`) is a **Reference echo** of
> the chosen dial positions (with a "source" column showing where each came
> from), not a computation.

### Outputs (the optional modules)

Every Output is an optional module that, when selected, produces exactly one
**kind** of result — defined below by *the question it answers*.

---

## 2. The five output categories (tightened definitions)

Each category is defined by the single **question** its outputs answer. The one
that used to be fuzzy — Optimization vs Stress — is now separated by a crisp
axis:

> **Optimization changes a variable the household *controls* (a lever).
> Stress test changes a variable *outside* their control (a risk).**

| # | Category | The question it answers | What changes between runs | Output shape |
|---|---|---|---|---|
| 1 | **Projection** | "Given the plan as-is, what happens over time?" | Nothing — one deterministic baseline | Time series / point-in-time statements |
| 2 | **Optimization** (Decision analysis) | "What should I *change*, and by how much is it worth?" | A **controllable lever** (or a bundle of them) | Recommended setting + quantified delta |
| 3 | **Stress test** | "Does the plan survive events *outside* my control?" | An **exogenous risk/event** | Survival probability / shortfall / gap |
| 4 | **Diagnostics** | "Is the *model itself* trustworthy?" | Nothing — inspects the run | Pass/fail, audit, reconciliation |
| 5 | **Reference / Documentation** | "What inputs and methods produced this?" | Nothing — restates | Echoed inputs / narrative, no computation |

Sub-groupings that are **modes or flavors, not new categories**:

- **Comparison / Scenario ("What-If")** is a *presentation mode* of
  Optimization: run the plan under several lever bundles and show them side by
  side. An Optimizer is the same thing with the solver picking the bundle. (See
  §3 — this is why there is no 6th category.)
- **Protection planning** (life/DI/P&C coverage adequacy) is a *flavor* of
  Optimization — the decision is "how much coverage to buy" — that takes a
  **Stress** output as a required input.

### Was I missing a category? Yes — one, and it is Reference.

The v1 four (Projection, Optimization, Stress, Diagnostics) left four existing
sheets homeless: `4B Assumptions`, `4A Plan Data`, `4F Methodology`, `4G
Glossary`. They **carry no computation** — they restate inputs or explain the
model. **Reference / Documentation** is the necessary 5th category and the
natural home for future narrative artifacts (cover letter, advisor memo).

### Categories considered and rejected (with the tightened rules)

- **Comparison / Scenario** as its own category — *rejected.* It is a way of
  *presenting* Optimization runs, not a distinct question. Promoting it created
  the Levers/Scenarios confusion in the first place.
- **Protection / Insurance** as its own category — *rejected.* It splits cleanly
  under the controllable/exogenous axis: the *event models* (LTC, survivor) are
  Stress; the *coverage decisions* (how much to buy) are Optimization. A
  separate bucket would force each module into two homes.
- **Planning / Design** (estate, special-needs, succession) — *rejected.* These
  recommend a controllable structure → Optimization.

No sixth category is warranted: every catalog item maps to exactly one of the
five.

---

## 3. Planning Levers vs Scenarios — resolved

The two felt redundant. They are not the same kind of object:

| | **Planning Levers** | **Scenarios (What-If)** |
|---|---|---|
| What it is | The individual **dials** (Roth policy, withdrawal order, allocation, SS age, residency, giving) | A **named bundle** of specific dial positions |
| Where it lives | An **Input** control surface (`planning_levers` step; `2H` sheet echoes settings) | A **comparison run** of the whole plan under that bundle (`scenarios` step; `16` sheet) |
| Role in the model | *Sets* the values the engine consumes | *Re-runs* the engine with an alternative set and **diffs** it |
| Category | Input (sheet = Reference echo) | A **mode of Optimization**, not its own category |

**A scenario is just "a saved set of lever positions + a re-run."** So:

- **Distinction (if kept):** Levers = the atomic controls you set; Scenarios =
  bundles of those controls run and compared. Clear once you stop treating
  Scenarios as a peer category.
- **Recommendation:** **do not build free-form scenario authoring as a headline
  feature.** The structured **Optimizers** already answer "best position for
  lever X," and the **Stress tests** already answer "what if the world turns
  bad." What remains for hand-built scenarios is a narrow "compare these 2–3
  saved lever bundles" view — keep that as a *comparison mode* on top of the
  Optimization machinery, not as a separate module or category. This directly
  addresses the concern that scenarios are "too complex and not needed": most of
  their value is already delivered by optimizers + stress tests.

---

## 4. Selection semantics: outputs pull in requirements

The reframing's core rule:

> Selecting an Output activates its **required Inputs** (module + specific
> elements) and any **prerequisite Outputs**. A required Input that is missing
> becomes a prompted gap; a prerequisite Output is auto-selected (or the toggle
> is blocked until it is on).

This already exists in fragments and should be made explicit and uniform:

- `module_enabled(c, key)` gates computation and sheet creation.
- `dashboard.js` hides input pages until their owning module is enabled (LTC
  inputs hidden unless `long_term_care_stress`; DAF rows unless
  `charitable_giving`; equity-comp rows unless `equity_compensation`).
- Empty section dividers are pruned when all child outputs are off
  (`test_optional_module_gating.py`).

**Output → Output dependencies to make first-class:**

- Every Optimization and Stress output requires the base **Projection** (net
  worth + cash flow) — the substrate they re-run or read.
- **Protection decisions require a Stress result:** Life Insurance Need, Existing
  Life Insurance, Disability Income, and P&C/Umbrella each read a survivor /
  income-loss / liability stress to size the coverage gap.
- **What-If / comparison mode** requires a completed base Projection to diff
  against.
- **RMD Audit** and **QC** read the projection's tax/RMD ledger.
- **Tax-Loss Harvesting** and **Asset Location** require **Holdings & lots**
  (basis depth), not just balances.

---

## 5. Recommendation table (assignments re-checked against §2)

Legend for **Likely usage** (high demand → obscure, 5 bands):
🟢 High · 🟩 Medium-High · 🟡 Medium · 🟠 Low · ⚪ Niche/Obscure

Assignments that **moved in v2** are flagged **(moved)** with the reason.

### 5.1 Projection — "what happens as-is?"

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Net Worth (`1B`, core) | Year-by-year total net worth; headline trajectory. | Household → ages/timing; Assets, Liabilities, Holdings → balances; Assumptions → growth/CMAs | 🟢 High |
| Cash Flow (`1C`, core) | Annual inflows/outflows, funding gaps, withdrawal need. | Income → all streams; Spending → all; Liabilities → payments; Household → SS/timing | 🟢 High |
| Balance Sheet (`1D`, core) | Point-in-time assets/liabilities by account & tax type. | Assets, Liabilities, Holdings | 🟢 High |
| Executive Summary (`1A`, core) | One-page KPI roll-up. | Consumes all Projection outputs | 🟢 High |
| Lifetime Taxes (`1F`, `lifetime_tax_projection`) | Cumulative federal/state/NIIT/IRMAA/payroll/cap-gains. | Income, Spending, Holdings; Assumptions → `tax_law_v10.json` | 🟢 High |
| Core Spending / Spending Summary (`1G`/`1H`) | Recurring-spend detail and roll-up feeding cash flow. | Spending → categories, housing, travel, discretionary; YTD (optional) | 🟩 Medium-High |
| Charts (`1E`, `charts_dashboard`) | Visual consolidation of the projection series. | Consumes Net Worth, Cash Flow, Allocation | 🟩 Medium-High |

### 5.2 Optimization — "what controllable lever should I change, and by how much?"

*Decision levers:*

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Roth Conversion (`2A`, `roth_conversion_plan`) | Conversion amounts/bracket-fill; lifetime tax savings. | Planning Levers → Roth policy/forced conversions; Income; Assumptions → brackets/IRMAA; base Projection | 🟢 High |
| Asset Allocation (`2B`, core) | Target vs actual mix, drift, rebalancing guidance. | Planning Levers → targets/controls; Holdings; Assumptions → CMAs | 🟢 High |
| Social Security (`2D`, `social_security_timing`) | Optimal claiming age; lifetime-benefit comparison. | Household → SS policy/DOBs/earnings; Planning Levers → claiming age; base Projection | 🟢 High |
| Withdrawal Sequencing (`retirement_strategy`) | Draw order across account tax types. | Planning Levers → sequencing; Assets, Holdings; base Projection | 🟩 Medium-High |
| Asset Location (`24`→`2B` family, core) | Which assets to hold in which tax bucket. | Holdings → lots; Planning Levers → location policy; Assumptions → tax rates | 🟩 Medium-High |
| What-If / Scenario **(comparison mode)** (`what_if_analysis`) | Side-by-side of 2–3 saved lever bundles with deltas. | **base Projection**; Planning Levers → bundled positions | 🟩 Medium-High |
| Tax-Loss Harvesting (`2I`, core) | Harvestable losses given current lots. | **Holdings → lots/basis** (depth); Market pricing | 🟡 Medium |
| Charitable Giving (`2F`, `charitable_giving`) | Bunching/QCD/DAF strategy and tax effect. | Assets → DAF; Income; Household → age (QCD); Assumptions → brackets | 🟡 Medium |
| State Residency (`2C`, `state_residency`) | Tax impact of relocating. | Planning Levers → residency choice; Income; Assumptions → `state_tax.csv` | 🟡 Medium |
| Estate & Legacy (`2G`, `estate_legacy_plan`) | Estate-tax exposure and legacy/bequest structure. | Insurance & estate → estate inputs; Assets; Assumptions → estate constants | 🟡 Medium |
| Education Funding 529 (`2J`, `education_funding_529`) | 529 sizing vs education goals. | Insurance & estate → 529 accounts/goals; Assumptions → growth | 🟠 Low |
| Equity Compensation (`2K`, `equity_compensation`) | RSU/ISO/NSO/ESPP tax & timing. | Insurance & estate → grants; Assumptions → tax | 🟠 Low |
| S-Corp vs LLC (`2E`, core) | Entity-structure tax comparison. | Income → self-employment; Business; Assumptions → tax | 🟠 Low |
| Business Succession (`2M`, `business_succession`) | Buy-sell/key-person/valuation planning. | Business → entity/valuation/funding | 🟠 Low |
| Special-Needs Planning (`2L`, `special_needs_planning`) | SNT/ABLE structure for a dependent. | Household → dependents; Insurance & estate | ⚪ Niche |

*Protection decisions (Optimization flavor; each requires a Stress result):*

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Life Insurance Need **(moved: Stress→Opt)** (`life_insurance_need`) | Coverage to buy vs survivor shortfall. Answers "how much to buy" → a decision. | **Requires Survivor stress**; Insurance → policies; Income | 🟡 Medium |
| Existing Life Insurance **(moved)** (`existing_life_insurance`) | Adequacy of in-force policies. | **Requires Survivor stress**; Insurance & estate → life policies | 🟠 Low |
| Disability Income **(moved)** (`disability_income_insurance`) | DI coverage vs income-replacement need. | **Requires income-loss stress**; Insurance → DI policies; Income | 🟠 Low |
| P&C / Umbrella **(moved)** (`property_casualty_umbrella`) | Liability coverage adequacy vs net worth. | **Requires Net Worth projection**; Insurance → P&C policies | ⚪ Niche |

### 5.3 Stress test — "does the plan survive exogenous events?"

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Monte Carlo (`3A`, `market_luck_stress_test`) | Probability of success across market-return paths. | base Projection; Assumptions → CMAs/correlations; Planning Levers → MC settings | 🟢 High |
| Survivor / Early Death (`3B`, `survivor_stress_test`) | Solvency after one spouse's early death. | Household → survivor state; Income → survivor continuation; Insurance | 🟡 Medium |
| LTC Stress (`3C`, `long_term_care_stress`) | Impact of a long-term-care event. | Insurance & estate → LTC policy; Assets → liquidity; Assumptions → LTC cost | 🟡 Medium |
| Divorce / QDRO (`divorce_qdro`, default off) | Plan under an imposed asset split (exogenous life event). | Household → divorce assumptions; Assets; Holdings | ⚪ Niche |

### 5.4 Diagnostics — "is the model trustworthy?"

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Quality Control (`4D`, core) | Pass/fail checks on internal consistency. | Consumes all Projection outputs + QC ledger | 🟡 Medium |
| RMD Audit (`4E`, `rmd_audit`) | Verifies RMD amounts/timing vs tax rules. | base Projection → RMD ledger; Household → ages; Assumptions → RMD tables | 🟡 Medium |
| Account Reconciliation (`4C`, core) | Reconciles modeled balances vs YTD actuals. | Holdings; YTD actuals → transactions/setup | 🟡 Medium |

### 5.5 Reference / Documentation — "what inputs and methods produced this?"

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Planning Levers echo **(moved: was a peer output)** (`2H`, core) | Restates the chosen dial positions with their source. | Planning Levers (input control surface) | 🟡 Medium |
| Assumptions (`4B`, core) | Echoes economic/tax assumptions used. | Assumptions (all) | 🟡 Medium |
| Plan Data (`4A`, core) | Snapshot of all inputs behind the run. | All input modules | 🟡 Medium |
| Methodology & Re-Run (`4F`, `methodology_rerun`) | Explains the model and how to reproduce. | none (narrative) | 🟠 Low |
| Glossary (`4G`, `glossary`) | Defines terms across the workbook. | none (static) | 🟠 Low |

---

## 6. What this reframing buys us

- **One selection model.** The UI becomes "pick your Outputs"; the system reveals
  only the Input pages those Outputs require and pulls in prerequisite Outputs
  automatically — generalizing the ad-hoc `optionalFunctionEnabled` guards.
- **A crisp taxonomy with one discriminating axis.** Controllable-vs-exogenous
  cleanly separates Optimization from Stress and makes every assignment testable
  rather than a judgment call.
- **Comparison as a mode, not a module.** Removes the Levers/Scenarios confusion
  and lets any output support side-by-side without a category of its own.
- **A dependency graph instead of a flat toggle list.** `OPTIONAL_MODULE_SHEETS`
  becomes a richer registry: each entry declares `kind`
  (projection/optimization/stress/diagnostics/reference), `requires_inputs`
  (module + elements), and `requires_outputs`.
- **Demand-ordered surfacing.** The Likely-usage band gives a default ordering:
  lead with 🟢/🟩 outputs; tuck ⚪ ones behind an "advanced" reveal.

## 7. Suggested next steps (not done here)

1. Add `kind`, `requires_inputs`, `requires_outputs`, and `demand` fields to the
   `OPTIONAL_MODULE_SHEETS` registry (or a sibling), keeping the sheet mapping
   intact.
2. Reclassify the four **protection** modules and the **Planning Levers echo** in
   any UI grouping to match §5 (protection → Optimization w/ Stress prerequisite;
   levers echo → Reference).
3. Reframe What-If as a **comparison mode** on the Optimization machinery rather
   than a standalone module; decide whether free-form scenario authoring is worth
   retaining at all.
4. Drive `dashboard.js` input-page visibility from `requires_inputs` instead of
   per-module hand-written guards.
5. Auto-select prerequisite Outputs (e.g. enabling Life Insurance Need enables
   Survivor stress).
