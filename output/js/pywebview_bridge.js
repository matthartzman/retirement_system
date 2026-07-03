/**
 * PyWebView Bridge — Retirement System v10
 *
 * Intercepts window.fetch() and window.EventSource so the unmodified
 * minified dashboard/admin scripts can run without an HTTP socket.
 *
 * How it works:
 *   1. Every fetch('/api/...') call is redirected to
 *      window.pywebview.api.request(method, url, bodyJson, bodyText).
 *   2. The Python side dispatches it through Flask's in-process test
 *      client and returns a plain object.
 *   3. This shim wraps that object in a Response-compatible interface so
 *      the existing api() helper (which calls .text() then JSON.parse)
 *      works without modification.
 *   4. Binary responses (_binary key) trigger a Blob download instead of
 *      returning JSON — matching what the browser would do with send_file.
 *   5. EventSource (SSE) is replaced by polling the snapshot endpoint so
 *      the build-progress UI still works.
 *   6. Internal navigation (location.href = '/') is intercepted and
 *      delegated to api.navigate() so the admin link still works.
 *
 * This file is loaded as the FIRST script in index.html and admin.html.
 * It is a no-op when window.pywebview is absent (i.e., normal browser use).
 */
(function () {
  'use strict';

  if (window.location && window.location.protocol !== 'file:' && !(window.pywebview && window.pywebview.api)) {
    return;
  }

  // -----------------------------------------------------------------
  // Readiness queue — calls made before the bridge is injected are held
  // here and replayed once window.pywebview.api is available.
  // -----------------------------------------------------------------
  var _ready = false;
  var _queue = [];

  function _onReady() {
    _ready = true;
    for (var i = 0; i < _queue.length; i++) {
      _queue[i]();
    }
    _queue = [];
  }

  window.addEventListener('pywebviewready', _onReady);
  // Fallback: if pywebviewready already fired or fires late
  if (window.pywebview && window.pywebview.api) {
    _ready = true;
  }

  // -----------------------------------------------------------------
  // Helpers
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

  function triggerDownload(b64, contentType, filename) {
    try {
      var bytes = Uint8Array.from(atob(b64), function (c) { return c.charCodeAt(0); });
      var blob = new Blob([bytes], { type: contentType || 'application/octet-stream' });
      var blobUrl = URL.createObjectURL(blob);
      var a = document.createElement('a');
      a.href = blobUrl;
      a.download = filename || 'download';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 10000);
    } catch (e) {
      console.error('[bridge] download error:', e);
    }
  }

  // -----------------------------------------------------------------
  // Core bridge call — waits for readiness if needed
  // -----------------------------------------------------------------

  function callBridge(method, url, bodyJson, bodyText) {
    return new Promise(function (resolve, reject) {
      function doCall() {
        if (!window.pywebview || !window.pywebview.api) {
          reject(new Error('PyWebView bridge not available'));
          return;
        }
        window.pywebview.api
          .request(method, url, bodyJson || null, bodyText || null)
          .then(resolve)
          .catch(reject);
      }
      if (_ready) {
        doCall();
      } else {
        _queue.push(doCall);
      }
    });
  }

  // -----------------------------------------------------------------
  // fetch() override
  // -----------------------------------------------------------------

  var _originalFetch = window.fetch.bind(window);

  window.fetch = function (resource, options) {
    var url = typeof resource === 'string' ? resource : String(resource);
    // Strip query string for prefix check; keep full URL for the bridge
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
      } else if (body instanceof FormData) {
        // FormData: not common in this app but handle gracefully
        bodyText = null;
      }
    }

    return callBridge(method, url, bodyJson, bodyText).then(function (result) {
      if (!result) return makeJsonResponse({ success: false, error: 'No response' }, false);

      // Binary file download
      if (result._binary !== undefined) {
        triggerDownload(result._binary, result._content_type, result._filename);
        return makeJsonResponse({ success: true });
      }

      // Text / CSV response
      if (result._text !== undefined) {
        return makeTextResponse(result._text, result._content_type);
      }

      // Normal JSON
      var ok = result.success !== false;
      return makeJsonResponse(result, ok);
    }).catch(function (err) {
      return makeJsonResponse({ success: false, error: String(err) }, false);
    });
  };

  // -----------------------------------------------------------------
  // EventSource override — replaces SSE with polling
  //
  // The build-events endpoint (/api/build/events/<job_id>) emits an SSE
  // stream.  Here we poll /api/build/events/<job_id>/snapshot every
  // second instead and dispatch synthetic MessageEvents so the existing
  // onmessage handler works unchanged.
  // -----------------------------------------------------------------

  var _OriginalEventSource = window.EventSource;

  window.EventSource = function (url, init) {
    var snapshotUrl = url.replace(/\/api\/build\/events\/([^/?]+)$/, '/api/build/events/$1/snapshot');
    if (snapshotUrl === url || !isApiUrl(url.split('?')[0])) {
      return new _OriginalEventSource(url, init);
    }

    // Minimal EventSource-compatible emitter
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
  // Navigation intercept — location.href = '/admin' etc.
  // -----------------------------------------------------------------

  function handleInternalNav(url) {
    if (!url || typeof url !== 'string') return false;
    // Only intercept root-relative paths that look like app routes
    if (!/^\/[a-z]/.test(url) && url !== '/') return false;
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.navigate(url);
      return true;
    }
    return false;
  }

  // Intercept Location.prototype.href setter
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

  // Intercept anchor clicks for any <a href="/..."> links
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (href && /^\/[a-z/]/.test(href)) {
      if (handleInternalNav(href)) {
        e.preventDefault();
      }
    }
  }, true);

  // -----------------------------------------------------------------
  // CSRF: disable in desktop mode (no cross-origin risk without HTTP)
  // -----------------------------------------------------------------
  window.__pywebview_no_csrf__ = true;

  // Feature flag readable by app code
  window.__is_desktop_app__ = true;

  console.log('[bridge] PyWebView fetch/EventSource bridge active');
})();
