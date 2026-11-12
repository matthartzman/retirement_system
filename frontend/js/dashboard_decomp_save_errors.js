// ── Save-validation error mapping/reporting, extracted verbatim from row_model (W4-06); the shared error Set/Map stay there ──
let saveValidationUnmapped = [];
// UX-003 (WI-504): the backend's validation errors are strings of the form
// "('<section>', '<subsection>', '<label>'): <message>; got '<value>'"
// (src/schema_registry.py validate_rows). Resolve each back to a row,
// remember it for fieldHtml's aria-invalid, and mark any control already on
// screen. Returns the matched row_index values in error order.
const SAVE_ERROR_KEY_RE = /^\(\s*(['"])(.*?)\1\s*,\s*(['"])(.*?)\3\s*,\s*(['"])(.*?)\5\s*\)/;
export function rowIndexesForSaveErrors(errs) {
  const out = [];
  for (const err of errs || []) {
    const m = String(err || "").match(SAVE_ERROR_KEY_RE);
    if (!m) continue;
    const sec = m[2].trim(),
      sub = m[4].trim(),
      lbl = m[6].trim();
    const row = (rows || []).find(
      (r) =>
        String(r.section || "").trim() === sec &&
        String(r.subsection || "").trim() === sub &&
        String(r.label || "").trim() === lbl,
    );
    if (row && !out.includes(row.row_index)) out.push(row.row_index);
  }
  return out;
}
// "('<section>', '<subsection>', '<label>'): <message>; got <value>" -> its message part.
const SAVE_ERROR_FULL_RE = /^\(\s*(['"])(.*?)\1\s*,\s*(['"])(.*?)\3\s*,\s*(['"])(.*?)\5\s*\)\s*:\s*([\s\S]*?)(?:;\s*got\s+[\s\S]*)?$/;
function saveErrorMessageFromString(err) {
  const m = String(err || "").match(SAVE_ERROR_FULL_RE);
  return m ? m[7].trim() : String(err || "").trim();
}
// Prefer the server's structured field_errors (WI-020); fall back to parsing the string list.
// Returns { mapped: [{row_index, message}], unmapped: [message] }.
export function resolveSaveErrors(errs, fieldErrs) {
  const mapped = [];
  const unmapped = [];
  const add = (row_index, message) => {
    const hit = mapped.find((m) => m.row_index === row_index);
    if (hit) {
      if (!hit.message.includes(message)) hit.message += "; " + message;
    } else mapped.push({ row_index, message });
  };
  if (Array.isArray(fieldErrs) && fieldErrs.length) {
    fieldErrs.forEach((f) => {
      if (!f) return;
      const known =
        f.row_index !== undefined && (rows || []).some((r) => r.row_index === f.row_index);
      if (known) {
        add(f.row_index, String(f.message || f.raw || "Invalid value"));
        return;
      }
      const viaRaw = rowIndexesForSaveErrors([f.raw]);
      if (viaRaw.length) add(viaRaw[0], String(f.message || saveErrorMessageFromString(f.raw)));
      else unmapped.push(String(f.message || f.raw || ""));
    });
    return { mapped, unmapped };
  }
  (errs || []).forEach((err) => {
    const idx = rowIndexesForSaveErrors([err]);
    if (idx.length) add(idx[0], saveErrorMessageFromString(err));
    else unmapped.push(String(err || ""));
  });
  return { mapped, unmapped };
}
function applySaveErrorToDom(rowIndex) {
  const el = document.getElementById(fieldControlId(rowIndex));
  if (!el || !el.setAttribute) return;
  el.setAttribute("aria-invalid", "true");
  const errId = saveFieldErrorId(rowIndex);
  const ids = String((el.getAttribute && el.getAttribute("aria-describedby")) || "")
    .split(/\s+/)
    .filter(Boolean);
  if (!ids.includes(errId)) el.setAttribute("aria-describedby", [errId, ...ids].join(" "));
  const field = el.closest ? el.closest(".field") : null;
  if (field) field.classList.add("invalid");
  const existing = document.getElementById(errId);
  if (existing && existing.parentNode) {
    existing.innerHTML = saveFieldErrorHtml(rowIndex).replace(/^<div[^>]*>|<\/div>$/g, "");
    return;
  }
  const anchor = (el.closest && el.closest("label.toggle-switch")) || el;
  if (anchor.insertAdjacentHTML) anchor.insertAdjacentHTML("afterend", saveFieldErrorHtml(rowIndex));
}
function removeSaveErrorFromDom(rowIndex) {
  const el = document.getElementById(fieldControlId(rowIndex));
  const errEl = document.getElementById(saveFieldErrorId(rowIndex));
  if (errEl && errEl.remove) errEl.remove();
  if (!el || !el.setAttribute) return;
  const errId = saveFieldErrorId(rowIndex);
  const ids = String((el.getAttribute && el.getAttribute("aria-describedby")) || "")
    .split(/\s+/)
    .filter((x) => x && x !== errId);
  if (ids.length) el.setAttribute("aria-describedby", ids.join(" "));
  else if (el.removeAttribute) el.removeAttribute("aria-describedby");
  const row = (rows || []).find((r) => r.row_index === rowIndex);
  if (!(row && isMissing(row)) && el.removeAttribute) el.removeAttribute("aria-invalid");
  const field = el.closest ? el.closest(".field") : null;
  if (field) field.classList.remove("invalid");
}
// The error summary (a region above the page): one link per rejected field plus any
// error the server could not tie to a single field. Moves focus to it after a failed save.
export function renderSaveErrorSummary(moveFocus) {
  const box = document.getElementById("saveErrorSummary");
  if (!box) return;
  const items = Array.from(saveValidationErrors.entries());
  const n = items.length + saveValidationUnmapped.length;
  if (!n) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const label = (i) => {
    const r = (rows || []).find((x) => x.row_index === i);
    return r ? humanLabel(r.label, r) : "Field " + i;
  };
  box.innerHTML =
    '<h2 class="error-summary-title" id="saveErrorSummaryTitle">' +
    n +
    (n === 1 ? " problem" : " problems") +
    " to fix before this can be saved</h2><ul>" +
    items
      .map(
        ([i, msg]) =>
          '<li><button type="button" class="link-btn" onclick="goToInvalidField(' +
          Number(i) +
          ')">' +
          esc(label(i)) +
          "</button>: " +
          esc(msg) +
          "</li>",
      )
      .join("") +
    saveValidationUnmapped.map((m) => "<li>" + esc(m) + "</li>").join("") +
    "</ul>";
  box.setAttribute("aria-labelledby", "saveErrorSummaryTitle");
  box.hidden = false;
  if (moveFocus && box.focus) {
    if (box.scrollIntoView) box.scrollIntoView({ block: "start" });
    box.focus();
  }
}
export function markSaveValidationErrors(errs, fieldErrs) {
  const { mapped, unmapped } = resolveSaveErrors(errs, fieldErrs);
  saveValidationInvalidRows.clear();
  saveValidationErrors.clear();
  saveValidationUnmapped = unmapped;
  mapped.forEach(({ row_index, message }) => {
    saveValidationInvalidRows.add(row_index);
    saveValidationErrors.set(row_index, message);
  });
  mapped.forEach(({ row_index }) => applySaveErrorToDom(row_index));
  renderSaveErrorSummary(true);
  return mapped.map((m) => m.row_index);
}
export function clearSaveValidationErrors() {
  Array.from(saveValidationErrors.keys()).forEach(removeSaveErrorFromDom);
  saveValidationInvalidRows.clear();
  saveValidationErrors.clear();
  saveValidationUnmapped = [];
  renderSaveErrorSummary(false);
}
// The user is fixing this field: drop its own error (the rest stay until the next save).
export function clearFieldSaveError(rowIndex) {
  removeSaveErrorFromDom(rowIndex);
  saveValidationInvalidRows.delete(rowIndex);
  saveValidationErrors.delete(rowIndex);
  renderSaveErrorSummary(false);
}
export function goToInvalidField(rowIndex) {
  const row = (rows || []).find((r) => r.row_index === rowIndex);
  if (!row) return;
  const step = sourceStepForRow(row);
  if (step && step !== activeStep) setStep(step);
  setTimeout(() => {
    const el = document.getElementById(fieldControlId(rowIndex));
    if (el && typeof el.focus === "function") el.focus();
  }, 0);
}

// Shared by saveAll and saveBeforeStructuralChange (UX-001): turn a failed
// save into the field-aware error toast.
export function reportSaveFailure(e) {
  // #315: the backend's structured validation-error list (api_client.js's
  // request() attaches it as e.errors from the response body's `errors`
  // array, e.g. /api/config/rows' 422 "Plan Data validation failed") was
  // being discarded in favor of the generic e.message toast, so a save
  // failure gave no clue which field(s) actually failed. Surface the full
  // list in the message's expandable "Technical details" section (and to
  // the console) whenever the backend supplied one; fall back to the
  // plain message when it didn't.
  const errs = e && Array.isArray(e.errors) ? e.errors : null;
  if (typeof console !== "undefined" && console.error)
    console.error("Save failed:", e, errs || undefined);
  if (errs && errs.length) {
    // UX-003 (WI-504): tie each validation error back to its field --
    // aria-invalid on the control, and a "Go to" action for the first.
    const bad = markSaveValidationErrors(errs, e && e.fieldErrors);
    const first = bad.length ? rows.find((r) => r.row_index === bad[0]) : null;
    showMessage("Error saving: " + e.message, "error", {
      persistent: true,
      technicalDetail: errs.join("\n"),
      action: first
        ? {
            label: "Go to " + humanLabel(first.label, first),
            fn: "goToInvalidField(" + Number(first.row_index) + ")",
          }
        : undefined,
    });
  } else {
    showMessage("Error saving: " + e.message, "error");
  }
}
Object.assign(window, {
  reportSaveFailure, clearFieldSaveError, clearSaveValidationErrors, goToInvalidField, markSaveValidationErrors, renderSaveErrorSummary, resolveSaveErrors, rowIndexesForSaveErrors,
});
