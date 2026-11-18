// Where the sign-in page sends a person: the real src/gateway/pages/gateway.js runs in a sandbox with a minimal DOM, and
// only its exported landingPath rule is exercised. An explicit address always wins; a guest is never offered a choice;
// Financial Insight opens only when the server offers it to that account.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const SRC = new URL("../../src/gateway/pages/gateway.js", import.meta.url);

function load() {
  const sandbox = {
    document: { getElementById: () => null, body: { getAttribute: () => null }, querySelectorAll: () => [], documentElement: {}, addEventListener() {} },
    MutationObserver: class { observe() {} },
    location: { search: "", href: "" },
    localStorage: { getItem: () => null, setItem() {} },
    fetch: () => Promise.reject(new Error("no network in this test")),
    URLSearchParams,
  };
  sandbox.window = sandbox;
  sandbox.window.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(fs.readFileSync(SRC, "utf8"), { filename: "gateway.js" }).runInContext(sandbox);
  return sandbox.GatewayLanding.landingPath;
}

const landingPath = load();

test("a member who chose Financial Insight lands there when the server offers it", () => {
  assert.equal(landingPath({ next: "/", app: "insights", kind: "member", insights: true }), "/insights/");
});

test("a member who chose the planner, or has no saved choice, lands on the planner", () => {
  assert.equal(landingPath({ next: "/", app: "planner", kind: "member", insights: true }), "/");
  assert.equal(landingPath({ next: "", app: undefined, kind: "member", insights: true }), "/");
});

test("Financial Insight is not used when the server does not offer it to this account", () => {
  assert.equal(landingPath({ next: "/", app: "insights", kind: "member", insights: false }), "/");
  assert.equal(landingPath({ next: "/", app: "insights", kind: "member" }), "/");
});

test("a guest is never sent to Financial Insight, whatever the saved choice", () => {
  assert.equal(landingPath({ next: "/", app: "insights", kind: "viewer", insights: true }), "/");
  assert.equal(landingPath({ next: "/", app: "insights", kind: "viewer", insights: false }), "/");
});

test("an explicit address wins over the choice", () => {
  assert.equal(landingPath({ next: "/insights/", app: "planner", kind: "member", insights: true }), "/insights/");
  assert.equal(landingPath({ next: "/gateway/account", app: "insights", kind: "member", insights: true }), "/gateway/account");
});
