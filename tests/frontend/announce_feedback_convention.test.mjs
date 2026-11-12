// W2-05 / UX-003: one feedback convention. announce() writes to persistent polite/assertive regions; a panel's
// inline message carries no live role of its own and is announced once per change (a repaint is silent).
import { test, before, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { installInAppConfirm } from "./inapp_confirm_stub.mjs";

let live, alert;
before(async () => {
  globalThis.window = globalThis;
  await installInAppConfirm(); // loads dashboard_shared_helpers.js
});
beforeEach(() => {
  live = { textContent: "" }; alert = { textContent: "" };
  globalThis.document = { getElementById: (id) => (id === "rpLive" ? live : id === "rpAlert" ? alert : null) };
});

test("announce routes errors to the assertive region and everything else to the polite one", () => {
  announce("saved");
  assert.equal(live.textContent, "saved"); assert.equal(alert.textContent, "");
  announce("failed", { error: true });
  assert.equal(alert.textContent, "failed");
});

test("announce is a no-op when the regions are absent", () => {
  globalThis.document = { getElementById: () => null };
  assert.doesNotThrow(() => announce("x"));
});

test("a panel message is announced once per change and never carries a live role", () => {
  const html = panelMsgHtml("t1", { text: "1099-B applied", error: false });
  assert.doesNotMatch(html, /role=|aria-live/);
  assert.equal(live.textContent, "1099-B applied");
  live.textContent = "";
  panelMsgHtml("t1", { text: "1099-B applied", error: false }); // a repaint
  assert.equal(live.textContent, "", "a repaint must not re-announce");
  panelMsgHtml("t1", null);                                       // cleared
  panelMsgHtml("t1", { text: "1099-B applied", error: false });   // the same text again is a new message
  assert.equal(live.textContent, "1099-B applied");
});

test("a panel error is announced assertively", () => {
  panelMsgHtml("t2", { text: "Void failed", error: true });
  assert.equal(alert.textContent, "Void failed");
  assert.equal(live.textContent, "");
});

test("index.html carries both persistent regions at load", () => {
  const html = fs.readFileSync(new URL("../../frontend/index.html", import.meta.url), "utf8");
  assert.match(html, /id="rpLive"[^>]*aria-live="polite"/);
  assert.match(html, /id="rpAlert"[^>]*role="alert"/);
});

test("no panel module injects its own role=status message paragraph any more", () => {
  for (const f of ["cash_accounts", "broker_import", "sales_1099b", "sales_entry", "sales_ledger", "sales_queue", "sales_tax", "sales_wash", "transactions_log"]) {
    const src = fs.readFileSync(new URL(`../../frontend/js/dashboard_decomp_${f}.js`, import.meta.url), "utf8");
    assert.ok(!/Message\.error \? "(field-)?error"[^`]*role="status"/.test(src), `${f} still injects a role=status message`);
  }
});
