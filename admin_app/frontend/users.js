// Users & access: people list, add/edit with app grants, account actions, activity by app, admin audit.
// No inline handlers or styles (the page's CSP forbids them); every dynamic string goes through esc().
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
  const day = (t) => (t ? new Date(t * 1000).toLocaleDateString() : "none");
  const host = window.AdminHost || {};  // a hosting page (the gateway) may set this first; see src/gateway/pages/admin-gateway.js
  const api = (path, body) => (host.fetch || fetch)((host.apiBase || "/api") + path, body === undefined ? undefined
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json().then((j) => ({ ok: r.ok && j.success !== false, ...j })))
    .catch(() => ({ ok: false, error: "The Admin app did not answer." }));
  let MIN_PW = 10;
  const MONEY = { dollars: "Dollars", percent: "Percent", both: "Both" };
  const APP_LABEL = { insights: "Financial Insights", planner: "Retirement Planner" };
  const main = $("#main");
  let meta = { views: [] }, users = [];
  const feat = (n) => !meta.features || meta.features[n] !== false;  // false = this host has no such thing, so hide it

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
    users = r.users; meta = r; MIN_PW = r.min_password || MIN_PW;
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
      ${u ? `<details class="acts"><summary>${host.maintenance || "Password, sessions and removal"}</summary>${host.note || ""}
        ${field("New temporary password", '<input id="fResetPw" type="password" autocomplete="new-password">')}
        <div class="actions"><button type="button" data-act="reset-password">Reset password</button>${feat("end_sessions") ? '<button type="button" data-act="end-sessions">End sessions</button>' : ""}<button type="button" data-act="reset-totp">Reset two-factor</button>${host.showCode ? '<button type="button" data-act="enrol-code">New enrolment code</button>' : ""}
        ${host.sections ? "" : `<button type="button" data-act="${u.status === "disabled" ? "enable" : "disable"}">${u.status === "disabled" ? "Enable" : "Disable"}</button>`}${host.removal ? "" : '<button type="button" class="danger" data-act="delete">Delete</button>'}</div>${host.removal ? host.removal(u) : ""}</details>` : ""}</section>`;
    const planner = sec("Retirement Planner", tog("Can use the Retirement Planner", u ? u.grants.some((g) => g.app === "planner") : false, 'id="gPlanner"', "stored now; enforced when the multi-user server arrives"), true);
    const insights = sec("Financial Insights", `${field("Money shown as", `<select id="gMoney">${Object.entries(MONEY).map(([v, l]) => `<option value="${v}"${(ins ? ins.money_view : "percent") === v ? " selected" : ""}>${l}</option>`).join("")}</select>`)}
      ${tog("Can sign in", u ? !!ins : true, 'id="gInsights"')} ${tog("Require two-factor sign-in", !u || u.totp_required, 'id="fTotp"', u && u.totp_enrolled ? "already set up" : "")}
      ${meta.views.map((v) => tog(esc(v), allowed.includes(v), `data-view="${esc(v)}"`)).join("")}`, true);
    return `<form id="userForm" novalidate><header class="dhead"><h2 id="dlgTitle">${u ? `Edit ${esc(u.display_name)}` : "Add person"}</h2>
      <div class="dact"><button type="button" id="fCancel">Close</button><button type="submit" class="primary" id="fSave">${save}</button></div><div class="err" id="formErr" role="alert"></div></header>
      ${account}${host.sections ? host.sections(u, { tog, sec, field, esc, MONEY }) : feat("grants") ? planner + insights : ""}${u && feat("activity") ? sec(`Activity for ${esc(u.display_name)}`, '<div id="userActivity" class="note">Loading&hellip;</div>') : ""}
      ${feat("notes") ? `<label class="field"><span>Notes</span><textarea id="fNotes" rows="2" maxlength="500">${esc(u ? u.notes : "")}</textarea></label>` : ""}</form>`;
  }

  function readGrants() {
    if (!feat("grants")) return {};
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
      if (!out.ok) return err(out.error || "The change was refused."); await (host.showCode && host.showCode(out, u ? u.display_name : $("#fName", dlg).value.trim()));  // SEC-04: gateway shows the one-time enrolment code once
      dlg.close();
      showUsers();
    });
    if (u) wireAccount(u, err);
    dlg.showModal();
    $("#fName", dlg).focus();
  }

  const insightsGrant = (g) => ({ money_view: g.money_view, views: g.views }); const extras = () => ({ ...(host.collect && host.collect(dlg)), ...(feat("notes") && { notes: $("#fNotes", dlg).value }), ...(feat("require_totp") && { totp_required: $("#fTotp", dlg).checked }) });

  async function saveNew(g) {
    const name = $("#fName", dlg).value.trim(), username = $("#fUser", dlg).value.trim(), pw = $("#fPw", dlg).value;
    if (!name || !username) return { error: "Name and username are both needed." };
    if (pw.length < MIN_PW) return { error: `Temporary password must be at least ${MIN_PW} characters.` };
    const out = await api("/users", { display_name: name, username, temp_password: pw, role: $("#fRole", dlg).value, ...extras(),
      ...(feat("expiry") && { expires_at: endOfDay($("#fExpires", dlg).value) }), ...(feat("grants") && { grants: { insights: g.insights ? insightsGrant(g) : null, planner: g.planner } }) }); const done = host.after ? await host.after(out, null, dlg, api) : out; return out.enrol_code && done.ok ? { ...done, enrol_code: out.enrol_code, enrol_code_minutes: out.enrol_code_minutes } : done;  // SEC-04: keep the one-time code through the after-hook
  }

  async function saveEdit(u, g) {
    const body = { id: u.id, role: $("#fRole", dlg).value, ...(feat("edit_name") && { display_name: $("#fName", dlg).value.trim() }), ...extras() };
    const expires = feat("expiry") ? endOfDay($("#fExpires", dlg).value) : u.expires_at;
    if (expires !== u.expires_at && dateValue(expires) !== dateValue(u.expires_at)) body.expires_at = expires;
    let out = await api("/users/update", body); if (host.after) out = await host.after(out, u, dlg, api);
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
    if (host.wire) host.wire(dlg, u); if (feat("activity")) api(`/activity?person=${encodeURIComponent(u.display_name)}&limit=50`).then((r) => {
      $("#userActivity", dlg).innerHTML = r.ok && r.events.length ? `<table>${activityRows(r.events)}</table>` : "No activity recorded.";
    });
    dlg.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
      const act = b.dataset.act;
      if (act === "delete" && !host.removal && !confirm(`Delete ${u.display_name}? This cannot be undone.`)) return;
      if (act === "disable" && !confirm(`Disable ${u.display_name} and end their sessions?`)) return;
      const body = { id: u.id, ...(host.actBody && host.actBody(act, dlg)) };
      if (act === "reset-password") {
        body.temp_password = $("#fResetPw", dlg).value;
        if (body.temp_password.length < MIN_PW) return err(`Temporary password must be at least ${MIN_PW} characters.`);
      }
      const out = await api(`/users/${act}`, body);
      if (!out.ok) return err(out.error || "The change was refused."); await (host.showCode && host.showCode(out, u.display_name));
      dlg.close();
      showUsers();
    }));
  }

  // ---- activity and audit ----
  const activityRows = (list) => list.map((e) => `<tr><td>${esc(when(e.at))}</td><td>${esc(e.app)}</td><td>${esc(e.person)}</td><td>${esc(e.listener)}</td><td>${esc(e.event)}</td><td>${esc(e.details)}</td><td>${esc(e.source)}</td></tr>`).join("");

  async function showActivity() {
    main.innerHTML = `<h2 class="page">Activity</h2>
      <form class="bar" id="actForm"><label>App <select id="actApp"><option value="">All apps</option><option value="insights">Financial Insights</option><option value="planner">Retirement Planner</option></select></label>
        <label>Person <select id="actPerson"><option value="">All people</option></select></label><button type="submit">Filter</button></form>
      <table><thead><tr><th>When</th><th>App</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr></thead><tbody id="actRows"></tbody></table>`;
    const load = async () => {
      const q = new URLSearchParams({ app: $("#actApp").value, person: $("#actPerson").value });
      const r = await api(`/activity?${q}`), pick = $("#actPerson").value; if (r.ok) $("#actPerson").innerHTML = ["", ...(r.people || [])].map((p) => `<option value="${esc(p)}"${p === pick ? " selected" : ""}>${esc(p || "All people")}</option>`).join("");
      $("#actRows").innerHTML = r.ok ? activityRows(r.events) : `<tr><td colspan="7" class="err">${esc(r.error)}</td></tr>`;
    };
    $("#actForm").addEventListener("submit", (e) => { e.preventDefault(); load(); }); $("#actPerson").addEventListener("change", () => load()); $("#actApp").addEventListener("change", () => { $("#actPerson").value = ""; load(); });
    load();
  }

  async function showAudit() {
    const r = await api("/audit"), w = r.ok && r.audit.some((a) => a.address !== undefined);  // the gateway log also says where from
    main.innerHTML = `<h2 class="page">Admin audit</h2><table><thead><tr><th>When</th><th>Admin</th><th>Action</th><th>Person</th><th>Details</th>${w ? "<th>Address</th><th>Listener</th>" : ""}</tr></thead><tbody>${
      r.ok ? r.audit.map((a) => `<tr><td>${esc(when(a.at))}</td><td>${esc(a.admin)}</td><td>${esc(a.action)}</td><td>${esc(a.target_user)}</td><td>${esc(a.details)}</td>${w ? `<td>${esc(a.address)}</td><td>${esc(a.listener)}</td>` : ""}</tr>`).join("") : `<tr><td colspan="5" class="err">${esc(r.error)}</td></tr>`}</tbody></table>`;
  }

  // ---- routing ----
  const PAGES = { users: showUsers, activity: showActivity, audit: showAudit };
  function route() {
    if (location.hash.startsWith("#sys-")) return;
    const name = PAGES[location.hash.slice(1)] && (!host.pages || host.pages.includes(location.hash.slice(1))) ? location.hash.slice(1) : "users";
    document.querySelectorAll("nav a").forEach((a) => (a.dataset.page === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    PAGES[name]();
  }
  window.addEventListener("hashchange", route); route();
})();
