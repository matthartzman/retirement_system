// W3-10 / DOC-003: the Data & Backups "Help: Concepts Guide" card is a working link to the in-app guide.
import { test } from "node:test";
import assert from "node:assert/strict";
import { loadDashboardSandbox } from "./load_dashboard.mjs";

const sandbox = loadDashboardSandbox();

test("the Concepts Guide card links to /frontend/concepts.html, not a Word path", () => {
  const html = sandbox.renderSystemConfiguration();
  assert.match(html, /<h3>Help: Concepts Guide<\/h3>[^]*?<a href="\/frontend\/concepts\.html"/);
  assert.doesNotMatch(html, /Concepts_Guide\.docx/);
});
