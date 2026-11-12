// Sales Ledger page UI state: tab model, persisted section open/closed state, deep-link hash parsing (pure, no DOM).
const SL_UI_KEY = "salesLedger.ui.v1";
export const SL_TABS = [["fix", "To fix"], ["ledger", "Sales"], ["tax", "Tax year"]];
const slTabOk = (id) => SL_TABS.some((t) => t[0] === id);
const slDefaults = () => ({ tab: "fix", sections: {}, taxableOnly: true });
export function slUiLoad(storage = globalThis.localStorage) {
  const out = slDefaults();
  try {
    const o = JSON.parse(storage.getItem(SL_UI_KEY));
    if (!o || typeof o !== "object") return out;
    if (slTabOk(o.tab)) out.tab = o.tab;
    out.taxableOnly = o.taxableOnly !== false;
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
  if (alertCount !== 0 && e.lastAlertCount !== alertCount) return true; // counted alerts are > 0, countless ones a negative signature
  return !!e.open;
}
export function slTabBarHtml(active, markers = {}) {
  const tabs = SL_TABS.map(([id, label]) => {
    const mk = markers[id];
    const tone = mk && mk.tone === "bad" ? "bad" : "warn";
    const badge = mk && mk.count > 0 ? ` <span class="sl-tab-badge ${tone}"><span aria-hidden="true">${Number(mk.count)}</span><span class="sr-only">${Number(mk.count)} ${Number(mk.count) === 1 ? "item needs" : "items need"} attention</span></span>`
      : mk && mk.attn ? ` <span class="sl-tab-badge ${tone}"><span aria-hidden="true">!</span><span class="sr-only"> needs attention</span></span>` : "";
    return [id, `${label}${badge}`];
  });
  return window.tabBarHtml("sl", tabs, active, "slSetTab", "Sales ledger sections", "workspace-tabs sl-tabbar");
}
export const slTabPanelHtml = (id, bodyHtml, active) => window.tabPanelHtml("sl", id, bodyHtml, "sl-tab", id !== active);
// The active tab is kept in memory once chosen, so it survives repaints when storage is off; storage (or a deep link) only
// gives the initial value. It is bound to the store it was chosen under: a different store starts from storage again.
let slCurTab = null;
const slStore = () => { try { return globalThis.localStorage; } catch (e) { return undefined; } };
export const slCurrentTab = () => (slCurTab && slCurTab.store === slStore() ? slCurTab.tab : slUiLoad().tab);
export function slSetCurrentTab(id) {
  if (!slTabOk(id)) return;
  slCurTab = { tab: id, store: slStore() };
  slUiSave(slUiSetTab(slUiLoad(), id));
}
// Year drives every tab. Taxable accounts only is locked on in Tax year (tax is taxable-only by definition) and says why.
export function slHeadControlState(tab) {
  const off = tab === "tax";
  return { disabled: off, title: off ? "Tax year always covers taxable accounts only." : "" };
}
export function slHeadSync(tab) {
  const doc = globalThis.document;
  if (!doc) return;
  const st = slHeadControlState(tab);
  for (const id of ["slTaxableBox"]) {
    const el = doc.getElementById(id);
    if (!el) continue;
    el.disabled = st.disabled;
    if (el.setAttribute) { el.setAttribute("aria-disabled", String(st.disabled)); el.setAttribute("title", st.title); }
    const lab = el.parentNode;
    if (lab && lab.classList) lab.classList.toggle("sl-ctl-off", st.disabled);
  }
}
export function slSetTab(id, opts = {}) {
  if (!slTabOk(id)) return;
  const doc = globalThis.document;
  if (!doc) return;
  for (const [tid] of SL_TABS) {
    const on = tid === id;
    const btn = doc.getElementById(`sl-t-${tid}`);
    const pnl = doc.getElementById(`sl-p-${tid}`);
    if (btn) { btn.setAttribute("aria-selected", String(on)); btn.tabIndex = on ? 0 : -1; if (btn.classList) btn.classList.toggle("active", on); }
    if (pnl) pnl.hidden = !on;
  }
  slSetCurrentTab(id);
  slHeadSync(id);
  if (id === "tax" && globalThis.window && globalThis.window.stOnShown) globalThis.window.stOnShown();
  if (opts.focus) { const b = doc.getElementById(`sl-t-${id}`); if (b) b.focus(); }
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
const SL_KEY_TAB = { queue: "fix", health: "fix", wash: "fix", windows: "fix", cf: "tax", b1099: "tax" };
const slEsc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const slIsAlert = (s) => !!s && (s.tone === "warn" || s.tone === "bad" || /^(stale|never run)$/i.test(String(s.text).trim()) || (s.count > 0 && s.tone !== ""));
const slAlertItems = (sums) => Object.keys(SL_KEY_TAB).filter((k) => slIsAlert(sums && sums[k])).map((k) => [k, SL_KEY_TAB[k], sums[k]]);
export function slStripHtml(summaries) {
  const items = slAlertItems(summaries).map(([k, tab, s]) =>
    `<a href="#sales_ledger?tab=${tab}&amp;sec=${k}" data-go="${tab}:${k}" class="sl-strip-item ${s.tone === "bad" ? "bad" : "warn"}" onclick="slGo('${tab}','${k}');return false">${slEsc(s.text || s.count)}</a>`);
  return `<nav aria-label="Needs attention" class="sl-strip">${items.length ? items.join(" ") : "<span>No open items</span>"}</nav>`;
}
// A tab's marker counts its alert ITEMS with a count (raw counts mix units: sales, accounts, cash rows); bad wins.
export function slMarkers(summaries) {
  const out = {};
  for (const [, tab, s] of slAlertItems(summaries)) {
    const m = out[tab] || (out[tab] = { count: 0, tone: "warn" });
    if (s.count > 0) m.count += 1;
    if (s.tone === "bad") m.tone = "bad";
  }
  for (const m of Object.values(out)) if (m.count === 0) m.attn = true; // an alert with no count still needs a text marker
  return out;
}
export const slLiveHtml = () => ""; // the live regions are persistent (index.html); this page used to inject its own
export const slAnnounce = (text, assertive = false) => announce(text, { error: assertive });
const SL_SEC_META = { queue: ["Sales waiting for lots", false], health: ["Log health", false], ledger: ["Sales", true], wash: ["Wash sales", true], tax: ["Tax year", true], cf: ["Carryforward", false], b1099: ["Import a 1099-B", false] };
const SL_TAB_SECS = { fix: ["queue", "health", "wash"], ledger: ["ledger"], tax: ["tax", "cf", "b1099"] };
// Only real alerts (same predicate as the strip) count; informational counts such as row totals never open or pin a section.
// A countless alert (stale, never run, log not started) gets a stable negative signature from its text, so the persisted-collapse
// rule re-opens the section when it first appears or changes; an alert is never hideable.
const slSig = (s) => { let h = 7; for (const c of `${s.tone}|${String(s.text).trim().toLowerCase()}`) h = (h * 31 + c.charCodeAt(0)) % 1000003; return -(h + 1); };
export const slAlertCountOf = (s) => (!slIsAlert(s) ? 0 : s.count > 0 ? s.count : slSig(s));
// Strip keys that have no section of their own land in (and re-open) another: Carryforward lives in the wash section.
const SL_SEC_OF = { cf: "tax" };
const SL_SEC_SRC = { tax: ["tax", "cf"] };
const slSecKey = (k) => SL_SEC_OF[k] || k;
// A section's alert signature: the sum over every summary that lands in it (never 0 while any of them is an alert).
export function slSecAlert(key) {
  const parts = (SL_SEC_SRC[key] || [key]).map((k) => slAlertCountOf(slSums[k])).filter((n) => n !== 0);
  const sum = parts.reduce((a, b) => a + b, 0);
  return parts.length && sum === 0 ? -1 : sum;
}
const slAlertCount = slSecAlert;
const SL_FOCUS_FALLBACK = { health: "tlStartBtn" }; // a bare prompt stands in for a section that does not exist yet
export function slGo(tab, sec) {
  if (!slTabOk(tab)) return;
  slSetTab(tab);
  const doc = globalThis.document;
  const ok = SL_SEC_META[slSecKey(sec)] ? slSecKey(sec) : null;
  const el = ok && doc && doc.getElementById(`sl-sec-${ok}`);
  if (el) {
    el.open = true;
    slUiSave(slUiRecordToggle(slUiLoad(), ok, true, slAlertCount(ok))); // navigating to a section is the user's choice to see it
    const sum = el.querySelector && el.querySelector("summary");
    if (sum && sum.focus) sum.focus();
  } else if (ok && doc && SL_FOCUS_FALLBACK[ok]) { // e.g. "log not started": the bare Start prompt is the place to land
    const f = doc.getElementById(SL_FOCUS_FALLBACK[ok]);
    if (f) { if (f.scrollIntoView) f.scrollIntoView({ block: "center" }); if (f.focus) f.focus(); }
  }
  try { globalThis.history.replaceState(null, "", location.pathname + location.search); } catch (e) { /* no history API: the tab switch still happened */ } // never leave a hash: a later render would re-apply it
}
// Collapsible section shell. `state` is the status text shown in the summary; badges are text, never colour alone.
export function slSecHtml({ key, title, badges = [], state = "", alertCount = 0, open = false, body = "" }) {
  const bs = badges.filter((b) => b && b.text).map((b, i) =>
    `<span class="sl-sec-badge sl-tone-${slEsc(b.tone || "none")}"${i === 0 ? ` id="sl-sec-badge-${key}"` : ""}>${slEsc(b.text)}</span>`).join(" ");
  const badge = bs || `<span class="sl-sec-badge sl-tone-none" id="sl-sec-badge-${key}"></span>`;
  return `<details class="sl-sec" id="sl-sec-${key}" data-key="${key}"${open ? " open" : ""} data-alert="${Number(alertCount) || 0}">` +
    `<summary id="sl-sec-sum-${key}" onclick="slOnSummaryClick('${key}')"><span class="sl-sec-chev" aria-hidden="true">&#9656;</span>` +
    `<h3 class="sl-sec-title">${slEsc(title)}</h3> ${badge} <span class="sl-sec-state" id="sl-sec-state-${key}">${slEsc(state)}</span></summary>` +
    `<div class="sl-sec-body">${body}</div></details>`;
}
// Whether a section should be open now: stored choice, except a new alert count (or any alert with no stored choice) opens it.
export function slSecWantOpen(state, key, alertCount) {
  const meta = SL_SEC_META[key];
  const n = Number(alertCount) || 0;
  if (n !== 0 && !(state && state.sections && state.sections[key])) return true;
  return slSecOpen(state, key, !!(meta && meta[1]), n);
}
// The only writer of section choices: runs from the summary click, after the browser has toggled `open`.
export function slOnSummaryClick(key) {
  setTimeout(() => {
    const el = globalThis.document && globalThis.document.getElementById(`sl-sec-${key}`);
    if (el) slUiSave(slUiRecordToggle(slUiLoad(), key, el.open, slAlertCount(key)));
  }, 0);
}
// Patch a section in place when its panel publishes a summary; never re-renders, never moves focus, never writes the store.
export function slSecUpdate(srcKey, srcSummary) {
  const key = slSecKey(srcKey);
  const summary = key === srcKey ? srcSummary : slSums[key];
  const meta = SL_SEC_META[key];
  const doc = globalThis.document;
  if (!meta || !doc) return;
  const b = doc.getElementById(`sl-sec-badge-${key}`);
  if (b) {
    b.textContent = String((summary && summary.text) || "");
    b.className = `sl-sec-badge sl-tone-${(summary && summary.tone) || "none"}`;
  }
  const stateFn = { queue: "slQueueStateText", health: "slHealthStateText" }[key];
  if (stateFn && window[stateFn]) slSecSetState(key, window[stateFn]());
  const el = doc.getElementById(`sl-sec-${key}`);
  if (!el) return;
  const st = slUiLoad();
  const n = slSecAlert(key);
  const e = st.sections[key];
  if (n === 0 && e && e.lastAlertCount !== 0) slUiSave(slUiRecordToggle(st, key, e.open, 0)); // alert cleared: forget it so its return re-opens the section
  const want = slSecWantOpen(st, key, n);
  if (want && !el.open) { // a summary update may only open a section, never close one under the user
    el.open = true;
    slAnnounce(`${meta[0]}: ${(summary && summary.text) || ""}`);
  }
}
// Panels call this from their paint functions so the summary's status text follows their live state.
export function slSecSetState(key, text) {
  const el = globalThis.document && globalThis.document.getElementById(`sl-sec-state-${key}`);
  if (el) el.textContent = String(text || "");
}
export function slSecAll(tab, open) { // no tab: the active one
  const doc = globalThis.document;
  if (!doc) return;
  let st = slUiLoad();
  for (const key of SL_TAB_SECS[tab || slCurrentTab()] || []) {
    const el = doc.getElementById(`sl-sec-${key}`);
    if (!el) continue;
    const want = !!open || slAlertCount(key) !== 0;
    el.open = want;
    st = slUiRecordToggle(st, key, want, slAlertCount(key));
  }
  slUiSave(st);
}
slOnSummary((key, summary) => slSecUpdate(key, summary));
// Post-apply links: re-run the wash check after a 1099-B apply, and Fix lots when sales are waiting.
export function slNextStepHtml(result) {
  if (!result) return "";
  const q = Number((slSums.queue || {}).count) || 0;
  const link = (tab, sec, text) => `<a href="#sales_ledger?tab=${tab}&amp;sec=${sec}" onclick="slGo('${tab}','${sec}');return false">${text}</a>`;
  const items = [result.wash ? link("tax", "wash", "Review changed lots / re-run wash check") : "", q > 0 ? link("fix", "queue", `${q} sale${q === 1 ? "" : "s"} waiting → Fix lots`) : ""].filter(Boolean);
  return items.length ? `<p class="sl-next">Next: ${items.join(" · ")}</p>` : "";
}
Object.assign(window, { slStripHtml, slMarkers, slLiveHtml, slAnnounce, slGo, slPublish, slOnSummary, slSummaries, SL_TABS, slUiLoad, slUiSave, slUiSetTab, slUiRecordToggle, slParseHash, slSecOpen, slSecHtml, slAlertCountOf, slSecAlert, slSecWantOpen, slOnSummaryClick, slSecUpdate, slSecSetState, slSecAll, slTabBarHtml, slTabPanelHtml, slSetTab, slCurrentTab, slSetCurrentTab, slHeadControlState, slHeadSync, slNextStepHtml });