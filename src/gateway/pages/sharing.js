// The owner's Shared views page (Phase 9, multi-user-shared-view-design.md 6.2). Text only: every string is inserted
// with textContent. The preview uses the guest page's own renderer, so it is exactly what the viewer sees.
import { renderRecord } from "/gateway/viewer/static/viewer.js";

const doc = document;
const $ = (id) => doc.getElementById(id);
const state = { csrf: "", plan: null, shares: [], viewers: [] };

function el(tag, attrs, ...kids) {
  const n = doc.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "text") n.textContent = String(v); else n.setAttribute(k, String(v));
  }
  for (const c of kids.flat()) if (c !== null && c !== undefined) n.appendChild(typeof c === "object" ? c : doc.createTextNode(String(c)));
  return n;
}
const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); };
const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "–");
const say = (text) => { $("sharing-status").textContent = text; };

async function api(path, body) {
  const opts = body === undefined ? { credentials: "same-origin" }
    : { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf }, body: JSON.stringify(body) };
  const r = await fetch(path, opts);
  if (r.status === 401) { location.assign("/login?next=%2Fgateway%2Fsharing"); return { ok: false, data: {} }; }
  return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
}

const STATE_TEXT = (s) => (s.state === "suspended" ? `Suspended: ${s.state_reason || "suspended"}` : s.state === "revoked" ? "Revoked"
  : s.expired ? "Expired" : s.published_at ? "Shared" : "Not published");

function drawShares() {
  const box = $("share-table");
  clear(box);
  const live = state.shares.filter((s) => s.state !== "revoked");
  if (!live.length) { box.appendChild(el("p", { class: "note", text: "Nothing is shared yet." })); return; }
  const rows = live.map((s) => {
    const act = el("td", { class: "share-actions" });
    const btn = (label, fn) => { const b = el("button", { type: "button", text: label }); b.addEventListener("click", fn); act.appendChild(b); };
    if (s.state === "suspended") btn("Enable", () => action(s, "enable"));
    else {
      btn("Refresh", () => action(s, "publish"));
      btn("Preview", () => preview(s));
    }
    btn("Extend", () => action(s, "expiry", { expires_in_days: 90 }));
    btn("Who looked", () => looked(s));
    btn("Revoke", () => { if (confirm(`Stop sharing "${s.title}"?`)) action(s, "revoke"); });
    return el("tr", null, el("td", { text: s.title }), el("td", { text: s.viewer }), el("td", { text: STATE_TEXT(s) }),
      el("td", { text: s.money_view === "percent" ? "Percent" : "Dollars" }), el("td", { text: when(s.published_at) }),
      el("td", { text: when(s.expires_at) }), el("td", { text: when(s.last_viewed) }), act);
  });
  const head = ["Title", "Viewer", "State", "Amounts", "As of", "Expires", "Last viewed", ""].map((h) => el("th", { scope: "col", text: h }));
  box.appendChild(el("table", null, el("thead", null, el("tr", null, head)), el("tbody", null, rows)));
}

function drawViewers() {
  const box = $("viewer-table");
  clear(box);
  const sel = $("f-viewer");
  clear(sel);
  if (!state.viewers.length) {
    box.appendChild(el("p", { class: "note", text: "No viewer accounts yet. An administrator creates them for you." }));
    $("f-publish").disabled = true;
    return;
  }
  for (const v of state.viewers) sel.appendChild(el("option", { value: v.id, text: v.display_name }));
  $("f-publish").disabled = false;
  const rows = state.viewers.map((v) => el("tr", null, el("td", { text: v.display_name }), el("td", { text: when(v.expires_at) }),
    el("td", { text: v.enrolled ? "Yes" : "Not yet" })));
  const head = ["Viewer", "Account ends", "Has signed in"].map((h) => el("th", { scope: "col", text: h }));
  box.appendChild(el("table", null, el("thead", null, el("tr", null, head)), el("tbody", null, rows)));
}

async function refresh() {
  const [list, viewers] = await Promise.all([api("/api/share/list"), api("/api/share/viewers")]);
  state.shares = list.data.shares || [];
  state.viewers = viewers.data.viewers || [];
  if (list.data.default_days) $("f-days").value = String(list.data.default_days);
  if (list.data.max_days) $("f-days").max = String(list.data.max_days);
  drawShares();
  drawViewers();
}

async function action(s, what, body) {
  const r = await api(`/api/share/${encodeURIComponent(s.id)}/${what}`, body || {});
  say(r.data.message || r.data.error || (r.ok ? "Done." : "That did not work."));
  await refresh();
  if (r.ok && (what === "publish" || what === "enable")) await preview(s);
}

async function preview(s) {
  const r = await api(`/api/share/${encodeURIComponent(s.id)}/preview`);
  const box = $("preview");
  clear(box);
  $("preview-section").hidden = false;
  if (!r.ok) { box.appendChild(el("p", { text: "Nothing is published for this view yet." })); return; }
  box.appendChild(renderRecord(doc, r.data, { title: s.title, owner: "you" }, {}).root);
}

async function looked(s) {
  const r = await api(`/api/share/${encodeURIComponent(s.id)}/views`);
  const list = r.data.views || [];
  say(list.length ? `Viewed: ${list.map((v) => `${v.viewer} at ${when(v.at)}`).join("; ")}` : "Nobody has opened this view yet.");
}

$("share-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!state.plan) { say("Open the plan you want to share in the planner first."); return; }
  const views = [...doc.querySelectorAll("input[name=tab]:checked")].map((i) => i.value);
  const money = doc.querySelector("input[name=money]:checked").value;
  const r = await api("/api/share/create", {
    viewer_id: Number($("f-viewer").value), title: $("f-title").value, money_view: money, views,
    expires_in_days: Number($("f-days").value), expected_plan_id: state.plan.id,
  });
  say(r.data.message || r.data.error || (r.ok ? "Shared." : "That did not work."));
  await refresh();
  if (r.ok && r.data.id) await preview({ id: r.data.id, title: $("f-title").value });
});

(async () => {
  const sess = await api("/api/auth/session");
  state.csrf = sess.data.csrf_token || "";
  const who = await api("/insights/api/whoami");
  state.plan = who.ok && who.data.plan && who.data.plan.id ? who.data.plan : null;
  $("plan-line").textContent = state.plan ? `Plan: ${state.plan.name || state.plan.id}` : "Open Financial Insight once so this page knows your plan.";
  await refresh();
})();
