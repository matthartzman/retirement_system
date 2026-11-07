// Note Receivable installment-sale inputs show the Form 8949 names, not the raw keys
// (design: documentation/future/superpowers/plans/2026-11-06-note-installment-gain-tax-design-and-plan.md 4.1).
import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const { humanLabel } = loadDashboardSandbox();
const row = (label) => ({ section: "Note Receivable", subsection: "Note 1", label });

describe("note installment labels", () => {
  test("the four 8949 fields name their part and column", () => {
    assert.equal(humanLabel("st_proceeds", row("st_proceeds")), "Short-term proceeds per payment (8949 Part I)");
    assert.equal(humanLabel("st_basis", row("st_basis")), "Short-term basis per payment (8949 Part I)");
    assert.equal(humanLabel("lt_proceeds", row("lt_proceeds")), "Long-term proceeds per payment (8949 Part II)");
    assert.equal(humanLabel("lt_basis", row("lt_basis")), "Long-term basis per payment (8949 Part II)");
  });
});
