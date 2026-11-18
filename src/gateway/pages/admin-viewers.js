// Gateway-only part of the Admin console for shared views (Phase 9): Add viewer, the Kind of each person, and a
// disabled role for viewers. Kept out of admin_app/frontend/users.js, which the desktop Admin app also loads.
// Shown only when the console API reports features.viewers === true (the gateway's --shared-views). Text only.
(function () {
  "use strict";
  const host = window.AdminHost;
  if (!host) return;
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === "text") n.textContent = String(v); else n.setAttribute(k, String(v)); }
    for (const c of kids) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    return n;
  };
  const dateValue = (t) => { const d = new Date(t * 1000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const endOfDay = (s) => { if (!s) return null; const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d, 23, 59, 59).getTime() / 1000; };
  let people = [], minPw = 12;

  // The edit dialog: a viewer has no role to change.
  const wire = host.wire;
  host.wire = (dlg, u) => {
    if (wire) wire(dlg, u);
    const role = dlg.querySelector("#fRole");
    if (u && u.kind === "viewer" && role) { role.disabled = true; role.title = "A viewer has no role to change"; }
  };

  function viewerDialog() {
    const dlg = el("dialog", { "aria-labelledby": "vTitle" });
    const members = people.filter((p) => p.kind === "member" && p.status !== "disabled" && !p.expired);
    const field = (label, input) => el("label", { class: "field" }, el("span", { text: label }), input);
    const sponsor = el("select", { id: "vSponsor" });
    for (const m of members) sponsor.appendChild(el("option", { value: m.id, text: m.display_name }));
    const err = el("div", { class: "err", id: "vErr", role: "alert" });
    const form = el("form", { id: "viewerForm", novalidate: "" },
      el("header", { class: "dhead" }, el("h2", { id: "vTitle", text: "Add viewer" }), el("button", { type: "submit", class: "primary", text: "Add viewer" }), err),
      el("p", { class: "note", text: "A viewer can only read the shared views their sponsor publishes for them. They get no planner, and two-factor sign-in is required." }),
      field("Name", el("input", { id: "vName", maxlength: "80" })), field("Username", el("input", { id: "vUser", maxlength: "32" })),
      field("Temporary password", el("input", { id: "vPw", type: "password", autocomplete: "new-password" })),
      field("Sponsor (the member who shares with them)", sponsor),
      field("Access ends", el("input", { id: "vExpires", type: "date", value: dateValue(Date.now() / 1000 + 90 * 86400) })),
      el("div", { class: "bar" }, el("button", { type: "button", id: "vCancel", text: "Cancel" })));
    dlg.appendChild(form);
    document.body.appendChild(dlg);
    form.querySelector("#vCancel").addEventListener("click", () => { dlg.close(); dlg.remove(); });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = (id) => form.querySelector(id).value;
      if (!v("#vName").trim() || !v("#vUser").trim()) { err.textContent = "Name and username are both needed."; return; }
      if (v("#vPw").length < minPw) { err.textContent = `Temporary password must be at least ${minPw} characters.`; return; }
      const r = await host.fetch(host.apiBase + "/viewers", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: v("#vName").trim(), username: v("#vUser").trim(), temp_password: v("#vPw"),
          sponsor_id: Number(v("#vSponsor")), expires_at: endOfDay(v("#vExpires")) }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j.success === false) { err.textContent = j.error || "The change was refused."; return; }
      location.reload();
    });
    dlg.showModal();
    form.querySelector("#vName").focus();
  }

  async function decorate(main) {
    const bar = main.querySelector(".bar");
    if (!bar || bar.querySelector("#addViewer")) return;
    bar.dataset.viewers = "pending";
    const r = await host.fetch(host.apiBase + "/users");
    const j = await r.json().catch(() => ({}));
    if (!j.features || j.features.viewers !== true || bar.querySelector("#addViewer")) return;
    people = j.users || [];
    minPw = j.min_password || minPw;
    const byId = new Map(people.map((p) => [p.id, p]));
    const add = el("button", { type: "button", id: "addViewer", text: "Add viewer" });
    add.addEventListener("click", viewerDialog);
    bar.insertBefore(add, bar.children[1] || null);
    for (const row of main.querySelectorAll("tr[data-user]")) {
      const p = byId.get(Number(row.dataset.user));
      const cell = row.children[2];  // the Role column
      if (!p || !cell) continue;
      const sponsor = p.kind === "viewer" ? byId.get(p.sponsor_id) : null;
      const text = p.kind === "viewer" ? ` · Viewer for ${sponsor ? sponsor.display_name : "?"}` : "";
      const counts = p.shares_owned || p.shares_received ? ` · shares ${p.shares_owned} owned, ${p.shares_received} received` : "";
      if (text || counts) cell.appendChild(el("span", { class: "note", text: text + counts }));
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const main = document.getElementById("main");
    if (!main) return;
    new MutationObserver(() => { decorate(main); }).observe(main, { childList: true });
  });
})();
