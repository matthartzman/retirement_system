// System > Apps & sessions: start / stop the Planner and Financial Insights, and see who is signed in right now.
(function () {
  "use strict";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "-");
  const ago = (t) => { const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 90 ? `${s}s ago` : `${Math.round(s / 60)} min ago`; };
  const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json().then((j) => ({ ok: r.ok && j.success !== false, ...j }))).catch(() => ({ ok: false, error: "The Admin app did not answer." }));
  const get = (url) => fetch(url, { cache: "no-store" }).then((r) => r.json()).catch(() => ({ success: false }));
  const STATE = { running: "ok", starting: "", stopped: "bad" };
  const panel = () => document.getElementById("procPanel");
  function appRow(a) {
    const note = a.state === "running" && !a.managed ? " (started outside the Admin app)" : "";
    const extra = (a.extra_ports || []).map((p) => `, remote ${p.port} ${p.listening ? "listening" : "closed"}`).join("");
    const btn = a.state === "stopped" ? `<button type="button" class="primary" data-start="${a.name}">Start</button>`
      : `<button type="button" class="danger" data-stop="${a.name}">Stop</button>`;
    return `<tr><td>${esc(a.label)}</td><td><span class="badge ${STATE[a.state] || ""}">${esc(a.state)}</span>${esc(note)}</td>
      <td>${a.port}${esc(extra)}</td><td>${a.pid ?? "-"}</td><td>${btn}</td></tr>`;
  }
  const sessionRow = (s) => `<tr><td>${esc(s.person)} <span class="note">${esc(s.username)}</span></td><td>${esc(s.app_label)}</td>
    <td>${s.where === "remote" ? "Remote" + (s.source ? " " + esc(s.source) : "") : "This computer"}</td><td>${esc(when(s.started_at))}</td>
    <td>${esc(ago(s.last_seen))}</td><td><button type="button" data-end="${s.user_id}" data-name="${esc(s.person)}">End sessions</button></td></tr>`;
  async function refresh() {
    if (!panel()) return clearInterval(window.procTimer);
    const [p, s] = await Promise.all([get("/api/processes"), get("/api/sessions")]);
    if (!panel()) return;
    const rows = [...(p.apps || []), p.admin ? { ...p.admin, label: "Admin app", managed: true } : null].filter(Boolean);
    panel().querySelector("#procApps").innerHTML = rows.map((a) => (a.name ? appRow(a)
      : `<tr><td>Admin app</td><td><span class="badge ok">running</span></td><td>${a.port}</td><td>${a.pid}</td><td></td></tr>`)).join("");
    panel().querySelector("#procSessions").innerHTML = (s.sessions || []).map(sessionRow).join("")
      || `<tr><td colspan="6" class="note">Nobody is signed in. ${esc(s.note || "")}</td></tr>`;
  }
  async function act(btn) {
    const name = btn.dataset.start || btn.dataset.stop;
    if (btn.dataset.stop && !(await adminConfirm(`Stop ${name === "planner" ? "the Retirement Planner" : "Financial Insights"}? Anyone using it is disconnected.`, "Stop"))) return;
    btn.disabled = true;
    const out = await post(btn.dataset.start ? "/api/processes/start" : "/api/processes/stop", { app: name });
    msg(out.ok ? (btn.dataset.start ? "Started." : "Stopped.") : out.error || "That did not work.", !out.ok);
    refresh();
  }
  window.showAppSettings = async function () {
    setAdminStep("app_settings");
    document.getElementById("main").innerHTML = `<div id="procPanel"><h2>Apps</h2>
      <table><tr><th>App</th><th>Status</th><th>Port</th><th>Process id</th><th></th></tr><tbody id="procApps"></tbody></table>
      <p class="note">Apps started here keep running if you close the Admin app. <button type="button" data-cache="1">Clear cache</button></p><h2>Signed-in sessions</h2>
      <table><tr><th>Person</th><th>App</th><th>From</th><th>Signed in</th><th>Last seen</th><th></th></tr><tbody id="procSessions"></tbody></table></div>`;
    panel().addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (b && b.dataset.cache) clearAppCache();
      else if (b && (b.dataset.start || b.dataset.stop)) act(b);
      else if (b && b.dataset.end && (await adminConfirm(`End all of ${b.dataset.name}'s sessions in every app?`, "End sessions"))) {
        const out = await post("/api/sessions/end", { user_id: Number(b.dataset.end) });
        msg(out.ok ? "Sessions ended." : out.error, !out.ok);
        refresh();
      }
    });
    clearInterval(window.procTimer);
    await refresh();
    window.procTimer = setInterval(refresh, 4000);
  };
})();
