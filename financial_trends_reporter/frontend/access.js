// Owner-only People and Activity screens. Served on the local listener only (404 on the remote one).
// A modal dialog: add / reset / delete are staged, sent only on Save & Exit; Exit without Saving discards them.
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
  const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
  const MIN_PW = 10;

  const style = document.createElement("style");
  style.textContent = `
    #peopleDlg { width: min(860px, calc(100vw - 32px)); max-height: calc(100vh - 48px); padding: 0; border: 1px solid #c8c8cc; border-radius: 10px;
      background: var(--card-bg); color: inherit; box-shadow: 0 8px 32px rgba(0,0,0,.25); }
    #peopleDlg::backdrop { background: rgba(0,0,0,.35); }
    #peopleDlg .pd-body { padding: 16px 20px; overflow-y: auto; max-height: calc(100vh - 140px); font-size: 13px; }
    #peopleDlg h2 { font-size: 15px; margin: 4px 0 8px; }
    #peopleDlg table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    #peopleDlg th { text-align: left; font-weight: 600; opacity: .7; }
    #peopleDlg td, #peopleDlg th { padding: 3px 6px; vertical-align: middle; }
    #peopleDlg tr.pd-del td:not(:last-child) { text-decoration: line-through; opacity: .55; }
    #peopleDlg .pd-tag { font-size: 11px; padding: 0 6px; border-radius: 8px; background: rgba(37,99,235,.15); color: #2563eb; margin-left: 4px; }
    #peopleDlg button, #peopleDlg input { font-size: 13px; padding: 4px 8px; border-radius: 6px; border: 1px solid #ccc; background: transparent; color: inherit; }
    #peopleDlg button { cursor: pointer; }
    #peopleDlg .pd-form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 4px 0 12px; }
    #peopleDlg .pd-form[hidden] { display: none; }
    #peopleDlg .pd-err { color: #dc2626; font-size: 12px; min-height: 1em; }
    #peopleDlg .pd-foot { display: flex; gap: 8px; align-items: center; justify-content: flex-end; padding: 12px 20px; border-top: 1px solid #c8c8cc; }
    #peopleDlg .pd-foot .pd-count { margin-right: auto; font-size: 12px; opacity: .75; }
    #peopleDlg .pd-primary { background: #2563eb; border-color: #2563eb; color: #fff; font-weight: 600; }
    #peopleDlg .pd-primary:disabled { opacity: .45; cursor: default; }`;
  document.head.appendChild(style);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.id = "peopleBtn";
  btn.textContent = "People & Activity";
  btn.setAttribute("aria-haspopup", "dialog");
  const exit = document.getElementById("exitBtn");
  exit.parentNode.insertBefore(btn, exit);

  const dlg = document.createElement("dialog");
  dlg.id = "peopleDlg";
  dlg.setAttribute("aria-labelledby", "pdTitle");
  dlg.innerHTML = `<div class="pd-body" id="pdBody"></div>
    <div class="pd-foot"><span class="pd-count" id="pdCount"></span>
      <button type="button" id="pdDiscard">Exit without Saving</button>
      <button type="button" id="pdSave" class="pd-primary">Save &amp; Exit</button></div>`;
  document.body.appendChild(dlg);
  const body = dlg.querySelector("#pdBody");

  let people = [];      // as last fetched from the server
  let events = [];      // activity rows shown
  let pending = [];     // staged: {kind:"add", display_name, username, temp_password} | {kind:"reset"|"delete", id, temp_password?}
  let error = "";

  const pendingFor = (id, kind) => pending.find((p) => p.id === id && p.kind === kind);
  const activityRows = (list) => list.map((e) => `<tr><td>${esc(when(e.at))}</td><td>${esc(e.person)}</td><td>${esc(e.listener)}</td><td>${esc(e.event)}</td><td>${esc(e.details)}</td><td>${esc(e.source)}</td></tr>`).join("");

  function render() {
    const rows = people.map((p) => {
      const del = pendingFor(p.id, "delete"), reset = pendingFor(p.id, "reset");
      const status = `${p.locked ? "locked " : ""}${p.must_change ? "must change password" : ""}${reset ? '<span class="pd-tag">password reset (unsaved)</span>' : ""}`;
      const actions = del ? `<button data-undo-del="${p.id}">Undo delete</button>`
        : `${reset ? `<button data-undo-reset="${p.id}">Undo reset</button>` : `<button data-reset="${p.id}">Reset password</button>`} <button data-del="${p.id}">Delete</button>`;
      return `<tr class="${del ? "pd-del" : ""}"><td>${esc(p.display_name)}</td><td>${esc(p.username)}</td><td>${esc(when(p.last_signin_at))}</td><td>${status}</td><td>${actions}</td></tr>`;
    }).join("");
    const added = pending.map((p, i) => (p.kind !== "add" ? "" : `<tr><td>${esc(p.display_name)}<span class="pd-tag">new (unsaved)</span></td><td>${esc(p.username)}</td><td>never</td><td>must change password</td><td><button data-undo-add="${i}">Remove</button></td></tr>`)).join("");
    body.innerHTML = `<h2 id="pdTitle">People</h2>
      <table><tr><th>Name</th><th>Username</th><th>Last sign-in</th><th>Status</th><th></th></tr>${rows}${added}</table>
      <div class="pd-form" id="pdResetForm" hidden><span id="pdResetFor"></span>
        <input id="pdResetPw" type="password" autocomplete="new-password" placeholder="Temporary password (${MIN_PW}+ characters)" size="30">
        <button type="button" id="pdResetOk">Stage reset</button> <button type="button" id="pdResetCancel">Cancel</button></div>
      <div class="pd-form"><strong>Add person:</strong>
        <input id="pdName" placeholder="Name" size="14"> <input id="pdUser" placeholder="Username" size="12" autocomplete="off">
        <input id="pdPw" type="password" autocomplete="new-password" placeholder="Temporary password (${MIN_PW}+)" size="22">
        <button type="button" id="pdAdd">Add</button></div>
      <div class="pd-err" role="alert">${esc(error)}</div>
      <p class="note">They must choose their own password at first sign-in. Nothing changes until you press Save &amp; Exit.</p>
      <h2>Activity</h2>
      <div class="pd-form">Person: <input id="actPerson" placeholder="exact name"> <button type="button" id="actFilter">Filter</button></div>
      <table id="pdActivity"><tr><th>When</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr>${activityRows(events)}</table>`;
    const n = pending.length;
    dlg.querySelector("#pdCount").textContent = n ? `${n} unsaved change${n === 1 ? "" : "s"}` : "No unsaved changes";
    dlg.querySelector("#pdSave").disabled = n === 0;
    wire();
  }

  function stage(change) { pending.push(change); error = ""; render(); }
  function unstage(pred) { pending = pending.filter((p) => !pred(p)); error = ""; render(); }
  function fail(msg) { error = msg; render(); }

  function wire() {
    body.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
      const id = Number(b.dataset.del);
      pending = pending.filter((p) => !(p.id === id && p.kind === "reset"));
      stage({ kind: "delete", id });
    }));
    body.querySelectorAll("[data-undo-del]").forEach((b) => b.addEventListener("click", () => unstage((p) => p.kind === "delete" && p.id === Number(b.dataset.undoDel))));
    body.querySelectorAll("[data-undo-reset]").forEach((b) => b.addEventListener("click", () => unstage((p) => p.kind === "reset" && p.id === Number(b.dataset.undoReset))));
    body.querySelectorAll("[data-undo-add]").forEach((b) => b.addEventListener("click", () => { const gone = pending[Number(b.dataset.undoAdd)]; unstage((p) => p === gone); }));
    const form = body.querySelector("#pdResetForm");
    body.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", () => {
      const p = people.find((x) => x.id === Number(b.dataset.reset));
      form.hidden = false;
      form.dataset.id = p.id;
      body.querySelector("#pdResetFor").textContent = `Reset password for ${p.display_name}:`;
      body.querySelector("#pdResetPw").focus();
    }));
    body.querySelector("#pdResetCancel").addEventListener("click", () => { form.hidden = true; });
    body.querySelector("#pdResetOk").addEventListener("click", () => {
      const temp = body.querySelector("#pdResetPw").value;
      if (temp.length < MIN_PW) return fail(`Temporary password must be at least ${MIN_PW} characters.`);
      stage({ kind: "reset", id: Number(form.dataset.id), temp_password: temp });
    });
    body.querySelector("#pdAdd").addEventListener("click", () => {
      const display_name = body.querySelector("#pdName").value.trim();
      const username = body.querySelector("#pdUser").value.trim();
      const temp_password = body.querySelector("#pdPw").value;
      if (!display_name || !username) return fail("Name and username are both needed.");
      const taken = people.some((p) => p.username.toLowerCase() === username.toLowerCase() && !pendingFor(p.id, "delete"))
        || pending.some((p) => p.kind === "add" && p.username.toLowerCase() === username.toLowerCase());
      if (taken) return fail(`Username "${username}" is already in use.`);
      if (temp_password.length < MIN_PW) return fail(`Temporary password must be at least ${MIN_PW} characters.`);
      stage({ kind: "add", display_name, username, temp_password });
    });
    body.querySelector("#actFilter").addEventListener("click", async () => {
      const person = body.querySelector("#actPerson").value.trim();
      const r = await fetch("/api/activity?person=" + encodeURIComponent(person)).then((x) => x.json());
      body.querySelector("#pdActivity").innerHTML = `<tr><th>When</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr>${activityRows(r.events)}`;
    });
  }

  async function load() {
    const [p, a] = await Promise.all([fetch("/api/people").then((r) => r.json()), fetch("/api/activity").then((r) => r.json())]);
    people = p.people;
    events = a.events;
    render();
  }

  // Deletes first (frees usernames), then resets, then adds. Stops at the first refusal and keeps the rest staged.
  async function save() {
    const order = { delete: 0, reset: 1, add: 2 };
    const queue = pending.slice().sort((x, y) => order[x.kind] - order[y.kind]);
    const saveBtn = dlg.querySelector("#pdSave");
    saveBtn.disabled = true;
    for (const c of queue) {
      const out = c.kind === "delete" ? await post("/api/people/delete", { id: c.id })
        : c.kind === "reset" ? await post("/api/people/reset", { id: c.id, temp_password: c.temp_password })
        : await post("/api/people", { display_name: c.display_name, username: c.username, temp_password: c.temp_password });
      if (out && out.success === false) {
        pending = pending.filter((p) => queue.indexOf(p) >= queue.indexOf(c));
        error = `Not saved: ${out.error || "the server refused this change"}. Earlier changes were saved.`;
        await load();
        return;
      }
    }
    pending = [];
    dlg.close();
  }

  function discard() {
    if (pending.length && !confirm(`Discard ${pending.length} unsaved change${pending.length === 1 ? "" : "s"}?`)) return;
    pending = [];
    dlg.close();
  }

  dlg.querySelector("#pdSave").addEventListener("click", save);
  dlg.querySelector("#pdDiscard").addEventListener("click", discard);
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); discard(); });   // Esc = Exit without Saving
  dlg.addEventListener("close", () => { pending = []; error = ""; });

  btn.addEventListener("click", () => {
    pending = [];
    error = "";
    people = [];
    events = [];
    render();
    dlg.showModal();
    fetch("/api/view", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ view: "people" }) }).catch(() => {});
    load();
  });
})();
