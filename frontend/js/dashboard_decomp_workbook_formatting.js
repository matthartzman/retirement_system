// ── Workbook formatting (Settings → Manage Workbook Formatting) ─────────────
// Per-column Excel width editor. State: the tree from the last-built workbook,
// the saved overrides map, and an in-progress draft the user edits before
// saving. Draft is keyed draft[sheet][columnLetter] = width.
//
// Extracted from dashboard.js verbatim (first modularization increment);
// shares the classic-script global scope with dashboard.js, so these remain
// plain global functions/vars just as they were inline.
let workbookFormatData = null;
let workbookFormatLoading = false;
let workbookFormatError = "";
let workbookFormatDraft = {};
// Horizontal-alignment draft, keyed the same way: draft[sheet][col] = "left"|"center"|"right".
let workbookFormatAlignDraft = {};
// Persist which <details> are expanded so a re-render (save/reset) does not
// collapse the tree the user is working in.
let wfOpen = new Set();

function wfToggle(key, open) {
  if (open) wfOpen.add(key);
  else wfOpen.delete(key);
}

// Tab/Shift+Tab on a column-width field jumps straight to the next/previous
// width field in sheet -> table -> column order, expanding any collapsed
// Sheet/Table <details> along the way so the target is actually reachable --
// matching a spreadsheet-style "keep tabbing through every field" flow
// instead of the browser's default behavior of skipping hidden/collapsed
// content.
function wfWidthInputKeydown(event) {
  if (event.key !== "Tab") return;
  const inputs = Array.from(
    document.querySelectorAll(".workbook-format-panel .wf-col-width input[type=number]"),
  );
  const idx = inputs.indexOf(event.target);
  if (idx === -1) return;
  const nextIdx = idx + (event.shiftKey ? -1 : 1);
  const target = inputs[nextIdx];
  if (!target) return; // at the boundary: let focus leave the field list normally
  event.preventDefault();
  const table = target.closest("details.wf-table");
  if (table && !table.open) table.open = true;
  const sheet = target.closest("details.wf-sheet");
  if (sheet && !sheet.open) sheet.open = true;
  target.focus();
  target.select();
}

function _wfCloneOverrides(src) {
  const out = {};
  Object.keys(src || {}).forEach((sheet) => {
    out[sheet] = Object.assign({}, src[sheet]);
  });
  return out;
}

async function loadWorkbookFormat(force = false) {
  if (workbookFormatLoading) return;
  if (workbookFormatData && !force) return;
  workbookFormatLoading = true;
  workbookFormatError = "";
  try {
    const out = await api("/api/workbook-format", { timeoutMs: 30000 });
    workbookFormatData = out || { available: false, sheets: [] };
    workbookFormatDraft = _wfCloneOverrides(out && out.overrides);
    workbookFormatAlignDraft = _wfCloneOverrides(out && out.alignments);
  } catch (e) {
    workbookFormatData = { available: false, sheets: [] };
    workbookFormatError = e && e.message ? e.message : String(e);
  } finally {
    workbookFormatLoading = false;
    if (activeStep === "workbook_formatting") renderMain();
  }
}

function refreshWorkbookFormat() {
  workbookFormatData = null;
  loadWorkbookFormat(true);
  renderMain();
}

// Effective width for a column = draft override if present, else the width read
// from the last-built workbook.
function _wfEffectiveWidth(sheet, col, builtWidth) {
  const s = workbookFormatDraft[sheet];
  if (s && Object.prototype.hasOwnProperty.call(s, col)) return s[col];
  return builtWidth;
}

function _wfIsOverridden(sheet, col) {
  const s = workbookFormatDraft[sheet];
  return !!(s && Object.prototype.hasOwnProperty.call(s, col));
}

function setWorkbookColWidth(sheet, col, value) {
  const w = parseFloat(value);
  if (!workbookFormatDraft[sheet]) workbookFormatDraft[sheet] = {};
  if (!Number.isFinite(w) || w <= 0) {
    delete workbookFormatDraft[sheet][col];
  } else {
    workbookFormatDraft[sheet][col] = Math.round(Math.max(1, Math.min(255, w)) * 100) / 100;
  }
  updateWorkbookFormatDirty();
}

function resetWorkbookCol(sheet, col) {
  if (workbookFormatDraft[sheet]) {
    delete workbookFormatDraft[sheet][col];
    if (!Object.keys(workbookFormatDraft[sheet]).length)
      delete workbookFormatDraft[sheet];
  }
  renderMain();
}

// Effective horizontal alignment for a column = draft override if present,
// else the alignment read from the last-built workbook's data rows.
function _wfEffectiveAlign(sheet, col, builtAlign) {
  const s = workbookFormatAlignDraft[sheet];
  if (s && Object.prototype.hasOwnProperty.call(s, col)) return s[col];
  return builtAlign;
}

function _wfIsAlignOverridden(sheet, col) {
  const s = workbookFormatAlignDraft[sheet];
  return !!(s && Object.prototype.hasOwnProperty.call(s, col));
}

function setWorkbookColAlign(sheet, col, align) {
  if (!workbookFormatAlignDraft[sheet]) workbookFormatAlignDraft[sheet] = {};
  workbookFormatAlignDraft[sheet][col] = align;
  updateWorkbookFormatDirty();
  renderMain();
}

function resetWorkbookColAlign(sheet, col) {
  if (workbookFormatAlignDraft[sheet]) {
    delete workbookFormatAlignDraft[sheet][col];
    if (!Object.keys(workbookFormatAlignDraft[sheet]).length)
      delete workbookFormatAlignDraft[sheet];
  }
  renderMain();
}

function _wfCountDiffs(saved, draft) {
  const keys = new Set();
  const collect = (m) =>
    Object.keys(m || {}).forEach((sh) =>
      Object.keys(m[sh] || {}).forEach((c) => keys.add(sh + "||" + c)),
    );
  collect(saved);
  collect(draft);
  let n = 0;
  keys.forEach((k) => {
    const [sh, c] = k.split("||");
    const a = saved[sh] && saved[sh][c];
    const b = draft[sh] && draft[sh][c];
    if ((a === undefined ? null : a) !== (b === undefined ? null : b)) n++;
  });
  return n;
}

function workbookFormatDirtyCount() {
  const savedW = (workbookFormatData && workbookFormatData.overrides) || {};
  const savedA = (workbookFormatData && workbookFormatData.alignments) || {};
  return (
    _wfCountDiffs(savedW, workbookFormatDraft) +
    _wfCountDiffs(savedA, workbookFormatAlignDraft)
  );
}

function updateWorkbookFormatDirty() {
  const el = document.getElementById("wfDirtyCount");
  if (el) {
    const n = workbookFormatDirtyCount();
    el.textContent = n
      ? `${n} unsaved change${n === 1 ? "" : "s"}`
      : "No unsaved changes";
  }
}

async function saveWorkbookFormat() {
  try {
    const out = await api("/api/workbook-format", {
      method: "POST",
      body: JSON.stringify({ overrides: workbookFormatDraft, alignments: workbookFormatAlignDraft }),
    });
    if (out && out.success) {
      workbookFormatDraft = _wfCloneOverrides(out.overrides);
      workbookFormatAlignDraft = _wfCloneOverrides(out.alignments);
      if (workbookFormatData) {
        workbookFormatData.overrides = _wfCloneOverrides(out.overrides);
        workbookFormatData.alignments = _wfCloneOverrides(out.alignments);
      }
      showMessage(
        "Workbook formatting saved. Rebuild the workbook to apply the new column widths.",
        "success",
      );
      renderMain();
    } else {
      showMessage(
        "Could not save workbook formatting: " + ((out && out.error) || "unknown error"),
        "error",
      );
    }
  } catch (e) {
    showMessage(
      "Could not save workbook formatting: " + (e && e.message ? e.message : e),
      "error",
    );
  }
}

function _wfDetails(key, cls, summary, body) {
  const open = wfOpen.has(key) ? " open" : "";
  return `<details class="${cls}"${open} data-wfkey="${esc(key)}" ontoggle="wfToggle('${escJs(key)}',this.open)"><summary>${summary}</summary>${body}</details>`;
}

const _WF_ALIGN_OPTIONS = [
  ["left", "L", "Align left"],
  ["center", "C", "Align center"],
  ["right", "R", "Align right"],
];

function _wfAlignHtml(sheet, col, colNode) {
  const eff = _wfEffectiveAlign(sheet, col, colNode.align || "left");
  const overridden = _wfIsAlignOverridden(sheet, col);
  const btns = _WF_ALIGN_OPTIONS.map(
    ([val, label, hint]) =>
      `<button type="button" class="wf-align-btn${val === eff ? " active" : ""}" title="${hint}" onclick="setWorkbookColAlign('${escJs(sheet)}','${escJs(col)}','${val}')">${label}</button>`,
  ).join("");
  const resetBtn = overridden
    ? `<button class="btn tiny" type="button" onclick="resetWorkbookColAlign('${escJs(sheet)}','${escJs(col)}')">Reset</button>`
    : "";
  return `<span class="wf-col-align${overridden ? " wf-align-overridden" : ""}"><span class="small wf-col-align-label">Align</span><span class="wf-align-group">${btns}</span>${resetBtn}</span>`;
}

function _wfColumnHtml(sheet, colNode) {
  const col = colNode.col;
  const eff = _wfEffectiveWidth(sheet, col, colNode.width);
  const overridden = _wfIsOverridden(sheet, col);
  const title = esc(colNode.title || col);
  const resetBtn = overridden
    ? `<button class="btn tiny" type="button" onclick="resetWorkbookCol('${escJs(sheet)}','${escJs(col)}')">Reset</button>`
    : "";
  return `<div class="wf-col-row${overridden ? " wf-col-overridden" : ""}"><span class="wf-col-title">${title}</span><span class="wf-col-meta">col ${esc(col)}</span><label class="wf-col-width">Width <input type="number" min="1" max="255" step="0.5" value="${esc(String(eff))}" onchange="setWorkbookColWidth('${escJs(sheet)}','${escJs(col)}',this.value)" onkeydown="wfWidthInputKeydown(event)" /></label><span class="small wf-col-default">Automatic: ${esc(String(colNode.width))}</span>${resetBtn}${_wfAlignHtml(sheet, col, colNode)}</div>`;
}

function _wfTableHtml(sheet, tableNode, showTableLayer) {
  const cols = (tableNode.columns || []).map((c) => _wfColumnHtml(sheet, c)).join("");
  if (!showTableLayer) return cols;
  const name = esc(tableNode.name || "Table");
  const n = (tableNode.columns || []).length;
  const key = "table::" + sheet + "::" + (tableNode.name || "");
  const summary = `<span class="wf-table-title">${name}</span><span class="wf-col-meta">${n} column${n === 1 ? "" : "s"}</span>`;
  return _wfDetails(key, "wf-table", summary, `<div class="wf-table-body">${cols}</div>`);
}

function _wfSheetHtml(sheetNode, maxNameLen) {
  const sheet = sheetNode.sheet;
  const showTableLayer = !sheetNode.single_table;
  const body = (sheetNode.tables || [])
    .map((t) => _wfTableHtml(sheet, t, showTableLayer))
    .join("");
  const totalCols = (sheetNode.tables || []).reduce(
    (s, t) => s + (t.columns || []).length,
    0,
  );
  const key = "sheet::" + sheet;
  const titleStyle = maxNameLen ? ` style="min-width:${maxNameLen}ch"` : "";
  const summary = `<span class="wf-sheet-title"${titleStyle}>${esc(sheet)}</span><span class="wf-col-meta">${totalCols} column${totalCols === 1 ? "" : "s"}${showTableLayer ? " · " + (sheetNode.tables || []).length + " tables" : ""}</span>`;
  return _wfDetails(key, "wf-sheet", summary, `<div class="wf-sheet-body">${body}</div>`);
}

function renderWorkbookFormatting() {
  if (!workbookFormatData && !workbookFormatLoading) loadWorkbookFormat(false);
  const back = `<button class="btn" type="button" data-step-id="system_configuration">← Back to Settings</button>`;
  const header = `<div class="section-note"><b>Workbook formatting.</b> Adjust Excel column widths per sheet, table, and column. Widths come from the most recently built workbook; each edit is saved as an override and applied on the next build. Columns you don't touch keep their automatic width.</div>`;
  if (workbookFormatLoading && !workbookFormatData) {
    return `<div class="workbook-format-panel">${back}${header}<div class="section-note">Loading workbook layout…</div></div>`;
  }
  if (workbookFormatError) {
    return `<div class="workbook-format-panel">${back}${header}<div class="section-note warn">Could not load workbook layout: ${esc(workbookFormatError)} <button class="btn tiny" type="button" onclick="refreshWorkbookFormat()">Retry</button></div></div>`;
  }
  if (!workbookFormatData || !workbookFormatData.available) {
    return `<div class="workbook-format-panel">${back}${header}<div class="section-note warn">No built workbook found yet. Build the workbook once (Reports &amp; Review → Build), then return here to fine-tune column widths.</div></div>`;
  }
  const sheetNodes = workbookFormatData.sheets || [];
  const maxSheetNameLen = sheetNodes.reduce(
    (m, s) => Math.max(m, (s.sheet || "").length),
    0,
  );
  const sheets = sheetNodes
    .map((s) => _wfSheetHtml(s, maxSheetNameLen))
    .join("");
  const n = workbookFormatDirtyCount();
  const toolbar = `<div class="wf-toolbar"><button class="btn primary" type="button" onclick="saveWorkbookFormat()">Save formatting</button> <button class="btn" type="button" onclick="refreshWorkbookFormat()">Reload from last build</button> <span class="small" id="wfDirtyCount">${n ? `${n} unsaved change${n === 1 ? "" : "s"}` : "No unsaved changes"}</span></div>`;
  return `<div class="workbook-format-panel">${back}${header}${toolbar}<div class="wf-sheets">${sheets}</div></div>`;
}
