# Phase D: Module Decomposition — Implementation Progress

**Status**: Starting parallel to Phase C completion  
**Date**: 2026-07-07  
**Focus**: Safe module splits using facade pattern → physical extraction

---

## Completed Foundation Work

### ✅ Facades Created (Imports Established)
- `src/planning_query_api.py` (127 lines) — Query API extraction ready
  - `project_scenario()`, `compare_scenarios()`, `optimize_roth_strategy()`
  - `monte_carlo_run()`, `sensitivity_run()`
  
- `src/reporting/sheets_summary_builder.py` — Executive summary facade
  - Imports: `build_sheet1`, `build_sheet2` from `sheets_summary.py`
  
- `src/reporting/sheets_allocation_helpers.py` — Allocation logic facade
  - 25+ helpers: allocation buckets, tax-aware trading, lot management
  
- `src/reporting/sheets_tax_reporter.py` — Balance sheet facade
  - Imports: `build_sheet3` from `sheets_summary.py`

---

## Phase D Extraction Tasks (By Priority)

### Tier 1: High-Impact, Lower-Risk (Start Immediately)

#### Task 1A: Extract planning_query_api (Already scaffolded)
**Goal**: Pure additive extraction — no changes to rebinding harness  
**Current State**: Facade created, functions aliased  
**Work**: Verify all projection/optimization functions accessible via new module  
**Files**: `src/planning_engines.py` → `src/planning_query_api.py` (facade + re-export)  
**Risk**: LOW — read-only wrapper, no core logic changes  
**Time**: ~30 min (testing)

**Criteria for Done**:
- All functions callable via new API
- Original planning_engines.py unchanged (harness intact)
- Tests pass (golden-master + query API tests)

---

#### Task 1B: Extract build_sheet1/build_sheet2 (Executive summary)
**Goal**: Separate UI/reporting from data preparation  
**Current State**: 2 functions in sheets_summary.py:890+  
**Work**: Physical extraction to sheets_summary_builder.py  
**Dependencies**: ~15 helpers, imports from workbook_common, sheets_summary helpers  
**Risk**: MEDIUM — many internal dependencies, formatting logic  
**Time**: ~2 hours (extraction + dependency mapping + testing)

**Dependency Map**:
```
build_sheet1/2 depends on:
  - write_cell(), write_hdr(), section_title() [workbook_common.py]
  - auto_fit_columns(), input_style() [workbook_common.py]
  - _workbook_pricing_source_label() [sheets_summary.py]
  - qc() [workbook_common.py QC/audit]
  - FMT_DOLLAR, FMT_PCT, color constants
  - datetime import
```

**Extraction Plan**:
1. Copy functions 1:1 to sheets_summary_builder.py
2. Add necessary imports
3. Update sheets_summary.py to import from new module
4. Verify imports work, tests pass
5. Move helper definitions if exclusive to build_sheet1/2

---

#### Task 1C: Extract reporting submodules (Allocation, Tax, Strategy)
**Goal**: Split 58K+ sheets_projection.py by concern  
**Current State**: Single 58K line file  
**Work**: Logical split into concern areas  
**Risk**: HIGH — complex interdependencies, needs deep analysis  
**Time**: ~6-8 hours (analysis + extraction + integration)

**Proposed Split**:
- `sheets_allocation.py` — Asset allocation, rebalancing, drift
- `sheets_tax.py` — Tax reporting, capital gains, strategy
- `sheets_strategy.py` — (Keep as is, most cohesive)
- `sheets_projection.py` — (Keep minimal core)

---

### Tier 2: Foundation Infrastructure (After Tier 1)

#### Task 2A: Update __init__.py for new imports
**Goal**: Re-export all facades consistently  
**Work**: Update src/reporting/__init__.py to export new modules  
**Time**: ~15 min

#### Task 2B: Integration tests for module boundaries
**Goal**: Verify facades don't break calling code  
**Work**: Add tests for cross-module function calls  
**Time**: ~45 min

---

### Tier 3: Infrastructure & Cleanup (After Tier 1 + 2)

#### Task 3A: Dashboard.js modularization
**Goal**: Split 1670+ line minified JS into feature modules  
**Concern**: Minified code, global state, event handlers  
**Approach**: 
1. De-minify (optional) or carefully extract named functions
2. Create modules by feature: income, spending, assets, strategy, reporting
3. Preserve global STEPS and renderMain() dispatch

#### Task 3B: data_io.py / spending_tracker.py splitting
**Goal**: Extract projection-specific logic from readers  
**Concern**: These are blocked until Phase C shim deletion completes  
**Status**: DEFERRED until Phase C Shims 1-11 deleted

---

## Parallel Phase C Work

### Remaining 8 Complex Shims (Being deleted in parallel)
- Shims 1, 2, 4: Spending model (interconnected)
- Shims 8-11: Data I/O (read-side fallbacks)
- UI terminology sweep (37 wellness→healthcare refs)

**Blocker for Phase D**: Once shims deleted, data_io.py / spending_tracker.py splits unblock

---

## Success Criteria

### Phase D Complete When:
1. ✅ All facades created (done)
2. ⏳ Tier 1A: planning_query_api tested & working
3. ⏳ Tier 1B: build_sheet1/2 extracted & re-imported
4. ⏳ Tier 2: __init__.py updated, module integration tests pass
5. ⏳ Tier 3A: Dashboard.js modularized (optional for MVP)
6. ⏳ Tier 3B: data_io.py / spending_tracker.py splits (blocks on Phase C)

### Test Gates
- All golden-master tests passing (6/6)
- New module import tests passing (TBD)
- No regressions in existing tests (648/649 baseline)

---

## Next Steps

**Immediate** (Next 30 min):
1. Verify planning_query_api.py façade works with tests
2. Begin extraction of build_sheet1/build_sheet2

**Short-term** (Next 2 hours):
1. Complete sheets_summary extraction
2. Refactor sheets_projection.py split planning

**Parallel**:
1. Continue Phase C shim deletion (user can run independently)
2. Once Phase C shims deleted, data_io.py extraction unblocks
