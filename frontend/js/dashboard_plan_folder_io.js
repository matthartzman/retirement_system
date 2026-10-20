// Browser folder import / export (File System Access API) over the CSV import/export API.
// Import reads the *.csv files of a chosen folder and posts their texts to /api/import/preview,
// then /api/import/commit once the user confirms. Export reads /api/export/plan-set?format=files
// and writes each file into a chosen folder. No file name is known to the client.
import { api, showMessage, showInAppConfirm, loadAll, hasUnsavedPlanChanges } from "./dashboard_decomp_row_model.js";

const pickFolder = (mode) =>
  typeof window.showDirectoryPicker === "function"
    ? window.showDirectoryPicker({ mode })
    : Promise.reject(new Error("This browser cannot open folders; use the CSV backup zip instead."));

async function readFolderCsvTexts(dir) {
  const files = {};
  for await (const [name, handle] of dir.entries()) {
    if (handle.kind === "file" && /\.(csv|json)$/i.test(name)) files[name] = await (await handle.getFile()).text();
  }
  return files;
}

const esc = (v) => window.esc(String(v));

export async function importPlanFolder() {
  try {
    const files = await readFolderCsvTexts(await pickFolder("read"));
    if (!Object.keys(files).length) return showMessage("No CSV files found in that folder.", "error");
    const post = (path) => api(path, { method: "POST", body: JSON.stringify({ dataset: "plan-set", files }) });
    const pre = await post("/api/import/preview");
    const names = Object.keys(pre.datasets || {});
    if (!pre.will_write) return showMessage(`Nothing to import (${pre.errors || 0} error(s)).`, "error");
    // UX-011 / WI-018: in-app confirm (not window.confirm) that lists each dataset with its row
    // counts, and warns when staged edits would be discarded by the refresh that follows.
    const lines = names.map((n) => {
      const d = pre.datasets[n] || {};
      const counts = d.rows_incoming !== undefined ? ` (${d.rows_current} current rows, ${d.rows_incoming} incoming)` : "";
      return `<li>${esc(n)}${esc(counts)}</li>`;
    });
    const unsaved = hasUnsavedPlanChanges();
    const body =
      `<p>Import ${names.length} dataset(s) into the open plan? This replaces their current rows.</p><ul>${lines.join("")}</ul>` +
      (unsaved ? "<p><b>You have unsaved edits on screen. They will be discarded when the plan reloads.</b></p>" : "");
    const ok = await showInAppConfirm(body, {
      bodyIsHtml: true,
      title: "Import Plan Folder",
      confirmLabel: "Import",
      variant: unsaved ? "warn" : "danger",
    });
    if (!ok) return;
    await post("/api/import/commit");
    // The import wrote the database directly; reload so the screen (and a later Save Changes)
    // reflects the imported rows, not the stale pre-import ones. loadAll clears the dirty map.
    await loadAll({ source: "Local database", preferLocal: false, silent: true, overlayTitle: "Refreshing plan", overlayDetail: "Reloading the plan after the import." });
    showMessage(`Imported ${names.length} dataset(s) from the folder.`, "success");
  } catch (e) {
    if (e && e.name !== "AbortError") showMessage("Folder import failed: " + (e.message || e), "error");
  }
}

export async function exportPlanFolder() {
  try {
    const dir = await pickFolder("readwrite");
    const out = await api("/api/export/plan-set?format=files");
    for (const [name, text] of Object.entries(out.files || {})) {
      const w = await (await dir.getFileHandle(name, { create: true })).createWritable();
      await w.write(text);
      await w.close();
    }
    showMessage(`Exported ${Object.keys(out.files || {}).length} file(s) to the folder.`, "success");
  } catch (e) {
    if (e && e.name !== "AbortError") showMessage("Folder export failed: " + (e.message || e), "error");
  }
}

Object.assign(window, { importPlanFolder, exportPlanFolder });
