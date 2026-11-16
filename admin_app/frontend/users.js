// Users & access: people list, add/edit with app grants, account actions, activity by app, admin audit.
// No inline handlers or styles (the page's CSP forbids them); every dynamic string goes through esc().
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
  const day = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "none");
  const api = (url, body) => fetch(url, body === undefined ? undefined
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json().then((j) => ({ ok: r.ok && j.success !== false, ...j })))
    .catch(() => ({ ok: false, error: "The Admin app did not answer." }));
  const MIN_PW = 10;
  const MONEY = { dollars: "Dollars", percent: "Percent", both: "Both" };
  const APP_LABEL = { insights: "Financial Insights", planner: "Retirement Planner" };
  const main = $("#main");
  let meta = { views: [] };
  let users = [];

  // ---- date helpers: the form edits a calendar day, the server stores epoch seconds (end of that local day) ----
  const dateValue = (t) => { if (!t) return ""; const d = new Date(t * 1000); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const endOfDay = (s) => { if (!s) return null; const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d, 23, 59, 59).getTime() / 1000; };

  // ---- dialog (one, reused) ----
  const dlg = document.createElement("dialog");
  dlg.setAttribute("aria-labelledby", "dlgTitle");
  document.body.appendChild(dlg);

  function grantSummary(u) {
    return u.grants.map((g) => `<span class="tag">${esc(APP_LABEL[g.app] || g.app)}${g.app === "insights" ? ` · ${esc(MONEY[g.money_view] || g.money_view)}` : ""}</span>`).join("") || '<span class="note">none</span>';
  }

  function userRow(u) {
    const flags = [u.status === "disabled" ? '<span class="tag bad">disabled</span>' : "", u.expired ? '<span class="tag bad">expired</span>' : "",
      u.locked ? '<span class="tag bad">locked</span>' : "", u.must_change ? '<span class="tag">must change password</span>' : "",
      u.totp_enrolled ? '<span class="tag">two-factor on</span>' : u.totp_required ? '<span class="tag">two-factor to set up</span>' : ""].join("");
    return `<tr class="${u.status === "disabled" || u.expired ? "off" : ""}" data-user="${u.id}">
      <td>${esc(u.display_name)}</td><td>${esc(u.username)}</td><td>${esc(u.role)}</td><td>${flags || "active"}</td>
      <td>${esc(day(u.expires_at))}</td><td>${esc(when(u.last_signin_at))}</td><td>${grantSummary(u)}</td>
      <td><button type="button" data-edit="${u.id}">Edit</button></td></tr>`;
  }

  async function showUsers() {
    const r = await api("/api/users");
    if (!r.ok) { main.innerHTML = `<p class="err" role="alert">${esc(r.error || "Could not load people.")}</p>`; return; }
    users = r.users;
    meta = r;
    main.innerHTML = `<h2 class="page">Users</h2>
      <div class="bar"><button type="button" class="primary" id="addUser">Add person</button><span class="note">${users.length} ${users.length === 1 ? "person" : "people"}</span></div>
      <table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th>Expires</th><th>Last sign-in</th><th>Access</th><th></th></tr></thead>
      <tbody>${users.map(userRow).join("")}</tbody></table>`;
    $("#addUser").addEventListener("click", () => openForm(null));
    main.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openForm(users.find((u) => u.id === Number(b.dataset.edit)))));
  }

  function formHtml(u) {
    const ins = u ? u.grants.find((g) => g.app === "insights") : { money_view: "percent", views: null };
    const planner = u ? u.grants.some((g) => g.app === "planner") : false;
    const insOn = u ? !!ins : true;
    const allowed = ins && ins.views ? ins.views : meta.views;
    return `<form id="userForm" novalidate><h2 id="dlgTitle">${u ? `Edit ${esc(u.display_name)}` : "Add person"}</h2>
      <label class="field"><span>Name</span><input id="fName" value="${esc(u ? u.display_name : "")}" autocomplete="off"></label>
      <label class="field"><span>Username</span><input id="fUser" value="${esc(u ? u.username : "")}" autocomplete="off" ${u ? "readonly" : ""}></label>
      ${u ? "" : `<label class="field"><span>Temporary password (${MIN_PW}+ characters; they choose their own at first sign-in)</span><input id="fPw" type="password" autocomplete="new-password"></label>`}
      <label class="field"><span>Role</span><select id="fRole"><option value="user"${u && u.role === "user" || !u ? " selected" : ""}>User</option><option value="admin"${u && u.role === "admin" ? " selected" : ""}>Administrator</option></select></label>
      <label class="field"><span>Access ends after (blank = never)</span><input id="fExpires" type="date" value="${esc(dateValue(u && u.expires_at))}"></label>
      <label><input type="checkbox" id="fTotp"${!u || u.totp_required ? " checked" : ""}> Require two-factor sign-in (Financial Insights)${u && u.totp_enrolled ? " &mdash; already set up" : ""}</label>
      <label class="field"><span>Notes</span><textarea id="fNotes" rows="2" maxlength="500">${esc(u ? u.notes : "")}</textarea></label>
      <fieldset><legend>Financial Insights</legend>
        <label><input type="checkbox" id="gInsights"${insOn ? " checked" : ""}> Can sign in</label>
        <label>Money shown as <select id="gMoney">${Object.entries(MONEY).map(([v, l]) => `<option value="${v}"${(ins ? ins.money_view : "percent") === v ? " selected" : ""}>${l}</option>`).join("")}</select></label>
        <div>${meta.views.map((v) => `<label><input type="checkbox" data-view="${esc(v)}"${allowed.includes(v) ? " checked" : ""}> ${esc(v)}</label>`).join("")}</div></fieldset>
      <fieldset><legend>Retirement Planner</legend><label><input type="checkbox" id="gPlanner"${planner ? " checked" : ""}> Has access (stored now; enforced when the multi-user server arrives)</label></fieldset>
      <div class="err" id="formErr" role="alert"></div>
      ${u ? `<fieldset><legend>Account</legend>
        <label class="field"><span>New temporary password</span><input id="fResetPw" type="password" autocomplete="new-password"></label>
        <div class="actions"><button type="button" data-act="reset-password">Reset password</button>
        <button type="button" data-act="end-sessions">End sessions</button><button type="button" data-act="reset-totp">Reset two-factor</button>
        <button type="button" data-act="${u.status === "disabled" ? "enable" : "disable"}">${u.status === "disabled" ? "Enable" : "Disable"}</button>
        <button type="button" class="danger" data-act="delete">Delete</button></div></fieldset>
        <details><summary>Activity for ${esc(u.display_name)}</summary><div id="userActivity" class="note">Loading&hellip;</div></details>` : ""}
      <div class="foot"><button type="button" id="fCancel">Close</button><button type="submit" class="primary" id="fSave">${u ? "Save changes" : "Add person"}</button></div></form>`;
  }

  function readGrants() {
    const picked = [...dlg.querySelectorAll("[data-view]")].filter((c) => c.checked).map((c) => c.dataset.view);
    return { insights: $("#gInsights", dlg).checked, money_view: $("#gMoney", dlg).value,
      views: picked.length === meta.views.length ? null : picked, planner: $("#gPlanner", dlg).checked };
  }

  function openForm(u) {
    dlg.innerHTML = formHtml(u);
    const err = (m) => { $("#formErr", dlg).textContent = m; };
    $("#fCancel", dlg).addEventListener("click", () => dlg.close());
    $("#userForm", dlg).addEventListener("submit", async (e) => {
      e.preventDefault();
      err("");
      const g = readGrants();
      if (g.insights && g.views && !g.views.length) return err("Choose at least one view, or untick Can sign in.");
      const out = u ? await saveEdit(u, g) : await saveNew(g);
      if (!out.ok) return err(out.error || "The change was refused.");
      dlg.close();
      showUsers();
    });
    if (u) wireAccount(u, err);
    dlg.showModal();
    $("#fName", dlg).focus();
  }

  const insightsGrant = (g) => ({ money_view: g.money_view, views: g.views });

  async function saveNew(g) {
    const name = $("#fName", dlg).value.trim(), username = $("#fUser", dlg).value.trim(), pw = $("#fPw", dlg).value;
    if (!name || !username) return { error: "Name and username are both needed." };
    if (pw.length < MIN_PW) return { error: `Temporary password must be at least ${MIN_PW} characters.` };
    return api("/api/users", { display_name: name, username, temp_password: pw, role: $("#fRole", dlg).value, notes: $("#fNotes", dlg).value, totp_required: $("#fTotp", dlg).checked,
      expires_at: endOfDay($("#fExpires", dlg).value), grants: { insights: g.insights ? insightsGrant(g) : null, planner: g.planner } });
  }

  async function saveEdit(u, g) {
    const body = { id: u.id, display_name: $("#fName", dlg).value.trim(), role: $("#fRole", dlg).value, notes: $("#fNotes", dlg).value, totp_required: $("#fTotp", dlg).checked };
    const expires = endOfDay($("#fExpires", dlg).value);
    if (expires !== u.expires_at && dateValue(expires) !== dateValue(u.expires_at)) body.expires_at = expires;
    let out = await api("/api/users/update", body);
    if (!out.ok) return out;
    const ins = u.grants.find((x) => x.app === "insights");
    const same = ins && ins.money_view === g.money_view && JSON.stringify(ins.views) === JSON.stringify(g.views);
    if (g.insights && !same) out = await api("/api/users/grants", { id: u.id, app: "insights", enabled: true, ...insightsGrant(g) });
    else if (!g.insights && ins) out = await api("/api/users/grants", { id: u.id, app: "insights", enabled: false });
    if (!out.ok) return out;
    const had = u.grants.some((x) => x.app === "planner");
    if (g.planner !== had) out = await api("/api/users/grants", { id: u.id, app: "planner", enabled: g.planner });
    return out;
  }

  function wireAccount(u, err) {
    api(`/api/activity?person=${encodeURIComponent(u.display_name)}&limit=50`).then((r) => {
      $("#userActivity", dlg).innerHTML = r.ok && r.events.length ? `<table>${activityRows(r.events)}</table>` : "No activity recorded.";
    });
    dlg.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "delete" && !confirm(`Delete ${u.display_name}? This cannot be undone.`)) return;
      if (act === "disable" && !confirm(`Disable ${u.display_name} and end their sessions?`)) return;
      const body = { id: u.id };
      if (act === "reset-password") {
        body.temp_password = $("#fResetPw", dlg).value;
        if (body.temp_password.length < MIN_PW) return err(`Temporary password must be at least ${MIN_PW} characters.`);
      }
      const out = await api(`/api/users/${act}`, body);
      if (!out.ok) return err(out.error || "The change was refused.");
      dlg.close();
      showUsers();
    }));
  }

  // ---- activity and audit ----
  const activityRows = (list) => list.map((e) => `<tr><td>${esc(when(e.at))}</td><td>${esc(e.app)}</td><td>${esc(e.person)}</td><td>${esc(e.listener)}</td><td>${esc(e.event)}</td><td>${esc(e.details)}</td><td>${esc(e.source)}</td></tr>`).join("");

  async function showActivity() {
    main.innerHTML = `<h2 class="page">Activity</h2>
      <form class="bar" id="actForm"><label>App <select id="actApp"><option value="">All apps</option><option value="insights">Financial Insights</option><option value="planner">Retirement Planner</option></select></label>
        <label>Person <input id="actPerson" placeholder="exact name"></label><button type="submit">Filter</button></form>
      <table><thead><tr><th>When</th><th>App</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr></thead><tbody id="actRows"></tbody></table>`;
    const load = async () => {
      const q = new URLSearchParams({ app: $("#actApp").value, person: $("#actPerson").value.trim() });
      const r = await api(`/api/activity?${q}`);
      $("#actRows").innerHTML = r.ok ? activityRows(r.events) : `<tr><td colspan="7" class="err">${esc(r.error)}</td></tr>`;
    };
    $("#actForm").addEventListener("submit", (e) => { e.preventDefault(); load(); });
    load();
  }

  async function showAudit() {
    const r = await api("/api/audit");
    main.innerHTML = `<h2 class="page">Admin audit</h2><table><thead><tr><th>When</th><th>Admin</th><th>Action</th><th>Person</th><th>Details</th></tr></thead><tbody>${
      r.ok ? r.audit.map((a) => `<tr><td>${esc(when(a.at))}</td><td>${esc(a.admin)}</td><td>${esc(a.action)}</td><td>${esc(a.target_user)}</td><td>${esc(a.details)}</td></tr>`).join("") : `<tr><td colspan="5" class="err">${esc(r.error)}</td></tr>`}</tbody></table>`;
  }

  // ---- routing ----
  const PAGES = { users: showUsers, activity: showActivity, audit: showAudit };
  function route() {
    const name = PAGES[location.hash.slice(1)] ? location.hash.slice(1) : "users";
    document.querySelectorAll("nav a").forEach((a) => (a.dataset.page === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    PAGES[name]();
  }
  window.addEventListener("hashchange", route);
  route();
})();
