// v11 admin note: Client-specific Plan Data is read-only here
// v11 local-only system configuration area: Local reports
// v11 admin UI compatibility marker: class="section-help-btn" onclick="showSectionHelp(event,this)" data-help-note
// v11 admin UI marker: setting-help-btn
// v11 nav descriptions use line-broken labels: <br><span class="step-desc"
let csrfToken = "";
const ADMIN_APP_UNAVAILABLE_MESSAGE =
  "Application unavailable. System Configuration editing, local report downloads, reference-data saves, pricing refresh, and diagnostics are unavailable";
const api = (p, o = {}) => {
  o = o || {};
  const method = String(o.method || "GET").toUpperCase();
  const headers = Object.assign(
    { "Content-Type": "application/json" },
    o.headers || {},
  );
  if (csrfToken && method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  return fetch(p, { ...o, headers }).then(async (r) => {
    const t = await r.text();
    let j;
    try {
      j = JSON.parse(t);
    } catch (e) {
      j = { success: r.ok, text: t };
    }
    if (!r.ok || j.success === false) throw new Error(j.error || t);
    return j;
  });
};
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (m) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        m
      ],
  );
const TRASH_SVG_ICON =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><path fill="currentColor" d="M6 1.5h4a.5.5 0 0 1 .5.5v1h3a.5.5 0 0 1 0 1h-.6l-.7 9.4a1.5 1.5 0 0 1-1.5 1.4H5.3a1.5 1.5 0 0 1-1.5-1.4L3.1 4H2.5a.5.5 0 0 1 0-1h3V2a.5.5 0 0 1 .5-.5Zm-1.9 2.5.68 9.32a.5.5 0 0 0 .5.46h5.44a.5.5 0 0 0 .5-.46L11.9 4H4.1Zm2.15 1.75a.5.5 0 0 1 .5.5v5.5a.5.5 0 0 1-1 0v-5.5a.5.5 0 0 1 .5-.5Zm3.5 0a.5.5 0 0 1 .5.5v5.5a.5.5 0 0 1-1 0v-5.5a.5.5 0 0 1 .5-.5ZM7 2.5v.5h2v-.5H7Z"/></svg>';
function deleteIconBtn(onclickExpr, opts) {
  opts = opts || {};
  const extraCls = opts.cls ? " " + opts.cls : "";
  return `<button type="button" class="danger icon-btn${extraCls}" onclick="${onclickExpr}" title="Delete" aria-label="Delete">${TRASH_SVG_ICON}</button>`;
}
// UX-006: #msg is a live region (role=status, aria-live=polite in admin.html).
// Errors switch it to role=alert / assertive and add the .error style.
function msg(s, isError) {
  const el = document.getElementById("msg");
  if (!el) return;
  el.setAttribute("role", isError ? "alert" : "status");
  el.setAttribute("aria-live", isError ? "assertive" : "polite");
  el.classList.toggle("error", !!isError);
  el.textContent = s;
}
// Unsaved-change announcement: announced once per editor, not per keystroke.
function announceUnsaved(title) {
  const text = "Unsaved changes in " + title;
  const el = document.getElementById("msg");
  if (el && el.textContent === text && !el.classList.contains("error")) return;
  msg(text);
}
// UX-006: in-app confirm (a modal <dialog>: native focus trap, Escape, restore).
function adminConfirm(message, confirmLabel) {
  return new Promise((resolve) => {
    const d = document.createElement("dialog");
    d.className = "admin-modal";
    d.setAttribute("role", "alertdialog");
    d.setAttribute("aria-labelledby", "adminConfirmText");
    d.innerHTML = `<p id="adminConfirmText">${esc(message)}</p><form method="dialog" class="admin-modal-actions"><button value="no" autofocus>Cancel</button><button value="yes" class="danger">${esc(confirmLabel || "Confirm")}</button></form>`;
    d.addEventListener("close", () => {
      d.remove();
      resolve(d.returnValue === "yes");
    });
    document.body.appendChild(d);
    d.showModal();
  });
}
let adminAppReady = true;
async function checkApp() {
  const st = document.getElementById("adminAppStatus");
  const was = adminAppReady;
  try {
    const r = await fetch("/api/ping", { cache: "no-store" });
    if (r.ok) {
      adminAppReady = true;
      try {
        const sr = await fetch("/api/auth/session", { cache: "no-store" });
        const sj = await sr.json();
        if (sj && sj.csrf_token) csrfToken = sj.csrf_token;
      } catch (_e) {}
      if (st) {
        st.className = "status ok";
        if (st.dataset.label) st.textContent = st.dataset.label;
      }
      return true;
    }
  } catch (e) {}
  adminAppReady = false;
  if (st) {
    st.className = "status bad";
    st.textContent = "Unavailable";
  }
  if (was)
    msg(
      "Application unavailable. System Configuration editing, reference-data saves, pricing refresh, and diagnostics are unavailable until the app restarts.",
    );
  return false;
}
let sysCfgRows = [],
  sysCfgOriginal = "",
  sysCfgChanged = false,
  activeEditor = null;
let activeAdminStep = "app_settings",
  activeEditorHeadingPage = 0,
  editorHeadingNavPages = [],
  lastAdminNavItems = [],
  adminNavSearchText = "",
  adminSearchScope = "nav",
  adminPageSearchText = "";
const ADMIN_HELP = {
  app_settings: {
    title: "App settings",
    purpose: "Review the local desktop app address, port, and start commands.",
    impact:
      "These settings affect whether the local User UI and System Configuration can connect and whether workbook builds run from the browser.",
    consider:
      "Ask: do I need to change how I start the local app or give builds more time? Change the port only if it conflicts with another local program; change build timeout when Advanced Exact Scalar Monte Carlo needs more time. This build is local-only: client registry, public-hosting, reverse-proxy and browser-login controls are removed, plan data lives in the plan file, and reports come from the download buttons after a build. Clear cache removes saved browser-side UI state (Build History, workbench layout, etc.) and the app window's render/HTTP cache; use it if the UI still looks stale after an update. A code change to the Python backend always needs a full app restart.",
  },
  system_config: {
    title: "System configuration",
    purpose:
      "Maintain the shared settings that shape app behavior, build behavior, pricing, security, and reporting defaults.",
    impact:
      "These rows flow into runtime startup, workbook generation, optimizer choices, report content, output warnings, and advisor-readiness flags.",
    consider:
      "Use the focused pages for routine edits. Use the broad table only when you need to audit or change several related settings. Compact table view: changes save to the system configuration store and keep CSV adapter compatibility. Use the triangles to expand sections; focus any value control to update this panel. The raw CSV editor is only for bulk adapter maintenance or adding columns; normal planning edits belong in the main UI.",
  },
  pricing: {
    title: "Pricing / market data",
    purpose:
      "Control whether holdings are valued from live quotes, cached quotes, or fallback cost basis.",
    impact:
      "Pricing affects account values in the workbook, allocation drift, trade recommendations, tax-lot gain/loss estimates, report warnings, and advisor-ready pricing status.",
    consider:
      "Use CACHE for ordinary work. It uses any cached quote, even stale, before falling back to cost basis when no cache exists. Cost basis is now only a fallback when no cached quote exists. The single-symbol tester calls each live provider directly, bypassing cache selection, and prints the redacted command sent to each service plus response status, timing, preview, parser result and final provider selection.",
  },
  tax_law: {
    title: "Tax-law update dashboard",
    purpose:
      "Review every tax-sensitive constant with its vintage, source, last reviewed date and whether it blocks advisor-ready status.",
    impact:
      "Blocking means the report may still be illustrative, but advisor-ready or recommendation status is not allowed until the constant is updated or signed off.",
    consider:
      "Plan assumption review lives in the User UI Review section so it stays connected to plan outputs; it is not mandatory signoff language.",
  },
  diagnostics: {
    title: "Workbook build diagnostics",
    purpose: "Review what the last build actually used and produced.",
    impact:
      "Diagnostics reveal the source data behind workbook outputs: price sources, QC status, generated files, and whether report warnings should be investigated.",
    consider:
      "Ask: did the workbook use the data and assumptions I expected? Open this after changing pricing, tax, allocation, or other system settings. The list shows the last generated local output files.",
  },
  allocation: {
    title: "Allocation policy / asset classes",
    purpose:
      "Define which asset classes are targets, alternates, exclusions, or covered by existing non-liquid assets.",
    impact:
      "These controls drive recommended allocations, drift analysis, coverage by pensions/home equity/notes, and trade completeness.",
    consider:
      "Do not let excluded or covered sleeves consume liquid target allocation unless that is intentional.",
  },
  optimizer: {
    title: "Optimizer / rebalancing controls",
    purpose:
      "Set the constraints that balance drift, taxes, turnover, account location, concentration, and fallback behavior.",
    impact:
      "Tighter limits reduce unintended trades but can leave more drift; looser limits may improve fit at greater tax or turnover cost.",
    consider:
      "Change one family of constraints at a time and check diagnostics after rebuilding.",
  },
  etf: {
    title: "ETF universe / replacements",
    purpose:
      "Maintain the security universe and capital-market assumptions used by allocation and replacement recommendations.",
    impact:
      "Ticker mapping, expected return, volatility, and correlations affect optimizer output even when account values are correct.",
    consider:
      "Review asset-class mapping before trusting recommendations for a new holding.",
  },
  accountsTax: {
    title: "Tax constants & tax-aware settings",
    purpose:
      "Maintain reference tax constants and system-level tax-aware trade assumptions. Client holdings and tax lots are edited in the User UI.",
    impact:
      "Tax constants affect workbook tax schedules, Roth strategy scoring, withdrawal taxes, estate-tax exposure, and tax-freshness warnings. Pricing fallback behavior still uses cost basis only when no cached quote exists.",
    consider:
      "Review tax source years before relying on tax-sensitive outputs; stale cache remains preferred over cost basis for prices.",
  },
  household: {
    title: "User inputs / household assumptions",
    purpose:
      "Edit client facts from the admin side using the same style of field help as the user workflow.",
    impact:
      "Household, income, spending, insurance, estate, and policy rows feed projections and report language.",
    consider:
      "Treat these as production Plan Data changes, not just admin settings.",
  },
  optional: {
    title: "Optional workbook functions",
    purpose: "Turn advanced report modules on or off.",
    impact:
      "Disabled modules shorten reports but can hide diagnostics or explanations that matter for review.",
    consider:
      "Disable only when a section is irrelevant or intentionally out of scope.",
  },
};
function navHelpKey(id) {
  const item =
    (lastAdminNavItems || []).find((x) => x.id === id) ||
    (editorHeadingNavPages || []).find((x) => x.id === id);
  return item?.helpKey || id;
}
function adminHelpMarkup(h) {
  return `<div class="help-title">${esc(h.title || "Guided step")}</div><div class="help-body"><h3>What this page controls</h3><p>${esc(h.purpose || "Review this setting and change it only when the real-world assumption, data source, or planning goal has changed.")}</p><h3>How the settings work together</h3><p>${esc(h.connections || h.impact || "These settings can affect cash flow, terminal net worth, lifetime taxes, post-terminal taxes, Medicare premiums, risk, recommendations, warnings, workbook narratives, or system reliability.")}</p><h3>How to choose values</h3><p>${esc(h.options || h.consider || "Choose the value that matches the documented assumption or operational goal. Change one related setting family at a time when troubleshooting.")}</p><h3>Likely planning or system impact</h3><p>${esc(h.impact || "Changes can affect report output, build behavior, diagnostics, or recommendations after the next save/rebuild.")}</p></div>`;
}
function setAdminStep(id) {
  activeAdminStep = id || activeAdminStep;
  renderAdminNav();
  document
    .querySelectorAll("[data-admin-step]")
    .forEach((b) =>
      b.classList.toggle("active", b.dataset.adminStep === activeAdminStep),
    );
  const item =
    (lastAdminNavItems || []).find((x) => x.id === activeAdminStep) ||
    (editorHeadingNavPages || []).find((x) => x.id === activeAdminStep);
  const h = ADMIN_HELP[navHelpKey(activeAdminStep)] || {
    title: item?.title || "Guided step",
    purpose: item?.desc || "Review this focused system configuration area.",
    impact:
      "The edited values flow into the database-backed build workflow while preserving CSV adapter compatibility for bulk maintenance.",
    connections:
      "Settings on this page often work together; review sibling fields before changing isolated values.",
    options:
      "Use row help for value-level meaning, options, relationships, and likely impact. Rebuild after saving when outputs depend on the setting.",
  };
  const box = document.getElementById("adminHelp");
  if (box) box.innerHTML = adminHelpMarkup(h);
  const st = document.getElementById("adminAppStatus");
  if (st) {
    st.dataset.label = h.title;
    if (adminAppReady) {
      st.className = "status ok";
      st.textContent = h.title;
    }
  }
}

function modeCard(key, m, current) {
  return `<div class="mode-card active"><h3>${esc(m.title)}</h3><p>${esc(m.description)}</p><p><b>Host:</b> <span class="code">${esc(m.host)}</span></p><p><b>Start:</b> <span class="code">${esc(m.command)}</span></p></div>`;
}
async function showAppSettings() {
  setAdminStep("app_settings");
  const s = await api("/api/admin/server");
  document.getElementById("main").innerHTML =
    `<h2>App settings</h2><div class="row"><span class="pill">Mode: Local desktop</span><span class="pill">URL: ${esc("http://" + s.host + ":" + s.port)}</span></div><div class="mode-grid">${Object.entries(
      s.modes || {},
    )
      .map(([k, v]) => modeCard(k, v, s.app_mode))
      .join(
        "",
      )}</div><button class="primary" onclick="showSystemConfig('build_timeout')">Edit build timeout / max_build_seconds</button><h3>Start commands</h3><table><tr><th>Command</th><th>Purpose</th></tr>${Object.entries(
      s.commands || {},
    )
      .map(
        ([k, v]) =>
          `<tr><td>${esc(k)}</td><td><code>${esc(v)}</code></td></tr>`,
      )
      .join(
        "",
      )}</table><button class="danger" onclick="shutdown()">Shut down app</button> <button onclick="clearAppCache()">Clear cache</button>`;
  msg("App settings loaded");
}
async function clearAppCache() {
  if (
    !(await adminConfirm(
      "Clear saved UI state (Build History, workbench layout, etc.) and the app's render cache? This cannot be undone.",
      "Clear cache",
    ))
  )
    return;
  try {
    localStorage.clear();
  } catch (_e) {}
  const out = await api("/api/admin/clear-webview-cache", {
    method: "POST",
    body: "{}",
  });
  const cleared = (out && out.cleared) || [];
  const skipped = (out && out.skipped) || [];
  let text = cleared.length
    ? `Cleared: ${cleared.join(", ")}.`
    : "No render-cache folders needed clearing.";
  if (skipped.length)
    text += ` ${skipped.length} folder(s) are in use by this running window and could not be cleared -- fully close and reopen the app to finish.`;
  msg(text);
}
function navigateToClientUi() {
  if (window.__is_desktop_app__) {
    // Call the pywebview bridge directly instead of relying on
    // location.href interception: WebView2/EdgeChromium does not always
    // allow pywebview_bridge.js to override Location.prototype.href (see
    // the try/catch there), so that path can silently fall through to a
    // real file:// navigation to a URL that doesn't exist on disk.
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.navigate("/");
    } else {
      window.addEventListener(
        "pywebviewready",
        function () {
          window.pywebview.api.navigate("/");
        },
        { once: true },
      );
    }
    return;
  }
  location.href = "/";
}
async function logout() {
  navigateToClientUi();
}
async function shutdown() {
  await api("/api/admin/server/shutdown", { method: "POST", body: "{}" });
  msg("Shutdown requested. Close this tab after the app closes.");
}

// Each page belongs to one nav group (see NAV_GROUP_ORDER). Pages scoped to a
// system_config.csv section/subsection. 'assumptions' and 'correlations' each
// edit their settings and link to the matching custom CSV (one nav entry each).
const SYSTEM_CONFIG_PAGES = [
  {
    id: "runtime",
    group: "System configuration",
    title: "Runtime & files",
    desc: "Core version, config backend, file paths, output paths, and local Plan Data defaults.",
    filterSections: ["System Configuration"],
    filterSubsections: ["Runtime"],
  },
  {
    id: "access",
    group: "System configuration",
    title: "Dashboard & security",
    desc: "Local dashboard host, port, and local-only security settings.",
    filterSections: ["System Configuration"],
    filterSubsections: ["Dashboard", "Security"],
  },
  {
    id: "build_timeout",
    group: "System configuration",
    title: "Build timeout",
    desc: "Maximum build runtime before timeout. Increase this for exact scalar Monte Carlo or larger simulation counts.",
    filterSections: ["System Configuration"],
    filterKeys: ["max_build_seconds"],
  },
  {
    id: "assumptions",
    group: "Market data",
    title: "Capital market assumptions",
    desc: "Expected returns, volatility, custom assumption files, and long-term optimizer inputs.",
    filterSections: ["Asset Class Assumptions"],
  },
  {
    id: "correlations",
    group: "Market data",
    title: "Asset correlations",
    desc: "Pairwise correlation settings used by optimizer diversification calculations.",
    filterSections: ["Asset Correlations"],
  },
  {
    id: "jobs",
    group: "Market data",
    title: "Refresh & drift",
    desc: "Nightly price refresh, drift thresholds, and portfolio file links.",
    filterSections: ["System Configuration"],
    filterSubsections: ["Price Refresh", "Portfolio Drift"],
    helpKey: "pricing",
  },
  {
    id: "plan",
    group: "Tax & accounts",
    title: "Tax modeling",
    desc: "System-level switches for the Net Investment Income Tax (NIIT) and residence-state estate tax.",
    filterSections: ["Plan Settings"],
    helpKey: "tax",
  },
  {
    id: "rebalancing",
    group: "Tax & accounts",
    title: "Global rebalancing controls",
    desc: "Household-level tax-aware optimizer mode, risk limits, tax-aware trade controls, and objective weights.",
    filterSections: ["Rebalancing"],
    helpKey: "optimizer",
  },
  {
    id: "annuity_calibration",
    group: "Tax & accounts",
    title: "Annuity calibration",
    desc: "Carrier-agnostic annuity purchase-rate curve and reserve-decay factors used to value annuity income. Edit to match a specific carrier's rates.",
    filterSections: ["Annuity Calibration"],
    helpKey: "tax",
  },
];
function systemConfigPage(id) {
  return SYSTEM_CONFIG_PAGES.find((p) => p.id === id) || SYSTEM_CONFIG_PAGES[0];
}
const NAV_GROUP_ORDER = ["System configuration", "Market data", "Tax & accounts"];
function adminNavItems() {
  const byGroup = {};
  const add = (item) => (byGroup[item.group] = byGroup[item.group] || []).push(item);
  const pageItem = (p) => ({
    id: "syscfg_" + p.id,
    group: p.group,
    title: p.title,
    desc: p.desc,
    action: `showSystemConfig('${p.id}')`,
    helpKey: p.helpKey || "system_config",
  });
  const pages = (group) =>
    SYSTEM_CONFIG_PAGES.filter((p) => p.group === group).map(pageItem);

  add({
    id: "app_settings",
    group: "System configuration",
    title: "App settings",
    desc: "Local host, port, start commands, and shutdown / cache tools",
    action: "showAppSettings()",
    helpKey: "app_settings",
  });
  pages("System configuration").forEach(add);
  add({
    id: "diagnostics",
    group: "System configuration",
    title: "Workbook build diagnostics",
    desc: "Last build source, QC, forecast package status",
    action: "showDiagnostics()",
    helpKey: "diagnostics",
  });

  add({
    id: "pricing_controls",
    group: "Market data",
    title: "Pricing controls",
    desc: "CACHE, LIVE, OFFLINE, cache window, and provider settings",
    action: "openPricingControls()",
    helpKey: "pricing",
  });
  pages("Market data").forEach(add);

  add({
    id: "tax_law_dashboard",
    group: "Tax & accounts",
    title: "Tax-law update dashboard",
    desc: "Federal/state/IRMAA/Social Security/RMD constants, source, year, and review status",
    action: "showTaxLawDashboard()",
    helpKey: "tax_law",
  });
  pages("Tax & accounts").forEach(add);

  return NAV_GROUP_ORDER.flatMap((g) => byGroup[g] || []);
}
function renderAdminNav() {
  const box = document.getElementById("adminSteps");
  if (!box) return;
  lastAdminNavItems = adminNavItems();
  let items = [...lastAdminNavItems, ...editorHeadingNavPages];
  const q = String(adminNavSearchText || "")
    .trim()
    .toLowerCase();
  if (q) {
    items = items.filter(
      (it) =>
        [it.id, it.group, it.title, it.desc, it.file]
          .join(" ")
          .toLowerCase()
          .includes(q) || it.id === activeAdminStep,
    );
  }
  let lastGroup = "",
    stepNo = 0;
  box.classList.add("grouped");
  box.innerHTML =
    items
      .map((it) => {
        const group = it.group || "Current editor";
        const label =
          group !== lastGroup
            ? `<div class="nav-group-label">${esc(group)}</div>`
            : "";
        if (group !== lastGroup) lastGroup = group;
        stepNo++;
        return `${label}<button class="stepbtn ${it.id === activeAdminStep ? "active" : ""}"${it.id === activeAdminStep ? ' aria-current="step"' : ""} data-admin-step="${esc(it.id)}" onclick="${it.action}"><span class="num">${stepNo}</span><span><span class="step-title">${esc(it.title)}</span><div class="step-desc">${esc(it.desc || "Open this page")}</div></span></button>`;
      })
      .join("") || '<div class="no-results">No navigation matches.</div>';
}
function setAdminNavSearch(q) {
  adminNavSearchText = q;
  renderAdminNav();
}
function updateAdminSearchToggle() {
  const el = document.getElementById("adminCombinedSearch");
  if (el) {
    el.value =
      adminSearchScope === "nav" ? adminNavSearchText : adminPageSearchText;
    el.placeholder =
      adminSearchScope === "nav"
        ? "Search navigation..."
        : "Search this page...";
  }
  document
    .querySelectorAll("[data-admin-search-scope]")
    .forEach((b) =>
      b.classList.toggle(
        "primary",
        b.dataset.adminSearchScope === adminSearchScope,
      ),
    );
}
function setAdminSearchScope(scope) {
  adminSearchScope = scope === "page" ? "page" : "nav";
  updateAdminSearchToggle();
  if (adminSearchScope === "page") filterActiveTable();
  else renderAdminNav();
}
function setAdminCombinedSearch(q) {
  if (adminSearchScope === "nav") {
    adminNavSearchText = q;
    renderAdminNav();
  } else {
    adminPageSearchText = q;
    const cfg = document.getElementById("cfgSearch");
    if (cfg) cfg.value = q;
    filterActiveTable();
  }
  updateAdminSearchToggle();
}
async function showSystemConfig(pageId = "runtime") {
  const page = systemConfigPage(pageId);
  setAdminStep("syscfg_" + page.id);
  const def = {
    kind: "system",
    file: "system_config.csv",
    title: page.title,
    profile: "section_settings",
    filterSections: page.filterSections || [],
    filterSubsections: page.filterSubsections || [],
    // Was missing: SYSTEM_CONFIG_PAGES' "build_timeout" entry (and any future
    // page scoped by exact setting key rather than by section/subsection)
    // silently fell back to showing its whole section, since
    // filteredSettingRows() only skips the filterKeys check when the field is
    // absent/empty -- undefined here always counted as "no filter."
    filterKeys: page.filterKeys || [],
    defaultOpen: false,
    collapseBySubsection: true,
    note: page.desc + " Changes save to this install's settings (engine knobs to the active plan).",
    navStep: "syscfg_" + page.id,
  };
  await loadCsvEditor(def, `showSystemConfig('${page.id}')`);
  sysCfgRows = activeEditor.rows;
  sysCfgOriginal = rowsToCsv(sysCfgRows);
  sysCfgChanged = false;
  const h = document.querySelector("#main h2");
  if (h)
    h.insertAdjacentHTML(
      "afterend",
      summarizeRows(filteredSettingRows(sysCfgRows, def).map((x) => x.r)),
    );
}
async function openPricingControls() {
  setAdminStep("pricing_controls");
  await loadCsvEditor(
    {
      kind: "system",
      file: "system_config.csv",
      title: "Pricing controls",
      profile: "section_settings",
      filterSections: ["Market Pricing"],
      defaultOpen: false,
      note: "LIVE tries quote providers first; CACHE uses cached prices even when stale before live calls; OFFLINE avoids live calls.",
      navStep: "pricing_controls",
    },
    "openPricingControls()",
  );
  renderPricingSymbolTester();
}

function renderPricingSymbolTester() {
  const main = document.getElementById("main");
  if (!main || document.getElementById("pricingSymbolTester")) return;
  const html = `<div id="pricingSymbolTester" class="note-box" style="margin:0 0 14px 0">
    <h3 style="margin-top:0">Single-symbol live pricing tester</h3>
        <div class="row"><input id="pricingTestSymbol" aria-label="Ticker symbol to test" placeholder="Ticker, e.g. VTI" style="max-width:220px;text-transform:uppercase" onkeydown="if(event.key==='Enter')runLivePriceSymbolTest()"><button class="primary" onclick="runLivePriceSymbolTest()">Test live quote</button><span id="pricingTestStatus" class="muted"></span></div>
    <div id="pricingTestResult" style="margin-top:12px"></div>
  </div>`;
  const pane = main.querySelector(".pane-head");
  if (pane) pane.insertAdjacentHTML("afterend", html);
  else main.insertAdjacentHTML("afterbegin", html);
}
function fmtPriceDiagnostic(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0
    ? "$" +
        n.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        })
    : esc(v ?? "");
}
function renderJsonBlock(obj) {
  return `<pre class="code" style="display:block;white-space:pre-wrap;max-height:260px;overflow:auto;margin:6px 0">${esc(JSON.stringify(obj, null, 2))}</pre>`;
}
function renderProviderAttempt(a) {
  return `<div class="diag-card" style="margin:8px 0;background:${a.ok ? "#f0fdf4" : "#fff7ed"}"><div class="row"><b>${esc(a.transport || "transport")}</b><span class="pill">${a.ok ? "ok" : "failed"}</span>${a.status_code ? `<span class="pill">HTTP ${esc(a.status_code)}</span>` : ""}<span class="pill">${esc(a.elapsed_ms ?? "")} ms</span>${a.content_type ? `<span class="pill">${esc(a.content_type)}</span>` : ""}</div><h4>Command sent</h4>${renderJsonBlock(a.command || {})}${a.cause ? `<h4>Failure cause</h4><p class="muted">${esc(a.cause)}</p>` : ""}${a.exception ? `<h4>Exception</h4><p class="muted">${esc(a.exception)}</p>` : ""}${a.response_preview ? `<h4>Response preview</h4><pre class="code" style="display:block;white-space:pre-wrap;max-height:180px;overflow:auto">${esc(a.response_preview)}</pre>` : ""}</div>`;
}
function renderProviderStep(s) {
  const ok = s.outcome === "success";
  const skipped = s.outcome === "skipped" || s.enabled === false;
  return `<details class="cfg-section" ${ok || !skipped ? "open" : ""}><summary><span class="summary-title">${esc(s.provider || "provider")} · ${esc(s.endpoint || "endpoint")}</span><span class="badge ${ok ? "ok" : skipped ? "warn" : "bad"}">${esc(s.outcome || "unknown")}</span></summary><div style="padding:12px"><div class="diag-grid"><div class="diag-card"><b>Parsed price</b><p>${s.parsed_price ? fmtPriceDiagnostic(s.parsed_price) : "—"}</p></div><div class="diag-card"><b>Parser note</b><p class="muted">${esc(s.parse_note || "")}</p></div><div class="diag-card"><b>Cause</b><p class="muted">${esc(s.cause || "")}</p></div></div>${(s.attempts || []).map(renderProviderAttempt).join("")}${!s.attempts || !s.attempts.length ? `<p class="muted">${esc(s.cause || "No command was sent for this provider.")}</p>` : ""}</div></details>`;
}
function renderPricingSymbolTrace(r) {
  const steps = r.steps || [];
  return `<div class="section-note"><b>${esc(r.symbol || "")}</b> — ${esc(r.summary || "No summary")}</div><div class="diag-grid"><div class="diag-card"><b>Selected live provider</b><p>${esc(r.selected_provider || "none")}</p></div><div class="diag-card"><b>Selected price</b><p>${r.selected_price ? fmtPriceDiagnostic(r.selected_price) : "—"}</p></div><div class="diag-card"><b>Provider order</b><p class="muted">${esc((r.provider_order || []).join(" → "))}</p></div><div class="diag-card"><b>Proxy/cert environment</b><p class="muted">${r.proxy_environment_present ? "Present: " + esc((r.proxy_environment_keys || []).join(", ")) : "None detected"}</p></div></div><details class="cfg-section" open><summary><span class="summary-title">Runtime and key diagnostics</span></summary><div style="padding:12px">${renderJsonBlock({ generated_at_utc: r.generated_at_utc, config_backend: r.config_backend, config_path: r.config_path, workspace_id: r.workspace_id, timeout_seconds: r.timeout_seconds, max_retries: r.max_retries, requests_available: r.requests_available, effective_api_key_sources: r.effective_api_key_sources, cache_record: r.cache_record })}</div></details><h3>Provider command / response trace</h3>${steps.map(renderProviderStep).join("") || '<div class="no-results">No provider steps returned.</div>'}`;
}
async function pollLivePriceSymbolJob(jobId, status, result) {
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const out = await api(
      "/api/prices/test-symbol/status/" + encodeURIComponent(jobId),
      { timeoutMs: 9000 },
    );
    const trace = out.result || {
      symbol: out.symbol,
      summary: "Calling live providers...",
      steps: out.steps || [],
    };
    if (out.steps && (!trace.steps || !trace.steps.length))
      trace.steps = out.steps;
    if (result) result.innerHTML = renderPricingSymbolTrace(trace);
    const count = (trace.steps || []).length;
    if (status)
      status.textContent =
        out.status === "running"
          ? `Calling live providers... ${count} step${count === 1 ? "" : "s"} returned`
          : out.status === "completed"
            ? out.live_pricing_working
              ? "Live quote found"
              : "No live quote found"
            : "Diagnostic error";
    if (out.status === "completed" || out.status === "error") return out;
  }
  throw new Error(
    "Pricing tester timed out waiting for the local diagnostic job. A provider call may still be running; try a shorter timeout in Market Pricing settings.",
  );
}
async function runLivePriceSymbolTest() {
  const input = document.getElementById("pricingTestSymbol");
  const status = document.getElementById("pricingTestStatus");
  const result = document.getElementById("pricingTestResult");
  const symbol = (input?.value || "").trim().toUpperCase();
  if (!symbol) {
    msg("Enter one ticker symbol first");
    return;
  }
  if (status) status.textContent = "Starting diagnostic...";
  if (result)
    result.innerHTML =
      '<div class="section-note" data-kind="state">Starting local diagnostic job…</div>';
  try {
    const started = await api("/api/prices/test-symbol/start", {
      method: "POST",
      body: JSON.stringify({ symbol }),
      timeoutMs: 9000,
    });
    if (status) status.textContent = "Calling live providers...";
    const out = await pollLivePriceSymbolJob(started.job_id, status, result);
    const liveOk = !!(
      out.live_pricing_working ||
      (out.result && out.result.success)
    );
    msg(
      liveOk
        ? "Live pricing tester found a quote"
        : "Live pricing tester completed with failures",
    );
  } catch (e) {
    const detail = String((e && e.message) || e || "Unknown error");
    if (result)
      result.innerHTML = `<div class="section-note warn" data-kind="warn" title="Endpoint: /api/prices/test-symbol/start"><b>Pricing tester could not reach the local API.</b><br>${esc(detail)}<br>Restart the app and check the status shows Ready.</div>`;
    if (status) status.textContent = "Error";
    msg("Pricing tester error: " + detail, true);
  }
}

async function showTaxLawDashboard() {
  setAdminStep("tax_law_dashboard");
  const out = await api("/api/admin/tax-law-dashboard");
  document.getElementById("main").innerHTML =
    `<h2>Tax-law update dashboard</h2><table><tr><th>Constant</th><th>Category</th><th>Year</th><th>Source</th><th>Last reviewed</th><th>Status</th></tr>${(out.rows || []).map((r) => `<tr><td>${esc(r.constant)}</td><td>${esc(r.category)}</td><td>${esc(r.year)}</td><td>${esc(r.source)}</td><td>${esc(r.last_reviewed)}</td><td><span class="badge ${r.blocking ? "bad" : "ok"}">${esc(r.status)}</span></td></tr>`).join("")}</table>`;
  msg("Tax-law dashboard loaded");
}
async function showAdvisorSignoff() {
  setAdminStep("reference");
  document.getElementById("main").innerHTML =
    `<h2>Assumption review moved</h2><p class="muted" data-kind="state">Plan assumption review is in the User UI Review section.</p>`;
  msg("Assumption review is in the User UI");
}

async function showDiagnostics() {
  setAdminStep("diagnostics");
  const out = await api("/api/admin/diagnostics");
  document.getElementById("main").innerHTML =
    `<h2>Workbook build diagnostics</h2><p class="muted">${esc(out.output_dir)}</p><div class="diag-grid">${out.files.map((f) => `<div class="diag-card"><b>${esc(f.name)}</b><p class="muted">${esc(f.path)}</p><span class="pill ${f.available ? "good" : "bad"}">${f.available ? "available" : "missing"}</span><span class="pill">${esc(f.bytes)} bytes</span>${f.json ? `<h4>Summary</h4><pre class="code" style="white-space:pre-wrap;display:block;max-height:220px;overflow:auto">${esc(JSON.stringify(summarizeDiagnostic(f.json), null, 2))}</pre>` : ""}</div>`).join("")}</div>`;
  msg("Diagnostics loaded");
}
function summarizeDiagnostic(j) {
  if (!j || typeof j !== "object") return j;
  const keep = [
    "pricing_source_summary",
    "pricing_source_category",
    "pricing_source_note",
    "pricing_mode",
    "live_enabled",
    "cache_as_of_local",
    "cache_as_of_utc",
    "source_counts",
    "qc_summary",
    "build_time_utc",
    "allocation_recommendation_source",
    "trade_optimizer_mode",
  ];
  const o = {};
  keep.forEach((k) => {
    if (j[k] !== undefined) o[k] = j[k];
  });
  return Object.keys(o).length ? o : j;
}
async function showWorkspaces() {
  setAdminStep("app_settings");
  document.getElementById("main").innerHTML =
    `<h2>Local-only package</h2><p class="muted" data-kind="state">Client registry and report browsing pages were removed.</p>`;
  msg("Local-only package: client registry removed");
}
async function editWorkspacePlanData(t, name) {
  msg(
    "Client Plan Data editing has moved to the User UI. Admin shows Plan Data read-only by default.",
  );
  return false;
}
window.addEventListener("beforeunload", (e) => {
  if (sysCfgChanged || (activeEditor && activeEditor.changed)) {
    e.preventDefault();
    e.returnValue = "Unsaved changes";
  }
});
renderAdminNav();
updateAdminSearchToggle();
// system_review 2026-08-31 item 3.11: showAppSettings()/checkApp() fire real
// fetch() calls (through api()) and used to run as bare top-level statements
// here, synchronously, during this classic script's own execution. That was
// fine while pywebview_bridge.js was ALSO classic -- classic scripts run in
// document order, and its tag comes first. Once pywebview_bridge.js became
// type="module" (frontend/admin.html), its fetch()/EventSource patch moved
// to the deferred-module phase, which runs strictly after every classic
// script -- including this one. Firing these calls unchanged would race the
// unpatched native fetch under pywebview, the same failure shape
// test_dashboard_startup_race_and_script_order.py guards against for
// dashboard.js. DOMContentLoaded fires only after all deferred/module
// scripts have run, so waiting for it here is what actually closes the race
// (a queueMicrotask, dashboard.js's own boot-defer mechanism, does NOT --
// microtasks queued during a classic script's execution flush within that
// same pre-parsing-complete phase, before any deferred module runs).
// See tests/test_pywebview_bridge_load_order_regression.py.
function _bootAppStatus() {
  showAppSettings().catch((e) => msg("Error: " + e.message, true));
  checkApp();
  setInterval(checkApp, 5000);
}
if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", _bootAppStatus, { once: true });
} else {
  // Classic scripts always run before parsing finishes, so this branch is
  // not expected in a real page load -- kept only so a script injected after
  // DOMContentLoaded (e.g. a test harness) still boots instead of hanging.
  _bootAppStatus();
}
