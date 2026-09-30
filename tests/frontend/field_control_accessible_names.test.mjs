// UX-002 (system review 2026-09-25, Wave 5 item WI-503): plan-data fields
// rendered by fieldHtml() had their visible label in a <div>, with no id on
// the control and no <label for>/aria-labelledby -- a screen reader announced
// "edit text" (or the placeholder default), an unnamed combo box, or a
// checkbox named "YES"/"NO" from the toggle's own text. Admin settings
// (admin.js settingControl) had the same gap.
//
// This renders the real fieldHtml()/buildSectionSettings() output from the
// production source and computes each control's accessible name the way a
// browser would for these markup shapes (aria-labelledby first, then
// <label for>), plus required state and description wiring.

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);

function stripTags(html) {
  return html.replace(/<[^>]*aria-hidden="true"[^>]*>[^<]*<\/[a-z]+>/g, "").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
}

function textOfId(html, id) {
  const re = new RegExp(`<([a-z]+)[^>]*\\sid="${id}"[^>]*>([\\s\\S]*?)</\\1>`);
  const m = html.match(re);
  return m ? stripTags(m[2]) : null;
}

// All form controls in the markup with their attributes.
function controls(html) {
  const out = [];
  for (const m of html.matchAll(/<(input|select)\b([^>]*)>/g)) {
    const attrs = {};
    for (const a of m[2].matchAll(/([a-zA-Z-]+)="([^"]*)"/g)) attrs[a[1]] = a[2];
    out.push({ tag: m[1], attrs });
  }
  return out;
}

function accessibleName(html, ctl) {
  if (ctl.attrs["aria-labelledby"]) {
    return ctl.attrs["aria-labelledby"]
      .split(/\s+/)
      .map((id) => textOfId(html, id) || "")
      .join(" ")
      .trim();
  }
  if (ctl.attrs["aria-label"]) return ctl.attrs["aria-label"];
  if (ctl.attrs.id) {
    const m = html.match(new RegExp(`<label[^>]*\\sfor="${ctl.attrs.id}"[^>]*>([\\s\\S]*?)</label>`));
    if (m) return stripTags(m[1]);
  }
  return "";
}

function setup(rows) {
  sandbox.window.STATE_INPUT_LABELS = new Set();
  run("dirty.clear(); planLoaded = true; activeStep = 'household_people';");
  sandbox.__rows = rows;
  run("rows.length = 0; for (const r of __rows) rows.push(r);");
}

const TEXT_ROW = {
  row_index: 101,
  section: "Household",
  subsection: "",
  label: "retirement_age",
  value: "65",
  units: "years",
  schema: { type: "number", default: "67", required: "FALSE" },
};
const CHOICE_ROW = {
  row_index: 102,
  section: "Household",
  subsection: "",
  label: "filing_status",
  value: "MFJ",
  units: "choice",
  schema: { type: "choice", choices: "MFJ|Single", default: "MFJ" },
};
const BOOL_ROW = {
  row_index: 103,
  section: "Household",
  subsection: "",
  label: "has_pension",
  value: "YES",
  units: "yes/no",
  schema: { type: "boolean" },
};
const REQUIRED_EMPTY_ROW = {
  row_index: 104,
  section: "Household",
  subsection: "",
  label: "member_1_name",
  value: "",
  units: "",
  schema: { type: "text", required: "TRUE" },
  editable: true,
};

describe("fieldHtml(): every control has a computed accessible name", () => {
  for (const [kind, row, expected] of [
    ["text", TEXT_ROW, /retirement age/i],
    ["choice", CHOICE_ROW, /filing status/i],
    ["boolean", BOOL_ROW, /pension/i],
    ["required", REQUIRED_EMPTY_ROW, /name/i],
  ]) {
    test(`${kind} row`, () => {
      setup([row]);
      const html = sandbox.fieldHtml(row);
      const ctls = controls(html);
      assert.equal(ctls.length, 1, `expected one control in: ${html}`);
      const name = accessibleName(html, ctls[0]);
      assert.match(name, expected, `accessible name was "${name}"`);
      assert.doesNotMatch(name, /^(YES|NO)$/);
    });
  }
});

describe("fieldHtml(): state and description wiring", () => {
  test("clicking a text field's label focuses its control (<label for> matches the control id)", () => {
    setup([TEXT_ROW]);
    const html = sandbox.fieldHtml(TEXT_ROW);
    const [ctl] = controls(html);
    assert.equal(ctl.attrs.id, "field-101-ctl");
    assert.match(html, /<label id="field-101-lbl" for="field-101-ctl">/);
  });

  test("unit caption is the control's description", () => {
    setup([TEXT_ROW]);
    const html = sandbox.fieldHtml(TEXT_ROW);
    const [ctl] = controls(html);
    const ids = (ctl.attrs["aria-describedby"] || "").split(/\s+/);
    assert.ok(ids.includes("field-101-unit"));
    assert.equal(textOfId(html, "field-101-unit"), "years");
  });

  test("a required, missing field is aria-required, aria-invalid and described by the Required badge", () => {
    setup([REQUIRED_EMPTY_ROW]);
    assert.equal(sandbox.isMissing(REQUIRED_EMPTY_ROW), true, "fixture must be a missing required row");
    const html = sandbox.fieldHtml(REQUIRED_EMPTY_ROW);
    const [ctl] = controls(html);
    assert.equal(ctl.attrs["aria-required"], "true");
    assert.equal(ctl.attrs["aria-invalid"], "true");
    const ids = (ctl.attrs["aria-describedby"] || "").split(/\s+/);
    assert.ok(ids.includes("field-104-req"));
    assert.equal(textOfId(html, "field-104-req"), "Required");
  });

  test("an optional, filled field is neither aria-required nor aria-invalid", () => {
    setup([TEXT_ROW]);
    const [ctl] = controls(sandbox.fieldHtml(TEXT_ROW));
    assert.equal(ctl.attrs["aria-required"], undefined);
    assert.equal(ctl.attrs["aria-invalid"], undefined);
  });

  test("toggle YES/NO text is aria-hidden and the checkbox is named by the field label, not the toggle", () => {
    setup([BOOL_ROW]);
    const html = sandbox.fieldHtml(BOOL_ROW);
    assert.match(html, /toggle-text-yes" aria-hidden="true">YES</);
    assert.match(html, /toggle-text-no" aria-hidden="true">NO</);
    const [ctl] = controls(html);
    assert.equal(ctl.attrs["aria-labelledby"], "field-103-lbl");
    // No <label for> on a toggle: clicking the field name must not flip the value.
    assert.doesNotMatch(html, /for="field-103-ctl"/);
  });
});

describe("admin.js settings table: every setting control has a <label for>", () => {
  function loadAdmin() {
    const src = fs.readFileSync(path.join(HERE, "..", "..", "frontend", "js", "admin.js"), "utf8");
    const noop = () => {};
    const stub = () => ({
      style: {},
      classList: { add: noop, remove: noop, toggle: noop, contains: () => false },
      addEventListener: noop,
      setAttribute: noop,
      querySelectorAll: () => [],
      querySelector: () => null,
      textContent: "",
      innerHTML: "",
      value: "",
    });
    const box = {
      console,
      window: { addEventListener: noop, location: { search: "", href: "" } },
      document: {
        getElementById: stub,
        querySelectorAll: () => [],
        querySelector: () => null,
        addEventListener: noop,
        readyState: "complete",
        createElement: stub,
        body: stub(),
      },
      localStorage: { getItem: () => null, setItem: noop, removeItem: noop },
      setTimeout: () => 0,
      clearTimeout: noop,
      setInterval: () => 0,
      clearInterval: noop,
      fetch: async () => ({ ok: true, json: async () => ({}), text: async () => "" }),
      URLSearchParams,
    };
    box.globalThis = box;
    vm.createContext(box);
    try {
      new vm.Script(src, { filename: "admin.js" }).runInContext(box);
    } catch (_e) {
      // Top-level bootstrap may reach past this stub; declarations are hoisted.
    }
    return box;
  }

  test("text and choice settings are both labelled by their visible setting name", () => {
    const admin = loadAdmin();
    const rows = [
      ["section", "subsection", "label", "value", "units", "notes"],
      ["System Configuration", "", "max_build_seconds", "600", "seconds", "n"],
      ["System Configuration", "", "app_mode", "LOCAL", "choice:LOCAL|SAAS", "n"],
    ];
    const html = admin.buildSectionSettings(rows, {});
    const ctls = controls(html).filter((c) => /cfg-(input|select)/.test(c.attrs.class || ""));
    assert.equal(ctls.length, 2, html);
    const names = ctls.map((c) => accessibleName(html, c));
    assert.deepEqual(names.slice().sort(), ["App Mode", "Max Build Seconds"]);
  });
});
