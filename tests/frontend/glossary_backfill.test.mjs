// T1e (system review 2026-07-21, D3): ~10 terms that exist only in the
// workbook glossary (src/reporting/sheets_qc_reference.py) and appear in
// on-screen narrative with no front-end definition must resolve via the
// front end's own acronymDefinitionsHtml() glossary lookup.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

const BACKFILLED_TERMS = [
  "Basis",
  "Credit-Shelter Trust",
  "ILIT",
  "Joint-and-Survivor",
  "Percentile Band",
  "SALT Cap",
  "Sec. 121 Exclusion",
  "Sequence-of-Returns Risk",
  "Spousal Rollover",
  "Standard Deduction",
  "Step-Up in Basis",
];

for (const term of BACKFILLED_TERMS) {
  test(`"${term}" resolves via acronymDefinitionsHtml()`, () => {
    const html = sandbox.acronymDefinitionsHtml([`Sentence mentioning ${term} in context.`]);
    assert.match(html, /Acronym definitions/);
    assert.ok(html.includes(`<b>${term}</b>:`), `expected a definition entry for "${term}", got: ${html}`);
  });
}
