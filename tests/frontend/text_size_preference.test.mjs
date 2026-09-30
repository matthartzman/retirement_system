// Text-size preference (100/115/130%) and desktop zoomable window.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

test("text_size module applies zoom and persists via /api/prefs", async () => {
  const style = {};
  const sel = { value: "100", addEventListener() {} };
  globalThis.document = {
    readyState: "complete",
    documentElement: { style },
    getElementById: (id) => (id === "textSizeSelect" ? sel : null),
    addEventListener() {},
  };
  const store = {};
  globalThis.localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => (store[k] = v),
  };
  const calls = [];
  globalThis.fetch = (url, opts) => {
    calls.push([url, opts]);
    return Promise.resolve({ json: () => Promise.resolve({ prefs: {} }) });
  };
  const m = await import("../../frontend/js/text_size.js");
  assert.deepEqual(m.TEXT_SIZE_OPTIONS, [100, 115, 130]);
  assert.equal(m.normalizeTextSize("999"), 100);
  assert.equal(m.setTextSize("130"), 130);
  assert.equal(style.zoom, "1.3");
  assert.equal(store.rpTextSize, "130");
  const post = calls.find((c) => c[1] && c[1].method === "POST");
  assert.equal(post[0], "/api/prefs");
  assert.equal(JSON.parse(post[1].body).rpTextSize, 130);
  m.applyTextSize(100);
  assert.equal(style.zoom, "");
});

test("index.html loads text_size.js and has the selector; desktop window is zoomable", () => {
  const html = fs.readFileSync("frontend/index.html", "utf8");
  assert.match(html, /js\/text_size\.js/);
  assert.match(html, /id="textSizeSelect"/);
  const py = fs.readFileSync("src/desktop_app.py", "utf8");
  assert.match(py, /zoomable=True/);
});
