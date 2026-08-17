// Extracted from dashboard.js by tools/js_codemod/extract_module.mjs.

export function normalizeYtdActualsPeriod(v) {
  return String(v || "").toLowerCase() === "last_year" ? "last_year" : "ytd";
}

export function readYtdActualsPeriod() {
  try {
    return normalizeYtdActualsPeriod(
      localStorage.getItem(YTD_ACTUALS_PERIOD_LS_KEY) || "ytd",
    );
  } catch (_e) {
    return "ytd";
  }
}

export function setYtdActualsPeriod(period) {
  const next = normalizeYtdActualsPeriod(period);
  if (next === ytdActualsPeriod) return;
  ytdActualsPeriod = next;
  try {
    localStorage.setItem(YTD_ACTUALS_PERIOD_LS_KEY, ytdActualsPeriod);
  } catch (_e) {}
  loadYtdStatus().then(() => renderMain());
}

export function ytdActualsPeriodToggleHtml(idSuffix) {
  const id = "ytdActualsPeriod_" + String(idSuffix || "default");
  const isLastYear = ytdActualsPeriod === "last_year";
  return (
    `<div class="ytd-actuals-period-toggle segmented-toggle" role="radiogroup" aria-label="Actuals period">` +
    `<button type="button" class="seg-btn${isLastYear ? "" : " active"}" role="radio" aria-checked="${!isLastYear}" onclick="setYtdActualsPeriod('ytd')">Year-to-date</button>` +
    `<button type="button" class="seg-btn${isLastYear ? " active" : ""}" role="radio" aria-checked="${isLastYear}" onclick="setYtdActualsPeriod('last_year')">Last year</button>` +
    `</div>`
  );
}

export function cacheChart(html, title) {
  var id = "cc" + ++chartCacheSeq;
  chartCache[id] = { html: html, title: title || "" };
  return id;
}

export function openCachedChart(id) {
  var c = chartCache[id];
  if (!c) return;
  var modal = document.getElementById("chartModal");
  if (!modal) return;
  var titleEl = document.getElementById("chartModalTitle");
  var bodyEl = document.getElementById("chartModalBody");
  if (titleEl) titleEl.textContent = c.title;
  if (bodyEl) bodyEl.innerHTML = c.html;
  modal.style.display = "flex";
  document.body.classList.add("chart-modal-open");
}

export function csvEscape(v) {
  v = String(v ?? "");
  return /[",\n\r]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
}

export function clientDataKey(row) {
  return [
    String(row?.[0] || "").trim(),
    String(row?.[1] || "").trim(),
    String(row?.[2] || "").trim(),
  ].join("\x1f");
}

export function parseCsvTable(text) {
  const lines = String(text || "").split(/\r?\n/);
  const rows = [];
  let cur = "",
    q = false,
    row = [];
  function pushCell() {
    row.push(cur);
    cur = "";
  }
  function pushRow() {
    rows.push(row);
    row = [];
  }
  for (let li = 0; li < lines.length; li++) {
    const line = lines[li];
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (q && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else q = !q;
      } else if (ch === "," && !q) {
        pushCell();
      } else cur += ch;
    }
    if (q) {
      cur += "\n";
    } else {
      pushCell();
      pushRow();
      cur = "";
    }
  }
  if (cur || row.length) {
    pushCell();
    pushRow();
  }
  while (
    rows.length &&
    rows[rows.length - 1].every((c) => !String(c || "").trim())
  )
    rows.pop();
  return rows;
}

export function serializeCsvTable(rows) {
  return rows.map((r) => r.map(csvEscape).join(",")).join("\n") + "\n";
}

export function mergeProtectedClientData(primary, fallback) {
  if (!fallback) return primary;
  const rows = parseCsvTable(primary);
  const fallbackRows = parseCsvTable(fallback);
  const keep = {};
  fallbackRows.forEach((r) => {
    const k = clientDataKey(r);
    if (PROTECTED_CLIENT_DATA_KEYS.has(k) && String(r[3] || "").trim())
      keep[k] = r[3];
  });
  let changed = false;
  rows.forEach((r) => {
    const k = clientDataKey(r);
    if (
      PROTECTED_CLIENT_DATA_KEYS.has(k) &&
      keep[k] &&
      !String(r[3] || "").trim()
    ) {
      while (r.length < 4) r.push("");
      r[3] = keep[k];
      changed = true;
    }
  });
  return changed ? serializeCsvTable(rows) : primary;
}

export function serializeLiabilities() {
  const h = ensureLiabilityRows();
  const lines = [h.header.map(csvEscape).join(",")];
  h.data.forEach((r) =>
    lines.push(h.header.map((col) => csvEscape(r[col] ?? "")).join(",")),
  );
  liabilitiesText = lines.join("\n") + "\n";
  return liabilitiesText;
}

export async function saveLiabilities() {
  if (!liabilitiesChanged) return { updated: 0 };
  const content = serializeLiabilities();
  const res = await fetch(apiUrl("/api/liabilities"), {
    method: "POST",
    headers: { "Content-Type": "text/csv" },
    body: content,
  });
  if (!res.ok) throw new Error(await res.text());
  liabilitiesText = content;
  liabilitiesChanged = false;
  return { updated: 1 };
}

export function ytdMoney(v) {
  if (v === null || v === undefined || v === "") return "Not available";
  const n = Number(String(v).replace(/[$,]/g, ""));
  if (!Number.isFinite(n)) return "Not available";
  return n.toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function ytdPct(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0.00%";
  return (n * 100).toFixed(2) + "%";
}

export function updateYtdTxnAmount(i, input) {
  const raw = ytdRawMoney(input?.value);
  if (input)
    input.classList.toggle("ytd-negative-amount", ytdAmountIsNegative(raw));
  updateYtdTxn(i, "Amount", raw);
}

export function focusYtdTxnAmount(input) {
  if (input) input.value = ytdRawMoney(input.value);
}

export function blurYtdTxnAmount(i, input) {
  const raw = ytdRawMoney(input?.value);
  if (input) {
    input.value = ytdTxnMoneyDisplay(raw);
    input.classList.toggle("ytd-negative-amount", ytdAmountIsNegative(raw));
  }
  updateYtdTxn(i, "Amount", raw);
}

export function addYtdTxn() {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  ytdData.transactions = ytdData.transactions || [];
  ytdData.transactions.unshift({
    Date: new Date().toISOString().slice(0, 10),
    Merchant: ytdFirstExistingValue("Merchant"),
    Category: ytdFirstExistingValue("Category"),
    Account: ytdFirstExistingValue("Account"),
    "Original Statement": "Manual",
    Notes: "",
    Amount: "0",
    Tags: "",
    Owner: "",
  });
  markYtdTransactionsDirty();
  renderMain();
}

export async function deleteYtdTxn(i) {
  if (
    !(await showInAppConfirm("This cannot be undone.", {
      title: "Delete Transaction",
      confirmLabel: "Delete",
      variant: "danger",
    }))
  )
    return;
  ytdData.transactions.splice(i, 1);
  markYtdTransactionsDirty();
  renderMain();
}

export async function saveYtdTransactions() {
  try {
    await api("/api/ytd/transactions/bulk", {
      method: "PUT",
      body: JSON.stringify({ transactions: ytdData.transactions || [] }),
    });
    await loadYtdStatus();
    setYtdDirtyButtonStates();
    spendingData = null;
    renderMain();
    showMessage("YTD transactions saved.");
  } catch (e) {
    showMessage("Error saving YTD transactions: " + e.message, "error");
  }
}

export async function downloadYtdTemplate() {
  try {
    const text = await fetchText("/api/ytd/transactions/template");
    await saveGeneratedTextFile("ytd_transactions_template.csv", text, "Transaction template");
  } catch (e) {
    showMessage("Error downloading YTD template: " + e.message, "error");
  }
}

export function importPreviewList(items, limit = 6) {
  items = Array.isArray(items) ? items : [];
  const shown = items.slice(0, limit).join(", ");
  return shown + (items.length > limit ? ` +${items.length - limit} more` : "");
}

export function ytdImportPreviewMessage(out) {
  const d = out.date_range || {},
    dup = out.duplicate_candidates || {},
    acct = out.account_summary || {};
  const lines = [
    "Review transaction import preview before anything is written:",
    "",
    `Mode: ${out.mode || "replace"}`,
    `Rows in file: ${out.received || 0}`,
    `Current-year rows kept: ${out.valid_current_year_rows || 0}`,
    `Rows that would be added: ${out.rows_added || 0}`,
    `Rows that would be replaced: ${out.rows_replaced || 0}`,
    `Rows skipped: ${out.rows_skipped || 0}`,
    `Total rows after import: ${out.total_after || 0}`,
    `Date range: ${d.earliest || "—"} through ${d.latest || "—"}`,
    `Duplicate candidates: ${dup.total || 0}`,
  ];
  if (out.skipped_not_current_year)
    lines.push(
      `Non-current-year rows skipped: ${out.skipped_not_current_year}`,
    );
  if (out.unmapped_category_count)
    lines.push(
      `Unmapped categories: ${importPreviewList(out.unmapped_categories || [])}`,
    );
  if ((acct.new_accounts || []).length)
    lines.push(`New accounts/sources: ${importPreviewList(acct.new_accounts)}`);
  (out.warnings || []).forEach((w) => lines.push("Warning: " + w));
  lines.push("", "Save Changes after importing to persist the transactions.");
  return lines.join("\n");
}

export async function handleYtdTransactionUpload(input) {
  try {
    const file = input && input.files && input.files[0];
    if (!file) return;
    const mode =
      (document.getElementById("ytdUploadMode") || {}).value || "replace";
    const text = await file.text();
    const preview = await api("/api/ytd/transactions/preview", {
      method: "POST",
      body: JSON.stringify({ mode, csv_text: text }),
    });
    if (
      !(await showInAppConfirm(ytdImportPreviewMessage(preview), {
        title: "Confirm Transaction Import",
        confirmLabel: "Import",
        variant: "warn",
      }))
    )
      return;
    const out = await api("/api/ytd/transactions/upload", {
      method: "POST",
      body: JSON.stringify({ mode, csv_text: text }),
    });
    await loadYtdStatus();
    renderMain();
    showMessage(
      `YTD transactions loaded: ${out.added || 0} added, ${out.skipped || 0} skipped (${out.skipped_not_current_year || 0} non-current-year), ${out.total || 0} current-year total.`,
    );
  } catch (e) {
    showMessage("Error uploading transactions: " + e.message, "error");
  } finally {
    if (input) input.value = "";
  }
}

export async function deleteAllYtdTransactions() {
  const txCount =
    ytdData && ytdData.transactions ? ytdData.transactions.length : 0;
  const countLabel = txCount > 0 ? String(txCount) + " " : "all ";
  if (
    !(await showInAppConfirm(
      countLabel +
        "YTD transactions will be permanently deleted. Account setup rows will remain.",
      {
        title: "Delete All Transactions",
        confirmLabel: "Delete All",
        variant: "danger",
      },
    ))
  )
    return;
  try {
    await api("/api/ytd/transactions", {
      method: "DELETE",
      body: JSON.stringify({}),
    });
    await loadYtdStatus();
    renderMain();
    showMessage("All YTD transactions deleted.");
  } catch (e) {
    showMessage("Error deleting YTD transactions: " + e.message, "error");
  }
}

export function ytdFilterOptions(field) {
  const vals = [
    ...new Set(
      (ytdData?.transactions || [])
        .map((r) => String(r[field] || "").trim())
        .filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
  return vals
    .map((v) => `<option value="${esc(v)}">${esc(v)}</option>`)
    .join("");
}

export function ytdFirstExistingValue(field) {
  const vals = ytdExistingValues(field);
  return vals.length ? vals[0] : "";
}

// ytdSelectFieldHtml / ytdExistingDatalistsHtml / commitYtdExistingValue live in
// dashboard_decomp_row_model.js, next to ytdExistingValues. The per-row <select>
// that used to live here (ytdSelectOptions + a <select>-emitting
// ytdSelectFieldHtml) was replaced by one shared <datalist> per field: the old
// shape inlined every distinct value into every row.

export function resetYtdTxnPage() {
  ytdTxPage = 0;
}

export function setYtdTxnPage(page, total) {
  ytdTxPage = Math.max(0, Number(page) || 0);
  renderMain();
}

export function ytdDateAwarePageBoundaries(rows, maxPerPage) {
  // Navigation is by date: never split a single day's transactions across two
  // pages. Pages accumulate rows until they reach maxPerPage, then close at
  // the next day boundary rather than mid-day (a single day busier than
  // maxPerPage becomes its own oversized page, which is expected/rare).
  const n = rows.length;
  if (!n) return [{ start: 0, end: 0 }];
  const pages = [];
  let start = 0;
  for (let i = 1; i <= n; i++) {
    const atEnd = i === n;
    const dayChanged = !atEnd && rows[i].r.Date !== rows[i - 1].r.Date;
    if (atEnd) {
      pages.push({ start, end: i });
      break;
    }
    if (dayChanged && i - start >= maxPerPage) {
      pages.push({ start, end: i });
      start = i;
    }
  }
  return pages;
}

export function ytdTxPageBoundaries(rows) {
  return ytdTxSort.field === "Date"
    ? ytdDateAwarePageBoundaries(rows, YTD_TX_PAGE_SIZE)
    : null;
}

export function ytdShortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  return `${Number(m[2])}/${Number(m[3])}`;
}

export function ytdTxnPager(total, start, end, pages, firstDate, lastDate) {
  pages = Math.max(1, pages || 1);
  if (total <= YTD_TX_PAGE_SIZE && pages <= 1)
    return `<p class="small">Showing ${total} of ${total} matching transactions.</p>`;
  const canShowRange = ytdTxSort.field === "Date" && firstDate && lastDate;
  const rangeLabel = canShowRange
    ? `Showing ${ytdShortDate(firstDate)}–${ytdShortDate(lastDate)}`
    : `Showing ${start + 1}–${end} of ${total} matching transactions`;
  return `<div class="ytd-tx-pager"><span>${rangeLabel} · Page ${ytdTxPage + 1} of ${pages}${ytdTxSort.field === "Date" ? " · pages break on day boundaries" : ""}</span><div class="ytd-tx-pager-buttons"><button class="btn" type="button" ${ytdTxPage <= 0 ? "disabled" : ""} onclick="setYtdTxnPage(0,${total})">First</button><button class="btn" type="button" ${ytdTxPage <= 0 ? "disabled" : ""} onclick="setYtdTxnPage(${ytdTxPage - 1},${total})">Previous</button><button class="btn" type="button" ${ytdTxPage >= pages - 1 ? "disabled" : ""} onclick="setYtdTxnPage(${ytdTxPage + 1},${total})">Next</button><button class="btn" type="button" ${ytdTxPage >= pages - 1 ? "disabled" : ""} onclick="setYtdTxnPage(${pages - 1},${total})">Last</button></div></div>`;
}

export function ytdTxYear(dateStr) {
  const s = String(dateStr || "");
  const iso = /^(\d{4})-\d{2}-\d{2}/.exec(s);
  if (iso) return Number(iso[1]);
  const m = /\d{4}/.exec(s);
  return m ? Number(m[0]) : null;
}

export function ytdPeriodTargetYear() {
  return Number(ytdData?.summary?.current_year) || new Date().getFullYear();
}

export function ytdTxnsForPeriod() {
  const targetYear = ytdPeriodTargetYear();
  return (ytdData?.transactions || [])
    .map((r, i) => ({ r, i }))
    .filter((x) => ytdTxYear(x.r.Date) === targetYear);
}

export function ytdFilteredTxns() {
  let rows = ytdTxnsForPeriod();
  const q = String(ytdTxSearch || "")
    .toLowerCase()
    .trim();
  if (q) {
    rows = rows.filter((x) =>
      Object.values(x.r).join(" ").toLowerCase().includes(q),
    );
  }
  if (ytdCategoryFilter)
    rows = rows.filter((x) => String(x.r.Category || "") === ytdCategoryFilter);
  if (ytdAccountFilter)
    rows = rows.filter((x) => String(x.r.Account || "") === ytdAccountFilter);
  const f = ytdTxSort.field,
    dir = ytdTxSort.dir === "asc" ? 1 : -1;
  rows.sort((a, b) => {
    let av = a.r[f] || "",
      bv = b.r[f] || "";
    if (f === "Amount") {
      av = Number(ytdRawMoney(av)) || 0;
      bv = Number(ytdRawMoney(bv)) || 0;
      return (av - bv) * dir;
    }
    return String(av).localeCompare(String(bv)) * dir;
  });
  return rows;
}

export function setYtdSort(field) {
  if (ytdTxSort.field === field)
    ytdTxSort.dir = ytdTxSort.dir === "asc" ? "desc" : "asc";
  else ytdTxSort = { field, dir: "asc" };
  resetYtdTxnPage();
  renderMain();
}

export function ytdHeader(label, field) {
  const mark =
    ytdTxSort.field === field ? (ytdTxSort.dir === "asc" ? " ▲" : " ▼") : "";
  return `<th><button class="table-sort" type="button" onclick="setYtdSort('${escJs(field)}')">${esc(label)}${mark}</button></th>`;
}

export function ytdSparkline(series, actualKey, forecastKey, opts = null) {
  series = series || [];
  const vals = [];
  series.forEach((p) => {
    if (actualKey && Number.isFinite(Number(p[actualKey])))
      vals.push(Number(p[actualKey]));
    if (forecastKey && Number.isFinite(Number(p[forecastKey])))
      vals.push(Number(p[forecastKey]));
  });
  let min =
    opts && opts.scale === "range" ? Math.min(...vals) : Math.min(0, ...vals);
  let max = Math.max(...vals);
  if (!Number.isFinite(min)) min = 0;
  if (!Number.isFinite(max)) max = 1;
  if (max === min) max = min + 1;
  // Layout: y-axis labels at left (x=0-44), plot area x=50-330, x-axis labels below y=125
  const X0 = 50,
    X1 = 330,
    Y_TOP = 14,
    Y_BOT = 118;
  function px(i) {
    return X0 + i * ((X1 - X0) / Math.max(1, series.length - 1));
  }
  function py(v) {
    return (
      Y_BOT -
      (((Number.isFinite(v) ? v : min) - min) / (max - min)) * (Y_BOT - Y_TOP)
    );
  }
  function points(key) {
    if (!key) return "";
    return series
      .map((p, i) => {
        const v = Number(p[key]);
        return `${px(i).toFixed(1)},${Math.max(Y_TOP, Math.min(Y_BOT, py(v))).toFixed(1)}`;
      })
      .join(" ");
  }
  function fmtY(v) {
    const abs = Math.abs(v);
    if (abs >= 1000000) return "$" + (v / 1000000).toFixed(1) + "M";
    if (abs >= 1000) return "$" + Math.round(v / 1000) + "K";
    return "$" + Math.round(v);
  }
  const midVal = (min + max) / 2;
  const yLabels = `<text class="spark-axis" x="44" y="${(Y_BOT + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(min))}</text><text class="spark-axis" x="44" y="${(py(midVal) + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(midVal))}</text><text class="spark-axis" x="44" y="${(Y_TOP + 4).toFixed(0)}" text-anchor="end">${esc(fmtY(max))}</text>`;
  const xLabels = series
    .map(
      (p, i) =>
        `<text class="spark-axis" x="${px(i).toFixed(0)}" y="136" text-anchor="middle">${esc(p.label || "")}</text>`,
    )
    .join("");
  const forecastLine = forecastKey
    ? `<polyline class="forecast" points="${points(forecastKey)}"/>`
    : "";
  var svgStr = `<svg class="ytd-chart" viewBox="0 0 340 145" role="img" aria-label="YTD chart"><line x1="${X0}" y1="${Y_BOT}" x2="${X1}" y2="${Y_BOT}"/><line x1="${X0}" y1="${Y_TOP}" x2="${X0}" y2="${Y_BOT}"/>${yLabels}${forecastLine}<polyline class="actual" points="${points(actualKey)}"/>${xLabels}</svg>`;
  var sparkId = cacheChart(svgStr, "Chart");
  return (
    '<div class="ytd-chart-wrap chart-expandable" onclick="openCachedChart(\'' +
    sparkId +
    '\')" title="Click to expand"><div class="chart-expand-hint">&#x2922; Expand</div>' +
    svgStr +
    "</div>"
  );
}

export function ytdMetricCard(
  title,
  actual,
  forecast,
  series,
  actualKey,
  forecastKey,
  extra = "",
  forecastLabel = "Projected full year",
  sparkOptions = null,
) {
  const isLastYear = !!ytdData?.summary?.is_last_year;
  const actualLabel = isLastYear ? "Actual (last year)" : "Actual YTD";
  return `<div class="ytd-metric"><h3>${esc(title)}</h3><div class="ytd-metric-values"><span><b>${ytdMoney(actual)}</b><small>${esc(actualLabel)}</small></span><span><b>${ytdMoney(forecast)}</b><small>${esc(forecastLabel)}</small></span></div>${ytdSparkline(series, actualKey, forecastKey, sparkOptions)}${extra ? `<p class="small">${esc(extra)}</p>` : ""}</div>`;
}

export function renderYtdUploadPanel(enabled) {
  return `<div class="ytd-upload-panel"><input type="file" id="ytdUploadInput" accept=".csv,text/csv" style="display:none" onchange="handleYtdTransactionUpload(this)"><div><h3>Import transactions</h3><p class="small">CSV columns: <code>Date, Merchant, Category, Account, Original Statement, Notes, Amount, Tags, Owner</code> — only <code>Date</code> and <code>Amount</code> are required. Column order does not matter, capitalization is ignored, and extra columns are skipped. All rows with a valid date are imported, regardless of year. Use the Year-to-date / Last year toggle above to choose which calendar year's actuals are shown.</p></div><div class="table-actions"><select id="ytdUploadMode"><option value="replace">Replace all</option><option value="incremental">Add without replacing</option></select><button class="btn primary" type="button" data-requires-app="1" onclick="document.getElementById('ytdUploadInput').click()">Preview &amp; import CSV</button><button class="btn" type="button" data-requires-app="1" onclick="downloadYtdTemplate()">Download Template</button>${enabled ? `<button class="btn" type="button" data-requires-app="1" onclick="deduplicateYtdTransactions()">Remove Duplicates</button>` : ""} ${enabled ? `<button class="btn danger" type="button" data-requires-app="1" onclick="deleteAllYtdTransactions()">Delete All</button>` : ""}</div></div>`;
}

export function renderYtdSummary() {
  const s = ytdData?.summary || { enabled: false };
  if (!s.enabled)
    return `<div class="section-note ytd-disabled"><b>YTD tracking is not enabled yet.</b> Upload transaction data to enable YTD spending, income, growth charts, transaction editing, and account mapping. All years of transaction history are kept; use the Year-to-date / Last year toggle to choose the reporting window once enabled.</div>`;
  const inv = s.investment_balance || {};
  const growthExtra = inv.actual_growth_available
    ? `Actual growth = mapped account current value − 12/31 prior-year balance. Investment rows use current holdings prices; non-investment rows use Current Value/Current Balance. Net investment cashflow is shown for diagnostics only.`
    : "Actual growth needs account setup rows with prior-year balances and either mapped holdings or current values.";
  const comp = s.cashflow_components || {};
  const spc = s.forecast?.spending_plan_components || {};
  const spendingExtra = s.forecast?.spending_annual_plan
    ? `Expected YTD = annual plan ${ytdMoney(s.forecast.spending_annual_plan)} × year complete (${esc(s.ytd_days || 0)}/${esc(s.year_days || 365)}). Core: ${ytdMoney(spc.core_spending)}. Mortgage and RE Tax: ${ytdMoney(spc.mortgage_and_re_tax ?? spc.mortgage)} (mortgage ${ytdMoney(spc.mortgage_payment)}, RE tax ${ytdMoney(spc.real_estate_taxes)}, annual adjustment ${ytdPct(spc.real_estate_tax_annual_adjustment_pct)}). Large discretionary: ${ytdMoney(spc.large_discretionary)}.`
    : s.forecast?.spending_plan_benchmark
      ? `Current annual core-spending benchmark: ${ytdMoney(s.forecast.spending_plan_benchmark)}.`
      : "";
  const growthSeries = s.growth_series || [];
  const windowLabel = s.is_last_year
    ? "Last year reporting window"
    : "YTD reporting window";
  return `<div class="ytd-status-grid"><div class="pill"><b>Earliest transaction</b><span>${esc(s.earliest_transaction_date || "—")}</span></div><div class="pill"><b>Latest transaction</b><span>${esc(s.latest_transaction_date || "—")}</span></div><div class="pill"><b>${esc(windowLabel)}</b><span>${esc(s.ytd_start || "—")} through ${esc(s.through_date || "—")}</span></div><div class="pill"><b>Transactions</b><span>${esc(s.transaction_count || 0)}</span></div><div class="pill"><b>Earned income</b><span>${ytdMoney(s.actual?.earned_income)}</span></div><div class="pill"><b>Investment income</b><span>${ytdMoney(s.actual?.investment_income)}</span></div><div class="pill"><b>Tax payments</b><span>${ytdMoney(s.actual?.taxes)}</span></div><div class="pill"><b>Net investment cashflow</b><span>${ytdMoney(inv.net_ytd_investment_cashflow)}</span></div></div><div class="ytd-metric-grid">${ytdMetricCard("YTD spending", s.actual?.spending, s.forecast?.spending, s.series, "actual_spending", "forecast_spending", spendingExtra, "Expected YTD")}${ytdMetricCard("YTD income", s.actual?.income, s.forecast?.income, s.series, "actual_income", "forecast_income", `Income categories only: ${(s.allowed_income_categories || []).join(", ") || "No income categories configured"}. Earned forecast remaining: ${ytdMoney(s.forecast?.earned_income_remaining)}. Note receivable included to date only: ${ytdMoney(comp.note_receivable_income)}. Investment/other income straight-lined: ${ytdMoney(s.forecast?.investment_income_annualized)} / ${ytdMoney(s.forecast?.other_income_annualized)}.`)}${ytdMetricCard("YTD growth", s.actual?.growth, inv.current_balance, growthSeries, "balance", null, growthExtra, "Current value", { scale: "range" })}</div>`;
}

export function renderYtdTransactions() {
  if (ytdDuplicateGroups) return renderYtdDuplicateReview();
  const enabled = !!ytdData?.summary?.enabled;
  if (!enabled)
    return `<div class="ytd-disabled-table"><h3>Transactions</h3><p class="small">Upload a transaction CSV to enable the compact table.</p></div>`;
  const tx = ytdFilteredTxns();
  const total = tx.length;
  const periodHasAnyTx = ytdTxnsForPeriod().length > 0;
  const emptyMessage = periodHasAnyTx
    ? "No transactions match the current filters."
    : ytdActualsPeriod === "last_year"
      ? `No transactions from last year (${ytdPeriodTargetYear()}) — please import.`
      : `No transactions from this year (${ytdPeriodTargetYear()}) yet — please import.`;
  const boundaries = ytdTxPageBoundaries(tx);
  const pages = boundaries
    ? boundaries.length
    : Math.max(1, Math.ceil(total / YTD_TX_PAGE_SIZE));
  if (ytdTxPage >= pages) ytdTxPage = pages - 1;
  if (ytdTxPage < 0) ytdTxPage = 0;
  let start, end, pageRows;
  if (boundaries) {
    const b = boundaries[ytdTxPage] || { start: 0, end: total };
    start = b.start;
    end = b.end;
    pageRows = tx.slice(start, end);
  } else {
    start = ytdTxPage * YTD_TX_PAGE_SIZE;
    pageRows = tx.slice(start, start + YTD_TX_PAGE_SIZE);
    end = start + pageRows.length;
  }
  const firstDate = pageRows.length ? pageRows[0].r.Date : "";
  const lastDate = pageRows.length ? pageRows[pageRows.length - 1].r.Date : "";
  const pagerHtml = ytdTxnPager(total, start, end, pages, firstDate, lastDate);
  return `<div class="holdings ytd-section">${ytdExistingDatalistsHtml()}<h3 class="group-title">Transactions</h3><div class="table-actions"><input class="search" style="max-width:260px" placeholder="Search transactions..." value="${esc(ytdTxSearch)}" oninput="ytdTxSearch=this.value;resetYtdTxnPage();renderMain()"><select onchange="ytdCategoryFilter=this.value;resetYtdTxnPage();renderMain()"><option value="">All categories</option>${ytdFilterOptions("Category").replace(`value=\"${esc(ytdCategoryFilter)}\"`, `value=\"${esc(ytdCategoryFilter)}\" selected`)}</select><select onchange="ytdAccountFilter=this.value;resetYtdTxnPage();renderMain()"><option value="">All accounts</option>${ytdFilterOptions("Account").replace(`value=\"${esc(ytdAccountFilter)}\"`, `value=\"${esc(ytdAccountFilter)}\" selected`)}</select><button class="btn" type="button" onclick="addYtdTxn()">Add transaction</button><button class="btn primary" id="ytdSaveTransactionsBtn" type="button" ${ytdTransactionsChanged ? "" : "disabled"} onclick="saveYtdTransactions()">Save transaction edits</button><button class="btn col-group-toggle" type="button" onclick="ytdTxColsCollapsed=!ytdTxColsCollapsed;renderMain()">${ytdTxColsCollapsed ? "Show all columns" : "Hide extra columns"}</button></div>${pagerHtml}<div class="lot-table-wrap ytd-table-wrap ytd-tx-table-wrap pinned-col${ytdTxColsCollapsed ? " cols-collapsed" : ""}"><table class="lot-table ytd-tx-table"><thead><tr>${ytdHeader("Date", "Date")}${ytdHeader("Merchant", "Merchant")}${ytdHeader("Category", "Category")}${ytdHeader("Account", "Account")}${ytdHeader("Amount", "Amount")}<th data-col-group="extra">Statement</th><th data-col-group="extra">Notes</th><th data-col-group="extra">Tags</th><th data-col-group="extra">Owner</th><th></th></tr></thead><tbody>${pageRows.map(({ r, i }) => `<tr><td class="ytd-date-cell"><input class="ytd-date-input" value="${esc(r.Date || "")}" oninput="updateYtdTxn(${i},'Date',this.value)"></td><td>${ytdSelectFieldHtml(i, "Merchant", r.Merchant)}</td><td>${ytdSelectFieldHtml(i, "Category", r.Category)}</td><td>${ytdSelectFieldHtml(i, "Account", r.Account)}</td><td class="ytd-amount-cell"><input class="ytd-amount-input${ytdAmountIsNegative(r.Amount) ? " ytd-negative-amount" : ""}" value="${esc(ytdTxnMoneyDisplay(r.Amount))}" onfocus="focusYtdTxnAmount(this)" oninput="updateYtdTxnAmount(${i},this)" onblur="blurYtdTxnAmount(${i},this)"></td><td data-col-group="extra"><input value="${esc(r["Original Statement"] || "")}" oninput="updateYtdTxn(${i},'Original Statement',this.value)"></td><td data-col-group="extra"><input value="${esc(r.Notes || "")}" oninput="updateYtdTxn(${i},'Notes',this.value)"></td><td data-col-group="extra"><input value="${esc(r.Tags || "")}" oninput="updateYtdTxn(${i},'Tags',this.value)"></td><td data-col-group="extra"><input value="${esc(r.Owner || "")}" oninput="updateYtdTxn(${i},'Owner',this.value)"></td><td><button class="danger-link" type="button" onclick="deleteYtdTxn(${i})">Delete</button></td></tr>`).join("") || `<tr><td colspan="10"><span class="small">${esc(emptyMessage)}</span></td></tr>`}</tbody></table></div>${pagerHtml}</div>`;
}

export function ytdBlendEnabledRow() {
  return rows.find(
    (r) =>
      r.section === "Cashflow" &&
      norm(r.subsection) === "spending" &&
      norm(r.label) === "ytd_blend_enabled",
  );
}

export function ytdBlendToggleHtml() {
  if (!ytdData?.summary?.enabled) return "";
  const row = ytdBlendEnabledRow();
  if (!row) return "";
  const val = String(valOf(row) || "TRUE").toUpperCase();
  const on = val === "TRUE" || val === "YES";
  const dirtyHere = dirty.has(row.row_index);
  return `<div class="section-note${on ? "" : " warn"}"><b>Blend real YTD actuals into this plan's current-year projection:</b> ${on ? "On (recommended) — the current-year Net Worth/Cash Flow projection blends real spending/income tracked below into the remainder of this year." : "Off — this plan is modeled as fully hypothetical for the current year; real activity tracked below is not blended in."} <select onchange="editValue(${row.row_index},this.value,this);renderMain()"><option value="TRUE" ${on ? "selected" : ""}>On (recommended)</option><option value="FALSE" ${on ? "" : "selected"}>Off (fully hypothetical)</option></select>${dirtyHere ? ' <span class="badge dirty">Edited — Save Changes to apply</span>' : ""}</div>`;
}

export function renderYtdTracking() {
  const enabled = !!ytdData?.summary?.enabled;
  return `<div class="holdings ytd-tracking"><h3 class="group-title">YTD spending and growth progress</h3>${enabled ? ytdActualsPeriodToggleHtml("tracking") : ""}${ytdBlendToggleHtml()}${renderYtdUploadPanel(enabled)}${renderYtdSummary()}</div>${renderYtdTransactions()}${renderYtdAccounts()}`;
}

export function renderYtdTransactionsStep() {
  const enabled = !!ytdData?.summary?.enabled;
  return `<div class="holdings ytd-tracking"><h3 class="group-title">Income &amp; Expense Transactions</h3><div class="section-note"><b>Step 1 of 2 — Import transactions here.</b> After importing, go to <a href="#" onclick="setStep('spending_core');return false">Spending Categories</a> (step 2) to assign categories to your transactions. Use Accounts &amp; Sources below to identify account/source type and balances.</div>${enabled ? ytdActualsPeriodToggleHtml("transactions_step") : ""}${ytdBlendToggleHtml()}${renderYtdUploadPanel(enabled)}${renderYtdTransactions()}${renderYtdAccounts()}</div>`;
}

export function deduplicateYtdTransactions() {
  if (!ytdData || !ytdData.transactions) {
    showMessage("No transactions loaded.");
    return;
  }
  const txns = ytdData.transactions;
  const keyFn = (r) =>
    [r.Date, r.Merchant, String(r.Amount || ""), r.Account, r.Category].join(
      "\x1f",
    );
  const groupMap = new Map();
  txns.forEach((r, i) => {
    const k = keyFn(r);
    if (!groupMap.has(k)) groupMap.set(k, []);
    groupMap.get(k).push(i);
  });
  const groups = [...groupMap.values()].filter((g) => g.length > 1);
  if (!groups.length) {
    showMessage("No duplicate transactions found.");
    return;
  }
  ytdDuplicateGroups = groups;
  ytdDuplicateSelected = new Set();
  groups.forEach((g) => g.slice(1).forEach((i) => ytdDuplicateSelected.add(i)));
  renderMain();
}

export function ytdUpdateDedupDeleteBtn() {
  const btn = document.querySelector(".ytd-dedup-delete-btn");
  if (btn)
    btn.textContent = ytdDuplicateSelected.size
      ? "Delete " + ytdDuplicateSelected.size + " selected"
      : "Delete Selected";
}

export function ytdToggleDuplicateSelect(i) {
  if (ytdDuplicateSelected.has(i)) ytdDuplicateSelected.delete(i);
  else ytdDuplicateSelected.add(i);
  const sel = ytdDuplicateSelected.has(i);
  const row = document.querySelector('tr[data-ytd-dup-row="' + i + '"]');
  if (row) {
    row.classList.toggle("ytd-dedup-sel-row", sel);
    const cb = row.querySelector("input[type=checkbox]");
    if (cb) cb.checked = sel;
    const gi = row.dataset.ytdDupGidx;
    const group = ytdDuplicateGroups && ytdDuplicateGroups[gi];
    if (group) {
      const allSel = group.every((idx) => ytdDuplicateSelected.has(idx));
      const ghdr = document.querySelector('tr[data-ytd-dup-ghdr="' + gi + '"]');
      if (ghdr) {
        const gcb = ghdr.querySelector("input[type=checkbox]");
        if (gcb) gcb.checked = allSel;
      }
    }
  }
  ytdUpdateDedupDeleteBtn();
}

export function ytdToggleDuplicateGroup(gi, checked) {
  const group = ytdDuplicateGroups && ytdDuplicateGroups[gi];
  if (!group) return;
  group.forEach((i) => {
    if (checked) ytdDuplicateSelected.add(i);
    else ytdDuplicateSelected.delete(i);
    const row = document.querySelector('tr[data-ytd-dup-row="' + i + '"]');
    if (row) {
      row.classList.toggle("ytd-dedup-sel-row", checked);
      const cb = row.querySelector("input[type=checkbox]");
      if (cb) cb.checked = checked;
    }
  });
  ytdUpdateDedupDeleteBtn();
}

export function ytdSelectAllDuplicates() {
  if (ytdDuplicateGroups)
    ytdDuplicateGroups.forEach((g) =>
      g.slice(1).forEach((i) => ytdDuplicateSelected.add(i)),
    );
  renderMain();
}

export function ytdDeleteSelectedDuplicates() {
  if (!ytdDuplicateSelected.size) {
    showMessage("No rows selected for deletion.");
    return;
  }
  const sorted = [...ytdDuplicateSelected].sort((a, b) => b - a);
  sorted.forEach((i) => ytdData.transactions.splice(i, 1));
  markYtdTransactionsDirty();
  ytdDuplicateGroups = null;
  ytdDuplicateSelected = new Set();
  renderMain();
  showMessage(
    sorted.length +
      " duplicate transaction" +
      (sorted.length === 1 ? "" : "s") +
      " removed. Save to persist.",
  );
}

export function ytdCancelDedup() {
  ytdDuplicateGroups = null;
  ytdDuplicateSelected = new Set();
  renderMain();
}

export function renderYtdDuplicateReview() {
  const groups = ytdDuplicateGroups || [];
  const txns = (ytdData && ytdData.transactions) || [];
  let html = '<div class="holdings ytd-section">';
  html +=
    '<h3 class="group-title">Review Duplicates — ' +
    groups.length +
    " group" +
    (groups.length === 1 ? "" : "s") +
    "</h3>";
  html +=
    '<p class="small">Rows marked <b>Dup</b> are pre-checked for deletion. Uncheck any to keep, then click Delete Selected.</p>';
  html += '<div class="table-actions">';
  html +=
    '<button class="btn danger ytd-dedup-delete-btn" type="button" onclick="ytdDeleteSelectedDuplicates()">' +
    (ytdDuplicateSelected.size
      ? "Delete " + ytdDuplicateSelected.size + " selected"
      : "Delete Selected") +
    "</button>";
  html +=
    ' <button class="btn" type="button" onclick="ytdSelectAllDuplicates()">Re-select defaults</button>';
  html +=
    ' <button class="btn" type="button" onclick="ytdCancelDedup()">Cancel</button>';
  html += "</div>";
  html +=
    '<div class="lot-table-wrap ytd-dedup-wrap"><table class="lot-table ytd-dedup-table"><thead><tr><th></th><th>Date</th><th>Merchant</th><th>Category</th><th>Account</th><th>Amount</th><th>Statement</th></tr></thead><tbody>';
  groups.forEach((group, gi) => {
    const allSel = group.every((i) => ytdDuplicateSelected.has(i));
    html +=
      '<tr class="ytd-dedup-group-hdr" data-ytd-dup-ghdr="' +
      gi +
      '"><td colspan="7"><label style="cursor:pointer;display:flex;align-items:center;gap:6px"><input type="checkbox" ' +
      (allSel ? "checked" : "") +
      ' onchange="ytdToggleDuplicateGroup(' +
      gi +
      ',this.checked)"> <b>Group ' +
      (gi + 1) +
      "</b> — " +
      group.length +
      " rows</label></td></tr>";
    group.forEach((i, rowIdx) => {
      const r = txns[i] || {};
      const sel = ytdDuplicateSelected.has(i);
      html +=
        '<tr class="' +
        (sel ? "ytd-dedup-sel-row " : "") +
        (rowIdx === 0 ? "ytd-dedup-orig" : "") +
        '" data-ytd-dup-row="' +
        i +
        '" data-ytd-dup-gidx="' +
        gi +
        '"><td><label style="cursor:pointer;display:flex;align-items:center;gap:4px"><input type="checkbox" ' +
        (sel ? "checked" : "") +
        ' onchange="ytdToggleDuplicateSelect(' +
        i +
        ')">' +
        (rowIdx === 0
          ? '<span class="badge ok">Keep</span>'
          : '<span class="badge bad">Dup</span>') +
        "</label></td><td>" +
        esc(r.Date || "") +
        "</td><td>" +
        esc(r.Merchant || "") +
        "</td><td>" +
        esc(r.Category || "") +
        "</td><td>" +
        esc(r.Account || "") +
        '</td><td class="ytd-amount-cell">' +
        esc(ytdTxnMoneyDisplay(r.Amount)) +
        "</td><td>" +
        esc(r["Original Statement"] || "") +
        "</td></tr>";
    });
    html += '<tr class="ytd-dedup-spacer"><td colspan="7"></td></tr>';
  });
  html += "</tbody></table></div></div>";
  return html;
}

export async function fetchText(path) {
  if (window.RetirementApiClient) {
    window.RetirementApiClient.setBase(apiBase || "");
    return await window.RetirementApiClient.text(path);
  }
  const res = await fetch(apiUrl(path), { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return await res.text();
}

export async function fetchPlanDataFiles(opts = {}) {
  const out = {};
  const mergeProtected = opts.mergeProtectedClientData !== false;
  for (const name of PLAN_DATA_FILES) {
    try {
      out[name] = await fetchText("/api/plan-data/" + encodeURIComponent(name));
    } catch (e) {
      if (name.startsWith("ytd_")) {
        out[name] = "";
        continue;
      }
      throw e;
    }
    if (mergeProtected && planFolderHandle && name.startsWith("client_")) {
      try {
        const localText = await readFileFromFolder(planFolderHandle, name);
        out[name] = mergeProtectedClientData(out[name], localText);
      } catch (_e) {}
    }
  }
  return out;
}

export function normalizePlanDataTextForCompare(v) {
  return String(v ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    .trimEnd();
}

export async function selectedFolderDiffersFromLoadedPlan() {
  if (!planFolderHandle) return false;
  const local = await readPlanDataFolderContents(planFolderHandle, false);
  const saved = await fetchPlanDataFiles({ mergeProtectedClientData: false });
  return PLAN_DATA_FILES.some(
    (name) =>
      normalizePlanDataTextForCompare(local[name] || "") !==
      normalizePlanDataTextForCompare(saved[name] || ""),
  );
}

export async function saveCurrentPlanToSelectedFolderForBuild() {
  if (!planFolderHandle) return false;
  const planFiles = await fetchPlanDataFiles();
  await savePlanDataToCurrentFolder(planFiles);
  return true;
}

export async function readFileFromFolder(dirHandle, name) {
  const h = await dirHandle.getFileHandle(name);
  const f = await h.getFile();
  return await f.text();
}

// Every export above is also re-attached to window: dashboard.js calls these
// as bare globals, and this file's own rendered HTML uses inline
// onclick="..." handlers, which always resolve through window regardless of
// module scoping. New code should prefer `import` from this module; this
// bridge exists only for callers that cannot move to import in the same pass.
Object.assign(window, {
  normalizeYtdActualsPeriod,
  readYtdActualsPeriod,
  setYtdActualsPeriod,
  ytdActualsPeriodToggleHtml,
  cacheChart,
  openCachedChart,
  csvEscape,
  clientDataKey,
  parseCsvTable,
  serializeCsvTable,
  mergeProtectedClientData,
  serializeLiabilities,
  saveLiabilities,
  ytdMoney,
  ytdPct,
  updateYtdTxnAmount,
  focusYtdTxnAmount,
  blurYtdTxnAmount,
  addYtdTxn,
  deleteYtdTxn,
  saveYtdTransactions,
  downloadYtdTemplate,
  importPreviewList,
  ytdImportPreviewMessage,
  handleYtdTransactionUpload,
  deleteAllYtdTransactions,
  ytdFilterOptions,
  ytdFirstExistingValue,
  resetYtdTxnPage,
  setYtdTxnPage,
  ytdDateAwarePageBoundaries,
  ytdTxPageBoundaries,
  ytdShortDate,
  ytdTxnPager,
  ytdTxYear,
  ytdPeriodTargetYear,
  ytdTxnsForPeriod,
  ytdFilteredTxns,
  setYtdSort,
  ytdHeader,
  ytdSparkline,
  ytdMetricCard,
  renderYtdUploadPanel,
  renderYtdSummary,
  renderYtdTransactions,
  ytdBlendEnabledRow,
  ytdBlendToggleHtml,
  renderYtdTracking,
  renderYtdTransactionsStep,
  deduplicateYtdTransactions,
  ytdUpdateDedupDeleteBtn,
  ytdToggleDuplicateSelect,
  ytdToggleDuplicateGroup,
  ytdSelectAllDuplicates,
  ytdDeleteSelectedDuplicates,
  ytdCancelDedup,
  renderYtdDuplicateReview,
  fetchText,
  fetchPlanDataFiles,
  normalizePlanDataTextForCompare,
  selectedFolderDiffersFromLoadedPlan,
  saveCurrentPlanToSelectedFolderForBuild,
  readFileFromFolder,
});
