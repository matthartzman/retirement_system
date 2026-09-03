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
    const f = document.querySelector('.lot-table input[data-hcol="symbol"]');
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
  return `<div id="userPricingSymbolTester" class="section-note"><b>Single-symbol live pricing tester:</b> Type one ticker to see every live pricing command and response trace without relying on the workbook build. <div class="row" style="margin-top:8px"><input id="userPricingTestSymbol" placeholder="Ticker, e.g. VTI" style="max-width:210px;text-transform:uppercase" onkeydown="if(event.key==='Enter')runUserLivePriceSymbolTest()"><button class="btn primary" type="button" onclick="runUserLivePriceSymbolTest()">Test live quote</button><span id="userPricingTestStatus" class="small"></span></div><div id="userPricingTestResult" style="margin-top:10px"></div></div>`;
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
    result.innerHTML =
      '<p class="small">Starting local diagnostic job. Provider commands and responses will appear as each service returns.</p>';
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
      result.innerHTML = `<div class="section-note warn"><b>Pricing tester could not reach the local API.</b><br>${esc(detail)}<br><br>Endpoint: <code>/api/prices/test-symbol/start</code>. If the browser says "Failed to fetch", restart the app and confirm the status indicator shows Ready.</div>`;
    if (status) status.textContent = "Error";
    showMessage("Pricing tester error: " + detail, "error");
  }
}
export function renderHoldings() {
  const h = ensureHoldingRows();
  const accounts = holdingAccounts();
  const visible = h.data
    .map((r, i) => ({ r, i }))
    .filter(
      (x) =>
        window.currentHoldingAccount === "ALL" ||
        String(x.r.account || "") === window.currentHoldingAccount,
    );
  const cols = h.header.length
    ? h.header
    : [
        "account",
        "symbol",
        "purchase_date",
        "shares",
        "purchase_price",
        "lot_type",
        "note",
      ];
  // 6.3 (system review 2026-08-04, finding `ui-inconsistent-wide-table-pattern`):
  // pinned account/symbol columns + a collapsible "note" column, matching the
  // pattern applied to the YTD transactions table in dashboard.js. Kept on
  // window (not module-local) because the toggle button's onclick attribute
  // runs in global scope, not this module's scope -- see the file header.
  const colsCollapsed = window.holdingsColsCollapsed !== false;
  let html = `<div class="holdings"><h3 class="group-title">Plan Holdings</h3><div class="section-note">Enter investment holdings by account and lot. A lot is a separate purchase, reinvestment, or cash position. Use CASH with price 1 for cash balances.</div><div class="section-note small"><b>CSV import columns:</b> <code>account, symbol, purchase_date, shares, purchase_price, lot_type, note</code> — date as YYYY-MM-DD, lot_type as <code>standard</code>, <code>reinvestment</code>, or <code>cash</code>. Download a template from your broker CSV export or use Export CSV backup in Settings first.</div>${renderUserPricingSymbolTester()}<input type="file" id="holdingsImportInput" accept=".csv,text/csv" style="display:none" onchange="handleHoldingsCsvImport(this)"><div class="table-actions"><select data-focus-key="holdings:account-select" onchange="setHoldingAccount(this.value)"><option value="ALL" ${window.currentHoldingAccount === "ALL" ? "selected" : ""}>All accounts</option>${accounts.map((a) => `<option value="${esc(a)}" ${window.currentHoldingAccount === a ? "selected" : ""}>${esc(accountDisplayLabel(a))}</option>`).join("")}</select><button class="btn" onclick="addHoldingLot()">Add Lot</button><button class="btn" onclick="addHoldingAccount()">Add Account</button><button class="btn" type="button" data-requires-app="1" onclick="document.getElementById('holdingsImportInput').click()">Preview &amp; replace CSV</button><button class="btn danger" ${window.currentHoldingAccount === "ALL" ? "disabled" : ""} onclick="deleteHoldingAccount()">Delete Account</button><button class="btn col-group-toggle" type="button" onclick="window.holdingsColsCollapsed=${colsCollapsed ? "false" : "true"};renderMain()">${colsCollapsed ? "Show note column" : "Hide note column"}</button></div><div class="lot-table-wrap pinned-col${colsCollapsed ? " cols-collapsed" : ""}"><table class="lot-table"><thead><tr>${cols.map((c) => `<th${c === "note" ? ' data-col-group="extra"' : ""}>${esc(humanLabel(c))}</th>`).join("")}<th>Actions</th></tr></thead><tbody>`;
  visible.forEach(({ r, i }) => {
    html +=
      "<tr>" +
      cols
        .map((c) => {
          const isDate = c.includes("date");
          const isPrice =
            norm(c).includes("price") ||
            norm(c).includes("cost") ||
            norm(c).includes("value");
          const isAccount = c === "account";
          const type = isDate ? "date" : "text";
          const cls = ["shares", "purchase_price"].includes(c) ? "tiny" : "";
          const display = isPrice
            ? currencyDisplay(r[c] || "", 4)
            : isAccount
              ? accountDisplayLabel(r[c] || "")
              : r[c] || "";
          const focus = isPrice
            ? `onfocus="showStepHelp('holdings');this.value=currencyRaw(this.value);this.select&&this.select()"`
            : isAccount
              ? `onfocus="showStepHelp('holdings');this.value=ensureHoldingRows().data[${i}].account||'';this.select&&this.select()"`
              : `onfocus="showStepHelp('holdings')"`;
          const input = isPrice
            ? `oninput="updateHolding(${i},'${esc(c)}',currencyRaw(this.value))" onblur="this.value=currencyDisplay(this.value,4)"`
            : isAccount
              ? `oninput="updateHolding(${i},'account',this.value)" onblur="this.value=accountDisplayLabel(this.value)"`
              : `oninput="updateHolding(${i},'${esc(c)}',this.value)"`;
          return `<td data-label="${esc(humanLabel(c))}"${c === "note" ? ' data-col-group="extra"' : ""}><input class="${cls}" data-hcol="${esc(c)}" type="${type}" value="${esc(display)}" ${input} ${focus}></td>`;
        })
        .join("") +
      `<td data-label="Actions">${deleteIconBtn(`deleteHoldingLot(${i})`)}</td></tr>`;
  });
  html += `</tbody></table></div>`;
  // #235: moved here from Economic & Tax Assumptions -- dividend reinvestment
  // is a per-holding-account behavior, not a system-wide economic assumption.
  const divRows = rows.filter(
    (r) =>
      isEditable(r) &&
      r.section === "Economic Assumptions" &&
      ["reinvest_dividends_default", "cash_yield_rate"].includes(norm(r.label)),
  );
  if (divRows.length)
    html += `<details><summary>Dividend Reinvestment</summary><div class="field-list">${divRows.map(fieldHtml).join("")}</div></details>`;
  html += `</div>`;
  return html;
}

// Last cached/live price per symbol, from the most recent build's pricing_diagnostics.json.
// Used to show current market value in Plan Data Review instead of cost basis.
export async function loadHoldingsPriceData() {
  if (window.holdingsPriceLoading || window.holdingsPriceData) return;
  window.holdingsPriceLoading = true;
  try {
    const out = await api("/api/admin/diagnostics");
    const f = ((out && out.files) || []).find(function (x) {
      return x.name === "pricing_diagnostics.json";
    });
    window.holdingsPriceData = (f && f.json && f.json.prices) || {};
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
    headers: { "Content-Type": "text/csv" },
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
  serializeHoldings,
  markHoldingsDirty,
  holdingAccounts,
  updateHolding,
  addHoldingLot,
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
  loadHoldingsPriceData,
  holdingsCurrentPrice,
  holdingLotCurrentValue,
  saveHoldings,
  
});
