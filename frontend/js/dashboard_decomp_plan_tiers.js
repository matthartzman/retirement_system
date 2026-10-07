// ── Plan tiers (Settings → Plan Features, WP5.1) ─────────────────────────────
// The tier picker at the top of Plan Features (design 2026-10-04 §2-§4, P4): four
// starting sets of switches (Simple, Standard, Advanced, Expert), the plan's
// current tier with "(customized)" when its switches differ from the preset, a
// "Reset to <tier> preset" action, and a confirm dialog that previews what a
// pick turns on and off before anything is written. Every switch below the
// picker stays individually overridable; a row whose switch differs from the
// preset carries a small badge (planTierDiffBadgeHtml).
//
// Its own module because dashboard.js sits on a size ratchet
// (tests/test_frontend_size_ratchet.py) and Plan Features already has one
// (dashboard_decomp_plan_features.js); loaded right after that one. The server
// decides everything that is a rule -- the presets (module_catalog.tier_preset),
// the profile (plan_profile) and what a pick changes (POST /api/plan/tier with
// preview) -- so this module only assembles strings and makes the two calls.
//
// SHAPE: as in dashboard_decomp_plan_features.js, everything that decides what
// the picker says is a pure function taking its data as parameters (tested in
// tests/frontend/plan_tiers.test.mjs); only the planTier* wrappers read the
// shared state below.

// The plan profile and tier presets from the last /api/config/rows read
// (loadAll() hands the payload to setPlanTierPayload). Per-load, never sent back.
let planTierPayload = { profile: {}, presets: { tiers: [] }, suggestions: [] };

export function setPlanTierPayload(cfg) {
  planTierPayload = {
    profile: (cfg && cfg.plan_profile) || {},
    presets: (cfg && cfg.tier_presets) || { tiers: [] },
    suggestions: (cfg && cfg.feature_suggestions) || [],
  };
}

// The preset entry for `tier`, or null.
export function tierPresetEntry(presets, tier) {
  return ((presets || {}).tiers || []).find((t) => t.key === tier) || null;
}

// How many nav pages a preset would show: the visible STEPS (not hidden, not
// redirect-only) that `gateFn(stepId, isOn)` -- stepGatedByOptionalModule --
// does not gate when only the preset's features are on.
export function tierPageCount(steps, featureKeys, gateFn, switchable) {
  const on = new Set(featureKeys || []);
  // A module with no switch of its own (bundle member, any-of-flags) follows
  // another feature; count it as on rather than hiding its page in every tier.
  const own = switchable ? new Set(switchable) : null;
  const isOn = (key) => on.has(key) || (own !== null && !own.has(key));
  return (steps || []).filter((s) => s && s.group !== null && !s.hidden && !(gateFn && gateFn(s.id, isOn))).length;
}

// "Simple" / "Advanced (customized)" -- the server's own label, else the tier.
export function planTierLabel(profile, presets) {
  if (profile && profile.label) return profile.label;
  const entry = tierPresetEntry(presets, profile && profile.tier);
  return entry ? entry.label : "";
}

// The four cards. `pageCounts` is {tier: n} (a tier without one shows no count).
export function tierCardsHtml(presets, profile, pageCounts) {
  const current = (profile || {}).tier || (presets || {}).default || "";
  const tiers = (presets || {}).tiers || [];
  if (!tiers.length) return "";
  const counts = pageCounts || {};
  let html = '<div class="pf-tier-cards" role="group" aria-label="Plan tier">';
  tiers.forEach((t) => {
    const selected = t.key === current;
    const n = counts[t.key];
    html +=
      `<button type="button" class="pf-tier-card${selected ? " selected" : ""}" aria-pressed="${selected}" ` +
      `data-requires-app="1" onclick="pickPlanTier('${esc(escJs(t.key))}')">` +
      `<span class="pf-tier-name">${esc(t.label)}</span>` +
      (Number.isFinite(n) ? `<span class="pf-tier-pages">${n} page${n === 1 ? "" : "s"}</span>` : "") +
      `<span class="pf-tier-desc">${esc(t.description || "")}</span>` +
      (selected ? '<span class="pf-tier-current">Current</span>' : "") +
      "</button>";
  });
  return html + "</div>";
}

// The line under the cards: the plan's tier, whether it is customized, and the
// reset action. A plan that never picked a tier reads as Expert with its own
// switches (nothing is written until a tier is picked).
export function tierStatusHtml(profile, presets) {
  const p = profile || {};
  if (!p.tier) return "";
  const entry = tierPresetEntry(presets, p.tier);
  const name = entry ? entry.label : p.tier;
  const n = (p.differing || []).length;
  let html = '<div class="pf-tier-status"><span>Plan tier: <b>' + esc(planTierLabel(p, presets)) + "</b>";
  if (p.customized)
    html += " · " + n + " switch" + (n === 1 ? " differs" : "es differ") + " from the " + esc(name) + " preset";
  html += "</span>";
  if (p.customized)
    html +=
      `<button type="button" class="btn pf-tier-reset" data-requires-app="1" onclick="pickPlanTier('${esc(escJs(p.tier))}')">` +
      "Reset to " + esc(name) + " preset</button>";
  html += "</div>";
  if (!p.tier_stored)
    html +=
      '<div class="section-note">No tier picked yet: this plan keeps the switches it has, read as Expert. ' +
      "Picking a tier sets every switch to that tier's preset; you can still change any switch afterwards.</div>";
  return html;
}

// The small per-row badge: this switch differs from the plan tier's preset.
export function tierDiffBadgeHtml(key, profile, presets) {
  const p = profile || {};
  if (!p.tier || !(p.differing || []).includes(key)) return "";
  const entry = tierPresetEntry(presets, p.tier);
  const inPreset = !!entry && (entry.features || []).includes(key);
  const name = entry ? entry.label : p.tier;
  return (
    '<span class="badge pf-tier-diff" title="' +
    esc(name + " preset: " + (inPreset ? "on" : "off")) +
    '">Differs from ' + esc(name) + " preset</span>"
  );
}

// The confirm dialog's body from the server's preview. `localCount(key)` is the
// page's own entered-row count for a feature (null when it has none), preferred
// over the server's so the dialog agrees with the row it describes.
export function tierPreviewHtml(preview, localCount) {
  const pv = preview || {};
  const label = pv.label || pv.tier || "";
  const on = pv.turn_on || [];
  const off = pv.turn_off || [];
  if (pv.unchanged)
    return "<p>Every switch already matches the " + esc(label) + " preset. Applying it records " + esc(label) + " as the plan's tier.</p>";
  let html = "<p>Picking " + esc(label) + " sets every feature switch to its preset. Your entered data is kept.</p>";
  html += '<div class="pf-tier-preview">';
  if (off.length) {
    html += "<p><b>Turns off (" + off.length + ")</b></p><ul class=\"inapp-modal-list\">";
    off.forEach((f) => {
      const local = localCount ? localCount(f.key) : null;
      const n = local !== null && local !== undefined ? local : f.entered_rows;
      html += "<li>" + esc(f.name || f.key);
      if (n) html += ' <span class="pf-retained">' + offRowsLabel(n) + "</span>";
      const warn = engineIgnoredWarning({ name: f.name, engine_participation: f.engine_participation });
      if (warn) html += '<br><span class="pf-engine-ignored">' + esc(warn) + "</span>";
      html += "</li>";
    });
    html += "</ul>";
  }
  if (on.length) {
    html += "<p><b>Turns on (" + on.length + ")</b></p><ul class=\"inapp-modal-list\">";
    on.forEach((f) => (html += "<li>" + esc(f.name || f.key) + "</li>"));
    html += "</ul>";
  }
  return html + "</div>";
}

// ── Field tiers (WP5.2) ───────────────────────────────────────────────────────
// Each row carries `min_tier` (reference.db). A page shows the fields at or below
// the plan's tier; "Show advanced" reveals the rest for that page. A required
// field that is still empty is never hidden, and a row with no tier always shows.
const FIELD_TIER_RANK = { simple: 0, standard: 1, advanced: 2, expert: 3 };

// -> {shown, hidden}: `rows` split by the field filter. `isMissing(row)` marks the
// required-empty rows that must stay visible. An unknown plan tier hides nothing.
export function splitFieldsByTier(rows, planTier, isMissingFn) {
  const limit = FIELD_TIER_RANK[planTier];
  const shown = [];
  const hidden = [];
  (rows || []).forEach((r) => {
    const rank = FIELD_TIER_RANK[(r && r.min_tier) || ""];
    if (limit === undefined || rank === undefined || rank <= limit || (isMissingFn && isMissingFn(r))) shown.push(r);
    else hidden.push(r);
  });
  return { shown, hidden };
}

export function fieldTierControlHtml(step, hiddenCount, expanded) {
  if (!hiddenCount) return "";
  const n = hiddenCount;
  const label = expanded
    ? "Hide advanced fields"
    : "Show advanced (" + n + " more field" + (n === 1 ? "" : "s") + ")";
  return (
    '<div class="section-note pf-show-advanced"><button class="btn" type="button" aria-pressed="' +
    (expanded ? "true" : "false") +
    '" onclick="toggleShowAdvanced(\'' +
    esc(escJs(step)) +
    "')\">" +
    esc(label) +
    "</button></div>"
  );
}

// Per-page UI state only (not persisted, not sent to the server).
const showAdvancedSteps = new Set();

export function toggleShowAdvanced(step) {
  if (showAdvancedSteps.has(step)) showAdvancedSteps.delete(step);
  else showAdvancedSteps.add(step);
  renderMain();
}

// What renderFields() calls: {rows, controlHtml}. The filter is off while searching.
export function fieldTierView(step, rows, searching) {
  const tier = (planTierPayload.profile || {}).tier;
  if (searching) return { rows, controlHtml: "" };
  const { shown, hidden } = splitFieldsByTier(rows, tier, isMissing);
  const expanded = showAdvancedSteps.has(step);
  return {
    rows: expanded ? rows : shown,
    controlHtml: fieldTierControlHtml(step, hidden.length, expanded),
  };
}

// ── Interview and self-suggest (WP5.3) ────────────────────────────────────────
// A short question flow (wording served by GET /api/plan/interview) that suggests a
// tier and the extra switches; and "Turn on X?" for off features that hold entered data.

// "Turn on HELOC? You have 3 rows entered for it." with a button per suggestion.
export function featureSuggestionsHtml(suggestions) {
  const list = suggestions || [];
  if (!list.length) return "";
  let html = '<div class="pf-suggest" role="region" aria-label="Suggested features">';
  list.forEach((s) => {
    html +=
      '<div class="pf-suggest-row"><span>' + esc(s.text || "Turn on " + s.name + "?") + "</span>" +
      `<button type="button" class="btn" data-requires-app="1" onclick="setPlanFeatureSwitch('${esc(escJs(s.key))}', true)">Turn on ${esc(s.name)}</button></div>`;
  });
  return html + "</div>";
}

// The interview panel. state: {questions, answers, result}.
export function interviewHtml(state) {
  const st = state || {};
  const qs = st.questions || [];
  if (!qs.length) return "";
  const answers = st.answers || {};
  let html = '<form class="pf-interview" onsubmit="return false"><div class="pf-tier-head">Plan interview</div>';
  qs.forEach((q) => {
    html += '<fieldset class="pf-interview-q"><legend>' + esc(q.text) + "</legend>";
    const opts = q.kind === "choice" ? q.options || [] : [{ value: "true", label: "Yes" }, { value: "false", label: "No" }];
    opts.forEach((o) => {
      const checked = String(answers[q.id]) === String(o.value);
      html +=
        `<label class="pf-interview-opt"><input type="radio" name="iv_${esc(q.id)}" value="${esc(o.value)}"` +
        (checked ? " checked" : "") +
        ` onchange="setInterviewAnswer('${esc(escJs(q.id))}', '${esc(escJs(o.value))}')"> ${esc(o.label)}</label>`;
    });
    html += "</fieldset>";
  });
  const ready = qs[0] && answers[qs[0].id];
  html +=
    '<div class="pf-interview-actions"><button type="button" class="btn" data-requires-app="1"' +
    (ready ? "" : " disabled") + ' onclick="suggestFromInterview()">See my suggestion</button>' +
    '<button type="button" class="btn" onclick="closePlanInterview()">Cancel</button></div>';
  return html + interviewResultHtml(st.result) + "</form>";
}

export function interviewResultHtml(result) {
  if (!result) return "";
  let html = '<div class="pf-interview-result"><p><b>Suggested: ' + esc(result.label || result.tier) + "</b>";
  const extra = result.reasons || [];
  if (extra.length) {
    html += " plus " + extra.length + " extra feature" + (extra.length === 1 ? "" : "s") + ":</p><ul>";
    extra.forEach((r) => (html += "<li>" + esc(r.name) + "</li>"));
    html += "</ul>";
  } else html += ".</p>";
  html +=
    '<button type="button" class="btn" data-requires-app="1" onclick="applyInterview()">Apply this suggestion</button></div>';
  return html;
}

let planInterview = null;

export async function openPlanInterview() {
  try {
    const out = await api("/api/plan/interview");
    planInterview = { questions: out.questions || [], answers: {}, result: null };
    renderMain();
  } catch (e) {
    showMessage("Could not load the interview: " + e.message, "error");
  }
}

export function closePlanInterview() {
  planInterview = null;
  renderMain();
}

export function setInterviewAnswer(id, value) {
  if (!planInterview) return;
  const q = planInterview.questions.find((x) => x.id === id);
  planInterview.answers[id] = q && q.kind === "yes_no" ? value === "true" : value;
  planInterview.result = null;
  renderMain();
}

async function interviewCall(apply) {
  return api("/api/plan/interview", {
    method: "POST",
    body: JSON.stringify({ answers: planInterview.answers, apply }),
  });
}

export async function suggestFromInterview() {
  if (!planInterview) return;
  try {
    planInterview.result = await interviewCall(false);
    renderMain();
  } catch (e) {
    showMessage("Could not suggest a tier: " + e.message, "error");
  }
}

export async function applyInterview() {
  if (!planInterview) return;
  try {
    if (dirty && dirty.size && !(await saveAll(false))) return;
    const out = await interviewCall(true);
    planInterview = null;
    await planTierReload("Plan tier set to " + out.label + ".");
  } catch (e) {
    showMessage("Could not apply the suggestion: " + e.message, "error");
  }
}

// ── Page wiring (reads the shared state) ──────────────────────────────────────

export function planTierPickerHtml() {
  const { profile, presets } = planTierPayload;
  if (!((presets || {}).tiers || []).length) return "";
  const counts = {};
  presets.tiers.forEach((t) => {
    counts[t.key] = tierPageCount(STEPS, t.features, stepGatedByOptionalModule, presets.switchable);
  });
  return (
    '<section class="pf-tier" aria-label="Plan tier"><div class="pf-tier-head">Plan tier</div>' +
    '<div class="pf-tier-intro">A tier is a starting set of features. Pick one, then turn any feature on or off below.</div>' +
    tierCardsHtml(presets, profile, counts) +
    tierStatusHtml(profile, presets) +
    '<div class="pf-tier-status"><button type="button" class="btn" data-requires-app="1" onclick="openPlanInterview()">Not sure? Answer a few questions</button></div>' +
    interviewHtml(planInterview) +
    featureSuggestionsHtml(planTierPayload.suggestions) +
    "</section>"
  );
}

export function planTierDiffBadgeHtml(key) {
  return tierDiffBadgeHtml(key, planTierPayload.profile, planTierPayload.presets);
}

// The page's own count for an off feature (moduleOwnedRows, as the feature
// rows below the picker count it), or null when the page has none.
function planTierLocalCount(key) {
  const owned = typeof moduleOwnedRows === "function" ? moduleOwnedRows(key) : null;
  return owned === null ? null : enteredRowCount(owned);
}

async function planTierReload(message) {
  await loadAll({ source: "Local database", preferLocal: false, silent: true, overlayTitle: "Updating plan features" });
  renderMain();
  if (message) showMessage(message);
}

// Preview what picking `tier` changes, confirm, then apply it in one edit.
export async function pickPlanTier(tier) {
  try {
    // Unsaved edits first, so the preview and the apply see the plan the user sees.
    if (dirty && dirty.size && !(await saveAll(false))) return;
    const preview = await api("/api/plan/tier", { method: "POST", body: JSON.stringify({ tier, preview: true }) });
    const current = planTierPayload.profile || {};
    if (preview.unchanged && current.tier === tier && current.tier_stored) {
      showMessage("Every switch already matches the " + preview.label + " preset.");
      return;
    }
    const ok = await showInAppConfirm(tierPreviewHtml(preview, planTierLocalCount), {
      bodyIsHtml: true,
      title: "Use the " + preview.label + " preset?",
      confirmLabel: "Apply " + preview.label,
      variant: (preview.engine_ignored || []).length ? "warn" : "",
    });
    if (!ok) return;
    await api("/api/plan/tier", { method: "POST", body: JSON.stringify({ tier }) });
    await planTierReload("Plan tier set to " + preview.label + ".");
  } catch (e) {
    showMessage("Could not change the plan tier: " + e.message, "error");
  }
}

// One switch with no row yet (a page switch, a plan flag the plan never stored).
export async function setPlanFeatureSwitch(key, on) {
  try {
    if (dirty && dirty.size && !(await saveAll(false))) return;
    await api("/api/plan/feature", { method: "POST", body: JSON.stringify({ key, on: !!on }) });
    await planTierReload("");
  } catch (e) {
    showMessage("Could not change the feature: " + e.message, "error");
  }
}

Object.assign(window, {
  pickPlanTier,
  planTierDiffBadgeHtml,
  planTierLabel,
  planTierPickerHtml,
  setPlanFeatureSwitch,
  setPlanTierPayload,
  applyInterview,
  closePlanInterview,
  featureSuggestionsHtml,
  interviewHtml,
  interviewResultHtml,
  openPlanInterview,
  setInterviewAnswer,
  suggestFromInterview,
  fieldTierControlHtml,
  fieldTierView,
  splitFieldsByTier,
  toggleShowAdvanced,
  tierCardsHtml,
  tierDiffBadgeHtml,
  tierPageCount,
  tierPresetEntry,
  tierPreviewHtml,
  tierStatusHtml,
});
