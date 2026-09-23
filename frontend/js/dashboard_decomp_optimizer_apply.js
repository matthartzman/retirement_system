/* dashboard_decomp_optimizer_apply.js: #329 P6 / §4.2-§4.6 (W10c) -- applying an optimizer's
   result to the plan.

   The whole design is "reuse the promote path, add nothing". An optimizer
   result becomes appliable by emitting an *optimizer patch*: a list of items
   in planning_workbench_ui.js's existing overrideFromRow() shape. Apply =
   build a Planning Case with source "optimizer" and hand it to the existing
   promotePlanningCase(), which already owns the confirmation dialog, the
   before -> after list, and editValue() staging. What falls out for free:

     - un-apply is the reverse patch (after <-> before), no new storage;
     - the comparison matrix, Decision panel and Saved Cases list pick the
       case up unchanged, because it is the same record type;
     - the case store's `source` enum gains exactly ONE value, "optimizer",
       not one per optimizer (§4.2: an enum that grows with every optimizer
       is the hand-maintained-list failure #329 exists to remove). Which
       optimizer produced a case lives in its provenance note.

   §4.6 is the rule most likely to rot, so it is stated here too: there is no
   stored `applied` flag anywhere in this file, and adding one would be a bug.
   The plan rows ARE the source of truth; "applied" is COMPUTED every time by
   comparing the patch's `afterRaw` against the live row values. Three honest
   states: not applied (no row matches), applied (all match), diverged (some
   match, some do not -- i.e. applied, then hand-edited).

   §4.6 caveat, which the UI copy in this file must keep saying out loud: the
   Planning Case store is localStorage. Provenance and the convenience of
   un-apply are browser-local and lost on a cache clear. The applied VALUES
   are plan data and are safe. Never word a string here so that it implies
   the provenance is a durable audit trail.

   Loaded as type="module" after dashboard.js, so everything it needs from the
   monolith is read off `window` at call time rather than imported. Named
   dashboard_decomp_* per the frontend size ratchet's own extraction pattern,
   which also puts it in tests/frontend/load_dashboard.mjs's shared sandbox --
   safe here, unlike dashboard_source_truth_banners.js (W10b's recorded
   finding), because nothing in this file monkey-patches renderMain or touches
   the DOM at load. */
(function () {
  "use strict";

  const SOURCE = "optimizer";
  const NOT_APPLIED = "not_applied";
  const APPLIED = "applied";
  const DIVERGED = "diverged";

  function esc(v) {
    try {
      return window.esc ? window.esc(v) : String(v == null ? "" : v);
    } catch (_e) {
      return "";
    }
  }
  function escJs(v) {
    try {
      return window.escJs ? window.escJs(v) : String(v == null ? "" : v);
    } catch (_e) {
      return "";
    }
  }
  function nowIso() {
    try {
      return new Date().toISOString();
    } catch (_e) {
      return "";
    }
  }

  /* Value comparison for the applied-state computation.

     Deliberately tolerant in exactly two ways, and no more. Whitespace,
     because a stored value and a rendered one differ by trimming all over
     this codebase; and numeric equality, because "70" and "70.0" are the
     same claim age and an optimizer that emits one against a row holding the
     other must not read as "diverged". Everything else compares as an exact
     string: a lenient comparator here would silently report "applied" for a
     plan that is not, which is the one failure §4.6 exists to prevent. */
  function sameValue(a, b) {
    const sa = String(a == null ? "" : a).trim();
    const sb = String(b == null ? "" : b).trim();
    if (sa === sb) return true;
    if (sa === "" || sb === "") return false;
    const na = Number(sa);
    const nb = Number(sb);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na === nb;
    return false;
  }

  /* The live raw value of one plan row: the staged edit if the row is dirty,
     else the saved value. Mirrors editValue()'s own view of a row exactly --
     it deletes the dirty entry when a staged value returns to the saved one,
     so "dirty wins, else saved" is the whole rule. */
  function liveRawValueForRowIndex(idx) {
    try {
      const dirty = window.dirty;
      if (dirty && typeof dirty.has === "function" && dirty.has(idx))
        return dirty.get(idx);
      const rows = window.rows || [];
      const row = rows.find((r) => r.row_index === idx);
      return row ? row.value : undefined;
    } catch (_e) {
      return undefined;
    }
  }

  /* The live value of a row, normalized the way editValue() would store it.

     The default comparison above reads the raw stored text, which is right
     for a plain text row. It is NOT right for a currency or percent row: the
     plan file holds "$400,000" and "35%", while storageValueForInput() -- the
     function editValue() puts every write through -- normalizes those to
     "400000" and "35". A patch whose afterRaw is the normalized form (which
     it must be, so the write is exact) would then compare unequal against a
     row that already holds exactly that value, and an applied plan would read
     "not applied".

     So a patch that touches formatted rows declares this as its liveValueOf:
     both sides then go through the same normalizer, and the comparison stays
     strict rather than being loosened for everyone. */
  function liveStorageValueForRowIndex(idx) {
    try {
      const rows = window.rows || [];
      const row = rows.find((r) => r.row_index === idx);
      if (!row) return undefined;
      const raw = liveRawValueForRowIndex(idx);
      return window.storageValueForInput
        ? window.storageValueForInput(row, raw)
        : raw;
    } catch (_e) {
      return undefined;
    }
  }

  /* Items a patch can actually write. Items without a row_index are advisory
     (§4.2) -- they route the user to a source page and never take part in
     the applied-state computation, because there is no row to compare. */
  function promotableItems(patch) {
    return (patch || []).filter((x) => x && x.row_index != null);
  }
  function advisoryItems(patch) {
    return (patch || []).filter((x) => x && x.row_index == null);
  }

  /* §4.6, the heart of this file. NEVER replace this with a stored flag.

     `liveValueOf` and an item's optional `compareAfter` exist together, for
     the case where the stored text and the thing the optimizer chose are not
     the same quantity. Social Security is the worked example: the row holds a
     claim DATE, the sweep chose a claim AGE, and a blank date is not "unset"
     -- the engine reads it as age 70. Comparing the raw text there would
     report "not applied" for a plan that already does exactly what the
     optimizer recommends. An optimizer that needs that declares both halves;
     everything else compares the stored value, which is the honest default. */
  function optimizerAppliedState(patch, liveValueOf) {
    const items = promotableItems(patch);
    if (!items.length) return NOT_APPLIED;
    const read = typeof liveValueOf === "function" ? liveValueOf : liveRawValueForRowIndex;
    let matched = 0;
    items.forEach(function (x) {
      const want =
        x.compareAfter != null
          ? x.compareAfter
          : x.afterRaw != null
            ? x.afterRaw
            : x.after;
      if (sameValue(read(x.row_index), want)) matched++;
    });
    if (matched === 0) return NOT_APPLIED;
    return matched === items.length ? APPLIED : DIVERGED;
  }

  /* Un-apply (§4.6) is the reverse patch and nothing else: swap after <->
     before on every item and send it through the same promote path. The
     patch items this file emits carry beforeRaw alongside afterRaw -- the
     same way currentManualOverrideItems() already extends overrideFromRow()'s
     shape with afterRaw -- precisely so this swap is total rather than
     losing the storage-form value on the way back. */
  function reverseOptimizerPatch(patch) {
    return (patch || []).map(function (x) {
      const out = Object.assign({}, x);
      out.before = x.after;
      out.after = x.before;
      out.beforeRaw = x.afterRaw != null ? x.afterRaw : x.after;
      out.afterRaw = x.beforeRaw != null ? x.beforeRaw : x.before;
      out.rationale = "Reverses the values this optimizer applied.";
      return out;
    });
  }

  /* The provenance note §4.6 calls an audit *note*, not a state. Worded as a
     record of what happened, never as a guarantee that it is kept. */
  function optimizerProvenanceNote(meta) {
    const m = meta || {};
    const when = String(m.at || nowIso()).slice(0, 10);
    return (
      "Applied from the " +
      String(m.optimizerTitle || m.optimizerId || "optimizer") +
      (when ? ", " + when : "") +
      ". This note is stored in this browser only."
    );
  }

  function optimizerCaseName(meta) {
    const m = meta || {};
    let d = "";
    try {
      d = new Date().toLocaleDateString();
    } catch (_e) {}
    return (
      String(m.optimizerTitle || m.optimizerId || "Optimizer") +
      " result" +
      (d ? " " + d : "")
    );
  }

  /* Builds the Planning Case record the existing store holds. Shape matches
     createCase()'s output field for field (case_id / name / base_snapshot_id
     / source / overrides / run_type / result_summary / created_at), so the
     matrix, the Decision panel and the Saved Cases list need no changes. */
  function optimizerPlanningCase(patch, meta) {
    const m = meta || {};
    const wb = window.RetirementPlanningWorkbench || {};
    let baseSnapshot = "latest_saved_baseline";
    let summary = null;
    try {
      baseSnapshot = window.planningCaseBaseSnapshotId() || baseSnapshot;
    } catch (_e) {}
    try {
      summary = window.planningCaseMetricSummary() || null;
    } catch (_e) {}
    return {
      case_id:
        (typeof wb.caseId === "function" && wb.caseId()) ||
        "case_" + Date.now().toString(36),
      name: String(m.name || optimizerCaseName(m)),
      base_snapshot_id: baseSnapshot,
      source: SOURCE,
      overrides: (patch || []).slice(),
      run_type: "quick_compare",
      result_summary: summary,
      created_at: nowIso(),
      // Provenance, per §4.6: an audit note on the record, never the state.
      optimizer_id: String(m.optimizerId || ""),
      optimizer_title: String(m.optimizerTitle || ""),
      provenance_note: optimizerProvenanceNote(m),
    };
  }

  /* Saves a case into the existing store (newest first, the store's own
     25-case cap applies) and returns it. "Pin" in §4.4's three-state strip:
     the case exists, unadopted, so two optimizer results can be compared in
     the matrix before either is committed. */
  function saveOptimizerCase(patch, meta) {
    const wb = window.RetirementPlanningWorkbench;
    if (!wb || typeof wb.readAll !== "function") return null;
    const rec = optimizerPlanningCase(patch, meta);
    const cases = wb.readAll();
    cases.unshift(rec);
    wb.saveAll(cases);
    return rec;
  }

  /* Apply (§4.4): save the case, then hand it to the EXISTING promote path.
     promotePlanningCase() owns the confirmation, the before -> after list and
     the editValue() staging, and it deliberately stops at staged -- it does
     not save and does not build. That is load-bearing: the whole app's
     staleness model assumes edits are staged, then saved, then built, and an
     optimizer that jumped straight to a build would bypass every
     build_impact/review notice dashboard_source_truth_banners.js raises. */
  async function applyOptimizerPatch(patch, meta) {
    const items = promotableItems(patch);
    if (!items.length) {
      try {
        window.showMessage(
          "This result has nothing to write to the plan directly — open the source page to adopt it.",
          "warn",
        );
      } catch (_e) {}
      return null;
    }
    const rec = saveOptimizerCase(patch, meta);
    if (!rec) return null;
    await window.promotePlanningCase(rec.case_id);
    return rec;
  }

  /* Un-apply: the reverse patch, through the same confirmation. Available
     while the case exists and the rows still match -- worded that way in the
     UI below, never as "forever". */
  async function unapplyOptimizerPatch(patch, meta) {
    const m = Object.assign({}, meta || {});
    m.name = "Undo " + optimizerCaseName(meta);
    return applyOptimizerPatch(reverseOptimizerPatch(patch), m);
  }

  const STATE_TEXT = {
    not_applied: {
      badge: "",
      note: "These values are not in the plan yet.",
    },
    applied: {
      badge: '<span class="badge ok">In the plan</span>',
      note: "Every row this result touches currently matches it.",
    },
    diverged: {
      badge: '<span class="badge warn">Edited since</span>',
      note: "Some rows match this result and some have been changed since. Applying again resets all of them.",
    },
  };

  /* §4.4's action strip, as a pure function of its arguments so it is
     testable without a DOM or a build.

     `actions` is what the CALLER declares, not a fixed list -- the two named
     actions §4.3 decided on ("Let the plan keep optimizing this" primary,
     "Lock in this schedule" secondary) belong to the policy-adoption
     optimizers, while a scalar one like Social Security has a single apply
     and no live/frozen distinction to offer. Rendering only what the caller
     passes is what keeps a button from claiming a capability its optimizer
     does not have. */
  function optimizerApplyStripHtml(opts) {
    const o = opts || {};
    const patch = o.patch || [];
    const items = promotableItems(patch);
    const advisory = advisoryItems(patch);
    const state = o.state || NOT_APPLIED;
    const text = STATE_TEXT[state] || STATE_TEXT.not_applied;
    const handler = String(o.handlerNamespace || "window.OptimizerApply");
    // Two escapers, in this order, because these values land inside a JS
    // string INSIDE a double-quoted HTML attribute: escJs closes the JS
    // string-literal hole, esc closes the attribute hole. escJs alone is not
    // enough -- the HTML parser ends the attribute at a raw `"` before the JS
    // is ever parsed, which is how a registry id could smuggle in markup.
    const attrJs = (v) => esc(escJs(v == null ? "" : v));
    const key = attrJs(o.optimizerId || "");
    if (!items.length && !advisory.length) return "";
    let html =
      '<div class="optimizer-apply-strip" data-optimizer="' +
      esc(o.optimizerId || "") +
      '" data-applied-state="' +
      esc(state) +
      '">';
    html +=
      '<div class="optimizer-apply-state"><b>Apply to plan</b>' +
      text.badge +
      '<span class="small">' +
      esc(text.note) +
      "</span></div>";
    if (items.length) {
      const buttons = (o.actions || [])
        .map(function (a) {
          const cls = a.primary ? "btn primary" : "btn";
          return (
            '<button type="button" class="' +
            cls +
            '" onclick="' +
            handler +
            ".runAction('" +
            key +
            "','" +
            attrJs(a.intent || "apply") +
            "')\"" +
            (a.title ? ' title="' + esc(a.title) + '"' : "") +
            ">" +
            esc(a.label || "Apply to plan") +
            "</button>"
          );
        })
        .join("");
      html += '<div class="table-actions">' + buttons;
      html +=
        '<button type="button" class="btn" onclick="' +
        handler +
        ".runAction('" +
        key +
        "','pin')\" title=\"Saves this result as a planning case so you can compare it before committing.\">Save as planning case</button>";
      if (state !== NOT_APPLIED)
        html +=
          '<button type="button" class="btn" onclick="' +
          handler +
          ".runAction('" +
          key +
          "','unapply')\">Undo this</button>";
      html += "</div>";
    }
    if (advisory.length)
      html +=
        '<p class="small">' +
        esc(
          advisory.length +
            (advisory.length === 1 ? " change" : " changes") +
            " in this result has no field on this page and must be adopted from its own page: " +
            advisory
              .map((x) => x.label || x.field || "a field")
              .join(", ") +
            ".",
        ) +
        "</p>";
    html +=
      '<p class="small">Applying stages the changes — Save Changes, then rebuild, to see the effect. ' +
      // §4.6's caveat, stated rather than implied. The values are plan data;
      // the record of where they came from is not.
      "The applied values become ordinary plan data. The record of which optimizer produced them, and the ability to undo it from here, are kept in this browser only and are lost if you clear its storage.</p>";
    html += "</div>";
    return html;
  }

  /* The registry the strip's inline handlers dispatch through. An optimizer
     registers a descriptor with a patch builder; the strip never closes over
     a patch, so the patch is rebuilt at click time against whatever the rows
     hold right then rather than whatever they held at render time. */
  const registry = new Map();

  function registerOptimizer(descriptor) {
    const d = descriptor || {};
    if (!d.id) return;
    registry.set(String(d.id), d);
  }
  function optimizerDescriptor(id) {
    return registry.get(String(id)) || null;
  }
  function buildPatch(id) {
    const d = optimizerDescriptor(id);
    if (!d || typeof d.buildPatch !== "function") return [];
    try {
      return d.buildPatch() || [];
    } catch (_e) {
      return [];
    }
  }

  /* Renders the strip for a registered optimizer, computing the applied
     state fresh (§4.6) rather than reading a stored one. */
  function renderApplyStrip(id) {
    const d = optimizerDescriptor(id);
    if (!d) return "";
    const patch = buildPatch(id);
    if (!patch.length) return "";
    return optimizerApplyStripHtml({
      optimizerId: d.id,
      patch: patch,
      state: optimizerAppliedState(patch, d.liveValueOf),
      actions: d.actions || [
        { intent: "apply", label: "Apply to plan", primary: true },
      ],
    });
  }

  async function runAction(id, intent) {
    const d = optimizerDescriptor(id);
    if (!d) return;
    const patch = buildPatch(id);
    const meta = {
      optimizerId: d.id,
      optimizerTitle: d.title || d.id,
      at: nowIso(),
    };
    if (intent === "pin") {
      const rec = saveOptimizerCase(patch, meta);
      if (rec)
        try {
          window.showMessage(
            '"' +
              rec.name +
              '" saved as a planning case. It is stored in this browser only.',
            "success",
          );
          window.renderMain();
        } catch (_e) {}
      return;
    }
    if (intent === "unapply") return unapplyOptimizerPatch(patch, meta);
    // Every other intent is an apply; the descriptor decides which patch the
    // intent produces (policy adoption vs schedule freeze, §4.3).
    const forIntent =
      typeof d.patchForIntent === "function" ? d.patchForIntent(intent) : patch;
    return applyOptimizerPatch(forIntent || patch, meta);
  }

  window.OptimizerApply = Object.assign(window.OptimizerApply || {}, {
    SOURCE: SOURCE,
    NOT_APPLIED: NOT_APPLIED,
    APPLIED: APPLIED,
    DIVERGED: DIVERGED,
    sameValue: sameValue,
    liveRawValueForRowIndex: liveRawValueForRowIndex,
    liveStorageValueForRowIndex: liveStorageValueForRowIndex,
    promotableItems: promotableItems,
    advisoryItems: advisoryItems,
    optimizerAppliedState: optimizerAppliedState,
    reverseOptimizerPatch: reverseOptimizerPatch,
    optimizerProvenanceNote: optimizerProvenanceNote,
    optimizerPlanningCase: optimizerPlanningCase,
    saveOptimizerCase: saveOptimizerCase,
    applyOptimizerPatch: applyOptimizerPatch,
    unapplyOptimizerPatch: unapplyOptimizerPatch,
    optimizerApplyStripHtml: optimizerApplyStripHtml,
    registerOptimizer: registerOptimizer,
    optimizerDescriptor: optimizerDescriptor,
    buildPatch: buildPatch,
    renderApplyStrip: renderApplyStrip,
    runAction: runAction,
  });
})();
