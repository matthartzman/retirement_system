// Multi-user Phase 5: remote-mode detection, the single 401 handler, the keep-alive policy, browser file
// flows and the queued build state. Runs the real frontend/js files in a Node vm with a fake window.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const JS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js");
const src = (n) => fs.readFileSync(path.join(JS_DIR, n), "utf8");

function res(status, body, headers = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return { ok: status >= 200 && status < 300, status, headers: { get: (k) => headers[k] ?? null },
    text: async () => text, json: async () => JSON.parse(text), blob: async () => ({ size: text.length }),
    clone() { return res(status, body, headers); } };
}

// A tiny window: enough DOM for the banner, the class list and the style tag.
function makeWindow({ protocol = "https:", routes = {} } = {}) {
  const els = {};
  const mk = (tag) => ({ tag, children: [], style: {}, classList: new Set(), attrs: {}, appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); delete els[this.id]; },
    setAttribute(k, v) { this.attrs[k] = v; }, set innerHTML(_v) { this.children = []; }, get innerHTML() { return ""; } });
  const body = mk("body"), head = mk("head");
  const docEl = { classList: { add(c) { docEl.classes.add(c); }, contains: (c) => docEl.classes.has(c) }, classes: new Set() };
  const doc = { hidden: false, body, head, documentElement: docEl, listeners: {},
    createElement: mk, getElementById: (id) => els[id] || null, querySelector: () => null,
    addEventListener(ev, fn) { (this.listeners[ev] ||= []).push(fn); } };
  const origAppend = body.appendChild.bind(body);
  body.appendChild = (c) => { if (c.id) els[c.id] = c; return origAppend(c); };
  const calls = [], assigned = [];
  const win = { location: { protocol, pathname: "/", search: "", assign: (u) => assigned.push(u) }, document: doc, calls, assigned,
    fetch: async (url, opts) => { calls.push(`${(opts && opts.method) || "GET"} ${url}`); const r = routes[url.split("?")[0]]; return typeof r === "function" ? r(url, opts) : r || res(200, { success: true }); },
    setInterval: () => 1, CustomEvent: class { constructor(t) { this.type = t; } }, dispatchEvent() {}, setTimeout, console };
  win.window = win;
  vm.createContext(win);
  vm.runInContext(src("remote_mode.js"), win, { filename: "remote_mode.js" });
  return win;
}
const settle = () => new Promise((r) => setTimeout(r, 5));

test("desktop (file://) leaves fetch untouched and never turns on remote mode", async () => {
  const win = makeWindow({ protocol: "file:" });
  assert.equal(win.RetirementRemote.enabled, false);
  assert.equal(win.RetirementRemote.ready, undefined);
  assert.equal(win.calls.length, 0);
});

test("a ping that says remote_mode turns it on once, hides refused controls and relabels nothing else", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { success: true, remote_mode: true }) } });
  await win.RetirementRemote.ready; await settle();
  assert.equal(win.RetirementRemote.enabled, true);
  assert.ok(win.document.documentElement.classes.has("remote-mode"));
  const css = win.document.head.children.find((c) => c.id === "remoteModeCss").textContent;
  assert.match(css, /local-backup-card/);
  assert.match(css, /monarch-autoupdate-card/);
});

test("a ping without remote_mode (a desktop-style server over http) stays off", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { success: true }) } });
  await win.RetirementRemote.ready; await settle();
  assert.equal(win.RetirementRemote.enabled, false);
});

test("401 on any /api/ call in remote mode goes to the login page, once, with the page to return to", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }), "/api/plan": res(401, { success: false, authenticated: false }) } });
  await win.RetirementRemote.ready; await settle();
  await win.fetch("/api/plan"); await win.fetch("/api/plan");
  assert.deepEqual([...win.assigned], ["/login?next=%2F"]);
});

test("a gateway 401 body ({authenticated:false}) redirects even before the ping has been answered", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(401, { success: false, authenticated: false, error: "sign in required" }) } });
  await win.RetirementRemote.ready; await settle();
  assert.equal(win.assigned.length, 1);
});

test("a plain 401 with no gateway marker and no remote mode does not redirect (desktop token servers)", async () => {
  const win = makeWindow({ routes: { "/api/thing": res(401, { error: "bad token" }) } });
  await win.fetch("/api/thing");
  assert.equal(win.assigned.length, 0);
});

test("login and TOTP calls are never treated as an expired session", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }), "/api/auth/login": res(401, { authenticated: false }) } });
  await win.RetirementRemote.ready; await settle();
  await win.fetch("/api/auth/login", { method: "POST" });
  assert.equal(win.assigned.length, 0);
});

test("keep-alive: the status ping is answered locally for an idle or hidden tab, and goes out for an active one", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }) } });
  await win.RetirementRemote.ready; await settle();
  const before = win.calls.length;
  win.document.hidden = true;
  const out = await win.fetch("/api/ping", { cache: "no-store" });
  assert.equal(win.calls.length, before, "hidden tab: no request reaches the gateway");
  assert.equal((await out.json()).remote_mode, true);
  win.document.hidden = false;
  await win.fetch("/api/ping");
  assert.equal(win.calls.length, before + 1, "visible and recently active: a real ping");
});

test("keep-alive: a notice appears near expiry, with Stay signed in, and goes away after any successful request", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }) } });
  await win.RetirementRemote.ready; await settle();
  const R = win.RetirementRemote;
  const realNow = () => Date.now();
  try {
    R.now = () => realNow() + R.warnMs + 60000;
    R.tick();
    const banner = win.document.getElementById("remoteSessionBanner");
    assert.ok(banner, "notice shown");
    assert.equal(banner.children[1].textContent, "Stay signed in");
    banner.children[1].onclick();
    await settle();
    assert.ok(win.calls.includes("GET /api/auth/session"), "Stay signed in sends one cheap touch");
    assert.equal(win.document.getElementById("remoteSessionBanner"), null, "notice cleared once the touch succeeds");
    R.now = () => realNow() + 2 * R.idleMs;
    R.tick();
    assert.equal(win.document.getElementById("remoteSessionBanner").children[1].textContent, "Sign in");
  } finally { R.now = realNow; }
});

test("sign out posts to the gateway then leaves for the login page", async () => {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }) } });
  win.RetirementApiClient = { request: async (p, o) => { win.calls.push(`${o.method} ${p}`); } };
  await win.RetirementRemote.signOut();
  assert.ok(win.calls.includes("POST /api/auth/logout"));
  assert.deepEqual([...win.assigned], ["/login"]);
});

// ---- browser file flows (remote_files.js) ----
function withFiles(extra = {}) {
  const win = makeWindow({ routes: { "/api/ping": res(200, { remote_mode: true }) } });
  const sent = [], msgs = [];
  Object.assign(win, { showMessage: (t, k) => msgs.push([t, k]), hasUnsavedPlanChanges: () => false, showInAppConfirm: async () => true,
    loadAll: async () => {}, renderMain: () => {}, sent, msgs,
    RetirementApiClient: { request: async (p, o) => { const b = JSON.parse(o.body); sent.push([p, b]); return extra.reply ? extra.reply(b) : { success: true }; } } });
  win.FileReader = class { readAsDataURL(f) { this.result = "data:;base64," + f.b64; setTimeout(() => this.onload()); } };
  vm.runInContext(src("remote_files.js"), win, { filename: "remote_files.js" });
  const files = [];
  win.document.createElement = ((orig) => (tag) => { const el = orig(tag); if (tag === "input") el.click = () => setTimeout(() => el.onchange()); return el; })(win.document.createElement);
  win.__pick = (f) => { win.document.createElement = (tag) => ({ tag, style: {}, files: [f], click() { setTimeout(() => this.onchange()); } }); };
  return win;
}

test("plan upload refuses an oversize file before reading it, and sends base64 with the mode otherwise", async () => {
  const win = withFiles();
  win.__pick({ name: "big.rpx", size: 60 * 1024 * 1024, b64: "x" });
  await win.RetirementRemote.uploadPlan("open");
  assert.equal(win.sent.length, 0);
  assert.match(win.msgs[0][0], /limit is 47 MB/);
  win.__pick({ name: "my.rpx", size: 10, b64: "QUJD" });
  await win.RetirementRemote.uploadPlan("restore");
  assert.deepEqual(win.sent[0], ["/api/plan/upload", { filename: "my.rpx", mode: "restore", content_base64: "QUJD" }]);
});

test("Monarch upload: the dry run runs first, shows masked names verbatim, and only a confirm imports", async () => {
  const win = withFiles({ reply: (b) => ({ success: true, dry_run: b.dry_run, rows_read: 3, accounts: 1, date_range: ["2026-01-01", "2026-02-01"], account_names: ["Brokerage ••••1234"], added: 3, updated: 0, skipped: 0 }) });
  const slot = { innerHTML: "" };
  win.document.getElementById = (id) => (id === "monarchUpload_transactions" ? slot : null);
  win.__pick({ name: "tx.csv", size: 10, b64: "QQ==" });
  await win.chooseMonarchUpload("transactions");
  assert.equal(win.sent.length, 1);
  assert.equal(win.sent[0][1].dry_run, true);
  assert.match(slot.innerHTML, /Brokerage ••••1234/);
  assert.match(slot.innerHTML, /nothing imported yet/);
  await win.confirmMonarchUpload("transactions");
  assert.equal(win.sent.length, 2);
  assert.equal(win.sent[1][1].dry_run, false);
  assert.equal(win.sent[1][1].kind, "transactions");
  assert.match(slot.innerHTML, /Imported/);
});

test("the Monarch upload card leaves a named seam for a future Connect Monarch button", async () => {
  const win = withFiles();
  const html = win.RetirementRemote.monarchUploadCardHtml();
  assert.match(html, /chooseMonarchUpload\('transactions'\)/);
  assert.match(html, /chooseMonarchUpload\('balances'\)/);
});

// ---- build queue state (dashboard_decomp_build_lifecycle.js) ----
test("a queued build shows 'waiting for another build to finish', not a failure, then runs to done", async () => {
  const sb = loadDashboardSandbox();
  vm.runInContext(src("api_client.js"), sb, { filename: "api_client.js" });
  const overlay = [];
  let polls = 0;
  sb.updateBuildOverlay = (phase, detail, pct, kind) => overlay.push([phase, detail, pct, kind]);
  sb.setActiveBuildJob = () => {}; sb.startSmoothProgress = () => {}; sb.stopSmoothProgress = () => {};
  sb.sleep = async () => {};
  sb.fetch = async (url) => {
    const ok = (o) => ({ ok: true, status: 200, text: async () => JSON.stringify(o) });
    if (url.endsWith("/api/build/start")) return ok({ success: true, queued: true, job_id: "queued-ab12", position: 2, progress: 0, phase: "Waiting for a free build slot", detail: "1 build(s) ahead of yours." });
    polls += 1;
    if (polls === 1) return ok({ success: true, job: { job_id: "queued-ab12", status: "queued", queued: true, progress: 0, position: 1, detail: "Position 1 in the build queue." } });
    return ok({ success: true, job: { status: "done", progress: 100, result: { success: true, via: "queue" } } });
  };
  vm.runInContext('appReady = true; apiBase = "";', sb);
  const out = await sb.buildWithProgress({});
  assert.equal(out.via, "queue");
  const phases = overlay.map((o) => o[0]);
  assert.ok(phases.includes("Waiting for another build to finish"));
  assert.ok(overlay.every((o) => o[3] !== "error"), "never shown as an error");
});

test("the 127.0.0.1:5050 fallback is skipped once remote mode is on", async () => {
  const sb = loadDashboardSandbox();
  const urls = [];
  sb.AbortController = AbortController;
  sb.fetch = async (url) => { urls.push(url); throw new Error("down"); };
  sb.window.RetirementRemote = { enabled: true };
  vm.runInContext('appReady = false; apiBase = "";', sb);
  await sb.checkAppStatus(false);
  assert.deepEqual(urls, ["/api/ping"]);
  urls.length = 0;
  sb.window.RetirementRemote = { enabled: false };
  await sb.checkAppStatus(false);
  assert.deepEqual(urls, ["/api/ping", "http://127.0.0.1:5050/api/ping"]);
});

// ---- optional connector panel ----
test("the connector panel appears only when the server says it is available, and walks start, paste, sync", async () => {
  const win = withFiles();
  const slot = { innerHTML: "" };
  win.document.getElementById = (id) => (id === "monarchConnector" ? slot : null);
  const opened = [];
  win.open = (u) => opened.push(u);
  let status = { success: true, available: false, reason: "Not enabled on this server." };
  const seen = [];
  win.RetirementApiClient = { request: async (p, o) => {
    seen.push(p + (o && o.body ? " " + o.body : ""));
    if (p.endsWith("/start")) return { success: true, authorize_url: "https://auth.example/x", expires_in: 600 };
    if (p.endsWith("/complete")) return { success: true, available: true, connected: true };
    if (p.endsWith("/sync")) return { success: true, accounts_seen: 3, hidden_by_monarch: 2, transactions: { added: 5 }, balances: { rows: 7 } };
    return status;
  } };
  win.RetirementRemote.monarchUploadCardHtml();
  await settle();
  assert.match(slot.innerHTML, /Not enabled on this server/);
  assert.doesNotMatch(slot.innerHTML, /Connect<\/button>/);
  status = { success: true, available: true, connected: false, sign_in_pending: false };
  win.RetirementRemote.monarchUploadCardHtml();
  await settle();
  assert.match(slot.innerHTML, /monarchConnectorStart/);
  await win.monarchConnectorStart();
  assert.deepEqual([...opened], ["https://auth.example/x"]);
  assert.match(slot.innerHTML, /Finish connecting/);
  win.document.getElementById = (id) => (id === "monarchConnector" ? slot : id === "monarchCallback" ? { value: "http://127.0.0.1/callback?code=abc" } : null);
  await win.monarchConnectorFinish();
  assert.ok(seen.some((s) => s.includes('/complete {"callback_url":"http://127.0.0.1/callback?code=abc"}')));
  assert.match(slot.innerHTML, /Sync now/);
  status = { success: true, available: true, connected: true };
  await win.monarchConnectorSync();
  assert.match(slot.innerHTML, /2 hidden by the provider/);
  assert.match(slot.innerHTML, /5 transactions added, 7 balance rows/);
});
