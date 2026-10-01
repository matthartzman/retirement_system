// Roth conversion guardrail panel (Strategy > Roth Conversion).
// Shows every limit that capped conversions in the last build, ranked by the
// dollars it allows, with its controls and a what-if (measured by re-running
// the projection with that guardrail off). New feature module -- dashboard.js
// is on a size ratchet. Hooked by wrapping renderMain, like the Tax
// Assumptions card. Pure helpers take their data as parameters so tests can
// call them directly. Data: result.guardrails from roth_guardrail_analysis()
// (src/planning_engines.py), carried in plan_summary.json's roth_strategy_result.
const RG_STEP = "roth_conversion";
const RG_ORDER_KEY = "rothGuardrailOrder";
const RG_RATES = ["10.00%", "12.00%", "22.00%", "24.00%", "32.00%", "35.00%", "37.00%"];
const RG_LTCG_BANDS = ["auto", "0%", "15%"];
const RG_NAMES = {
  irmaa: "Medicare IRMAA tier",
  ltcg: "Capital gains rate band",
  niit: "3.8% investment income tax",
  aca: "ACA subsidy limit",
  pct: "Annual share of traditional IRA",
  fixed: "Fixed dollar amount",
};
const RG_DESC = {
  bracket: "Room left in your target tax bracket.",
  irmaa: "Keeps income under the chosen Medicare premium tier.",
  ltcg: "Stops before conversions push dividends and gains into a higher rate band.",
  niit: "Keeps income under the 3.8% investment income tax threshold.",
  aca: "Keeps income under the limit where ACA premium credits shrink.",
  pct: "Caps one year at a share of your pre-tax balance.",
  fixed: "The fixed annual amount you set.",
};
// Which setting rows each guardrail edits. `on` rows are switches.
const RG_ROWS = {
  bracket: { select: "roth_target_bracket_rate", pct: "roth_headroom_usage_pct" },
  irmaa: { on: "irmaa_guardrail_mode", select: "roth_irmaa_target_tier", pct: "roth_irmaa_headroom_usage_pct" },
  ltcg: { on: "roth_ltcg_guardrail", select: "roth_ltcg_band", pct: "roth_ltcg_headroom_usage_pct" },
  niit: { on: "roth_niit_guardrail", pct: "roth_niit_headroom_usage_pct" },
  pct: { pct: "max_annual_conversion_pct_of_traditional_ira" },
};
const RG_SWITCHABLE = ["irmaa", "ltcg", "niit"];

let rgYear = null;
let rgManual = false;
let rgOrder = [];
try {
  const saved = JSON.parse(localStorage.getItem(RG_ORDER_KEY) || "null");
  if (Array.isArray(saved) && saved.length) {
    rgOrder = saved.map(String);
    rgManual = true;
  }
} catch (_e) {}

function rgEsc(v) {
  return typeof window.esc === "function"
    ? window.esc(v)
    : String(v).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
}

export function rgMoney(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "n/a";
  return (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");
}

export function rgSigned(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "n/a";
  return (n < 0 ? "−$" : "+$") + Math.abs(Math.round(n)).toLocaleString("en-US");
}

export function rgPctNumber(text, fallback) {
  const n = parseFloat(String(text == null ? "" : text).replace(/[%,$]/g, ""));
  return Number.isFinite(n) ? n : fallback;
}

// Guardrails for one plan year, ranked. `order` (ids) wins when `manual`.
export function rgRankRows(guardrails, year, order, manual) {
  const years = (guardrails && guardrails.years) || [];
  const entry = years.find((y) => String(y.year) === String(year)) || years[0];
  if (!entry) return { entry: null, rows: [] };
  const capById = {};
  (entry.caps || []).forEach((c) => {
    if (c.id !== "balance") capById[c.id] = c;
  });
  const switches = (guardrails.settings && guardrails.settings.switches) || {};
  const ids = [];
  years.forEach((y) =>
    (y.caps || []).forEach((c) => {
      if (c.id !== "balance" && !ids.includes(c.id)) ids.push(c.id);
    }),
  );
  RG_SWITCHABLE.forEach((id) => {
    if (!ids.includes(id)) ids.push(id);
  });
  const rows = ids.map((id) => {
    const cap = capById[id];
    return {
      id,
      name: cap && id === "bracket" ? cap.name : RG_NAMES[id] || (cap && cap.name) || id,
      active: !!cap,
      cap: cap ? cap.cap : null,
      off: switches[id] === false,
    };
  });
  const live = rows.filter((r) => r.active).sort((a, b) => a.cap - b.cap);
  live.forEach((r, i) => {
    r.binding = i === 0 ? "now" : i === 1 ? "next" : "";
  });
  let ordered;
  if (manual && order && order.length) {
    const pos = (id) => {
      const i = order.indexOf(id);
      return i < 0 ? order.length + ids.indexOf(id) : i;
    };
    ordered = rows.slice().sort((a, b) => pos(a.id) - pos(b.id));
  } else {
    ordered = live.concat(rows.filter((r) => !r.active));
  }
  return { entry, rows: ordered, maxCap: Math.max(1, ...live.map((r) => r.cap)) };
}

// Four measured what-if numbers for one guardrail, or null.
export function rgWhatIf(guardrails, id) {
  const w = guardrails && guardrails.whatif && guardrails.whatif[id];
  if (!w) return null;
  const base = Number(guardrails.baseline && guardrails.baseline.lcv) || 0;
  const margin = Math.max(1500, Math.abs(base) * 0.0005);
  const net = Number(w.lcv_change) || 0;
  const verdict = net > margin ? "ok" : net < -margin ? "keep" : "close";
  return { ...w, verdict };
}

const RG_VERDICT = {
  ok: ["v-ok", "Turning off helps"],
  keep: ["v-keep", "Keep it on"],
  close: ["v-none", "Close call"],
};

function rgSelect(label, id, current, options, ctx) {
  const idx = ctx.idx(id);
  if (idx == null) return "";
  const opts = options
    .map(([v, t]) => `<option value="${rgEsc(v)}"${String(v).toLowerCase() === String(current).toLowerCase() ? " selected" : ""}>${rgEsc(t)}</option>`)
    .join("");
  return `<label>${rgEsc(label)} <select aria-label="${rgEsc(label)}" onchange="editValue(${idx},this.value,this);renderMain()">${opts}</select></label>`;
}

function rgSlider(label, id, ctx, capText) {
  const idx = ctx.idx(id);
  if (idx == null) return "";
  const v = Math.min(100, Math.max(5, rgPctNumber(ctx.val(id), 95)));
  return `<label>${rgEsc(label)} <input type="range" min="5" max="100" step="5" value="${v}" aria-label="${rgEsc(label)}" oninput="this.nextElementSibling.textContent=this.value+'%'" onchange="editValue(${idx},this.value+'.00%',this);renderMain()"><output>${v}%</output>${capText ? ` <span class="rg-note">${rgEsc(capText)}</span>` : ""}</label>`;
}

function rgSwitch(id, ctx, on, aria) {
  const idx = ctx.idx(id);
  if (idx == null) return "";
  const off = id === "irmaa_guardrail_mode" ? "IGNORE" : "FALSE";
  const onVal = id === "irmaa_guardrail_mode" ? "AVOID_NEXT_TIER" : "TRUE";
  return `<span class="rg-sw"><input type="checkbox" ${on ? "checked" : ""} aria-label="${rgEsc(aria)}" onchange="editValue(${idx},this.checked?'${onVal}':'${off}',this);renderMain()"><span></span></span>`;
}

function rgControls(row, g, ctx) {
  const map = RG_ROWS[row.id];
  if (!map) return "";
  const opts = g.options || {};
  let h = "";
  if (map.on) h += rgSwitch(map.on, ctx, !row.off, "Use " + row.name);
  if (row.id === "bracket")
    h += rgSelect("Target bracket", map.select, ctx.val(map.select) || "", RG_RATES.map((r) => [r, r]), ctx);
  if (row.id === "irmaa") {
    const tiers = opts.irmaa || {};
    h += rgSelect(
      "Tier",
      map.select,
      ctx.val(map.select) || "TIER_2",
      ["TIER_1", "TIER_2", "TIER_3", "TIER_4", "TIER_5"].map((t) => [
        t,
        t.replace("TIER_", "Tier ") + (tiers[t] ? " · " + rgMoney(tiers[t]) : ""),
      ]),
      ctx,
    );
  }
  if (row.id === "ltcg") {
    const l = opts.ltcg || {};
    h += rgSelect(
      "Stay within",
      map.select,
      ctx.val(map.select) || "auto",
      RG_LTCG_BANDS.map((b) => [b, b === "auto" ? "Current band (auto)" : b + " band" + (l[b] ? " · income to " + rgMoney(l[b]) : "")]),
      ctx,
    );
  }
  if (row.id === "niit" && opts.niit) h += `<span class="rg-note">Threshold ${rgMoney(opts.niit)}</span>`;
  if (map.pct)
    h += rgSlider(row.id === "pct" ? "Annual cap" : "Use", map.pct, ctx, row.active ? "= " + rgMoney(row.cap) : "");
  return h;
}

function rgWhatIfHtml(row, g) {
  if (!RG_SWITCHABLE.includes(row.id) || row.off) return "";
  const w = rgWhatIf(g, row.id);
  if (!w) return "";
  const v = RG_VERDICT[w.verdict];
  const cls = (n) => (n >= 0 ? "pos" : "neg");
  return (
    `<div class="rg-whatif"><div class="hd">If you turned this off, over the whole plan <span class="rg-verdict ${v[0]}">${v[1]}</span></div>` +
    `<div>Extra converted<b>${rgSigned(w.extra_converted)}</b></div>` +
    `<div>Lifetime tax (PV)<b class="${cls(-w.lifetime_tax_pv_change)}">${rgSigned(w.lifetime_tax_pv_change)}</b></div>` +
    `<div>After-tax terminal wealth (PV)<b class="${cls(w.terminal_wealth_pv_change)}">${rgSigned(w.terminal_wealth_pv_change)}</b></div>` +
    `<div>Net lifetime value<b class="${cls(w.lcv_change)}">${rgSigned(w.lcv_change)}</b></div></div>`
  );
}

// ctx: { year, order, manual, val(labelKey)->string, idx(labelKey)->row index|null }
export function rothGuardrailPanelHtml(g, ctx) {
  if (!g || !(g.years || []).length) return "";
  const year = ctx.year != null ? ctx.year : g.years[0].year;
  const { entry, rows, maxCap } = rgRankRows(g, year, ctx.order, ctx.manual);
  if (!entry) return "";
  const yearOpts = g.years
    .map((y) => `<option value="${y.year}"${String(y.year) === String(entry.year) ? " selected" : ""}>${y.year}</option>`)
    .join("");
  const live = rows.filter((r) => r.active).sort((a, b) => a.cap - b.cap);
  const win = live[0];
  const second = live[1];
  const summary = win
    ? `In ${entry.year}, conversions were held to <b>${rgMoney(entry.amount)}</b>, limited by <b>${rgEsc(win.name)}</b>${second ? `, with <b>${rgEsc(second.name)}</b> next at ${rgMoney(second.cap)}` : ""}.`
    : `No guardrail capped a conversion in ${entry.year}.`;
  const items = rows
    .map((r, i) => {
      const badge = !r.active
        ? `<span class="rg-badge boff">${r.off ? "Off" : "Not this year"}</span>`
        : r.binding === "now"
          ? '<span class="rg-badge b1">Binding now</span>'
          : r.binding === "next"
            ? '<span class="rg-badge b2">Next in line</span>'
            : "";
      const bar = r.active ? `<div class="rg-bar" aria-hidden="true"><i style="width:${Math.min(100, (r.cap / maxCap) * 100)}%"></i></div>` : "";
      return (
        `<li class="rg-row${r.binding === "now" ? " p1" : ""}${r.active ? "" : " off"}" data-gid="${rgEsc(r.id)}">` +
        `<span class="rg-grip" title="Drag to reorder" aria-label="Drag to reorder ${rgEsc(r.name)}" role="button" tabindex="0">⋮⋮</span>` +
        `<div class="rg-main"><div class="rg-name">${i + 1}. ${rgEsc(r.name)} ${badge}</div><div class="rg-desc">${rgEsc(RG_DESC[r.id] || "")}</div></div>` +
        `<div class="rg-cap">${r.active ? rgMoney(r.cap) : "—"}<small>${r.active ? "allows up to" : "not counted"}</small></div>` +
        bar +
        `<div class="rg-ctl">${rgControls(r, g, ctx)}</div>` +
        rgWhatIfHtml(r, g) +
        "</li>"
      );
    })
    .join("");
  return (
    `<div id="rothGuardrailPanel" class="rg-panel"><div class="group-title">Conversion guardrails — from the last build</div>` +
    `<div class="rg-bar-top"><label>Plan year <select aria-label="Plan year" onchange="rothGuardrailSetYear(this.value)">${yearOpts}</select></label>` +
    `<button class="btn" type="button" aria-pressed="${ctx.manual ? "false" : "true"}" onclick="rothGuardrailAuto()">Auto-sort by dollars</button>` +
    `<span class="rg-note">${ctx.manual ? "Using your order." : "Sorted by dollars, lowest first."}</span></div>` +
    `<p class="rg-sum">${summary}</p><ol class="rg-list">${items}</ol>` +
    `<p class="small">Conversion is always the lowest active cap, whatever order you set. Your order controls how guardrails are listed; the badges follow the dollars. The what-if figures come from re-running your plan with that guardrail off; changes to settings take effect at the next build.</p></div>`
  );
}

function rgContext() {
  const g = window.rothStrategyResultFromLastBuild && window.rothStrategyResultFromLastBuild();
  const guard = g && g.guardrails;
  const fromLabel = (key) => (typeof window.rowByNormLabel === "function" ? window.rowByNormLabel(key) : null);
  return {
    guard,
    ctx: {
      year: rgYear,
      order: rgOrder,
      manual: rgManual,
      idx: (key) => {
        const r = fromLabel(key);
        return r ? r.row_index : null;
      },
      val: (key) => {
        const r = fromLabel(key);
        return r && typeof window.valOf === "function" ? window.valOf(r) : "";
      },
    },
  };
}

function rgRender() {
  const pane = document.getElementById("mainPane");
  if (!pane) return;
  const old = pane.querySelector("#rothGuardrailPanel");
  const { guard, ctx } = rgContext();
  const html = rothGuardrailPanelHtml(guard, ctx);
  if (old) {
    if (html) old.outerHTML = html;
    else old.remove();
    return;
  }
  if (!html) return;
  const anchor = pane.querySelector(".roth-optimizer-result");
  if (anchor) anchor.insertAdjacentHTML("afterend", html);
  else {
    const first = pane.querySelector(".field-list");
    if (first) first.insertAdjacentHTML("beforebegin", html);
    else pane.insertAdjacentHTML("beforeend", html);
  }
}

export function rothGuardrailSetYear(y) {
  rgYear = y;
  rgRender();
}

export function rothGuardrailAuto() {
  rgManual = false;
  rgOrder = [];
  try {
    localStorage.removeItem(RG_ORDER_KEY);
  } catch (_e) {}
  rgRender();
}

// Pointer-based drag so it also works on touch. Reorders live; the new order is
// read back from the DOM on release.
function rgStartDrag(ev) {
  const grip = ev.target.closest && ev.target.closest(".rg-grip");
  if (!grip) return;
  const li = grip.closest(".rg-row");
  const list = li && li.parentElement;
  if (!list) return;
  ev.preventDefault();
  li.classList.add("dragging");
  const move = (e) => {
    const rows = Array.from(list.querySelectorAll(".rg-row")).filter((r) => r !== li);
    const next = rows.find((r) => {
      const b = r.getBoundingClientRect();
      return e.clientY < b.top + b.height / 2;
    });
    if (next) list.insertBefore(li, next);
    else list.appendChild(li);
  };
  const end = () => {
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", end);
    document.removeEventListener("pointercancel", end);
    li.classList.remove("dragging");
    rgOrder = Array.from(list.querySelectorAll(".rg-row")).map((r) => r.dataset.gid);
    rgManual = true;
    try {
      localStorage.setItem(RG_ORDER_KEY, JSON.stringify(rgOrder));
    } catch (_e) {}
    rgRender();
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", end);
  document.addEventListener("pointercancel", end);
}

function rgInsert() {
  if (window.activeStep !== RG_STEP) return;
  rgRender();
}

try {
  document.addEventListener("pointerdown", rgStartDrag);
  const prevRenderMain = window.renderMain;
  if (typeof prevRenderMain === "function")
    window.renderMain = function () {
      prevRenderMain.apply(this, arguments);
      rgInsert();
    };
} catch (_e) {}

Object.assign(window, {
  rgMoney,
  rgRankRows,
  rgWhatIf,
  rothGuardrailPanelHtml,
  rothGuardrailSetYear,
  rothGuardrailAuto,
});
