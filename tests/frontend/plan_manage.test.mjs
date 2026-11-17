// Manage plans (multi-user server): the header gets a "Manage plans" button only when the server says the
// plan list is manageable; the dialog lists every plan with Rename / Duplicate / Delete, disables what the
// server would refuse, and builds name-only request bodies (the server assigns plan ids).
//
// Run with: node --test tests/frontend/

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

// the sandbox is another realm: compare plain JSON, not prototypes
const j = (v) => JSON.parse(JSON.stringify(v));
const mk = (id, name, extra = {}) => ({ plan_id: id, name, kind: "user", active: false, exists: true, ...extra });
const base = mk("plan", "Base case", { active: true });
const whatIf = mk("w1", "What if <b>", {});
const demo = mk("demo", "Demo plan", { kind: "demo" });
const limits = { max_plans: 10, plan_count: 2, disk_quota_mb: 1024, disk_used_mb: 12.34 };

describe("header button", () => {
  test("Manage plans shows only when the server marks the list manageable", () => {
    const on = sandbox.planSwitcherHtml({ plans: [base], active: base, manageable: true, limits });
    const off = sandbox.planSwitcherHtml({ plans: [base], active: base, limits });
    assert.match(on, /onclick="openManagePlans\(\)">Manage plans<\/button>/);
    assert.doesNotMatch(off, /Manage plans/);
  });
});

describe("managePlansHtml", () => {
  const html = sandbox.managePlansHtml({ plans: [base, whatIf, demo], limits });

  test("shows usage against both limits", () => {
    assert.equal(sandbox.planUsageText(limits), "2 of 10 plans · 12.3 of 1024 MB used");
    assert.equal(sandbox.planUsageText({ plan_count: 3, disk_used_mb: 1 }), "3 plans · 1 MB used");
    assert.match(html, /2 of 10 plans/);
  });

  test("plan names are escaped", () => {
    assert.match(html, /What if &lt;b&gt;/);
    assert.doesNotMatch(html, /What if <b>/);
  });

  test("the active plan and the demo cannot be deleted; others can", () => {
    assert.match(html, /data-plan-act="delete" data-plan-id="plan" disabled/);
    assert.match(html, /data-plan-act="delete" data-plan-id="w1">/);
    assert.doesNotMatch(html, /data-plan-id="demo"/); // the demo has no rename, duplicate or delete
  });

  test("a user's only plan cannot be deleted", () => {
    const solo = sandbox.managePlansHtml({ plans: [mk("p", "Only", { active: true })], limits: { ...limits, plan_count: 1 } });
    assert.match(solo, /data-plan-act="delete" data-plan-id="p" disabled/);
  });

  test("at the plan cap New and Duplicate are disabled and the reason is shown", () => {
    const full = sandbox.managePlansHtml({ plans: [base, whatIf], limits: { ...limits, plan_count: 10 } });
    assert.match(full, /data-plan-act="new-blank" disabled/);
    assert.match(full, /data-plan-act="new-sample" disabled/);
    assert.match(full, /data-plan-act="duplicate" data-plan-id="w1" disabled/);
    assert.match(full, /reached the plan limit/);
    assert.doesNotMatch(html, /data-plan-act="new-blank" disabled/);
  });

  test("a plan whose file is missing cannot be duplicated", () => {
    const gone = mk("g", "Gone", { exists: false });
    const out = sandbox.managePlansHtml({ plans: [base, gone], limits });
    assert.match(out, /data-plan-act="duplicate" data-plan-id="g" disabled/);
    assert.match(out, /Gone \(file missing\)/);
  });
});

describe("planManageRequest", () => {
  test("create sends a name and a source, never an id or a path", () => {
    assert.deepEqual(j(sandbox.planManageRequest("create", null, { name: "N", from: "demo" })), {
      url: "/api/plans/create",
      body: { name: "N", from: "demo" },
    });
    assert.equal(sandbox.planManageRequest("create", null, { name: "N" }).body.from, "blank");
  });

  test("duplicate, rename and delete carry the plan id; delete carries the typed name", () => {
    assert.deepEqual(j(sandbox.planManageRequest("duplicate", whatIf, { name: "C" }).body), { plan_id: "w1", name: "C" });
    assert.deepEqual(j(sandbox.planManageRequest("rename", whatIf, { name: "R" }).body), { plan_id: "w1", name: "R" });
    assert.deepEqual(j(sandbox.planManageRequest("delete", whatIf, { name: "typed" })), {
      url: "/api/plans/delete",
      body: { plan_id: "w1", confirm_name: "typed" },
    });
  });

  test("an unknown action builds no request", () => {
    assert.equal(sandbox.planManageRequest("forget", whatIf, {}), null);
  });
});
