# Phase D Tier 1C: sheets_projection.py Module Decomposition

## Overview
`src/reporting/sheets_projection.py` is the largest reporting module (~1500 lines) combining four distinct projection sheets with different concerns and dependencies. This plan outlines safe, low-risk extraction using the facade pattern.

## Current Structure

### File Statistics
- **Total lines**: ~1500 (measured with docstrings + helper functions)
- **Public functions**: 4
  - `build_sheet5(ws, c, rows)` — Net Worth Projection (lines 2-219)
  - `build_sheet6(ws, c, rows)` — Cash Flow Projection (lines 220-536)
  - `build_sheet7(ws, c, rows)` — Lifetime Tax Projection (lines 537-598)
  - `build_sheet8(ws, c, rows, mc_data=None)` — Charts Dashboard (lines 599+)

### Shared Dependencies
All four functions import from `workbook_common`:
- `section_title()`, `col_letter()`, `append_row()`, `bold()`, `pct_fmt()`, `num_fmt()`, etc.
- Excel formatting utilities, row/column helpers
- No circular dependencies detected between sheet builders

## Decomposition Strategy

### Approach: Facade + Physical Extraction
1. Create facades immediately (act as import boundaries)
2. Physically extract one sheet builder at a time
3. Update `workbook_builder.py` to import from facades
4. Test after each extraction to ensure no regressions

### Target Structure

```
src/reporting/
├── sheets_projection.py          (remains, empty after extraction)
│
├── sheets_projection_net_worth.py (NEW)
│   └── build_sheet5(ws, c, rows)
│       ~220 lines (lines 2-219 from current file)
│       Concern: Net worth accumulation, account tracking
│
├── sheets_projection_cashflow.py (NEW)
│   └── build_sheet6(ws, c, rows)
│       ~320 lines (lines 220-536)
│       Concern: Cash flow per account, withdrawal logic, collapsible groups
│
├── sheets_projection_tax.py      (NEW)
│   └── build_sheet7(ws, c, rows)
│       ~60 lines (lines 537-598)
│       Concern: Tax calculations by source
│
├── sheets_projection_charts.py   (NEW)
│   └── build_sheet8(ws, c, rows, mc_data=None)
│       ~300+ lines (lines 599+)
│       Concern: Chart creation, monte carlo visualization
│
└── sheets_projection_facade.py   (NEW, IMMEDIATE)
    └── Imports all four builders and re-exports
```

## Phase 1: Facade Creation (15 minutes)

Create `src/reporting/sheets_projection_facade.py`:

```python
"""Projection sheets facade — entry point for all projection sheet builders.

This module provides the public interface for projection sheet generation:
- build_sheet5: Net Worth Projection
- build_sheet6: Cash Flow Projection
- build_sheet7: Lifetime Tax Projection
- build_sheet8: Charts Dashboard

The actual builders are located in separate concern-specific modules:
- sheets_projection_net_worth.py
- sheets_projection_cashflow.py
- sheets_projection_tax.py
- sheets_projection_charts.py

This facade maintains backwards compatibility during module extraction.
"""

from .sheets_projection_net_worth import build_sheet5
from .sheets_projection_cashflow import build_sheet6
from .sheets_projection_tax import build_sheet7
from .sheets_projection_charts import build_sheet8

__all__ = ['build_sheet5', 'build_sheet6', 'build_sheet7', 'build_sheet8']
```

## Phase 2: Create Individual Builders (2-3 hours)

### Step 2A: sheets_projection_net_worth.py
- Copy `build_sheet5` and all its helpers from current file
- Ensure all imports work
- Test: `python -c "from src.reporting.sheets_projection_net_worth import build_sheet5"`

### Step 2B: sheets_projection_cashflow.py
- Copy `build_sheet6` and all its helpers
- Likely has most complexity (collapsible groups, account nesting)
- Test: `python -c "from src.reporting.sheets_projection_cashflow import build_sheet6"`

### Step 2C: sheets_projection_tax.py
- Copy `build_sheet7` and all its helpers
- Smallest extraction, ~60 lines
- Test: `python -c "from src.reporting.sheets_projection_tax import build_sheet7"`

### Step 2D: sheets_projection_charts.py
- Copy `build_sheet8` and all its helpers
- May have monte carlo visualization dependencies
- Test: `python -c "from src.reporting.sheets_projection_charts import build_sheet8"`

## Phase 3: Update Import Path (10 minutes)

### Modify src/reporting/workbook_builder.py

**Before:**
```python
from .sheets_projection import build_sheet5, build_sheet6, build_sheet7, build_sheet8
```

**After:**
```python
from .sheets_projection_facade import build_sheet5, build_sheet6, build_sheet7, build_sheet8
```

## Phase 4: Test & Verify (30 minutes)

### Tests to Run
```bash
# Import path test
python -c "from src.reporting.workbook_builder import build_sheet5, build_sheet6, build_sheet7, build_sheet8; print('✅ All imports work')"

# Integration test (full workbook generation)
python -m pytest tests/test_200_workbook_generation.py -xvs -k "test_full_workbook" 2>&1 | head -50

# Reconciliation tests
python -m pytest tests/test_150_immediate_next_actions.py -xvs
```

### Success Criteria
- [ ] All four sheet builders import successfully via facade
- [ ] No syntax errors in extracted modules
- [ ] Full workbook generates without errors
- [ ] All reconciliation tests pass
- [ ] No performance regression (workbook generation time)

## Dependencies & Risk Analysis

### Low Risk Factors
- **No circular imports**: Sheet builders only import from `workbook_common`
- **Stateless functions**: Each sheet builder is pure (takes ws, c, rows; returns None)
- **No shared state**: No module-level variables that span builders
- **Clear boundaries**: Each sheet has its own concern (net worth, cashflow, tax, charts)

### Potential Blockers
- **Helper functions**: Each sheet likely has local helpers (formatting, row building). Must extract with sheets.
- **workbook_common re-exports**: Ensure all formatting helpers used by extracted sheets are available
- **Monte Carlo data**: Sheet8 takes optional `mc_data` parameter. Must ensure data flow works post-extraction.

## Extraction Checklist

- [ ] Phase D Tier 1C plan document created ✅
- [ ] Facade created (sheets_projection_facade.py)
- [ ] Extract build_sheet5 to sheets_projection_net_worth.py
- [ ] Extract build_sheet6 to sheets_projection_cashflow.py
- [ ] Extract build_sheet7 to sheets_projection_tax.py
- [ ] Extract build_sheet8 to sheets_projection_charts.py
- [ ] Update workbook_builder.py import path
- [ ] Run integration tests
- [ ] Run reconciliation tests
- [ ] Commit all extractions
- [ ] Push to branch

## Timeline Estimate
- **Phase 1 (Facade)**: 15 minutes
- **Phase 2 (Extractions)**: 2-3 hours (30-45 min per sheet)
- **Phase 3 (Imports)**: 10 minutes
- **Phase 4 (Testing)**: 30-45 minutes
- **Total**: 3.5-4.5 hours

## Success Metrics
✅ **Module organization**: Projection sheets now have dedicated modules by concern
✅ **Code locality**: Related logic (e.g., all net worth logic) in single file
✅ **Maintainability**: Future changes to one sheet don't require scanning large combined file
✅ **Test coverage**: All four sheets testable in isolation
✅ **Zero regressions**: Workbook generation and reconciliation tests all pass

## Next Steps After Tier 1C Complete
→ **Phase D Tier 2**: Update `src/reporting/__init__.py` to export new facades
→ **Phase D Tier 2**: Create integration tests for each sheet builder in isolation
→ **Phase C Continuation**: Tackle remaining 5 interconnected shims (1-2, 4, 9) after Tier 1 complete
