import { readFileSync, readdirSync } from "node:fs";
import test from "node:test"; import assert from "node:assert";
test("no 'Annualized Actual' copy in frontend", () => {
  for (const f of readdirSync("frontend/js").filter((x) => x.endsWith(".js"))) {
    assert.ok(!/Annualized Actual/.test(readFileSync(`frontend/js/${f}`, "utf8")), f);
  }
});
