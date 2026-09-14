# Phase B: Test Suite Modernization — Triage Analysis

**Generated:** 2026-07-07  
**Status:** Ready for Opus 4.8 review + execution plan

## Problem Statement

121 of 154 test files read production source as text (`.read_text()` or `inspect.getsource()`) instead of testing behavior. This creates four problems:

1. **Renames break tests** — every identifier rename, helper-text rewrite, or module move requires updating string assertions
2. **False confidence** — a string can be present while the feature is broken (Phase A showed this: "Export CSV backup" shipped broken; "Download PDF" regression shipped)
3. **Refactor friction** — splitting large modules or reorganizing code now requires hunting down 120+ test files to update assertions
4. **Unclear intent** — the test passes if the string exists, not if the feature works

## Test Categorization (120 source-text-matching files)

| Category | Count | Pattern | Disposition |
|---|---|---|---|
| **JS string matching** | 71 | Assert on text in `dashboard.js`, `admin.js`, other frontend files | Convert to `node:test` for pure functions; delete if UI navigation only |
| **Route URL checks** | 28 | Assert route paths in `plan_routes.py`, `admin_routes.py`, etc. | Convert to call test client (`stdlib test client` in `desktop_api.py`) and assert response |
| **Sheet name assertions** | 6 | Verify workbook tab names, structure via `.read_text()` | Keep (minimal): these *do* verify real structure; improve to read workbook object model instead |
| **Comment/doc text** | 6 | Assert documentation/comments exist in source | Delete (no behavior value) |
| **Change-log only** | 1 | `test_29_roadmap_completion.py` — pure "did we finish roadmap items" | Delete |
| **Other patterns** | 8 | Miscellaneous (symlink checks, file structure) | Case-by-case triage |
| **Designated guards** | ~5 | e.g. `test_125_flask_free_runtime.py` (verifies Flask dependency removed) | Keep as-is; explicitly documented as anti-regression guards |

**Total to convert/delete:** ~113  
**Total to keep:** ~7

---

## Conversion Patterns by Category

### Pattern 1: JS String Matching → node:test (71 files)

**Current:** Reads `dashboard.js`, asserts text exists  
**Example:**
```python
def test_roth_objective_mode_weights():
    js = read("frontend/js/dashboard.js")
    assert "legacy_objective_mode" in js
    assert "estate_tax_objective_mode" in js
    assert "roth_optimize_terminal_weight" in js
```

**Converted to:** Extract pure JS function and test with `node:test`  
**Example:** `tests/frontend/dashboard_pure_functions.test.mjs`
```javascript
import { normalizeRothObjective } from '../../frontend/js/modules/roth_objective.mjs';
test('Roth objective mode has all required weight fields', () => {
  const result = normalizeRothObjective({ 
    legacy_objective_mode: 'BALANCED', 
    estate_tax_objective_mode: 'MONITOR' 
  });
  assert(result.weights.legacy !== undefined);
  assert(result.weights.estate !== undefined);
});
```

**Acceptance:** Test passes by calling the function and asserting on return value, not on source text.

---

### Pattern 2: Route URL Checks → Test Client (28 files)

**Current:** Reads `plan_routes.py`, asserts URL exists  
**Example:**
```python
def test_build_preflight_endpoint():
    routes = read("src/server/plan_routes.py")
    assert "'/api/build/preflight'" in routes or '"/api/build/preflight"' in routes
```

**Converted to:** Call route test client, assert response  
**Example:**
```python
def test_build_preflight_endpoint(test_client, sample_config):
    response = test_client.get('/api/build/preflight', json=sample_config)
    assert response.status_code in (200, 400)  # Endpoint exists and responds
    assert 'warnings' in response.json or 'errors' in response.json
```

**Test client:** `src/server/app_core.py` already exports `create_app()` for testing.  
**Acceptance:** Test actually calls the endpoint and verifies behavior.

---

### Pattern 3: Sheet Name Assertions → Keep + Improve (6 files)

**Current:** Reads workbook XML or parsed sheet text, asserts names  
**Behavior:** These *do* validate real structure, unlike patterns 1–2  
**Improvement:** Use `openpyxl.load_workbook()` to read workbook object model instead of text
**Example:**
```python
# Before (text matching)
def test_sheet_names():
    wb = read("output/retirement_plan.xlsx")  # reads as text
    assert "1. Executive Summary" in wb

# After (object model)
def test_sheet_names(built_workbook_path):
    from openpyxl import load_workbook
    wb = load_workbook(built_workbook_path)
    assert "1. Executive Summary" in wb.sheetnames
```

**Acceptance:** Uses real workbook parsing, not text search.

---

### Pattern 4: Comment/Doc Text → Delete (6 files)

**Current:** Asserts comments or documentation exist in source  
**Example:** `assert "see documentation/SYSTEM_REVIEW_AND_REFACTOR_PLAN.md Phase 5" in js`  
**Behavior:** No value; documentation comments don't affect feature behavior  
**Disposition:** Delete entirely; keep real behavior tests.

---

### Pattern 5: Change-Log Only → Delete (1 file)

**File:** `test_29_roadmap_completion.py`  
**Current:** Asserts roadmap items were completed  
**Behavior:** No value; historical record, not a forward test  
**Disposition:** Delete; archive in `documentation/archive/` if needed for records.

---

## Implementation Strategy

### Phase B-1: Design + Triage (Opus 4.8) — This Document

Review the categorization above and decide:
1. Are the 5 category boundaries correct, or do tests need different grouping?
2. Which tests in each category should be **kept** (anti-regression guards)?
3. What's the conversion template for each pattern (e.g., is one JS test file enough, or does every feature need its own test)?
4. Should routes be tested with the stdlib test client, or should tests call functions directly?

**Output:** Refined categorization + explicit keep/delete/convert list by test name.

### Phase B-2: Bulk Execution (Sonnet 5) — Per Refined Plan

1. Create `tests/frontend/` directory for `.mjs` test files
2. Convert pattern 1 (71 JS tests) → extract modules from `dashboard.js`, write 20–30 focused `.mjs` tests
3. Convert pattern 2 (28 route tests) → 5–8 test files calling test client for major routes
4. Keep + improve pattern 3 (6 sheet tests)
5. Delete patterns 4–5 (7 files)
6. Case-by-case triage for pattern 6 (8 files)

### Phase B-3: Verification

- Run `pytest tests/` — must pass (now with real behavior tests)
- Run `npm test` (Node runner for `.mjs` tests) — must pass
- CI must show fewer than 150 tests (down from 154 after deletions)
- `grep -r "\.read_text\|inspect.getsource" tests/` should return only designated guards

---

## Key Decisions Needed

**For Opus 4.8 to make:**

1. **JS module extraction strategy:** Should we pull each pure function into its own file (e.g. `roth_objective.mjs`), or group related functions by feature area?

2. **Route test coverage:** Should we test every route, or only the high-risk ones? (28 files suggests every route is tested currently.)

3. **Workbook fixtures:** The `conftest.py` `built_workbook_dir` fixture tries to build the workbook at session start — should this stay, or move to on-demand builds per test?

4. **Node.js test setup:** The CI already has `node:test` available. Should we add npm script for `npm test`, or integrate `.mjs` tests into `pytest` somehow?

5. **Phased approach:** Convert all 71 JS tests at once, or in batches (e.g. 20 per PR)?

---

## Reference: Test File List by Category

### JS String Matching (71 files)
`test_10_allocation_ui_backfill.py`, `test_105_educational_helper_copy.py`, `test_105_ytd_levers_dashboard.py`, `test_106_helper_value_definitions_not_boilerplate.py`, `test_107_ytd_account_currency_display.py`, `test_108_current_year_earned_income_removed.py`, `test_109_delete_scenario_refresh_validation.py`, `test_110_results_workbook_hidden_helper_rows.py`, `test_111_workbook_section_reference_consistency.py`, `test_112_budget_detail_authority_refinements.py`, `test_113_consolidated_mapping_currency_format.py`, `test_114_workbook_housing_wellness_cashflow.py`, `test_115_workbook_shared_scenario_output.py`, `test_116_workbook_annuity_policy_detail.py`, `test_117_workbook_home_sale_scenario_trigger.py`, `test_118_workbook_detailed_results_flow.py`, `test_119_ira_conversion_outflows.py`, `test_12_package_consolidation.py`, `test_120_earned_income_retirement_boundary.py`, `test_121_irs_tax_calc_rules.py`, `test_122_workbook_hidden_row_reconciliation.py`, `test_123_workbook_strategy_tabs_populated.py`, `test_124_architecture_spending_coherence.py`, `test_127_strategy_asset_service_schema_contract.py`, `test_128_ytd_drag_drop_category_update.py`, `test_129_plan_data_service_schema_extraction.py`, `test_130_spending_tracker_category_system.py`, `test_131_workbook_tab_audit_expense_rows.py`, `test_132_workbook_tax_detail_consistency.py`, `test_133_workbook_annuity_beneficiary_fields.py`, `test_134_scenario_withdrawal_tax_effect.py`, `test_135_workbook_section_structure_audit.py`, `test_14_allocation_policy_cleanup.py`, `test_140_scenario_comparison_result_export.py`, `test_141_plan_data_service_row_archive.py`, `test_142_system_configuration_page_access.py`, `test_143_import_preview_routes_ui.py`, `test_144_data_sync_plan_data_routes.py`, `test_145_plan_data_routes_export_import.py`, `test_146_local_backup_scheduler.py`, `test_147_page_recommendations.py`, `test_148_api_contracts_and_route_manifest.py`, `test_149_admin_routes_integration.py`, `test_15_covered_allocation_targets.py`, `test_150_batch_assumption_edit_tools.py`, `test_152_admin_page_module_extraction.py`, `test_154_admin_routes_system_configuration.py`, `test_155_strategy_asset_service_extraction.py`, `test_156_plan_data_budget_service_extraction.py`, `test_17_admin_system_config_compact.py`, `test_18_allocation_ui_tabs.py`, `test_19_allocation_optimizer_preview_ui.py`, `test_2_recommendations.py`, `test_20_allocation_ui_optimizer_disabled.py`, `test_24_admin_final_nav_and_acronyms.py`, `test_25_dashboard_refresh_build_button_ux.py`, `test_27_build_progress_globals_and_packaging.py`, `test_32_large_discretionary_clean_ui.py`, `test_5_allocation_optimizer_toggle.py`, `test_8_allocation_ui_mode_panels.py`, `test_80_detailed_results_ui.py`, `test_92_v10_roadmap_items_1_8_complete.py`, `test_96_database_first_ui_refactor.py`, `test_98_workbook_section_divider_no_unsupported_args.py`, `test_99_workbook_chart_titles_audit.py`

### Route URL Checks (28 files)
`test_106_ytd_account_setup_db_recovery.py`, `test_113_consolidated_mapping_currency_format.py`, `test_125_flask_free_runtime.py`, `test_126_service_extraction.py`, `test_137_roadmap_usability_surfaces.py`, `test_138_build_job_service_extraction.py`, `test_139_report_service_extraction.py`, `test_21_dashboard_ui_workbook_automation.py`, `test_22_dashboard_ui_build_product_ux.py`, `test_23_admin_ui_system_configuration.py`, `test_26_admin_ui_navigation_and_help_sidebar.py`, `test_30_admin_ui_service_consolidation.py`, `test_36_admin_ui_service_layer.py`, `test_37_admin_ui_workbook_audit.py`, `test_44_admin_ui_settings_and_scenario.py`, `test_45_admin_ui_workbook_save_recovery.py`, `test_47_admin_ui_scenario_detail.py`, `test_49_dashboard_ui_ytd_integration.py`, `test_50_dashboard_ytd_performance.py`, `test_63_ytd_workbook_reconciliation.py`, `test_70_spending_analytics_dashboard.py`, `test_71_spending_growth_and_forecasts.py`, `test_78_ytd_spending_growth.py`, `test_79_ytd_scenario_analysis.py`, `test_87_admin_workbook_recovery.py`, `test_88_planning_workbench_ui.py`, `test_89_planning_workbench_integration.py`, `test_90_v10_architecture.py`

### Other Categories (20 files)
**Sheet assertions (6):** `test_102_dashboard_charts_renamed_sheet_build.py`, `test_119_ira_conversion_outflows.py`, `test_16_tax_aware_rebalance.py`, `test_95_before_after_zero_rows_and_layout.py`, `test_97_workbook_five_area_tabs.py`, `test_100_workbook_numbered_section_tabs.py`  
**Comment text (6):** `test_10_allocation_ui_backfill.py`, `test_12_package_consolidation.py`, `test_14_allocation_policy_cleanup.py`, `test_156_plan_data_budget_service_extraction.py`, `test_8_allocation_ui_mode_panels.py`, `test_11_compact_allocation_selection.py`  
**Change-log only (1):** `test_29_roadmap_completion.py`  
**Other (8):** `test_124_architecture_spending_coherence.py`, `test_146_local_backup_scheduler.py`, `test_4_simplified_allocation.py`, `test_5_allocation_optimizer_toggle.py`, `test_3_modularization.py`, `test_151_frontend_module_extraction.py`, `test_147_snapshot_restore_contract.py`, `test_6_allocation_ui_styling_and_defaults.py`

---

## Next Steps

1. **Opus 4.8 reviews** this document and the test file list
2. **Opus decides:**
   - Confirm categorization or propose revisions
   - Which tests are anti-regression guards (keep as-is)
   - Conversion template for each pattern
   - Phasing strategy (all-at-once or batches)
3. **Sonnet 5 executes** per Opus's refined plan, one batch at a time
4. **Each PR** lands with before/after test counts and CI confirmation
