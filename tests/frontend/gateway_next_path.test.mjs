// The sign-in page's `?next=` target must stay on this site. The browser strips tab, newline and carriage return from
// a URL, so "/%09/evil.example" becomes "//evil.example" if it is ever assigned to location.href. The real
// src/gateway/pages/gateway.js runs in a sandbox with a minimal DOM; only its exported nextPath is exercised.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const SRC = new URL("../../src/gateway/pages/gateway.js", import.meta.url);
const ORIGIN = "https://gateway.example.ts.net";

function nextFor(search) {
  const sandbox = {
    document: { getElementById: () => null, body: { getAttribute: () => null }, querySelectorAll: () => [], documentElement: {}, addEventListener() {} },
    MutationObserver: class { observe() {} },
    location: { search, href: "", origin: ORIGIN },
    localStorage: { getItem: () => null, setItem() {} },
    fetch: () => Promise.reject(new Error("no network in this test")),
    URLSearchParams,
    URL,
  };
  sandbox.window = sandbox;
  sandbox.window.addEventListener = () => {};
  vm.createContext(sandbox);
  new vm.Script(fs.readFileSync(SRC, "utf8"), { filename: "gateway.js" }).runInContext(sandbox);
  return sandbox.GatewayLanding.nextPath();
}

const q = (v) => "?next=" + encodeURIComponent(v);

test("a normal same-site path, query and hash are kept", () => {
  assert.equal(nextFor(q("/insights/?x=1")), "/insights/?x=1");
  assert.equal(nextFor(q("/gateway/account#top")), "/gateway/account#top");
});

test("no next gives the home page", () => {
  assert.equal(nextFor(""), "/");
});

test("tab, newline and carriage return after the slash are refused", () => {
  assert.equal(nextFor(q("/\t/evil.example")), "/");
  assert.equal(nextFor(q("/\n/evil.example")), "/");
  assert.equal(nextFor(q("/\r/evil.example")), "/");
  assert.equal(nextFor("?next=/%09/evil.example"), "/");
  assert.equal(nextFor("?next=/%0a/evil.example"), "/");
  assert.equal(nextFor("?next=/%0d/evil.example"), "/");
});

test("protocol-relative, backslash and absolute targets are refused", () => {
  assert.equal(nextFor(q("//evil.example")), "/");
  assert.equal(nextFor(q("/\\evil.example")), "/");
  assert.equal(nextFor(q("/a\\b")), "/");
  assert.equal(nextFor(q("https://evil.example/")), "/");
  assert.equal(nextFor(q("evil.example")), "/");
  assert.equal(nextFor(q("/ok\u007f")), "/");
});
