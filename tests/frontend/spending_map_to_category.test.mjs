// "Map to category" on the unmapped-categories warning (spending_dashboard.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const src = fs
  .readFileSync(path.join(HERE, "..", "..", "frontend", "js", "spending_dashboard.js"), "utf8")
  .replace(/^export /gm, "");
const sb = { console, window: {}, esc: (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"), renderMain() {}, api() { return Promise.resolve({}); } };
sb.window = sb;
vm.createContext(sb);
vm.runInContext(src, sb);

test("existing category -> exact category alias on raw text", () => {
  const r = sb.spendMapRequest("  Mystery Category ", { mode: "existing", category_id: "groceries" });
  assert.equal(r.path, "/api/spending/alias");
  assert.deepEqual({ ...r.body }, { match_value: "Mystery Category", match_field: "category", exact: true, category_id: "groceries" });
});
test("new category -> create route with alias fields", () => {
  const r = sb.spendMapRequest("Mystery", { mode: "new", tracking_type: "Core Expenses", group: "Fun", label: "Mystery" });
  assert.equal(r.path, "/api/spending/category");
  assert.equal(r.body.match_value, "Mystery");
  assert.equal(r.body.exact, true);
  assert.equal(r.body.group, "Fun");
});
test("validation errors", () => {
  assert.ok(sb.spendMapRequest("x", { mode: "existing", category_id: "" }).error);
  assert.ok(sb.spendMapRequest("x", { mode: "new", label: "a", group: "", tracking_type: "t" }).error);
  assert.ok(sb.spendMapRequest("", { mode: "existing", category_id: "a" }).error);
});
test("warning renders a button per category; picker groups by Tracking Type > Group", () => {
  const html = sb.renderUnmappedWarning({ unmapped_categories: ["A", "B"] });
  assert.equal((html.match(/Map to category<\/button>/g) || []).length, 2);
  const opts = sb.spendMapOptionsHtml([{ tracking_type: "Core Expenses", groups: [{ group: "Food", categories: [{ id: "g", label: "Groceries" }] }, { group: "Empty", categories: [] }] }]);
  assert.match(opts, /optgroup label="Core Expenses &gt; Food"/);
  assert.match(opts, /value="g">Groceries/);
  assert.ok(!/Empty/.test(opts));
  assert.equal(sb.renderUnmappedWarning({ unmapped_categories: [] }), "");
});
