// UX-003 (system review 2026-09-25, Wave 5 item WI-504): every message,
// errors included, went through one toast (#actionMessage) that was not a
// live region and auto-hid after 10 s; error text was often the server's raw
// "<ExceptionClass>: <message>", and save-validation failures were not tied
// back to the failing fields. These tests run the real showMessage() and
// save-error helpers from the production source (load_dashboard.mjs vm
// sandbox).

import { test, describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = fs.readFileSync(path.join(HERE, "..", "..", "frontend", "index.html"), "utf8");

const sandbox = loadDashboardSandbox();
const run = (code) => vm.runInContext(code, sandbox);

let msgEl;
let scheduled;
let controlsById;

function makeMsgEl() {
  const classes = new Set(["message", "hidden"]);
  const attrs = {};
  return {
    innerHTML: "",
    attrs,
    setAttribute(k, v) {
      attrs[k] = String(v);
    },
    get className() {
      return [...classes].join(" ");
    },
    set className(v) {
      classes.clear();
      String(v).split(/\s+/).filter(Boolean).forEach((c) => classes.add(c));
    },
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
  };
}

beforeEach(() => {
  msgEl = makeMsgEl();
  scheduled = [];
  controlsById = {};
  sandbox.setTimeout = (fn, ms) => {
    scheduled.push({ fn, ms });
    return scheduled.length;
  };
  sandbox.clearTimeout = () => {};
  sandbox.document = {
    getElementById: (id) => (id === "actionMessage" ? msgEl : controlsById[id] || null),
  };
});

describe("showMessage(): errors persist and are announced", () => {
  test("an error does not schedule an auto-hide and gets a dismiss button", () => {
    sandbox.showMessage("Error saving: disk full", "error");
    assert.equal(scheduled.filter((s) => s.ms === 10000).length, 0, "error toast must not auto-hide");
    assert.ok(msgEl.classList.contains("persistent"));
    assert.match(msgEl.innerHTML, /msg-dismiss/);
    assert.ok(!msgEl.classList.contains("hidden"));
  });

  test("an error is exposed as role=alert", () => {
    sandbox.showMessage("Error building: failed", "error");
    assert.equal(msgEl.attrs.role, "alert");
    assert.equal(msgEl.attrs["aria-atomic"], "true");
  });

  test("an info message still auto-hides and is a polite status", () => {
    sandbox.showMessage("Changes saved.");
    assert.equal(scheduled.filter((s) => s.ms === 10000).length, 1);
    assert.equal(msgEl.attrs.role, "status");
    assert.equal(msgEl.attrs["aria-live"], "polite");
  });

  test("a caller can still opt an error out of persistence explicitly", () => {
    sandbox.showMessage("Transient", "error", { persistent: false });
    assert.equal(scheduled.filter((s) => s.ms === 10000).length, 1);
  });

  test("#actionMessage is a live region in the static markup too", () => {
    assert.match(INDEX_HTML, /id="actionMessage"[^>]*aria-live="polite"/);
  });
});

describe("showMessage(): raw exception text moves under Technical details", () => {
  test("'Error building: ValueError: ...' shows a plain summary; the raw text is in the disclosure", () => {
    const raw = "ValueError: household config is missing plan_start";
    sandbox.showMessage("Error building: " + raw, "error");
    const headline = msgEl.innerHTML.match(/<span class="msg-text">([\s\S]*?)<\/span>/)[1];
    assert.doesNotMatch(headline, /ValueError/);
    assert.match(headline, /^Error building\./);
    assert.match(msgEl.innerHTML, /Technical details/);
    const pre = msgEl.innerHTML.match(/<pre class="msg-detail-pre">([\s\S]*?)<\/pre>/)[1];
    assert.ok(pre.includes(raw), "raw exception text must stay reachable in the detail");
  });

  test("messages without an exception class are shown as-is", () => {
    sandbox.showMessage("Error saving: Plan Data validation failed", "error");
    assert.match(msgEl.innerHTML, /<span class="msg-text">Error saving: Plan Data validation failed<\/span>/);
    assert.equal(sandbox.splitRawErrorText("Error: nothing raw here"), null);
  });
});

describe("save validation errors are tied to their fields", () => {
  const ROWS = [
    { row_index: 7, section: "Household", subsection: "", label: "retirement_age", value: "abc", units: "", schema: { type: "number" } },
    { row_index: 8, section: "Income Streams", subsection: "Pension_1", label: "start_year", value: "x", units: "", schema: { type: "year" } },
  ];

  function loadRows() {
    sandbox.__rows = ROWS;
    run("rows.length = 0; for (const r of __rows) rows.push(r); dirty.clear(); saveValidationInvalidRows.clear();");
    sandbox.window.STATE_INPUT_LABELS = new Set();
  }

  test("backend error keys resolve to row indexes", () => {
    loadRows();
    const errs = [
      "('Household', '', 'retirement_age'): expected a number; got 'abc'",
      "('Income Streams', 'Pension_1', 'start_year'): expected a year; got 'x'",
      "something unrelated",
    ];
    assert.deepEqual([...sandbox.rowIndexesForSaveErrors(errs)], [7, 8]);
  });

  test("marking sets aria-invalid on the on-screen control and on the next render", () => {
    loadRows();
    const ctl = { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
    controlsById["field-7-ctl"] = ctl;
    sandbox.markSaveValidationErrors(["('Household', '', 'retirement_age'): expected a number; got 'abc'"]);
    assert.equal(ctl.attrs["aria-invalid"], "true");
    const html = sandbox.fieldHtml(ROWS[0]);
    assert.match(html, /id="field-7-ctl"[^>]*aria-invalid="true"/);
    const other = sandbox.fieldHtml(ROWS[1]);
    assert.doesNotMatch(other, /aria-invalid/);
  });
});
