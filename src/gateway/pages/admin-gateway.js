// Host adapter for the shared Users UI (users.js) when the gateway serves it. Runs before users.js (both deferred, in
// page order). It tells users.js where the console API is and adds the per-session CSRF header the gateway demands
// on every unsafe request; the token comes from the signed-in session, as in gateway.js.
(function () {
  "use strict";
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
    headers: async () => ({ "X-CSRF-Token": await csrf() }),
    onUnauthenticated: () => { location.href = "/login?next=" + encodeURIComponent("/gateway/admin"); },
  };
})();
