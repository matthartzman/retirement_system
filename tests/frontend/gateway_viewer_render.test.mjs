// The guest page (src/gateway/pages/viewer.js, Phase 9): hostile strings in a record render as text only (C24), and
// the page fetches only its three record routes plus the session and sign-out (C38). Runs the real module against a
// minimal DOM whose innerHTML setter throws, so any HTML insertion fails the test.
import { test } from "node:test";
import assert from "node:assert/strict";

import { NOT_AVAILABLE, formatValue, keysForScope, renderRecord, startViewer } from "../../src/gateway/pages/viewer.js";

const HOSTILE = [
  "<script>alert(1)</script>", "<img src=x onerror=alert(2)>", "\"><svg onload=alert(3)>", "javascript:alert(4)",
  "&lt;b&gt;entity&lt;/b&gt;", "{{constructor.constructor('alert(5)')()}}", "</td></tr><tr><td>row",
];

class Text {
  constructor(text) { this.nodeType = 3; this.data = String(text); }
}

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.nodeType = 1; this.children = []; this.attrs = {}; this.listeners = {};
    this.dataset = {}; this.className = "";
  }
  set innerHTML(_v) { throw new Error("innerHTML must never be used"); }
  get innerHTML() { throw new Error("innerHTML must never be read"); }
  set outerHTML(_v) { throw new Error("outerHTML must never be used"); }
  insertAdjacentHTML() { throw new Error("insertAdjacentHTML must never be used"); }
  set textContent(v) { this.children = [new Text(v)]; }
  get textContent() { return this.children.map((c) => (c.nodeType === 3 ? c.data : c.textContent)).join(""); }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-(\w)/g, (_m, c) => c.toUpperCase())] = String(value);
  }
  appendChild(node) { this.children.push(node); return node; }
  removeChild(node) { this.children = this.children.filter((c) => c !== node); return node; }
  get firstChild() { return this.children[0] || null; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  closest(sel) {
    if (sel.includes("[data-tab]") && this.attrs["data-tab"] !== undefined) return this;
    if (sel.includes("[data-share]") && this.attrs["data-share"] !== undefined) return this;
    return null;
  }
}

function fakeDocument() {
  const created = [];
  const byId = {};
  const doc = {
    created,
    createElement(tag) { const e = new Element(tag); created.push(e); return e; },
    createTextNode(t) { return new Text(t); },
    getElementById(id) { return byId[id] || null; },
    byId,
  };
  byId["viewer-main"] = new Element("main");
  byId.logout = new Element("button");
  return doc;
}

function walk(node, visit) {
  visit(node);
  for (const c of node.children || []) walk(c, visit);
}

function hostileRecord(mv = "percent") {
  const name = HOSTILE.join(" | ");
  return {
    schema: "shared_view/1", share_id: "a".repeat(32), scope_rev: 1, generated_at: "2026-11-18T12:00:00Z",
    plan: { id: "p", name }, money_view: mv, basis_date: "2026-11-18",
    scopes: { week: { from: "2026-11-11", to: "2026-11-18" }, month: { from: "2026-10-18", to: "2026-11-18" } },
    views: {
      trends: {
        "/api/balances": { accounts: HOSTILE.map((h, i) => ({ display_name: h, type: h, latest_balance: 0.1 * i })) },
        "/api/spending?scope=month": { budget: { by_type: Object.fromEntries(HOSTILE.map((h) => [h, 0.01])) } },
        "/api/spending?scope=week": { hierarchy: {} },
      },
      live: { "/api/live-snapshot?scope=month": { liquid: { positions: [{ symbol: HOSTILE[0], value: 0.2 }] } } },
      projections: { "/api/projections": { available: false } },
    },
  };
}

test("hostile strings in a record render as text", () => {
  for (const mv of ["percent", "dollars"]) {
    const doc = fakeDocument();
    const rec = hostileRecord(mv);
    for (const tab of ["trends", "live", "projections"]) {
      const share = { id: rec.share_id, title: HOSTILE[1], owner: HOSTILE[2] };
      const { root } = renderRecord(doc, rec, share, { tab, scope: "month", now: Date.parse("2026-11-19T00:00:00Z") });
      const texts = [];
      walk(root, (n) => {
        if (n.nodeType === 3) texts.push(n.data);
        if (n.nodeType === 1) {
          assert.ok(!["SCRIPT", "IMG", "SVG", "IFRAME", "OBJECT", "STYLE"].includes(n.tagName), n.tagName);
          for (const [k, v] of Object.entries(n.attrs)) {
            assert.ok(!k.startsWith("on"), k);
            for (const h of HOSTILE) assert.ok(!v.includes(h), `${k}=${v}`);
          }
        }
      });
      const all = texts.join("\n");
      assert.ok(all.includes(HOSTILE[2]), "the owner's name is shown, as text");
      if (tab === "trends") for (const h of HOSTILE) assert.ok(all.includes(h), h);
    }
    // Every element the module made came from its own tag list, never from data.
    const tags = new Set(doc.created.map((e) => e.tagName));
    for (const t of tags) assert.ok(["DIV", "HEADER", "P", "H2", "H3", "SPAN", "BUTTON", "SELECT", "OPTION", "LABEL",
      "SECTION", "DL", "DT", "DD", "DETAILS", "SUMMARY", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "UL", "LI"].includes(t), t);
  }
});

test("only the tabs and presets present in the record are offered", () => {
  const doc = fakeDocument();
  const rec = hostileRecord();
  delete rec.views.live;
  const { root, tab, scope } = renderRecord(doc, rec, { title: "t", owner: "o" }, {});
  const buttons = [];
  walk(root, (n) => { if (n.tagName === "BUTTON") buttons.push(n.attrs["data-tab"]); });
  assert.deepEqual(buttons, ["trends", "projections"]);
  assert.equal(tab, "trends");
  assert.equal(scope, "month");
  assert.deepEqual(keysForScope(rec.views.trends, "week"), ["/api/balances", "/api/spending?scope=week"]);
});

test("percent records say what the numbers are", () => {
  assert.equal(formatValue("total", 0.25, "percent"), "25.00% of net worth");
  assert.equal(formatValue("return_pct", 0.05, "percent"), "5.0%");
  assert.equal(formatValue("year", 2030, "percent"), "2030");
  assert.equal(formatValue("total", 1234.4, "dollars"), "$1,234");
});

function fakeWindow(answers) {
  const doc = fakeDocument();
  const calls = [];
  const intervals = [];
  const win = {
    document: doc, calls, intervals, listeners: {},
    location: { assigned: [], assign(u) { this.assigned.push(u); }, replace(u) { this.assigned.push(u); }, reload() {} },
    setInterval(fn) { intervals.push(fn); return intervals.length; },
    clearInterval() {},
    addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); },
    async fetch(url, opts = {}) {
      calls.push({ url, method: opts.method || "GET", headers: opts.headers || {} });
      const a = answers(url, opts);
      return { status: a.status, ok: a.status >= 200 && a.status < 300, json: async () => a.body };
    },
  };
  return win;
}

const flush = () => new Promise((r) => setTimeout(r, 0));

test("the page fetches only its three routes, plus the session and sign-out", async () => {
  const rec = hostileRecord();
  let available = true;
  const win = fakeWindow((url) => {
    if (url === "/api/auth/session") return { status: 200, body: { csrf_token: "csrf-1" } };
    if (url === "/api/viewer/shares") return { status: 200, body: { shares: [{ id: rec.share_id, title: "T", owner: "O" }] } };
    if (url === `/api/viewer/shares/${rec.share_id}`) return { status: 200, body: rec };
    if (url === `/api/viewer/shares/${rec.share_id}/status`) return available ? { status: 200, body: { available: true } } : { status: 404, body: {} };
    if (url === "/api/auth/logout") return { status: 200, body: {} };
    return { status: 599, body: {} };
  });
  startViewer(win);
  for (let i = 0; i < 6; i++) await flush();
  const main = win.document.byId["viewer-main"];
  assert.ok(main.textContent.includes("Shared by O"));
  assert.equal(win.intervals.length, 1);
  await win.intervals[0]();  // the 60-second status poll
  const poll = win.calls.find((c) => c.url.endsWith("/status"));
  assert.equal(poll.headers["X-Background-Poll"], "1");
  available = false;
  await win.intervals[0]();
  for (let i = 0; i < 3; i++) await flush();
  assert.equal(main.textContent, NOT_AVAILABLE);  // revoked: the content is cleared
  for (const fn of win.document.byId.logout.listeners.click) await fn();
  for (let i = 0; i < 3; i++) await flush();
  assert.equal(main.textContent, "");  // cleared on sign-out
  const allowed = new Set(["/api/auth/session", "/api/viewer/shares", `/api/viewer/shares/${rec.share_id}`,
    `/api/viewer/shares/${rec.share_id}/status`, "/api/auth/logout"]);
  for (const c of win.calls) assert.ok(allowed.has(c.url), c.url);
  const logout = win.calls.find((c) => c.url === "/api/auth/logout");
  assert.equal(logout.method, "POST");
  assert.equal(logout.headers["X-CSRF-Token"], "csrf-1");
  assert.ok(win.location.assigned.includes("/login"));
});

test("an unavailable share shows the one plain message", async () => {
  const win = fakeWindow((url) => {
    if (url === "/api/auth/session") return { status: 200, body: { csrf_token: "c" } };
    if (url === "/api/viewer/shares") return { status: 200, body: { shares: [{ id: "b".repeat(32), title: "T", owner: "O" }] } };
    return { status: 404, body: { success: false, available: false, error: "Not available." } };
  });
  startViewer(win);
  for (let i = 0; i < 6; i++) await flush();
  assert.equal(win.document.byId["viewer-main"].textContent, NOT_AVAILABLE);
});
