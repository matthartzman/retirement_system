// The guest's page (Phase 9, multi-user-shared-view-design.md 6.1): one published record, rendered as text only.
//
// Every string from a record is inserted with createTextNode or textContent, never as HTML (C24); there is no
// innerHTML anywhere in this file. The page fetches only the viewer's three record routes, plus the session (for
// the CSRF token) and sign-out (C38). There is no Update, no account editing and no download.

const LIST = "/api/viewer/shares";
const SESSION = "/api/auth/session";
const LOGOUT = "/api/auth/logout";
const POLL_MS = 60000;
const STALE_DAYS = 7;
const MAX_ROWS = 200;
export const NOT_AVAILABLE = "This view is not available. Ask the person who shared it with you.";
export const TAB_LABELS = { live: "Snapshot", trends: "Trends", projections: "Projections" };
const TAB_ORDER = ["live", "trends", "projections"];
const SCOPE_LABELS = { week: "1 Week", month: "1 Month", "3m": "3 Months", "6m": "6 Months", ytd: "YTD", "1y": "1 Year", all: "All Time" };
// Keys whose numbers are not amounts (financial_trends_reporter/percent_view.py NON_MONEY_KEYS and ratio rules).
const NON_MONEY = new Set(["id", "days", "year", "year_fraction", "count", "share", "share_of_gain", "delayed_minutes",
  "tax_year", "years", "basis_missing", "not_estimated", "ages", "plan_first_year", "plan_last_year", "pct", "rate",
  "weight", "rows", "accounts"]);
const RATIO_SUFFIXES = ["_rate", "_pct", "_ratio", "_fraction"];
const HIDDEN_KEYS = new Set(["money_view", "freshness"]);

export const shareUrl = (id) => `${LIST}/${encodeURIComponent(id)}`;
export const statusUrl = (id) => `${shareUrl(id)}/status`;

export function isRatioKey(key) {
  const k = String(key || "");
  return k === "pct" || k === "rate" || RATIO_SUFFIXES.some((s) => k.endsWith(s));
}

// One value as display text. Percent records hold each amount as a fraction of net worth on the basis date.
export function formatValue(key, value, moneyView) {
  if (value === null || value === undefined) return "–";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value !== "number" || !Number.isFinite(value)) return String(value);
  const k = String(key || "");
  if (isRatioKey(k)) return `${(value * 100).toFixed(1)}%`;
  if (NON_MONEY.has(k)) return String(value);
  if (moneyView === "percent") return `${(value * 100).toFixed(2)}% of net worth`;
  return value.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

export function humanKey(key) {
  const k = String(key || "").replace(/_/g, " ");
  return k ? k[0].toUpperCase() + k.slice(1) : "";
}

export function daysOld(iso, now = Date.now()) {
  const t = Date.parse(String(iso || ""));
  return Number.isFinite(t) ? Math.floor((now - t) / 86400000) : null;
}

// ---- DOM helpers: text only ----
function el(doc, tag, attrs, ...children) {
  const node = doc.createElement(tag);
  for (const [name, value] of Object.entries(attrs || {})) {
    if (name === "text") node.textContent = String(value);
    else if (name === "className") node.className = String(value);
    else node.setAttribute(name, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(typeof child === "object" ? child : doc.createTextNode(String(child)));
  }
  return node;
}

function table(doc, rows, moneyView) {
  const cols = [];
  for (const row of rows.slice(0, MAX_ROWS)) {
    for (const k of Object.keys(row || {})) if (!cols.includes(k) && !HIDDEN_KEYS.has(k)) cols.push(k);
  }
  const head = el(doc, "tr", null, cols.map((c) => el(doc, "th", { scope: "col", text: humanKey(c) })));
  const body = rows.slice(0, MAX_ROWS).map((row) => el(doc, "tr", null, cols.map((c) => {
    const v = (row || {})[c];
    return el(doc, "td", { text: v !== null && typeof v === "object" ? summarize(v) : formatValue(c, v, moneyView) });
  })));
  const note = rows.length > MAX_ROWS ? el(doc, "p", { className: "note", text: `Showing ${MAX_ROWS} of ${rows.length} rows.` }) : null;
  return el(doc, "div", { className: "table-wrap" }, el(doc, "table", null, el(doc, "thead", null, head), el(doc, "tbody", null, body)), note);
}

function summarize(v) {
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  return `${Object.keys(v).length} field${Object.keys(v).length === 1 ? "" : "s"}`;
}

const isFlatRow = (r) => r && typeof r === "object" && !Array.isArray(r);

// Any JSON value as nested sections, tables and definition lists (no markup from the data).
export function renderValue(doc, value, moneyView, key = "", depth = 0) {
  if (value === null || typeof value !== "object") return el(doc, "span", { text: formatValue(key, value, moneyView) });
  if (Array.isArray(value)) {
    if (!value.length) return el(doc, "p", { className: "note", text: "None." });
    if (value.every(isFlatRow)) return table(doc, value, moneyView);
    return el(doc, "ul", null, value.slice(0, MAX_ROWS).map((v) => el(doc, "li", null, renderValue(doc, v, moneyView, key, depth + 1))));
  }
  const entries = Object.entries(value).filter(([k]) => !HIDDEN_KEYS.has(k));
  if (!entries.length) return el(doc, "p", { className: "note", text: "None." });
  const dl = el(doc, "dl", { className: depth ? "nested" : "" });
  for (const [k, v] of entries) {
    dl.appendChild(el(doc, "dt", { text: humanKey(k) }));
    if (v !== null && typeof v === "object" && depth >= 2) {
      dl.appendChild(el(doc, "dd", null, el(doc, "details", null, el(doc, "summary", { text: summarize(v) }),
        renderValue(doc, v, moneyView, k, depth + 1))));
    } else {
      dl.appendChild(el(doc, "dd", null, renderValue(doc, v, moneyView, k, depth + 1)));
    }
  }
  return dl;
}

// One route's panel. An unavailable route says so; nothing else is guessed.
export function renderPanel(doc, routeKey, payload, moneyView) {
  const title = panelTitle(routeKey);
  const section = el(doc, "section", { className: "panel" }, el(doc, "h3", { text: title }));
  if (!payload || payload.available === false) {
    section.appendChild(el(doc, "p", { className: "note", text: "Not available in this copy." }));
  } else if (payload.missing === true) {
    section.appendChild(el(doc, "p", { className: "note", text: "No recent projections were available when this copy was made." }));
  } else {
    section.appendChild(renderValue(doc, payload, moneyView));
  }
  return section;
}

const PANEL_TITLES = { "/api/history": "History", "/api/balances": "Balances", "/api/flows": "Investment flows",
  "/api/liquid-change": "Liquid accounts: daily change", "/api/spending": "Spending", "/api/live-snapshot": "Holdings",
  "/api/realized": "Realized gains", "/api/projections": "Recent projections" };

export function panelTitle(routeKey) {
  const [route, query] = String(routeKey).split("?");
  const base = PANEL_TITLES[route] || route;
  const year = /tax_year=(\d{4})/.exec(query || "");
  return year ? `${base}, tax year ${year[1]}` : base;
}

// Which keys of a tab show for a Time scope: scoped routes for that preset only, unscoped routes always.
export function keysForScope(panel, scope) {
  return Object.keys(panel || {}).filter((k) => {
    const m = /[?&]scope=([^&]+)/.exec(k);
    return !m || m[1] === scope;
  });
}

export function scopesIn(rec) {
  return Object.keys(SCOPE_LABELS).filter((sc) => rec && rec.scopes && rec.scopes[sc]);
}

// The whole record: header, the tabs present, the preset picker, the panels.
export function renderRecord(doc, rec, share, state = {}) {
  const mv = rec.money_view === "percent" ? "percent" : "dollars";
  const tabs = TAB_ORDER.filter((t) => rec.views && rec.views[t]);
  const tab = tabs.includes(state.tab) ? state.tab : tabs[0];
  const scopes = scopesIn(rec);
  const scope = scopes.includes(state.scope) ? state.scope : (scopes.includes("month") ? "month" : scopes[0]);
  const root = el(doc, "div", { className: "record" });
  const header = el(doc, "header", { className: "record-head" },
    el(doc, "p", { className: "owner", text: `Shared by ${share && share.owner ? share.owner : "the plan owner"}` }),
    el(doc, "h2", { text: share && share.title ? share.title : "Shared view" }));
  const age = daysOld(rec.generated_at, state.now);
  const asOf = el(doc, "p", { className: "as-of", text: `As of ${String(rec.generated_at || "").replace("T", " ").replace("Z", " UTC")}` });
  if (age !== null && age > STALE_DAYS) asOf.appendChild(el(doc, "span", { className: "badge", text: `more than ${STALE_DAYS} days old` }));
  header.appendChild(asOf);
  if (mv === "percent") {
    header.appendChild(el(doc, "p", { className: "basis", text: `Amounts are shown as a percent of net worth on ${rec.basis_date || "the basis date"}.` }));
  }
  if (rec.plan && rec.plan.name) header.appendChild(el(doc, "p", { className: "plan", text: `Plan: ${rec.plan.name}` }));
  root.appendChild(header);
  const bar = el(doc, "div", { className: "toolbar", role: "group", "aria-label": "View" });
  for (const t of tabs) {
    bar.appendChild(el(doc, "button", { type: "button", "data-tab": t, "aria-pressed": t === tab ? "true" : "false", text: TAB_LABELS[t] }));
  }
  if (scopes.length) {
    const select = el(doc, "select", { id: "scopeSelect", "aria-label": "Time scope" },
      scopes.map((sc) => {
        const o = el(doc, "option", { value: sc, text: SCOPE_LABELS[sc] });
        if (sc === scope) o.setAttribute("selected", "selected");
        return o;
      }));
    bar.appendChild(el(doc, "label", { className: "scope-pick" }, "Time scope ", select));
  }
  root.appendChild(bar);
  const panel = (rec.views || {})[tab] || {};
  const body = el(doc, "div", { className: "panels", "data-tab": tab });
  for (const key of keysForScope(panel, scope)) body.appendChild(renderPanel(doc, key, panel[key], mv));
  root.appendChild(body);
  return { root, tab, scope };
}

export function renderList(doc, shares) {
  const ul = el(doc, "ul", { className: "share-list" });
  for (const s of shares) {
    ul.appendChild(el(doc, "li", null, el(doc, "a", { href: `#${encodeURIComponent(s.id)}`, "data-share": s.id, text: s.title }),
      el(doc, "span", { className: "note", text: ` shared by ${s.owner}` })));
  }
  return ul;
}

// ---- wiring (browser) ----
export function startViewer(win) {
  const doc = win.document;
  const main = doc.getElementById("viewer-main");
  const state = { csrf: "", share: null, rec: null, tab: "", scope: "", timer: null };
  const show = (...nodes) => {
    while (main.firstChild) main.removeChild(main.firstChild);
    for (const n of nodes) main.appendChild(n);
  };
  const message = (text) => show(el(doc, "p", { id: "viewer-status", role: "status", text }));
  const clear = () => {
    state.rec = null;
    if (state.timer) win.clearInterval(state.timer);
    state.timer = null;
  };
  const getJson = async (url, opts) => {
    const resp = await win.fetch(url, { credentials: "same-origin", cache: "no-store", ...(opts || {}) });
    if (resp.status === 401) { win.location.assign("/login"); return null; }
    return { ok: resp.ok, data: resp.ok ? await resp.json() : null };
  };
  const unavailable = () => { clear(); message(NOT_AVAILABLE); };
  const draw = () => {
    if (!state.rec) return;
    const out = renderRecord(doc, state.rec, state.share, { tab: state.tab, scope: state.scope, now: Date.now() });
    state.tab = out.tab; state.scope = out.scope;
    show(out.root);
  };
  main.addEventListener("click", (ev) => {
    const t = ev.target && ev.target.closest ? ev.target.closest("[data-tab],[data-share]") : null;
    if (!t) return;
    if (t.dataset.share) { ev.preventDefault(); open(t.dataset.share); return; }
    if (t.tagName === "BUTTON") { state.tab = t.dataset.tab; draw(); }
  });
  main.addEventListener("change", (ev) => {
    if (ev.target && ev.target.id === "scopeSelect") { state.scope = ev.target.value; draw(); }
  });
  const poll = async () => {
    if (!state.share) return;
    const r = await getJson(statusUrl(state.share.id), { headers: { "X-Background-Poll": "1" } });
    if (r && !r.ok) unavailable();
  };
  async function open(id) {
    clear();
    const share = (state.list || []).find((s) => s.id === id);
    const r = await getJson(shareUrl(id));
    if (!r) return;
    if (!r.ok || !share) { unavailable(); return; }
    state.share = share; state.rec = r.data;
    draw();
    state.timer = win.setInterval(poll, POLL_MS);
  }
  const logout = async () => {
    clear();
    show();
    try {
      await win.fetch(LOGOUT, { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": state.csrf, "Content-Type": "application/json" }, body: "{}" });
    } finally {
      win.location.replace("/login");
    }
  };
  const btn = doc.getElementById("logout");
  if (btn) btn.addEventListener("click", logout);
  // A page restored from the back-forward cache after sign-out shows nothing until it has checked again.
  win.addEventListener("pageshow", (ev) => { if (ev.persisted) { clear(); show(); win.location.reload(); } });
  (async () => {
    const sess = await getJson(SESSION);
    if (!sess || !sess.ok) return;
    state.csrf = sess.data.csrf_token || "";
    const list = await getJson(LIST);
    if (!list) return;
    if (!list.ok) { unavailable(); return; }
    state.list = list.data.shares || [];
    if (!state.list.length) { message(NOT_AVAILABLE); return; }  // the same text whatever the reason (6.1)
    if (state.list.length === 1) { open(state.list[0].id); return; }
    show(el(doc, "h2", { text: "Shared with you" }), renderList(doc, state.list));
  })();
}

if (typeof window !== "undefined" && window.document && window.document.getElementById("viewer-main")) {
  startViewer(window);
}
