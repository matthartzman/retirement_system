// ── Workbook formatting (Settings → Manage Workbook Formatting) ─────────────
// Per-column Excel width/alignment editor. Every edit auto-saves immediately
// as a small per-column PATCH that the server MERGES into the persisted
// overrides/alignments files (workbook_format_config.merge_overrides /
// merge_alignments) -- there is no client-held "draft" and no manual Save
// step. A sheet/column this page never touches is never sent, so it can
// never be wiped out by an edit made elsewhere; only this UI ever writes
// those two files (see workbook_format_config.py's module docstring).
//
// Extracted from dashboard.js verbatim (first modularization increment);
// shares the classic-script global scope with dashboard.js, so these remain
// plain global functions/vars just as they were inline.
let workbookFormatData = null;
let workbookFormatLoading = false;
let workbookFormatError = "";
// Persist which <details> are expanded so a re-render (after an autosave)
// does not collapse the tree the user is working in.
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

async function loadWorkbookFormat(force = false) {
  if (workbookFormatLoading) return;
  if (workbookFormatData && !force) return;
  workbookFormatLoading = true;
  workbookFormatError = "";
  try {
    const out = await api("/api/workbook-format", { timeoutMs: 30000 });
    workbookFormatData = out || { available: false, sheets: [] };
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

// Effective width/alignment for a column = the currently-saved override if
// present, else the value read from the last-built workbook. There is no
// separate in-progress draft -- workbookFormatData.overrides/.alignments IS
// the current truth, kept in sync with the server after every autosave.
function _wfEffectiveWidth(sheet, col, builtWidth) {
  const s = workbookFormatData && workbookFormatData.overrides && workbookFormatData.overrides[sheet];
  return s && Object.prototype.hasOwnProperty.call(s, col) ? s[col] : builtWidth;
}

function _wfIsOverridden(sheet, col) {
  const s = workbookFormatData && workbookFormatData.overrides && workbookFormatData.overrides[sheet];
  return !!(s && Object.prototype.hasOwnProperty.call(s, col));
}

function _wfEffectiveAlign(sheet, col, builtAlign) {
  const s = workbookFormatData && workbookFormatData.alignments && workbookFormatData.alignments[sheet];
  return s && Object.prototype.hasOwnProperty.call(s, col) ? s[col] : builtAlign;
}

function _wfIsAlignOverridden(sheet, col) {
  const s = workbookFormatData && workbookFormatData.alignments && workbookFormatData.alignments[sheet];
  return !!(s && Object.prototype.hasOwnProperty.call(s, col));
}

function _wfSetOverrideLocal(sheet, col, width) {
  if (!workbookFormatData) return;
  if (!workbookFormatData.overrides) workbookFormatData.overrides = {};
  if (width > 0) {
    if (!workbookFormatData.overrides[sheet]) workbookFormatData.overrides[sheet] = {};
    workbookFormatData.overrides[sheet][col] = width;
  } else if (workbookFormatData.overrides[sheet]) {
    delete workbookFormatData.overrides[sheet][col];
    if (!Object.keys(workbookFormatData.overrides[sheet]).length)
      delete workbookFormatData.overrides[sheet];
  }
}

function _wfSetAlignLocal(sheet, col, align) {
  if (!workbookFormatData) return;
  if (!workbookFormatData.alignments) workbookFormatData.alignments = {};
  if (align) {
    if (!workbookFormatData.alignments[sheet]) workbookFormatData.alignments[sheet] = {};
    workbookFormatData.alignments[sheet][col] = align;
  } else if (workbookFormatData.alignments[sheet]) {
    delete workbookFormatData.alignments[sheet][col];
    if (!Object.keys(workbookFormatData.alignments[sheet]).length)
      delete workbookFormatData.alignments[sheet];
  }
}

// Optimistically apply the edit locally (instant feedback), fire the PATCH
// in the background, then reconcile with the server's authoritative
// post-merge state -- or roll back and surface an error if the save failed.
// This is the ONLY path that persists a width edit; there is no "Save"
// button to remember to click.
async function setWorkbookColWidth(sheet, col, value) {
  const w = parseFloat(value);
  const width =
    Number.isFinite(w) && w > 0
      ? Math.round(Math.max(1, Math.min(255, w)) * 100) / 100
      : 0;
  const prevSheet = workbookFormatData && workbookFormatData.overrides && workbookFormatData.overrides[sheet];
  const prevVal = prevSheet ? prevSheet[col] : 0;
  _wfSetOverrideLocal(sheet, col, width);
  renderMain();
  try {
    const out = await api("/api/workbook-format", {
      method: "POST",
      body: JSON.stringify({ overrides: { [sheet]: { [col]: width } } }),
    });
    if (!out || !out.success) throw new Error((out && out.error) || "unknown error");
    workbookFormatData.overrides = out.overrides;
  } catch (e) {
    _wfSetOverrideLocal(sheet, col, prevVal);
    showMessage(
      "Could not save column width: " + (e && e.message ? e.message : e),
      "error",
    );
  } finally {
    renderMain();
  }
}

function resetWorkbookCol(sheet, col) {
  setWorkbookColWidth(sheet, col, "0");
}

// Same optimistic-apply/reconcile-or-rollback pattern as setWorkbookColWidth,
// for horizontal alignment.
async function setWorkbookColAlign(sheet, col, align) {
  const prevSheet = workbookFormatData && workbookFormatData.alignments && workbookFormatData.alignments[sheet];
  const prevVal = prevSheet ? prevSheet[col] : "";
  _wfSetAlignLocal(sheet, col, align);
  renderMain();
  try {
    const out = await api("/api/workbook-format", {
      method: "POST",
      body: JSON.stringify({ alignments: { [sheet]: { [col]: align } } }),
    });
    if (!out || !out.success) throw new Error((out && out.error) || "unknown error");
    workbookFormatData.alignments = out.alignments;
  } catch (e) {
    _wfSetAlignLocal(sheet, col, prevVal);
    showMessage(
      "Could not save column alignment: " + (e && e.message ? e.message : e),
      "error",
    );
  } finally {
    renderMain();
  }
}

function resetWorkbookColAlign(sheet, col) {
  setWorkbookColAlign(sheet, col, "");
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
  // #209/#210/#212/#228: "sheet" is the stable save/lookup key (letters can
  // shift build to build); "display" is this build's actual tab title,
  // shown to the user instead.
  const sheet = sheetNode.sheet;
  const display = sheetNode.display || sheet;
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
  const summary = `<span class="wf-sheet-title"${titleStyle}>${esc(display)}</span><span class="wf-col-meta">${totalCols} column${totalCols === 1 ? "" : "s"}${showTableLayer ? " · " + (sheetNode.tables || []).length + " tables" : ""}</span>`;
  return _wfDetails(key, "wf-sheet", summary, `<div class="wf-sheet-body">${body}</div>`);
}

function renderWorkbookFormatting() {
  if (!workbookFormatData && !workbookFormatLoading) loadWorkbookFormat(false);
  const back = `<button class="btn" type="button" data-step-id="system_configuration">← Back to Settings</button>`;
  const header = `<div class="section-note"><b>Workbook formatting.</b> Adjust Excel column widths per sheet, table, and column. Widths come from the most recently built workbook. Every edit saves immediately — there is no separate Save step, and no other part of the app ever touches these saved widths except this page. Columns you don't touch keep their automatic width.</div>`;
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
    (m, s) => Math.max(m, (s.display || s.sheet || "").length),
    0,
  );
  const sheets = sheetNodes
    .map((s) => _wfSheetHtml(s, maxSheetNameLen))
    .join("");
  const toolbar = `<div class="wf-toolbar"><button class="btn" type="button" onclick="refreshWorkbookFormat()">Reload from last build</button> <span class="small">Changes save automatically as you edit</span></div>`;
  return `<div class="workbook-format-panel">${back}${header}${toolbar}<div class="wf-sheets">${sheets}</div></div>`;
}
