// Manage plans (multi-user server): the header gets a "Manage plans" button only when the server marks the plan
// list manageable; the menu offers only what the server would accept, and requests carry names, never ids or paths
// of the user's choosing (the server assigns plan ids).
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
const whatIf = mk("w1", "What if", {});
const demo = mk("demo", "Demo plan", { kind: "demo" });
const limits = { max_plans: 10, plan_count: 2, disk_quota_mb: 1024, disk_used_mb: 12.34 };
const values = (state) => j(sandbox.planManageChoices(state)).map((c) => c.value);

describe("header button", () => {
  test("Manage plans shows only when the server marks the list manageable", () => {
    const on = sandbox.planSwitcherHtml({ plans: [base], active: base, manageable: true, limits });
    const off = sandbox.planSwitcherHtml({ plans: [base], active: base, limits });
    assert.match(on, /onclick="openManagePlans\(\)">Manage plans<\/button>/);
    assert.doesNotMatch(off, /Manage plans/);
  });
});

describe("planUsageText", () => {
  test("shows usage against both limits, or just usage when unlimited", () => {
    assert.equal(sandbox.planUsageText(limits), "2 of 10 plans · 12.3 of 1024 MB used");
    assert.equal(sandbox.planUsageText({ plan_count: 3, disk_used_mb: 1 }), "3 plans · 1 MB used");
  });
});

describe("planManageChoices", () => {
  test("with room and two plans every action is offered", () => {
    assert.deepEqual(values({ plans: [base, whatIf], active: base, limits }), ["new-blank", "new-sample", "duplicate", "rename", "delete"]);
  });

  test("at the plan cap nothing new or copied is offered", () => {
    assert.deepEqual(values({ plans: [base, whatIf], active: base, limits: { ...limits, plan_count: 10 } }), ["rename", "delete"]);
  });

  test("a single plan cannot be deleted, and the demo is not counted or renamed", () => {
    assert.ok(!values({ plans: [base], active: base, limits }).includes("delete"));
    assert.ok(!values({ plans: [base, demo], active: base, limits }).includes("delete"));
    assert.ok(!values({ plans: [base, whatIf, demo], active: demo, limits }).includes("rename"));
  });

  test("delete is offered when another non-demo plan exists to delete", () => {
    assert.ok(values({ plans: [base, whatIf, demo], active: base, limits }).includes("delete"));
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
