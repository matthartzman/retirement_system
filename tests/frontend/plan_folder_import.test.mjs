// WI-031 / QA-008: behavioural tests for importPlanFolder / exportPlanFolder
// (dashboard_plan_folder_io.js). That file is a real ES module with an
// import line the shared loader does not handle, so it is evaluated here in
// its own vm context with the imported helpers supplied as stubs.

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const SRC = fs.readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js", "dashboard_plan_folder_io.js"),
  "utf8",
);

let calls, messages, confirmed, unsaved, loads, win;
function load() {
  const src = SRC.replace(/^import .*$/m, "const { api, showMessage, showInAppConfirm, loadAll, hasUnsavedPlanChanges } = __h;").replace(/^export /gm, "");
  win = { esc: (s) => s };
  const __h = {
    api: async (url, opts) => {
      calls.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
      if (url === "/api/import/preview")
        return { will_write: true, datasets: { "plan-set": { rows_current: 3, rows_incoming: 5 } } };
      if (url.startsWith("/api/export/plan-set")) return { files: { "a.csv": "x,y" } };
      return {};
    },
    showMessage: (m, k) => messages.push([m, k]),
    showInAppConfirm: async (body) => ((confirmed.push(body)), confirmed.ok),
    loadAll: async () => loads++,
    hasUnsavedPlanChanges: () => unsaved,
  };
  const ctx = vm.createContext({ window: win, __h });
  vm.runInContext(src, ctx);
  return ctx;
}
const fileHandle = (text) => ({ kind: "file", getFile: async () => ({ text: async () => text }) });
const dirOf = (files) => ({
  entries: async function* () {
    for (const [n, t] of Object.entries(files)) yield [n, fileHandle(t)];
  },
});

describe("importPlanFolder", () => {
  beforeEach(() => {
    calls = [];
    messages = [];
    confirmed = [];
    confirmed.ok = true;
    unsaved = false;
    loads = 0;
  });

  test("posts only csv/json files, commits after confirm, then reloads", async () => {
    const ctx = load();
    win.showDirectoryPicker = async () => dirOf({ "a.csv": "1", "b.json": "2", "c.txt": "3" });
    await ctx.importPlanFolder();
    assert.deepEqual(Object.keys(calls[0].body.files).sort(), ["a.csv", "b.json"]);
    assert.deepEqual(calls.map((c) => c.url), ["/api/import/preview", "/api/import/commit"]);
    assert.equal(loads, 1);
    assert.match(confirmed[0], /3 current rows, 5 incoming/);
    assert.equal(messages.at(-1)[1], "success");
  });

  test("declining the confirm commits nothing", async () => {
    confirmed.ok = false;
    const ctx = load();
    win.showDirectoryPicker = async () => dirOf({ "a.csv": "1" });
    await ctx.importPlanFolder();
    assert.deepEqual(calls.map((c) => c.url), ["/api/import/preview"]);
    assert.equal(loads, 0);
  });

  test("unsaved edits are called out in the confirm body", async () => {
    unsaved = true;
    const ctx = load();
    win.showDirectoryPicker = async () => dirOf({ "a.csv": "1" });
    await ctx.importPlanFolder();
    assert.match(confirmed[0], /unsaved edits/);
  });

  test("empty folder and unsupported browser report errors without API calls", async () => {
    let ctx = load();
    win.showDirectoryPicker = async () => dirOf({ "c.txt": "3" });
    await ctx.importPlanFolder();
    assert.equal(calls.length, 0);
    assert.equal(messages.at(-1)[1], "error");
    ctx = load();
    await ctx.importPlanFolder();
    assert.match(messages.at(-1)[0], /cannot open folders/);
  });

  test("picker cancel (AbortError) is silent", async () => {
    const ctx = load();
    win.showDirectoryPicker = async () => { throw Object.assign(new Error("x"), { name: "AbortError" }); };
    await ctx.importPlanFolder();
    assert.equal(messages.length, 0);
  });
});

describe("exportPlanFolder", () => {
  test("writes each exported file into the chosen folder", async () => {
    calls = []; messages = [];
    const ctx = load();
    const written = {};
    win.showDirectoryPicker = async () => ({
      getFileHandle: async (name) => ({
        createWritable: async () => ({ write: async (t) => (written[name] = t), close: async () => {} }),
      }),
    });
    await ctx.exportPlanFolder();
    assert.deepEqual(written, { "a.csv": "x,y" });
    assert.equal(messages.at(-1)[1], "success");
  });
});
