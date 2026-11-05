/* Investment Holdings (Plan Holdings lot table) -- extracted from dashboard.js.
   Wave 6.4 (system review 2026-08-04, architect finding
   frontend-single-global-namespace, "leaves inward"): second leaf after
   spending_dashboard.js, and the first extracted FROM inside the dashboard.js
   monolith rather than a file that already stood alone. Loaded as
   type="module" (deferred), so it always finishes executing before any
   user-triggered click handler or async callback can run -- see
   dashboard_shared_helpers.js for why an EARLY-loaded file can't take this
   same treatment.

   State that dashboard.js also reads/writes directly (holdingsText,
   holdingsChanged, currentHoldingAccount, holdingRowsCache, holdingsPriceData,
   holdingsPriceLoading) is kept on window explicitly rather than as
   module-local bindings: a module's own top-level declarations are private to
   the module and invisible to classic <script> tags, so dashboard.js's own
   references to this state (loadAll's reset-on-plan-load, the unsaved-changes
   counter, the allocation-preview fingerprint, etc.) would silently break if
   this state were hidden inside the module instead. Everything else --
   dashboard.js's own let/const/function declarations like rows, appReady,
   lastBuildOk, renderMain, esc, accountDisplayLabel -- IS visible to this
   module as a bare identifier without any window.* bridging: classic
   <script> declarations and module code share the same realm's global scope
   for lookups the module doesn't declare itself (verified live in a running
   browser session, not just assumed from the spec). accountDisplayLabel
   specifically stayed in dashboard.js despite living right next to this code
   originally, because it's a general account-label utility other domains
   (QDRO labels, YTD dropdowns) and an earlier-loaded classic script
   (dashboard_decomp_supplemental_tables.js) also depend on. */

window.holdingsText = "";
window.holdingsChanged = false;
window.holdingRowsCache = null;
window.currentHoldingAccount = "ALL";
window.holdingsPriceData = null;
window.holdingsPriceLoading = false;

export function isHoldingDateColumn(col) {
  return /date/i.test(String(col || ""));
}
export function normalizeHoldingDateValue(v) {
  const raw = String(v ?? "").trim();
  if (!raw) return "";
  let m = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) {
    const y = +m[1],
      mo = +m[2],
      d = +m[3];
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31)
      return `${String(y).padStart(4, "0")}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  m = raw.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2}|\d{4})$/);
  if (m) {
    let mo = +m[1],
      d = +m[2],
      y = +m[3];
    if (y < 100) y += y >= 70 ? 1900 : 2000;
    if (mo >= 1 && mo <= 12 && d >= 1 && d <= 31)
      return `${String(y).padStart(4, "0")}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  }
  return raw;
}
export function ensureHoldingRows() {
  if (window.holdingRowsCache) return window.holdingRowsCache;
  const lines = String(window.holdingsText || "")
    .split(/\r?\n/)
    .filter((x) => x.trim());
  const parsed = lines.map(parseCsvLine);
  const header = (
    parsed[0] || [
      "account",
      "symbol",
      "purchase_date",
      "shares",
      "purchase_price",
      "lot_type",
      "note",
    ]
  ).map((x) => String(x || "").trim());
  const data = (parsed.length > 1 ? parsed.slice(1) : []).map((r) => {
    const o = {};
    header.forEach((h, i) => {
      let v = r[i] ?? "";
      if (isHoldingDateColumn(h)) v = normalizeHoldingDateValue(v);
      else v = String(v).trim();
      o[h] = v;
    });
    return o;
  });
  window.holdingRowsCache = { header, data };
  return window.holdingRowsCache;
}
export function serializeHoldings() {
  const h = ensureHoldingRows();
  const lines = [h.header.map(csvEscape).join(",")];
  h.data.forEach((r) =>
    lines.push(h.header.map((col) => csvEscape(r[col] ?? "")).join(",")),
  );
  window.holdingsText = lines.join("\n") + "\n";
  return window.holdingsText;
}
export function markHoldingsDirty() {
  serializeHoldings();
  window.holdingsChanged = true;
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
  scheduleStatusUpdate();
}
export function holdingAccounts() {
  const h = ensureHoldingRows();
  return [
    ...new Set(
      h.data.map((r) => String(r.account || "").trim()).filter(Boolean),
    ),
  ].sort();
}
// Display-only: turn an internal account key like "Member_1_401k" into the
// person's nickname form ("Matt's 401k"). The stored account value stays the
// internal key (it is a data join key for pricing, YTD mapping, etc.); only
// the label shown to the user changes. Non-member accounts pass through as-is.
export function updateHolding(i, col, val) {
  ensureHoldingRows().data[i][col] = val;
  markHoldingsDirty();
}
export function addHoldingLot(account = "") {
  const h = ensureHoldingRows();
  if (!account || account === "ALL")
    account =
      window.currentHoldingAccount !== "ALL"
        ? window.currentHoldingAccount
        : holdingAccounts()[0] || "New_Account";
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  row.account = account;
  row.symbol = "";
  row.purchase_date = "";
  row.shares = "";
  row.purchase_price = "";
  row.lot_type = "buy";
  h.data.push(row);
  window.currentHoldingAccount = account;
  markHoldingsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(
      `.lot-table tr[data-hidx="${h.data.length - 1}"] input[data-hcol="symbol"]`,
    );
    if (f) f.focus();
  }, 0);
}
export async function addHoldingAccount() {
  const name = await showInAppPrompt("New account name:", "", {
    title: "Add Account",
    placeholder: "e.g. Fidelity IRA",
  });
  if (!name) return;
  window.currentHoldingAccount = name.trim();
  addHoldingLot(window.currentHoldingAccount);
}
export async function deleteHoldingLot(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Lot",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ensureHoldingRows().data.splice(i, 1);
  markHoldingsDirty();
  renderMain();
}
export async function deleteHoldingAccount() {
  if (window.currentHoldingAccount === "ALL") {
    showMessage("Choose an account first.", "warn");
    return;
  }
  if (
    !(await showInAppConfirm(
      "All lots in " +
        accountDisplayLabel(window.currentHoldingAccount) +
        " will be permanently removed.",
      {
        title: "Delete Account",
        confirmLabel: "Delete All Lots",
        variant: "danger",
      },
    ))
  )
    return;
  const h = ensureHoldingRows();
  h.data = h.data.filter(
    (r) => String(r.account || "") !== window.currentHoldingAccount,
  );
  window.currentHoldingAccount = "ALL";
  markHoldingsDirty();
  renderMain();
}
export function setHoldingAccount(v) {
  window.currentHoldingAccount = v;
  renderMain();
}
export function holdingsImportPreviewMessage(out) {
  const d = out.date_range || {},
    dup = out.duplicate_candidates || {},
    acct = out.account_summary || {},
    sym = out.symbol_summary || {},
    dq = out.data_quality || {};
  const lines = [
    "Review holdings import preview before the table is replaced:",
    "",
    `Rows in file: ${out.received || 0}`,
    `Current rows: ${out.current_rows || 0}`,
    `Rows that would be staged: ${out.rows_added || 0}`,
    `Rows that would be replaced: ${out.rows_replaced || 0}`,
    `Total rows after staging: ${out.total_after || 0}`,
    `Purchase date range: ${d.earliest || "—"} through ${d.latest || "—"}`,
    `Duplicate candidates: ${dup.total || 0}`,
    `Estimated cost basis in file: ${ytdMoney(out.estimated_cost_basis)}`,
  ];
  if ((acct.new_accounts || []).length)
    lines.push(`New holding accounts: ${importPreviewList(acct.new_accounts)}`);
  if ((sym.symbols_not_in_security_master || []).length)
    lines.push(
      `Symbols not in security master: ${importPreviewList(sym.symbols_not_in_security_master)}`,
    );
  if (
    dq.missing_account_rows ||
    dq.missing_symbol_rows ||
    dq.invalid_share_rows ||
    dq.invalid_price_rows ||
    dq.unparseable_date_rows
  )
    lines.push(
      `Data quality flags: missing account ${dq.missing_account_rows || 0}, missing symbol ${dq.missing_symbol_rows || 0}, invalid shares ${dq.invalid_share_rows || 0}, invalid price ${dq.invalid_price_rows || 0}, date warnings ${dq.unparseable_date_rows || 0}`,
    );
  (out.warnings || []).forEach((w) => lines.push("Warning: " + w));
  lines.push(
    "",
    "Staged lots are held in the browser — use Save Changes to write them to disk.",
  );
  return lines.join("\n");
}
export async function handleHoldingsCsvImport(input) {
  try {
    const file = input && input.files && input.files[0];
    if (!file) return;
    const text = await file.text();
    const preview = await api("/api/holdings/preview", {
      method: "POST",
      body: JSON.stringify({ mode: "replace", csv_text: text }),
    });
    if (
      !(await showInAppConfirm(holdingsImportPreviewMessage(preview), {
        title: "Confirm Holdings Import",
        confirmLabel: "Stage Import",
        variant: "warn",
      }))
    )
      return;
    window.holdingsText = text;
    window.holdingRowsCache = null;
    window.currentHoldingAccount = "ALL";
    markHoldingsDirty();
    noteSpecialSessionChange(
      "Investment holdings import staged",
      `CSV import preview accepted: ${preview.received || 0} lots staged.`,
    );
    renderMain();
    showMessage(
      `Holdings import staged: ${preview.received || 0} lots. Save Changes to persist.`,
    );
  } catch (e) {
    showMessage("Error previewing holdings import: " + e.message, "error");
  } finally {
    if (input) input.value = "";
  }
}

export function renderUserPricingSymbolTester() {
  return `<div id="userPricingSymbolTester" class="section-note" data-help-section="holdings.pricing_tester"><b>Single-symbol live pricing tester:</b> ${(window.RPHelp?.sectionButtonHtml("holdings.pricing_tester") || "")} <div class="row" style="margin-top:8px"><input id="userPricingTestSymbol" placeholder="Ticker, e.g. VTI" style="max-width:210px;text-transform:uppercase" onkeydown='event.key==="Enter"&&runUserLivePriceSymbolTest()'><button class="btn primary" type="button" onclick="runUserLivePriceSymbolTest()">Test live quote</button><span id="userPricingTestStatus" class="small"></span></div><div id="userPricingTestResult" style="margin-top:10px"></div></div>`;
}
export function fmtUserPriceDiagnostic(v) {
  const n = Number(v);
  return Number.isFinite(n) && n > 0
    ? "$" +
        n.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 4,
        })
    : esc(v ?? "");
}
export function renderUserJsonBlock(obj) {
  return `<pre class="code" style="display:block;white-space:pre-wrap;max-height:220px;overflow:auto;margin:6px 0">${esc(JSON.stringify(obj, null, 2))}</pre>`;
}
export function renderUserProviderAttempt(a) {
  return `<div class="impact-card" style="margin:8px 0"><b>${esc(a.transport || "transport")}</b> · ${a.ok ? "ok" : "failed"} ${a.status_code ? "· HTTP " + esc(a.status_code) : ""} · ${esc(a.elapsed_ms ?? "")} ms<h4>Command sent</h4>${renderUserJsonBlock(a.command || {})}${a.cause ? `<h4>Failure cause</h4><p class="small">${esc(a.cause)}</p>` : ""}${a.exception ? `<h4>Exception</h4><p class="small">${esc(a.exception)}</p>` : ""}${a.response_preview ? `<h4>Response preview</h4><pre class="code" style="display:block;white-space:pre-wrap;max-height:160px;overflow:auto">${esc(a.response_preview)}</pre>` : ""}</div>`;
}
export function renderUserProviderStep(s) {
  const ok = s.outcome === "success";
  return `<details><summary><b>${esc(s.provider || "provider")} · ${esc(s.endpoint || "endpoint")}</b> — ${esc(s.outcome || "unknown")}${s.parsed_price ? " · " + fmtUserPriceDiagnostic(s.parsed_price) : ""}</summary><div style="padding:8px"><p class="small">${esc(s.parse_note || s.cause || "")}</p>${(s.attempts || []).map(renderUserProviderAttempt).join("") || `<p class="small">${esc(s.cause || "No command was sent for this provider.")}</p>`}</div></details>`;
}
export function renderUserPricingTrace(r) {
  return `<div class="impact-card"><b>${esc(r.symbol || "")}</b> — ${esc(r.summary || "No summary")}<div class="mini-grid"><div><b>Selected provider</b><span>${esc(r.selected_provider || "none")}</span></div><div><b>Selected price</b><span>${r.selected_price ? fmtUserPriceDiagnostic(r.selected_price) : "—"}</span></div><div><b>Order</b><span>${esc((r.provider_order || []).join(" → "))}</span></div></div></div><details><summary><b>Runtime and key diagnostics</b></summary>${renderUserJsonBlock({ generated_at_utc: r.generated_at_utc, config_backend: r.config_backend, timeout_seconds: r.timeout_seconds, max_retries: r.max_retries, requests_available: r.requests_available, effective_api_key_sources: r.effective_api_key_sources, proxy_environment_keys: r.proxy_environment_keys, cache_record: r.cache_record })}</details><h4>Provider command / response trace</h4>${(r.steps || []).map(renderUserProviderStep).join("")}`;
}
export async function pollUserLivePriceSymbolJob(jobId, status, result) {
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
    if (result) result.innerHTML = renderUserPricingTrace(trace);
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
export async function runUserLivePriceSymbolTest() {
  const input = document.getElementById("userPricingTestSymbol");
  const status = document.getElementById("userPricingTestStatus");
  const result = document.getElementById("userPricingTestResult");
  const symbol = (input?.value || "").trim().toUpperCase();
  if (!symbol) {
    showMessage("Enter one ticker symbol first", "error");
    return;
  }
  if (status) status.textContent = "Starting diagnostic...";
  if (result)
    result.innerHTML = "";
  try {
    const started = await api("/api/prices/test-symbol/start", {
      method: "POST",
      body: JSON.stringify({ symbol }),
      timeoutMs: 9000,
    });
    if (status) status.textContent = "Calling live providers...";
    const out = await pollUserLivePriceSymbolJob(
      started.job_id,
      status,
      result,
    );
    const liveOk = !!(
      out.live_pricing_working ||
      (out.result && out.result.success)
    );
    showMessage(
      liveOk
        ? "Live pricing tester found a quote"
        : "Live pricing tester completed with failures",
      liveOk ? "success" : "warn",
    );
  } catch (e) {
    const detail = String((e && e.message) || e || "Unknown error");
    if (result)
      result.innerHTML = `<div class="section-note warn" data-kind="warn" title="Endpoint: /api/prices/test-symbol/start"><b>Pricing tester could not reach the local API.</b><br>${esc(detail)}<br>Restart the app and check the status shows Ready.</div>`;
    if (status) status.textContent = "Error";
    showMessage("Pricing tester error: " + detail, "error");
  }
}
// #355: display order is always account, then symbol, then purchase date
// (ascending). Blank values sort last so a freshly added lot stays at the end
// of its group until it is filled in. Stored row order is never changed.
function holdingSortPart(v) {
  const s = String(v || "").trim().toLowerCase();
  return [s === "" ? 1 : 0, s];
}
export function compareHoldingLots(a, b) {
  for (const col of ["account", "symbol", "purchase_date"]) {
    const [ab, av] = holdingSortPart(a.r[col]);
    const [bb, bv] = holdingSortPart(b.r[col]);
    if (ab !== bb) return ab - bb;
    if (av !== bv) return av < bv ? -1 : 1;
  }
  return a.i - b.i;
}
export function insertHoldingLotLike(i) {
  const h = ensureHoldingRows();
  const src = h.data[i] || {};
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  row.account = src.account || "";
  row.symbol = src.symbol || "";
  row.lot_type = src.lot_type || "buy";
  h.data.push(row);
  window.focusHoldingIdx = h.data.length - 1;
  markHoldingsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(
      `.lot-table tr[data-hidx="${window.focusHoldingIdx}"] input[data-hcol="purchase_date"]`,
    );
    if (f) f.focus();
  }, 0);
}
// Accounts whose holdings the transaction log writes (schema v22). Their rows are read-only here: edit them in the log.
window.managedHoldingAccounts = window.managedHoldingAccounts || null;
export function isManagedHoldingAccount(account) {
  const key = String(account || "").trim().toLowerCase();
  return (window.managedHoldingAccounts || []).some((a) => String(a).trim().toLowerCase() === key);
}
// Accounts whose only holding is one CASH lot are checking/savings accounts: their page is Checking & Savings.
export function cashOnlyAccounts(rows) {
  const lots = new Map();
  for (const r of rows || []) {
    const k = String(r.account || "").trim().toLowerCase();
    if (k) lots.set(k, [...(lots.get(k) || []), String(r.symbol || "").trim().toUpperCase()]);
  }
  return new Set([...lots].filter(([, syms]) => syms.length === 1 && syms[0] === "CASH").map(([k]) => k));
}
export async function loadManagedHoldingAccounts() {
  try {
    const out = await api("/api/transactions/accounts");
    window.managedHoldingAccounts = (out && out.managed) || [];
  } catch (e) {
    window.managedHoldingAccounts = [];
  }
  if (window.activeStep === "holdings" && typeof renderMain === "function") renderMain();
}

// Investment accounts keep one cash balance each. The securities lots come from the transaction log, so the only thing
// edited here is the CASH lot: its balance (shares x $1) and the date the balance is as of.
export function isCashHoldingLot(r) {
  return String(r.symbol || "").trim().toUpperCase() === "CASH";
}
export function addHoldingCash(account) {
  const h = ensureHoldingRows();
  const row = {};
  h.header.forEach((c) => (row[c] = ""));
  Object.assign(row, { account, symbol: "CASH", purchase_date: "", shares: "", purchase_price: "1", lot_type: "buy" });
  h.data.push(row);
  markHoldingsDirty();
  renderMain();
  setTimeout(() => {
    const f = document.querySelector(`.lot-table tr[data-hidx="${h.data.length - 1}"] input[data-hcol="shares"]`);
    if (f) f.focus();
  }, 0);
}

export function renderHoldings() {
  const h = ensureHoldingRows();
  // Checking & Savings accounts have their own page; keep them off this one.
  const hiddenCash = cashOnlyAccounts(h.data);
  const isHiddenCash = (a) => hiddenCash.has(String(a || "").trim().toLowerCase());
  const accounts = holdingAccounts().filter((a) => !isHiddenCash(a));
  const cashRows = h.data
    .map((r, i) => ({ r, i }))
    .filter((x) => !isHiddenCash(x.r.account) && isCashHoldingLot(x.r))
    .filter((x) => window.currentHoldingAccount === "ALL" || String(x.r.account || "") === window.currentHoldingAccount)
    .sort(compareHoldingLots);
  const shown = accounts.filter((a) => window.currentHoldingAccount === "ALL" || a === window.currentHoldingAccount);
  const missing = shown.filter((a) => !cashRows.some((x) => String(x.r.account || "") === a));
  // Ticket 374: the grouped, collapsible view leads; the cash balances sit under "Edit cash in investment accounts".
  const tree = typeof window.renderHoldingsTree === "function"
    ? window.renderHoldingsTree(h.data.filter((r) => !isHiddenCash(r.account)), accountDisplayLabel)
    : "";
  const cashInput = (i, col, type, value, cls) =>
    `<input class="${cls}" data-hcol="${col}" type="${type}" value="${esc(value)}" oninput="updateHolding(${i},'${col}',${col === "shares" ? "currencyRaw(this.value)" : "this.value"})" ${col === "shares" ? `onfocus="this.value=currencyRaw(this.value);this.select&&this.select()" onblur="this.value=currencyDisplay(this.value,2)"` : ""}>`;
  let html = `${tree}<div class="holdings" data-help-section="holdings.plan_holdings"><details${tree && !window.holdingsEditOpen ? "" : " open"} ontoggle="window.holdingsEditOpen=this.open"><summary>Edit cash in investment accounts ${(window.RPHelp?.sectionButtonHtml("holdings.plan_holdings") || "")}</summary>`
    + `<input type="file" id="holdingsImportInput" accept=".csv,text/csv" style="display:none" onchange="handleHoldingsCsvImport(this)"><div class="table-actions"><select data-focus-key="holdings:account-select" aria-label="Show account" onchange="setHoldingAccount(this.value)"><option value="ALL" ${window.currentHoldingAccount === "ALL" ? "selected" : ""}>All accounts</option>${accounts.map((a) => `<option value="${esc(a)}" ${window.currentHoldingAccount === a ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("")}</select><button class="btn" type="button" data-requires-app="1" onclick="document.getElementById('holdingsImportInput').click()">Preview &amp; replace CSV</button></div><div class="lot-table-wrap"><table class="lot-table"><thead><tr><th>Account</th><th>Cash balance</th><th>As of</th><th></th></tr></thead><tbody>`;
  cashRows.forEach(({ r, i }) => {
    html += `<tr data-hidx="${i}"><td data-label="Account">${esc(accountDisplayLabel(r.account))}</td>`
      + `<td data-label="Cash balance">${cashInput(i, "shares", "text", currencyDisplay(r.shares || "", 2), "tiny")}</td>`
      + `<td data-label="As of">${cashInput(i, "purchase_date", "date", r.purchase_date || "", "")}</td>`
      + `<td data-label="Actions">${deleteIconBtn(`deleteHoldingLot(${i})`)}</td></tr>`;
  });
  missing.forEach((a) => {
    html += `<tr><td data-label="Account">${esc(accountDisplayLabel(a))}</td><td colspan="3"><button class="btn" type="button" onclick="addHoldingCash('${esc(a).replace(/'/g, "\'")}')">Add cash balance</button></td></tr>`;
  });
  html += `</tbody></table></div></details></div>`;
  return html;
}

// Last build's price per symbol; the file is "pricing_diagnostics" (was ".json" before build results moved into the plan file).
export function pricesFromDiagnostics(out) {
  const f = ((out && out.files) || []).find((x) => /^pricing_diagnostics(\.json)?$/.test(x.name));
  return (f && f.json && f.json.prices) || {};
}
// The date the last build's prices are as of: the oldest per-symbol quote date, else the overall cache date.
export function priceAsOfFromDiagnostics(out) {
  const f = ((out && out.files) || []).find((x) => /^pricing_diagnostics(\.json)?$/.test(x.name));
  const j = (f && f.json) || {};
  const dates = Object.values(j.cache_as_of_by_symbol_local || j.cache_as_of_by_symbol || {}).map((v) => String(v || "").slice(0, 10)).filter(Boolean).sort();
  return dates[0] || String(j.cache_as_of_local || j.cache_as_of_utc || "").slice(0, 10);
}
export async function loadHoldingsPriceData() {
  if (window.holdingsPriceLoading || window.holdingsPriceData) return;
  window.holdingsPriceLoading = true;
  try {
    const out = await api("/api/admin/diagnostics");
    window.holdingsPriceData = pricesFromDiagnostics(out);
    window.holdingsPriceAsOf = priceAsOfFromDiagnostics(out);
  } catch (e) {
    window.holdingsPriceData = {};
  }
  window.holdingsPriceLoading = false;
  renderMain();
}
export function holdingsCurrentPrice(symbol) {
  const sym = String(symbol || "")
    .trim()
    .toUpperCase();
  if (sym === "CASH") return 1;
  if (
    window.holdingsPriceData &&
    Object.prototype.hasOwnProperty.call(window.holdingsPriceData, sym)
  ) {
    const n = Number(window.holdingsPriceData[sym]);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
// Current value uses the last cached/live price; falls back to cost basis
// (purchase_price) only when no price is available for the symbol.
export function holdingLotCurrentValue(h) {
  const shares = Number(h.shares || 0);
  const live = holdingsCurrentPrice(h.symbol);
  const price = live !== null ? live : Number(h.purchase_price || 0);
  return { price: price, value: shares * price, isEstimate: live === null };
}

export async function saveHoldings() {
  if (!window.holdingsChanged) return { updated: 0 };
  const content = serializeHoldings();
  const res = await fetch(apiUrl("/api/holdings"), {
    method: "POST",
    headers: { "Content-Type": "text/plain", "X-CSRF-Token": window.csrfToken || "" },
    body: content,
  });
  if (!res.ok) throw new Error(await res.text());
  window.holdingsText = content;
  window.holdingsChanged = false;
  return { updated: 1 };
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals (event-handler dispatch, save/load flows), and this file's
// own rendered HTML uses inline onclick="addHoldingLot()"-style handlers,
// which always resolve through window regardless of module scoping. New code
// should prefer `import` from this module; this bridge exists only for
// callers that can't move to import in the same pass.
Object.assign(window, {
  isHoldingDateColumn,
  normalizeHoldingDateValue,
  ensureHoldingRows,
  cashOnlyAccounts,
  serializeHoldings,
  markHoldingsDirty,
  holdingAccounts,
  updateHolding,
  addHoldingLot,
  insertHoldingLotLike,
  addHoldingAccount,
  deleteHoldingLot,
  deleteHoldingAccount,
  setHoldingAccount,
  holdingsImportPreviewMessage,
  handleHoldingsCsvImport,
  renderUserPricingSymbolTester,
  fmtUserPriceDiagnostic,
  renderUserJsonBlock,
  renderUserProviderAttempt,
  renderUserProviderStep,
  renderUserPricingTrace,
  pollUserLivePriceSymbolJob,
  runUserLivePriceSymbolTest,
  renderHoldings,
  addHoldingCash,
  isCashHoldingLot,
  isManagedHoldingAccount,
  loadManagedHoldingAccounts,
  loadHoldingsPriceData,
  priceAsOfFromDiagnostics,
  holdingsCurrentPrice,
  holdingLotCurrentValue,
  saveHoldings,
  
});
