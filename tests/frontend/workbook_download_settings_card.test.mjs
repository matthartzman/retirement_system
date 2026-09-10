// Ticket <workbook-filename>: Settings > Data & Maintenance gets a new
// "Workbook download" card controlling the configurable filename root and
// the desktop-app-only save folder. workbookDownloadControlsHtml() renders
// the card from cached settings; refreshWorkbookDownloadSettings()/
// saveWorkbookDownloadSettings() populate and persist that cache via
// /api/settings/workbook-download.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

function freshSandbox() {
  const sandbox = loadDashboardSandbox();
  sandbox.window.activeStep = "system_configuration";
  return sandbox;
}

describe("workbookDownloadControlsHtml", () => {
  test("renders the default filename root and an empty folder before any refresh", () => {
    const sandbox = freshSandbox();
    const html = sandbox.workbookDownloadControlsHtml();
    assert.match(html, /value="Retirement Workbook"/);
    assert.match(html, /id="workbookDownloadFolder"/);
  });
});

describe("refreshWorkbookDownloadSettings", () => {
  test("populates the cache from the API and re-renders while on Settings", async () => {
    const sandbox = freshSandbox();
    sandbox.api = async () => ({
      success: true,
      filename_root: "Smith Family Plan",
      desktop_download_folder: "D:/Reports",
    });
    let rendered = false;
    sandbox.window.renderMain = () => {
      rendered = true;
    };
    await sandbox.refreshWorkbookDownloadSettings(true);
    assert.equal(rendered, true);
    const html = sandbox.workbookDownloadControlsHtml();
    assert.match(html, /value="Smith Family Plan"/);
    assert.match(html, /value="D:\/Reports"/);
  });

  test("does not re-render when navigated away from Settings", async () => {
    const sandbox = freshSandbox();
    sandbox.window.activeStep = "start";
    sandbox.api = async () => ({ success: true, filename_root: "X", desktop_download_folder: "" });
    let rendered = false;
    sandbox.window.renderMain = () => {
      rendered = true;
    };
    await sandbox.refreshWorkbookDownloadSettings(true);
    assert.equal(rendered, false);
  });

  test("a failed fetch shows an error message (non-silent) and leaves settings unset", async () => {
    const sandbox = freshSandbox();
    sandbox.api = async () => {
      throw new Error("network down");
    };
    const messages = [];
    sandbox.showMessage = (msg, kind) => messages.push([msg, kind]);
    const result = await sandbox.refreshWorkbookDownloadSettings(false);
    assert.equal(result, null);
    assert.equal(messages.length, 1);
    assert.match(messages[0][0], /unavailable/);
    assert.equal(messages[0][1], "error");
  });
});

describe("saveWorkbookDownloadSettings", () => {
  test("posts the current field values and updates the cache on success", async () => {
    const sandbox = freshSandbox();
    const inputs = { workbookFilenameRoot: "My Plan", workbookDownloadFolder: "C:/Out" };
    sandbox.document.getElementById = (id) => (id in inputs ? { value: inputs[id] } : null);
    let posted = null;
    sandbox.api = async (url, opts) => {
      posted = { url, body: JSON.parse(opts.body) };
      return { success: true, filename_root: "My Plan", desktop_download_folder: "C:/Out" };
    };
    const messages = [];
    sandbox.showMessage = (msg, kind) => messages.push([msg, kind]);
    let rendered = false;
    sandbox.window.renderMain = () => {
      rendered = true;
    };
    await sandbox.saveWorkbookDownloadSettings();
    assert.equal(posted.url, "/api/settings/workbook-download");
    assert.deepEqual(posted.body, { filename_root: "My Plan", desktop_download_folder: "C:/Out" });
    assert.equal(rendered, true);
    assert.equal(messages[0][1], "success");
    const html = sandbox.workbookDownloadControlsHtml();
    assert.match(html, /value="My Plan"/);
  });

  test("shows the server's error message and does not update the cache on a rejected save", async () => {
    const sandbox = freshSandbox();
    sandbox.document.getElementById = (id) =>
      id === "workbookFilenameRoot" ? { value: "   " } : { value: "" };
    sandbox.api = async () => ({ success: false, error: "filename_root cannot be blank" });
    const messages = [];
    sandbox.showMessage = (msg, kind) => messages.push([msg, kind]);
    await sandbox.saveWorkbookDownloadSettings();
    assert.deepEqual(messages[0], ["filename_root cannot be blank", "error"]);
    // Cache untouched -- still the pre-save default.
    const html = sandbox.workbookDownloadControlsHtml();
    assert.match(html, /value="Retirement Workbook"/);
  });
});
