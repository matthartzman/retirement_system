/* planning_workbench_ui.js: browser-local Planning Workbench case store and rendering. */
(function () {
  "use strict";
  const STORE_KEY = "retirement.planning_case_v1";
  const ACTIVE_KEY = "retirement.planning_case_active_v1";
  function translatePerson(v) {
    try {
      if (typeof translatePersonPlaceholders === "function")
        return translatePersonPlaceholders(v);
    } catch (_e) {}
    return String(v == null ? "" : v);
  }
  function esc(ctx, v) {
    return ctx && ctx.esc
      ? ctx.esc(v)
      : String(v ?? "").replace(/[&<>"']/g, function (c) {
          return {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;",
          }[c];
        });
  }
  function escJs(ctx, v) {
    return ctx && ctx.escJs
      ? ctx.escJs(v)
      : String(v ?? "")
          .replace(/\\/g, "\\\\")
          .replace(/'/g, "\\'");
  }
  function call(fn) {
    try {
      return typeof fn === "function" ? fn() : undefined;
    } catch (_e) {
      return undefined;
    }
  }
  function nowIso() {
    try {
      return new Date().toISOString();
    } catch (_e) {
      return "";
    }
  }
  function normalizeSource(v) {
    v = String(v || "manual").toLowerCase();
    return ["strategy", "scenario", "stress", "manual"].includes(v)
      ? v
      : "manual";
  }
  function normalizeRunType(v) {
    v = String(v || "quick_compare").toLowerCase();
    return ["quick_compare", "full_build", "stress_suite"].includes(v)
      ? v
      : "quick_compare";
  }
  function readAll() {
    try {
      const raw = localStorage.getItem(STORE_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.filter(Boolean) : [];
    } catch (_e) {
      return [];
    }
  }
  function saveAll(cases) {
    try {
      localStorage.setItem(
        STORE_KEY,
        JSON.stringify((cases || []).slice(0, 25)),
      );
    } catch (_e) {}
  }
  function activeId() {
    try {
      return localStorage.getItem(ACTIVE_KEY) || "";
    } catch (_e) {
      return "";
    }
  }
  function setActive(id, ctx) {
    try {
      if (id) localStorage.setItem(ACTIVE_KEY, id);
      else localStorage.removeItem(ACTIVE_KEY);
    } catch (_e) {}
    call(ctx && ctx.renderMain);
  }
  function caseId() {
    return (
      "case_" +
      Date.now().toString(36) +
      "_" +
      Math.random().toString(36).slice(2, 7)
    );
  }
  function metricSummary(ctx) {
    call(ctx.loadBuildHistory);
    const h =
      ((call(ctx.getBuildHistory) || [])[0] &&
        (call(ctx.getBuildHistory) || [])[0].kpi) ||
      {};
    const last = call(ctx.getLastBuildSummary) || {};
    const k = Object.keys(last).length ? last : h;
    return {
      terminal_nw:
        Number(
          k.inheritable_nw ?? k.terminal_net_worth ?? k.terminal_nw ?? 0,
        ) || 0,
      success_probability:
        Number(k.mc_success ?? k.success_probability ?? 0) || 0,
      lifetime_tax: Number(k.lifetime_tax ?? 0) || 0,
      roth_conversion_total:
        Number(k.roth_conversion_total ?? k.total_roth_conversions ?? 0) || 0,
      pti: Number(k.post_tax_inheritance ?? k.pti ?? 0) || 0,
      source: "latest_build_or_snapshot",
    };
  }
  function baseSnapshotId(ctx) {
    call(ctx.loadBuildHistory);
    const h = call(ctx.getBuildHistory) || [];
    return (h && h[0] && h[0].id) || "latest_saved_baseline";
  }
  function overrideFromRow(ctx, row, source, reason) {
    if (!row) return null;
    const stepId =
      call(() => ctx.stepIdForRow(row)) || call(ctx.getActiveStep) || "";
    const dirty = call(ctx.getDirty) || new Map();
    return {
      source: source || "manual",
      sourceStep: stepId,
      sourceTitle: call(() => ctx.stepTitleById(stepId)) || "",
      section: String(row.section || ""),
      subsection: String(row.subsection || ""),
      field: String(row.label || ""),
      label:
        call(() => ctx.humanLabel(row.label, row)) || String(row.label || ""),
      before:
        call(() => ctx.displayValueForInput(row, row.value || "")) ||
        String(row.value || ""),
      after:
        call(() =>
          ctx.displayValueForInput(
            row,
            dirty.has(row.row_index)
              ? dirty.get(row.row_index)
              : row.value || "",
          ),
        ) || "",
      row_index: row.row_index,
      rationale:
        reason ||
        row.notes ||
        "Review this assumption as part of the change set.",
    };
  }
  function currentManualOverrideItems(ctx) {
    const items = [];
    const dirty = call(ctx.getDirty) || new Map();
    const rows = call(ctx.getRows) || [];
    dirty.forEach(function (v, idx) {
      const row = rows.find((r) => r.row_index === idx);
      const item = overrideFromRow(
        ctx,
        row,
        "manual",
        "Currently staged unsaved edit.",
      );
      if (item) {
        item.after = call(() => ctx.displayValueForInput(row, v)) || String(v);
        item.afterRaw = String(v);
        items.push(item);
      }
    });
    return items;
  }
  function currentScenarioOverrideItems(ctx) {
    try {
      return (
        ctx.scenarioActiveOverrideItems(ctx.rowsForStep("scenarios")) || []
      ).map(function (x) {
        return {
          source: "scenario",
          sourceStep: "scenarios",
          sourceTitle: "Scenario Change Sets",
          section: x.group || "Scenarios",
          subsection: "",
          field: x.label || "",
          label: x.label || "",
          before: "Baseline",
          after: x.value || "",
          rationale: "Active scenario override.",
        };
      });
    } catch (_e) {
      return [];
    }
  }
  function strategyLeverOverrideItems(ctx) {
    try {
      return (ctx.planningLeverRows() || []).slice(0, 8).map(function (x) {
        const inputs = call(ctx.getPlanningLeverInputs) || {};
        return {
          source: "strategy",
          sourceStep: x.sourceStep || "planning_levers",
          sourceTitle: x.source || "Strategy Levers",
          section: x.focus || "Strategy",
          subsection: "",
          field: x.key || x.lever,
          label: x.lever,
          before: "Current saved plan",
          after: (inputs[x.key] ?? "") + " " + (x.unit || ""),
          rationale: x.note || "Strategy lever selected for evaluation.",
          estimated_tnw_delta: x.tnw,
          estimated_success_delta: x.success,
        };
      });
    } catch (_e) {
      return [];
    }
  }
  function stressOverrideItems(ctx) {
    const ids = ["monte_carlo_options", "survivor_stress", "ltc_stress"];
    const out = [];
    ids.forEach(function (id) {
      (ctx.rowsForStep(id) || []).slice(0, 10).forEach(function (r) {
        const it = overrideFromRow(
          ctx,
          r,
          "stress",
          "Stress-suite assumption; adverse test, not a forecast.",
        );
        if (it) out.push(it);
      });
    });
    return out.slice(0, 20);
  }
  function overridesForSource(ctx, source) {
    source = normalizeSource(source);
    if (source === "scenario") return currentScenarioOverrideItems(ctx);
    if (source === "strategy") return strategyLeverOverrideItems(ctx);
    if (source === "stress") return stressOverrideItems(ctx);
    return currentManualOverrideItems(ctx);
  }
  async function createCase(ctx, source) {
    source = normalizeSource(source);
    const def =
      source.charAt(0).toUpperCase() +
      source.slice(1) +
      " case " +
      new Date().toLocaleDateString();
    const name = await ctx.prompt("Name this planning case:", def, {
      title: "Save Planning Case",
    });
    if (!name) return;
    const cases = readAll();
    const c = {
      case_id: caseId(),
      name: String(name).trim(),
      base_snapshot_id: baseSnapshotId(ctx),
      source: source,
      overrides: overridesForSource(ctx, source),
      run_type: source === "stress" ? "stress_suite" : "quick_compare",
      result_summary: metricSummary(ctx),
      created_at: nowIso(),
      schema: "planning_case_v1",
    };
    cases.unshift(c);
    saveAll(cases);
    setActive(c.case_id, ctx);
    call(() =>
      ctx.showMessage(
        "Planning case saved locally. Review it in the Planning Workbench.",
        "success",
      ),
    );
  }
  async function deleteCase(ctx, id) {
    if (
      !(await ctx.confirm("Delete this local planning case?", {
        title: "Delete Case",
        confirmLabel: "Delete",
        variant: "danger",
      }))
    )
      return;
    const cases = readAll().filter((c) => c.case_id !== id);
    saveAll(cases);
    if (activeId() === id) setActive("", ctx);
    else call(ctx.renderMain);
  }
  function archiveCase(ctx, id) {
    const cases = readAll();
    const c = cases.find((x) => x.case_id === id);
    if (c) {
      c.archived = !c.archived;
      c.updated_at = nowIso();
      saveAll(cases);
      call(ctx.renderMain);
    }
  }
  function adoptCase(ctx, id) {
    const c = readAll().find((x) => x.case_id === id);
    if (!c) return;
    const first = (c.overrides || []).find((x) => x.sourceStep);
    if (first) {
      call(() =>
        ctx.showMessage(
          "Open each source page, apply the chosen inputs, Save Changes, then rebuild. Planning cases never mutate the saved plan automatically.",
          "warn",
          { persistent: true },
        ),
      );
      call(() => ctx.setStep(first.sourceStep));
    } else
      call(() =>
        ctx.showMessage("This case has no source links to adopt.", "error"),
      );
  }
  function sourceButtons() {
    return `<div class="workbench-action-grid"><button class="btn primary" type="button" onclick="planningCaseCreate('manual')">Save staged edits as case</button><button class="btn" type="button" onclick="planningCaseCreate('strategy')">Save strategy levers as case</button><button class="btn" type="button" onclick="planningCaseCreate('scenario')">Save scenario overrides as case</button><button class="btn" type="button" onclick="planningCaseCreate('stress')">Save stress suite as case</button></div>`;
  }
  function overrideTable(ctx, items, empty) {
    items = items || [];
    if (!items.length)
      return `<p class="small">${esc(ctx, empty || "No overrides captured yet.")}</p>`;
    let html =
      '<div class="lot-table-wrap"><table class="lot-table planning-case-overrides"><thead><tr><th>Source</th><th>Assumption</th><th>Before</th><th>After / test</th><th>Rationale</th></tr></thead><tbody>';
    items.slice(0, 40).forEach(function (x) {
      const src = x.sourceStep
        ? `<button class="btn tiny" type="button" data-step-id="${esc(ctx, x.sourceStep)}">${esc(ctx, x.sourceTitle || call(() => ctx.stepTitleById(x.sourceStep)) || x.sourceStep)}</button>`
        : esc(ctx, x.source || "manual");
      html += `<tr><td>${src}</td><td><b>${esc(ctx, x.label || x.field || "Assumption")}</b><div class="small">${esc(ctx, translatePerson([x.section, x.subsection].filter(Boolean).join(" · ")))}</div></td><td>${esc(ctx, translatePerson(String(x.before ?? "")))}</td><td>${esc(ctx, translatePerson(String(x.after ?? "")))}</td><td class="small">${esc(ctx, x.rationale || "")}</td></tr>`;
    });
    html += "</tbody></table></div>";
    if (items.length > 40)
      html += `<p class="small">+${items.length - 40} more captured items.</p>`;
    return html;
  }
  function matrixHtml(ctx, cases) {
    const base = metricSummary(ctx);
    let rows = [
      {
        name: "Built Baseline",
        source: "baseline",
        run_type: "baseline",
        result_summary: base,
        case_id: "",
      },
    ].concat(cases.filter((c) => !c.archived));
    let html =
      '<div class="lot-table-wrap"><table class="lot-table planning-workbench-matrix"><thead><tr><th>Case</th><th>Source</th><th>Run type</th><th>Success</th><th>Terminal NW</th><th>Lifetime tax</th><th>Roth conversions</th><th>Decision</th></tr></thead><tbody>';
    rows.forEach(function (c, i) {
      const r = c.result_summary || {};
      html += `<tr class="${i === 0 ? "baseline-row" : ""}"><td><b>${esc(ctx, c.name || "Built Baseline")}</b><div class="small">${esc(ctx, c.base_snapshot_id || "latest build")}</div></td><td>${esc(ctx, c.source || "baseline")}</td><td>${esc(ctx, c.run_type || "baseline")}</td><td>${ctx.fmtPct((Number(r.success_probability ?? r.mc_success ?? 0) || 0) * 100)}</td><td>${ctx.fmtMoney(Number(r.terminal_nw ?? r.terminal_net_worth ?? r.inheritable_nw ?? 0) || 0)}</td><td>${ctx.fmtMoney(Number(r.lifetime_tax ?? 0) || 0)}</td><td>${ctx.fmtMoney(Number(r.roth_conversion_total ?? 0) || 0)}</td><td>${i === 0 ? "—" : `<button class="btn tiny" type="button" onclick="setPlanningCaseActive('${escJs(ctx, c.case_id)}')">Review</button>`}</td></tr>`;
    });
    html += "</tbody></table></div>";
    return html;
  }
  function cardsHtml(ctx, cases, active) {
    if (!cases.length)
      return '<p class="small">No saved planning cases yet. Use the actions above to save staged edits, strategy levers, scenario overrides, or stress assumptions as a reusable case.</p>';
    let html = '<div class="planning-case-list">';
    cases.forEach(function (c) {
      const selected = active && c.case_id === active.case_id;
      html += `<details class="scenario-set-card planning-case-card" ${selected ? "open" : ""}><summary><b>${esc(ctx, c.name)}</b><span>${esc(ctx, c.source)} · ${esc(ctx, c.run_type)} · ${(c.overrides || []).length} override${(c.overrides || []).length === 1 ? "" : "s"}${c.archived ? " · archived" : ""}</span></summary><div class="scenario-set-body">${overrideTable(ctx, c.overrides, "This case has no captured override rows.")}<div class="table-actions">${(c.overrides || []).some((x) => x.row_index != null) ? `<button class="btn" type="button" onclick="promotePlanningCase('${escJs(ctx, c.case_id)}')">Promote to Plan</button>` : ""}<button class="btn primary" type="button" onclick="planningCaseAdopt('${escJs(ctx, c.case_id)}')">Adopt via source pages</button><button class="btn" type="button" onclick="setPlanningCaseActive('${escJs(ctx, c.case_id)}')">Use for comparison</button><button class="btn" type="button" onclick="planningCaseArchive('${escJs(ctx, c.case_id)}')">${c.archived ? "Unarchive" : "Archive"}</button><button class="danger-link" type="button" onclick="planningCaseDelete('${escJs(ctx, c.case_id)}')">Delete</button></div></div></details>`;
    });
    html += "</div>";
    return html;
  }
  function stressSelectorHtml(ctx, cases) {
    const opts = ['<option value="baseline">Built Baseline</option>']
      .concat(
        cases
          .filter((c) => !c.archived)
          .map(
            (c) =>
              `<option value="${esc(ctx, c.case_id)}">${esc(ctx, c.name)}</option>`,
          ),
      )
      .join("");
    return `<div class="feature-card"><h3>Stress suite target</h3><p class="small">Run adverse assumptions against the baseline or a saved planning case. Stress tests remain labels and inputs until you save/build deliberately.</p><label class="small">Apply stress assumptions to</label><select class="compact-input" onchange="setPlanningCaseActive(this.value==='baseline'?'':this.value)">${opts}</select><div class="pane-actions"><button class="btn" type="button" data-step-id="monte_carlo_options">Configure Stress Suite</button><button class="btn" type="button" onclick="planningCaseCreate('stress')">Save stress case</button></div></div>`;
  }
  function renderWorkbench(ctx) {
    const cases = readAll();
    const aid = activeId();
    const active =
      cases.find((c) => c.case_id === aid) ||
      cases.find((c) => !c.archived) ||
      null;
    const staged = currentManualOverrideItems(ctx);
    let html = '<div class="planning-workbench">';
    html +=
      '<div class="section-note workbench-model"><b>Planning Workbench model:</b> Baseline → Change Set → Run Type → Impact → Decision. A Planning Case is browser-local and never changes the saved plan by itself.</div>';
    html +=
      '<div class="feature-grid workbench-overview"><div class="feature-card"><h3>1. Review baseline</h3><p>Use the latest saved and built plan as the comparison anchor.</p><button class="btn" type="button" data-step-id="build_impact">Open Impact & Build History</button></div><div class="feature-card"><h3>2. Try a strategy lever</h3><p>Adjust test amounts in the Strategy Levers panel below to rank ideas, then save the selected set as a case.</p><button class="btn" type="button" data-step-id="distribution_strategy">Open Distribution Strategy &rarr;</button></div><div class="feature-card"><h3>3. Compare scenarios</h3><p>Set deterministic what-if overrides in the Scenario Change Sets panel below, save as a named set, then compare in the matrix.</p></div><div class="feature-card"><h3>4. Run stress suite</h3><p>Set adverse assumptions in the Stress &amp; Probability panel below, rebuild, then compare results in the matrix.</p></div></div>';
    html +=
      '<details><summary><b>Strategy Levers</b><span class="small"> test amounts and directional estimates — edit source pages to change the actual plan</span></summary><div class="scenario-set-body">' +
      call(ctx.renderWorkbenchLeverEditorHtml) +
      "</div></details>";
    html +=
      '<details><summary><b>Scenario Change Sets</b><span class="small"> deterministic what-if overrides — save as a named set, then compare in the matrix</span></summary><div class="scenario-set-body">' +
      call(ctx.renderScenarios) +
      "</div></details>";
    html +=
      '<details><summary><b>Stress &amp; Probability</b><span class="small"> Monte Carlo settings, survivor, long-term care, and adverse scenarios</span></summary><div class="scenario-set-body">' +
      call(ctx.renderWorkbenchStressHtml) +
      "</div></details>";
    html +=
      '<details open><summary><b>Change Set Builder</b><span class="small"> staged edits, strategy levers, scenarios, and stresses share one override list</span></summary><div class="scenario-set-body">' +
      sourceButtons() +
      "<h4>Currently staged manual edits</h4>" +
      overrideTable(
        ctx,
        staged,
        "No unsaved field edits are currently staged.",
      ) +
      "</div></details>";
    html +=
      '<details open><summary><b>Unified Comparison Matrix</b><span class="small"> one vocabulary for every run type</span></summary>' +
      matrixHtml(ctx, cases) +
      "</details>";
    html +=
      '<div class="feature-grid">' +
      stressSelectorHtml(ctx, cases) +
      '<div class="feature-card"><h3>Decision panel</h3><p class="small">Every comparison ends with one deliberate choice: adopt selected changes into the saved plan via source pages, keep as a named scenario only, or archive/no action.</p>' +
      (active
        ? `<p><b>Selected:</b> ${esc(ctx, active.name)}</p><div class="pane-actions"><button class="btn primary" type="button" onclick="planningCaseAdopt('${escJs(ctx, active.case_id)}')">Adopt via source pages</button><button class="btn" type="button" data-step-id="build_impact">View impact</button><button class="btn" type="button" onclick="planningCaseArchive('${escJs(ctx, active.case_id)}')">Archive/no action</button></div>`
        : '<p class="small">Select or create a case to make a decision.</p>') +
      "</div></div>";
    html +=
      "<details " +
      (active ? "open" : "") +
      '><summary><b>Saved Planning Cases</b><span class="small"> planning_case_v1 browser-local store</span></summary>' +
      cardsHtml(ctx, cases, active) +
      "</details>";
    html += "</div>";
    return html;
  }
  function renderBuildImpactContext(ctx) {
    const cases = readAll().filter((c) => !c.archived);
    if (!cases.length) return "";
    const active = cases.find((c) => c.case_id === activeId()) || cases[0];
    return `<div class="impact-panel planning-workbench-impact"><h3>Planning Workbench comparison context</h3><p class="small">Build Impact now uses the same Baseline / Change Set / Run Type / Impact vocabulary as Strategy, Scenario Change Sets, and Stress Suite. The selected planning case is for comparison context only; adopt changes on source pages before rebuilding.</p><div class="feature-grid"><div class="feature-card"><h3>Baseline</h3><p>${esc(ctx, active.base_snapshot_id || "Latest saved/built plan")}</p></div><div class="feature-card"><h3>Change Set</h3><p><b>${esc(ctx, active.name)}</b></p><p class="small">${(active.overrides || []).length} override${(active.overrides || []).length === 1 ? "" : "s"} from ${esc(ctx, active.source)}</p></div><div class="feature-card"><h3>Run Type</h3><p>${esc(ctx, active.run_type || "quick_compare")}</p></div><div class="feature-card"><h3>Decision</h3><div class="pane-actions"><button class="btn tiny" type="button" data-step-id="planning_workbench">Open Workbench</button><button class="btn tiny" type="button" onclick="planningCaseAdopt('${escJs(ctx, active.case_id)}')">Adopt via source pages</button></div></div></div>${overrideTable(ctx, (active.overrides || []).slice(0, 8), "No overrides captured for the selected case.")}</div>`;
  }
  window.RetirementPlanningWorkbench = {
    STORE_KEY,
    ACTIVE_KEY,
    nowIso,
    normalizeSource,
    normalizeRunType,
    readAll,
    saveAll,
    activeId,
    setActive,
    caseId,
    metricSummary,
    baseSnapshotId,
    overrideFromRow,
    currentManualOverrideItems,
    currentScenarioOverrideItems,
    strategyLeverOverrideItems,
    stressOverrideItems,
    overridesForSource,
    createCase,
    deleteCase,
    archiveCase,
    adoptCase,
    sourceButtons,
    overrideTable,
    matrixHtml,
    cardsHtml,
    stressSelectorHtml,
    renderWorkbench,
    renderBuildImpactContext,
  };
})();
