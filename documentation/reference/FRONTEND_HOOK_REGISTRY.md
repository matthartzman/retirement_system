# Frontend hook registry (WI-035 / ARC-007)

`frontend/js/render_hooks.js` defines `window.RPHooks`. It replaces the
`renderMain` / `showStepHelp` monkey-patch decorator chain.

- `dashboard.js`'s base `renderMain()` and `showStepHelp(id)` call
  `RPHooks.run(point, ...args)` after their own work.
- Modules add behaviour with `RPHooks.after(point, fn, order)`. Hooks run in
  ascending numeric `order`, so the sequence is explicit rather than an
  accident of `<script>` order.
- Current registrations: `renderMain` 10 tax assumptions, 20 Roth guardrails,
  30 source-truth banners, 40 batch assumption edit; `showStepHelp` 30 glossary.
- A throwing hook is logged and does not stop later hooks (the old chain let an
  inner exception skip every outer wrapper).
- `tests/frontend/wi015_script_order_wrapper_guard.test.mjs` fails if a module
  assigns/wraps `renderMain` outside `dashboard.js`, if hook orders collide, or
  if the registry is not loaded before registrants.
- `renderMain` / `showStepHelp` remain `let` with a get+set `window` accessor
  only as a node-test stubbing seam (`tools/js_codemod/census.mjs`
  `SETTABLE_TEST_SEAMS`); no production code assigns them.

## Bundling decision: not now

The registry removed the real coupling (hook order). What remains is 54
module scripts, hand-bumped `?v=` queries and window-global coupling.
A bundler (e.g. esbuild) would add a Node build step to the PyInstaller
release, and the node tests and several Python harnesses evaluate
`dashboard.js` and the `dashboard_decomp_*` files as concatenated classic
scripts. Load time and request count were not measured, so there is no
evidence the 54 local requests matter for a local-only app. Revisit if
measured startup latency, CSP adoption (needs inline `onclick` removal) or
cache-busting errors become a problem. Owner decision.
