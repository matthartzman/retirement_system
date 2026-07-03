/**
 * Android Bridge — Retirement System v10
 *
 * Intercepts window.fetch() and window.EventSource so the unmodified
 * dashboard/admin scripts can run inside the Android WebView shell without an
 * HTTP socket, exactly like frontend/js/pywebview_bridge.js does for the
 * PyWebView desktop shell. This file is the third transport described in
 * documentation/ANDROID_MOBILE_ENHANCEMENT_PLAN.md: same route registry,
 * different plumbing to reach it.
 *
 * Why this isn't just another branch in pywebview_bridge.js: PyWebView's
 * js_api methods return real Promises to JS automatically. Android's
 * `WebView.addJavascriptInterface()` only exposes synchronous, primitive-only
 * methods — calling one from JS blocks the JS thread until it returns, which
 * is unacceptable for a workbook build that can run for a minute or more.
 * So the transport here is fire-and-forget + callback instead of
 * call-and-return:
 *
 *   1. JS calls window.AndroidBridge.request(method, url, bodyJsonText,
 *      bodyText, requestId) — a void method, dispatched on a background
 *      executor on the Kotlin side.
 *   2. Kotlin calls the Python route registry in-process (src/android_api.py,
 *      mirroring src/desktop_api.py) and, when done, posts back to the WebView
 *      thread and calls window.__androidBridgeResolve(requestId, resultJson).
 *   3. This file keeps a pending-request map keyed by requestId and resolves
 *      the matching Promise when that callback fires.
 *
 * Binary responses (`_binary`) are handed to Kotlin's saveFile() (which
 * writes via MediaStore/ACTION_CREATE_DOCUMENT) instead of the Blob-anchor
 * download trick pywebview_bridge.js uses — Android WebView does not reliably
 * surface blob: downloads to the system Downloads folder.
 *
 * This file is a no-op when window.AndroidBridge is absent (i.e., normal
 * browser use or the PyWebView desktop shell), so it is safe to always load
 * it alongside pywebview_bridge.js.
 */
(function () {
  'use strict';

  if (!window.AndroidBridge) {
    return;
  }

  window.__is_android_app__ = true;
  window.__pywebview_no_csrf__ = true; // no cross-origin risk without HTTP either

  // -----------------------------------------------------------------
  // Pending-request table keyed by requestId
  // -----------------------------------------------------------------

  var _pending = Object.create(null);
  var _nextId = 1;

  function _newRequestId() {
    _nextId += 1;
    return 'req' + Date.now().toString(36) + '_' + _nextId.toString(36);
  }

  window.__androidBridgeResolve = function (requestId, resultJsonText) {
    var entry = _pending[requestId];
    if (!entry) return; // late/duplicate callback — ignore
    delete _pending[requestId];
    var data;
    try {
      data = JSON.parse(resultJsonText);
    } catch (e) {
      entry.reject(new Error('Malformed bridge response: ' + String(e)));
      return;
    }
    entry.resolve(data);
  };

  function callBridge(method, url, bodyJson, bodyText) {
    return new Promise(function (resolve, reject) {
      var requestId = _newRequestId();
      _pending[requestId] = { resolve: resolve, reject: reject };
      try {
        var bodyJsonText = bodyJson !== null && bodyJson !== undefined ? JSON.stringify(bodyJson) : null;
        window.AndroidBridge.request(method, url, bodyJsonText, bodyText || null, requestId);
      } catch (e) {
        delete _pending[requestId];
        reject(e);
      }
    });
  }

  // -----------------------------------------------------------------
  // Helpers (identical shape to pywebview_bridge.js so both shims produce
  // Response-compatible objects for the unmodified api() helper in dashboard.js)
  // -----------------------------------------------------------------

  function isApiUrl(url) {
    if (typeof url !== 'string') return false;
    return (
      url.indexOf('/api/') === 0 ||
      url.indexOf('/files/') === 0 ||
      url.indexOf('/frontend/') === 0
    );
  }

  function makeJsonResponse(data, ok) {
    if (ok === undefined) ok = data && data.success !== false;
    var text = JSON.stringify(data);
    return {
      ok: ok,
      status: ok ? 200 : 400,
      statusText: ok ? 'OK' : 'Error',
      text: function () { return Promise.resolve(text); },
      json: function () { return Promise.resolve(data); },
      blob: function () {
        return Promise.resolve(new Blob([text], { type: 'application/json' }));
      },
    };
  }

  function makeTextResponse(text, contentType) {
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      text: function () { return Promise.resolve(text); },
      json: function () {
        try { return Promise.resolve(JSON.parse(text)); }
        catch (_) { return Promise.resolve({ success: true, text: text }); }
      },
      blob: function () {
        return Promise.resolve(new Blob([text], { type: contentType || 'text/plain' }));
      },
    };
  }

  // -----------------------------------------------------------------
  // fetch() override
  // -----------------------------------------------------------------

  var _originalFetch = window.fetch.bind(window);

  window.fetch = function (resource, options) {
    var url = typeof resource === 'string' ? resource : String(resource);
    if (!isApiUrl(url.split('?')[0])) {
      return _originalFetch(resource, options);
    }

    options = options || {};
    var method = String(options.method || 'GET').toUpperCase();

    var bodyJson = null;
    var bodyText = null;
    var body = options.body;
    if (body !== undefined && body !== null) {
      if (typeof body === 'string') {
        try { bodyJson = JSON.parse(body); }
        catch (_) { bodyText = body; }
      } else if (typeof body === 'object' && !(body instanceof FormData)) {
        bodyJson = body;
      }
    }

    return callBridge(method, url, bodyJson, bodyText).then(function (result) {
      if (!result) return makeJsonResponse({ success: false, error: 'No response' }, false);

      // Binary file: hand off to Kotlin's MediaStore/Downloads writer instead
      // of trying to trigger an in-WebView blob download.
      if (result._binary !== undefined) {
        try {
          window.AndroidBridge.saveFile(result._binary, result._content_type || '', result._filename || 'download');
        } catch (e) {
          console.error('[android-bridge] saveFile error:', e);
        }
        return makeJsonResponse({ success: true });
      }

      if (result._text !== undefined) {
        return makeTextResponse(result._text, result._content_type);
      }

      var ok = result.success !== false;
      return makeJsonResponse(result, ok);
    }).catch(function (err) {
      return makeJsonResponse({ success: false, error: String(err) }, false);
    });
  };

  // -----------------------------------------------------------------
  // EventSource override — replaces SSE with polling (same approach as
  // pywebview_bridge.js; the build-progress UI already polls a snapshot
  // endpoint so no server push is needed on Android either)
  // -----------------------------------------------------------------

  var _OriginalEventSource = window.EventSource;

  window.EventSource = function (url, init) {
    var snapshotUrl = url.replace(/\/api\/build\/events\/([^/?]+)$/, '/api/build/events/$1/snapshot');
    if (snapshotUrl === url || !isApiUrl(url.split('?')[0])) {
      return new _OriginalEventSource(url, init);
    }

    var emitter = Object.create(EventTarget.prototype);
    EventTarget.call(emitter);
    emitter.url = url;
    emitter.readyState = 1; // OPEN
    emitter.onmessage = null;
    emitter.onerror = null;
    emitter.onopen = null;
    emitter.CONNECTING = 0;
    emitter.OPEN = 1;
    emitter.CLOSED = 2;

    var lastSeq = -1;

    var pollInterval = setInterval(function () {
      if (emitter.readyState !== 1) return;
      callBridge('GET', snapshotUrl, null, null).then(function (snapshot) {
        if (emitter.readyState !== 1) return;
        var events = (snapshot && snapshot.events) || [];
        for (var i = 0; i < events.length; i++) {
          var ev = events[i];
          var seq = (ev.sequence !== undefined) ? ev.sequence : i;
          if (seq <= lastSeq) continue;
          lastSeq = seq;
          var msgEvent = new MessageEvent('message', { data: JSON.stringify(ev) });
          emitter.dispatchEvent(msgEvent);
          if (emitter.onmessage) emitter.onmessage(msgEvent);
        }
        var status = snapshot && snapshot.status;
        if (status === 'done' || status === 'failed') {
          emitter.close();
        }
      }).catch(function (err) {
        var errEvent = new Event('error');
        errEvent.message = String(err);
        emitter.dispatchEvent(errEvent);
        if (emitter.onerror) emitter.onerror(errEvent);
      });
    }, 1000);

    emitter.close = function () {
      emitter.readyState = 2; // CLOSED
      clearInterval(pollInterval);
    };

    return emitter;
  };
  window.EventSource.CONNECTING = 0;
  window.EventSource.OPEN = 1;
  window.EventSource.CLOSED = 2;

  // -----------------------------------------------------------------
  // Navigation intercept — location.href = '/system-configuration' etc.
  //
  // dashboard.js/admin.js only special-case window.pywebview for internal
  // nav (see api.navigate() in pywebview_bridge.js); on Android that check is
  // always false, so they fall through to a plain location.href assignment.
  // Both target pages are real files under the same asset-loader virtual
  // host, so this is a genuine (reloading) navigation, not an SPA swap.
  // -----------------------------------------------------------------

  var ANDROID_NAV_MAP = {
    '': 'frontend/index.html',
    '/': 'frontend/index.html',
    '/frontend': 'frontend/index.html',
    '/admin': 'frontend/admin.html',
    '/system-configuration': 'frontend/admin.html',
  };

  function androidNavTarget(url) {
    if (!url || typeof url !== 'string') return null;
    var path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0].split('#')[0].replace(/\/$/, '');
    if (path === '' && url.indexOf('://') === -1 && url.charAt(0) !== '/') return null;
    return Object.prototype.hasOwnProperty.call(ANDROID_NAV_MAP, path) ? ANDROID_NAV_MAP[path] : null;
  }

  function handleInternalNav(url) {
    var target = androidNavTarget(url);
    if (!target) return false;
    window.location.href = 'https://appassets.androidplatform.net/' + target;
    return true;
  }

  try {
    var _locProto = window.Location.prototype;
    var _origHrefDescriptor = Object.getOwnPropertyDescriptor(_locProto, 'href');
    if (_origHrefDescriptor && _origHrefDescriptor.set) {
      Object.defineProperty(_locProto, 'href', {
        get: _origHrefDescriptor.get,
        set: function (url) {
          if (!handleInternalNav(url)) {
            _origHrefDescriptor.set.call(this, url);
          }
        },
        configurable: true,
      });
    }
  } catch (_) {
    // Some browsers don't allow overriding Location.prototype — fall through
  }

  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (href && /^\/[a-z/]/.test(href) && handleInternalNav(href)) {
      e.preventDefault();
    }
  }, true);

  console.log('[android-bridge] Android WebView fetch/EventSource bridge active');
})();
