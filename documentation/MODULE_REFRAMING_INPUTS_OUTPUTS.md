# Module Reframing: Inputs and Outputs

Status: proposal / planning document. No code changes. This reframes the
existing module catalog (workbook sheets + optional-function toggles) around a
single organizing idea: **the system is a set of Inputs that feed a set of
selectable Outputs, and selecting an Output pulls in exactly the Inputs (and
sometimes other Outputs) it needs.**

Grounded in the current code:

- Optional-module registry: `src/reporting/workbook_common.py`
  (`OPTIONAL_MODULE_SHEETS`, `module_enabled`, `WORKBOOK_SECTION_LAYOUT`).
- Toggle source of truth: `input/client_optional_functions.csv`.
- Nav/UI gating: `frontend/js/dashboard.js` (`optionalFunctionEnabled`).
- Input catalog: `input/client_*.csv`, `reference_data/*`, and the projection
  stage contract in `src/projection_pipeline.py`.

---

## 1. The two top-level categories

### Inputs (always present; some are conditionally required)

Inputs are the plan's facts and assumptions. They never produce a
recommendation on their own; they exist to be consumed. Every Output declares
which Input modules — and which specific elements inside them — it requires.

| Input module | Backing file(s) | Representative elements |
|---|---|---|
| Household & timing | `client_household.csv` | member names/DOBs, retirement ages, survivor state, economic assumptions, SS policy |
| Income | `client_income.csv` | earned income, self-employment, pension/annuity streams, contribution rates |
| Spending | `client_spending.csv`, `client_spending_budget_lines.csv`, `spending_*` | base spending, housing/mortgage, travel, large discretionary, category tree |
| Assets & liquidity | `client_assets.csv` | home, cash reserves, HSA/DAF, liquidity buffers, special assets |
| Liabilities | `client_liabilities.csv` | mortgages, auto, HELOC, student loans (amortized into cash flow) |
| Holdings & lots | `client_holdings.csv`, `security_master.csv` | per-account lots (symbol/shares/basis), tax-aware cost basis |
| Allocation policy | `target_allocation.csv`, `asset_class_optimizer_controls.csv` | target mix, include/exclude/alternate, drift/location controls |
| Strategy controls | `client_policy.csv` | withdrawal sequencing, Roth policy, forced conversions, scenario/MC settings |
| Insurance & estate | `client_insurance_estate.csv` | life/DI/LTC policies, annuity death benefits, estate inputs, 529, equity comp |
| Business | `client_business.csv` | entity valuation, buy-sell funding, key-person coverage |
| Assumptions (economic/tax) | `reference_data/*`, `tax_law_v10.json` | CMAs, correlations, state tax, tax constants, IRMAA brackets |
| Market pricing | live/cached providers, `security_master.csv` | quotes used to value holdings at plan start |
| YTD actuals | `ytd_transactions.csv`, `ytd_account_setup.csv` | current-year imports for reconciliation |
| Module toggles | `client_optional_functions.csv` | which Outputs are switched on |

### Outputs (the optional modules)

Every Output is an optional module that, when selected, produces exactly one
**kind** of result. The four kinds you proposed hold up well against the
catalog:

1. **Projection** — carries the base plan forward in time (net worth, cash
   flow, lifetime taxes, balance sheet, spending).
2. **Optimization** — recommends a better setting for one decision lever (Roth
   conversion, SS timing, allocation/location, residency, charitable, entity).
3. **Stress test** — evaluates resilience under an adverse or probabilistic
   event (Monte Carlo, survivor, LTC, disability, P&C).
4. **Diagnostics** — validates the model's own integrity (QC, RMD audit,
   reconciliation).

---

## 2. Am I missing a category? Yes — add a 5th, and consider a 6th.

### Recommended 5th category: **Reference / Documentation**

Several existing output sheets carry **no new computation**. They echo inputs
or explain the model so the plan is auditable and self-explaining:

- `4B. Assumptions` (echoes economic/tax inputs)
- `4A. Plan Data` (snapshot of the inputs)
- `4F. Methodology` + re-run instructions (`methodology_rerun`)
- `4G. Glossary` (`glossary`)

These do not fit Projection / Optimization / Stress / Diagnostics: they neither
project, nor recommend, nor test, nor validate — they **restate and explain**.
They are the natural home for anything that is "output for the reader, not for
the math." Recommend making **Reference / Documentation** a first-class 5th
output kind. It also cleanly absorbs future narrative/export artifacts (cover
letter, advisor summary memo) without distorting the other four.

### Candidate 6th category: **Comparison / Scenario (What-If)**

`what_if_analysis` (`16. Scenario Analysis`) is doing something the other four
don't: it runs the **whole plan under alternative configurations side by side**
and reports the deltas. That is neither a single-lever optimization nor a
single-shock stress test — it is a *meta-output* that consumes a base
Projection and re-runs it. Two defensible choices:

- **Fold it into Stress test** (a stress test is "re-run under a changed world";
  what-if is "re-run under changed assumptions"). Simplest.
- **Promote it to its own "Comparison / Scenario" kind.** Cleaner if you expect
  to add plan-vs-plan, before/after-lever, or multi-client comparison views —
  all of which share the "diff two full runs" machinery.

Recommendation: keep it as its own **Comparison / Scenario** kind *if* you plan
to grow scenario tooling; otherwise fold under Stress test. I would not add any
category beyond these six — everything in the current catalog maps cleanly into
Projection, Optimization, Stress test, Diagnostics, Reference, and Comparison.

### Categories considered and rejected

- *Protection / Insurance* as its own kind — tempting (life, DI, LTC, P&C,
  umbrella), but these all answer a resilience question ("does the plan survive
  this event / is coverage adequate?"), so they belong under **Stress test**.
  Keeping them there avoids a taxonomy where the same module could sit in two
  places.
- *Planning / Design* (estate, special-needs, business succession) as its own
  kind — these recommend a structure/lever setting, so they are
  **Optimization**. A "Planning" bucket would just be Optimization by another
  name.

---

## 3. Selection semantics: outputs pull in requirements

The reframing's core rule:

> Selecting an Output activates its **required Inputs** (module + specific
> elements) and any **prerequisite Outputs**. A required Input that is missing
> becomes a prompted gap; a prerequisite Output is auto-selected (or the toggle
> is blocked until it is on).

This already exists in fragments in the code and should be made explicit and
uniform:

- `module_enabled(c, key)` gates computation and sheet creation.
- `dashboard.js` hides input pages until their owning module is enabled (e.g.
  LTC inputs hidden unless `long_term_care_stress` is on; DAF rows hidden unless
  `charitable_giving`; equity-comp rows unless `equity_compensation`).
- Empty section dividers are pruned when all child outputs are off
  (`test_optional_module_gating.py`).

**Output → Output dependencies observed in the catalog** (make these first-class):

- Every Optimization / Stress / Comparison output requires the base
  **Projection** (net worth + cash flow) to exist first — it is the substrate
  they re-run or read.
- **Life Insurance Need** ↔ **Survivor stress**: the survivor re-run sizes the
  need; the need analysis reads the survivor shortfall.
- **What-If / Scenario** requires a completed base Projection to diff against.
- **RMD Audit** and **QC** read the projection's tax/RMD ledger.
- **Tax-Loss Harvesting** and **Asset Location** require **Holdings & lots**
  (not just balances) — an input-depth requirement, not just an input-module
  requirement.

---

## 4. Recommendation table

Legend for **Likely usage** (high demand → obscure, 5 bands):
🟢 High · 🟩 Medium-High · 🟡 Medium · 🟠 Low · ⚪ Niche/Obscure

### 4.1 Projection outputs

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Net Worth (`1B`, core) | Year-by-year total net worth; the plan's headline trajectory. | Household → ages/timing; Assets, Liabilities, Holdings → balances; Assumptions → growth/CMAs | 🟢 High |
| Cash Flow (`1C`, core) | Annual inflows/outflows, funding gaps, withdrawal need. | Income → all streams; Spending → all; Liabilities → payments; Household → SS/timing | 🟢 High |
| Balance Sheet (`1D`, core) | Point-in-time assets/liabilities by account & tax type. | Assets, Liabilities, Holdings | 🟢 High |
| Executive Summary (`1A`, core) | One-page KPI roll-up of the whole plan. | Consumes all Projection outputs | 🟢 High |
| Lifetime Taxes (`1F`, `lifetime_tax_projection`) | Cumulative federal/state/NIIT/IRMAA/payroll/cap-gains over the plan. | Income, Spending, Holdings; Assumptions → tax constants/`tax_law_v10.json` | 🟢 High |
| Core Spending (`1G`) / Spending Summary (`1H`) | Recurring spend detail and category roll-up feeding cash flow. | Spending → categories, housing, travel, discretionary; YTD (optional) | 🟩 Medium-High |
| Charts (`1E`, `charts_dashboard`) | Visual consolidation of the projection series. | Consumes Net Worth, Cash Flow, Allocation | 🟩 Medium-High |

### 4.2 Optimization outputs

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Roth Conversion (`2A`, `roth_conversion_plan`) | Recommends conversion amounts/bracket-fill; quantifies lifetime tax savings. | Strategy → Roth policy/forced conversions; Income; Assumptions → brackets/IRMAA; base Projection | 🟢 High |
| Asset Allocation (`2B`, core) | Target vs actual mix, drift, rebalancing guidance. | Allocation policy → targets/controls; Holdings; Assumptions → CMAs | 🟢 High |
| Social Security (`2D`, `social_security_timing`) | Optimal claiming age; lifetime-benefit comparison. | Household → SS policy/DOBs/earnings; base Projection | 🟢 High |
| Retirement Strategy / Sequencing (`9`→core, `retirement_strategy`) | Withdrawal order across account tax types. | Strategy → sequencing; Assets, Holdings; base Projection | 🟩 Medium-High |
| Asset Location (`24`→`2B` family, core) | Which assets to hold in which tax bucket. | Holdings → lots; Allocation policy; Assumptions → tax rates | 🟩 Medium-High |
| Tax-Loss Harvesting (`2I`, core) | Harvestable losses given current lots. | **Holdings → lots/basis** (depth required); Market pricing | 🟡 Medium |
| Charitable Giving (`2F`, `charitable_giving`) | Bunching/QCD/DAF strategy and tax effect. | Assets → DAF; Income; Household → age (QCD); Assumptions → brackets | 🟡 Medium |
| State Residency (`2C`, `state_residency`) | Tax impact of relocating. | Household → state; Income; Assumptions → `state_tax.csv` | 🟡 Medium |
| Estate & Legacy (`2G`, `estate_legacy_plan`) | Estate-tax exposure, legacy/bequest design. | Insurance & estate → estate inputs; Assets; Assumptions → estate constants | 🟡 Medium |
| Planning Levers (`2H`, core) | Central hub of adjustable strategy knobs. | Strategy controls (all) | 🟡 Medium |
| Education Funding 529 (`2J`, `education_funding_529`, default off) | 529 sizing vs education goals. | Insurance & estate → 529 accounts/goals; Assumptions → growth | 🟠 Low |
| Equity Compensation (`2K`, `equity_compensation`, default off) | RSU/ISO/NSO/ESPP tax & timing. | Insurance & estate → equity-comp grants; Assumptions → tax | 🟠 Low |
| S-Corp vs LLC (`2E`, core) | Entity-structure tax comparison for self-employed. | Income → self-employment; Business; Assumptions → tax | 🟠 Low |
| Business Succession (`2M`, `business_succession`, default off) | Buy-sell/key-person/valuation planning. | Business → entity/valuation/funding | 🟠 Low |
| Special-Needs Planning (`2L`, `special_needs_planning`, default off) | SNT/ABLE structure for a dependent. | Household → dependents; Insurance & estate | ⚪ Niche |

### 4.3 Stress-test outputs

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Monte Carlo (`3A`, `market_luck_stress_test`) | Probability of success across market-return paths. | base Projection; Assumptions → CMAs/correlations; Strategy → MC settings | 🟢 High |
| Survivor / Early Death (`3B`, `survivor_stress_test`) | Plan solvency after one spouse's early death. | Household → survivor state; Income → survivor continuation; Insurance | 🟡 Medium |
| LTC Stress (`3C`, `long_term_care_stress`) | Impact of a long-term-care event. | Insurance & estate → LTC policy; Assets → liquidity; Assumptions → LTC cost | 🟡 Medium |
| Life Insurance Need (`3C`, `life_insurance_need`) | Coverage gap vs survivor shortfall. | **Requires Survivor stress**; Insurance → policies; Income | 🟡 Medium |
| Existing Life Insurance (`3D`, `existing_life_insurance`, default off) | Inventory/adequacy of in-force policies. | Insurance & estate → life policies | 🟠 Low |
| Disability Income (`3E`, `disability_income_insurance`, default off) | DI coverage vs income-replacement need. | Insurance & estate → DI policies; Income | 🟠 Low |
| P&C / Umbrella (`3F`, `property_casualty_umbrella`, default off) | Liability-coverage adequacy vs net worth. | Insurance & estate → P&C policies; Net Worth projection | ⚪ Niche |
| Divorce / QDRO (`divorce_qdro`, default off, no sheet yet) | Divorce-specific asset-split modeling. | Household → divorce assumptions; Assets; Holdings | ⚪ Niche |

### 4.4 Diagnostics outputs

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Quality Control (`4D`, core) | Pass/fail checks on the projection's internal consistency. | Consumes all Projection outputs + QC ledger | 🟡 Medium |
| RMD Audit (`4E`, `rmd_audit`) | Verifies RMD amounts/timing against tax rules. | base Projection → RMD ledger; Household → ages; Assumptions → RMD tables | 🟡 Medium |
| Account Reconciliation (`4C`, core) | Reconciles modeled balances against YTD actuals. | Holdings; YTD actuals → transactions/setup | 🟡 Medium |

### 4.5 Reference / Documentation outputs (proposed 5th kind)

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| Assumptions (`4B`, core) | Echoes the economic/tax assumptions used, for auditability. | Assumptions (all) | 🟡 Medium |
| Plan Data (`4A`, core) | Snapshot of all inputs behind the run. | All input modules | 🟡 Medium |
| Methodology & Re-Run (`4F`, `methodology_rerun`) | Explains the model and how to reproduce the run. | none (narrative) | 🟠 Low |
| Glossary (`4G`, `glossary`) | Defines terms used across the workbook. | none (static) | 🟠 Low |

### 4.6 Comparison / Scenario output (candidate 6th kind)

| Output (module) | Description & value | Required inputs (modules → specific elements) | Likely usage |
|---|---|---|---|
| What-If / Scenario Analysis (`16`/`H`, `what_if_analysis`) | Side-by-side of alternative full-plan configurations with deltas. | **Requires base Projection**; Strategy → scenario definitions | 🟩 Medium-High |

---

## 5. What this reframing buys us

- **One selection model.** The UI becomes "pick your Outputs"; the system then
  reveals only the Input pages those Outputs require, and pulls in prerequisite
  Outputs automatically. This generalizes the ad-hoc `optionalFunctionEnabled`
  hides already scattered through `dashboard.js`.
- **A dependency graph instead of a flat toggle list.** `OPTIONAL_MODULE_SHEETS`
  becomes a richer registry: each entry declares `kind`
  (projection/optimization/stress/diagnostics/reference/comparison),
  `requires_inputs` (module + elements), and `requires_outputs`.
- **Cleaner gating and pruning.** Section dividers, nav entries, and input pages
  all derive from the same requirement graph rather than being maintained in
  three places.
- **Demand-ordered surfacing.** The Likely-usage band gives a natural default
  ordering: lead with 🟢/🟩 outputs, tuck ⚪ ones behind an "advanced" reveal.

## 6. Suggested next steps (not done here)

1. Add `kind`, `requires_inputs`, `requires_outputs`, and `demand` fields to the
   `OPTIONAL_MODULE_SHEETS` registry (or a sibling registry), keeping the sheet
   mapping intact.
2. Decide the 6th-category question: promote **Comparison / Scenario** or fold
   What-If into Stress test.
3. Drive `dashboard.js` input-page visibility from `requires_inputs` instead of
   per-module hand-written guards.
4. Auto-select prerequisite Outputs (e.g. enabling Life Insurance Need enables
   Survivor stress) instead of relying on the user to enable both.
