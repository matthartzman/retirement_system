// #250: two bugs in the field-level help mechanism (tickets 219/220's
// superscript-i affordance, extended here to every field).
//
// 1. Clicking the "i" icon (or the field row) only ever wrote into
//    #helpPanel's innerHTML; it never re-showed the panel itself, which
//    autoCollapseHelpForNarrowLaptop() (U1) hides at typical laptop widths
//    (1181-1499px) via a `help-collapsed` class on <body>. The click did
//    something -- just nothing the user could see.
// 2. The icon was gated on a small hand-curated FIELD_TOOLTIPS dict (~30
//    entries), so most fields had no icon at all even though the full
//    explanation already exists for virtually every field via
//    fieldGuidance()/row.notes. Extending coverage risked surfacing raw
//    CSV notes that quote internal identifiers verbatim ("Gross in
//    earn_start_year") as user-facing hover text.
import { test, describe } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();
const { fieldTooltipPreview, fieldTooltipHtml, ensureHelpPanelVisible } = sandbox;

describe("ensureHelpPanelVisible", () => {
  test("removes help-collapsed from <body> so a hidden panel becomes visible", () => {
    const removed = [];
    sandbox.document.body.classList.remove = (cls) => removed.push(cls);
    ensureHelpPanelVisible();
    assert.deepEqual(removed, ["help-collapsed"]);
  });
});

describe("fieldTooltipPreview", () => {
  test("prefers a curated FIELD_TOOLTIPS entry when one exists", () => {
    const row = { label: "heloc_enabled", notes: "irrelevant", schema: {} };
    const tip = fieldTooltipPreview(row);
    assert.match(tip, /home-equity credit line/i);
  });

  test("falls back to row.notes when it reads as plain language", () => {
    const row = {
      label: "some_never_curated_field",
      notes: "Optional override for when this member's giving begins.",
      schema: {},
    };
    assert.equal(
      fieldTooltipPreview(row),
      "Optional override for when this member's giving begins.",
    );
  });

  test("skips notes that quote an internal identifier and uses fieldGuidance instead", () => {
    const row = {
      label: "annual_earned_income",
      section: "Cashflow",
      subsection: "Earned Income",
      notes: "Gross in earn_start_year",
      schema: {},
    };
    const tip = fieldTooltipPreview(row);
    assert.ok(tip, "expected a non-empty fallback tooltip");
    assert.doesNotMatch(tip, /earn_start_year/);
  });

  test("every field gets SOME tooltip text via the fieldGuidance fallback", () => {
    const row = { label: "totally_unmapped_field_xyz", section: "X", subsection: "Y", schema: {} };
    const tip = fieldTooltipPreview(row);
    assert.ok(tip && tip.length > 0, "fieldGuidance's default fallback should never be empty");
  });
});

describe("fieldTooltipHtml", () => {
  test("renders an icon for a field with no curated entry (broad coverage, not just ~30 fields)", () => {
    const row = {
      label: "some_never_curated_field",
      notes: "A perfectly ordinary explanation with no internal tokens.",
      schema: {},
    };
    const html = fieldTooltipHtml("some_never_curated_field", row);
    assert.match(html, /field-info-i/);
    assert.match(html, /A perfectly ordinary explanation/);
  });

  test("never emits a title containing a raw snake_case identifier", () => {
    const cases = [
      { label: "deferral_years", notes: "x", schema: {} },
      { label: "annual_earned_income", notes: "Gross in earn_start_year", schema: {} },
      { label: "entity_type", notes: "s_corp | sole_prop | W2", schema: {} },
    ];
    for (const row of cases) {
      const html = fieldTooltipHtml(row.label, row);
      const titleMatch = html.match(/title="([^"]*)"/);
      assert.ok(titleMatch, `expected a title attribute for ${row.label}`);
      assert.doesNotMatch(
        titleMatch[1],
        /[a-z][a-z0-9]*_[a-z0-9]+/,
        `tooltip for ${row.label} leaked an internal identifier: ${titleMatch[1]}`,
      );
    }
  });
});
