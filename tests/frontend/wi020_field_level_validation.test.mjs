// WI-020 (UX-004): a 422 save response with three field errors marks every server-flagged
// field visibly and programmatically (aria-invalid, an error text element wired through
// aria-describedby, an invalid style hook) and lists all three, each with a link, in a summary.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const ROWS = [
  { row_index: 11, section: "Household", subsection: "Person 1", label: "birth_year", value: "1970", units: "year", schema: { type: "integer" }, is_header: false },
  { row_index: 12, section: "Income", subsection: "Salary", label: "annual_amount", value: "abc", units: "$", schema: { type: "currency" }, is_header: false },
  { row_index: 13, section: "Estate", subsection: "Trust_1", label: "owner's_name", value: "", units: "", schema: { type: "text" }, is_header: false },
];

const ERRORS = [
  "('Household', 'Person 1', 'birth_year'): must be >= 1900; got '1700'",
  "('Income', 'Salary', 'annual_amount'): must be a number; got 'abc'",
  "('Estate', 'Trust_1', \"owner's_name\"): is required; got ''",
];

const FIELD_ERRORS = [
  { row_index: 11, section: "Household", subsection: "Person 1", label: "birth_year", message: "must be >= 1900", got: "'1700'", raw: ERRORS[0] },
  { row_index: 12, section: "Income", subsection: "Salary", label: "annual_amount", message: "must be a number", got: "'abc'", raw: ERRORS[1] },
  { row_index: 13, section: "Estate", subsection: "Trust_1", label: "owner's_name", message: "is required", got: "''", raw: ERRORS[2] },
];

function setup() {
  const sb = loadDashboardSandbox();
  const summary = { hidden: true, innerHTML: "", setAttribute() {}, focus() { summary.focused = true; }, scrollIntoView() {} };
  sb.document.getElementById = (id) => (id === "saveErrorSummary" ? summary : null);
  sb.rows = ROWS;
  vm.runInContext("rows = this.rows;", sb);
  return { sb, summary };
}

function checkThreeFieldsMarked(sb, summary) {
  for (const r of ROWS) {
    const html = sb.fieldHtml(r);
    assert.match(html, /aria-invalid="true"/, `row ${r.row_index} not aria-invalid`);
    const describedBy = /aria-describedby="([^"]*)"/.exec(html);
    assert.ok(describedBy && describedBy[1].split(" ").includes(`field-${r.row_index}-err`), `row ${r.row_index} describedby missing the error id`);
    assert.match(html, new RegExp(`id="field-${r.row_index}-err"`), "error text element missing");
    assert.match(html, /class="field [^"]*\binvalid\b/, "invalid style hook missing");
  }
  assert.match(sb.fieldHtml(ROWS[0]), /must be &gt;= 1900|must be >= 1900/);
  assert.match(sb.fieldHtml(ROWS[1]), /must be a number/);
  const links = summary.innerHTML.match(/goToInvalidField\((\d+)\)/g) || [];
  assert.deepEqual(links, ["goToInvalidField(11)", "goToInvalidField(12)", "goToInvalidField(13)"]);
  assert.match(summary.innerHTML, /3 problems/);
  assert.equal(summary.hidden, false);
  assert.equal(summary.focused, true, "focus moves to the summary after a failed save");
}

describe("422 with three field errors", () => {
  test("structured field_errors: three marked controls and a three-link summary", () => {
    const { sb, summary } = setup();
    const bad = sb.markSaveValidationErrors(ERRORS, FIELD_ERRORS);
    assert.deepEqual(Array.from(bad), [11, 12, 13]);
    checkThreeFieldsMarked(sb, summary);
  });

  test("string-only errors (older server) still produce the same result", () => {
    const { sb, summary } = setup();
    sb.markSaveValidationErrors(ERRORS, undefined);
    checkThreeFieldsMarked(sb, summary);
  });

  test("editing a flagged field clears only its own error; a successful save clears the rest", () => {
    const { sb, summary } = setup();
    sb.markSaveValidationErrors(ERRORS, FIELD_ERRORS);
    sb.clearFieldSaveError(11);
    assert.doesNotMatch(sb.fieldHtml(ROWS[0]), /aria-invalid|field-11-err/);
    assert.match(sb.fieldHtml(ROWS[1]), /aria-invalid="true"/);
    assert.match(summary.innerHTML, /2 problems/);
    sb.clearSaveValidationErrors();
    assert.equal(summary.hidden, true);
    assert.doesNotMatch(sb.fieldHtml(ROWS[1]), /field-12-err/);
  });

  test("an error the server cannot tie to a field is listed in the summary without a link", () => {
    const { sb, summary } = setup();
    sb.markSaveValidationErrors(["('Large Discretionary Expenses','Trip','repeat_start_year/repeat_end_year'): start year must be <= end year"], [
      { message: "start year must be <= end year", raw: "x" },
    ]);
    assert.match(summary.innerHTML, /1 problem\b/);
    assert.match(summary.innerHTML, /start year must be &lt;= end year/);
    assert.doesNotMatch(summary.innerHTML, /goToInvalidField/);
  });

  test("api_client attaches the structured list to the thrown error", async () => {
    const fs = await import("node:fs");
    const src = fs.readFileSync(new URL("../../frontend/js/api_client.js", import.meta.url), "utf8");
    assert.match(src, /err\.fieldErrors\s*=\s*data\.field_errors/);
  });
});

describe("estate add flows choose enumerated values (UX-010)", () => {
  function estateSetup() {
    const sb = loadDashboardSandbox();
    const prompts = [];
    const posted = [];
    vm.runInContext("planLoaded = true; dirty.clear();", sb);
    sb.showInAppPrompt = async (msg, def, opts) => {
      prompts.push({ msg, def, opts });
      return opts.choices ? (typeof opts.choices[1] === "object" ? opts.choices[1].value : opts.choices[1]) : "Trust A";
    };
    sb.api = async (p, o) => {
      posted.push([p, o && o.body]);
      return { message: "ok" };
    };
    sb.loadAll = async () => {};
    sb.showMessage = () => {};
    return { sb, prompts, posted };
  }
  test("Add trust account: trust type is a choice among the six types, no silent default", async () => {
    const { sb, prompts, posted } = estateSetup();
    await sb.addTrustAccount();
    const typePrompt = prompts[1];
    assert.deepEqual(Array.from(typePrompt.opts.choices), ["Revocable", "Irrevocable", "Credit Shelter", "QTIP", "Special Needs", "Other"]);
    assert.equal(JSON.parse(posted[0][1]).trust_type, "Irrevocable");
  });
  test("Add estate state: the state is chosen from the 50 states plus DC", async () => {
    const { sb, prompts } = estateSetup();
    await sb.addEstateState();
    const choices = Array.from(prompts[0].opts.choices);
    assert.equal(choices[0].value, "", "first option is the empty placeholder");
    assert.equal(choices.length, 52);
    assert.ok(choices.some((c) => c.value === "District of Columbia"));
  });
});
