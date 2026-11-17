// Users & access: people list, add/edit with app grants, account actions, activity by app, admin audit.
// No inline handlers or styles (the page's CSP forbids them); every dynamic string goes through esc().
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
  const day = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "none");
  // The host page may set window.AdminHost = { apiBase, headers(), pages, onUnauthenticated() } before this script runs
  // (the gateway does: it adds its CSRF header and base path). Without it this is the standalone Admin app.
  const host = window.AdminHost || {};
  const base = host.apiBase || "/api";
  const api = async (path, body) => {
    try {
      const extra = host.headers ? await host.headers() : {};
      const r = await fetch(base + path, body === undefined ? { headers: extra }
        : { method: "POST", headers: { "Content-Type": "application/json", ...extra }, body: JSON.stringify(body) });
      if (r.status === 401 && host.onUnauthenticated) host.onUnauthenticated();
      const j = await r.json().catch(() => ({}));
      return { ok: r.ok && j.success !== false, ...j };
    } catch (e) { return { ok: false, error: host.apiBase ? "The server did not answer." : "The Admin app did not answer." }; }
  };
  let MIN_PW = 10;  // the server sends its own minimum with the people list (the gateway's is 12)
  const feat = (name) => !meta.features || meta.features[name] !== false;   // a capability the host has not turned off
  const extra = (name) => !!(meta.features && meta.features[name] === true); // an extra the host turns on (gateway only)
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
      ${feat("expiry") ? `<td>${esc(day(u.expires_at))}</td>` : ""}<td>${esc(when(u.last_signin_at))}</td>${feat("grants") ? `<td>${grantSummary(u)}</td>` : ""}
      <td><button type="button" data-edit="${u.id}">Edit</button></td></tr>`;
  }

  async function showUsers() {
    const r = await api("/users");
    if (!r.ok) { main.innerHTML = `<p class="err" role="alert">${esc(r.error || "Could not load people.")}</p>`; return; }
    users = r.users;
    meta = r;
    if (r.min_password) MIN_PW = r.min_password;
    main.innerHTML = `<h2 class="page">Users</h2>
      <div class="bar"><button type="button" class="primary" id="addUser">Add person</button><span class="note">${users.length} ${users.length === 1 ? "person" : "people"}</span></div>
      <table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th>${feat("expiry") ? "<th>Expires</th>" : ""}<th>Last sign-in</th>${feat("grants") ? "<th>Access</th>" : ""}<th></th></tr></thead>
      <tbody>${users.map(userRow).join("")}</tbody></table>`;
    $("#addUser").addEventListener("click", () => openForm(null));
    main.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => openForm(users.find((u) => u.id === Number(b.dataset.edit)))));
  }

  const tog = (label, checked, attrs, hint) => `<label class="tog"><input type="checkbox" ${attrs}${checked ? " checked" : ""}><span>${label}${hint ? ` <small class="note">${hint}</small>` : ""}</span></label>`;
  const field = (label, input) => `<label class="field"><span>${label}</span>${input}</label>`;
  const sec = (title, body, open) => `<details class="sec"${open ? " open" : ""}><summary>${title}</summary><div class="secbody">${body}</div></details>`;

  function formHtml(u) {
    const ins = u ? u.grants.find((g) => g.app === "insights") : { money_view: "percent", views: null };
    const allowed = ins && ins.views ? ins.views : meta.views;
    const save = u ? "Save changes" : "Add person";
        const account = `<section class="acct"><h3>Account</h3>
      <div class="row2">${field("Name", `<input id="fName" value="${esc(u ? u.display_name : "")}" autocomplete="off"${u && !feat("edit_name") ? " readonly" : ""}>`)}
      ${field("Username", `<input id="fUser" value="${esc(u ? u.username : "")}" autocomplete="off" ${u ? "readonly" : ""}>`)}</div>
      ${u ? "" : field(`Temporary password (${MIN_PW}+ characters; they choose their own at first sign-in)`, '<input id="fPw" type="password" autocomplete="new-password">')}
      <div class="row3">${field("Role", `<select id="fRole"><option value="user"${u && u.role === "admin" ? "" : " selected"}>User</option><option value="admin"${u && u.role === "admin" ? " selected" : ""}>Administrator</option></select>`)} ${feat("expiry") ? field("Access ends after (blank = never)", `<input id="fExpires" type="date" value="${esc(dateValue(u && u.expires_at))}">`) : ""} ${field("Added", `<output id="fAdded">${esc(day(u ? u.created_at : Date.now() / 1000))}</output>`)}</div>
      ${feat("require_totp") ? "" : '<p class="note">Two-factor sign-in: required for everyone.</p>'}
      ${u ? `<details class="acts"><summary>Password, sessions and removal</summary>
        ${field("New temporary password", '<input id="fResetPw" type="password" autocomplete="new-password">')}
        <div class="actions"><button type="button" data-act="reset-password">Reset password</button>${feat("end_sessions") ? '<button type="button" data-act="end-sessions">End sessions</button>' : ""}<button type="button" data-act="reset-totp">Reset two-factor</button>
        ${extra("unlock") && u.locked ? '<button type="button" data-act="unlock">Unlock</button>' : ""}<button type="button" data-act="${u.status === "disabled" ? "enable" : "disable"}">${u.status === "disabled" ? "Enable" : "Disable"}</button>${extra("delete_confirm_username") ? "" : '<button type="button" class="danger" data-act="delete">Delete</button>'}</div>
        ${extra("delete_confirm_username") ? `<div class="delbox"><p class="note">Deleting ${esc(u.display_name)} permanently removes their plans and data. This cannot be undone. Type their username (<strong>${esc(u.username)}</strong>) to enable Delete.</p>
        ${field("Username to confirm", '<input id="fConfirmDel" autocomplete="off" autocapitalize="none" spellcheck="false">')}
        <div class="actions"><button type="button" class="danger" data-act="delete" id="fDelete" disabled>Delete ${esc(u.display_name)} and their data</button></div></div>` : ""}</details>` : ""}</section>`;
    const planner = sec("Retirement Planner", tog("Can use the Retirement Planner", u ? u.grants.some((g) => g.app === "planner") : false, 'id="gPlanner"', "stored now; enforced when the multi-user server arrives"), true);
    const insights = sec("Financial Insights", `${field("Money shown as", `<select id="gMoney">${Object.entries(MONEY).map(([v, l]) => `<option value="${v}"${(ins ? ins.money_view : "percent") === v ? " selected" : ""}>${l}</option>`).join("")}</select>`)}
      ${tog("Can sign in", u ? !!ins : true, 'id="gInsights"')} ${tog("Require two-factor sign-in", !u || u.totp_required, 'id="fTotp"', u && u.totp_enrolled ? "already set up" : "")}
      ${meta.views.map((v) => tog(esc(v), allowed.includes(v), `data-view="${esc(v)}"`)).join("")}`, true);
    return `<form id="userForm" novalidate><header class="dhead"><h2 id="dlgTitle">${u ? `Edit ${esc(u.display_name)}` : "Add person"}</h2>
      <button type="submit" class="primary" id="fSaveTop">${save}</button><div class="err" id="formErr" role="alert"></div></header>
      ${account}${feat("grants") ? planner + insights : ""}${u && feat("activity") ? sec(`Activity for ${esc(u.display_name)}`, '<div id="userActivity" class="note">Loading&hellip;</div>') : ""}
      ${feat("notes") ? `<label class="field"><span>Notes</span><textarea id="fNotes" rows="2" maxlength="500">${esc(u ? u.notes : "")}</textarea></label>` : ""}
      <div class="foot"><button type="button" id="fCancel">Close</button><button type="submit" class="primary" id="fSave">${save}</button></div></form>`;
  }

  function readGrants() {
    if (!feat("grants")) return { insights: false, money_view: "percent", views: null, planner: false };
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
    const body = { display_name: name, username, temp_password: pw, role: $("#fRole", dlg).value };
    if (feat("notes")) body.notes = $("#fNotes", dlg).value;
    if (feat("require_totp")) body.totp_required = $("#fTotp", dlg).checked;
    if (feat("expiry")) body.expires_at = endOfDay($("#fExpires", dlg).value);
    if (feat("grants")) body.grants = { insights: g.insights ? insightsGrant(g) : null, planner: g.planner };
    return api("/users", body);
  }

  async function saveEdit(u, g) {
    const body = { id: u.id, role: $("#fRole", dlg).value };
    if (feat("edit_name")) body.display_name = $("#fName", dlg).value.trim();
    if (feat("notes")) body.notes = $("#fNotes", dlg).value;
    if (feat("require_totp")) body.totp_required = $("#fTotp", dlg).checked;
    if (feat("expiry")) {
      const expires = endOfDay($("#fExpires", dlg).value);
      if (expires !== u.expires_at && dateValue(expires) !== dateValue(u.expires_at)) body.expires_at = expires;
    }
    let out = await api("/users/update", body);
    if (!out.ok || !feat("grants")) return out;
    const ins = u.grants.find((x) => x.app === "insights");
    const same = ins && ins.money_view === g.money_view && JSON.stringify(ins.views) === JSON.stringify(g.views);
    if (g.insights && !same) out = await api("/users/grants", { id: u.id, app: "insights", enabled: true, ...insightsGrant(g) });
    else if (!g.insights && ins) out = await api("/users/grants", { id: u.id, app: "insights", enabled: false });
    if (!out.ok) return out;
    const had = u.grants.some((x) => x.app === "planner");
    if (g.planner !== had) out = await api("/users/grants", { id: u.id, app: "planner", enabled: g.planner });
    return out;
  }

  function wireAccount(u, err) {
    if (feat("activity")) api(`/activity?person=${encodeURIComponent(u.display_name)}&limit=50`).then((r) => {
      $("#userActivity", dlg).innerHTML = r.ok && r.events.length ? `<table>${activityRows(r.events)}</table>` : "No activity recorded.";
    });
    const typed = $("#fConfirmDel", dlg), delBtn = $("#fDelete", dlg);
    if (typed && delBtn) typed.addEventListener("input", () => { delBtn.disabled = typed.value !== u.username; });
    dlg.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "delete" && !typed && !confirm(`Delete ${u.display_name}? This cannot be undone.`)) return;
      if (act === "disable" && !confirm(`Disable ${u.display_name} and end their sessions?`)) return;
      const body = { id: u.id };
      if (act === "delete" && typed) {
        if (typed.value !== u.username) return err("Type the username exactly to delete this person.");
        body.confirm_username = typed.value;
      }
      if (act === "reset-password") {
        body.temp_password = $("#fResetPw", dlg).value;
        if (body.temp_password.length < MIN_PW) return err(`Temporary password must be at least ${MIN_PW} characters.`);
      }
      const out = await api(`/users/${act}`, body);
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
      const r = await api(`/activity?${q}`);
      $("#actRows").innerHTML = r.ok ? activityRows(r.events) : `<tr><td colspan="7" class="err">${esc(r.error)}</td></tr>`;
    };
    $("#actForm").addEventListener("submit", (e) => { e.preventDefault(); load(); });
    load();
  }

  async function showAudit() {
    const r = await api("/audit");
    const wide = r.ok && r.audit.some((a) => a.address !== undefined);  // the gateway log also records where from
    main.innerHTML = `<h2 class="page">Admin audit</h2><table><thead><tr><th>When</th><th>Admin</th><th>Action</th><th>Person</th><th>Details</th>${wide ? "<th>Address</th><th>Listener</th>" : ""}</tr></thead><tbody>${
      r.ok ? r.audit.map((a) => `<tr><td>${esc(when(a.at))}</td><td>${esc(a.admin)}</td><td>${esc(a.action)}</td><td>${esc(a.target_user)}</td><td>${esc(a.details)}</td>${wide ? `<td>${esc(a.address)}</td><td>${esc(a.listener)}</td>` : ""}</tr>`).join("") : `<tr><td colspan="5" class="err">${esc(r.error)}</td></tr>`}</tbody></table>`;
  }

  // ---- routing ----
  const PAGES = { users: showUsers, activity: showActivity, audit: showAudit };
  function route() {
    if (location.hash.startsWith("#sys-")) return;
    const wanted = location.hash.slice(1);
    const name = PAGES[wanted] && (!host.pages || host.pages.includes(wanted)) ? wanted : "users";
    document.querySelectorAll("nav a").forEach((a) => (a.dataset.page === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    PAGES[name]();
  }
  window.addEventListener("hashchange", route);
  route();
})();
