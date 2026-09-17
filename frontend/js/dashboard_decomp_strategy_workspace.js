// Ticket 323 / Phase 1: the Strategy workspace -- Optimize, Stress Test and
// Scenarios -- built from one lazy collapsible-section primitive.
//
// Every section body is an existing renderer, reused unchanged. Nothing here
// computes anything: this module is composition and open-state bookkeeping
// only.

const STRATEGY_OPEN_STORAGE_KEY = "strategySectionsOpen";

// Open state lives in memory; localStorage is best-effort persistence across
// reloads, not the source of truth. That split matters: if a write throws
// (private mode, blocked site data, quota) and storage were authoritative, the
// persisted map would stay stale while the DOM had already toggled. The two
// would then disagree, and renderMain()'s restore pass -- which assigns
// d.open from the state it captured before its innerHTML write -- would flip
// the element back. That assignment fires another toggle event, which calls
// strategySectionToggle again, which fails to persist again: an unbounded
// render loop in exactly the environment the try/catch was added to tolerate.
// Reading through memory keeps the two in step whether or not the write lands.
let strategyOpenCache = null;

export function strategySectionOpenMap() {
  if (strategyOpenCache) return strategyOpenCache;
  let parsed = null;
  try {
    const raw = localStorage.getItem(STRATEGY_OPEN_STORAGE_KEY);
    parsed = raw ? JSON.parse(raw) : null;
  } catch (_e) {}
  strategyOpenCache = parsed && typeof parsed === "object" ? parsed : {};
  return strategyOpenCache;
}

// Drops the in-memory mirror so the next read re-hydrates from storage. Exists
// for tests, which swap the localStorage stub between cases and would
// otherwise see the previous case's state through the cache.
export function strategySectionResetOpenCache() {
  strategyOpenCache = null;
}

// Called from the <details> ontoggle handler. Update state FIRST, then
// re-render: renderMain() captures every <details> open-state before its
// innerHTML write and restores it after (keyed by data-dkey -- see _dKey in
// dashboard.js), so the state this reads must already be current by the time
// the re-render runs. Otherwise a section comes back open while still holding
// the collapsed stub body.
export function strategySectionSetOpen(key, open) {
  const map = strategySectionOpenMap();
  if (map[key] === !!open) return false;
  map[key] = !!open;
  try {
    localStorage.setItem(STRATEGY_OPEN_STORAGE_KEY, JSON.stringify(map));
  } catch (_e) {}
  return true;
}

export function strategySectionToggle(key, open) {
  // A toggle that changes nothing must not re-render. Besides being wasted
  // work, this is the second guard against re-entry: renderMain()'s restore
  // pass can fire a toggle event of its own, and without this it would call
  // back in here on every render.
  if (!strategySectionSetOpen(key, open)) return;
  renderMain();
}

// The "this section's optional module is off" note, lifted verbatim from the
// deleted Special Strategies renderer and generalized over the section, which
// is why it is one function and not one per section. HELOC is not a
// client_optional_functions.csv toggle -- it is a plan-data feature flag, so
// its note points at the HELOC setup page rather than Optional Modules, same
// as it always did.
export function strategySectionGatedNote(title, gateStepId) {
  if (gateStepId === "heloc_strategy")
    return `<div class="section-note">${esc(title)} strategy is off. Enable it on <a href="#" onclick="setStep('heloc_strategy');return false">HELOC &rarr; Setup &rarr; Enable HELOC Strategy</a> to use it.</div>`;
  return `<div class="section-note">${esc(title)} is off. Enable ${esc(title)} on <a href="#" onclick="setStep('optional_functions');return false">Optional Modules</a> to use it.</div>`;
}

// One collapsible section. bodyFn is called ONLY when the section is open:
// renderMain() re-renders the whole tree on every field edit, and
// renderAllocationRecommendation() alone emits seven sub-panels, so eager
// bodies would multiply per-keystroke cost on the heaviest screen in the app.
export function strategySection(key, title, bodyFn, gateStepId, defaultOpen) {
  // An explicit stored value is the reader's own choice and always wins.
  // defaultOpen only applies before they have expressed one.
  const stored = strategySectionOpenMap()[key];
  const open = stored === undefined ? !!defaultOpen : stored === true;
  const gated = gateStepId ? stepGatedByOptionalModule(gateStepId) : false;
  const body = gated
    ? strategySectionGatedNote(title, gateStepId)
    : open
      ? bodyFn()
      : "";
  return `<details class="strategy-section" data-dkey="strategy:${esc(key)}"${open ? " open" : ""} ontoggle="strategySectionToggle('${escJs(key)}',this.open)"><summary class="section-header">${esc(title)}</summary><div class="section-body">${body}</div></details>`;
}

// A screen is a list of section descriptors rendered in order. The first
// section the reader can actually USE defaults to open on a first visit, so
// landing on a screen shows content instead of a stack of collapsed bars.
// Skipping gated-off sections matters on Optimize, whose first section (Roth
// Conversion) is module-gated: defaulting that one open would greet a reader
// who has the module off with an enable-note and everything else collapsed.
export function renderStrategyScreen(sections) {
  const firstUsable = sections.find(
    (s) => !(s.gate && stepGatedByOptionalModule(s.gate)),
  );
  const defaultKey = firstUsable ? firstUsable.key : null;
  return sections
    .map((s) =>
      strategySection(s.key, s.title, s.body, s.gate, s.key === defaultKey),
    )
    .join("");
}

export function renderStrategyOptimize() {
  return renderStrategyScreen([
    {
      key: "roth_conversion",
      title: "Roth Conversion",
      gate: "roth_conversion",
      body: () => analysisFrame(renderRothConversion(), "strategy"),
    },
    {
      key: "asset_allocation",
      title: "Asset Allocation",
      gate: null,
      body: () =>
        analysisFrame(renderAllocationRecommendation(), "strategy") +
        `<details class="decide-embed-sub" open><summary>Allocation policy settings</summary>${renderAllocationPolicy()}</details>`,
    },
    {
      key: "housing",
      title: "Next Housing Move",
      gate: null,
      // Not analysisFrame-wrapped, unlike its siblings above: this is a
      // self-contained search tool with its own Run button and results
      // table, not a "set inputs, preview impact against the baseline"
      // planning-lever workflow -- analysisFrame's "Preview impact
      // (Planning overview)" footer would not apply to it. Matches
      // "Strategy Levers" (renderStrategyScenarios below), the other
      // non-lever tab in this file.
      body: () => renderHousingOptimizePanelHtml(),
    },
    {
      key: "charitable_giving",
      title: "Charitable Giving",
      gate: "entity_charitable",
      body: () => analysisFrame(renderEntityCharitable(), "strategy"),
    },
    {
      key: "heloc",
      title: "HELOC",
      gate: "heloc_strategy",
      body: () => analysisFrame(renderFields("heloc_strategy"), "strategy"),
    },
  ]);
}

export function renderStrategyStress() {
  return renderStrategyScreen([
    {
      key: "monte_carlo",
      title: "Monte Carlo",
      gate: "monte_carlo_options",
      body: () => analysisFrame(renderMonteCarloOptions(), "stress"),
    },
    {
      key: "survivor",
      title: "Survivor",
      gate: "survivor_stress",
      body: () => analysisFrame(renderSurvivorStress(), "stress"),
    },
    {
      key: "ltc",
      title: "Long-Term Care",
      gate: "ltc_stress",
      body: () => analysisFrame(renderLtcStress(), "stress"),
    },
    {
      key: "divorce",
      title: "Divorce Planning",
      gate: "divorce_options",
      body: () => analysisFrame(renderDivorceOptions(), "stress"),
    },
  ]);
}

export function renderStrategyScenarios() {
  return renderStrategyScreen([
    { key: "levers", title: "Strategy Levers", gate: null, body: () => renderPlanningLevers() },
    {
      key: "change_sets",
      title: "Scenario Change Sets",
      gate: "scenarios",
      body: () => analysisFrame(renderScenarios(), "strategy"),
    },
    {
      key: "workbench",
      title: "Planning Workbench",
      gate: null,
      body: () => renderPlanningWorkbench(),
    },
  ]);
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// ontoggle="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  strategySectionOpenMap,
  strategySectionResetOpenCache,
  strategySectionSetOpen,
  strategySectionToggle,
  strategySectionGatedNote,
  strategySection,
  renderStrategyScreen,
  renderStrategyOptimize,
  renderStrategyStress,
  renderStrategyScenarios,
});
