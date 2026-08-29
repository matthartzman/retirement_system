# Retirement Planning System — Functional Spec

Generated: 2026-08-29. Describes the system as the code currently behaves. This
is not a changelog — it does not describe how the system got here, only what
it does today.

## 1. What the system is

A local desktop application that turns one household's financial facts
(income, spending, assets, liabilities, holdings, insurance, estate plan) into
a year-by-year retirement projection, a set of optimization recommendations
(what to change), a set of stress tests (what could go wrong), and an
advisor-grade report package (Excel workbook, PDF, offline HTML dashboard, and
an in-app results browser). It runs for one household at a time, on the
household's or advisor's own machine, with no server-side multi-tenant
component.

## 2. Personas

- **Household user** — enters household/income/spending/asset facts, sets
  planning levers (Roth policy, withdrawal order, allocation targets, SS
  claiming age), imports actual spending, builds and reviews reports.
- **Advisor / power user** — validates assumptions, tunes advanced strategy
  and optimizer controls, reviews the full workbook and diagnostics sheets,
  uses the admin console to manage system-wide assumptions (tax law, capital
  market assumptions, pricing) across engagements.
- **Developer/maintainer** — extends projection logic, reporting sheets, and
  test coverage (out of scope for this document; see `documentation/CLAUDE.md`).

## 3. Core domain concepts

These are the terms the rest of this document and the product itself use.
Full definitions also live in `src/glossary.py`, which is the canonical
source shown in-app.

- **Plan** — the complete set of household facts plus the levers the
  household controls. One plan is active at a time; it can be saved,
  reloaded, and exported/imported as a portable file set.
- **Withdrawal cascade** — the fixed order the engine draws on accounts to
  cover any year's cash shortfall: RMDs (forced) → HSA (contingent-liability
  draw, then the scheduled window) → pre-tax/IRA (bracket-aware) → taxable/
  trust (with in-year tax-loss harvesting and gain harvesting) → an uncapped
  pre-tax pass once nothing else is left → Roth, last resort. This *is* the
  household's real spending policy; every other "compare withdrawal orders"
  tool is analysis layered on top of it, not a different way the plan
  actually spends.
- **Spending tiers** — every budget line is classified Essential / Important
  / Discretionary / Contingent-Liability, distinguishing spending that would
  genuinely hurt to cut from spending that is flexible. Distinct from, and
  not the same axis as, the account withdrawal cascade above.
- **Planning Levers** — the dials the household actually controls: Roth
  conversion policy, withdrawal sequencing, asset-allocation targets and
  mode, Social Security claiming age, state residency choice, giving
  strategy, forced conversions. Levers are inputs, not results — they are
  restated (never computed) on the workbook's Planning Levers page.
- **LCV (Lifetime Consumption-and-transfer Value)** — the headline scoring
  metric for Roth-conversion recommendations: present value of everything the
  household gets to spend over its lifetime plus the after-tax value
  transferred to heirs at death. Answers "how much did this household
  actually get, in total," not just terminal net worth.
- **Feasibility gate** — a Roth-conversion strategy is only eligible to be
  *recommended* if Monte Carlo shows at least a 95% probability that
  essential spending stays fully funded under it. A strategy can score well
  on LCV and still be excluded from the recommendation if it fails this gate;
  it stays visible for comparison, just not selected.
- **ELTR (effective lifetime tax rate)** — total taxes paid, discounted to
  plan start, divided by total gross cash that passed through the
  household's hands, discounted to plan start. One number answering "what
  share of every dollar did taxes take," reported as a distribution across
  Monte Carlo paths, and as a single whole-lifetime figure for the built
  baseline plan (Executive Summary; Planning Workbench Impact matrix).
- **FCV / EFTR (forward-looking LCV/ELTR)** — the same two figures restricted
  to what's left from today forward: years already elapsed are excluded, and
  present value is taken from today instead of plan start. Answers "from
  here on" for a plan that's partway through its horizon, rather than "over
  the whole plan." Shown on the Executive Summary and in its own
  supplemental Planning Workbench panel, deliberately separate from the
  Impact matrix's whole-lifetime LCV/ELTR — a saved comparison case is
  captured once and never re-run, so a "from today" number attached to it
  would go stale the moment it's reviewed later.
- **Monte Carlo stress test** — runs the plan hundreds to thousands of times
  under randomly sampled market returns, inflation, and (optionally)
  mortality, reporting probability of success, probability essential spending
  stays funded, percentile net-worth/spending bands, tax NPV, and ELTR. Two
  engines exist (see §7): an exact per-path re-run of the real projection
  engine, and a faster vectorized approximation used for large sample counts.
- **Guyton-Klinger guardrail shadow** — a separate, simplified simulation
  showing what the household's spending would have looked like under a
  classic adaptive-withdrawal-rate system (raise/cut spending by fixed
  triggers). Shown for comparison only; it never feeds back into the real
  plan or the withdrawal cascade.
- **Holding-period / real-loss-aware allocation** — buckets today's liquid
  balance by how soon the plan's own withdrawal schedule will spend it (0–2,
  3–5, 6–10, 11–15, 16+ years out), then penalizes holding equities with
  near-term money and holding cash with long-horizon money, based on
  per-asset-class real-loss-probability curves.
- **Tax-loss harvesting (TLH) / 0%-bracket gain harvesting** — TLH sells
  underwater lots to bank a deductible loss (offsets gains, then up to
  $3,000 of ordinary income, carries the rest forward); gain harvesting is
  the mirror move — sell appreciated long-term lots up to the room left in
  the 0% capital-gains bracket, tax-free, to step up basis.
- **Social Security funding-cut assumption** — the baseline projection itself
  assumes Social Security benefits are cut (22% by default) starting in a
  configurable year (2032 default), modeling trust-fund exhaustion as the
  realistic base case rather than an optimistic assumption. A stress
  scenario shows the *optimistic* alternative (no cut).
- **Divorce / QDRO scenario** — an optional, one-time, tax-free split of
  investment account balances at a configured year and percentage, modeling
  the asset-division impact of a divorce (not ongoing alimony/support).
- **Optional modules** — most non-core capabilities (equity compensation,
  DAF/charitable giving, LTC stress, survivor stress, divorce stress, 529
  education funding, business succession, special-needs planning, RMD audit,
  etc.) are switched on a per-plan basis. A disabled module runs no logic at
  all and produces no workbook sheet — it is not merely hidden.

## 4. What the household can do — functional areas

### 4.1 Household, income, and timing
Enter member identity, dates of birth, retirement ages, filing status,
survivor assumptions, and Social Security policy; enter earned income,
self-employment income, pensions/annuities, and Social Security benefits per
person (with a claiming-age calculator using the SSA early/delayed-credit
reduction formula).

### 4.2 Spending
Maintain a category taxonomy (tracking type → group → category, with alias
rules for auto-classifying imported bank transactions) covering core
recurring spend, housing (rent vs. own, mortgage, sale assumptions),
wellness/healthcare premiums (pre-65, Medicare Part B/D/Medigap) and an
out-of-pocket medical cap, travel, and large one-time discretionary items.
Household can enter budget lines with start/end years or one-time years and
CPI or manually-overridden growth.

### 4.3 Assets, holdings, and liabilities
Enter tax-lot-level investment holdings (account, symbol, purchase date,
shares, cost basis, lot type), cash reserves/liquidity buffers, home and
other real assets, HSA and DAF balances, other assets, and auto/HELOC/
student-loan liabilities (amortized into projected cash flow). Refresh
market prices from configured providers with cached snapshots and provider
fallback; view portfolio drift against target allocation.

### 4.4 Protection and estate
Enter life, disability, long-term-care, umbrella, auto, and home insurance
policies; annuity death benefits; estate structure (trusts, gifting, step-up,
special-needs sub-trusts) with federal/state exemption references; business
entity data (valuation, buy-sell funding, key-person coverage) when the
household owns a business.

### 4.5 Strategy (the levers)
- **Roth conversion policy** — choose a conversion strategy (bracket-fill
  target, fixed amount, IRMAA-guardrail-aware, or let the optimizer
  recommend one from ~30 candidates scored by LCV and gated by the 95%
  feasibility threshold).
- **Withdrawal sequencing** — the account draw order is fixed by the
  cascade (§3), but the household can compare named alternative orders
  (current plan, taxable-first, proportional, Roth-first) as a simplified
  side-by-side, and set per-account draw-priority overrides.
- **Asset allocation & location** — choose among five allocation modes
  (household-set target, optimizer risk-budgeted, max-Sharpe, pure tangency,
  holding-period real-loss-aware), with per-asset-class include/exclude/
  "consider alternate first" preferences (e.g., let guaranteed income stand
  in for bonds).
- **State residency** — compare projected tax impact of relocating.
- **Special strategies** — HELOC as a spending backstop, charitable giving
  (bunching, QCD, DAF sizing recommendations), 529 education funding, equity
  compensation (RSU/RSA/NSO/ISO/ESPP) timing.
- **Scenario change sets** — save named bundles of lever positions and
  compare them side by side against the baseline plan (a presentation mode
  over the same optimization machinery, not a separate engine).

### 4.6 Stress testing
- **Monte Carlo / Probability Analysis** — choose a fast (vectorized) or
  high-fidelity (exact scalar) engine mode and settings; view success
  probability, essential-spending-funded probability, percentile bands, tax
  NPV/ELTR distributions, and the Guyton-Klinger shadow comparison.
- **Survivor / early death** — solvency after one spouse's early death.
- **Long-term care** — impact of an LTC event on the plan.
- **Divorce / QDRO** — impact of an imposed asset split at a chosen year.
- **Combined stress test** — stacks multiple stress conditions in one run.
- Each stress area (survivor, LTC, divorce) is gated by its own optional
  module toggle and shows an explanatory placeholder when off.

### 4.7 Reports and review
Build a full report package on demand; watch build progress; review a
"Build Impact" diff of what admin/system assumptions changed since the last
build; browse every workbook sheet in-app (Results Explorer) without opening
Excel; download the Excel workbook and PDF; review a plan-data summary;
review Spending Analysis (actual vs. budget, annualized run rate, portfolio
growth vs. prior year, reconciliation back into the 30-year model).

### 4.8 Year-to-date actuals
Upload or manually enter actual account transactions and balances for the
current year (with add/replace/deduplicate import modes); the system blends
these actuals into the current projection year and reconciles modeled vs.
actual balances.

### 4.9 Settings
Economic and tax assumptions (capital market assumptions, correlations, tax
constants, state tax tables), optional-module toggles, a field-finder search
across every plan input, per-sheet/column workbook formatting overrides, and
data/maintenance tools (pricing snapshot management, local backups, CSV
export, a low-level config console).

### 4.10 Admin console (advisor/system scope)
A separate console for system-wide (not per-plan) settings: app/runtime
configuration, pricing/market-data provider settings and security-master
data, allocation policy and asset-class universe, optimizer/rebalancing
defaults, ETF universe and replacement rules, tax constants and tax-law
update tracking, workbook build diagnostics, and reference-file editing. Any
per-client plan data shown here is read-only.

### 4.11 Planning Workbench
A cross-cutting workspace that unifies strategy, stress, and scenario tools
into one flow: pick a baseline, build a change set, choose a run type, see
the impact, decide. The Impact matrix (Unified Comparison Matrix) compares
the built baseline against every saved case by success probability, LCV,
ELTR, and total Roth conversions — the same whole-lifetime figures the Roth
optimizer and Monte Carlo engine report, so a saved case is directly
comparable to those. A separate "Forward-Looking (From Today)" panel below
the matrix shows FCV/EFTR for the latest build only, deliberately kept off
the matrix itself since those numbers move every day and a saved case's
snapshot does not. Also includes a "Strategy Levers" table ranking each
lever by its estimated effect on terminal net worth and success rate, each
with a jump-to-source link back to the real input page. This workspace
holds its own state locally and never mutates the saved plan on its own.

## 5. Outputs and their audiences

Every build produces four artifacts from one projection run, so they cannot
disagree with each other:

| Artifact | Audience | What it contains |
|---|---|---|
| **Excel workbook** (`retirement_plan.xlsx`) | Advisor/QC review; detailed client inspection | ~35+ tabs across four numbered areas — Overview/Projection, Optimization/Strategy, Risk & Stress Tests, Reference/Diagnostics. The canonical, most detailed artifact; every other output is derived from it. |
| **PDF** (`retirement_plan.pdf`) | Print/share-friendly advisor report | Every visible workbook sheet rendered directly from the saved workbook (not a hand-picked subset), so it can never drift from the Excel version. Includes a generated table of contents. |
| **Offline HTML dashboard** (`retirement_dashboard.html`) | Lightweight client-facing snapshot, no Excel required | Self-contained single file: KPI masthead, inline charts (net worth, income, spending/tax), holdings-by-account grid. |
| **Results Explorer (JSON model)** | The app's own in-browser report viewer | A renderer-neutral semantic model of the workbook's sections/tables/charts, letting the UI show report content without downloading Excel. |

A build also writes a manifest (`report_package.json`) recording each
artifact's presence, size, hash, and version — a QC/integrity record, not a
user-facing document — plus `plan_summary.json` (the KPI snapshot the UI
reads for quick status).

## 6. Business rules worth calling out

- **Roth-last is enforced, not just preferred.** Even in the comparative
  withdrawal-order tool, drawing from Roth while non-Roth assets remain is
  penalized ten times as heavily as other objective terms.
- **The Social Security "cut" is the default assumption, not a stress
  scenario.** The optimistic "no cut" case is the override, appearing as an
  upside stress scenario.
- **A Roth strategy that jeopardizes essential spending cannot be
  recommended, no matter how much it saves in taxes** — the 95% feasibility
  gate is a hard exclusion from selection (§3), though such strategies
  remain visible in the comparison view, flagged as infeasible.
- **Disabling an optional module removes it from computation entirely**, not
  just from view — a plan with a module off produces byte-identical
  baseline results whether or not that module's inputs are populated.
- **TLH and gain harvesting use the same selection logic in the projection
  engine and in the reporting sheet that describes them**, so the "what
  would be harvested" report and what the plan actually harvests can never
  disagree.

## 7. What the system deliberately does not do

- It is not multi-user or multi-tenant; it manages exactly one active local
  plan at a time (see the companion design spec for how this is enforced at
  the runtime level).
- It does not send plan data off the local machine by default — market
  pricing lookups are the only outbound network calls, and everything else
  (storage, computation, report generation) happens locally.
- Free-form scenario authoring is deliberately kept narrow (compare a
  handful of saved lever bundles) rather than built out as a headline
  feature, because the structured optimizers and stress tests already answer
  "what should I change" and "what if the world turns bad" more directly.
