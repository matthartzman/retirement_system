// "Tax Assumptions" card on Economic & Tax Assumptions (step economic_tax_assumptions).
// New feature module (dashboard.js is on a size ratchet). Hooked by wrapping
// renderMain (the same monkey-patch chain other modules use): after the page
// renders, the card is appended to #mainPane. State is module-local; pure
// helpers take their data as parameters so tests can call them directly.
// Backend: GET/POST /api/tax-assumptions (src/tax_assumptions.py).

const TAX_STEP = "economic_tax_assumptions";
let taxPayload = null; // last GET payload
let taxDrafts = {}; // key -> text typed but not saved
let taxError = "";
let taxLoading = false;

export function taxPct(v) {
  const n = Number(v);
  if (v === null || v === undefined || v === "" || !Number.isFinite(n)) return "n/a";
  return (n * 100).toFixed(2).replace(/\.?0+$/, "") + "%";
}

export function taxMoney(v) {
  const n = Number(v);
  return Number.isFinite(n) ? "$" + Math.round(n).toLocaleString("en-US") : "n/a";
}

// Text shown in the override box when the saved value is an override.
export function taxOverrideText(lever) {
  return lever && lever.source === "override" ? taxPct(lever.value) : "";
}

// Rows whose typed text differs from what is saved -> {key: text} ('' = reset).
export function taxChangedOverrides(levers, drafts) {
  const out = {};
  (levers || []).forEach((lv) => {
    if (!Object.prototype.hasOwnProperty.call(drafts || {}, lv.key)) return;
    const text = String(drafts[lv.key] ?? "").trim();
    if (text !== taxOverrideText(lv)) out[lv.key] = text;
  });
  return out;
}

// Effective value as shown live: the typed text if it parses, else the saved value.
export function taxEffectiveText(lever, draft) {
  if (draft === undefined) return taxPct(lever.value);
  const t = String(draft).trim();
  if (t === "") return taxPct(lever.model_value) + " (Auto)";
  const m = /^[-+]?(\d+(\.\d*)?|\.\d+)\s*(%?)$/.exec(t);
  if (!m) return "invalid";
  const n = parseFloat(t);
  return taxPct(m[3] ? n / 100 : n);
}

function taxLeverRow(lv, draft) {
  const isOv = lv.source === "override";
  const val = draft === undefined ? taxOverrideText(lv) : draft;
  let h = `<tr data-tax-key="${esc(lv.key)}"><td><b>${esc(lv.label)}</b></td>`;
  h += `<td title="${esc(lv.basis || "")}">${esc(taxPct(lv.model_value))}</td>`;
  h += `<td><input type="text" value="${esc(val)}" placeholder="Auto" aria-label="${esc(lv.label)} override (blank = Auto)" oninput="taxAssumptionsEdit('${esc(escJs(lv.key))}',this.value)"></td>`;
  h += `<td>${esc(taxEffectiveText(lv, draft))}</td>`;
  h += `<td><span class="badge ${isOv ? "warn" : "ok"}">${isOv ? "Override" : "Auto"}</span> `;
  h += `<button class="btn" type="button" onclick="taxAssumptionsReset('${esc(escJs(lv.key))}')"${isOv || draft !== undefined ? "" : " disabled"}>Reset to Auto</button></td></tr>`;
  const notes = [];
  if (lv.warning) notes.push(lv.warning);
  if (lv.drifted)
    notes.push(`Model value changed from ${taxPct(lv.baseline_model_value)} to ${taxPct(lv.model_value)} since you overrode.`);
  if (notes.length)
    h += `<tr><td colspan="5" class="small">${notes.map(esc).join("<br>")}</td></tr>`;
  return h;
}

export function taxLawHtml(law, periods) {
  if (!law) return "";
  const mfj = (o) => (o || {}).MFJ;
  const ltcg = mfj(law.ltcg_brackets) || {};
  const br = (mfj(law.ordinary_brackets) || [])
    .map((b) => `${taxPct(b.rate)}: ${taxMoney(b.lower)} to ${b.upper === null ? "and up" : taxMoney(b.upper)}`)
    .join("; ");
  let h = `<details><summary>Tax law in use (read-only)</summary><div class="small" style="padding:10px 14px">`;
  h += `<p>Tax year ${esc(law.year)}, dataset ${esc(law.dataset_version)}. Source: ${esc(law.source)}. Married filing jointly.</p><ul>`;
  h += `<li>Standard deduction: ${esc(taxMoney(mfj(law.standard_deduction)))}</li>`;
  h += `<li>NIIT threshold: ${esc(taxMoney(mfj(law.niit_threshold)))}</li>`;
  h += `<li>Long-term capital gains 0% bracket top: ${esc(taxMoney(ltcg.zero_top))}; 15% bracket top: ${esc(taxMoney(ltcg.fifteen_top))}</li>`;
  h += `<li>SALT cap: ${esc(taxMoney(law.salt_cap))}</li>`;
  h += `<li>Ordinary brackets: ${esc(br)}</li></ul>`;
  if ((periods || []).length > 1) {
    h += `<p><b>Residency periods (model state rate)</b></p><ul>`;
    periods.forEach((p) => {
      h += `<li>${esc(p.state)} ${esc(p.start_year)} to ${esc(p.end_year)}: ${esc(taxPct(p.model_rate))}</li>`;
    });
    h += "</ul>";
  }
  return h + "</div></details>";
}

export function taxAssumptionsCardHtml(p, drafts, err, loading) {
  let h = `<div class="holdings" id="taxAssumptionsCard"><h3 class="group-title">Tax Assumptions</h3>`;
  h += `<div class="section-note">Model values come from the tax-law dataset and your state. Type a value (e.g. 3% or 0.03) to override one; leave it blank to use Auto.</div>`;
  if (!p) {
    return h + `<div class="small">${esc(err || (loading ? "Loading tax assumptions..." : "Tax assumptions are not available."))}</div></div>`;
  }
  h += `<div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Assumption</th><th>Model value</th><th>Your override</th><th>Effective</th><th>Status</th></tr></thead><tbody>`;
  (p.levers || []).forEach((lv) => {
    h += taxLeverRow(lv, (drafts || {})[lv.key]);
  });
  h += `</tbody></table></div>`;
  if (err) h += `<div class="missing-list" role="alert">${esc(err)}</div>`;
  h += `<div class="table-actions"><button class="btn primary" type="button" onclick="taxAssumptionsSave()">Save</button>`;
  h += `<button class="btn" type="button" onclick="taxAssumptionsResetAll()">Reset all</button></div>`;
  return h + taxLawHtml(p.law_table, p.residency_periods) + `</div>`;
}

function taxRefreshCard() {
  const old = document.getElementById("taxAssumptionsCard");
  if (old) old.outerHTML = taxAssumptionsCardHtml(taxPayload, taxDrafts, taxError, taxLoading);
}

async function taxLoad() {
  taxLoading = true;
  try {
    taxPayload = await api("/api/tax-assumptions");
    taxError = "";
  } catch (e) {
    taxError = String((e && e.message) || e);
  }
  taxLoading = false;
  taxRefreshCard();
}

export function taxAssumptionsEdit(key, text) {
  taxDrafts[key] = text;
  const tr = document.querySelector(`#taxAssumptionsCard tr[data-tax-key="${key}"]`);
  const lv = ((taxPayload || {}).levers || []).find((l) => l.key === key);
  if (tr && lv) tr.children[3].textContent = taxEffectiveText(lv, text);
}

async function taxPost(overrides) {
  if (!Object.keys(overrides).length) {
    taxError = "Nothing to save.";
    return taxRefreshCard();
  }
  try {
    await api("/api/tax-assumptions", { method: "POST", body: JSON.stringify({ overrides }) });
    taxDrafts = {};
    taxError = "";
    await taxLoad();
    // Overrides are written server-side; re-sync the in-memory plan unless that would drop unsaved edits.
    if (typeof window.unsavedChangeCount === "function" && !window.unsavedChangeCount() && typeof window.loadAll === "function")
      await window.loadAll({ overlayTitle: "Refreshing plan" });
  } catch (e) {
    taxError = String((e && e.message) || e);
    taxRefreshCard();
  }
}

export function taxAssumptionsSave() {
  return taxPost(taxChangedOverrides((taxPayload || {}).levers, taxDrafts));
}

export function taxAssumptionsReset(key) {
  return taxPost({ [key]: "" });
}

export function taxAssumptionsResetAll() {
  const o = {};
  ((taxPayload || {}).levers || []).forEach((lv) => {
    o[lv.key] = "";
  });
  return taxPost(o);
}

function taxInsertCard() {
  if (window.activeStep !== TAX_STEP) return;
  const pane = document.getElementById("mainPane");
  if (!pane || pane.querySelector("#taxAssumptionsCard")) return;
  const html = taxAssumptionsCardHtml(taxPayload, taxDrafts, taxError, taxLoading);
  const nav = pane.querySelector(".nav-actions");
  if (nav) nav.insertAdjacentHTML("beforebegin", html);
  else pane.insertAdjacentHTML("beforeend", html);
  if (!taxPayload && !taxLoading) taxLoad();
}

try {
  const prevRenderMain = window.renderMain;
  if (typeof prevRenderMain === "function")
    window.renderMain = function () {
      prevRenderMain.apply(this, arguments);
      taxInsertCard();
    };
} catch (_e) {}

Object.assign(window, {
  taxAssumptionsEdit,
  taxAssumptionsReset,
  taxAssumptionsResetAll,
  taxAssumptionsSave,
  taxChangedOverrides,
  taxEffectiveText,
  taxAssumptionsCardHtml,
  taxLawHtml,
  taxMoney,
  taxOverrideText,
  taxPct,
});
