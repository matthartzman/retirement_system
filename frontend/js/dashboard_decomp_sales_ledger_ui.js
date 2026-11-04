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

// Row density: "" (comfortable) or "compact". Touch devices always get comfortable rows, so coarse pointers neither apply nor store it.
const slCoarse = () => { try { return !!(globalThis.matchMedia && globalThis.matchMedia("(pointer:coarse)").matches); } catch (e) { return false; } };
export const slIsCompact = (storage) => slUiLoad(storage).density === "compact" && !slCoarse();
export function slSetDensity(d, opts = {}) {
  if ((d !== "" && d !== "compact") || slCoarse()) return;
  slUiSave({ ...slUiLoad(opts.storage), density: d }, opts.storage);
  const doc = globalThis.document;
  if (!doc) return;
  const root = doc.getElementById("slRoot");
  if (root && root.classList) root.classList.toggle("sl-compact", d === "compact");
  for (const [id, on] of [["slDensityComfort", d === ""], ["slDensityCompact", d === "compact"]]) {
    const b = doc.getElementById(id);
    if (b) b.setAttribute("aria-pressed", String(on));
  }
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
    const tone = mk && mk.tone === "bad" ? "bad" : "warn";
    const badge = mk && mk.count > 0 ? ` <span class="sl-tab-badge ${tone}">${Number(mk.count)}</span>`
      : mk && mk.attn ? ` <span class="sl-tab-badge ${tone}"><span aria-hidden="true">!</span><span class="sr-only"> needs attention</span></span>` : "";
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
  if (!doc) return;
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
  for (const m of Object.values(out)) if (m.count === 0) m.attn = true; // an alert with no count still needs a text marker
  return out;
}

export const slLiveHtml = () => '<div id="slLive" class="sr-only" aria-live="polite" aria-atomic="true"></div><div id="slAlert" class="sr-only" role="alert"></div>';

export function slAnnounce(text, assertive = false) {
  const el = globalThis.document && globalThis.document.getElementById(assertive ? "slAlert" : "slLive");
  if (el) el.textContent = String(text);
}

const SL_SEC_META = { queue: ["Sales waiting for lots", false], health: ["Log health", false], log: ["Transaction log", true], cash: ["Cash in investment", false],
  ledger: ["Sales ledger", true], wash: ["Realized gains & wash sales", true], cf: ["Carryforward", false], imports: ["Broker imports", false], b1099: ["Broker 1099-B", false], csv: ["Sales CSV import", false] };
const SL_TAB_SECS = { fix: ["queue", "health", "log", "cash"], ledger: ["ledger"], tax: ["wash", "cf"], import: ["imports", "b1099", "csv"] };
// Only real alerts (same predicate as the strip) count; informational counts such as row totals never open or pin a section.
export const slAlertCountOf = (s) => (slIsAlert(s) && s.count > 0 ? s.count : 0);
const slAlertCount = (key) => slAlertCountOf(slSums[key]);

export function slGo(tab, sec) {
  if (!slTabOk(tab)) return;
  slSetTab(tab);
  const doc = globalThis.document;
  const ok = SL_SEC_META[sec] ? sec : null;
  const el = ok && doc && doc.getElementById(`sl-sec-${ok}`);
  if (el) {
    el.open = true;
    slUiSave(slUiRecordToggle(slUiLoad(), ok, true, slAlertCount(ok))); // navigating to a section is the user's choice to see it
    const sum = el.querySelector && el.querySelector("summary");
    if (sum && sum.focus) sum.focus();
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
  const n = alertCount > 0 ? alertCount : 0;
  if (n > 0 && !(state && state.sections && state.sections[key])) return true;
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
export function slSecUpdate(key, summary) {
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
  const want = slSecWantOpen(slUiLoad(), key, slAlertCountOf(summary));
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

export function slSecAll(tab, open) {
  const doc = globalThis.document;
  if (!doc) return;
  let st = slUiLoad();
  for (const key of SL_TAB_SECS[tab] || []) {
    const el = doc.getElementById(`sl-sec-${key}`);
    if (!el) continue;
    const want = !!open || slAlertCount(key) > 0;
    el.open = want;
    st = slUiRecordToggle(st, key, want, slAlertCount(key));
  }
  slUiSave(st);
}

slOnSummary((key, summary) => slSecUpdate(key, summary));

// Shared Source -> Preview -> Apply skeleton: a text row (current step in bold and aria-current, never colour alone).
export const slStepsHtml = (current) => `<ol class="sl-steps" aria-label="Import steps">` + ["Source", "Preview", "Apply"].map((t, i) =>
  (i + 1 === current ? `<li class="sl-step on" aria-current="step"><strong>${i + 1} ${t}</strong></li>` : `<li class="sl-step">${i + 1} ${t}</li>`)).join("") + `</ol>`;

// Post-apply links: re-run the wash check after a 1099-B apply, and Fix lots when sales are waiting.
export function slNextStepHtml(result) {
  if (!result) return "";
  const q = Number((slSums.queue || {}).count) || 0;
  const link = (tab, sec, text) => `<a href="#sales_ledger?tab=${tab}&amp;sec=${sec}" onclick="slGo('${tab}','${sec}');return false">${text}</a>`;
  const items = [result.wash ? link("tax", "wash", "Review changed lots / re-run wash check") : "", q > 0 ? link("fix", "queue", `${q} sale${q === 1 ? "" : "s"} waiting → Fix lots`) : ""].filter(Boolean);
  return items.length ? `<p class="sl-next" role="status">Next: ${items.join(" · ")}</p>` : "";
}

Object.assign(window, { slStripHtml, slMarkers, slLiveHtml, slAnnounce, slGo, slPublish, slOnSummary, slSummaries, SL_TABS, slUiLoad, slUiSave, slUiSetTab, slUiRecordToggle, slParseHash, slSecOpen, slSetDensity, slIsCompact, slSecHtml, slAlertCountOf, slSecWantOpen, slOnSummaryClick, slSecUpdate, slSecSetState, slSecAll, slTabBarHtml, slTabPanelHtml, slSetTab, slTabKeydown, slStepsHtml, slNextStepHtml });
