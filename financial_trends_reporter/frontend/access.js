// Owner-only People and Activity screens. Served on the local listener only (404 on the remote one).
(function () {
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
  const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());

  const btn = document.createElement("button");
  btn.type = "button";
  btn.textContent = "People & Activity";
  const exit = document.getElementById("exitBtn");
  exit.parentNode.insertBefore(btn, exit);

  const panel = document.createElement("div");
  panel.style.cssText = "display:none;margin:12px 0;padding:12px;border:1px solid #ccc;border-radius:6px;background:#fff";
  exit.closest("body").insertBefore(panel, document.body.children[1] || null);

  async function render() {
    const [people, activity] = await Promise.all([
      fetch("/api/people").then((r) => r.json()),
      fetch("/api/activity").then((r) => r.json()),
    ]);
    const rows = people.people.map((p) => `<tr><td>${esc(p.display_name)}</td><td>${esc(p.username)}</td><td>${esc(when(p.last_signin_at))}</td>
      <td>${p.locked ? "locked " : ""}${p.must_change ? "must change password" : ""}</td>
      <td><button data-reset="${p.id}">Reset password</button> <button data-del="${p.id}">Delete</button></td></tr>`).join("");
    const events = activity.events.map((e) => `<tr><td>${esc(when(e.at))}</td><td>${esc(e.person)}</td><td>${esc(e.listener)}</td><td>${esc(e.event)}</td><td>${esc(e.details)}</td><td>${esc(e.source)}</td></tr>`).join("");
    panel.innerHTML = `<h2>People</h2>
      <table><tr><th>Name</th><th>Username</th><th>Last sign-in</th><th></th><th></th></tr>${rows}</table>
      <p><button id="addPerson">Add person…</button></p>
      <h2>Activity</h2>
      <p>Person: <input id="actPerson" placeholder="exact name"> <button id="actFilter">Filter</button></p>
      <table><tr><th>When</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr>${events}</table>`;
    panel.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", async () => {
      const temp = prompt("Temporary password (at least 10 characters). They must change it at next sign-in:");
      if (!temp) return;
      const out = await post("/api/people/reset", { id: Number(b.dataset.reset), temp_password: temp });
      if (!out.success) alert(out.error);
      render();
    }));
    panel.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
      if (!confirm("Delete this person? Their sessions end immediately.")) return;
      await post("/api/people/delete", { id: Number(b.dataset.del) });
      render();
    }));
    panel.querySelector("#addPerson").addEventListener("click", async () => {
      const display_name = prompt("Name:");
      const username = display_name && prompt("Username (they type this to sign in):");
      const temp_password = username && prompt("Temporary password (at least 10 characters):");
      if (!temp_password) return;
      const out = await post("/api/people", { display_name, username, temp_password });
      if (!out.success) alert(out.error);
      render();
    });
    panel.querySelector("#actFilter").addEventListener("click", async () => {
      const person = panel.querySelector("#actPerson").value.trim();
      const r = await fetch("/api/activity?person=" + encodeURIComponent(person)).then((x) => x.json());
      const body = r.events.map((e) => `<tr><td>${esc(when(e.at))}</td><td>${esc(e.person)}</td><td>${esc(e.listener)}</td><td>${esc(e.event)}</td><td>${esc(e.details)}</td><td>${esc(e.source)}</td></tr>`).join("");
      panel.querySelectorAll("table")[1].innerHTML = `<tr><th>When</th><th>Person</th><th>Where</th><th>Event</th><th>Details</th><th>From</th></tr>${body}`;
    });
  }

  btn.addEventListener("click", () => {
    const show = panel.style.display === "none";
    panel.style.display = show ? "block" : "none";
    if (show) {
      fetch("/api/view", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ view: "people" }) }).catch(() => {});
      render();
    }
  });
})();
