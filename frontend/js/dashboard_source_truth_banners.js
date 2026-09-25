(function () {
  "use strict";
  // D3 (system review 2026-08-31): these banners previously stated storage
  // mechanics verbatim to end users (SQLite, "adapter", literal CSV
  // filenames) on every listed step, which answers no question a retiree
  // has. Steps that carried no actionable fact beyond "here's where this is
  // stored" (plan_data_report, all_assumptions, holdings, ytd_transactions,
  // spending_dashboard, spending_core, system_configuration,
  // detailed_results) had their banner removed outright -- several of those
  // duplicated guidance already shown elsewhere (spendingFlowHtml() covers
  // the spending steps' workflow order; addStaleAdvisorNotice() below
  // already shows a conditional, implementation-noun-free staleness warning
  // on detailed_results/build_impact/review when the plan is actually
  // stale). Only build_impact and review carried a genuine, always-relevant
  // "this reflects your last build" warning, so those two are kept and
  // rewritten in outcome language instead.
  const SOURCE_TRUTH_STEPS = {
    review:
      "These reports reflect your last successful build, not live edits. Save and rebuild after changes to keep them current.",
    build_impact:
      "This shows the impact of your last build. Rebuild after edits to see updated numbers.",
  };
  // ytd_transactions, spending_dashboard, and review can no longer actually
  // be activeStep (navigation.js's WORKSPACE_TAB_REDIRECTS/REPORTS_REDIRECT_IDS
  // redirect all three elsewhere before activeStep is ever set) -- listed
  // here as the values spendingFlowHtml()'s stage buttons still navigate TO
  // and can still highlight AS, via effectiveSpendingStage() below, not as
  // literal activeStep values this array is tested against.
  //
  // reports_and_review (Reports & Review) is deliberately excluded (#320):
  // that page already has its own build/review flow (Compare & Decide ->
  // Build Reports -> View/Download), so surfacing the spending-input flow
  // guide there too is out of place, not merely redundant.
  const SPENDING_STEPS = ["spending_core", "actual_spending"];
  // Glossary terms come from the canonical source (src/glossary.py, served by
  // GET /api/glossary and merged into dashboard.js's ACRONYM_DEFINITIONS at
  // startup). This file previously carried its OWN third copy, which the
  // earlier consolidation missed -- its IRMAA wording had already drifted from
  // canonical, and PTI/QDRO/ACA existed only here so /api/glossary could never
  // reconcile them. Those four are now in src/glossary.py.
  function glossaryTerms() {
    return (typeof ACRONYM_DEFINITIONS !== "undefined" && ACRONYM_DEFINITIONS) || {};
  }

  const MODULE_MANIFEST = {
    schema: "dashboard_phase3_module_manifest_v1",
    extracted_modules: [
      "plan_state_build",
      "detailed_results",
      "navigation",
      "spending",
      "holdings",
      "strategy",
      "settings",
    ],
    active_overlay: "roadmap_steps_1_11",
    public_hooks: [
      "renderMain",
      "showStepHelp",
      "setStep",
      "saveAll",
      "runBuild",
    ],
  };
  window.RPDashboardRoadmap11 = Object.assign(
    {},
    window.RPDashboardRoadmap11 || {},
    { manifest: MODULE_MANIFEST, glossary: glossaryTerms() },
  );

  function escHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }
  function currentStep() {
    try {
      return activeStep || "start";
    } catch (_e) {
      return "start";
    }
  }
  function byId(id) {
    return document.getElementById(id);
  }
  function mainPane() {
    return byId("mainPane");
  }
  function safeRows() {
    try {
      return Array.isArray(rows) ? rows : [];
    } catch (_e) {
      return [];
    }
  }
  function visibleStepIds() {
    try {
      return visibleSteps().map(function (s) {
        return s.id;
      });
    } catch (_e) {
      return [];
    }
  }
  function callStep(id) {
    try {
      setStep(id);
    } catch (_e) {}
  }

  function sourceTruthHtml(step) {
    const text = SOURCE_TRUTH_STEPS[step];
    if (!text) return "";
    return (
      '<div class="source-truth-label" data-roadmap11="source-of-truth"><b>Source of truth:</b> ' +
      escHtml(text) +
      "</div>"
    );
  }
  function insertAfterPaneHead(html, marker) {
    const pane = mainPane();
    if (
      !pane ||
      !html ||
      pane.querySelector('[data-roadmap11="' + marker + '"]')
    )
      return;
    const head = pane.querySelector(".pane-head");
    if (head) {
      head.insertAdjacentHTML("afterend", html);
    } else {
      pane.insertAdjacentHTML("afterbegin", html);
    }
  }

  // Resolves which of the four workflow stages the user is effectively on.
  // step (activeStep) can only ever be "spending_core" or
  // "reports_and_review" now that every other stage id redirects on real
  // navigation (navigation.js) -- so distinguishing Categories/Transactions/
  // Spending Analysis while on spending_core means checking the current
  // workspace tab instead of comparing step directly.
  function effectiveSpendingStage(step) {
    // #338 W-C: Transactions/Spending Analysis are actual_spending's tabs.
    if (step === "actual_spending") {
      const tab =
        typeof getStrategyTab === "function" ? getStrategyTab("actual_spending") : "";
      return tab === "Analysis" ? "spending_dashboard" : "ytd_transactions";
    }
    if (step === "reports_and_review") return "review";
    return step;
  }

  function spendingFlowHtml(step) {
    if (!SPENDING_STEPS.includes(step)) return "";
    const stage = effectiveSpendingStage(step);
    const labels = [
      ["spending_core", "Categories"],
      ["ytd_transactions", "Transactions"],
      ["spending_dashboard", "Spending Analysis"],
      ["review", "Sync / Build"],
    ];
    let html =
      '<div class="spending-flow-guide" data-roadmap11="spending-flow"><div><b>Recommended spending flow</b><span>Categories → Transactions → Spending Analysis → Sync Actual Rate → Build</span></div><div class="spending-flow-buttons">';
    labels.forEach(function (pair) {
      html +=
        '<button type="button" class="btn ' +
        (pair[0] === stage ? "primary" : "") +
        '" data-step-id="' +
        pair[0] +
        '">' +
        pair[1] +
        "</button>";
    });
    html += "</div></div>";
    return html;
  }

  function reviewCloseoutHtml(step) {
    if (step !== "start" && step !== "review") return "";
    if (document.querySelector(".review-closeout")) return "";
    // Don't show when no plan is loaded — no data to close out
    try {
      if (!planLoaded) return "";
    } catch (_e) {
      return "";
    }
    let reason = "";
    try {
      reason =
        localStorage.getItem("retirement.first_run.skip_reason.v1") || "";
    } catch (_e) {}
    // Find first incomplete workflow step so button goes to data entry, not straight to R&R
    const WORKFLOW_ITEMS = [
      {
        steps: ["household_people", "household_timing"],
        next: "household_people",
      },
      { steps: ["income_work", "income_retirement"], next: "income_work" },
      {
        steps: [
          "spending_core",
          "retirement_wellness",
          "spending_mortgage_events",
          "spending_travel",
          "spending_travel_extras",
          "ytd_transactions",
          "spending_dashboard",
          "actual_spending",
        ],
        next: "spending_core",
      },
      {
        steps: [
          "holdings",
          "assets_home_cash",
          "insurance_ltc",
          "annuity_death_benefits",
          "assets_special",
          "estate",
        ],
        next: "holdings",
      },
      {
        steps: [
          "planning_levers",
          "roth_conversion",
          "allocation_assets",
          "allocation_policy",
          "withdrawal_strategy",
          "state_residency",
          "heloc_strategy",
          "entity_charitable",
        ],
        next: "distribution_strategy",
      },
      {
        steps: [
          "monte_carlo_options",
          "scenarios",
          "survivor_stress",
          "ltc_stress",
          "divorce_options",
        ],
        next: "monte_carlo_options",
      },
    ];
    let firstIncompleteStep = "reports_and_review";
    try {
      for (var i = 0; i < WORKFLOW_ITEMS.length; i++) {
        const st = checklistItemStatus(WORKFLOW_ITEMS[i].steps);
        if (st.cls !== "done") {
          firstIncompleteStep = WORKFLOW_ITEMS[i].next;
          break;
        }
      }
    } catch (_e) {}
    const btnLabel =
      firstIncompleteStep === "reports_and_review"
        ? "Open Build & Results"
        : "Continue Data Entry";
    return (
      '<div class="first-run-closeout" data-roadmap11="first-run-closeout"><b>First-run closeout</b><span>Required sections should be complete before advisor-ready reports. Optional skips should include a reason.</span><label class="small">Optional skip reason <input id="firstRunSkipReason" value="' +
      escHtml(reason) +
      '" placeholder="Example: LTC quote pending" oninput="window.RPDashboardRoadmap11.saveSkipReason(this.value)"></label><button type="button" class="btn primary" data-step-id="' +
      escHtml(firstIncompleteStep) +
      '">' +
      escHtml(btnLabel) +
      "</button></div>"
    );
  }

  function recommendationsHtml(step) {
    const recs = [];
    if (step === "state_residency") {
      recs.push([
        "Review residency timing",
        "State tax assumptions can change lifetime tax, estate exposure, and Roth conversion headroom.",
        "state_residency",
      ]);
      recs.push([
        "Model a move as a scenario",
        "Use Scenarios for temporary or future state changes instead of overwriting the base plan.",
        "scenarios",
      ]);
    }
    if (step === "withdrawal_strategy") {
      recs.push([
        "Check taxable bridge capacity",
        "Withdrawal order can create or close Roth-conversion windows before RMDs begin.",
        "withdrawal_strategy",
      ]);
      recs.push([
        "Coordinate with IRMAA guardrails",
        "Sequencing, Roth conversions, and Medicare thresholds should be reviewed together.",
        "roth_conversion",
      ]);
    }
    if (!recs.length) return "";
    let html =
      '<div class="page-recommendations roadmap11-recommendations" data-roadmap11="expanded-recommendations"><h3>Recommendations to review</h3>';
    recs.forEach(function (r) {
      html +=
        '<div class="recommendation-card"><b>' +
        escHtml(r[0]) +
        "</b><p>" +
        escHtml(r[1]) +
        '</p><button type="button" class="btn" data-step-id="' +
        escHtml(r[2]) +
        '">Open source input</button></div>';
    });
    html += "</div>";
    return html;
  }

  function planDataPreviewHtml(step) {
    if (step !== "plan_data_report") return "";
    return '<div class="plan-data-preview-tools" data-roadmap11="plan-data-preview"><b>Plan Data Summary preview</b><span>Print or save this input packet as PDF before sharing it.</span><button type="button" class="btn primary" onclick="window.print()">Print / Save PDF</button><button type="button" class="btn" onclick="window.RPDashboardRoadmap11.expandPrintableSections()">Expand all sections</button></div>';
  }

  function detailedResultsEnhancements(step) {
    if (step !== "detailed_results") return "";
    return '<div class="detail-readability-tools" data-roadmap11="detail-readability"><b>Workbook readability</b><span>Use sheet search, summaries, and quick jumps to inspect important rows before sending reports.</span><input id="roadmap11DetailJumpSearch" class="search" placeholder="Jump to row text…" oninput="window.RPDashboardRoadmap11.filterDetailJump(this.value)"><div id="roadmap11DetailJumps" class="detail-jump-list"></div></div>';
  }

  // #329 §4.7 (W10b): row badge + section banner for values that are live
  // optimizer output, built on this file's own SOURCE_TRUTH_STEPS/badge
  // machinery rather than a second, differently-styled disclosure system --
  // exactly what §4.7 warns against. Scoped to the three "policy adoption
  // (mode switch)" optimizers §4.3 names (Roth Conversion, HSA Drawdown,
  // Asset Allocation): each has a single mode/policy row whose value decides
  // whether the engine mutates the projection from a candidate it computed,
  // continuously, on every build (§4.1a) -- the exact behavior this
  // disclosure exists to name. Scalar/structural/trade-list optimizers
  // (Social Security, Withdrawal Sequencing, Housing, Charitable Giving,
  // Harvesting) have no such switch, so they are out of scope by
  // construction, not by omission.
  //
  // Each entry's `isLive()` reuses the exact classification its own input
  // renderer already computes (rothPolicyIsOptimizer, hsaWithdrawalModeValue,
  // allocationModeIsComputed) rather than a second copy of the same string
  // match -- the hand-maintained-twin failure #329/#330 exist to end.
  const LIVE_OPTIMIZER_MODES = [
    {
      key: "roth_conversion",
      title: "Roth Conversion",
      rowLabel: "roth_conversion_policy",
      isLive: function () {
        try {
          return rothPolicyIsOptimizer(rothPolicyValue());
        } catch (_e) {
          return false;
        }
      },
    },
    {
      key: "hsa_drawdown",
      title: "HSA Drawdown",
      rowLabel: "hsa_withdrawal_mode",
      isLive: function () {
        try {
          return hsaWithdrawalModeValue() === "optimize";
        } catch (_e) {
          return false;
        }
      },
    },
    {
      key: "asset_allocation",
      title: "Asset Allocation",
      rowLabel: "allocation_selection_mode",
      isLive: function () {
        try {
          return allocationModeIsComputed(allocationSelectionMode());
        } catch (_e) {
          return false;
        }
      },
    },
  ];

  function liveOptimizerModeRow(entry) {
    try {
      return rowByNormLabel(entry.rowLabel) || null;
    } catch (_e) {
      return null;
    }
  }

  // Pure HTML builders, split out from the DOM-writing functions below the
  // same way sourceTruthHtml()/insertAfterPaneHead() already split above --
  // so the markup itself (content, escaping) is directly testable without a
  // real DOM.
  function liveOptimizerBadgeHtml(title) {
    return (
      '<span class="badge live" data-roadmap11="live-optimizer-badge" title="' +
      escHtml(
        title +
          " is set to an optimizing mode: the plan recomputes this every build rather than using a value you last set.",
      ) +
      '">Live optimizer output</span>'
    );
  }

  // rowIndex is optional: the jump button only renders when the mode row was
  // actually found, so a missing row degrades to a banner with no dead link
  // rather than throwing.
  function liveOptimizerBannerHtml(title, rowIndex) {
    const jump =
      rowIndex == null
        ? ""
        : ' <button type="button" class="btn tiny" onclick="window.RPDashboardRoadmap11.jumpToLiveOptimizerRow(' +
          rowIndex +
          ');return false">Change to a fixed strategy</button>';
    return (
      '<div class="live-optimizer-banner" data-roadmap11="live-optimizer-banner"><b>Live optimizer output:</b> ' +
      escHtml(title) +
      " re-optimizes on every build. These numbers are not locked in." +
      jump +
      "</div>"
    );
  }

  // The mode row itself, not a guess at which downstream fields the engine
  // does or does not honor once optimizing: §4.1a's auto-optimize path
  // mutates the in-memory config with the winning candidate's overrides and
  // never writes them back to a CSV row, so there is no separate "output"
  // row to point at for any of the three today. The mode row is the one
  // fact every reader can see and act on -- flip it, and the section stops
  // self-optimizing.
  function liveOptimizerRowBadges() {
    LIVE_OPTIMIZER_MODES.forEach(function (entry) {
      if (!entry.isLive()) return;
      const row = liveOptimizerModeRow(entry);
      if (!row) return;
      const field = byId("field-" + row.row_index);
      if (!field) return;
      const meta = field.querySelector(".field-meta");
      if (!meta || meta.querySelector('[data-roadmap11="live-optimizer-badge"]'))
        return;
      meta.insertAdjacentHTML("beforeend", liveOptimizerBadgeHtml(entry.title));
    });
  }

  // Runs only on the Optimize screen, where each optimizer has its own
  // collapsible strategySection (data-dkey="strategy:<key>") -- unlike
  // SOURCE_TRUTH_STEPS above, one banner per whole step would not say which
  // optimizer it is about, so this inserts per-section instead of via
  // insertAfterPaneHead.
  function liveOptimizerSectionBanners() {
    if (currentStep() !== "strategy_optimize") return;
    LIVE_OPTIMIZER_MODES.forEach(function (entry) {
      if (!entry.isLive()) return;
      const section = document.querySelector(
        '[data-dkey="strategy:' + entry.key + '"]',
      );
      if (!section) return;
      const header = section.querySelector(".section-header");
      if (!header || section.querySelector('[data-roadmap11="live-optimizer-banner"]'))
        return;
      // The "Lock in this schedule" affordance §4.7 describes is W10c's
      // apply-to-plan patch (§4.3/§4.4) -- not built yet. Rather than a
      // button that claims to do that and does not, the banner's jump
      // button goes to the same mode row the badge above marks, which is
      // the one working way to stop the section from re-optimizing today:
      // switch the policy off "optimize" by hand.
      const row = liveOptimizerModeRow(entry);
      header.insertAdjacentHTML(
        "afterend",
        liveOptimizerBannerHtml(entry.title, row ? row.row_index : null),
      );
    });
  }

  function jumpToLiveOptimizerRow(rowIndex) {
    const field = byId("field-" + rowIndex);
    if (!field) return;
    field.scrollIntoView({ block: "center", behavior: "smooth" });
    const control = field.querySelector("select,input");
    if (control) control.focus();
  }

  function addStaleAdvisorNotice() {
    const step = currentStep();
    if (!["review", "build_impact", "detailed_results"].includes(step)) return;
    let stale = false;
    try {
      stale = !lastBuildOk && hasUnsavedPlanChanges && hasUnsavedPlanChanges();
    } catch (_e) {}
    if (!stale) return;
    insertAfterPaneHead(
      '<div class="advisor-ready-disabled" data-roadmap11="stale-advisor"><b>Advisor-ready disabled:</b> plan inputs changed after the last successful build. Save and rebuild before treating reports as final.</div>',
      "stale-advisor",
    );
  }

  function decorateGlossary(root) {
    if (!root) return;
    const terms = glossaryTerms();
    Object.keys(terms).forEach(function (term) {
      const selector = "h1,h2,h3,p,li,span,small,td,th,button,label,summary";
      root.querySelectorAll(selector).forEach(function (el) {
        if (
          el.children.length > 3 ||
          el.closest("script,style,input,select,textarea")
        )
          return;
        const text = el.textContent || "";
        if (text.indexOf(term) >= 0 && !el.getAttribute("title"))
          el.setAttribute("title", terms[term]);
      });
    });
  }

  function buildDetailJumpList() {
    const step = currentStep();
    if (step !== "detailed_results") return;
    const box = byId("roadmap11DetailJumps");
    if (!box) return;
    // Only scan tbody data rows — thead rows are headers and produce garbled text
    const rows = Array.from(
      document.querySelectorAll("#mainPane table tbody tr"),
    ).slice(0, 300);
    const picks = [];
    rows.forEach(function (tr, idx) {
      const cells = Array.from(tr.querySelectorAll("td"));
      if (!cells.length) return;
      const fullText = (tr.textContent || "").replace(/\s+/g, " ").trim();
      if (!fullText) return;
      const isKeyRow =
        /terminal|tax|roth|success|probability|net worth|cash flow|risk|warning|retire|social security/i.test(
          fullText,
        );
      if (!isKeyRow && idx >= 5) return;
      // Label: first 3 non-empty cell values joined with a separator
      const label = cells
        .slice(0, 4)
        .map((td) => (td.textContent || "").trim())
        .filter(Boolean)
        .slice(0, 3)
        .join(" · ");
      if (!label) return;
      if (!tr.id) tr.id = "detail-row-jump-" + idx;
      picks.push({ id: tr.id, label: label });
    });
    if (!picks.length) {
      box.innerHTML =
        '<span class="small">Open a result sheet to see key-row jumps.</span>';
      return;
    }
    box.innerHTML = picks
      .slice(0, 10)
      .map(function (p) {
        return (
          '<a class="detail-jump" href="#' +
          escHtml(p.id) +
          '">' +
          escHtml(p.label) +
          "</a>"
        );
      })
      .join("");
  }

  function filterDetailJump(q) {
    q = String(q || "").toLowerCase();
    document
      .querySelectorAll("#roadmap11DetailJumps .detail-jump")
      .forEach(function (a) {
        a.style.display =
          !q || a.textContent.toLowerCase().indexOf(q) >= 0
            ? "inline-flex"
            : "none";
      });
  }

  function applyEnhancements() {
    const step = currentStep();
    insertAfterPaneHead(sourceTruthHtml(step), "source-of-truth");
    insertAfterPaneHead(spendingFlowHtml(step), "spending-flow");
    insertAfterPaneHead(reviewCloseoutHtml(step), "first-run-closeout");
    insertAfterPaneHead(recommendationsHtml(step), "expanded-recommendations");
    insertAfterPaneHead(planDataPreviewHtml(step), "plan-data-preview");
    insertAfterPaneHead(
      detailedResultsEnhancements(step),
      "detail-readability",
    );
    addStaleAdvisorNotice();
    liveOptimizerRowBadges();
    liveOptimizerSectionBanners();
    decorateGlossary(mainPane());
    decorateGlossary(byId("helpPanel"));
    buildDetailJumpList();
  }

  function installShortcuts() {
    if (window.__rpRoadmap11ShortcutsInstalled) return;
    window.__rpRoadmap11ShortcutsInstalled = true;
    document.addEventListener("keydown", function (e) {
      const tag = ((e.target && e.target.tagName) || "").toLowerCase();
      const typing = ["input", "textarea", "select"].includes(tag);
      if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === "s") {
        e.preventDefault();
        try {
          saveAll(true);
        } catch (_e) {}
        return;
      }
      if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === "b") {
        e.preventDefault();
        try {
          runBuild(false);
        } catch (_e) {}
        return;
      }
      if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === "k") {
        e.preventDefault();
        const s = byId("combinedSearch");
        if (s) {
          s.focus();
          s.select();
        }
        return;
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        String(e.key).toLowerCase() === "r"
      ) {
        e.preventDefault();
        callStep("review");
        return;
      }
      if (typing) return;
      if (e.altKey && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        e.preventDefault();
        const ids = visibleStepIds();
        const cur = currentStep();
        const i = Math.max(0, ids.indexOf(cur));
        const next =
          ids[
            Math.max(
              0,
              Math.min(ids.length - 1, i + (e.key === "ArrowRight" ? 1 : -1)),
            )
          ];
        if (next) callStep(next);
      }
    });
  }

  function saveSkipReason(value) {
    try {
      localStorage.setItem(
        "retirement.first_run.skip_reason.v1",
        String(value || ""),
      );
    } catch (_e) {}
  }
  function expandPrintableSections() {
    document.querySelectorAll("#mainPane details").forEach(function (d) {
      d.open = true;
    });
  }

  try {
    const oldRenderMain = renderMain;
    renderMain = function () {
      oldRenderMain();
      applyEnhancements();
    };
  } catch (_e) {}
  try {
    const oldShowStepHelp = showStepHelp;
    showStepHelp = function (id) {
      oldShowStepHelp(id);
      decorateGlossary(byId("helpPanel"));
    };
  } catch (_e) {}

  window.RPDashboardRoadmap11.saveSkipReason = saveSkipReason;
  window.RPDashboardRoadmap11.expandPrintableSections = expandPrintableSections;
  window.RPDashboardRoadmap11.filterDetailJump = filterDetailJump;
  window.RPDashboardRoadmap11.jumpToLiveOptimizerRow = jumpToLiveOptimizerRow;
  // Exposed for tests (tests/frontend/live_optimizer_disclosure.test.mjs):
  // the pure markup builders and the live-mode classification, independent
  // of the DOM-writing functions above that call them.
  window.RPDashboardRoadmap11.liveOptimizerModes = LIVE_OPTIMIZER_MODES;
  window.RPDashboardRoadmap11.liveOptimizerBadgeHtml = liveOptimizerBadgeHtml;
  window.RPDashboardRoadmap11.liveOptimizerBannerHtml = liveOptimizerBannerHtml;
  installShortcuts();
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", applyEnhancements);
  else setTimeout(applyEnhancements, 0);
})();
