// Ticket 297: reverting to a prior build-history snapshot failed with
// "Error reverting to snapshot: Plan Data validation failed".
//
// Root cause: a change record's `row_index` is only the field's position in
// the CSV files at the moment the change was captured (see _client_csv_rows
// in src/server/app_core.py -- it's a freshly recomputed running count, not
// a stable id). If any row is added or removed anywhere in the plan data
// between the snapshot and the revert -- including a totally unrelated
// "special" table-edit change bundled in the same snapshot -- every
// row_index downstream of that edit shifts. Replaying the snapshot's old
// row_index values then writes stale values into whatever field now
// happens to sit at that offset, which is usually the wrong type/section
// and fails schema validation.
//
// resolveCurrentRowIndex() re-locates each change by its stable
// (section, subsection, label) identity against the *current* rows list
// instead of trusting the stored row_index.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { resolveCurrentRowIndex } = sandbox;

describe("resolveCurrentRowIndex (ticket 297)", () => {
  test("finds the field's current row_index even after it has shifted", () => {
    // A row was inserted ahead of this field since the snapshot was taken,
    // so its row_index moved from 5 (recorded in the change) to 6 now.
    const currentRows = [
      { row_index: 4, section: "Household", subsection: "", label: "birth_year" },
      { row_index: 5, section: "Household", subsection: "", label: "new_inserted_row" },
      { row_index: 6, section: "Household", subsection: "", label: "retirement_age" },
    ];
    const change = {
      row_index: 5, // stale -- this is where the field used to live
      section: "Household",
      subsection: "",
      rawLabel: "retirement_age",
    };
    assert.equal(resolveCurrentRowIndex(currentRows, change), 6);
  });

  test("returns null when the field no longer exists (was removed)", () => {
    const currentRows = [
      { row_index: 0, section: "Household", subsection: "", label: "birth_year" },
    ];
    const change = {
      row_index: 5,
      section: "Household",
      subsection: "",
      rawLabel: "retirement_age",
    };
    assert.equal(resolveCurrentRowIndex(currentRows, change), null);
  });

  test("distinguishes fields with the same label in different sections", () => {
    const currentRows = [
      { row_index: 0, section: "Household", subsection: "Member 1", label: "birth_year" },
      { row_index: 1, section: "Household", subsection: "Member 2", label: "birth_year" },
    ];
    const change = {
      row_index: 9, // stale, unrelated to either current position
      section: "Household",
      subsection: "Member 2",
      rawLabel: "birth_year",
    };
    assert.equal(resolveCurrentRowIndex(currentRows, change), 1);
  });
});
