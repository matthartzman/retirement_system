// WI-019 (UX-002, ARC-003): the build overlay never claims a cancellation that did not happen,
// a build the user hid does not navigate them away when it finishes, and the swallowed-step
// warnings (config_contract_warnings, WI-007) reach the build result banner.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const FRONTEND = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend");

function deferred() {
  let resolve, reject;
  const promise = new Promise((res, rej) => ((resolve = res), (reject = rej)));
  return { promise, resolve, reject };
}

function setup() {
  const sb = loadDashboardSandbox();
  const calls = { nav: [], messages: [] };
  const build = deferred();
  sb.validateAllocationTargetsOrMessage = () => true;
  sb.captureBuildBaseline = async () => ({});
  sb.saveWorkingCopy = async () => true;
  sb.api = async () => ({ blockers: [], warnings: [] });
  sb.updatePlanStateBanner = () => {};
  sb.setAppControls = () => {};
  sb.buildWithProgress = () => build.promise;
  sb.refreshBuildStatus = async () => ({});
  sb.rememberBuildCompare = () => {};
  sb.maybeRunLocalBackup = () => {};
  sb.renderMain = () => {};
  sb.renderBuildImpactAfterBuild = (m, step) => calls.nav.push([m, step]);
  sb.showMessage = (m, kind, opts) => calls.messages.push([m, kind, opts]);
  sb.showInAppConfirm = async () => true;
  vm.runInContext('planLoaded = true; activeStep = "household_people";', sb);
  return { sb, calls, build };
}

const OK = { success: true, kpi: { qc_result: "QC: 1 / 1 PASS", lcv: 1 }, qc_result: "QC: 1 / 1 PASS" };

describe("hiding a running build", () => {
  test("cancelBuild is gone and nothing claims the build was cancelled", () => {
    const sb = loadDashboardSandbox();
    assert.equal(typeof sb.cancelBuild, "undefined");
    const html = fs.readFileSync(path.join(FRONTEND, "index.html"), "utf8");
    assert.doesNotMatch(html, /cancelBuild/);
    assert.match(html, /hideBuildInBackground\(\)/);
    const src = fs.readFileSync(path.join(FRONTEND, "js", "dashboard_decomp_build_lifecycle.js"), "utf8");
    assert.doesNotMatch(src, /Build cancelled|left incomplete/);
  });

  test("pending build, hide, resolve: no navigation and an accurate message", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    sb.hideBuildInBackground();
    assert.ok(calls.messages.some(([m]) => /still running in the background/.test(m)));
    build.resolve(OK);
    await run;
    assert.equal(calls.nav.length, 0, "must not navigate to Build Impact after the user hid the build");
    assert.equal(vm.runInContext("activeStep", sb), "household_people");
    const last = calls.messages[calls.messages.length - 1];
    assert.match(last[0], /Build finished in the background/);
    assert.equal(last[2].action.label, "View Impact & Build History");
    assert.ok(!calls.messages.some(([m]) => /cancel/i.test(m)));
  });

  test("a second build cannot start while a hidden one runs", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    sb.hideBuildInBackground();
    assert.equal(await sb.runBuild(false), false);
    assert.ok(calls.messages.some(([m, k]) => /already running/.test(m) && k === "warn"));
    build.resolve(OK);
    await run;
    // finished: a new build may start again
    assert.equal(vm.runInContext("buildInFlight", sb), false);
  });

  test("not hidden: the normal flow still navigates to Build Impact", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    build.resolve(OK);
    await run;
    assert.equal(calls.nav.length, 1);
    assert.match(calls.nav[0][0], /Build successful/);
  });

  test("a hidden build that fails reports an error and clears the in-flight flag", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    sb.hideBuildInBackground();
    build.reject(new Error("engine exploded"));
    await run;
    assert.ok(calls.messages.some(([m, k]) => /engine exploded/.test(m) && k === "error"));
    assert.equal(vm.runInContext("buildInFlight", sb), false);
  });
});

describe("build warnings (ARC-003)", () => {
  test("warnings from the build result are shown in the banner message and the Impact page banner", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    build.resolve({ ...OK, warnings: ["PlanResult contract build failed: boom <b>", "ReportSpec contract build failed: x"] });
    await run;
    const warn = calls.messages.find(([m, k]) => k === "warn" && /2 warnings/.test(m));
    assert.ok(warn, JSON.stringify(calls.messages));
    assert.match(warn[0], /PlanResult contract build failed: boom/);
    assert.equal(warn[2].persistent, true);
    const html = sb.buildWarningsBannerHtml();
    assert.match(html, /2 warnings/);
    assert.match(html, /ReportSpec contract build failed: x/);
    assert.doesNotMatch(html, /<b>\s*<\/li>|boom <b>/, "warning text must be escaped");
  });

  test("a clean build has no banner and the plain success message", async () => {
    const { sb, calls, build } = setup();
    const run = sb.runBuild(false);
    await new Promise((r) => setImmediate(r));
    build.resolve({ ...OK, warnings: [] });
    await run;
    assert.equal(sb.buildWarningsBannerHtml(), "");
    assert.match(calls.nav[0][0], /Build successful/);
  });
});

describe("overlay button scope", () => {
  test("only the build overlay offers Hide; other shared popups get no-cancel", () => {
    const sb = loadDashboardSandbox();
    const classes = new Set();
    const overlay = {
      style: {},
      classList: {
        add: (c) => classes.add(c),
        remove: (c) => classes.delete(c),
        toggle: (c, on) => (on ? classes.add(c) : classes.delete(c)),
        contains: (c) => classes.has(c),
      },
      setAttribute() {},
    };
    sb.document.getElementById = (id) => (id === "buildOverlay" ? overlay : { style: {}, classList: overlay.classList, setAttribute() {}, textContent: "" });
    vm.runInContext("buildOverlayDepth = 0;", sb);
    sb.setBuildOverlay(true, "Loading plan", "", "waiting", "loadPlan");
    assert.ok(classes.has("no-cancel"));
    sb.hideBuildOverlay();
    sb.setBuildOverlay(true, "Preparing build", "", 0, "build");
    assert.ok(!classes.has("no-cancel"));
    sb.hideBuildOverlay();
  });
});
