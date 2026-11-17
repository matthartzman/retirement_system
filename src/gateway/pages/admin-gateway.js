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
    actBody: (act, dlg) => (act === "delete" ? { confirm_username: dlg.querySelector("#fConfirmDel").value } : {}),
  };
})();
