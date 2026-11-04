// Nav/page search box: updateSearchToggle must not overwrite what is being typed. The debounced commit has not stored
// the new text yet, so writing the stored text back erased every keystroke (found in the running app, 2026-11-03).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const SRC = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js", "navigation.js"), "utf8");

function load(activeIsInput) {
  const input = { id: "combinedSearch", value: "", placeholder: "" };
  const document = {
    activeElement: activeIsInput ? input : null,
    getElementById: (id) => (id === "combinedSearch" ? input : null),
    querySelectorAll: () => [],
    addEventListener: () => {},
  };
  const window = { addEventListener: () => {}, document };
  vm.runInNewContext(SRC, { window, document, setTimeout, clearTimeout, console });
  return { nav: window.RetirementNavigation, input };
}
const ctx = { getSearchScope: () => "nav", getNavSearchText: () => "old", getSearchText: () => "old" };

test("typing in the search box keeps the typed text", () => {
  const { nav, input } = load(true);
  input.value = "ro";
  nav.updateSearchToggle(ctx);
  assert.equal(input.value, "ro");
  assert.equal(input.placeholder, "Search navigation...");
});

test("switching scope from a button still restores the stored text for that scope", () => {
  const { nav, input } = load(false);
  input.value = "zzz";
  nav.updateSearchToggle(ctx);
  assert.equal(input.value, "old");
});
