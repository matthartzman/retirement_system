(function(){
  'use strict';
  window.RPPhase3Modules={
    schema:'phase3_frontend_module_manifest_v4',
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
    // v4 (docs/superpowers/plans/2026-08-06-dashboard-js-domain-module-split-SCOPE.md):
    // shared-core extraction, the first step that scope doc recommended.
    // Built an internal call-graph over dashboard.js's ~760 top-level
    // functions (jscodeshift-based, tools/js_codemod/extract_core.mjs) and
    // found 96.3% of them formed ONE connected component, glued together by
    // a shared "row" data model (section/norm/valOf/isEditable/fieldHtml/
    // rowsForStep/humanLabel/...) and app-shell orchestration (api/
    // showMessage/setStep/loadAll/saveAll/...) that nearly every domain
    // render function touches. Extracted the 172 functions with fan-in >= 3
    // (referenced by 3+ other top-level functions) into
    // frontend/js/dashboard_decomp_row_model.js -- named dashboard_decomp_*.js,
    // not dashboard_row_model.js, so existing tests that glob that pattern
    // for a multi-file "full dashboard source" read/smoke-exec pick it up
    // automatically. renderMain/showStepHelp stayed (still reassigned as a
    // monkey-patch chain by other leaf modules). dashboard.js dropped from
    // ~19,400 to ~15,300 lines. Domain clustering (the REST of the scope
    // doc's plan -- ~10-15 modules for the remaining ~586 functions) is
    // still not attempted: that's a separate pass on top of this one.
    // v5 (docs/superpowers/specs/2026-08-10-dashboard-js-split-codemod-design.md):
    // first DOMAIN cluster extracted, and the first one done by a general
    // tool rather than by hand. Built tools/js_codemod/extract_module.mjs: it
    // discovers byte offsets via the AST, splices the source string, then
    // proves the move was lossless by reading its own generated module back
    // off disk and reconstructing the original dashboard.js from it (deriving
    // the text from the OUTPUT is what makes that a real check and not a
    // tautology). Moved the 24-function assets cluster (liabilities, note
    // receivables, 529s, other-asset items) plus the 4 constant tables only
    // that cluster reads into frontend/js/dashboard_decomp_assets_other.js.
    // Loaded BEFORE dashboard.js like row_model.js: dashboard.js schedules its
    // boot work with queueMicrotask, whose checkpoint can fire before a later
    // module script evaluates, so a leaf loaded after it is not guaranteed to
    // have installed its window bridge in time. ~13 domain clusters remain;
    // re-run tools/js_codemod/find_clusters.mjs before each, since every
    // extraction changes the graph for the next one.
    // NOTE for anyone extending the codemods: extract_module.mjs and
    // find_clusters.mjs use @babel/parser directly, NOT jscodeshift.
    // jscodeshift's node.start/.end are only valid byte offsets on a CRLF
    // source -- on an LF checkout (Linux/CI) all 584 of dashboard.js's
    // top-level functions slice wrong. Do not "unify" them back.
    // v6 (same spec): SECOND domain cluster, extracted with the v5 tool
    // unchanged -- the point of building a general codemod was that the next
    // pass costs a dry run and a header file, not another bespoke edit. Moved
    // the 39-declaration spending cluster (taxonomy manager, category mapping
    // rules, domain budget tables, unified core-spending view) into
    // frontend/js/dashboard_decomp_spending_taxonomy.js; dashboard.js went
    // 14,822 -> 14,021 lines. Loaded BEFORE dashboard.js for the same
    // queueMicrotask reason as v5. No constants moved: unlike the assets
    // cluster, every constant table this one reads is shared with the rest of
    // dashboard.js. This cluster leans on the bridge harder than v5 did -- it
    // writes back to four dashboard.js `let`s (budgetLines, mappingRules,
    // rulesChanged, taxBudgetChanged) and reads thirteen more. Those bare
    // assignments only work because convert_dashboard.mjs emits set accessors:
    // module code is strict, and a strict-mode assignment to an unresolvable
    // identifier throws, so dropping a setter turns a silent global write into
    // a ReferenceError. The full dependency list is enumerated in the module's
    // own header (tools/js_codemod/headers/spending_taxonomy.txt).
    // This pass also added tools/js_codemod/finish_extraction.mjs, which runs
    // the whole deterministic follow-up (index.html wiring, census, bridge,
    // clusters report, manifest, ratchet) and verifies that every dashboard.js
    // binding the new module reaches back for is actually on the bridge, with
    // a setter where the module assigns to it. That last check is the one
    // nothing else in the pipeline performs.
    loaded_by:'dashboard_source_truth_banners.js',
    compatibility:'dashboard.js remains the public behavior owner; its top-level surface is now bridged to window explicitly and tool-verified (tests/test_dashboard_js_module_bridge_regression.py) instead of implicitly global.'
  };
})();
