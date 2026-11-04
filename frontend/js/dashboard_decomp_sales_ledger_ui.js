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

export function slTabBarHtml(active, markers = {}) {
  const tabs = SL_TABS.map(([id, label]) => {
    const mk = markers[id];
    const badge = mk && mk.count > 0 ? ` <span class="sl-tab-badge ${mk.tone === "bad" ? "bad" : "warn"}">${Number(mk.count)}</span>` : "";
    const on = id === active;
    return `<button type="button" role="tab" id="sl-t-${id}" class="workspace-tab${on ? " active" : ""}" aria-selected="${on}" aria-controls="sl-p-${id}" tabindex="${on ? 0 : -1}" onclick="slSetTab('${id}')" onkeydown="slTabKeydown(event)">${label}${badge}</button>`;
  }).join("");
  return `<div class="workspace-tabs sl-tabbar" role="tablist" aria-label="Sales ledger sections">${tabs}</div>`;
}

export const slTabPanelHtml = (id, bodyHtml, active) =>
  `<div class="sl-tab" role="tabpanel" id="sl-p-${id}" aria-labelledby="sl-t-${id}"${id === active ? "" : " hidden"}>${bodyHtml}</div>`;

export function slSetTab(id, opts = {}) {
  if (!slTabOk(id)) return;
  const doc = globalThis.document;
  for (const [tid] of SL_TABS) {
    const on = tid === id;
    const btn = doc.getElementById(`sl-t-${tid}`);
    const pnl = doc.getElementById(`sl-p-${tid}`);
    if (btn) { btn.setAttribute("aria-selected", String(on)); btn.tabIndex = on ? 0 : -1; if (btn.classList) btn.classList.toggle("active", on); }
    if (pnl) pnl.hidden = !on;
  }
  slUiSave(slUiSetTab(slUiLoad(), id));
  if (opts.focus) { const b = doc.getElementById(`sl-t-${id}`); if (b) b.focus(); }
}

export function slTabKeydown(event) {
  const ids = SL_TABS.map((t) => t[0]);
  const cur = ids.indexOf(String(event.target && event.target.id).replace("sl-t-", ""));
  if (cur < 0) return;
  const next = { ArrowRight: (cur + 1) % ids.length, ArrowLeft: (cur + ids.length - 1) % ids.length, Home: 0, End: ids.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  slSetTab(ids[next], { focus: true });
}

Object.assign(window, { SL_TABS, slUiLoad, slUiSave, slUiSetTab, slUiRecordToggle, slParseHash, slSecOpen, slTabBarHtml, slTabPanelHtml, slSetTab, slTabKeydown });
