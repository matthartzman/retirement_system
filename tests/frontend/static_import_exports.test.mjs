// Every static `import { a, b } from "./x.js"` in frontend/js must name an export x.js really has.
// The Node vm loaders strip imports, so only a real browser load caught a moved function (W4-06).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const JS_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "frontend", "js");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => {
  const p = path.join(d, e.name);
  return e.isDirectory() ? walk(p) : p.endsWith(".js") ? [p] : [];
});
const exportsOf = (src) => {
  const s = new Set([...src.matchAll(/^export (?:async )?(?:function|const|let|class)\s+(\w+)/gm)].map((m) => m[1]));
  for (const m of src.matchAll(/^export \{([^}]*)\}/gm)) for (const x of m[1].split(",")) if (x.trim()) s.add(x.split(" as ").pop().trim());
  return s;
};

test("every named static import resolves to an export of the imported module", () => {
  const files = walk(JS_DIR);
  const exp = new Map(files.map((f) => [f, exportsOf(fs.readFileSync(f, "utf8"))]));
  const missing = [];
  for (const f of files) {
    const src = fs.readFileSync(f, "utf8");
    for (const m of src.matchAll(/^import\s*\{([^}]*)\}\s*from\s*["'](\.[^"']+)["']/gm)) {
      const target = path.normalize(path.join(path.dirname(f), m[2]));
      for (const raw of m[1].split(",")) {
        const n = raw.split(" as ")[0].trim();
        if (n && !(exp.get(target) || new Set()).has(n)) missing.push(`${path.basename(f)} imports ${n} from ${m[2]}`);
      }
    }
  }
  assert.deepEqual(missing, []);
});
