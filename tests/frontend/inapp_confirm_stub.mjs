// Test double for the app's in-app confirm dialog (W2-04 / UX-002). Destructive record actions call the
// real confirmDestructive (dashboard_shared_helpers.js), which asks showInAppConfirm; this stubs the dialog
// so a test can answer it, read what it was asked (message + options) and check it fails closed without one.
export const confirmState = { answer: true, asked: [] };

export async function installInAppConfirm() {
  const keep = { esc: globalThis.esc, escJs: globalThis.escJs, fmtMoney: globalThis.fmtMoney };
  await import("../../frontend/js/dashboard_shared_helpers.js");
  for (const [k, v] of Object.entries(keep)) if (v !== undefined) globalThis[k] = v; // keep each test's own helpers
  globalThis.showInAppConfirm = async (message, opts) => { confirmState.asked.push({ message, opts }); return confirmState.answer; };
}
export function resetInAppConfirm() { confirmState.answer = true; confirmState.asked.length = 0; }
