# Phase D: Module Decomposition & Consistency — Design Brief for Fable 5 & Opus 4.8

**Status:** Design phase — ready for architectural review  
**Risk Level:** HIGH — projection engine stability, test regression  
**Date:** 2026-07-07

---

## Executive Summary

This phase decomposes six oversized modules (5 Python, 1 JavaScript) and eliminates wildcard route imports. The work is high-risk because:

1. **Known trap**: `planning_engines.py` uses underscore-alias rebinding for deterministic mode — a previous split attempt broke this
2. **Golden-master regression**: Any change to projection engine inputs/logic silently breaks validation numbers
3. **Cascading dependencies**: Module splits expose hidden cross-module contracts; reordering can break things
4. **Test-suite brittleness**: Phase B (test modernization) must complete first — string-matching tests will break on every rename

---

## Current State — Oversized Modules

### Python Backend (5 modules to split)

| Module | Lines | Purpose | Split Target |
|--------|-------|---------|---------------|
| `planning_engines.py` | 2,710 | Core projection logic + dashboard query; deterministic mode + Monte Carlo | 800–1000 max (keep consolidated; split dashboard query layer) |
| `sheets_summary.py` | 2,685 | Excel workbook summary sheets; allocation helpers; tax summary | 700–900 each (split into summary builder + allocation calculator + tax reporter) |
| `data_io.py` | 2,392 | Plan CSV loading, validation, backwards-compat shims, schema parsing | 600–800 each (after Phase C removes shims: plan loader + validator + schema reader) |
| `spending_tracker.py` | 2,258 | Budget line consolidation, spending classification, category alias layer | 700–900 each (tracker + classifier + taxonomy resolver) |
| `deterministic_engine.py` | 1,689 | Year-by-year projection; tax computation; withdrawal logic | 900–1100 (split withdrawal policy + tax engine + cash-flow builder) |

### JavaScript Frontend (1 module to split)

| Module | Lines | Purpose | Split Target |
|--------|-------|---------|---------------|
| `dashboard.js` | 2,698 | Main UI, all steps, rendering, state, API calls | Per-step modules (already started: `navigation.js`, `planning_workbench_ui.js`, `reports_ui.js` extracted) |

### Route Assembly (wildcard imports to eliminate)

| File | Problem | Solution |
|------|---------|----------|
| `src/server/workbook_routes.py` | `from .app_core import *` | Explicit imports of: `app`, `_read_plan_data_file()`, `_write_plan_data_file()`, `_sqlite_db()`, `_sync_config_backends()` |
| `src/server/admin_routes.py` | `from .app_core import *` | Explicit imports (same set) |
| `src/server/plan_routes.py` | Already fixed (explicit imports) | ✓ No change needed |

---

## The Known Trap — Underscore-Alias Rebinding

### Background

`planning_engines.py` supports two projection modes (deterministic + Monte Carlo) by rebinding functions:

```python
# Line ~1147 (deterministic mode)
if is_deterministic:
    _advance_year = _advance_year_deterministic
    _sample_returns = _returns_fixed_seed
    # ... 8 more rebindings for taxes, withdrawals, etc.
else:
    _advance_year = _advance_year_monte_carlo  # stochastic version
    # ... etc.
```

**Why this is dangerous:** The underscore-prefixed functions (`_advance_year`, `_sample_returns`, etc.) are rebindable module-level names. A previous split attempt:
1. Moved deterministic logic to `deterministic_engine.py`
2. Tried to import and rebind: `from deterministic_engine import _advance_year_deterministic`
3. **Result:** The rebinding overwrote a local variable, not the module's reference, breaking projection logic

### Safe Split Strategy

**Do NOT split by mode.** Instead:
1. **Keep the rebinding harness in `planning_engines.py`** (lines 1100–1180)
2. **Split query/dashboard-interaction layer OUT** into `planning_query_api.py`:
   - `project_scenario()`, `compare_scenarios()`, `sensitivity_run()` → API layer
   - These stay in engine for now; split the call site instead
3. **Leave core projection (`_advance_year`, `_sample_returns`, taxes, withdrawals) in `planning_engines.py`**
4. Test: Run `pytest tests/test_2_recommendations.py` (golden-master) — must pass byte-for-byte

---

## Split Details by Module

### 1. `planning_engines.py` → Keep consolidated + extract query API

**Current state:** 2,710 lines; 4 public functions, 25 underscore helpers

**Split approach:**
- **Keep in `planning_engines.py`:** Projection harness, rebinding logic, core year-by-year loop, tax/withdrawal computations (1,800–1,900 lines)
- **Extract to `planning_query_api.py`:** 
  - `project()` wrapper
  - `compare_scenarios()` logic
  - Sensitivity/stress-test runners
  - Dashboard query convenience methods
  - (~800–900 lines)

**Why:** Avoids rebinding trap; keeps deterministic/MC mode transparent

**Test gate:** Golden-master byte-diff test (`tests/test_2_recommendations.py`) must pass unchanged

---

### 2. `sheets_summary.py` → Split 3 ways

**Current state:** 2,685 lines; 8 public functions; three logical groups

**Split approach:**

**A. `sheets_summary_builder.py` (~700 lines)**
- Excel sheet creation/formatting
- Section layout helpers
- Public functions: `build_executive_summary()`, `build_allocation_target_vs_actual()`, `build_tax_summary()`
- Dependencies: allocation helpers, tax data

**B. `sheets_allocation_helpers.py` (~600 lines)**
- Pie-chart pie labels, allocation rank, comparison helpers
- Public functions: `compute_allocation_deviations()`, `format_pie_labels()`
- Standalone; no other sheet dependencies

**C. `sheets_tax_reporter.py` (~500 lines)**
- Tax schedule builder
- Public functions: `build_tax_detail()`, `tax_bucket_summary()`
- Dependencies: taxes.py

**Advantages:**
- Allocation logic independently testable
- Tax reporter can be extended without touching summary builder
- Clear responsibilities

---

### 3. `data_io.py` → Split into 3 modules (after Phase C removes shims)

**Current state:** 2,392 lines; heavily burdened with 4 legacy shims

**After Phase C removes shims: ~1,800 lines**

**Split approach:**

**A. `plan_data_loader.py` (~700 lines)**
- CSV reading: `load_csv()`, `_read_section_subsection()`
- Struct building: `parse_client()` scaffolding
- Schema versioning gate (from Phase C): `_check_schema_version()`, `_migrate_v0_to_v1()` call site

**B. `plan_data_validator.py` (~500 lines)**
- Validation logic: `summarize_validation()`, per-field checks
- Error messages
- Dependency: plan_config.py

**C. `plan_data_schema.py` (~600 lines)**
- Data class definitions (currently inline)
- Field metadata
- Section/subsection tree
- Independent; can be imported by other modules without circular risk

**Sequencing:** Must happen AFTER Phase C (legacy shim removal)

---

### 4. `spending_tracker.py` → Split into 3 modules

**Current state:** 2,258 lines; 3 logical groups + legacy shims

**After Phase C removes shims: ~2,000 lines**

**Split approach:**

**A. `spending_tracker_core.py` (~800 lines)**
- Budget line consolidation: `consolidate_budget_rows()`, `_legacy_budget_to_unified()` (deletion in Phase C)
- Tracking type mapping (deletion in Phase C removes `_LEGACY_TRACKING_MAP`)
- Public: `SpendingBudget`, `SpendingTracker` classes

**B. `spending_classifier.py` (~600 lines)**
- Category classification: `classify_spending_line()`, category rules
- Taxonomy resolver: `resolve_category_id()`
- Standalone; testable in isolation

**C. `spending_alias_layer.py` (~400 lines)**
- Keyword-key alias exposure (formerly used by legacy reader; Phase C deletes)
- Post-Phase-C: Can be deleted or repurposed as terminology bridge
- Decision needed: Is this still used?

**Sequencing:** Can overlap with Phase C; Phase C deletions will shrink this

---

### 5. `deterministic_engine.py` → Split into 3 modules

**Current state:** 1,689 lines; three functional groups + tightly coupled to `planning_engines.py`

**Problem:** Even though it's smaller, it's import-heavy and can't be split without breaking rebinding (see "Known Trap" above)

**Recommendation:** Keep as-is for now; revisit in Phase E if complexity grows further

---

### 6. `dashboard.js` → Continue modular extraction

**Current state:** 2,698 lines; monolithic but extraction has started

**Existing extractions (already on main):**
- ✅ `navigation.js` — step navigation, AUTOSAVE_STEPS
- ✅ `planning_workbench_ui.js` — scenario builder
- ✅ `reports_ui.js` — results explorer
- ✅ `dashboard_batch_assumption_edit.js` — batch editor
- ✅ `dashboard_source_truth_banners.js` — validation banners

**Remaining dashboard.js (~1,500 lines):**
- Main render orchestration
- Per-step render functions (income, assets, insurance, spending, strategy, assumptions)
- Field group rendering, dependency sorting
- State management wrappers

**Split approach:**
- Per-step modules: `dashboard_income_step.js`, `dashboard_assets_step.js`, etc.
- Shared render helpers: `dashboard_render_utils.js`
- State management facade: `dashboard_state.js`

**Manifest coordination:** Use `phase3_module_manifest.js` to track module load order

---

## Key Decisions for Fable 5

**These must be decided before Opus 4.8 implementation begins:**

1. **planning_engines.py strategy:** Confirm "keep rebinding harness + extract query API" approach is safe?
2. **sheets_summary.py triple split:** Agree on boundaries (builder/allocation/tax)? Or merge allocation helpers back into builder?
3. **data_io.py timing:** Should Phase D begin before Phase C completes, or wait for Phase C to remove shims first?
4. **spending_tracker.py alias layer:** After Phase C deletes legacy shims, is `spending_alias_layer.py` still needed? Recommend deletion?
5. **deterministic_engine.py:** Keep as-is for now, or attempt split with clear constraints?
6. **dashboard.js modularization:** What's the module load-order manifest format? Per-step modules or by feature (income/assets vs render-utils)?

---

## Sequencing Constraints & Dependencies

### Hard sequencing rules (do not reorder)

1. **Phase B (test modernization) MUST complete first**
   - String-matching tests break on every rename
   - Once converted to behavior tests, splits won't break CI
   
2. **Phase C (legacy removal) SHOULD complete before `data_io.py` and `spending_tracker.py` splits**
   - Shim removal shrinks these files by 20–30%
   - Cleaner split boundaries once shims are gone
   - Alternative: Proceed in parallel if Opus 4.8 can handle it

3. **`planning_engines.py` must pass golden-master byte-diff test**
   - Any change to projection inputs/outputs invalidates numbers
   - Baseline must be re-run after split if outputs change
   - Fable 5 review mandatory

4. **dashboard.js splits can overlap with Python backend work**
   - No dependencies on Python module boundaries
   - Can proceed in parallel once phase3_module_manifest.js structure is agreed

### Golden-master regression guardrail

**MANDATORY for every commit touching:**
- `src/planning_engines.py`
- `src/projection_stages/`
- `src/taxes.py`
- `src/data_io.py`
- `src/spending_tracker.py`

```bash
pytest tests/test_2_recommendations.py --tb=short -v
```

**Acceptance:** Expected values match actual values byte-for-byte (within 2.0 delta for net worth, 1.0 for individual cases)

---

## Risk Assessment

### High risks

1. **Deterministic mode rebinding:** The underscore-alias strategy is fragile. Previous split attempt broke it.
   - **Mitigation:** Keep rebinding harness in planning_engines.py; don't move it

2. **Circular imports:** Splitting data_io.py could create import cycles (schema ↔ loader, validator ↔ schema)
   - **Mitigation:** Strict dependency graph review before splits; schema module must be import-safe (no circular references)

3. **Test brittleness:** If Phase B doesn't fully convert string-matching tests, every rename breaks CI
   - **Mitigation:** Phase B completion is hard blocker

4. **Golden-master regression:** Silent changes to projection numbers
   - **Mitigation:** Byte-diff test mandatory on every commit; review every baseline change in writing

### Medium risks

1. **Alias layer dependency:** `spending_alias_layer.py` may still be used post-Phase-C; uncertain if safe to delete
   - **Mitigation:** Grep for usage; add deprecation warning if kept

2. **Module load-order complexity:** dashboard.js module manifest could become unreadable if not carefully structured
   - **Mitigation:** Document manifest format clearly; validate in CI

---

## Acceptance Criteria

1. ✅ `planning_engines.py` split: golden-master byte-diff passes; rebinding logic intact
2. ✅ `sheets_summary.py` split into 3 modules with clear boundaries; no cross-imports
3. ✅ `data_io.py` split (after Phase C) into 3 modules; no circular imports
4. ✅ `spending_tracker.py` split (after Phase C) into 3 modules
5. ✅ Wildcard imports eliminated from `workbook_routes.py`, `admin_routes.py`
6. ✅ `dashboard.js` continued modularization per manifest; load order validated
7. ✅ `deterministic_engine.py` either split safely or kept as-is with written justification
8. ✅ All modules ≤ ~1,000 lines (except deliberately-consolidated engine files)
9. ✅ No test failures (golden-master byte-diff mandatory)
10. ✅ Splits documented in CLAUDE.md (boundaries, dependencies, load order)

---

## Timeline & Model Assignment

| Step | Work | Model | Days | Blocker? |
|---|---|---|---|---|
| 1 | Fable 5 review: confirm split strategies, answer 6 decisions | **Fable 5** | 0.5 | Must complete |
| 2 | Opus 4.8 detailed design (e.g., import graph, interface definitions) | Opus 4.8 | 1 | After Fable 5 |
| 3 | planning_engines.py split + golden-master validation | Opus 4.8 | 1.5 | Highest risk |
| 4 | sheets_summary.py triple split | Sonnet 5 | 1 | Parallel with step 3 |
| 5 | Wildcard import elimination from routes | Sonnet 5 | 0.5 | After Opus 4.8 pattern |
| 6 | data_io.py split (if after Phase C) | Opus 4.8 | 1 | Waits for Phase C |
| 7 | spending_tracker.py split (if after Phase C) | Opus 4.8 | 1 | Waits for Phase C |
| 8 | dashboard.js modularization continuation | Sonnet 5 | 1 | Parallel |
| 9 | Code review + golden-master final verification | **Fable 5** | 0.5 | Before merge |

**Total: ~6–7 days, 5–7 PRs, zero user-facing breakage if Phase B completes first**

---

## Reference: Dependency Graph

```
planning_engines.py (⚠️ TRAP: rebinding)
  ├→ projection_stages/deterministic_engine.py
  ├→ taxes.py
  └→ planning_config.py

sheets_summary.py → split into:
  ├→ sheets_summary_builder.py
  │   └→ sheets_allocation_helpers.py (split out)
  └→ sheets_tax_reporter.py
      └→ taxes.py

data_io.py → split into:
  ├→ plan_data_loader.py
  ├→ plan_data_validator.py
  └→ plan_data_schema.py (no imports outside std lib + dataclasses)

spending_tracker.py → split into:
  ├→ spending_tracker_core.py
  ├→ spending_classifier.py
  └→ spending_alias_layer.py (post-Phase-C: delete or repurpose?)

dashboard.js → continue modularization:
  ├→ dashboard_income_step.js
  ├→ dashboard_assets_step.js
  ├→ dashboard_insurance_step.js
  ├→ dashboard_spending_step.js
  ├→ dashboard_strategy_step.js
  ├→ dashboard_assumptions_step.js
  ├→ dashboard_render_utils.js
  └→ dashboard_state.js
```

---

## Out of Scope (Phase E+)

- Help-text architecture and curation (Phase E)
- Ruff expansion and mypy burn-down (Phase E)
- Accessibility pass (Phase E)
- New unit tests for optimization/market_data/secrets_store modules (Phase E)
- Service-pattern unification (cross-cutting, but Phase E priority)

---

## Next Steps

1. **Fable 5:** Review this brief, answer 6 key decisions, confirm sequencing
2. **Opus 4.8:** Perform detailed design (import graph, interface definitions) after Fable 5 approval
3. **Phase B & C:** Complete in parallel; Phase D waits for both (test modernization essential; Phase C optional but recommended for data_io.py/spending_tracker.py)
4. **Sonnet 5:** Begin sheets_summary.py split once Opus 4.8 pattern is established

---

**Related Files & Tests:**

- `documentation/SYSTEM_MODERNIZATION_PLAN.md` Section 5 (Phase D workstream)
- `src/planning_engines.py` lines 1100–1180 (rebinding harness)
- `tests/test_2_recommendations.py` (golden-master byte-diff gate)
- `src/server/workbook_routes.py`, `src/server/admin_routes.py` (wildcard imports to fix)
- `frontend/js/phase3_module_manifest.js` (module load-order tracker)
