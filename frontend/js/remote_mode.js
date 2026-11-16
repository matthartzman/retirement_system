/* Remote mode (multi-user server, Phase 5): the one place the frontend learns it is served through the gateway.
   Desktop mode is untouched: nothing below runs under pywebview or file://, and everything is inert until
   GET /api/ping answers {"remote_mode": true}.
   1. Detection: window.RetirementRemote.enabled, class "remote-mode" on <html>, event "retirement-remote-mode".
   2. 401: ONE wrapper on window.fetch sends an expired session to /login (covers api_client.js, admin.js and
      every raw fetch). Matched only in remote mode or when the body says {"authenticated": false}.
   3. Keep-alive: the gateway's 15-minute idle clock restarts on every request. The 15-second status ping is
      therefore answered locally while the tab is hidden or the user idle, user activity sends one cheap touch
      a minute, and a notice with "Stay signed in" appears 3 minutes before expiry (running builds keep the
      session alive through their progress polling, by design).
   4. Hiding: controls for routes a remote worker refuses (src/server/remote_allowlist.py) are CSS-hidden. */
(function (global) {
  'use strict';
  const doc = global.document;
  const IDLE_MS = 15 * 60 * 1000, WARN_MS = 12 * 60 * 1000, ACTIVE_MS = 60 * 1000;
  const R = (global.RetirementRemote = { enabled: false, idleMs: IDLE_MS, warnMs: WARN_MS, now: () => Date.now() });
  const desktop = !global.location || global.location.protocol === 'file:' || !!(global.pywebview && global.pywebview.api);
  const rawFetch = global.fetch && global.fetch.bind(global);
  let lastTouch = R.now(), lastActivity = R.now(), lastPing = { success: true, remote_mode: true }, banner = null;
  const HIDE = ['.local-backup-card', '.monarch-autoupdate-card', '.conversion-notice', '#conversionNotice',
    '.feature-card:has([onclick*="openSystemConfigurationConsole"])', '[onclick*="recoverYtdAccountSetup"]',
    '[onclick*="clearAppCache"]', '[onclick*="shutdown()"]', 'a[href="/system-configuration"]'];
  const synthetic = (obj) => ({ ok: true, status: 200, statusText: 'OK', headers: { get: () => 'application/json' },
    json: async () => obj, text: async () => JSON.stringify(obj), clone() { return synthetic(obj); } });

  R.loginUrl = () => '/login?next=' + encodeURIComponent((global.location.pathname || '/') + (global.location.search || ''));
  R.toLogin = function () {
    if (R.leaving) return;
    R.leaving = true;
    try { global.location.assign(R.loginUrl()); } catch (_e) {}
  };
  R.setEnabled = function (on) {
    if (R.enabled === !!on) return;
    R.enabled = !!on;
    if (!on || !doc) return;
    doc.documentElement.classList.add('remote-mode');
    const exit = doc.querySelector('button[onclick="exitApp()"]');
    if (exit) exit.textContent = 'Sign out';
    if (!doc.getElementById('remoteModeCss')) {
      const st = doc.createElement('style');
      st.id = 'remoteModeCss';
      st.textContent = 'html.remote-mode :is(' + HIDE.join(',') + '){display:none!important}' +
        'html:not(.remote-mode) .remote-only{display:none!important}' +
        '#remoteSessionBanner{position:fixed;left:16px;right:16px;top:8px;z-index:100000;padding:10px 14px;' +
        'background:#fff8e1;color:#4a3b00;border:1px solid #c9a227;border-radius:8px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}';
      doc.head.appendChild(st);
    }
    if (global.dispatchEvent && global.CustomEvent) global.dispatchEvent(new global.CustomEvent('retirement-remote-mode'));
    try { if (typeof global.renderMain === 'function') global.renderMain(); } catch (_e) {}
  };

  // The gateway's "session over" 401 (or any 401 once we know we are remote).
  async function checkExpired(res) {
    let body = null;
    try { body = await res.clone().json(); } catch (_e) {}
    if (R.enabled || (body && body.authenticated === false)) R.toLogin();
  }
  R.wrapFetch = function (inner) {
    return async function (resource, opts) {
      const url = typeof resource === 'string' ? resource : String((resource && resource.url) || resource);
      const path = url.split('?')[0];
      const method = String((opts && opts.method) || 'GET').toUpperCase();
      const isPing = method === 'GET' && /(^|\/)api\/ping$/.test(path);
      if (R.enabled && isPing && (doc.hidden || R.now() - lastActivity > ACTIVE_MS)) return synthetic(lastPing);
      const res = await inner(resource, opts);
      if (res && res.status === 401 && /\/api\//.test(path) && !/\/api\/auth\/(login|totp)/.test(path)) await checkExpired(res);
      else if (res && res.ok && /\/api\//.test(path)) {
        lastTouch = R.now();
        hideBanner();
        if (isPing) {
          try { const j = await res.clone().json(); if (j && j.remote_mode) { lastPing = j; R.setEnabled(true); } } catch (_e) {}
        }
      }
      return res;
    };
  };

  function hideBanner() { if (banner) { banner.remove(); banner = null; } }
  R.touch = function () { return rawFetch ? global.fetch('/api/auth/session', { cache: 'no-store' }).catch(function () {}) : null; };
  function tick() {
    if (!R.enabled || !doc) return;
    const idle = R.now() - lastTouch;
    if (idle < WARN_MS) return hideBanner();
    const left = Math.max(0, Math.ceil((IDLE_MS - idle) / 60000));
    const text = idle >= IDLE_MS ? 'Your session has expired. Sign in again to keep working.'
      : 'Your session expires in about ' + left + ' minute' + (left === 1 ? '' : 's') + ' because of inactivity.';
    if (!banner) {
      banner = doc.createElement('div');
      banner.id = 'remoteSessionBanner';
      banner.setAttribute('role', 'alert');
      doc.body.appendChild(banner);
    }
    banner.innerHTML = '';
    const span = doc.createElement('span'), btn = doc.createElement('button');
    span.textContent = text;
    btn.type = 'button';
    btn.className = 'btn';
    btn.textContent = idle >= IDLE_MS ? 'Sign in' : 'Stay signed in';
    btn.onclick = idle >= IDLE_MS ? R.toLogin : function () { R.touch(); };
    banner.appendChild(span);
    banner.appendChild(btn);
  }
  R.tick = tick;
  function onActivity() {
    lastActivity = R.now();
    if (R.enabled && lastActivity - lastTouch > ACTIVE_MS) { lastTouch = lastActivity; R.touch(); }
  }
  R.signOutFlow = async function () {
    const dirty = global.unsavedChangeCount && global.unsavedChangeCount();
    if (dirty && !(await global.showInAppConfirm('You have unsaved changes that will be lost.', { title: 'Sign out', confirmLabel: 'Sign out anyway', variant: 'warn' }))) return;
    return R.signOut();
  };
  R.signOut = async function () {
    try { await global.RetirementApiClient.request('/api/auth/logout', { method: 'POST', body: '{}' }); } catch (_e) {}
    R.leaving = true;
    global.location.assign('/login');
  };

  if (!desktop && rawFetch) {
    global.fetch = R.wrapFetch(rawFetch);
    R.ready = global.fetch('/api/ping', { cache: 'no-store' }).catch(function () {});
    if (doc) {
      ['keydown', 'pointerdown', 'touchstart'].forEach(function (ev) { doc.addEventListener(ev, onActivity, { passive: true, capture: true }); });
      doc.addEventListener('visibilitychange', function () { if (!doc.hidden) onActivity(); });
      if (global.setInterval) global.setInterval(tick, 15000);
    }
  }
})(window);
