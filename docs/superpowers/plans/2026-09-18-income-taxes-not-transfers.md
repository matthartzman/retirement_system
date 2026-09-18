# Income Taxes Are Not Transfers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reclassify the `income_taxes` spending category out of `tracking_type = "Transfer"` into its own `"Taxes"` tracking type, so income-tax transactions flow through Actual Spending, the Spending Categories budget/actual/forecast table, and Spending Analysis like any other real expense — while still being excluded from the 30-year model's core spend-base sync (the retirement engine computes its own projected taxes; counting historical tax dollars there would double-count).

**Architecture:** `src/spending_tracker.py` is the single source of truth for the unified spending taxonomy (`tracking_type -> group -> category`) and is read by the Spending Categories page, Spending Analysis dashboard, and the Monthly Trajectory chart. `src/spending_budget_resolver.py` is a downstream adapter that decides what feeds the projection engine's spend base and optimization tiers. Both currently key off a fixed `_TRANSFER_NAMES = {"Transfer", "Transfers"}` set and a text-sniffing `_is_tax_actual()` heuristic to silently drop tax dollars before they ever reach any aggregation. The fix is: (1) self-healing taxonomy normalization that forces `income_taxes` onto a new `"Taxes"` tracking type regardless of what's stored in a household's CSV, (2) removal of the tax-specific drop logic now that taxes are correctly typed, (3) adding `"Taxes"` to the existing "excluded from spend base" allow-lists (the same lists that already carry Housing/Wellness/Business), and (4) frontend copy/label updates so the UI stops claiming taxes are excluded.

**Tech Stack:** Python (pytest), vanilla JS frontend, CSV-backed data model.

## Global Constraints

- Do not touch the retirement-engine tax calculators (`src/projection_stages/roth_conversion_and_agi_tax.py`, `src/after_tax.py`, `src/core.py`, etc.) — those compute *projected* future tax liability and are unrelated to this *actual/historical* transaction taxonomy change.
- Do not hand-edit any household's `client_spending_taxonomy.csv` (including `input/demo/` or test fixtures) to change `income_taxes`'s tracking type — rely on the self-healing normalizer in `_normalize_spending_group_assignment` so every existing plan (including the user's real one, which lives outside this repo) is fixed automatically on next load, with no migration script needed.
- Genuine internal-transfer categories (`401k_contribution`, `401k_match`, `buy`, `sell`, `cr_card_payment`, `credit_card_payment`, `hsa_contribution`, `transfer`) must remain excluded from spending totals exactly as today — only `income_taxes` moves.
- Every numeric assertion in an existing test that currently encodes "taxes are excluded" must be updated to the new expected totals shown in Task 2 below, not deleted.

---

### Task 1: Reclassify `income_taxes` off `Transfer` and stop dropping tax actuals

**Files:**
- Modify: `src/spending_tracker.py:338-341` (`TRACKING_TYPE_ORDER`)
- Modify: `src/spending_tracker.py:416-417` (`_EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE`, `_TIME_BOUNDED_TRACKING_TYPES`)
- Modify: `src/spending_tracker.py:533-604` (`_normalize_spending_group_assignment`)
- Modify: `src/spending_tracker.py:1316-1336` (delete `_is_tax_actual`)
- Modify: `src/spending_tracker.py:1339-1381` (`_actuals_by_taxonomy`)
- Modify: `src/spending_tracker.py:1729-1766` (`monthly_series`)
- Modify: `src/spending_tracker.py:1695-1726` (`spending_model` decisions text)
- Test: `tests/test_unified_spending_model_functional.py`
- Test: `tests/test_architecture_spending_coherence_functional.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: a `"Taxes"` tracking type that behaves like `"Core Expenses"` for aggregation (shows in `expense_actual`/`expense_annualized`, group rollups, `monthly_series`) but is excluded from `budget_derived_core_spend_base` and treated as lumpy (`no_annualize` defaults to `True`), matching the existing `real_estate_taxes` precedent. Later tasks (frontend) rely on the tracking type literally being the string `"Taxes"`.

- [ ] **Step 1: Add "Taxes" to the tracking-type order and exclusion sets**

In `src/spending_tracker.py`, change:

```python
TRACKING_TYPE_ORDER = [
    "Income", "Core Expenses", "Travel", "Large Discretionary", "Business",
    "Wellness", "Housing",
]
```

to:

```python
TRACKING_TYPE_ORDER = [
    "Income", "Taxes", "Core Expenses", "Travel", "Large Discretionary",
    "Business", "Wellness", "Housing",
]
```

and change:

```python
_EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE = {"Income", "Transfer", "Business", "Housing", "Wellness"}
_TIME_BOUNDED_TRACKING_TYPES = {"Travel", "Large Discretionary"}
```

to:

```python
_EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE = {"Income", "Transfer", "Business", "Housing", "Wellness", "Taxes"}
_TIME_BOUNDED_TRACKING_TYPES = {"Travel", "Large Discretionary", "Taxes"}
```

`Taxes` in `_EXCLUDED_TRACKING_TYPES_FOR_SPEND_BASE` keeps income-tax dollars out of the "Sync Actual Rate → 30-Year Model" core-spend-base figure (the retirement engine computes its own projected tax, so counting historical tax dollars there would double-count). `Taxes` in `_TIME_BOUNDED_TRACKING_TYPES` means its actual-to-date is reported as-is instead of being scaled by the days-elapsed annualization factor — quarterly/lump tax payments would otherwise wildly over- or under-state an annualized run rate, exactly like `real_estate_taxes` already does via `_TIME_BOUNDED_CATEGORY_IDS`.

- [ ] **Step 2: Self-heal any stored `income_taxes` row onto the new tracking type**

In `_normalize_spending_group_assignment` (`src/spending_tracker.py:533`), add a forced override near the top of the function, right after `tt`/`grp`/`cid`/`lab` are computed and before the `Food / Dining` consolidation block:

```python
    # income_taxes was originally promoted from the legacy Transfer/Financial
    # bucket during the unified-spending migration. Force it onto its own
    # "Taxes" tracking type regardless of what a household's CSV still has
    # stored, so it stops being silently excluded as a transfer. This is a
    # read-time normalization (like the entertainment_recreation rule below),
    # not a one-time migration script, so it self-heals every plan.
    if cid == "income_taxes":
        return "Taxes", "Taxes"
```

- [ ] **Step 3: Delete the tax-sniffing exclusion helper**

Remove the `_is_tax_actual` function entirely (`src/spending_tracker.py:1323-1336`). It existed only to catch tax payments that weren't properly typed; Step 2 fixes that at the source, so callers no longer need a text heuristic.

- [ ] **Step 4: Stop dropping tax actuals in `_actuals_by_taxonomy`**

In `_actuals_by_taxonomy` (`src/spending_tracker.py:1339`), change:

```python
            if tt in _TRANSFER_NAMES or _is_tax_actual(info, cid, raw_cat):
                continue
```

to:

```python
            if tt in _TRANSFER_NAMES:
                continue
```

Update the comment two lines above from:
```python
            # Spending Analysis is comprehensive for Income and expenses, but
            # still ignores transfers and tax payments. Income is positive;
            # expenses are shown as positive outflows.
```
to:
```python
            # Spending Analysis is comprehensive for Income and expenses,
            # including taxes; only internal transfers (401k/HSA
            # contributions, brokerage buys/sells, credit card payments) are
            # ignored. Income is positive; expenses are shown as positive
            # outflows.
```

- [ ] **Step 5: Stop dropping tax actuals in `monthly_series`**

In `monthly_series` (`src/spending_tracker.py:1752`), change:

```python
        if tt == "Income" or tt in _TRANSFER_NAMES or _is_tax_actual(info, cid or "", raw_cat) or _is_medical_cap_reference(cid or "", info):
            continue
```

to:

```python
        if tt == "Income" or tt in _TRANSFER_NAMES or _is_medical_cap_reference(cid or "", info):
            continue
```

Update the function's docstring (`src/spending_tracker.py:1730-1735`) from:
```
    """Monthly all-spending actual vs budget, excluding taxes and transfers.
    ...
    Income, transfers, and tax payments stay excluded.
    """
```
to:
```
    """Monthly all-spending actual vs budget, excluding transfers.
    ...
    Income and internal transfers stay excluded; income taxes are included
    like any other expense.
    """
```

- [ ] **Step 6: Update the `spending_model` decisions text**

In `spending_model` (`src/spending_tracker.py:1720-1721`), change:

```python
            "spend_base_includes": "Projection spend base excludes Income, Transfer, Business, Housing, Wellness, Travel, and Large Discretionary at every level; Monthly Trajectory separately includes all non-tax spending actuals.",
```

to:

```python
            "spend_base_includes": "Projection spend base excludes Income, Transfer, Business, Housing, Wellness, Taxes, Travel, and Large Discretionary at every level; Monthly Trajectory separately includes all non-transfer spending actuals, including taxes.",
```

- [ ] **Step 7: Update the two existing tests that encode the old "taxes excluded" behavior**

In `tests/test_unified_spending_model_functional.py`, rename `test_spending_analysis_includes_income_and_expenses_but_excludes_taxes` (line 147) to `test_spending_analysis_includes_income_expenses_and_taxes`, and change its final two assertions (lines 168-172) from:

```python
    dash = st.spending_dashboard(root, year=2026)
    assert dash["income_total"] == 10000
    assert dash["actuals_total"] == 150
    assert any(g["tracking_type"] == "Income" for g in dash["groups"])
    assert not any(g["tracking_type"] == "Transfer" for g in dash["groups"])
```

to:

```python
    dash = st.spending_dashboard(root, year=2026)
    assert dash["income_total"] == 10000
    assert dash["actuals_total"] == 650  # 100 groceries + 50 business + 500 income taxes
    assert any(g["tracking_type"] == "Income" for g in dash["groups"])
    assert any(g["tracking_type"] == "Taxes" for g in dash["groups"])
    assert not any(g["tracking_type"] == "Transfer" for g in dash["groups"])
```

(The fixture's `Transfer,Tax,income_taxes,...` taxonomy row at line 153 does NOT need editing — Step 2's normalizer forces it onto `"Taxes"` regardless of what the CSV says.)

In `tests/test_architecture_spending_coherence_functional.py`, rename `test_monthly_trajectory_includes_all_non_tax_spending` (line 69) to `test_monthly_trajectory_includes_all_non_transfer_spending_including_taxes`, and change its final assertions (lines 110-113) from:

```python
    series = monthly_series(tmp_path, 2026, total_budget=1200)
    assert series[0]['actual'] == 210.0
    assert series[0]['budget'] == 100.0
    assert all(m['actual'] == 0.0 for m in series[1:])
```

to:

```python
    series = monthly_series(tmp_path, 2026, total_budget=1200)
    assert series[0]['actual'] == 280.0  # 210 (groceries+mortgage+premium+travel+wedding+office) + 70 income taxes
    assert series[0]['budget'] == 100.0
    assert all(m['actual'] == 0.0 for m in series[1:])
```

(Credit Card Payment, $80, stays excluded — it's a genuine Transfer category and untouched by this change.)

- [ ] **Step 8: Run the targeted tests**

```bash
pytest tests/test_unified_spending_model_functional.py tests/test_architecture_spending_coherence_functional.py -v
```
Expected: PASS, including the two renamed tests.

- [ ] **Step 9: Commit**

```bash
git add src/spending_tracker.py tests/test_unified_spending_model_functional.py tests/test_architecture_spending_coherence_functional.py
git commit -m "fix(spending): stop treating income taxes as an excluded transfer"
```

**Estimated effort:** Sonnet, medium reasoning effort. ~15-25 tool-use turns (mostly targeted `Edit` calls plus two focused pytest runs). Context driver is `spending_tracker.py` itself (~1900 lines, but edits are all in the ~450-line window already identified above, so reads can stay scoped). Light-to-moderate relative to a 5-hour session — the main cost is re-running the two test files a few times if an edge case in the fixture data surfaces.

---

### Task 2: Keep the optimization/spend-base resolver consistent

**Files:**
- Modify: `src/spending_budget_resolver.py:19` (`EXCLUDED_FROM_SPEND_BASE`)
- Modify: `src/spending_budget_resolver.py:167` (`_TIER_UNCLASSIFIED_TRACKING_TYPES`)
- Test: none exist today that assert on `income_taxes`'s tier — add one.
- Test: `tests/test_...` (new, colocated with existing resolver tests — search `tests/` for `spending_budget_resolver` to find the right file before adding)

**Interfaces:**
- Consumes: the `"Taxes"` tracking type from Task 1.
- Produces: `resolve_spending_tier("income_taxes", "Taxes", "Taxes")` returns `None` (unclassified, same as `Income`/`Transfer`/`Business` today) so the planning-lever/optimization engine does not try to assign a cut-priority tier to tax dollars.

- [ ] **Step 1: Add "Taxes" to both exclusion sets**

In `src/spending_budget_resolver.py`, change:

```python
EXCLUDED_FROM_SPEND_BASE = {"Income", "Transfer", "Transfers", "Business", "Housing", "Wellness"}
```

to:

```python
EXCLUDED_FROM_SPEND_BASE = {"Income", "Transfer", "Transfers", "Business", "Housing", "Wellness", "Taxes"}
```

and change:

```python
_TIER_UNCLASSIFIED_TRACKING_TYPES = {"Income", "Transfer", "Transfers", "Business"}
```

to:

```python
_TIER_UNCLASSIFIED_TRACKING_TYPES = {"Income", "Transfer", "Transfers", "Business", "Taxes"}
```

Update the comment above `_TIER_UNCLASSIFIED_TRACKING_TYPES` (line 163-166) from:
```python
#: Tracking types that are never household lifestyle spending and are
#: therefore left untiered (Income/Transfer are cash-flow sources, not
#: spending; Business is tracked for reference only and is already excluded
#: from spend_base -- see EXCLUDED_FROM_SPEND_BASE above).
```
to:
```python
#: Tracking types that are never household lifestyle spending and are
#: therefore left untiered (Income/Transfer are cash-flow sources, not
#: spending; Business and Taxes are tracked for reference only and are
#: already excluded from spend_base -- see EXCLUDED_FROM_SPEND_BASE above).
```

- [ ] **Step 2: Add a regression test for the tier resolution**

Find the existing test file covering `resolve_spending_tier` (run `pytest --collect-only -q | grep -i tier` if unsure) and add:

```python
def test_income_taxes_are_untiered_like_income_and_transfer():
    from spending_budget_resolver import resolve_spending_tier
    assert resolve_spending_tier("income_taxes", "Taxes", "Taxes") is None
```

- [ ] **Step 3: Run the resolver's test file**

```bash
pytest tests/test_spending_budget_reconciliation_qc_regression.py -v
```
(Substitute the actual file name found in Step 2 if different.)
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/spending_budget_resolver.py tests/
git commit -m "fix(spending): exclude Taxes tracking type from spend-base and tier resolution"
```

**Estimated effort:** Sonnet, low reasoning effort. ~6-10 tool-use turns — two one-line set edits, one new 3-line test, one test run. Very light relative to a 5-hour session. Main risk (worth a quick manual look, not a broad search) is confirming which existing test file already imports `resolve_spending_tier` so the new test lands next to its siblings rather than in a new file.

---

### Task 3: Surface Taxes on the Spending Categories budget/actual/forecast table

**Files:**
- Modify: `frontend/js/dashboard_decomp_spending_taxonomy.js:559-579` (`trackingBudgetTypesForDomain`)
- Modify: `frontend/js/dashboard.js:550-556` (`spending_core` page help copy)

**Interfaces:**
- Consumes: the `"Taxes"` tracking type string from Task 1 (must match exactly).
- Produces: the "core" domain filter set includes `"Taxes"`, so `currentSpendingTreeForDomain("core")` (which every render of the Spending Categories page calls) stops silently dropping it.

- [ ] **Step 1: Add "Taxes" to the core domain's tracking-type filter**

In `trackingBudgetTypesForDomain` (`frontend/js/dashboard_decomp_spending_taxonomy.js:566-573`), change:

```javascript
    return [
      "Core Expenses",
      "Travel",
      "Large Discretionary",
      "Business",
      "Wellness",
      "Housing",
    ];
```

to:

```javascript
    return [
      "Core Expenses",
      "Taxes",
      "Travel",
      "Large Discretionary",
      "Business",
      "Wellness",
      "Housing",
    ];
```

- [ ] **Step 2: Update the Spending Categories page help copy**

In `frontend/js/dashboard.js:552`, change:

```javascript
    "This page is the comprehensive category model for income and expenses, excluding taxes/transfers. Projection spending controls, plus Travel and Large Items budgets, live here; Housing and Wellness detailed budget inputs stay on their own pages.",
```

to:

```javascript
    "This page is the comprehensive category model for income and expenses, including taxes but excluding internal transfers (401k/HSA contributions, brokerage buys/sells, credit card payments). Projection spending controls, plus Travel and Large Items budgets, live here; Housing and Wellness detailed budget inputs stay on their own pages.",
```

- [ ] **Step 3: Manually verify in the browser**

Start the app's dev server via the `run` skill or `.claude/launch.json`, open Spending Categories, import/confirm at least one `Income Taxes`-categorized transaction exists in `ytd_transactions.csv` for the active plan, and confirm a "Taxes" tracking-type section now renders with a nonzero YTD Actual.

- [ ] **Step 4: Commit**

```bash
git add frontend/js/dashboard_decomp_spending_taxonomy.js frontend/js/dashboard.js
git commit -m "feat(spending): show Taxes tracking type on the Spending Categories page"
```

**Estimated effort:** Sonnet, low reasoning effort. ~8-12 tool-use turns including one live browser check via `preview_start`. Light relative to a 5-hour session. The browser-verification step is the only part that isn't purely mechanical — budget a couple of extra turns if the plan's `input/` data has no income-tax transactions loaded yet and a fixture transaction needs adding first.

---

### Task 4: Fix Spending Analysis copy that claims taxes are excluded

**Files:**
- Modify: `frontend/js/spending_dashboard.js:161-164` (taxonomy card disclaimer)
- Modify: `frontend/js/spending_dashboard.js:187-230` (`renderSpendingSummary` all-in companion row + footnote)
- Modify: `frontend/js/spending_dashboard.js:232-236` (`renderSpendingBars` comment)
- Modify: `frontend/js/dashboard.js:571-577` (`spending_dashboard` page help copy)

**Interfaces:**
- Consumes: `d.actuals_total`, `d.annualized_total`, `d.actuals_total_all_in`, `d.annualized_total_all_in`, `d.annual_budget_total_all_in` (all already produced by `spending_tracker.py`; after Task 1 these "all-in" figures now differ from the plain totals only when a household has real dollars sitting under a genuine `Transfer` category, e.g. credit-card payments imported as transactions — not because of taxes).
- Produces: no backend changes; only label/copy accuracy.

- [ ] **Step 1: Fix the "How spending is organized" card**

In `frontend/js/spending_dashboard.js:161-164`, change:

```javascript
  html += '<div class="spend-taxonomy-card"><b>How spending is organized:</b> ' +
    '<span><b>Hierarchy</b> — Tracking Type → Group → Category;</span> ' +
    '<span><b>Included</b> — all Income and all expense Tracking Types;</span> ' +
    '<span><b>Excluded</b> — taxes and transfers.</span></div>';
```

to:

```javascript
  html += '<div class="spend-taxonomy-card"><b>How spending is organized:</b> ' +
    '<span><b>Hierarchy</b> — Tracking Type → Group → Category;</span> ' +
    '<span><b>Included</b> — all Income and all expense Tracking Types, including Taxes;</span> ' +
    '<span><b>Excluded</b> — internal transfers only.</span></div>';
```

- [ ] **Step 2: Rename the "All-In" companion row from taxes to transfers**

The all-in figures no longer differ from the main KPIs because of taxes (Task 1 already put taxes in the main KPIs) — they differ only when a household has actual dollars logged under a genuine `Transfer` category (credit card payments, brokerage buys/sells, 401k/HSA contributions). In `frontend/js/spending_dashboard.js:211-228`, change the comment block:

```javascript
  // Companion all-in figures (incl. all taxes, e.g. Income Taxes) -- kept as
  // a separate row rather than folded into the KPI tiles above, so the
  // Actual-vs-Budget comparison stays scoped consistently while still
  // surfacing the household's true out-the-door annual spend including taxes.
  // Only rendered when it actually differs from the KPI tiles above -- with
  // no taxes logged, annualizedAllIn===annualized and repeating identical
  // figures reads as a contradiction, not confirmation.
```

to:

```javascript
  // Companion all-in figures (incl. internal transfers, e.g. credit card
  // payments, brokerage buys/sells, 401k/HSA contributions) -- kept as a
  // separate row rather than folded into the KPI tiles above, so the
  // Actual-vs-Budget comparison stays scoped to real spending. Taxes are
  // already included in the KPI tiles above as of the Taxes tracking type
  // (see spending_tracker.py); this row now only ever differs when a
  // household has transfer-categorized transactions with real dollars.
  // Only rendered when it actually differs from the KPI tiles above.
```

and the two row labels:

```javascript
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(annualizedAllIn) + '</span><span class="spend-kpi-label">Annualized Actual, All-In (Incl. All Taxes)</span></div>';
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(budgetAllIn) + '</span><span class="spend-kpi-label">Annual Budget, All-In (Incl. All Taxes)</span></div>';
```

to:

```javascript
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(annualizedAllIn) + '</span><span class="spend-kpi-label">Annualized Actual, All-In (Incl. Transfers)</span></div>';
    html += '<div class="spend-kpi"><span class="spend-kpi-value">' + fmtSpend(budgetAllIn) + '</span><span class="spend-kpi-label">Annual Budget, All-In (Incl. Transfers)</span></div>';
```

and the footnote (line 227-228):

```javascript
  html += '<p class="small" style="margin:0 0 12px">' + d.days_elapsed + ' days elapsed &middot; annualization factor ' + (d.annualization_factor || 1).toFixed(2) + 'x &middot; the five KPI tiles above exclude income taxes and transfers (real estate taxes still count as Housing spending)' +
    (hasAllInDelta ? '; the All-In row adds income taxes back in' : '; no income tax or transfer transactions are logged this year, so the All-In totals would match the tiles above and are omitted') + '</p>';
```

to:

```javascript
  html += '<p class="small" style="margin:0 0 12px">' + d.days_elapsed + ' days elapsed &middot; annualization factor ' + (d.annualization_factor || 1).toFixed(2) + 'x &middot; the five KPI tiles above include income taxes and exclude only internal transfers' +
    (hasAllInDelta ? '; the All-In row adds transfer transactions back in' : '; no transfer transactions are logged this year, so the All-In totals would match the tiles above and are omitted') + '</p>';
```

- [ ] **Step 3: Fix the hierarchy-table comment**

In `frontend/js/spending_dashboard.js:233-234`, change:

```javascript
  // Full Tracking Type -> Group -> Category hierarchy from the taxonomy summary
  // (each level carries annualized actual + budget). Income is included; taxes/transfers are filtered in the backend.
```

to:

```javascript
  // Full Tracking Type -> Group -> Category hierarchy from the taxonomy summary
  // (each level carries annualized actual + budget). Income and Taxes are included; internal transfers are filtered in the backend.
```

- [ ] **Step 4: Fix the Spending Analysis page help copy**

`frontend/js/dashboard.js:571-577` currently doesn't mention exclusions explicitly, so no text change is strictly required there — read it after Steps 1-3 land and only touch it if it now reads inconsistently with the updated in-page copy.

- [ ] **Step 5: Manually verify in the browser**

With the same plan/data used in Task 3's Step 3, open Spending Analysis and confirm: the top KPI tiles' "This Year Expenses" total now includes the income-tax dollars, the "How spending is organized" card says "including Taxes," and the All-In row (if still shown) is now labeled about transfers, not taxes.

- [ ] **Step 6: Commit**

```bash
git add frontend/js/spending_dashboard.js frontend/js/dashboard.js
git commit -m "docs(spending): fix Spending Analysis copy after taxes stopped being excluded"
```

**Estimated effort:** Sonnet, low reasoning effort. ~8-12 tool-use turns, almost entirely mechanical string edits plus one browser check (can reuse the same preview session as Task 3). Light relative to a 5-hour session.

---

### Task 5: Full regression pass

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend test suite**

```bash
pytest -q
```
Expected: PASS. If `tests/test_frozen_sample_plan_golden_master_regression.py` or any other snapshot-style test fails because its expected numbers assumed income taxes were excluded, update that test's expected values the same way Task 1 Step 7 did — do not weaken the assertion or skip the test.

- [ ] **Step 2: Grep for any remaining stale "taxes excluded" claims**

```bash
grep -rn "exclud.*tax\|tax.*exclud" src frontend/js --include=*.py --include=*.js -i
```
Review each hit; anything left over should be about the *projection engine's* tax modeling (out of scope per Global Constraints), not the actual-spending taxonomy. Fix any that are actually about the taxonomy.

- [ ] **Step 3: Report results back to the user**

Summarize which tests changed, their old vs. new expected numbers, and confirm the browser checks from Tasks 3-4 passed.

**Estimated effort:** Sonnet or Opus (Opus if the golden-master snapshot needs non-trivial re-derivation), medium-to-heavy reasoning effort depending on how many snapshot-style tests need updating. This is the step most likely to run long: a full `pytest -q` on a codebase this size, plus a possible test-fix loop if the golden-master regression test needs new expected numbers. Budget this as **moderate-to-heavy** relative to a 5-hour ProPlan session — if the golden-master diff is large, stop and show the user the diff before changing expected values, rather than iterating blindly.

---

## Self-Review Notes

- **Spec coverage:** "shown in actual spending" → Task 1 (`_actuals_by_taxonomy`). "show up on cash flow similar to other expenses (budget/actual/forecast)" → Task 3 (Spending Categories page) + Task 1 (`monthly_series`, group rollups). "spending analysis too" → Task 1 (`expense_actual`/`expense_annualized`) + Task 4 (copy). "income taxes should not be transfers" → Task 1 Steps 1-2 (tracking-type reclassification) is the literal fix; Task 2 keeps the optimization/spend-base resolver from breaking as a side effect.
- **Not in scope, flagged for awareness, not action:** `src/ytd_tracking.py`'s `TAX_RE`/`classify_transaction` already tracks a separate `taxes` running total for the "This Year Performance" summary widget (a different code path from the taxonomy system this plan changes). It already treats tax as its own bucket rather than silently dropping it, so no change is needed there — but after this plan ships, it would be worth a follow-up check that its `taxes` figure and the new Spending Analysis "Taxes" tracking-type figure agree, since they're now both visible in the same UI.

**Note:** check `/usage` against these per-task estimates as you execute — Task 5 (full regression) is the one most likely to run over if the golden-master snapshot needs rework.
