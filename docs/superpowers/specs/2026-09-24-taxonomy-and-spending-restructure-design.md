# Taxonomy reconciliation and Spending / Housing restructure — design + implementation plan

> Items **#332** (taxonomy across Plan Features filters, Plan Features
> categories, left nav, workbook) and **#334–#339** (IRMAA indexing, spending
> adjustments, Large Discretionary, "Annualized" label, nav restructure,
> reserve checking). Decisions below were made with the user in the
> 2026-09-23/24 brainstorming session; each is marked **[decided]** with the
> option chosen. Part 1 is the design; Part 2 is the implementation plan.

---

# Part 1 — Design

## 1. The taxonomy model

Two independent facets, one controlled vocabulary, declared once in
`src/module_catalog.py`. Every surface draws its labels from it.

| Facet | Question it answers | Values |
|---|---|---|
| **Topic** (catalog `domain`) | "What part of my life is this about?" | 9 topics, §1.1 |
| **Answer type** (derived from catalog `kind`) | "What kind of answer is this?" | 5 answer types, §1.2 |

`kind` (8 values) stays as the engine-facing field; users only ever see its
answer type.

### 1.1 Topics [decided: dissolve Risk & Resilience; Assets & Protection → Insurance & Care]

Order is the `DOMAINS` tuple order.

| # | Topic | Change from today |
|---|---|---|
| 1 | Income & Benefits | — |
| 2 | Spending | — |
| 3 | Housing & Property | — |
| 4 | Investments | + `market_luck_stress_test` |
| 5 | Taxes | + `daf_giving`, `qcd_giving` (their nav home is Taxes → Charitable Giving) |
| 6 | **Insurance & Care** | renamed from *Assets & Protection*; + `life_insurance_need`, `survivor_stress_test`, `long_term_care_stress` |
| 7 | Estate & Legacy | − `daf_giving`, `qcd_giving` |
| 8 | Family & Business | + `divorce_qdro` |
| 9 | **Whole Plan** | renamed from *Reports & Documentation*; + `what_if_analysis`, `charts_dashboard` |

*Risk & Resilience* is removed: 4 of its 6 modules were stress tests, i.e. the
answer-type facet in disguise. (Insurance & Care ends up all-"Risks" by
answer type; that is acceptable — it is named for a life area, and the
problem was a topic *named* after an answer type, not one that happens to
contain only one.)

### 1.2 Answer types [decided: workbook "System" → "Reference"]

| Answer type | Kinds | Workbook section |
|---|---|---|
| Reports | projection, worksheet | `1. Reports` |
| Optimizers | optimization | `2. Optimizers` |
| Comparisons | comparison | `3. Comparisons` |
| Risks | stress_test, protection | `4. Risks` |
| Reference | diagnostics, reference | `5. Reference` (was `5. System`) |

`KIND_LETTER_PREFIX` becomes derived from `KIND_ANSWER_TYPE` + `ANSWER_TYPES`
order, so there is one table, not two.

### 1.3 Each surface picks a primary facet

| Surface | Primary | Secondary |
|---|---|---|
| Plan Features | Topic groups | Answer-type chips (5, human labels — replaces 7 raw `snake_case` kind ids) |
| Left nav | Topic groups for input pages, then answer-type-ish analysis groups (Strategy) and utility groups | — |
| Workbook | Answer-type sections (unchanged structure) | Topic column in the section-index table built from `_SECTION_META` |
| Categories | *is* the Topic registry | — |

### 1.4 The consistency rule (enforced by a test, §W-F)

A nav group label is either (a) a Topic label, (b) a join of Topic labels
with `&` (e.g. *Investments & Property* = Investments + Housing & Property),
or (c) in the explicit utility allowlist
`{Plan Status, Household, Strategy, Reports & Review, Settings}`.
A surface may **merge** topics under a join; it may never **reuse** a Topic
label for a different membership. Plan Features chip labels must equal the
workbook section titles minus their number prefix.

Workbook tab names are already lettered by answer-type section
(`1A. Executive Summary` … `5H. Tax Capacity`); §9.1 makes the order *within*
a section follow Topic, so the workbook shows both facets.

## 2. Target left nav

```
Plan Status
Household                Household & People
Income & Benefits        Work Income · SS/Pensions/Annuities
Spending                 Spending Model
Investments & Property   Investment Holdings · Reserve Requirements · Other Assets and Liabilities · Home Equity Line
Insurance & Care         Insurance
Estate & Legacy          Estate Inputs
Taxes                    Roth Conversion · Charitable Giving
Family & Business        Education & Equity Comp
Strategy                 Optimize (incl. Next Housing Move) · Stress Test · Scenarios · Workbench
Reports & Review         Actual Spending · Build & Results
Settings                 (unchanged)
```

There is exactly **one** reports group. Today a second group string,
`"Reports"`, exists only on hidden hub sub-pages (`review` "Download
Reports", `build_impact`, `detailed_results`, `plan_data_report`,
`spending_dashboard`); it never renders in the nav and the Field Finder
already relabels it (`fieldFinderCategoryName`, `dashboard.js:2357`). Those
sub-pages move to `group: "Reports & Review"` and the relabel special case is
deleted, so the string `"Reports"` no longer exists as a group.

Changes vs. today: *Housing & Property* nav group dissolves (its topic lives on
in Plan Features and the workbook; the merge rule allows this); *Assets &
Protection* splits into *Investments & Property*, *Insurance & Care*, *Estate &
Legacy*; *Wellness* and *Housing* pages leave the nav (§3); *Actual Spending*
is new; the visible `reports_and_review` hub is retitled **Build & Results**
[decided: C] — it holds readiness, build, impact, results, downloads and plan
data review, so a name covering only "impact" would undersell it. The hidden
sub-page `build_impact` keeps its title "Impact & Build History" (no longer
a near-duplicate). *People and Income* splits into *Household* (utility) and
*Income & Benefits* (topic) — §9.2.

Note: the brainstorming mockup labelled the group "Investments and assets";
it is *Investments & Property* here so the label is a legal join under §1.4
(it holds HELOC and home value, both Housing & Property).

## 3. Spending Model (#338, #337) [decided]

Spending Model becomes the single read/write surface for every spending
tracking type: one accordion per tracking type, **in this order**:

1. Core Expenses · 2. Housing · 3. Wellness · 4. Travel · 5. Large Discretionary · 6. Taxes · 7. Business

then an **Adjustments** accordion (§5).

- Housing, Wellness and Travel stop being "read-only reference — budgeted on
  its source page". Their accordion bodies render the **same field-group
  renderers** the old source pages used (extracted, not copied — the W13
  `familyBusinessGroupsHtml()` precedent). Travel keeps its
  "group number wins" budget mode.
- The standalone *Housing* (`spending_mortgage_events`) and *Wellness*
  (`retirement_wellness`) nav steps are removed; `SECTION_REDIRECTS` send old
  ids to `spending_core` with the right accordion open.
- Housing **costs** (P&I, property tax, HOA, upkeep) live in the Housing
  accordion. Home **value** and mortgage **balance** move to Other Assets and
  Liabilities (§6). Home **sale / next moves / state over time** move to Next
  Housing Move (§6).
- **Withdrawal Order** tab is removed from Spending Model — but only after a
  parity test proves every row it renders today renders on Optimize
  (HSA Drawdown, Harvesting, Withdrawal Sequencing). Any row that fails parity
  is moved to Optimize, never dropped.
- **Actual Spending** — `ytd_transactions` ("Actual Spending (This Year)") and
  `spending_dashboard` ("Spending Analysis") merge into one visible step
  `actual_spending` in *Reports & Review*, two tabs. Old ids redirect.
- **#337** — the string "Annualized Actual" is replaced by "Annualized"
  everywhere (category, detail, and the four KPI labels in
  `frontend/js/spending_dashboard.js`). A test forbids the old string in
  `frontend/`.

## 4. Large Discretionary (#336) [decided: one-time only]

- One section (the Large Discretionary accordion). Category pulldown:
  **Weddings, Large Gifts, Education, Auto, Other.** The Large Discretionary
  groups in `client_spending_taxonomy.csv` are retired.
- Each row = one amount, one year. **Never annualized** — YTD actual is shown,
  no Annualized figure.
- **Budget** for the current year includes a row only when its year equals
  the current year. (Fixes the observed Budget $290,000 vs Projection
  $140,000.)
- **Projection / cash flow**: every row lands in its own year, regardless.
- Education label reads *Education (not 529-funded)*; when
  `education_funding_529` is on, the section shows a one-line double-count
  caution.
- **Migration** of legacy repeatable rows (`extra_N_start_year`/`end_year`,
  annual amount): on load, each is expanded into one dated row per year and an
  import notice lists them; when a row expands to > 10 rows the notice
  recommends moving it to a Core category. Legacy `extra_N_type` values map:
  Weddings→Weddings, anything gift-like→Large Gifts, Education/Tuition→Education,
  Vehicle/Auto→Auto, else→Other.

## 5. Spending Adjustments (#335) [decided: A — step-down, end year, ± allowed]

Editable table (add / edit / delete), in the Adjustments accordion:

| Column | Meaning |
|---|---|
| Category ▾ | Every active category in Core, Housing, Wellness, Travel, plus one "All ‹tracking type›" option per tracking type. Excludes Large Discretionary, Taxes, Business. |
| Start year | First year the change applies |
| End year | Optional; blank = through plan end |
| Change % | Negative = decrease, positive = increase |

Semantics: a **one-time step** applied multiplicatively from start year
(inclusive) to end year (inclusive); inflation continues on the stepped base.
Multiple rows on the same category compound in start-year order
(−20% then −10% ⇒ 0.72). An "All Travel" row and a "Hotels" row compound for
Hotels. Storage: new CSV section `Spending Adjustments` in
`client_spending.csv`, rows `adj_N_category`, `adj_N_start_year`,
`adj_N_end_year`, `adj_N_change_pct`.

## 6. Housing restructure (#338) [decided: C gating; A placement; toggle on Plan Features]

- **Next Housing Move** (the Optimize section) holds: home sale, next housing
  steps 1 & 2, state residency over time, and the "where to live" ZIP search.
- Catalog module `housing_location_search` is **renamed "Next Housing Move"**
  (key unchanged) and its switch stays on **Plan Features** under Housing &
  Property with the other optional modules. The section's off-state note links
  to Plan Features; it has no inline switch.
- **Off semantics [C]:** when the switch is off, the engine treats every Next
  Housing Move input as blank (stay in current home, current state, whole
  plan). Values persist in the CSV and are restored when switched on. The
  module becomes `engine_participation=True`. The off-state note reads
  "Off — N saved fields not applied: the plan assumes you stay in your current
  home and state." with the saved values listed muted below it.
- `housing_trajectory_comparison` and `state_residency` declare a soft
  dependency (`degrades_without`) on it.
- **Plan Features missing-row bug:** Plan Features lists module toggles only
  from rows present in the plan's `client_optional_functions.csv`, so a plan
  created before a module existed shows no switch. Fix: when the config
  payload is built, backfill a row for every catalog `module_toggle` module
  missing from the plan, with value = its current effective state from
  `module_status()`, and persist it — the existing `editValue(row_index)` path
  then works unchanged.
- **Home value & mortgage balance** → Other Assets and Liabilities (always in
  effect). **HELOC** (`heloc_strategy`) → its own step in *Investments &
  Property*, still gated by its plan flag.

## 7. IRMAA indexing (#334)

Today: thresholds grow at `irmaa_annual_inflator` (2%), surcharge dollars do
not grow at all, and the growth is re-implemented in six places.

New rule, implemented once in `src/tax_kernel.py`:

| Quantity | Grows with | Deterministic | Monte Carlo |
|---|---|---|---|
| MAGI thresholds | CPI | `(1+c['inf'])^(y−plan_start)` | `inflation_index_by_year` |
| Part B surcharge $ | Medicare Part B | `med_inf` | `medical_index_by_year` |
| Part D surcharge $ | Medicare Part D | `partd_inf` | `partd_index_by_year` if present, else `partd_inf` |

`irmaa_annual_inflator` and `irmaa_index_by_year` are retired;
`c['irmaa_inflator']` is no longer read. All callers (`core.py`,
`daf_optimizer.py`, `planning_engines.py` ×2 + MC index builder,
`sheets_strategy.py`, `sheets_tax_capacity.py`,
`withdrawal_cascade_ira_true_up.py`) route through `tax_kernel`. This
**intentionally moves** the golden master (`lifetime_tax`, likely
`terminal_nw`).

## 8. Reserve Requirements checking (#339)

The *Checking accounts* field (`Other Assets,Cash,value`) is not read by the
engine — `c['cash_other']` comes from `_Checking` holdings accounts
(`src/data_io.py:1812`). Remove the field from Reserve Requirements, the demo
CSV and the schema. On load, a plan with a non-zero value and no `_Checking`
holdings account gets an import warning naming the amount.

## 9. Formerly out of scope — now resolved

### 9.1 Workbook sheet numbering

Finding: user-visible tab names are **already** derived — section number +
letter (`compute_final_sheet_renames`, e.g. `'11B. Tax Capacity'` →
`'5H. Tax Capacity'`). The legacy numbers survive only in internal
`SHEET_REGISTRY` dict keys, which users never see and which the in-cell
text-substitution pass depends on.

Resolution:
- **Within each answer-type section, order sheets by Topic** (`DOMAINS`
  order), then by the existing `letter_rank`. Letters stay derived, so the
  tab strip shows answer type (number) and topic (sequence). Example,
  section 2: Social Security (Income & Benefits) → Housing Comparison
  (Housing & Property) → Asset Allocation, Withdrawal Sequencing, Asset
  Location (Investments) → Roth, HSA, Charitable, Tax-Loss, Gain Harvesting
  (Taxes) → Estate (Estate & Legacy) → Education, Equity Comp, Special
  Needs, Business Succession (Family & Business).
- Internal dict keys are **not** renamed (all churn, no user value); a guard
  test asserts no final tab name carries a legacy number.
- Sheets without a module (`Plan Data`, `Assumptions`, `Balance Sheet`,
  `Net Worth`, `Cash Flow`, `Executive Summary`, …) sort as *Whole Plan*.

### 9.2 People and Income split

*People and Income* is neither a Topic nor a join. Split it:
**Household** (utility group, like Plan Status — plan-wide facts:
Household & People) and **Income & Benefits** (Topic: Work Income,
SS/Pensions/Annuities). Utility allowlist replaces *People and Income* with
*Household*.

### 9.3 IRMAA base year

The tier tables are in `IRMAA_TIERS_VALUE_YEAR` (2025) dollars, but today's
growth compounds from `plan_start`, so a 2026-start plan applies 2025
thresholds in 2026 — one year of indexing lost. All IRMAA factors grow from
`IRMAA_TIERS_VALUE_YEAR`. Monte Carlo paths (which are 1.0 at `plan_start`)
are bridged by the deterministic rate from value year to `plan_start`.

### 9.4 IRMAA statutory rounding and top tier

- Indexed thresholds round to the nearest **$1,000** (Single, HOH, MFS) and
  **$2,000** (MFJ, which is twice the individual amount).
- The **top tier** is frozen through 2027 and indexed from **2028** on its
  2027 value (Bipartisan Budget Act of 2018).
- Monthly surcharge amounts round to the nearest **$0.10**.

### 9.5 Found while resolving: broken MFS table

`IRMAA_TIERS_BASE_YEAR['MFS']` has 5 rows where the statute has 2, with
non-monotonic thresholds (106k, 403k, 335k, 402k, 750k) — the last three are
MFJ rows appended in error. Under `reversed()` scanning, an MFS household at
$410k MAGI is billed the 367.8 tier instead of the top tier. Fix the source
data (`reference_data/tax_law_v10.json` MFS `irmaa_tier3..5` entries —
delete; re-check tiers 1–2 against the CMS annual notice) and add a validator:
every filing status's thresholds strictly increase.

### 9.6 Still out of scope

Nothing from the original list remains out of scope.

---

# Part 2 — Implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver §1–§8 as six independently mergeable workstreams.

**Architecture:** Catalog (`src/module_catalog.py`) is the single source for
Topic and Answer-type vocabulary; server serves it via
`config_service.module_taxonomy`; Plan Features, nav and workbook consume it.
Engine changes are confined to `tax_kernel.py` (IRMAA) and the spending /
housing loaders.

**Tech stack:** Python 3 (pytest), vanilla ES modules (node --test), Playwright e2e.

## Global constraints

- `dashboard.js` is under a zero-headroom size ratchet
  (`tests/test_frontend_size_ratchet.py`): every added line must be paid for
  by moving code to a `dashboard_decomp_*.js` file.
- Never read `dashboard.js` (7,287 lines) or `dashboard_decomp_row_model.js`
  (5,188) whole — Grep, then Read with offset/limit.
- Golden master: `python tools/regen_golden_master.py measure` after every
  workstream. Only **W-B** may change pins, via one `regen --reason`, after a
  hand-verified delta.
- Fast loop: `pytest -m "not slow"`; frontend: `npm test`.
- Codemod census after any change to `dashboard.js` top-level declarations:
  `node tools/js_codemod/census.mjs` then `node tools/js_codemod/convert_dashboard.mjs`.
- Label copy: "Annualized" (never "Annualized Actual"); Topic and Answer-type
  labels exactly as in §1.1 / §1.2.

## Detail level

W-A and W-B are specified to code level. W-C–W-F touch the two >5,000-line
files; each task names files, interfaces and the exact test assertions, and
its **first step** is a scoped Grep/Read to locate the edit points — the code
for those steps is written at that point rather than guessed here.

## Workstream summary and usage estimates

Check `/usage` against these as the plan executes.

| WS | Scope | Model / effort | Relative usage (5-h Pro session) | Drivers | Depends on |
|---|---|---|---|---|---|
| W-A | Taxonomy vocabulary + Plan Features | Sonnet / medium | Moderate | `module_catalog.py` (grep), catalog tests pinning domains | — |
| W-B | IRMAA indexing, value-year base, statutory rounding, MFS table fix | Opus / high | Moderate | 8 call sites; tax-law JSON; golden-master verification | — |
| W-C | Spending Model consolidation | Opus / medium | **Heavy ⚠** | `dashboard.js` ratchet, renderer extraction, redirects, many UI tests | W-A |
| W-D | Large Discretionary + Adjustments | Opus / medium | **Heavy ⚠** | budget resolver + engine + migration + two tables | W-C |
| W-E | Housing restructure | Opus / medium | Moderate–heavy | loader gating, catalog, Optimize section | W-A |
| W-F | Nav regroup (incl. Household / Income & Benefits), reserve checking, workbook Topic column + topic ordering, consistency test | Sonnet / medium | Moderate | nav pin tests, sheet-order pins, e2e nav-integrity | W-A, W-C, W-E |

**Expensive-step flags:**
- W-C Task C2 (renderer extraction): scope by grepping the render function
  names only; do not open the source pages' full files.
- W-D Task D3 (engine adjustments): the only engine change outside IRMAA —
  run `measure` before and after; demo has no adjustment rows, so expected
  delta is 0.00. A non-zero delta is a bug, not a regen.
- W-B: never loop regen → run → regen. One hand check, one regen.

---

## W-A — Taxonomy vocabulary

### Task A1: Topics re-cut in the catalog

**Files:**
- Modify: `src/module_catalog.py:97-110` (domain constants), and the `domain=` of 11 modules listed in §1.1
- Test: `tests/test_module_catalog.py`

**Interfaces — Produces:** constants `INSURANCE_CARE = "Insurance & Care"`,
`WHOLE_PLAN = "Whole Plan"`; `DOMAINS` 9-tuple in §1.1 order;
`RISK_RESILIENCE`, `ASSETS_PROTECTION`, `REPORTS_DOCUMENTATION` deleted.

- [ ] **Step 1: Write the failing test** (append to `tests/test_module_catalog.py`)

```python
from src import module_catalog as mc

def test_topics_are_the_nine_life_areas():
    assert mc.DOMAINS == (
        "Income & Benefits", "Spending", "Housing & Property", "Investments",
        "Taxes", "Insurance & Care", "Estate & Legacy", "Family & Business",
        "Whole Plan",
    )

def test_topic_recut_membership():
    want = {
        "market_luck_stress_test": "Investments",
        "daf_giving": "Taxes", "qcd_giving": "Taxes",
        "life_insurance_need": "Insurance & Care",
        "survivor_stress_test": "Insurance & Care",
        "long_term_care_stress": "Insurance & Care",
        "existing_life_insurance": "Insurance & Care",
        "hybrid_ltc_policy": "Insurance & Care",
        "divorce_qdro": "Family & Business",
        "what_if_analysis": "Whole Plan",
        "charts_dashboard": "Whole Plan",
    }
    assert {k: mc.CATALOG[k].domain for k in want} == want

def test_no_module_uses_a_retired_topic():
    retired = {"Risk & Resilience", "Assets & Protection", "Reports & Documentation"}
    assert not [k for k, m in mc.CATALOG.items() if m.domain in retired]
```

- [ ] **Step 2: Run** `pytest tests/test_module_catalog.py -k "topic" -v` — Expected: FAIL (`KIND_ANSWER_TYPE` missing / tuple mismatch).
- [ ] **Step 3: Implement.** Replace lines 97–110:

```python
INCOME_BENEFITS = "Income & Benefits"
SPENDING = "Spending"
HOUSING_PROPERTY = "Housing & Property"
INVESTMENTS = "Investments"
TAXES = "Taxes"
INSURANCE_CARE = "Insurance & Care"
ESTATE_LEGACY = "Estate & Legacy"
FAMILY_BUSINESS = "Family & Business"
WHOLE_PLAN = "Whole Plan"

DOMAINS = (INCOME_BENEFITS, SPENDING, HOUSING_PROPERTY, INVESTMENTS, TAXES,
           INSURANCE_CARE, ESTATE_LEGACY, FAMILY_BUSINESS, WHOLE_PLAN)
```

Then `grep -n "domain=ASSETS_PROTECTION\|domain=RISK_RESILIENCE\|domain=REPORTS_DOCUMENTATION" src/module_catalog.py` and set each per the table in Step 1 (`ASSETS_PROTECTION`→`INSURANCE_CARE`, `REPORTS_DOCUMENTATION`→`WHOLE_PLAN`, and each `RISK_RESILIENCE` module per the map; `daf_giving`/`qcd_giving`/`market_luck_stress_test`/`charts_dashboard` changed by key). Update the comment at lines 89–96 ("Monte Carlo a STRESS_TEST in Risk & Resilience" → "in Investments"). Task A2 supplies `KIND_ANSWER_TYPE`; run A1's tests after A2 if executing strictly in order.
- [ ] **Step 4: Run** `pytest tests/test_module_catalog.py -v` and `pytest -m "not slow" -k "catalog or domain or plan_feature"` — Expected: PASS after fixing any test that pins old domain names (update the pin, stating the rename).
- [ ] **Step 5: Commit** `git commit -am "feat(catalog): re-cut topics — Insurance & Care, Whole Plan; dissolve Risk & Resilience"`

### Task A2: Answer types derived from kinds

**Files:** Modify `src/module_catalog.py:1335-1363`; `src/reporting/workbook_common.py:207-213`; `src/server_services/config_service.py` (taxonomy payload); Test `tests/test_module_catalog.py`, `tests/test_sheet_table_consistency.py`

**Interfaces — Produces:** `ANSWER_TYPES: tuple[str,...] = ("Reports","Optimizers","Comparisons","Risks","Reference")`; `KIND_ANSWER_TYPE: dict[str,str]`; `KIND_LETTER_PREFIX` derived; taxonomy payload gains `"answer_types": list(ANSWER_TYPES)` and per-module `"answer_type"`.

- [ ] **Step 1: Failing test**

```python
def test_answer_types_drive_letter_groups():
    assert mc.ANSWER_TYPES == ("Reports", "Optimizers", "Comparisons", "Risks", "Reference")
    assert mc.KIND_ANSWER_TYPE == {
        "projection": "Reports", "worksheet": "Reports",
        "optimization": "Optimizers", "comparison": "Comparisons",
        "stress_test": "Risks", "protection": "Risks",
        "diagnostics": "Reference", "reference": "Reference",
    }
    for kind, at in mc.KIND_ANSWER_TYPE.items():
        assert mc.KIND_LETTER_PREFIX[kind] == str(mc.ANSWER_TYPES.index(at) + 1)

def test_workbook_section_titles_match_answer_types():
    from src.reporting.workbook_common import _SECTION_META
    assert [t.split(". ", 1)[1] for t, _ in (_SECTION_META[str(i)] for i in range(1, 6))] == list(mc.ANSWER_TYPES)
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** — replace the `KIND_LETTER_PREFIX` literal:

```python
ANSWER_TYPES = ("Reports", "Optimizers", "Comparisons", "Risks", "Reference")
KIND_ANSWER_TYPE: Dict[str, str] = {
    PROJECTION: "Reports", WORKSHEET: "Reports",
    OPTIMIZATION: "Optimizers", COMPARISON: "Comparisons",
    STRESS_TEST: "Risks", PROTECTION: "Risks",
    DIAGNOSTICS: "Reference", REFERENCE: "Reference",
}
KIND_LETTER_PREFIX: Dict[str, str] = {
    k: str(ANSWER_TYPES.index(at) + 1) for k, at in KIND_ANSWER_TYPE.items()
}
```

`ANSWER_TYPES`/`KIND_ANSWER_TYPE` must be defined above `validate()` and above
any use; place them directly after `KIND_QUESTION`. In `workbook_common.py`
change `'5': ('5. System', …)` to `'5': ('5. Reference', …)`. In
`config_service.py` taxonomy dict add `"answer_types": list(ANSWER_TYPES)` and
per module `"answer_type": KIND_ANSWER_TYPE[m.kind]`. Then
`grep -rn "5. System" src tests tools` and update every hit (including
`src/reporting/_template_layout_data.json` keys, which still carry the older
4-section names — rename its section keys to the five `_SECTION_META` titles).
- [ ] **Step 4: Run** `pytest -m "not slow"` — PASS; `python tools/regen_golden_master.py measure` — `MATCH +0.00`.
- [ ] **Step 5: Commit** `feat(catalog): answer types as the user-facing kind vocabulary; System → Reference`

### Task A3: Plan Features chips use answer types; catalog-driven toggle list

**Files:** Modify `frontend/js/dashboard_decomp_plan_features.js:115-192`; `src/server_services/config_service.py` (backfill); Test `tests/frontend/plan_features.test.mjs`, new `tests/test_optional_functions_backfill.py`

**Interfaces — Consumes:** payload `answer_types`, `modules[k].answer_type` (A2). **Produces:** `planFeatureKinds()` returns answer-type labels; `setPlanFeatureKind(label)` filters on `meta.answer_type`.

- [ ] **Step 1: Failing tests**

```js
// tests/frontend/plan_features.test.mjs
test("chips are answer-type labels, not raw kind ids", () => {
  const tax = { answer_types: ["Reports","Optimizers","Comparisons","Risks","Reference"],
    modules: { a: { kind: "stress_test", answer_type: "Risks", domain: "Investments" },
               b: { kind: "optimization", answer_type: "Optimizers", domain: "Taxes" } } };
  const rows = [{ label: "a" }, { label: "b" }];
  assert.deepEqual(planFeatureKinds(rows, tax), ["Optimizers", "Risks"]);
  const g = planFeatureGroups(rows, tax, "Risks");
  assert.deepEqual(g.flatMap((x) => x.entries.map((e) => e.key)), ["a"]);
});
```

```python
# tests/test_optional_functions_backfill.py
from src.module_catalog import CATALOG, GATE_MODULE_TOGGLE
from src.server_services.config_service import backfill_optional_function_rows

def test_missing_module_toggle_rows_are_backfilled():
    rows = [{"section": "Optional Functions", "label": "roth_conversion_plan", "value": "TRUE"}]
    out = backfill_optional_function_rows(rows, effective={"housing_location_search": True})
    labels = {r["label"] for r in out}
    toggles = {k for k, m in CATALOG.items() if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by}
    assert toggles <= labels
    hls = next(r for r in out if r["label"] == "housing_location_search")
    assert hls["value"] == "TRUE"
    assert out[0] == rows[0]  # existing rows untouched, order kept
```

- [ ] **Step 2: Run** `npm test -- tests/frontend/plan_features.test.mjs` and `pytest tests/test_optional_functions_backfill.py -v` — FAIL.
- [ ] **Step 3: Implement.** In `planFeatureGroups`/`planFeatureKinds` replace `meta.kind` with `meta.answer_type` for filtering and chip collection; order chips by `taxonomy.answer_types`. In `config_service.py` add:

```python
def backfill_optional_function_rows(rows, effective):
    """Append a row for every switchable catalog module the plan's
    client_optional_functions.csv lacks, valued at its current effective
    state, so Plan Features can show and edit it (the missing-row bug)."""
    from ..module_catalog import CATALOG, GATE_MODULE_TOGGLE
    have = {r.get("label") for r in rows}
    out = list(rows)
    for key, m in CATALOG.items():
        if m.optional and m.gate_kind == GATE_MODULE_TOGGLE and not m.gated_by and key not in have:
            out.append({"section": "Optional Functions", "subsection": "", "label": key,
                        "value": "TRUE" if effective.get(key, True) else "FALSE",
                        "units": "boolean", "notes": m.name})
    return out
```

Call it where the config payload assembles optional-function rows (grep `client_optional_functions` / `_module_status` in `config_service.py`), passing `effective` from `module_status()`, and persist via the existing sectioned-data save path so `row_index` is real.
- [ ] **Step 4: Run** both tests + `pytest -m "not slow" -k "optional or plan_feature or module"` — PASS.
- [ ] **Step 5: Commit** `feat(plan-features): answer-type chips; backfill missing module toggle rows`

### Task A4: Rename "Housing Location Search" → "Next Housing Move"

**Files:** `src/module_catalog.py:715`; `input/demo/client_optional_functions.csv:36` (notes text); `tests/frontend/housing_location_search_gating.test.mjs`; `src/server/plan_routes.py` (label string)

- [ ] **Step 1:** Failing test in `tests/test_module_catalog.py`: `assert mc.CATALOG["housing_location_search"].name == "Next Housing Move"`.
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Change the catalog name string; `grep -rn "Housing Location Search" src frontend tests` and update user-visible strings (keep the key).
- [ ] **Step 4:** `pytest -m "not slow"`, `npm test` — PASS.
- [ ] **Step 5:** Commit `feat(catalog): name the housing module Next Housing Move to match its section`

---

## W-B — IRMAA indexing (#334)

### Task B0: Fix the MFS IRMAA table; monotonicity validator (§9.5)

**Files:** `reference_data/tax_law_v10.json` (MFS `irmaa_tier3_*`..`irmaa_tier5_*` entries); `src/taxes.py:349-350` (table load); Test new `tests/test_irmaa_tables_valid.py`

- [ ] **Step 1: Failing test**

```python
from src import taxes as _td

def test_every_filing_status_has_increasing_thresholds():
    for filing, tiers in _td.IRMAA_TIERS_BASE_YEAR.items():
        thr = [t[0] for t in tiers]
        assert thr == sorted(set(thr)), (filing, thr)

def test_mfs_has_the_two_statutory_tiers():
    assert len(_td.IRMAA_TIERS_BASE_YEAR["MFS"]) == 2
```

- [ ] **Step 2:** `pytest tests/test_irmaa_tables_valid.py -v` — FAIL (MFS: 106000, 403000, 335000, …).
- [ ] **Step 3:** `grep -n "irmaa_tier" reference_data/tax_law_v10.json` and delete the MFS `irmaa_tier3/4/5` threshold and surcharge entries; confirm the remaining MFS tier 1–2 thresholds and surcharges against the CMS annual Medicare premium notice for the value year, correcting if they differ. In `src/taxes.py`, after the table load, raise `ValueError` naming the filing status if thresholds are not strictly increasing (so bad data fails at import, not silently).
- [ ] **Step 4:** `pytest tests/test_irmaa_tables_valid.py -v` — PASS; `measure` → `+0.00` (demo is MFJ).
- [ ] **Step 5:** Commit `fix(irmaa): MFS table had three MFJ rows appended; validate monotonic thresholds`

### Task B1: Single IRMAA indexing implementation in `tax_kernel` (§7, §9.3, §9.4)

**Files:** Modify `src/tax_kernel.py:70-99`; Test new `tests/test_irmaa_indexing_unit.py`

**Interfaces — Produces:**
`irmaa_threshold(c, filing, tier_idx, year) -> float` (indexed, rounded, top-tier rule);
`irmaa_threshold_factor(c, year) -> float` (unrounded CPI growth from the value year, for callers that scale one base amount);
`irmaa_partb_factor(c, year)`, `irmaa_partd_factor(c, year) -> float`;
`irmaa_surcharge(agi, year, n_people, filing, c)` and `irmaa_tier(agi, year, filing, c)` keep their signatures.
`irmaa_factor_for_year = irmaa_threshold_factor` (alias; `projection_pipeline.py:92` exports it).

- [ ] **Step 1: Failing test**

```python
import pytest
from src import tax_kernel as tk
from src import taxes as _td

VY = _td.IRMAA_TIERS_VALUE_YEAR          # 2025
C = {"plan_start": 2026, "inf": 0.03, "med_inf": 0.055, "partd_inf": 0.0125}

def _round(x, step):
    return round(x / step) * step

def test_threshold_is_cpi_indexed_from_value_year_and_rounded():
    c = dict(C, irmaa_inflator=0.10)                      # must be ignored
    n = 2036 - VY
    assert tk.irmaa_threshold(c, "MFJ", 0, 2036) == _round(212000 * 1.03 ** n, 2000)
    assert tk.irmaa_threshold(c, "Single", 0, 2036) == _round(106000 * 1.03 ** n, 1000)

def test_top_tier_frozen_through_2027_then_indexed():
    top = len(_td.IRMAA_TIERS_BASE_YEAR["MFJ"]) - 1
    assert tk.irmaa_threshold(C, "MFJ", top, 2027) == 750000
    assert tk.irmaa_threshold(C, "MFJ", top, 2030) == _round(750000 * 1.03 ** 3, 2000)

def test_surcharge_dollars_grow_with_medicare_rates_rounded_to_dimes():
    _, pb, pd = _td.IRMAA_TIERS_BASE_YEAR["MFJ"][-1]
    n = 2036 - VY
    want = (round(pb * 1.055 ** n, 1) + round(pd * 1.0125 ** n, 1)) * 2 * 12
    assert tk.irmaa_surcharge(10_000_000, 2036, 2, "MFJ", C) == pytest.approx(want)

def test_monte_carlo_path_bridged_from_value_year():
    c = dict(C, inflation_index_by_year={2030: 1.5}, medical_index_by_year={2030: 2.0})
    assert tk.irmaa_threshold_factor(c, 2030) == pytest.approx(1.03 ** (2026 - VY) * 1.5)
    assert tk.irmaa_partb_factor(c, 2030) == pytest.approx(1.055 ** (2026 - VY) * 2.0)
    assert tk.irmaa_partd_factor(c, 2030) == pytest.approx(1.0125 ** (2030 - VY))

def test_tier_boundaries_use_rounded_threshold():
    t = tk.irmaa_threshold(C, "MFJ", 0, 2036)
    assert tk.irmaa_tier(t, 2036, "MFJ", C) == 0          # statute: "more than"
    assert tk.irmaa_tier(t + 1, 2036, "MFJ", C) == 1
```

- [ ] **Step 2: Run** `pytest tests/test_irmaa_indexing_unit.py -v` — FAIL (`irmaa_threshold` undefined).
- [ ] **Step 3: Implement** — replace `tax_kernel.py:70-99`:

```python
# #334 / spec §9.4: statutory indexing rules for IRMAA.
IRMAA_TOP_TIER_INDEX_START = 2028   # BBA 2018: top tier indexed from 2028


def _index_factor(c, path_key, rate, year, base_year):
    """Growth from ``base_year`` to ``year``. Monte Carlo paths are 1.0 at
    plan_start, so they are bridged from base_year at the deterministic rate."""
    r = float(rate or 0.0)
    path = c.get(path_key)
    if isinstance(path, dict):
        v = path.get(year, path.get(int(year)))
        if v is not None:
            ps = int(c.get('plan_start', year))
            return (1.0 + r) ** (ps - int(base_year)) * float(v)
    return (1.0 + r) ** (int(year) - int(base_year))


def irmaa_threshold_factor(c, year):
    """CPI growth of IRMAA MAGI thresholds from the tier tables' value year."""
    return _index_factor(c, 'inflation_index_by_year', c.get('inf', 0.025),
                         year, _td.IRMAA_TIERS_VALUE_YEAR)


irmaa_factor_for_year = irmaa_threshold_factor


def irmaa_partb_factor(c, year):
    """Part B IRMAA dollars scale with the Part B premium."""
    return _index_factor(c, 'medical_index_by_year',
                         c.get('med_inf', c.get('inf', 0.025)),
                         year, _td.IRMAA_TIERS_VALUE_YEAR)


def irmaa_partd_factor(c, year):
    """Part D IRMAA dollars scale with the Part D base premium."""
    return _index_factor(c, 'partd_index_by_year',
                         c.get('partd_inf', c.get('med_inf', 0.0125)),
                         year, _td.IRMAA_TIERS_VALUE_YEAR)


def _tiers(filing):
    return _td.IRMAA_TIERS_BASE_YEAR.get(filing, _td.IRMAA_TIERS_BASE_YEAR['MFJ'])


def irmaa_threshold(c, filing, tier_idx, year):
    """Indexed, statutorily rounded MAGI threshold for 0-based ``tier_idx``."""
    tiers = _tiers(filing)
    base = tiers[tier_idx][0]
    if tier_idx == len(tiers) - 1:
        if int(year) < IRMAA_TOP_TIER_INDEX_START:
            return float(base)
        f = (irmaa_threshold_factor(c, year)
             / irmaa_threshold_factor(c, IRMAA_TOP_TIER_INDEX_START - 1))
    else:
        f = irmaa_threshold_factor(c, year)
    step = 2000 if filing == 'MFJ' else 1000
    return float(round(base * f / step) * step)


def irmaa_surcharge(agi, year, n_people, filing, c):
    """Annual Part B + Part D IRMAA surcharge for a household at ``agi``."""
    tiers = _tiers(filing)
    for i in range(len(tiers) - 1, -1, -1):
        if agi > irmaa_threshold(c, filing, i, year):
            _, partb, partd = tiers[i]
            monthly = (round(partb * irmaa_partb_factor(c, year), 1)
                       + round(partd * irmaa_partd_factor(c, year), 1))
            return monthly * n_people * 12
    return 0.0


def irmaa_tier(agi, year, filing, c):
    """1-indexed IRMAA tier (0 = no surcharge) for a household at ``agi``."""
    tiers = _tiers(filing)
    for i in range(len(tiers) - 1, -1, -1):
        if agi > irmaa_threshold(c, filing, i, year):
            return i + 1
    return 0
```

- [ ] **Step 4: Run** `pytest tests/test_irmaa_indexing_unit.py -v` — PASS.
- [ ] **Step 5: Commit** `feat(irmaa): CPI thresholds from value year, statutory rounding, top-tier 2028 rule, Medicare-indexed surcharges (#334)`

### Task B2: Route every caller through `tax_kernel`; retire `irmaa_inflator`

**Files:** `src/core.py:1085-1099`; `src/daf_optimizer.py:51-64`; `src/planning_engines.py:2251,2292,3611,3639,4989`; `src/reporting/sheets_strategy.py:1056`; `src/reporting/sheets_tax_capacity.py:68-76`; `src/data_io.py:1494,2160`; `input/demo/client_policy.csv:28`; `tests/fixtures/sample_plan_frozen/client_policy.csv`; `reference_data/schema.csv`; frontend refs in `admin.js`, `dashboard.js`, `dashboard_decomp_allocation_optimizer.js`, `dashboard_decomp_row_model.js` (grep `irmaa_inflator|irmaa_annual_inflator`)

- [ ] **Step 1: Failing guard test** `tests/test_irmaa_single_source_regression.py`:

```python
import pathlib, re
def test_no_irmaa_inflator_outside_kernel():
    hits = [p for p in pathlib.Path("src").rglob("*.py")
            if re.search(r"irmaa_inflator|irmaa_index_by_year", p.read_text(encoding="utf-8"))]
    assert hits == [], hits
```

- [ ] **Step 2: Run** — FAIL (lists the files above).
- [ ] **Step 3: Implement.** `core.irmaa_surcharge/irmaa_tier`: keep signatures for back-compat but build `c={'plan_start': plan_start, 'inf': inflator}` only if no config is passed — better: add a `c=None` kwarg and delegate to `tax_kernel`; update `daf_optimizer` to pass `c`. `planning_engines` 2251/2292, `sheets_strategy.py:1056` and `withdrawal_cascade_ira_true_up.py:45` (`c['irmaa_base'] * factor`): replace with `_tk.irmaa_threshold(c, filing, tier_idx, year)` so every caller sees the same rounded, top-tier-aware threshold (`c['irmaa_base']` is MFJ tier 2 ⇒ `tier_idx=1`); use `_tk.irmaa_threshold_factor` only where a non-tier amount is scaled. `sheets_tax_capacity.py:68-76`: replace the mirror function body with `return _tk.irmaa_threshold_factor(c, year)`. MC builder (3611/3639/4989): delete `irmaa_rate`/`irmaa_factor`/`irmaa_index` and the `'irmaa_index_by_year'` and `'sampled_irmaa_inflation_geometric'` keys (thresholds now follow `inflation_index_by_year`); also remove `'irmaa_index_by_year'` from the key list at 3471. `data_io.py`: delete both `c['irmaa_inflator']` assignments. Remove the demo/fixture CSV row and the schema row; frontend: remove the field from whatever renders it (grep hits).
- [ ] **Step 4: Run** `pytest -m "not slow"`; fix tests that asserted the 2% inflator (`test_irmaa_guardrail_dedup_functional.py`, `test_ltcg_cross_implementation_equivalence_unit.py`, `test_roth_user_ui_render_fix.py`, `test_withdrawal_roth_ui_cleanup.py`, `test_active_input_recursion_guard_functional.py`, `test_after_tax_cap_gain_estate_functional.py`) by updating their expectations to CPI/Medicare indexing — each edit must state the reason. `npm test` — PASS.
- [ ] **Step 5: Commit** `refactor(irmaa): one indexing implementation; retire irmaa_annual_inflator`

### Task B3: Golden master — measure, verify one delta by hand, regen once

- [ ] **Step 1:** `python tools/regen_golden_master.py measure` — record deltas.
- [ ] **Step 2:** Hand-verify one year: pick the first demo year with a non-zero IRMAA surcharge from the projection output; with `n = year − 2025`, recompute `(round(partB×1.055^n, 1) + round(partD×1.0125^n, 1))×people×12` and the threshold `round(base×1.03^n / 2000)×2000` (MFJ) by hand; must match the engine to the cent.
- [ ] **Step 3:** `python tools/regen_golden_master.py regen --reason "#334 IRMAA: CPI thresholds from 2025 value year with statutory rounding and 2028 top-tier rule; Part B/D surcharges indexed by med_inf/partd_inf"`.
- [ ] **Step 4:** `pytest` (full) — PASS.
- [ ] **Step 5:** Commit `test(golden): repin for #334 IRMAA indexing`

---

## W-C — Spending Model consolidation (#338, #337)

### Task C1: "Annualized" everywhere

**Files:** `frontend/js/spending_dashboard.js:217-299`; `frontend/js/dashboard_decomp_spending_taxonomy.js:521,628,724`; `src/spending_tracker.py:1677-1680` (comments only); Test new `tests/frontend/annualized_label.test.mjs`

- [ ] **Step 1: Failing test**

```js
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test"; import assert from "node:assert";
test("no 'Annualized Actual' copy in frontend", () => {
  for (const f of readdirSync("frontend/js").filter((x) => x.endsWith(".js"))) {
    assert.ok(!/Annualized Actual/.test(readFileSync(`frontend/js/${f}`, "utf8")), f);
  }
});
```

- [ ] **Step 2:** `npm test -- tests/frontend/annualized_label.test.mjs` — FAIL.
- [ ] **Step 3:** Replace "Annualized Actual" → "Annualized" (and "Load Annualized Actuals" → "Load annualized amounts") in the listed files; `grep -rn "Annualized Actual" tests` and update pinned strings.
- [ ] **Step 4:** `npm test`; `pytest -m "not slow" -k spending` — PASS.
- [ ] **Step 5:** Commit `fix(spending): label is Annualized at every level (#337)`

### Task C2: Tracking-type accordion order and editable Housing/Wellness/Travel

**Files:** `frontend/js/dashboard_decomp_spending_taxonomy.js` (accordion renderer; grep "read-only reference" and "budgeted on its source page"); new `frontend/js/dashboard_decomp_spending_sources.js` (extracted Housing/Wellness/Travel field-group renderers); `frontend/js/dashboard.js` (grep `renderSpendingMortgageEvents|renderRetirementWellness|spending_travel`); Test new `tests/frontend/spending_model_accordion.test.mjs`

**Interfaces — Produces:** `TRACKING_TYPE_ORDER = ["Core Expenses","Housing","Wellness","Travel","Large Discretionary","Taxes","Business"]`; `housingCostGroupsHtml(rows)`, `wellnessGroupsHtml(rows)`, `travelGroupsHtml(rows)` exported from `dashboard_decomp_spending_sources.js`, each returning HTML of editable fields keyed by `row_index`.

- [ ] **Step 1: Locate.** `Grep` the three render functions and the "read-only reference" note; Read only those regions.
- [ ] **Step 2: Failing tests** — assert (a) accordion headers render in `TRACKING_TYPE_ORDER`; (b) the Housing/Wellness/Travel bodies contain `<input` elements whose `data-row-index` match the rows the old pages rendered for the demo fixture; (c) the string "read-only reference" is absent; (d) `sourceStepForRow()` for a housing-cost row returns `spending_core`.
- [ ] **Step 3: Implement** — extract the three renderers into the new module (moving lines out of `dashboard.js` pays the ratchet), call them from the accordion bodies, reorder by `TRACKING_TYPE_ORDER`, remove the read-only note. Rows for home value/mortgage balance and home sale/next steps/state are excluded here (they move in W-E).
- [ ] **Step 4:** `npm test`; `pytest -m "not slow"`; census + convert codemod; `measure` → `+0.00`.
- [ ] **Step 5:** Commit `feat(spending): one editable accordion per tracking type, in planning order`

### Task C3: Remove Housing and Wellness nav steps; redirects

**Files:** `frontend/js/dashboard.js` STEPS (lines ~55–140), `SECTION_REDIRECTS` (grep), `AUTOSAVE_STEPS`, `SUGGESTED_NEXT` in `dashboard_decomp_row_model.js`; Test `tests/frontend/strategy_section_redirects.test.mjs`, `tests/test_database_first_ui_refactor_functional.py::test_dashboard_top_level_groups`

- [ ] **Step 1:** Failing tests: `setStep("spending_mortgage_events")` and `setStep("retirement_wellness")` land on `spending_core` with the matching accordion open; neither id appears in `visibleSteps()`.
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Mark both steps `hidden: true` with `SECTION_REDIRECTS` entries `{ step: "spending_core", open: "Housing" | "Wellness" }`; remove from `SUGGESTED_NEXT`; update `helpLink`s that target them (grep).
- [ ] **Step 4:** `npm test`; `pytest -m "not slow"`; `npx playwright test tests/e2e/nav-integrity.spec.js`.
- [ ] **Step 5:** Commit `feat(nav): Housing and Wellness edit inside Spending Model`

### Task C4: Withdrawal Order parity, then removal

**Files:** `frontend/js/dashboard.js:337,2727,3580-3584`; `dashboard_decomp_row_model.js` (grep `withdrawal_order`); Test new `tests/frontend/withdrawal_order_parity.test.mjs`

- [ ] **Step 1:** Failing parity test: the set of `row_index` values rendered by the Withdrawal Order tab for the demo fixture ⊆ the union rendered by Optimize's sections (`rawRowsForStep("strategy_optimize")`).
- [ ] **Step 2:** Run. If it FAILS on specific rows, add those rows to the Optimize section that owns their topic (Withdrawal Sequencing by default) until it PASSES — do not delete the tab first.
- [ ] **Step 3:** Remove "Withdrawal Order" from the `spending_core` tab list at `dashboard.js:3584` and its renderer branch; redirect its dkey to `strategy_optimize`.
- [ ] **Step 4:** `npm test`; `pytest -m "not slow"`.
- [ ] **Step 5:** Commit `feat(spending): drop Withdrawal Order tab — every row lives on Optimize`

### Task C5: Actual Spending step; rename Reports & Review hub to Build & Results

**Files:** `frontend/js/dashboard.js:396-440` (STEPS for `reports_and_review`, `spending_dashboard`, `ytd_transactions`, `build_impact`); `dashboard.js:2357,3720` (group-name mapping); Test `tests/frontend/actual_spending_step.test.mjs`

**Interfaces — Produces:** step `{ id: "actual_spending", group: "Reports & Review", title: "Actual Spending" }` rendering two tabs, "This year" (ytd_transactions body) and "Analysis" (spending_dashboard body). Step `reports_and_review` keeps its id, `title: "Build & Results"`. The hidden step `build_impact` keeps its id and title "Impact & Build History". Every other hard-coded "Reports & Review" button label that means the hub (grep `data-step-id="reports_and_review"` in `frontend/js/*.js`: "Review Reports", "View Reports", "Review and Build", "Go to Build") is reworded to name "Build & Results".

- [ ] **Step 1:** Failing tests: visible nav group "Reports & Review" = `["Actual Spending", "Build & Results"]`; `setStep("ytd_transactions")` and `setStep("spending_dashboard")` land on `actual_spending` with the right tab; no STEPS entry has `group: "Reports"` (the hidden hub sub-pages `review`, `build_impact`, `detailed_results`, `plan_data_report` carry `group: "Reports & Review"`); `fieldFinderCategoryName("Reports & Review") === "Reports & Review"` with the `"Reports"` special case removed (`dashboard.js:2357`) and the `_eyebrow` list at `dashboard.js:3720` reduced to `["Reports & Review", "Settings"]`.
- [ ] **Step 2–4:** Implement, run `npm test`, `pytest -m "not slow"`, e2e nav-integrity.
- [ ] **Step 5:** Commit `feat(nav): Actual Spending under Reports & Review; hub renamed Build & Results`

---

## W-D — Large Discretionary and Spending Adjustments (#336, #335)

### Task D1: Large Discretionary one-time model + migration (backend)

**Files:** `src/spending_budget_resolver.py`, `src/ytd_tracking.py`, `src/ytd_projection_blend.py`, `src/projection_stages/spending_and_rmd.py` (grep `large_discretionary|extra_`); `src/data_io.py` (loader); new `src/large_discretionary.py`; Test new `tests/test_large_discretionary_one_time.py`

**Interfaces — Produces:**
`LD_CATEGORIES = ("Weddings","Large Gifts","Education","Auto","Other")`;
`load_ld_items(sectioned) -> list[LdItem]` where `LdItem(category:str, amount:float, year:int, note:str)`;
`migrate_repeatable(sectioned) -> tuple[list[LdItem], list[str]]` (items, notices);
`ld_budget_for_year(items, year) -> float`; `ld_cashflow_by_year(items) -> dict[int,float]`.

- [ ] **Step 1: Failing tests**

```python
from src.large_discretionary import LdItem, ld_budget_for_year, ld_cashflow_by_year, migrate_repeatable

ITEMS = [LdItem("Weddings", 60000, 2031, ""), LdItem("Auto", 45000, 2026, ""), LdItem("Large Gifts", 25000, 2029, "")]

def test_budget_counts_only_current_year_items():
    assert ld_budget_for_year(ITEMS, 2026) == 45000

def test_cashflow_lands_each_item_in_its_year():
    assert ld_cashflow_by_year(ITEMS) == {2031: 60000, 2026: 45000, 2029: 25000}

def test_repeatable_rows_expand_with_notice():
    sectioned = {"Large Discretionary Expenses": {
        "extra_1_type": "Vehicle", "extra_1_amount": "10000",
        "extra_1_start_year": "2026", "extra_1_end_year": "2037"}}
    items, notices = migrate_repeatable(sectioned)
    assert [i.year for i in items] == list(range(2026, 2038))
    assert all(i.category == "Auto" for i in items)
    assert any("Core category" in n for n in notices)  # 12 rows > 10
```

- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Implement `src/large_discretionary.py` (category map per spec §4), wire the loader to produce items, replace the annualization path for Large Discretionary in the YTD/budget resolvers with `ld_budget_for_year`, and feed `ld_cashflow_by_year` into the projection where `extra_N` amounts are applied today.
- [ ] **Step 4:** `pytest -m "not slow"`; `measure` — demo LD rows are one-time already, expected `+0.00`; any delta is investigated before proceeding.
- [ ] **Step 5:** Commit `feat(ld): large discretionary is one-time, never annualized (#336)`

### Task D2: Large Discretionary UI

**Files:** `frontend/js/dashboard_decomp_large_discretionary.js`; `input/demo/client_spending_taxonomy.csv` (retire LD groups: status `deleted`); Test `tests/frontend/large_discretionary.test.mjs`

- [ ] **Step 1:** Failing tests: pulldown options equal `LD_CATEGORIES` (Education labelled "Education (not 529-funded)"); rows have Amount, Year, Note, In budget; no start/end-year inputs; header shows no "Annualized"; caution line present when `education_funding_529` is on.
- [ ] **Step 2–4:** Implement; `npm test`; `pytest -m "not slow"`.
- [ ] **Step 5:** Commit `feat(ld): one section, five categories, In-budget column`

### Task D3: Spending Adjustments engine

**Files:** new `src/spending_adjustments.py`; `src/projection_stages/spending_and_rmd.py` (grep where per-category/tracking-type base spend is inflated); `src/data_io.py`; Test new `tests/test_spending_adjustments.py`

**Interfaces — Produces:** `Adjustment(category:str, start:int, end:int|None, pct:float)` where `category` is a category id or `"ALL:<tracking type>"`; `adjustment_factor(adjs, category_id, tracking_type, year) -> float`.

- [ ] **Step 1: Failing tests**

```python
import pytest
from src.spending_adjustments import Adjustment, adjustment_factor
A = [Adjustment("dining", 2035, None, -0.20), Adjustment("dining", 2042, None, -0.10),
     Adjustment("ALL:Travel", 2038, None, -0.50), Adjustment("home_aide", 2045, 2050, 0.40)]

def test_before_start_is_unchanged():
    assert adjustment_factor(A, "dining", "Core Expenses", 2034) == 1.0

def test_steps_compound_in_order():
    assert adjustment_factor(A, "dining", "Core Expenses", 2042) == pytest.approx(0.72)

def test_tracking_type_row_applies_to_every_category_in_it():
    assert adjustment_factor(A, "hotels", "Travel", 2040) == 0.5

def test_end_year_is_inclusive_then_reverts():
    assert adjustment_factor(A, "home_aide", "Wellness", 2050) == pytest.approx(1.4)
    assert adjustment_factor(A, "home_aide", "Wellness", 2051) == 1.0
```

- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** Implement; load `Spending Adjustments` rows (`adj_N_category/start_year/end_year/change_pct`); multiply each category's inflated spend by `adjustment_factor` in the projection.
- [ ] **Step 4:** `pytest -m "not slow"`; `measure` → `+0.00` (demo has no rows).
- [ ] **Step 5:** Commit `feat(spending): category step-downs/step-ups by year (#335)`

### Task D4: Spending Adjustments table UI

**Files:** new `frontend/js/dashboard_decomp_spending_adjustments.js`; accordion host in `dashboard_decomp_spending_taxonomy.js`; Test `tests/frontend/spending_adjustments.test.mjs`

- [ ] **Step 1:** Failing tests: pulldown = active categories of Core/Housing/Wellness/Travel + four "All ‹type›" options, none from Large Discretionary/Taxes/Business; add/edit/delete write `adj_N_*` rows; helper text shows the compounded result ("72% of today's level").
- [ ] **Step 2–4:** Implement; `npm test`.
- [ ] **Step 5:** Commit `feat(spending): Adjustments table in Spending Model`

---

## W-E — Housing restructure (#338)

### Task E1: Next Housing Move gates its inputs in the engine

**Files:** `src/module_catalog.py:715-729` (`engine_participation=True`, `degrades_without` on `housing_trajectory_comparison`, `state_residency`); `src/data_io.py` (home sale / next_housing_steps / state-over-time loaders; grep `home_sale_year|next_housing|state_residency`); Test new `tests/test_next_housing_move_gating.py`

- [ ] **Step 1: Failing test** — load the demo plan twice, with `housing_location_search` TRUE and FALSE; with FALSE assert `c` has no home-sale year, no next-step entries and a constant state for all years; the sectioned CSV data is byte-identical in both loads (values persisted).
- [ ] **Step 2:** Run — FAIL.
- [ ] **Step 3:** In the loader, when the module is off, skip those rows (treat as blank); flip catalog flags.
- [ ] **Step 4:** `pytest -m "not slow"`; `measure` → `+0.00` (demo switch is on).
- [ ] **Step 5:** Commit `feat(housing): Next Housing Move off ⇒ housing plan inputs ignored, kept`

### Task E2: Move housing plan inputs into the Optimize section; off-state note

**Files:** Next Housing Move section renderer (grep `housing_location_search` in `frontend/js/*.js`); `frontend/js/dashboard.js` housing page region (grep `home_sale_year`); `dashboard_decomp_row_model.js` `sourceStepForRow`; Test `tests/frontend/next_housing_move_section.test.mjs`, and read `tests/test_zip_screen_panel_functional.py` first (its assertions are an interface contract)

- [ ] **Step 1:** Failing tests: home sale, next steps 1–2, and state-over-time rows render in the Next Housing Move section; `sourceStepForRow` returns `strategy_optimize` for them; with the module off the section shows the note "Off — N saved fields not applied…" with an "Open Plan Features" link (no inline switch) and the values listed muted.
- [ ] **Step 2–4:** Implement; `npm test`; `pytest -m "not slow"`.
- [ ] **Step 5:** Commit `feat(housing): all housing planning lives in Optimize → Next Housing Move`

### Task E3: Home value and mortgage balance to Other Assets; HELOC step regroup

**Files:** `frontend/js/dashboard_decomp_assets_other.js`; STEPS entry `heloc_strategy` (`dashboard.js` ~line 138); Test `tests/frontend/other_assets_home.test.mjs`

- [ ] **Step 1:** Failing tests: Other Assets renders a "Primary home" group with home value and mortgage balance inputs; `heloc_strategy.group === "Investments & Property"`.
- [ ] **Step 2–4:** Implement; run suites.
- [ ] **Step 5:** Commit `feat(nav): home value on Other Assets; HELOC under Investments & Property`

---

## W-F — Nav regroup, reserve checking, workbook, consistency guard

### Task F1: Split Assets & Protection nav group

**Files:** `frontend/js/dashboard.js:146-190` STEPS `group:` values; `tests/test_database_first_ui_refactor_functional.py::test_dashboard_top_level_groups`

- [ ] **Step 1:** Update the pinned group list to §2 (failing first).
- [ ] **Step 2–3:** `holdings`, `assets_home_cash`, `assets_special`, `heloc_strategy` → `"Investments & Property"`; `annuity_death_benefits` → `"Insurance & Care"`; `estate` → `"Estate & Legacy"`; reorder STEPS so groups follow §2; delete the empty `"Housing & Property"` nav group.
- [ ] **Step 4:** `npm test`; `pytest -m "not slow"`; e2e nav-integrity.
- [ ] **Step 5:** Commit `feat(nav): topic-aligned asset groups`

### Task F2: Remove Reserve checking (#339)

**Files:** `frontend/js/dashboard.js:158,646-648,2633` (copy); row filter for `assets_home_cash` (grep `Other Assets.*Cash` / `"Cash"` in `rawRowsForStep`); `input/demo/client_assets.csv:15`; `reference_data/schema.csv`; `src/data_io.py` (import warning); Test new `tests/test_reserve_checking_removed.py`

- [ ] **Step 1: Failing tests** — (a) demo CSV has no `Other Assets,Cash,value` row; (b) loading a plan with that row = 25000 and no `_Checking` holdings emits a warning containing "25,000" and "Investment Holdings"; (c) Reserve Requirements page copy no longer mentions checking.
- [ ] **Step 2–4:** Implement; `pytest -m "not slow"`; `measure` → `+0.00` (value was never read).
- [ ] **Step 5:** Commit `fix(reserves): remove unused checking field (#339)`

### Task F3: Workbook Topic column

**Files:** `src/reporting/workbook_common.py` (section-index table built from `_SECTION_META`; grep its writer); Test `tests/test_workbook_topic_column.py`

- [ ] **Step 1:** Failing test: the section-index table for the demo build has a "Topic" column whose value for each sheet equals `CATALOG[module_key].domain`.
- [ ] **Step 2–4:** Implement; `pytest -m "not slow"`; `measure` → `+0.00`.
- [ ] **Step 5:** Commit `feat(workbook): Topic column in the section index`

### Task F5: Split People and Income (§9.2)

**Files:** `frontend/js/dashboard.js:20-50` STEPS `group:` values (`household`, `income_work`, `income_retirement` — confirm ids by grep `group: "People and Income"`); `SPENDING_COMPLETION`/`SUGGESTED_NEXT` in `dashboard_decomp_row_model.js` if they name the group; `tests/test_database_first_ui_refactor_functional.py::test_dashboard_top_level_groups`

- [ ] **Step 1:** Failing test: pinned group list begins `["Plan Status", "Household", "Income & Benefits", "Spending", …]`; the Household group holds only Household & People; Income & Benefits holds Work Income and SS/Pensions/Annuities; no STEPS entry has `group: "People and Income"`.
- [ ] **Step 2–3:** Change the three `group:` strings; `grep -rn "People and Income" frontend src tests` and update copy/pins (Field Finder order follows STEPS automatically).
- [ ] **Step 4:** `npm test`; `pytest -m "not slow"`; e2e nav-integrity.
- [ ] **Step 5:** Commit `feat(nav): Household utility group + Income & Benefits topic group`

### Task F6: Topic order within workbook sections (§9.1)

**Files:** `src/reporting/workbook_common.py` (`_derive_sheet_tables` — where `SHEET_LETTER_ORDER` is built from `letter_rank`); Test new `tests/test_workbook_topic_order.py`; existing `tests/test_sheet_table_consistency.py` (pins order)

**Interfaces — Consumes:** `DOMAINS`, `CATALOG[module_key].domain`, `SHEET_REGISTRY[name].letter_rank`. **Produces:** `sheet_topic(name) -> str` in `workbook_common.py` (module's domain, or `"Whole Plan"` when `module_key` is None).

- [ ] **Step 1: Failing tests**

```python
from src import module_catalog as mc
from src.module_catalog import SHEET_REGISTRY
from src.reporting import workbook_common as w

class _WB:
    sheetnames = list(SHEET_REGISTRY)

def _final_order():
    r = w.compute_final_sheet_renames(_WB())
    return sorted({v for k, v in r.items() if k in SHEET_REGISTRY})

def test_sheets_within_a_section_follow_topic_order():
    rank = {d: i for i, d in enumerate(mc.DOMAINS)}
    inv = {v: k for k, v in w.compute_final_sheet_renames(_WB()).items() if k in SHEET_REGISTRY}
    by_section = {}
    for final in _final_order():
        by_section.setdefault(final[0], []).append(rank[w.sheet_topic(inv[final])])
    for sec, ranks in by_section.items():
        assert ranks == sorted(ranks), sec

def test_no_final_tab_name_carries_a_legacy_number():
    import re
    for final in _final_order():
        assert re.match(r"^[1-5][A-Z]{1,2}\. ", final), final
```

- [ ] **Step 2:** `pytest tests/test_workbook_topic_order.py -v` — first test FAILS (e.g. section 2 starts with Roth Conversion, a Taxes sheet, before Social Security).
- [ ] **Step 3:** Add `sheet_topic()`; in `_derive_sheet_tables` sort each letter group by `(DOMAINS.index(sheet_topic(name)), letter_rank)` instead of `letter_rank` alone. Update the order pinned in `test_sheet_table_consistency.py`, stating the reason (#332 §9.1).
- [ ] **Step 4:** `pytest -m "not slow"`; `measure` → `+0.00` (order only).
- [ ] **Step 5:** Commit `feat(workbook): sheets ordered by topic within each answer-type section`

### Task F4: Cross-surface consistency guard

**Files:** new `tests/test_taxonomy_cross_surface_consistency.py`

- [ ] **Step 1: Write the test**

```python
import re, pathlib
from src import module_catalog as mc
from src.reporting.workbook_common import _SECTION_META

UTILITY = {"Plan Status", "Household", "Strategy", "Reports & Review", "Settings"}

def _nav_groups():
    src = pathlib.Path("frontend/js/dashboard.js").read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r'group:\s*"([^"]+)"', src)))

def _is_join(label):
    parts = [p.strip() for p in label.split("&")]
    topics_words = {w for d in mc.DOMAINS for w in (p.strip() for p in d.split("&"))}
    return all(p in topics_words for p in parts)

def test_every_nav_group_is_topic_join_or_utility():
    for g in _nav_groups():
        assert g in mc.DOMAINS or g in UTILITY or _is_join(g), g

def test_answer_type_labels_equal_workbook_sections():
    titles = [_SECTION_META[str(i)][0].split(". ", 1)[1] for i in range(1, 6)]
    assert titles == list(mc.ANSWER_TYPES)

def test_topic_label_never_reused_for_other_membership():
    # A nav group named exactly like a topic may only hold steps owned by modules of that topic
    src = pathlib.Path("frontend/js/dashboard.js").read_text(encoding="utf-8")
    for m in mc.CATALOG.values():
        if m.dashboard_step:
            hit = re.search(r'id:\s*"%s",\s*group:\s*"([^"]+)"' % re.escape(m.dashboard_step), src)
            if hit and hit.group(1) in mc.DOMAINS:
                assert hit.group(1) == m.domain, (m.dashboard_step, hit.group(1), m.domain)
```

- [ ] **Step 2:** Run — PASS (after W-A, W-C, W-E, F1, F5). If it fails, fix the surface, not the test.
- [ ] **Step 3:** Commit `test: cross-surface taxonomy consistency guard (#332)`

---

## Self-review notes

- Spec coverage: §1 → A1–A3, F3, F4; §2 → C3, C5, E3, F1, F5; §3 → C1–C5;
  §4 → D1–D2; §5 → D3–D4; §6 → A3 (backfill), A4, E1–E3; §7 → B1–B3; §8 → F2;
  §9.1 → F6; §9.2 → F5; §9.3–9.4 → B1; §9.5 → B0.
- Deliberate detail gap: W-C–W-F code for `dashboard.js` regions is written at
  each task's Locate step (see "Detail level").
