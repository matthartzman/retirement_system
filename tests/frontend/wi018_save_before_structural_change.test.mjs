// WI-018 (UX-001, UX-011): every in-page add/delete/seed handler must save staged
// edits BEFORE its structural API call (loadAll() would otherwise drop them), abort when
// that save fails, and folder import must refresh the plan afterwards.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const JS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js");

// name -> [handler args, expected structural API path]
const HANDLERS = {
  addOtherAssetItem: [[], "/api/other-asset/add"],
  deleteOtherAssetItem: [["Auto_1"], "/api/other-asset/delete"],
  addNoteReceivable: [[], "/api/note-receivable/add"],
  deleteNoteReceivable: [["Note_1"], "/api/note-receivable/delete"],
  addEducation529Section: [[], "/api/education-529/add"],
  addEstateState: [["CA"], "/api/estate-state/add"],
  addInsurancePolicy: [[], "/api/insurance-policy/add"],
  deleteInsurancePolicy: [[null, "Life_1"], "/api/insurance-policy/delete"],
  seedHousingRows: [[], "/api/housing/seed"],
};

function setup({ saveResult = true, saveThrows = null } = {}) {
  const sb = loadDashboardSandbox();
  const log = [];
  vm.runInContext("planLoaded = true; dirty.clear(); dirty.set(7, '123');", sb);
  sb.saveWorkingCopy = async () => {
    log.push("save:" + vm.runInContext("dirty.size", sb));
    if (saveThrows) throw saveThrows;
    return saveResult;
  };
  sb.api = async (p) => {
    log.push("api:" + p);
    return { message: "ok", seeded: 1, section: "Life_1" };
  };
  sb.loadAll = async () => log.push("loadAll");
  sb.renderMain = () => {};
  sb.setStep = () => {};
  sb.showInAppConfirm = async () => true;
  sb.showInAppPrompt = async () => "x";
  sb.messages = [];
  sb.showMessage = (m, kind) => sb.messages.push([m, kind]);
  return { sb, log };
}

describe("add/delete/seed handlers save staged edits first", () => {
  for (const [name, [args, apiPath]] of Object.entries(HANDLERS)) {
    test(`${name}: save precedes the mutation and the edit is still staged at save`, async () => {
      const { sb, log } = setup();
      await sb[name](...args);
      const iSave = log.findIndex((e) => e.startsWith("save:"));
      const iApi = log.indexOf("api:" + apiPath);
      assert.ok(iSave >= 0, `${name} never saved: ${log}`);
      assert.ok(iApi > iSave, `${name}: save must precede ${apiPath}: ${log}`);
      assert.equal(log[iSave], "save:1");
    });
    test(`${name}: a failed save aborts the mutation`, async () => {
      const { sb, log } = setup({ saveResult: false });
      await sb[name](...args);
      assert.ok(!log.includes("api:" + apiPath), `${name} mutated despite failed save: ${log}`);
      assert.ok(!log.includes("loadAll"));
    });
  }

  test("addTrustAccount aborts on a 422 save error and shows the field-aware message", async () => {
    const err = Object.assign(new Error("Plan Data validation failed"), { errors: ["bad"] });
    const { sb, log } = setup({ saveThrows: err });
    await sb.addTrustAccount();
    assert.ok(!log.includes("api:/api/trust-account/add"));
    assert.ok(sb.messages.some(([m, k]) => /Error saving/.test(m) && k === "error"));
  });

  test("addTrustAccount saves before adding", async () => {
    const { sb, log } = setup();
    await sb.addTrustAccount();
    assert.ok(log.findIndex((e) => e.startsWith("save:")) < log.indexOf("api:/api/trust-account/add"));
  });

  test("no staged edits: no save is attempted", async () => {
    const { sb, log } = setup();
    vm.runInContext("dirty.clear()", sb);
    await sb.addNoteReceivable();
    assert.ok(!log.some((e) => e.startsWith("save:")));
    assert.ok(log.includes("api:/api/note-receivable/add"));
  });
});

describe("importPlanFolder (UX-011)", () => {
  function loadImporter({ confirm = true, unsaved = false } = {}) {
    let src = fs.readFileSync(path.join(JS_DIR, "dashboard_plan_folder_io.js"), "utf8");
    src = src.replace(/^import .*$/m, "").replace(/^export /gm, "").replace(/Object\.assign\(window,[\s\S]*$/m, "");
    const log = [];
    const sb = {
      window: {
        showDirectoryPicker: async () => ({
          entries: async function* () {
            yield ["a.csv", { kind: "file", getFile: async () => ({ text: async () => "x" }) }];
          },
        }),
        esc: (s) => s,
      },
      console,
      api: async (p) => {
        log.push(p);
        return p.endsWith("preview")
          ? { datasets: { plan: { rows_current: 2, rows_incoming: 3 } }, will_write: true, errors: 0 }
          : {};
      },
      showMessage: (m) => log.push("msg:" + m),
      showInAppConfirm: async (body, o) => {
        log.push("confirm:" + body + "|" + o.variant);
        return confirm;
      },
      loadAll: async () => log.push("loadAll"),
      hasUnsavedPlanChanges: () => unsaved,
    };
    vm.createContext(sb);
    vm.runInContext(src + "\nthis.importPlanFolder = importPlanFolder;", sb);
    return { sb, log };
  }
  test("commit is followed by loadAll before the success message", async () => {
    const { sb, log } = loadImporter();
    await sb.importPlanFolder();
    const iCommit = log.indexOf("/api/import/commit");
    assert.ok(iCommit >= 0);
    assert.equal(log[iCommit + 1], "loadAll");
    assert.match(log[iCommit + 2], /^msg:Imported 1 dataset/);
  });
  test("declined confirm commits nothing and does not reload", async () => {
    const { sb, log } = loadImporter({ confirm: false });
    await sb.importPlanFolder();
    assert.ok(!log.includes("/api/import/commit"));
    assert.ok(!log.includes("loadAll"));
  });
  test("dirty edits produce a visible warning in the confirm", async () => {
    const { sb, log } = loadImporter({ unsaved: true });
    await sb.importPlanFolder();
    const c = log.find((e) => e.startsWith("confirm:"));
    assert.match(c, /unsaved edits/);
    assert.match(c, /2 current rows, 3 incoming/);
  });
});
