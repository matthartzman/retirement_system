(function () {
  "use strict";
  var csrf = null;
  var session = null;

  function $(id) { return document.getElementById(id); }

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text !== undefined && text !== null) { e.textContent = String(text); }
    if (cls) { e.className = cls; }
    return e;
  }

  function say(msg, ok) {
    var s = $("status");
    if (!s) { return; }
    s.textContent = msg || "";
    s.className = ok ? "status ok" : "status";
  }

  function getSession() {
    return fetch("/api/auth/session", { credentials: "same-origin" }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 200 && j.csrf_token) { csrf = j.csrf_token; session = j; }
        return { status: r.status, json: j };
      });
    });
  }

  function api(method, path, body) {
    var ready = (csrf || method === "GET") ? Promise.resolve() : getSession();
    return ready.then(function () {
      var headers = { "Accept": "application/json" };
      var opts = { method: method, headers: headers, credentials: "same-origin" };
      if (method !== "GET") {
        if (csrf) { headers["X-CSRF-Token"] = csrf; }
        headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body || {});
      }
      return fetch(path, opts);
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        return { status: r.status, json: j };
      });
    });
  }

  function errText(res, fallback) {
    if (res.json && res.json.error) { return res.json.error; }
    if (res.status === 429) { return "Too many attempts. Try again later."; }
    return fallback || "Request failed (" + res.status + ").";
  }

  function nextPath() {
    var n = new URLSearchParams(location.search).get("next") || "";
    if (n.charAt(0) === "/" && n.charAt(1) !== "/" && n.charAt(1) !== "\\") { return n; }
    return "/";
  }

  function toLogin() {
    location.href = "/login?next=" + encodeURIComponent(location.pathname);
  }

  function busy(form, on) {
    var b = form.querySelector("button[type=submit]");
    if (b) { b.disabled = on; }
  }

  function onSubmit(form, fn) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      say("");
      busy(form, true);
      Promise.resolve(fn()).catch(function () {
        say("Network error. Please try again.");
      }).then(function () { busy(form, false); });
    });
  }

  /* ---------- login ---------- */
  function initLogin() {
    var pw = $("login-form"), cf = $("code-form");
    function showCode() {
      pw.classList.add("hidden");
      cf.classList.remove("hidden");
      $("code").focus();
    }
    function showPassword() {
      cf.classList.add("hidden");
      pw.classList.remove("hidden");
      $("password").value = "";
      $("code").value = "";
    }
    getSession().then(function (r) {
      if (r.status === 200 && r.json.stage === "active") { location.href = nextPath(); }
      else if (r.status === 200 && r.json.stage === "pending") { showCode(); }
    }).catch(function () {});
    onSubmit(pw, function () {
      return api("POST", "/api/auth/login", {
        username: $("username").value.trim(), password: $("password").value
      }).then(function (r) {
        if (r.status !== 200 || !r.json.success) {
          $("password").value = "";
          say(errText(r, "Sign-in failed."));
          return;
        }
        if (r.json.csrf_token) { csrf = r.json.csrf_token; }
        if (r.json.next === "enrol") { location.href = "/gateway/enrol"; }
        else { showCode(); }
      });
    });
    onSubmit(cf, function () {
      return api("POST", "/api/auth/totp/verify", { code: $("code").value.trim() }).then(function (r) {
        if (r.status === 200 && r.json.success) { location.href = nextPath(); return; }
        say(errText(r, "Incorrect code."));
        if (r.status === 401) { showPassword(); } else { $("code").select(); }
      });
    });
  }

  /* ---------- enrol ---------- */
  function initEnrol() {
    api("POST", "/api/auth/totp/enrol/start", {}).then(function (r) {
      if (r.status === 401) { say("Your sign-in expired. Please sign in again."); return; }
      if (r.status !== 200 || !r.json.secret) { say(errText(r)); return; }
      $("secret").textContent = r.json.secret.replace(/\s+/g, "").replace(/(.{4})(?=.)/g, "$1 ");
      if (r.json.qr_svg_data_uri) { $("qr").src = r.json.qr_svg_data_uri; $("qr").hidden = false; }
      var a = $("uri");
      a.href = r.json.otpauth_uri;
      a.textContent = r.json.otpauth_uri;
    }).catch(function () { say("Network error. Please try again."); });
    onSubmit($("confirm-form"), function () {
      return api("POST", "/api/auth/totp/enrol/confirm", { code: $("code").value.trim() }).then(function (r) {
        if (r.status === 200 && r.json.success !== false) { location.href = "/"; return; }
        if (r.status === 401) {
          var s = $("status");
          s.textContent = "Your sign-in expired. ";
          var a = el("a", "Sign in again");
          a.href = "/login";
          s.appendChild(a);
          return;
        }
        say(errText(r, "Incorrect code."));
        $("code").select();
      });
    });
  }

  /* ---------- account ---------- */
  function initAccount() {
    getSession().then(function (r) {
      if (r.status === 401) { toLogin(); return; }
      var u = r.json.user || {};
      $("who-name").textContent = u.display_name || u.username || "";
      $("who-user").textContent = u.username || "";
      $("who-role").textContent = u.role || "";
      if (u.role === "admin") { $("users-link").classList.remove("hidden"); }
      if (u.must_change) { $("must").classList.remove("hidden"); }
    }).catch(function () { say("Could not load your account."); });
    $("logout").addEventListener("click", function () {
      api("POST", "/api/auth/logout", {}).catch(function () {}).then(function () {
        location.href = "/login";
      });
    });
    onSubmit($("pw-form"), function () {
      var cur = $("current").value, nw = $("new").value;
      if (nw !== $("confirm").value) { say("The new passwords do not match."); return; }
      if (nw.length < 12) { say("The new password must be at least 12 characters."); return; }
      return api("POST", "/api/auth/password", { current: cur, "new": nw }).then(function (r) {
        if (r.status === 401 && !r.json.error) { toLogin(); return; }
        if (r.status !== 200 || r.json.success === false) { say(errText(r)); return; }
        say("Password changed. Redirecting...", true);
        setTimeout(function () { location.href = "/"; }, 1200);
      });
    });
  }

  /* ---------- users ---------- */
  var BASE = "/api/auth/admin/users";

  function fmtTime(sec) {
    return sec ? new Date(sec * 1000).toLocaleString() : "never";
  }

  function act(path, body) {
    return api("POST", path, body || {}).then(function (r) {
      if (r.status === 401 && !r.json.error) { toLogin(); return; }
      if (r.status !== 200 || r.json.success === false) { say(errText(r)); }
      else { say(""); }
      return loadUsers();
    }).catch(function () { say("Network error. Please try again."); });
  }

  var users = [];
  var current = null;
  var MIN_PW = 12;

  function tag(text, bad) {
    var t = el("span", text, bad ? "tag bad" : "tag");
    return t;
  }

  function userRow(u) {
    var tr = document.createElement("tr");
    if (u.disabled) { tr.className = "off"; }
    var status = document.createElement("td");
    var any = false;
    [[u.disabled, "disabled", true], [u.locked, "locked", true], [u.must_change, "must change", false]]
      .forEach(function (f) { if (f[0]) { status.appendChild(tag(f[1], f[2])); any = true; } });
    if (!any) { status.textContent = "active"; }
    [u.display_name, u.username, u.role === "admin" ? "Administrator" : "User"]
      .forEach(function (t) { tr.appendChild(el("td", t)); });
    tr.appendChild(status);
    tr.appendChild(el("td", u.totp));
    tr.appendChild(el("td", fmtTime(u.last_login_at)));
    var td = document.createElement("td");
    var b = el("button", "Edit");
    b.type = "button";
    b.addEventListener("click", function () { openDialog(u); });
    td.appendChild(b);
    tr.appendChild(td);
    return tr;
  }

  function dlgErr(msg) { $("form-err").textContent = msg || ""; }

  function openDialog(u) {
    current = u;
    var dlg = $("user-dialog");
    dlgErr("");
    $("user-form").reset();
    $("dlg-title").textContent = u ? "Edit " + u.display_name : "Add person";
    var label = u ? "Save changes" : "Add person";
    $("u-save").textContent = label;
    $("u-save-top").textContent = label;
    $("u-display").value = u ? u.display_name : "";
    $("u-display").readOnly = !!u;
    $("u-username").value = u ? u.username : "";
    $("u-username").readOnly = !!u;
    $("u-role").value = u ? u.role : "user";
    $("u-added").textContent = (u && u.created_at ? new Date(u.created_at * 1000) : new Date()).toLocaleDateString();
    $("u-temp-field").classList.toggle("hidden", !!u);
    $("u-acts").classList.toggle("hidden", !u);
    $("u-acts").open = false;
    if (u) {
      $("u-toggle").textContent = u.disabled ? "Enable" : "Disable";
      $("u-unlock").classList.toggle("hidden", !u.locked);
    }
    dlg.showModal();
    (u ? $("u-role") : $("u-display")).focus();
  }

  function closeDialog() { $("user-dialog").close(); }

  /* One call; on refusal show the server's (generic) message inside the dialog and keep it open. */
  function dlgCall(path, body) {
    return api("POST", path, body || {}).then(function (r) {
      if (r.status === 401 && !r.json.error) { toLogin(); return false; }
      if (r.status !== 200 || r.json.success === false) { dlgErr(errText(r)); return false; }
      return true;
    }).catch(function () { dlgErr("Network error. Please try again."); return false; });
  }

  function refresh() { return loadUsers().then(loadAudit); }

  function saveDialog() {
    dlgErr("");
    if (!current) {
      var name = $("u-display").value.trim(), user = $("u-username").value.trim(), pw = $("u-temp").value;
      if (!name || !user) { dlgErr("Name and username are both needed."); return Promise.resolve(); }
      if (pw.length < MIN_PW) { dlgErr("Temporary password must be at least " + MIN_PW + " characters."); return Promise.resolve(); }
      return dlgCall(BASE, { username: user, display_name: name, role: $("u-role").value, temp_password: pw })
        .then(function (ok) { if (ok) { closeDialog(); say("Person added.", true); return refresh(); } });
    }
    if ($("u-role").value === current.role) { closeDialog(); return Promise.resolve(); }
    return dlgCall(BASE + "/" + encodeURIComponent(current.id) + "/role", { role: $("u-role").value })
      .then(function (ok) { if (ok) { closeDialog(); say(""); return refresh(); } });
  }

  function runAction(act) {
    var u = current, p = BASE + "/" + encodeURIComponent(u.id), call;
    if (act === "delete") {
      if (!window.confirm("Delete " + u.display_name + "? This cannot be undone.")) { return Promise.resolve(); }
      call = dlgCall(p + "/delete");
    } else if (act === "toggle") {
      if (!u.disabled && !window.confirm("Disable " + u.display_name + " and end their sessions?")) { return Promise.resolve(); }
      call = dlgCall(p + "/disabled", { disabled: !u.disabled });
    } else if (act === "reset-password") {
      var t = $("u-reset").value;
      if (t.length < MIN_PW) { dlgErr("Temporary password must be at least " + MIN_PW + " characters."); return Promise.resolve(); }
      call = dlgCall(p + "/reset-password", { temp_password: t });
    } else {
      call = dlgCall(p + "/" + act);
    }
    dlgErr("");
    return call.then(function (ok) { if (ok) { closeDialog(); say(""); return refresh(); } });
  }

  function fill(id, rows) {
    var body = $(id);
    while (body.firstChild) { body.removeChild(body.firstChild); }
    rows.forEach(function (r) { body.appendChild(r); });
  }

  function loadUsers() {
    return api("GET", BASE).then(function (r) {
      if (r.status === 401) { toLogin(); return; }
      if (r.status !== 200) { say(errText(r)); return; }
      users = r.json.users || [];
      $("user-count").textContent = users.length + (users.length === 1 ? " person" : " people");
      fill("users-body", users.map(userRow));
    });
  }

  function loadAudit() {
    return api("GET", "/api/auth/admin/audit?limit=200").then(function (r) {
      if (r.status !== 200) { return; }
      fill("audit-body", (r.json.events || []).map(function (e) {
        var tr = document.createElement("tr");
        var d = e.details;
        if (d && typeof d === "object") { d = JSON.stringify(d); }
        [fmtTime(e.at), e.actor_username || "", e.event, e.target_username || "", d || "",
          (e.client_ip || "") + (e.listener ? " (" + e.listener + ")" : "")]
          .forEach(function (t) { tr.appendChild(el("td", t)); });
        return tr;
      }));
    });
  }

  function initUsers() {
    loadUsers().then(loadAudit).catch(function () { say("Could not load users."); });
    $("add-user").addEventListener("click", function () { openDialog(null); });
    $("u-close").addEventListener("click", closeDialog);
    $("user-form").addEventListener("submit", function (ev) {
      ev.preventDefault();
      saveDialog();
    });
    Array.prototype.forEach.call(document.querySelectorAll("[data-act]"), function (b) {
      b.addEventListener("click", function () { runAction(b.getAttribute("data-act")); });
    });
  }

  var pages = { login: initLogin, enrol: initEnrol, account: initAccount, users: initUsers };
  var page = document.body.getAttribute("data-page");
  if (pages[page]) { pages[page](); }
})();
