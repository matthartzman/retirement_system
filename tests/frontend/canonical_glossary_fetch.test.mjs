// T3e (system review 2026-07-21, D3): the front end must merge the server's
// canonical glossary (GET /api/glossary, backed by src/glossary.py) over its
// local ACRONYM_DEFINITIONS fallback on load, so the two surfaces (in-app
// help panels and the workbook's Glossary sheet) can't drift apart again.
import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

// ACRONYM_DEFINITIONS is a top-level `const`, so (like STEPS elsewhere) it
// isn't a property of the sandbox object the way `function`-declared helpers
// are -- but the sandbox is already a vm-contextified object, so it can be
// read/reset directly.
function acronymDefinitions() {
  return vm.runInContext("ACRONYM_DEFINITIONS", sandbox);
}

let snapshot;

beforeEach(() => {
  // Snapshot once, restore before each test so tests don't see each other's
  // Object.assign mutations (ACRONYM_DEFINITIONS is shared, mutable state).
  if (!snapshot) snapshot = { ...acronymDefinitions() };
  const current = acronymDefinitions();
  for (const key of Object.keys(current)) delete current[key];
  Object.assign(current, snapshot);
});

describe("loadCanonicalGlossary", () => {
  test("merges server terms over the local fallback, overwriting duplicates", async () => {
    const originalIrmaa = acronymDefinitions().IRMAA;
    sandbox.api = (path) => {
      assert.equal(path, "/api/glossary");
      return Promise.resolve({
        success: true,
        schema: "glossary_v1",
        terms: {
          IRMAA: "Reconciled IRMAA definition from the server",
          "Brand New Term": "A term only the server knows about",
        },
      });
    };

    await sandbox.loadCanonicalGlossary();

    const defs = acronymDefinitions();
    assert.equal(defs.IRMAA, "Reconciled IRMAA definition from the server");
    assert.notEqual(defs.IRMAA, originalIrmaa);
    assert.equal(defs["Brand New Term"], "A term only the server knows about");
    // Terms the fetch didn't mention are untouched, not wiped.
    assert.equal(defs.RMD, "Required minimum distribution");
  });

  test("degrades silently to the local fallback if the fetch fails", async () => {
    const before = { ...acronymDefinitions() };
    sandbox.api = () => Promise.reject(new Error("offline"));

    await assert.doesNotReject(() => sandbox.loadCanonicalGlossary());
    // Spread both sides into this realm's plain object before comparing --
    // ACRONYM_DEFINITIONS lives in the vm sandbox's separate realm, and
    // deepStrictEqual treats cross-realm objects as unequal even with
    // identical own properties (different Object.prototype).
    assert.deepEqual({ ...acronymDefinitions() }, before);
  });

  test("degrades silently if the response shape is unexpected", async () => {
    const before = { ...acronymDefinitions() };
    sandbox.api = () => Promise.resolve({ success: false });

    await sandbox.loadCanonicalGlossary();
    // Spread both sides into this realm's plain object before comparing --
    // ACRONYM_DEFINITIONS lives in the vm sandbox's separate realm, and
    // deepStrictEqual treats cross-realm objects as unequal even with
    // identical own properties (different Object.prototype).
    assert.deepEqual({ ...acronymDefinitions() }, before);
  });
});
