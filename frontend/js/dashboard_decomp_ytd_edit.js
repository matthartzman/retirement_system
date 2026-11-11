// ── YTD (year-to-date) transaction/account edit helpers ──
// Extracted verbatim from dashboard_decomp_row_model.js (W4-06, ARC-005): the
// money parsing/display, dirty-state, existing-value datalist and Accounts
// panel helpers for the YTD pages. Bare-global bridge below, same convention as
// every other dashboard_decomp_*.js leaf; callers run after all modules load.

export function ytdRawMoney(v) {
  return String(v ?? "")
    .replace(/[$,]/g, "")
    .trim();
}

export function ytdTxnMoneyDisplay(v) {
  const raw = ytdRawMoney(v);
  if (raw === "") return "";
  const n = Number(raw);
  if (!Number.isFinite(n)) return String(v ?? "");
  const opts = {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
    maximumFractionDigits: 2,
  };
  return n.toLocaleString(undefined, opts);
}

export function ytdAmountIsNegative(v) {
  const n = Number(ytdRawMoney(v));
  return Number.isFinite(n) && n < 0;
}

export async function loadYtdStatus(silent = false) {
  // #201: loadAll() calls this as one sub-step among many -- it must not
  // clobber loadAll's own overlay message (e.g. "Saving changes") with
  // "Loading transactions" partway through an unrelated operation.
  if (!silent) showYtdLoadOverlay();
  try {
    const out = await api(
      "/api/ytd/status?period=" + encodeURIComponent(ytdActualsPeriod),
    );
    ytdData = out;
    ytdTransactionsChanged = false;
    ytdAccountsChanged = false;
  } catch (e) {
    ytdData = {
      success: false,
      error: e.message,
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  } finally {
    if (!silent) hideYtdLoadOverlay();
  }
}

export function setYtdDirtyButtonStates() {
  const txBtn = document.getElementById("ytdSaveTransactionsBtn");
  if (txBtn) txBtn.disabled = !ytdTransactionsChanged;
  const acctBtn = document.getElementById("ytdSaveAccountSetupBtn");
  if (acctBtn) acctBtn.disabled = !ytdAccountsChanged;
}

// Shared "inputs changed, last build is stale" step. #345: also called directly
// after server-side writes (import, delete-all, recover, roll-forward) that
// leave nothing to Save but still make the build stale -- activates Rebuild.
export function markBuildStale() {
  lastBuildOk = false;
  updateUnsaved();
  setAppControls(appReady);
}

export function markYtdTransactionsDirty() {
  ytdTransactionsChanged = true;
  markBuildStale();
  setYtdDirtyButtonStates();
}

export function markYtdAccountsDirty() {
  ytdAccountsChanged = true;
  markBuildStale();
  setYtdDirtyButtonStates();
}

export function updateYtdTxn(i, field, val) {
  if (!ytdData)
    ytdData = {
      transactions: [],
      account_setup: [],
      summary: { enabled: false },
    };
  if (!ytdData.transactions[i]) return;
  if (String(ytdData.transactions[i][field] ?? "") === String(val ?? ""))
    return;
  ytdData.transactions[i][field] = val;
  markYtdTransactionsDirty();
}

export function updateYtdAccount(i, field, val) {
  if (!ytdData.account_setup[i]) return;
  ytdData.account_setup[i][field] = val;
  if (field === "Role" && val === "Investment")
    ytdData.account_setup[i]["Current Value"] = "";
  markYtdAccountsDirty();
  if (field === "Role") renderMain();
  if (field === "Tax Treatment") renderMain();
}

export function ytdExistingValues(field) {
  return [
    ...new Set(
      (ytdData?.transactions || [])
        .map((r) => String(r[field] || "").trim())
        .filter(Boolean),
    ),
  ].sort((a, b) => a.localeCompare(b));
}

// The three transaction columns constrained to values already present
// somewhere in the transaction history.
const YTD_EXISTING_FIELDS = ["Merchant", "Category", "Account"];

export function ytdDatalistId(field) {
  return (
    "ytd-existing-" + String(field).toLowerCase().replace(/[^a-z0-9]+/g, "-")
  );
}

// One shared <datalist> per field, rendered once for the whole table.
//
// These columns used to inline a full <option> list into a per-row <select>,
// which is O(rows x distinct values): on a real plan that was 1,525 distinct
// merchants repeated on every visible row -- 825,635 <option> nodes and a
// ~62MB DOM for one page of the Transactions step. Sharing the lists makes it
// O(rows + distinct values), ~1.5k nodes, and gives type-ahead filtering
// instead of scrolling a 1,525-entry dropdown.
export function ytdExistingDatalistsHtml() {
  return YTD_EXISTING_FIELDS.map(
    (field) =>
      `<datalist id="${ytdDatalistId(field)}">${ytdExistingValues(field)
        .map((v) => `<option value="${esc(v)}"></option>`)
        .join("")}</datalist>`,
  ).join("");
}

// Cheap emptiness probe. ytdSelectFieldHtml runs once per row per field, so it
// must not rebuild (and sort) the whole distinct-value set the way the old
// per-row ytdExistingValues().length check did.
export function ytdHasExistingValues(field) {
  return (ytdData?.transactions || []).some((r) =>
    String(r[field] || "").trim(),
  );
}

// A <select> could only ever yield an existing value; a datalist-backed <input>
// also accepts free text, so enforce the same contract here -- anything typed
// that isn't already an existing value snaps back to the row's stored value.
// Matching is case-insensitive and commits the canonical casing, so picking
// from the list and typing the same text by hand land on the same value.
export function commitYtdExistingValue(i, field, el) {
  const row = ytdData?.transactions?.[i];
  const cur = row ? String(row[field] || "") : "";
  const typed = String(el.value || "").trim();
  const match = typed
    ? ytdExistingValues(field).find(
        (v) => v.toLowerCase() === typed.toLowerCase(),
      )
    : "";
  if (!match) {
    el.value = cur;
    return;
  }
  el.value = match;
  if (match !== cur) updateYtdTxn(i, field, match);
}

// An <input list> only offers options matching its text, so clear the text on
// focus to show every existing value; restore it on blur if nothing was chosen.
export function ytdOpenExistingList(el) { el.dataset.prev = el.value; el.value = ""; }
export function ytdRestoreExistingList(el) { if (!el.value) el.value = el.dataset.prev || ""; }

export function ytdSelectFieldHtml(i, field, value) {
  const has = ytdHasExistingValues(field);
  const disabled = has ? "" : " disabled";
  const placeholder = has ? `Select existing ${field}` : "No existing values";
  return `<input class="ytd-existing-select" list="${ytdDatalistId(field)}"${disabled} placeholder="${esc(placeholder)}" value="${esc(value || "")}" onfocus="ytdOpenExistingList(this)" onblur="ytdRestoreExistingList(this)" onchange="commitYtdExistingValue(${i},'${field}',this)">`;
}

export function ytdTransactionAccounts() {
  const saved =
    ytdData?.summary?.transaction_accounts ||
    ytdData?.transaction_accounts ||
    [];
  const local = (ytdData?.transactions || [])
    .map((r) => String(r.Account || "").trim())
    .filter(Boolean);
  return [...new Set([...saved, ...local].filter(Boolean))].sort((a, b) =>
    a.localeCompare(b),
  );
}

// #361: "<N-1> year end balance" where N is the plan's current year.
function ytdPriorYearEndHeader() {
  const y = Number(ytdData?.summary?.current_year);
  return y ? `${y - 1} year end balance` : "Prior year end balance";
}

export function renderYtdAccounts() {
  const enabled = !!ytdData?.summary?.enabled;
  if (!enabled) return "";
  const accounts = ytdData.account_setup || [];
  const holdingCount = ytdInvestmentHoldingAccounts().length;
  const addSourceControls = `<input id="ytdManualAccountName" class="search ytd-add-source-name" placeholder="Account/source name"><select id="ytdManualAccountRole" aria-label="Account/source type to add">${ytdAccountRoleOptions("Offline asset")}</select><button class="btn" type="button" onclick="addManualYtdAccount()">Add account/source</button>`;
  return `<div class="holdings ytd-section" data-help-section="actual_spending.accounts_sources"><h3 class="group-title">Accounts &amp; Sources</h3>${ytdRolloverBannerHtml()}<div class="table-actions ytd-account-actions">${addSourceControls}<button class="btn primary" id="ytdSaveAccountSetupBtn" type="button" ${ytdAccountsChanged ? "" : "disabled"} onclick="saveYtdAccountSetup()">Save Accounts &amp; Sources</button><button class="btn" type="button" onclick="recoverYtdAccountSetup()">Recover previous setup</button></div>${holdingCount ? "" : '<p class="small" data-kind="state">No investment holding accounts found in Holdings yet.</p>'}<div class="lot-table-wrap ytd-account-wrap"><table class="lot-table ytd-account-table"><thead><tr><th>Account / Source</th><th>Account Type</th><th>Mapped Account</th><th>${ytdPriorYearEndHeader()}</th><th>Current Value</th><th title="How a non-liquid balance is taxed when paid out. Used by the Financial Insight Current Snapshot estimate.">Tax Treatment</th><th title="What was paid in after tax. Only the growth above it is taxed.">After-Tax Premium</th><th class="ytd-delete-cell">Action</th></tr></thead><tbody>${
    accounts
      .map((r, i) => {
        const role = String(r.Role || "Cash / spending");
        const isInv = role === "Investment";
        const isGrowth = ytdIsGrowthRole(role);
        return `<tr><td><input list="ytdAccountChoices" value="${esc(r.Account || "")}" oninput="updateYtdAccount(${i},'Account',this.value)" placeholder="Account or source name"></td><td><select onchange="updateYtdAccount(${i},'Role',this.value)">${ytdAccountRoleOptions(role)}</select></td><td><select onchange="updateYtdAccount(${i},'Mapped Investment Account',this.value)" ${isGrowth ? "" : "disabled"}>${ytdInvestmentOptions(r["Mapped Investment Account"] || "")}</select></td><td><input class="ytd-money-input" value="${esc(ytdAccountMoneyDisplay(r["Prior Year End Balance"]))}" onfocus="focusYtdAccountMoney(this)" oninput="updateYtdAccountMoney(${i},'Prior Year End Balance',this)" onblur="blurYtdAccountMoney(${i},'Prior Year End Balance',this)" placeholder="$0"></td><td><input class="ytd-money-input" value="${esc(ytdAccountMoneyDisplay(r["Current Value"]))}" ${(() => {
          const mapped = r["Mapped Investment Account"] || "";
          const annuityPension =
            ytdData?.summary?.annuity_pension_accounts || [];
          const isMappedAnnuity =
            isGrowth && !isInv && mapped && annuityPension.includes(mapped);
          return isInv
            ? 'disabled placeholder="From holdings"'
            : isMappedAnnuity
              ? 'disabled placeholder="From income stream"'
              : 'placeholder="$0"';
        })()} onfocus="focusYtdAccountMoney(this)" oninput="updateYtdAccountMoney(${i},'Current Value',this)" onblur="blurYtdAccountMoney(${i},'Current Value',this)"></td>${(() => {
          const taxable = ["Annuity/Pension", "Annuity", "Pension", "Offline asset"].includes(role);
          const treat = r["Tax Treatment"] || "";
          const opts = ["", "Taxed in full", "Taxed above premium", "Not taxed"]
            .map((o) => `<option value="${esc(o)}"${o === treat ? " selected" : ""}>${o || "Guess from name"}</option>`).join("");
          return `<td><select aria-label="Tax treatment" onchange="updateYtdAccount(${i},'Tax Treatment',this.value)" ${taxable ? "" : "disabled"}>${opts}</select></td><td><input class="ytd-money-input" aria-label="After-tax premium" value="${esc(r["After-Tax Premium"] || "")}" oninput="updateYtdAccount(${i},'After-Tax Premium',this.value)" placeholder="$0" ${taxable && treat === "Taxed above premium" ? "" : "disabled"}></td>`;
        })()}<td class="ytd-delete-cell">${deleteIconBtn(`deleteYtdAccount(${i})`)}</td></tr>`;
      })
      .join("") ||
    `<tr><td colspan="8"><span class="small" data-kind="state">No accounts yet. Upload transactions or add a manual row.</span></td></tr>`
  }</tbody></table><datalist id="ytdAccountChoices">${ytdTransactionAccounts()
    .map((o) => `<option value="${esc(o)}"></option>`)
    .join("")}</datalist></div></div>`;
}
Object.assign(window, {
  commitYtdExistingValue, loadYtdStatus, markBuildStale, markYtdAccountsDirty,
  markYtdTransactionsDirty, renderYtdAccounts, setYtdDirtyButtonStates, updateYtdAccount,
  updateYtdTxn, ytdAmountIsNegative, ytdDatalistId, ytdExistingDatalistsHtml, ytdExistingValues,
  ytdHasExistingValues, ytdOpenExistingList, ytdRawMoney, ytdRestoreExistingList,
  ytdSelectFieldHtml, ytdTransactionAccounts, ytdTxnMoneyDisplay,
});
