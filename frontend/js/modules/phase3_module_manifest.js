(function(){
  'use strict';
  window.RPPhase3Modules={
    schema:'phase3_frontend_module_manifest_v3',
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
    // v3 (docs/superpowers/plans/2026-08-06-dashboard-js-ast-module-conversion.md):
    // dashboard.js itself is now a real type="module" script too. Unlike
    // every leaf above (self-contained, a handful to ~30 functions, exposed
    // through one namespace object), dashboard.js declares ~760 top-level
    // functions plus dozens of state variables, most referenced by its OWN
    // generated HTML via inline onclick="..." attributes scattered across
    // ~19,000 lines -- doing this by hand (the method used for every leaf
    // above) was correctly judged irresponsible for production financial
    // software at this scale. Instead, tools/js_codemod/census.mjs (an
    // AST-based cross-file reference finder, not a regex) and
    // convert_dashboard.mjs (an AST-based bridge generator) automated it:
    // every top-level function is bridged to window via a one-time
    // Object.assign value copy, EXCEPT the 2 that another leaf module
    // reassigns as a monkey-patch decorator chain (renderMain,
    // showStepHelp), which -- along with 42 externally read/written state
    // variables -- get a live get+set window accessor instead, so external
    // mutation is visible to dashboard.js's own internal references too.
    // Deliberately NO `export` keyword anywhere in the file: type="module"
    // alone (not any export) is what makes its top-level bindings private,
    // and several tests eval() dashboard.js (whole or by literal-text slice)
    // as a plain script, where `export` in any form is a SyntaxError.
    // dashboard.js still remains ONE file (~19,400 lines) after this pass --
    // this closed the "it's still classic" gap, not the "it's a monolith"
    // one. Splitting it into multiple cohesive modules by domain is a
    // SEPARATE, NOT-yet-scheduled future pass: that needs its own
    // dependency-graph analysis (which of the ~760 functions call which
    // others, to group them into non-circular modules) using the same
    // census/codemod tooling as a starting point, not a continuation of
    // this pass.
    loaded_by:'dashboard_source_truth_banners.js',
    compatibility:'dashboard.js remains the public behavior owner; its top-level surface is now bridged to window explicitly and tool-verified (tests/test_dashboard_js_module_bridge_regression.py) instead of implicitly global.'
  };
})();
