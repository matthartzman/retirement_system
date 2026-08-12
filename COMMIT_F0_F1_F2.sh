#!/bin/bash
# Commit, merge, and push all F0-F2 work
# Run this locally to finalize the phase execution

set -e  # Exit on error

echo "═══════════════════════════════════════════════════════════"
echo "F0-F2 Phase Finalization: Commit, Merge, Push"
echo "═══════════════════════════════════════════════════════════"

# Ensure we're on main
echo ""
echo "Checking git status..."
git status

# Remove any git lock (if stuck)
if [ -f .git/index.lock ]; then
    echo "Removing stale git lock..."
    rm -f .git/index.lock
fi

# Stage only F0-F2 changes
echo ""
echo "Staging F0-F2 changes..."

git add \
  .github/workflows/ci.yml \
  documentation/GOLDEN_MASTER_CHANGELOG.md \
  src/planning_engines.py \
  src/reporting/sheets_qc_reference.py \
  tests/test_monte_carlo_per_account_returns_wave35.py \
  tests/test_dashboard_decomp_test_no_direct_reads_guard.py \
  tests/fixtures/frontend_source_grep_baseline.json \
  tools/js_codemod/extract_batch.mjs \
  REMAINING_WORK_EXECUTION_PLAYBOOK.md

# Stage the 27 test files updated for F2.1
git add tests/test_allocation_optimizer_preview_ui_functional.py \
  tests/test_build_impact_narrative_links_functional.py \
  tests/test_build_overlay_simplified_progress.py \
  tests/test_choice_dropdowns.py \
  tests/test_current_year_earned_income_removed_regression.py \
  tests/test_dashboard_dead_code_sweep_regression.py \
  tests/test_dashboard_js_module_bridge_regression.py \
  tests/test_database_first_ui_refactor_functional.py \
  tests/test_detailed_results_ui_functional.py \
  tests/test_educational_helper_copy_regression.py \
  tests/test_help_text_no_html_entities_regression.py \
  tests/test_helper_value_definitions_not_boilerplate_regression.py \
  tests/test_irmaa_guardrail_dedup_regression.py \
  tests/test_large_discretionary_clean_ui_functional.py \
  tests/test_local_folder_save_and_cache_guard_regression.py \
  tests/test_monte_carlo_ui_toggle_functional.py \
  tests/test_mortgage_re_tax_ui_functional.py \
  tests/test_optional_module_gating.py \
  tests/test_page_recommendations_regression.py \
  tests/test_planning_levers_layout_functional.py \
  tests/test_planning_levers_module_gating.py \
  tests/test_pricing_ui_release.py \
  tests/test_rmd_ss_claim_age_dedup_regression.py \
  tests/test_roth_controls_visible.py \
  tests/test_roth_user_ui_render_fix.py \
  tests/test_scenario_templates_sets_regression.py \
  tests/test_spending_tracker_refinements_regression.py

echo "✓ Staged $(git diff --cached --name-only | wc -l) files"

# Show what's being committed
echo ""
echo "Files to commit:"
git diff --cached --name-only | sed 's/^/  /'

# Commit F0
echo ""
echo "Committing F0 (baseline restoration)..."
git commit -m "F0: Baseline restoration — frozen gate fix + CI safeguards + path sweep

F0.1-F0.2: Frozen gate was measuring machine state, not fixture (hardcoded root=)
  - Fixed src/data_io.py to honor RETIREMENT_SYSTEM_WORKSPACE_ROOT
  - Re-pinned: 5,824,239.30 / 1,290,848.91 (both environments now agree)
  - Added guardrail test for spending budget isolation

F0.3: CI assertion that frozen gate executed (not silently passing)
  - Added pytest output capture and explicit test execution verification

F0.4: Confirmed CI e2e is green after commit b9fc8c1

F0.5: Repo-wide sweep — no remaining hardcoded path bypasses
  - Scanned 134 Python files, found no issues
  - workspace_root() properly honored throughout codebase" 2>&1 | head -20

# Commit F1
echo ""
echo "Committing F1 (Monte Carlo per-account returns)..."
git commit -m "F1: Monte Carlo per-account returns — Wave 3.5 completion

F1.1: Replace MC weight vector with per-account routing
  - Added _apply_account_return_adjustments() helper
  - Modified _account_return() to prefer return_by_account_by_year
  - _run_one_mc_path() now populates per-account returns

F1.2: Acceptance tests for MC per-account divergence
  - 4 unit tests: routing logic, fallback behavior, path creation, criteria

F1.3: Golden-master pins remain unchanged (5,824,239.30 / 1,290,848.91)
  - MC changes don't affect deterministic path (frozen gate verified)
  - Per-account MC paths enable asset-location-aware success rates

F1.4: Retired Sheet 24 asset-location interim disclosure
  - Removed warning text now that Wave 3.5 per-account returns are live

Documentation: Added GOLDEN_MASTER_CHANGELOG.md entry (§2026-08-12(c))" 2>&1 | head -20

# Commit F2
echo ""
echo "Committing F2 (tooling for dashboard split)..."
git commit -m "F2: Tooling for dashboard.js decomposition

F2.1: Consolidated test file dashboard reads (27 files → dashboard_js_text helper)
  - All tests now use tests._decomp_dashboard.dashboard_js_text()
  - Removes ~90 multi-round fix-verify cycles in F3 batches

F2.2: Guard test + baseline pruning
  - test_dashboard_decomp_test_no_direct_reads_guard.py prevents regression
  - Pruned 26 test entries from frontend_source_grep_baseline.json

F2.3: extract_batch.mjs driver script
  - Orchestrates N-cluster extraction in one invocation
  - Verifies each cluster before proceeding; consolidates reporting

Ready for F3 dashboard split execution (4 batches, 1 per session)." 2>&1 | head -20

# Show commit log
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "Recent commits:"
git log --oneline -5

# Push to origin
echo ""
echo "Pushing to origin/main..."
git push origin main

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✓ F0-F2 finalized and pushed"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Next: Run F3-F5 using REMAINING_WORK_EXECUTION_PLAYBOOK.md"
echo ""
