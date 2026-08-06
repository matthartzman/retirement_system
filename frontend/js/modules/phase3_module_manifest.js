(function(){
  'use strict';
  window.RPPhase3Modules={
    schema:'phase3_frontend_module_manifest_v2',
    // Wave 6.4 (system review 2026-08-04, "leaves inward" ES-module
    // migration) converted every named leaf below to a real type="module"
    // script: spending_dashboard.js, dashboard_decomp_holdings.js (extracted
    // from dashboard.js itself), planning_workbench_ui.js (strategy),
    // dashboard_decomp_workbook_formatting.js + dashboard_decomp_state_inputs.js
    // (settings), reports_ui.js (detailed_results), navigation.js
    // (navigation), app_store.js + api_client.js + dashboard_decomp_build_lifecycle.js
    // (plan_state_build), plus dashboard_decomp_estate_insurance.js,
    // dashboard_decomp_supplemental_tables.js, dashboard_decomp_home_panels.js,
    // dashboard_source_truth_banners.js, dashboard_batch_assumption_edit.js
    // (not originally named leaves, converted for the same reason).
    extraction_order:['plan_state_build','detailed_results','navigation','spending','holdings','strategy','settings'],
    extraction_order_status:'complete',
    // dashboard_decomp_local_backups.js deliberately stays a classic script:
    // dashboard.js's own synchronous top-level boot chain
    // (checkAppStatus(true).then(...)) calls refreshLocalBackupStatus(),
    // which only that file defines -- converting it to a deferred module
    // would execute it AFTER dashboard.js's classic-script code instead of
    // before, reversing the load-order guarantee
    // test_dashboard_startup_race_and_script_order.py protects (a real
    // 2026-07-22 outage). dashboard_shared_helpers.js and
    // pywebview_bridge.js also stay classic: they're the FIRST scripts
    // loaded, and everything after them depends on their globals being
    // synchronously available at parse time, which a deferred module cannot
    // guarantee.
    remaining_classic_by_design:['dashboard_decomp_local_backups.js','dashboard_shared_helpers.js','pywebview_bridge.js'],
    // dashboard.js itself is the one leaf NOT converted. Unlike every file
    // above (self-contained, a handful to ~30 functions, exposed through
    // one namespace object or a short explicit list), dashboard.js declares
    // several hundred top-level functions, most referenced by its OWN
    // generated HTML via inline onclick="..." attributes scattered across
    // ~19,000 lines -- every one would need an individual window bridge, a
    // scale where a hand-driven grep-and-verify pass (the method used for
    // every leaf above) stops being a responsible way to change production
    // financial software. It also still has one classic-script consumer
    // (dashboard_decomp_local_backups.js reads activeStep/api/showMessage/
    // renderMain/esc as bare globals) that a conversion would need to
    // resolve first. Needs systematic tooling (an AST-based export/bridge
    // generator, not manual edits) and its own dedicated planning pass, not
    // a continuation of this wave's file-at-a-time approach.
    loaded_by:'dashboard_source_truth_banners.js',
    compatibility:'dashboard.js remains the public behavior owner while feature seams are extracted and tested.'
  };
})();
