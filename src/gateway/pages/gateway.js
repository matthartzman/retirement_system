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

  function actionButton(cell, label, cls, fn) {
    var b = el("button", label, "small " + cls);
    b.type = "button";
    b.addEventListener("click", fn);
    cell.appendChild(b);
  }

  function userRow(u) {
    var tr = document.createElement("tr");
    var st = [];
    if (u.disabled) { st.push("disabled"); }
    if (u.locked) { st.push("locked"); }
    if (u.must_change) { st.push("must change"); }
    [u.display_name, u.username, u.role, st.join(", ") || "ok", u.totp, fmtTime(u.last_login_at)]
      .forEach(function (t) { tr.appendChild(el("td", t)); });
    var td = document.createElement("td");
    var p = BASE + "/" + encodeURIComponent(u.id);
    actionButton(td, u.role === "admin" ? "Make user" : "Make admin", "secondary", function () {
      act(p + "/role", { role: u.role === "admin" ? "user" : "admin" });
    });
    actionButton(td, u.disabled ? "Enable" : "Disable", "secondary", function () {
      act(p + "/disabled", { disabled: !u.disabled });
    });
    if (u.locked) {
      actionButton(td, "Unlock", "secondary", function () { act(p + "/unlock"); });
    }
    actionButton(td, "Reset password", "secondary", function () {
      var t = window.prompt("Temporary password for " + u.username + " (at least 12 characters):");
      if (t === null) { return; }
      if (t.length < 12) { say("The temporary password must be at least 12 characters."); return; }
      act(p + "/reset-password", { temp_password: t });
    });
    actionButton(td, "Reset two-factor", "secondary", function () { act(p + "/reset-totp"); });
    actionButton(td, "Delete", "danger", function () {
      if (window.confirm("Delete user " + u.username + "? This cannot be undone.")) {
        act(p + "/delete");
      }
    });
    tr.appendChild(td);
    return tr;
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
      fill("users-body", (r.json.users || []).map(userRow));
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
    onSubmit($("create-form"), function () {
      return api("POST", BASE, {
        username: $("c-username").value.trim(),
        display_name: $("c-display").value.trim(),
        role: $("c-role").value,
        temp_password: $("c-temp").value
      }).then(function (r) {
        if (r.status === 401 && !r.json.error) { toLogin(); return; }
        if (r.status !== 200 || r.json.success === false) { say(errText(r)); return; }
        say("User created.", true);
        $("create-form").reset();
        return loadUsers().then(loadAudit);
      });
    });
  }

  var pages = { login: initLogin, enrol: initEnrol, account: initAccount, users: initUsers };
  var page = document.body.getAttribute("data-page");
  if (pages[page]) { pages[page](); }
})();
