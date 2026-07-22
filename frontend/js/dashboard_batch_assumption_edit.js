(function () {
  "use strict";
  const SCHEMA = "batch_assumption_edit_v1";
  const MAX_PREVIEW = 250;
  let planPreview = [];
  let systemRows = [];
  let systemPreview = [];
  let systemLoadedAt = "";

  // esc lives in dashboard_shared_helpers.js (A13), loaded first.
  function byId(id) {
    return document.getElementById(id);
  }
  function translatePerson(text) {
    try {
      if (typeof translatePersonPlaceholders === "function")
        return translatePersonPlaceholders(text);
    } catch (_e) {}
    return String(text == null ? "" : text);
  }
  function currentStep() {
    try {
      return activeStep || "start";
    } catch (_e) {
      return "start";
    }
  }
  function safeRows() {
    try {
      return Array.isArray(rows) ? rows : [];
    } catch (_e) {
      return [];
    }
  }
  function editableRows() {
    try {
      return safeRows().filter(isEditable);
    } catch (_e) {
      return safeRows().filter(function (r) {
        return !r.readonly;
      });
    }
  }
  function rowValue(row) {
    try {
      return valOf(row);
    } catch (_e) {
      return row && row.value != null ? row.value : "";
    }
  }
  function rowSearchText(row) {
    return [
      row.section,
      row.subsection,
      row.label,
      row.units,
      row.notes,
      row.value,
      row.schema && row.schema.description,
    ]
      .join(" ")
      .toLowerCase();
  }
  function mainPane() {
    return byId("mainPane");
  }
  function inputValue(id) {
    const el = byId(id);
    return el ? String(el.value || "") : "";
  }
  function checked(id) {
    const el = byId(id);
    return !!(el && el.checked);
  }
  function show(msg, kind) {
    try {
      showMessage(msg, kind || "info");
    } catch (_e) {}
  }
  function parseNumber(value) {
    const raw = String(value == null ? "" : value).replace(/[$,%\s,]/g, "");
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  }
  function formatNumberLike(original, n) {
    if (!Number.isFinite(n)) return String(original == null ? "" : original);
    const raw = String(original == null ? "" : original);
    let decimals = 0;
    const m = raw.match(/\.([0-9]+)/);
    if (m) decimals = Math.min(6, m[1].length);
    else if (Math.abs(n) !== Math.floor(Math.abs(n))) decimals = 2;
    let out = n.toFixed(decimals);
    if (decimals > 0) out = out.replace(/0+$/, "").replace(/\.$/, "");
    return raw.trim().endsWith("%") ? out + "%" : out;
  }
  function literalReplace(text, find, repl, caseSensitive) {
    if (!find) return text;
    const source = String(text == null ? "" : text);
    const needle = String(find);
    if (caseSensitive) return source.split(needle).join(String(repl));
    return source.replace(
      new RegExp(needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"),
      String(repl),
    );
  }
  function computeAfter(before, opts) {
    const op = opts.operation;
    if (op === "set") return opts.newValue;
    if (op === "find_replace")
      return literalReplace(
        before,
        opts.findText,
        opts.replaceText,
        opts.caseSensitive,
      );
    if (op === "multiply") {
      const n = parseNumber(before),
        factor = Number(opts.factor);
      if (n === null || !Number.isFinite(factor)) return null;
      return formatNumberLike(before, n * factor);
    }
    if (op === "add") {
      const n = parseNumber(before),
        amount = Number(opts.amount);
      if (n === null || !Number.isFinite(amount)) return null;
      return formatNumberLike(before, n + amount);
    }
    if (op === "clear") return "";
    return null;
  }
  function optionsFrom(prefix) {
    return {
      operation: inputValue(prefix + "Operation") || "set",
      newValue: inputValue(prefix + "NewValue"),
      findText: inputValue(prefix + "FindText"),
      replaceText: inputValue(prefix + "ReplaceText"),
      factor: inputValue(prefix + "Factor"),
      amount: inputValue(prefix + "Amount"),
      caseSensitive: checked(prefix + "CaseSensitive"),
    };
  }
  function filterRows(rowList, prefix, requireFilter) {
    const filter = inputValue(prefix + "Filter")
      .trim()
      .toLowerCase();
    if (requireFilter && !filter) {
      show(
        "Enter a field filter before previewing a broad batch edit.",
        "error",
      );
      return [];
    }
    const filtered = filter
      ? rowList.filter(function (r) {
          return rowSearchText(r).indexOf(filter) >= 0;
        })
      : rowList;
    return filtered;
  }
  function planCandidateRows() {
    const scope = inputValue("batchPlanScope") || "filtered";
    let candidate = editableRows();
    try {
      if (scope === "filtered") {
        candidate = rowsForStep("all_assumptions");
        if (String(searchText || "").trim()) {
          const q = String(searchText || "").toLowerCase();
          candidate = candidate.filter(function (r) {
            return rowSearchText(r).indexOf(q) >= 0;
          });
        }
      }
    } catch (_e) {}
    return filterRows(candidate, "batchPlan", scope === "all");
  }
  function buildPreview(rowList, opts, kind) {
    const preview = [];
    rowList.forEach(function (row, idx) {
      const before = String(kind === "system" ? row.value : rowValue(row));
      const after = computeAfter(before, opts);
      if (after == null) return;
      if (String(after) === String(before)) return;
      preview.push({
        kind: kind,
        row: row,
        row_index: row.row_index,
        index: idx,
        before: before,
        after: String(after),
        section: row.section || "",
        subsection: row.subsection || "",
        label: row.label || "",
      });
    });
    return preview;
  }
  function previewTableHtml(preview, emptyText) {
    if (!preview.length)
      return (
        '<div class="batch-preview-empty">' +
        esc(emptyText || "No changed rows matched this batch edit.") +
        "</div>"
      );
    const rowsHtml = preview
      .slice(0, MAX_PREVIEW)
      .map(function (p) {
        return (
          "<tr><td>" +
          esc(p.section) +
          "</td><td>" +
          esc(translatePerson(p.subsection)) +
          "</td><td>" +
          esc(p.label) +
          "</td><td>" +
          esc(translatePerson(p.before)) +
          "</td><td>" +
          esc(translatePerson(p.after)) +
          "</td></tr>"
        );
      })
      .join("");
    const capped =
      preview.length > MAX_PREVIEW
        ? '<p class="small warn">Showing first ' +
          MAX_PREVIEW +
          " of " +
          preview.length +
          " changed rows. Narrow the filter before applying a very broad edit.</p>"
        : "";
    return (
      '<div class="batch-preview-summary"><b>' +
      preview.length +
      " changed row" +
      (preview.length === 1 ? "" : "s") +
      " in preview.</b><span>Nothing has been saved yet. Review every row before applying.</span></div>" +
      capped +
      '<div class="lot-table-wrap"><table class="lot-table batch-preview-table"><thead><tr><th>Section</th><th>Subsection</th><th>Label</th><th>Before</th><th>After</th></tr></thead><tbody>' +
      rowsHtml +
      "</tbody></table></div>"
    );
  }
  function previewPlanBatchEdit() {
    const candidates = planCandidateRows();
    const opts = optionsFrom("batchPlan");
    if (opts.operation === "find_replace" && !opts.findText) {
      show("Enter text to find before previewing.", "error");
      return;
    }
    planPreview = buildPreview(candidates, opts, "plan");
    const box = byId("batchPlanPreview");
    if (box)
      box.innerHTML = previewTableHtml(
        planPreview,
        "No plan assumption values would change.",
      );
    const apply = byId("batchPlanApply");
    if (apply) apply.disabled = !planPreview.length;
    const dl = byId("batchPlanDownload");
    if (dl) dl.disabled = !planPreview.length;
  }
  async function applyPlanBatchEdit() {
    if (!planPreview.length) {
      show("Preview a batch edit before applying it.", "error");
      return;
    }
    if (
      planPreview.length > MAX_PREVIEW &&
      !(await showInAppConfirm(
        "This stages " +
          planPreview.length +
          " plan assumption edits in bulk. Save Changes to persist.",
        { title: "Batch Edit", confirmLabel: "Apply All" },
      ))
    )
      return;
    planPreview.forEach(function (p) {
      try {
        editValue(p.row.row_index, p.after, null);
      } catch (_e) {}
    });
    const count = planPreview.length;
    planPreview = [];
    try {
      lastBuildOk = false;
      renderMain();
      updateUnsaved();
      setAppControls(appReady);
    } catch (_e) {}
    show(
      "Staged " +
        count +
        " batch assumption edit" +
        (count === 1 ? "" : "s") +
        ". Click Save Changes to persist.",
      "success",
    );
  }
  function csvEscape(value) {
    const s = String(value == null ? "" : value);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function downloadPreviewCsv(kind) {
    const preview = kind === "system" ? systemPreview : planPreview;
    if (!preview.length) {
      show("Preview rows first.", "error");
      return;
    }
    const lines = [
      ["schema", "kind", "section", "subsection", "label", "before", "after"]
        .map(csvEscape)
        .join(","),
    ];
    preview.forEach(function (p) {
      lines.push(
        [SCHEMA, p.kind, p.section, p.subsection, p.label, p.before, p.after]
          .map(csvEscape)
          .join(","),
      );
    });
    try {
      downloadBlob(
        (kind === "system" ? "system_config" : "plan_assumptions") +
          "_batch_preview.csv",
        lines.join("\n"),
      );
    } catch (_e) {
      show("Could not download preview CSV.", "error");
    }
  }

  async function loadSystemConfigRows(silent) {
    try {
      const out = await api("/api/admin/system-config");
      systemRows = Array.isArray(out.rows) ? out.rows : [];
      systemLoadedAt = new Date().toLocaleString();
      if (!silent)
        show("System Configuration rows loaded for batch preview.", "success");
      const status = byId("batchSystemStatus");
      if (status)
        status.textContent =
          systemRows.length + " rows loaded · " + systemLoadedAt;
      return systemRows;
    } catch (e) {
      show(
        "Could not load System Configuration rows: " +
          (e && e.message ? e.message : e),
        "error",
      );
      return [];
    }
  }
  async function previewSystemBatchEdit() {
    if (!systemRows.length) await loadSystemConfigRows(true);
    const candidates = filterRows(systemRows, "batchSystem", true);
    const opts = optionsFrom("batchSystem");
    if (opts.operation === "find_replace" && !opts.findText) {
      show("Enter text to find before previewing.", "error");
      return;
    }
    systemPreview = buildPreview(candidates, opts, "system");
    const box = byId("batchSystemPreview");
    if (box)
      box.innerHTML = previewTableHtml(
        systemPreview,
        "No System Configuration values would change.",
      );
    const apply = byId("batchSystemApply");
    if (apply) apply.disabled = !systemPreview.length;
    const dl = byId("batchSystemDownload");
    if (dl) dl.disabled = !systemPreview.length;
    const status = byId("batchSystemStatus");
    if (status)
      status.textContent =
        (systemRows.length || 0) +
        " rows loaded · " +
        (systemPreview.length || 0) +
        " changed rows in preview";
  }
  async function applySystemBatchEdit() {
    if (!systemPreview.length) {
      show("Preview System Configuration edits before applying them.", "error");
      return;
    }
    if (
      !(await showInAppConfirm(
        systemPreview.length +
          " System Configuration edit" +
          (systemPreview.length === 1 ? "" : "s") +
          " will be written to system_config.csv immediately.",
        {
          title: "Apply System Config",
          confirmLabel: "Apply Now",
          variant: "warn",
        },
      ))
    )
      return;
    const keyFor = function (r) {
      return [r.section || "", r.subsection || "", r.label || ""].join(
        "\u001f",
      );
    };
    const updates = {};
    systemPreview.forEach(function (p) {
      updates[keyFor(p.row)] = p.after;
    });
    const next = systemRows.map(function (r) {
      const cp = Object.assign({}, r);
      const k = keyFor(cp);
      if (Object.prototype.hasOwnProperty.call(updates, k))
        cp.value = updates[k];
      return cp;
    });
    try {
      const out = await api("/api/admin/system-config", {
        method: "POST",
        body: JSON.stringify({ rows: next }),
      });
      systemRows = next;
      systemPreview = [];
      const box = byId("batchSystemPreview");
      if (box)
        box.innerHTML =
          '<div class="batch-preview-empty">System Configuration batch edit applied. Rebuild outputs before relying on reports.</div>';
      const apply = byId("batchSystemApply");
      if (apply) apply.disabled = true;
      const dl = byId("batchSystemDownload");
      if (dl) dl.disabled = true;
      show(
        "System Configuration batch edit saved. Change count: " +
          ((out.change_event && out.change_event.change_count) || "unknown") +
          ".",
        "success",
      );
    } catch (e) {
      show(
        "System Configuration batch edit failed: " +
          (e && e.message ? e.message : e),
        "error",
      );
    }
  }

  function operationInputs(prefix) {
    return (
      '<div class="batch-grid">' +
      '<label>Operation <select id="' +
      prefix +
      'Operation"><option value="set">Set value</option><option value="find_replace">Find and replace text</option><option value="multiply">Multiply number by factor</option><option value="add">Add number</option><option value="clear">Clear value</option></select></label>' +
      '<label>New value <input id="' +
      prefix +
      'NewValue" placeholder="Value for Set"></label>' +
      '<label>Find text <input id="' +
      prefix +
      'FindText" placeholder="Text to replace"></label>' +
      '<label>Replace with <input id="' +
      prefix +
      'ReplaceText" placeholder="Replacement text"></label>' +
      '<label>Factor <input id="' +
      prefix +
      'Factor" placeholder="Example: 1.03"></label>' +
      '<label>Add amount <input id="' +
      prefix +
      'Amount" placeholder="Example: 5000 or -5000"></label>' +
      '<label class="batch-checkbox"><input type="checkbox" id="' +
      prefix +
      'CaseSensitive"> Case-sensitive find</label>' +
      "</div>"
    );
  }
  function planBatchPanelHtml() {
    if (currentStep() !== "all_assumptions") return "";
    return (
      '<div class="batch-edit-panel" data-roadmap12="batch-assumption-edit"><div class="batch-edit-head"><div><span class="eyebrow">Power user</span><h3>Batch edit assumptions</h3><p class="small">Preview first, then stage many plan-row edits at once. Applying a preview only marks fields edited; click Save Changes to persist.</p></div></div><div class="batch-grid"><label>Rows to scan <select id="batchPlanScope"><option value="filtered">Current All Assumptions results</option><option value="all">All editable plan rows</option></select></label><label>Field filter <input id="batchPlanFilter" placeholder="Example: inflation, Roth, State Comparison"></label></div>' +
      operationInputs("batchPlan") +
      '<div class="table-actions"><button class="btn" type="button" onclick="window.RPDashboardRoadmap12.previewPlanBatchEdit()">Preview batch</button><button class="btn primary" type="button" id="batchPlanApply" onclick="window.RPDashboardRoadmap12.applyPlanBatchEdit()" disabled>Apply preview to staged edits</button><button class="btn" type="button" id="batchPlanDownload" onclick="window.RPDashboardRoadmap12.downloadPreviewCsv(\'plan\')" disabled>Download preview CSV</button></div><div id="batchPlanPreview" class="batch-preview-empty">No preview yet.</div></div>'
    );
  }
  function systemBatchPanelHtml() {
    // Item 180: the system-config batch editor was removed from the Settings
    // page. Raw system_config.csv edits belong in the System Configuration
    // Console, not a batch tool on the everyday Settings page.
    return "";
  }
  function insertPanels() {
    const pane = mainPane();
    if (!pane) return;
    if (
      currentStep() === "all_assumptions" &&
      !pane.querySelector('[data-roadmap12="batch-assumption-edit"]')
    ) {
      const q = pane.querySelector(".question");
      if (q) q.insertAdjacentHTML("afterend", planBatchPanelHtml());
    }
    // Item 180: no system-config batch editor is injected on the Settings page.
  }
  try {
    const oldRenderMain = renderMain;
    renderMain = function () {
      oldRenderMain();
      insertPanels();
    };
  } catch (_e) {}
  window.RPDashboardRoadmap12 = {
    schema: SCHEMA,
    previewPlanBatchEdit: previewPlanBatchEdit,
    applyPlanBatchEdit: applyPlanBatchEdit,
    downloadPreviewCsv: downloadPreviewCsv,
    loadSystemConfigRows: loadSystemConfigRows,
    previewSystemBatchEdit: previewSystemBatchEdit,
    applySystemBatchEdit: applySystemBatchEdit,
  };
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", insertPanels);
  else setTimeout(insertPanels, 0);
})();
