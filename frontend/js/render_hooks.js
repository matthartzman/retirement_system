// WI-035 / ARC-007: hook registry replacing the renderMain/showStepHelp
// decorator chain. dashboard.js calls RPHooks.run() after its base work;
// modules add behaviour with RPHooks.after(point, fn, order). Hooks run by
// ascending numeric `order`, so sequence is explicit, not <script> order.
// Must load before any registrant (guarded by tests/frontend/wi015_*).
(function () {
  "use strict";
  const hooks = { renderMain: [], showStepHelp: [] };
  let seq = 0;
  function after(point, fn, order) {
    if (!hooks[point]) throw new Error("RPHooks: unknown point " + point);
    if (typeof fn !== "function" || !isFinite(order))
      throw new Error("RPHooks: need a function and a numeric order");
    hooks[point].push({ fn: fn, order: order, seq: seq++ });
    hooks[point].sort((a, b) => a.order - b.order || a.seq - b.seq);
  }
  function run(point, ...args) {
    hooks[point].slice().forEach(function (h) {
      try {
        h.fn(...args);
      } catch (e) {
        console.error("RPHooks " + point + " hook failed", e);
      }
    });
  }
  window.RPHooks = { after: after, run: run };
})();
