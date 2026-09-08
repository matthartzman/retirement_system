// Storage identifiers must never reach the screen. Subsection keys like
// SN_Beneficiary, PC_Homeowner, DI_Group_Matthew, Grandchild_A_529, ISO_2023,
// buffer_1 and Member_1_401k used to be printed verbatim as section headings
// (and the Beneficiary & Titling panel additionally echoed the raw account key
// in parentheses next to the display name). humanizeGroupKey() turns each into
// real copy, and anything unrecognized still gets underscores-to-words rather
// than leaking raw.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { humanizeGroupKey } = sandbox;

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DASHBOARD_JS_PATH = path.join(__dirname, "..", "..", "frontend", "js", "dashboard.js");

// A rendered heading should never look like snake_case.
const LOOKS_INTERNAL = /[a-z0-9]_[a-z0-9]/i;

describe("humanizeGroupKey maps storage keys to display copy", () => {
  const CASES = {
    SN_Beneficiary: "Special-Needs Beneficiary",
    SN_Trust: "Special-Needs Trust",
    SN_ABLE: "ABLE Account",
    SN_GovBenefits: "Government Benefits",
    PC_Homeowner: "Homeowners Policy",
    PC_Auto: "Auto Policy",
    PC_Umbrella: "Umbrella Policy",
    PC_Targets: "Coverage Targets",
    DI_Scenario: "Disability Scenario",
    Life_1: "Life Policy 1",
    ISO_2023: "ISO Grant (2023)",
    RSU_2024: "RSU Grant (2024)",
    Grandchild_A_529: "Grandchild A — 529 Plan",
    Grandchild_A_Goal: "Grandchild A — Education Goal",
    buffer_1: "Reserve Rule 1",
    next_step_2: "Housing Step 2",
    Divorce_Alimony: "Alimony",
    Divorce_Property: "Property Division",
    Acme_Holdings: "Acme Holdings",
    Business_Checking: "Business Checking",
    Family_Checking: "Family Checking",
  };

  for (const [key, expected] of Object.entries(CASES)) {
    test(`${key} -> ${expected}`, () => {
      assert.equal(humanizeGroupKey(key), expected);
    });
  }
});

describe("humanizeGroupKey never emits a snake_case heading", () => {
  const KEYS = [
    "SN_Beneficiary", "PC_Homeowner", "DI_Group_Someone", "Life_Whole_Someone",
    "Life_Term_Someone", "ISO_2023", "Grandchild_A_529", "buffer_3",
    "next_step_1", "Acme_Holdings", "Business_Checking", "Member_1_401k",
    "Some_Brand_New_Key", "another_unmapped_key",
  ];
  for (const k of KEYS) {
    test(`${k} renders without an underscore`, () => {
      const out = humanizeGroupKey(k);
      assert.ok(out, `${k} produced empty output`);
      assert.ok(
        !LOOKS_INTERNAL.test(out),
        `humanizeGroupKey(${k}) leaked an internal-looking name: ${out}`,
      );
    });
  }
});

describe("FIELD_GUIDANCE_OVERRIDES help text never leaks internal config keys/enum literals", () => {
  // Finding DOC-203 (system review 2026-09-07, Wave 5 item W5-4): the
  // PHASE_VARYING Roth conversion help text surfaced raw internal config
  // keys (roth_phase_count, roth_phase_first_bracket_rate) and the literal
  // strategy enum value "PHASE_VARYING" directly to end users -- the same
  // pattern (D3) a prior review removed elsewhere, recurring on this new
  // surface. humanizeGroupKey() (above) can't catch this: it maps section-
  // heading KEYS to display copy, not arbitrary internal identifiers
  // embedded inside free-text help strings. This is a source-text scan
  // instead, run directly against the real file (not a hand-copied
  // fixture) so it can't silently drift from what ships.
  const FORBIDDEN_TOKENS = [
    "roth_phase_count",
    "roth_phase_first_bracket_rate",
    "roth_phase_second_bracket_rate",
    "roth_phase_third_bracket_rate",
    "PHASE_VARYING",
  ];
  const ENTRY_KEYS = [
    "roth_phase_count",
    "roth_phase_first_bracket_rate",
    "roth_phase_second_bracket_rate",
    "roth_phase_third_bracket_rate",
  ];

  const src = fs.readFileSync(DASHBOARD_JS_PATH, "utf8");

  for (const key of ENTRY_KEYS) {
    // Extract just this one entry's object body (from `key: {` to its
    // closing `},`) so a forbidden token elsewhere in the file (e.g. this
    // very guard's own FORBIDDEN_TOKENS list, or the config-row definition
    // that legitimately names the key) can never produce a false positive.
    const startMarker = `${key}: {`;
    const startIdx = src.indexOf(startMarker);
    test(`${key} entry exists in FIELD_GUIDANCE_OVERRIDES`, () => {
      assert.ok(startIdx !== -1, `could not find a "${startMarker}" entry in dashboard.js`);
    });
    if (startIdx === -1) continue;
    const bodyStart = startIdx + startMarker.length;
    const endIdx = src.indexOf("},", bodyStart);
    const entryBody = src.slice(bodyStart, endIdx === -1 ? undefined : endIdx);

    for (const token of FORBIDDEN_TOKENS) {
      test(`${key} help text does not mention "${token}"`, () => {
        assert.ok(
          !entryBody.includes(token),
          `dashboard.js's ${key} help text still contains the internal token "${token}"`,
        );
      });
    }
  }
});

describe("humanizeGroupKey leaves display copy untouched", () => {
  for (const s of ["Home", "529 Plan 1", "Member 1 Joint Annuity", "Settings", ""]) {
    test(`${JSON.stringify(s)} passes through`, () => {
      assert.equal(humanizeGroupKey(s), s);
    });
  }
});
