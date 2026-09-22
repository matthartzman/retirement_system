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

// The "this section's optional module is off" note, generalized over the
// section, which is why it is one function and not one per section. §5.3 (W6):
// a plan flag's switch lives WHERE ITS DATA IS, so its note names a click-path
// into the owning page, built from the catalog's gate_ref/gate_enable_label
// (moduleGates.flag_gates) rather than the hand-typed `if` this used to carry.
export function strategySectionGatedNote(title, gateStepId) {
  const g = (moduleGates.flag_gates || {})[gateStepId];
  if (g)
    return `<div class="section-note">${esc(title)} is off. Enable it on <a href="#" onclick="setStep('${escJs(gateStepId)}');return false">${[...(g.ref || []).slice(0, 2), g.enable_label].filter(Boolean).map((x) => esc(x)).join(" &rarr; ")}</a> to use it.</div>`;
  return `<div class="section-note">${esc(title)} is off. Enable ${esc(title)} on <a href="#" onclick="setStep('optional_functions');return false">Plan Features</a> to use it.</div>`;
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

// #329 §3.3 (W9): hsaWithdrawalPolicyBlock/taxLossHarvestingBlock/
// gainHarvestBlock/withdrawalMiscBlock moved here from dashboard.js (the
// frontend size ratchet -- see tests/test_frontend_size_ratchet.py -- only
// allows growth there by taking an equal number of lines out). Each is one
// row-filtering concept lifted unchanged from what
// dashboard.js's renderWithdrawalStrategy() (the Spending workspace's
// "Withdrawal Order" tab) already rendered inline, so Optimize's new HSA
// Drawdown / Withdrawal Sequencing / Harvesting sections below reuse the
// exact same filters and markup rather than duplicating them.
// #329 §4.7 (W10b): standalone accessor for the HSA drawdown mode, mirroring
// rothPolicyValue()/irmaaModeValue()'s pattern in dashboard_decomp_
// allocation_optimizer.js. dashboard_source_truth_banners.js's live-
// optimizer disclosure reads this to decide whether the mode row is live
// optimizer output, independent of hsaWithdrawalPolicyBlock()'s own
// pre-filtered `hsa` lookup below.
export function hsaWithdrawalModeValue() {
  const r = rowByNormLabel("hsa_withdrawal_mode");
  return String(r ? valOf(r) : "spend_as_needed")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
}

export function hsaWithdrawalPolicyBlock(other) {
  const hsa = other.filter(
    (r) => r.section === "HSA Policy" && r.subsection === "Withdrawals",
  );
  if (!hsa.length) return "";
  const modeRow = hsa.find((r) => norm(r.label) === "hsa_withdrawal_mode");
  const mode = String(modeRow ? valOf(modeRow) : "spend_as_needed")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_");
  let visible = modeRow ? [modeRow] : [];
  if (mode === "annual_pct" || mode === "annual_percent")
    visible = visible.concat(
      hsa.filter((r) =>
        [
          "hsa_withdrawal_pct",
          "hsa_withdrawal_start_year",
          "hsa_withdrawal_end_year",
        ].includes(norm(r.label)),
      ),
    );
  else if (mode === "smooth_window" || mode === "window")
    visible = visible.concat(
      hsa.filter((r) =>
        [
          "hsa_withdrawal_start_year",
          "hsa_withdrawal_end_year",
          "withdrawal_window",
        ].includes(norm(r.label)),
      ),
    );
  else if (mode === "optimize")
    visible = visible.concat(hsaOptimizeVisibleRows(hsa));
  else
    visible = visible.concat(
      hsa.filter(
        (r) =>
          ![
            "hsa_withdrawal_pct",
            "hsa_withdrawal_start_year",
            "hsa_withdrawal_end_year",
            "withdrawal_window",
            "hsa_consume_by",
            "hsa_min_ending_balance",
          ].includes(norm(r.label)) && r !== modeRow,
      ),
    );
  return `<details><summary>HSA withdrawal policy</summary><div class="field-list"><div class="section-note"><b>Start here:</b> choose HSA withdrawal mode. The schedule fields below change based on that mode. Default is spend as needed, which hides annual-percentage and window controls.</div>${sortRowsByDependency(visible).map(fieldHtml).join("")}</div></details>`;
}
export function taxLossHarvestingBlock(other) {
  const tlh = other.filter(
    (r) =>
      r.section === "Withdrawal Policy" &&
      r.subsection === "Tax-Loss Harvesting",
  );
  if (!tlh.length) return "";
  return `<details><summary>Tax Loss Harvesting</summary><div class="field-list"><div class="section-note">Controls whether and how the projection harvests capital losses from taxable-account lots each year.</div>${sortRowsByDependency(tlh).map(fieldHtml).join("")}</div></details>`;
}
// #277: Gain Harvest gets its own collapsible section, on par with TLH.
export function gainHarvestBlock(other) {
  const gainHarvest = other.filter(
    (r) => r.section === "Withdrawal Policy" && r.subsection === "Gain Harvesting",
  );
  if (!gainHarvest.length) return "";
  return `<details><summary>Gain Harvest</summary><div class="field-list"><div class="section-note">Controls whether and how the projection harvests capital gains from taxable-account lots each year (e.g. to fill up a low tax bracket).</div>${sortRowsByDependency(gainHarvest).map(fieldHtml).join("")}</div></details>`;
}
export function withdrawalMiscBlock(other) {
  const misc = other.filter(
    (r) =>
      !(r.section === "HSA Policy" && r.subsection === "Withdrawals") &&
      !(
        r.section === "Withdrawal Policy" &&
        r.subsection === "Tax-Loss Harvesting"
      ) &&
      !(
        r.section === "Withdrawal Policy" &&
        r.subsection === "Gain Harvesting"
      ),
  );
  if (!misc.length) return "";
  return `<details><summary>Other funding and rollover settings</summary><div class="field-list"><div class="section-note">Annual funding tolerance and spousal rollover settings are operational assumptions. They affect workbook QC, survivor account consolidation, RMD timing, and late-life cash-flow output.</div>${sortRowsByDependency(misc).map(fieldHtml).join("")}</div></details>`;
}

// #329 §3.3 (W9): Social Security has no page of its own -- its claiming-age
// rows live on the "SS, Pensions & Annuities" step (income_retirement)
// alongside pensions/annuities. This filters to the Social Security rows
// only, matching rowsForStep("income_retirement")'s own
// `sec === "Social Security"` half exactly, and links out for the rest
// (pensions/annuities) rather than duplicating them here.
function socialSecurityOptimizePanelHtml() {
  const rows = rowsForStep("income_retirement").filter(
    (r) => r.section === "Social Security",
  );
  if (!rows.length)
    return '<div class="field-list"><p class="small">No Social Security rows found.</p></div>';
  return `<div class="field-list"><div class="section-note">Claiming age and benefit assumptions. Pensions and annuities are entered on <button class="btn linklike" type="button" data-step-id="income_retirement">SS, Pensions &amp; Annuities</button>.</div>${sortRowsByDependency(rows).map(fieldHtml).join("")}</div>`;
}

export function renderStrategyOptimize() {
  return renderStrategyScreen([
    {
      key: "roth_conversion",
      title: "Roth Conversion",
      gate: "roth_conversion",
      body: () => analysisFrame(renderRothConversion(), "strategy"),
    },
    // #329 §3.3 (W9): "add" -- was reachable only by setting a mode field on
    // Other Assets and Liabilities, with no visible consequence. Reuses the
    // exact HSA-withdrawal-policy block the Spending workspace's Withdrawal
    // Order tab already renders (dashboard.js's hsaWithdrawalPolicyBlock()),
    // not a new renderer.
    {
      key: "hsa_drawdown",
      title: "HSA Drawdown",
      gate: null,
      body: () => {
        const html = hsaWithdrawalPolicyBlock(withdrawalOtherRows());
        return (
          html ||
          '<div class="field-list"><p class="small">No HSA withdrawal policy rows — configure HSA on Other Assets and Liabilities.</p></div>'
        );
      },
    },
    {
      key: "asset_allocation",
      title: "Asset Allocation",
      gate: null,
      body: () =>
        analysisFrame(renderAllocationRecommendation(), "strategy") +
        `<details class="decide-embed-sub" open><summary>Allocation policy settings</summary>${renderAllocationPolicy()}</details>`,
    },
    // #329 §1.2/§3.3 (W9): "hidden → restore". Reuses the withdrawal-order
    // table and the misc funding/rollover settings the Withdrawal Order tab
    // already renders.
    {
      key: "withdrawal_sequencing",
      title: "Withdrawal Sequencing",
      gate: null,
      body: () => {
        const other = withdrawalOtherRows();
        return renderWithdrawalOrderTable() + withdrawalMiscBlock(other);
      },
    },
    {
      key: "social_security",
      title: "Social Security",
      gate: null,
      body: () => socialSecurityOptimizePanelHtml(),
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
    // #329 §3.3 (W9): "add, as one panel" -- TLH and Gain Harvest together,
    // reusing the Withdrawal Order tab's own two blocks.
    {
      key: "harvesting",
      title: "Harvesting",
      gate: null,
      body: () => {
        const other = withdrawalOtherRows();
        const html = taxLossHarvestingBlock(other) + gainHarvestBlock(other);
        return (
          html ||
          '<div class="field-list"><p class="small">No harvesting rows configured.</p></div>'
        );
      },
    },
    // #329 O11 / #330 §4.3 (W9): HELOC moved to Assets & Protection -- a
    // liability held against an asset, not an optimizer. Its own nav step
    // (heloc_strategy) renders the same renderHelocOptimizePanel() body it
    // always did; it is no longer embedded here.
  ]);
}

export function renderStrategyStress() {
  const sections = [
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
  ];
  // Divorce Planning, unlike its Monte Carlo/Survivor/LTC siblings above,
  // should not appear at all -- not even as a collapsed "enable it here"
  // stub -- when the Divorce/QDRO optional module is off.
  return renderStrategyScreen(
    sections.filter(
      (s) => s.key !== "divorce" || !stepGatedByOptionalModule(s.gate),
    ),
  );
}

export function renderStrategyScenarios() {
  return renderStrategyScreen([
    {
      key: "change_sets",
      title: "Scenario Change Sets",
      gate: "scenarios",
      body: () => analysisFrame(renderScenarios(), "strategy"),
    },
  ]);
}

export function renderStrategyWorkbench() {
  const W = window.RetirementPlanningWorkbench;
  const ctx = planningWorkbenchContext();
  const cases = W.readAll();
  const active =
    cases.find((c) => c.case_id === W.activeId()) ||
    cases.find((c) => !c.archived) ||
    null;
  return (
    '<div class="section-note workbench-model"><b>Planning Workbench model:</b> Baseline -> Change Set -> Run Type -> Impact -> Decision. A Planning Case is browser-local and never changes the saved plan by itself.</div>' +
    renderStrategyScreen([
      {
        key: "levers",
        title: "Strategy Levers",
        gate: null,
        body: () => renderPlanningLevers(),
      },
      {
        key: "change_sets",
        title: "Change Set Builder",
        gate: null,
        body: () =>
          W.sourceButtons() +
          "<h4>Currently staged manual edits</h4>" +
          W.overrideTable(ctx, W.currentManualOverrideItems(ctx), "No unsaved field edits are currently staged."),
      },
      {
        key: "comparison",
        title: "Unified Comparison Matrix",
        gate: null,
        body: () => W.matrixHtml(ctx, cases),
      },
      {
        key: "decision",
        title: "Decision",
        gate: null,
        body: () =>
          W.forwardLookingHtml(ctx) +
          '<div class="feature-grid">' +
          W.stressSelectorHtml(ctx, cases) +
          '<div class="feature-card"><h3>Decision panel</h3><p class="small">Every comparison ends with one deliberate choice: adopt selected changes into the saved plan via source pages, keep as a named scenario only, or archive/no action.</p>' +
          (active
            ? `<p><b>Selected:</b> ${esc(active.name)}</p><div class="pane-actions"><button class="btn primary" type="button" onclick="planningCaseAdopt('${escJs(active.case_id)}')">Adopt via source pages</button><button class="btn" type="button" data-step-id="build_impact">View impact</button><button class="btn" type="button" onclick="planningCaseArchive('${escJs(active.case_id)}')">Archive/no action</button></div>`
            : '<p class="small">Select or create a case to make a decision.</p>') +
          "</div></div>",
      },
      {
        key: "saved_cases",
        title: "Saved Planning Cases",
        gate: null,
        body: () => W.cardsHtml(ctx, cases, active),
      },
    ])
  );
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
  renderStrategyWorkbench,
  hsaWithdrawalPolicyBlock,
  hsaWithdrawalModeValue,
  taxLossHarvestingBlock,
  gainHarvestBlock,
  withdrawalMiscBlock,
});
