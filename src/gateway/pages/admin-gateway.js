// Host adapter for the shared Users UI (admin_app/frontend/users.js) when the gateway serves it. Runs before users.js
// (both deferred, in page order). It tells users.js where the console API is, adds the per-session CSRF header the
// gateway demands on every unsafe request (the token comes from the signed-in session, as in gateway.js), and
// supplies the gateway-only parts of the dialog: Unlock and a Delete that needs the person's username typed in.
(function () {
  "use strict";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let token = "";
  async function csrf() {
    if (!token) {
      const r = await fetch("/api/auth/session");
      const j = await r.json().catch(() => ({}));
      token = j.csrf_token || "";
    }
    return token;
  }
  window.AdminHost = {
    apiBase: "/api/auth/admin/console",
    pages: ["users", "audit"],
    fetch: async (url, init = {}) => {
      const r = await fetch(url, { ...init, headers: { ...(init.headers || {}), "X-CSRF-Token": await csrf() } });
      if (r.status === 401) location.href = "/login?next=" + encodeURIComponent("/gateway/admin");
      return r;
    },
    removal: (u) => `${u.locked ? '<div class="actions"><button type="button" data-act="unlock">Unlock</button></div>' : ""}
      <div class="delbox"><p class="note">Deleting ${esc(u.display_name)} permanently removes their plans and data. This cannot be undone.
      Type their username (<strong>${esc(u.username)}</strong>) to enable Delete.</p>
      <label class="field"><span>Username to confirm</span><input id="fConfirmDel" autocomplete="off" autocapitalize="none" spellcheck="false"></label>
      <div class="actions"><button type="button" class="danger" data-act="delete" id="fDelete" disabled>Delete ${esc(u.display_name)} and their data</button></div></div>`,
    wire: (dlg, u) => {
      const typed = dlg.querySelector("#fConfirmDel"), del = dlg.querySelector("#fDelete");
      typed.addEventListener("input", () => { del.disabled = typed.value !== u.username; });
    },
    // the gateway's dialog: Retirement Planner is one "Can sign in" switch (the enabled state); Financial Insights
    // holds the stored-but-not-enforced module flags; two-factor is a note, never a switch
    maintenance: "Maintenance",
    note: '<p class="note">Two-factor sign-in is always required on this server.</p>',
    sections: (u, { tog, sec, field, esc: e, MONEY }) => {
      const m = (u && u.modules) || { snapshot: false, trends: false, projections: false, money_view: "percent" };
      const money = Object.entries(MONEY).map(([v, l]) => `<option value="${v}"${m.money_view === v ? " selected" : ""}>${l}</option>`).join("");
      const mods = Object.entries({ snapshot: "Snapshot", trends: "Trends", projections: "Projections" }).map(([k, l]) => tog(l, m[k], `data-module="${k}"`)).join("");
      return sec("Retirement Planner", tog("Can sign in", u ? u.status !== "disabled" : true, 'id="gSignIn"'), true)
        + sec("Financial Insights", `<div class="modrow"><label class="modlabel" for="gMoney">Money shown as</label><select id="gMoney">${money}</select></div>
        <div class="modrow"><span class="modlabel">Modules:</span>${mods}</div>`, true);
    },
    collect: (dlg) => ({ modules: { ...Object.fromEntries([...dlg.querySelectorAll("[data-module]")].map((c) => [c.dataset.module, c.checked])), money_view: dlg.querySelector("#gMoney").value } }),
    after: async (out, u, dlg, api) => {  // "Can sign in" is the account's enabled state; a new person is created, then switched off if asked
      if (!out.ok) return out;
      const on = dlg.querySelector("#gSignIn").checked, was = u ? u.status !== "disabled" : true, id = u ? u.id : out.id;
      if (on === was) return out;
      if (u && !on && !confirm(`Disable ${u.display_name} and end their sessions?`)) return { ok: false, error: "Not saved: sign-in left on." };
      return api(`/users/${on ? "enable" : "disable"}`, { id });
    },
    // SEC-04: the one-time enrolment code is shown to the administrator once, at creation or reset. The server keeps only
    // its hash, so closing this box loses it; "New enrolment code" on a person's page issues another.
    showCode: (out, who) => {
      if (!out || !out.enrol_code) return Promise.resolve();
      return new Promise((resolve) => {
        const box = document.createElement("dialog"), h = document.createElement("h3"), code = document.createElement("p");
        const note = document.createElement("p"), ok = document.createElement("button");
        h.textContent = `Enrolment code for ${who}`;
        code.textContent = out.enrol_code;
        code.style.cssText = "font:700 1.6rem/1.4 monospace;letter-spacing:.12em;user-select:all";
        note.className = "note";
        note.textContent = `Give this to ${who} by a different route than their temporary password (in person or by phone). It works once, expires in ${out.enrol_code_minutes || 20} minutes and cannot be shown again.`;
        ok.type = "button";
        ok.textContent = "I have passed it on";
        ok.addEventListener("click", () => { box.close(); box.remove(); resolve(); });
        box.append(h, code, note, ok);
        document.body.appendChild(box);
        box.showModal();
      });
    },
    actBody: (act, dlg) => (act === "delete" ? { confirm_username: dlg.querySelector("#fConfirmDel").value } : {}),
  };
})();
