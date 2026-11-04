// Sales Ledger page UI state: tab model, persisted section open/closed state, deep-link hash parsing (pure, no DOM).
const SL_UI_KEY = "salesLedger.ui.v1";

export const SL_TABS = [["fix", "Fix lots & transactions"], ["ledger", "Sales ledger"], ["tax", "Tax year"], ["import", "Import"]];
const slTabOk = (id) => SL_TABS.some((t) => t[0] === id);
const slDefaults = () => ({ tab: "fix", sections: {}, density: "" });

export function slUiLoad(storage = globalThis.localStorage) {
  const out = slDefaults();
  try {
    const o = JSON.parse(storage.getItem(SL_UI_KEY));
    if (!o || typeof o !== "object") return out;
    if (slTabOk(o.tab)) out.tab = o.tab;
    if (o.density === "compact") out.density = "compact";
    if (o.sections && typeof o.sections === "object") {
      for (const [k, v] of Object.entries(o.sections)) {
        if (v && typeof v === "object") out.sections[k] = { open: !!v.open, lastAlertCount: Number(v.lastAlertCount) || 0 };
      }
    }
  } catch (e) { /* storage unavailable or corrupt: use defaults */ }
  return out;
}

export function slUiSave(state, storage = globalThis.localStorage) {
  try { storage.setItem(SL_UI_KEY, JSON.stringify(state)); } catch (e) { /* storage unavailable: UI state is a convenience only */ }
}

export const slUiSetTab = (state, id) => (slTabOk(id) ? { ...state, tab: id } : state);

export const slUiRecordToggle = (state, key, open, alertCount) =>
  ({ ...state, sections: { ...state.sections, [key]: { open: !!open, lastAlertCount: Number(alertCount) || 0 } } });

export function slParseHash(hash) {
  const out = { tab: null, sec: null };
  const m = /^#sales_ledger\?(.*)$/.exec(String(hash || ""));
  if (!m) return out;
  const p = new URLSearchParams(m[1]);
  const tab = p.get("tab");
  if (slTabOk(tab)) out.tab = tab;
  out.sec = p.get("sec") || null;
  return out;
}

// Alert rule: a section with alerts re-opens whenever its alert count differs from the count the user last saw.
export function slSecOpen(state, key, defaultOpen, alertCount) {
  const e = state && state.sections && state.sections[key];
  if (!e) return !!defaultOpen;
  if (alertCount > 0 && e.lastAlertCount !== alertCount) return true;
  return !!e.open;
}

Object.assign(window, { SL_TABS, slUiLoad, slUiSave, slUiSetTab, slUiRecordToggle, slParseHash, slSecOpen });
