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

// Panel summaries: each panel publishes {count, tone, text} under its spec key; the page shell subscribes.
const slSums = {};
const slSubs = new Set();
export function slPublish(key, summary) {
  slSums[key] = { count: Number(summary && summary.count) || 0, tone: (summary && summary.tone) || "", text: String((summary && summary.text) || "") };
  for (const cb of [...slSubs]) { try { cb(key, { ...slSums[key] }); } catch (e) { /* a bad subscriber must not break a panel paint */ } }
}
export function slOnSummary(cb) { slSubs.add(cb); return () => { slSubs.delete(cb); }; }
export const slSummaries = () => Object.fromEntries(Object.entries(slSums).map(([k, v]) => [k, { ...v }]));

// Alert strip: one text badge per open item (warn/bad, stale/never run, or counted + toned), across all years.
const SL_KEY_TAB = { queue: "fix", health: "fix", log: "fix", cash: "fix", wash: "tax", cf: "tax", b1099: "import", imports: "import" };
const slEsc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const slIsAlert = (s) => !!s && (s.tone === "warn" || s.tone === "bad" || /^(stale|never run)$/i.test(String(s.text).trim()) || (s.count > 0 && s.tone !== ""));
const slAlertItems = (sums) => Object.keys(SL_KEY_TAB).filter((k) => slIsAlert(sums && sums[k])).map((k) => [k, SL_KEY_TAB[k], sums[k]]);

export function slStripHtml(summaries) {
  const items = slAlertItems(summaries).map(([k, tab, s]) =>
    `<a href="#sales_ledger?tab=${tab}&amp;sec=${k}" data-go="${tab}:${k}" class="sl-strip-item ${s.tone === "bad" ? "bad" : "warn"}" onclick="slGo('${tab}','${k}');return false">${slEsc(s.text || s.count)}</a>`);
  return `<nav aria-label="Needs attention" class="sl-strip">${items.length ? items.join(" ") : "<span>No open items</span>"}</nav>`;
}

export function slMarkers(summaries) {
  const out = {};
  for (const [, tab, s] of slAlertItems(summaries)) {
    const m = out[tab] || (out[tab] = { count: 0, tone: "warn" });
    m.count += s.count;
    if (s.tone === "bad") m.tone = "bad";
  }
  return out;
}

export const slLiveHtml = () => '<div id="slLive" class="sr-only" aria-live="polite" aria-atomic="true"></div><div id="slAlert" class="sr-only" role="alert"></div>';

export function slAnnounce(text, assertive = false) {
  const el = globalThis.document && globalThis.document.getElementById(assertive ? "slAlert" : "slLive");
  if (el) el.textContent = String(text);
}

export function slGo(tab, sec) {
  slSetTab(tab);
  const ok = ["queue", "health", "log", "wash", "cf", "b1099", "cash", "imports"].includes(sec) ? sec : null;
  const el = ok && globalThis.document.getElementById(`sl-sec-${ok}`);
  if (el) {
    el.open = true;
    const sum = el.querySelector && el.querySelector("summary");
    if (sum && sum.focus) sum.focus();
  }
  try { globalThis.history.replaceState(null, "", `#sales_ledger?tab=${tab}${ok ? `&sec=${ok}` : ""}`); } catch (e) { /* no history API: the tab switch still happened */ }
}

Object.assign(window, { slStripHtml, slMarkers, slLiveHtml, slAnnounce, slGo, slPublish, slOnSummary, slSummaries, SL_TABS, slUiLoad, slUiSave, slUiSetTab, slUiRecordToggle, slParseHash, slSecOpen, slTabBarHtml, slTabPanelHtml, slSetTab, slTabKeydown });
