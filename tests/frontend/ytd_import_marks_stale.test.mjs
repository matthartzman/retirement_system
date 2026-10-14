// #345: YTD actions that write straight to the server (transaction import,
// delete-all, account-setup recover / roll-forward) change the plan's inputs,
// so the last build must be flagged stale -- otherwise the Rebuild button
// stays disabled after "import & replace".

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const dash = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, dash);

beforeEach(() => {
  run(`
    lastBuildOk = true;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
    api = async () => ({ added: 1, skipped: 0, total: 1, recovered: false });
    loadYtdStatus = async () => { ytdTransactionsChanged = false; ytdAccountsChanged = false; };
    renderMain = () => {};
    showMessage = () => {};
    showInAppConfirm = async () => true;
    showInAppPrompt = async () => "";
    ytdImportPreviewMessage = () => "preview";
  `);
});

const rebuildActive = () => run("reportsAndReviewCanBuild()");

describe("#345 server-side YTD writes mark the build stale", () => {
  test("baseline: a fresh build leaves Rebuild inactive", () => {
    assert.equal(rebuildActive(), false);
  });

  test("transaction import (replace) activates Rebuild", async () => {
    await run(`handleYtdTransactionUpload({ files: [{ text: async () => "Date,Amount\\n" }], value: "x" })`);
    assert.equal(run("lastBuildOk"), false);
    assert.equal(rebuildActive(), true);
  });

  test("a cancelled import does not mark the build stale", async () => {
    run("showInAppConfirm = async () => false;");
    await run(`handleYtdTransactionUpload({ files: [{ text: async () => "Date,Amount\\n" }], value: "x" })`);
    assert.equal(run("lastBuildOk"), true);
    assert.equal(rebuildActive(), false);
  });

  test("a failed import does not mark the build stale", async () => {
    run("api = async () => { throw new Error('boom'); };");
    await run(`handleYtdTransactionUpload({ files: [{ text: async () => "Date,Amount\\n" }], value: "x" })`);
    assert.equal(run("lastBuildOk"), true);
  });

  test("delete-all transactions activates Rebuild", async () => {
    await run("deleteAllYtdTransactions()");
    assert.equal(run("lastBuildOk"), false);
    assert.equal(rebuildActive(), true);
  });

  test("account-setup roll-forward activates Rebuild", async () => {
    await run("rollForwardYtdAccounts()");
    assert.equal(run("lastBuildOk"), false);
    assert.equal(rebuildActive(), true);
  });

  test("account-setup recover that recovers rows activates Rebuild", async () => {
    run("api = async () => ({ recovered: true, after: { rows: 3 } });");
    await run("recoverYtdAccountSetup()");
    assert.equal(run("lastBuildOk"), false);
    assert.equal(rebuildActive(), true);
  });
});
