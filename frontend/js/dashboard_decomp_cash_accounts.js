// Checking & Savings page (Investments & Property): each cash account as a name, a balance and the date the balance
// was last updated. Add and delete here; the account import updates balances. No symbol, shares, price or lot fields.
// Logic and storage live on the server (src/cash_accounts.py, /api/cash-accounts); helpers are bare globals.

let caData = null;
let caMessage = null; // { text, error }
let caDraft = { name: "", balance: "", as_of: "", import_account_key: "" };

export function caMoney(v) {
  const n = Number(v);
  if (v === null || v === undefined || v === "" || Number.isNaN(n)) return "—";
  return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function caHtml(data, draft = caDraft, message = caMessage) {
  const accts = (data && data.accounts) || [];
  const imports = (data && data.import_accounts) || [];
  const msg = panelMsgHtml("ca", message);
  const rows = accts.map((a) => `<tr><td>${esc(a.name)}</td><td class="rc-num">${caMoney(a.balance)}</td><td>${esc(a.as_of || "—")}</td>` +
    `<td>${a.import_account ? `Account import: ${esc(a.import_account)}` : "Entered by hand"}</td>` +
    `<td><button class="btn" type="button" aria-label="Delete ${esc(a.name)}" onclick="caDelete('${esc(a.account)}')">Delete</button></td></tr>`).join("");
  const table = accts.length ? `<table class="rc-table"><thead><tr><th>Account</th><th class="rc-num">Balance</th><th>Last updated</th><th>Balance comes from</th><th></th></tr></thead><tbody>${rows}</tbody></table>` :
    `<p class="muted">${data ? "No checking or savings accounts yet." : "Loading…"}</p>`;
  const pick = `<label>Account import<select aria-label="Account import" onchange="caSetDraft('import_account_key',this.value)"><option value="">None (I will enter it)</option>` +
    imports.map((i) => `<option value="${esc(i.account_key)}"${i.account_key === draft.import_account_key ? " selected" : ""}>${esc(i.account)}</option>`).join("") + `</select></label>`;
  return `<h2>Checking &amp; Savings</h2><p class="muted">Cash accounts. When an account is linked to the account import, the import keeps its balance and last-updated date current.</p>${msg}${table}` +
    `<h3>Add an account</h3><div class="field-grid"><label>Name<input aria-label="Account name" value="${esc(draft.name)}" onchange="caSetDraft('name',this.value)"></label>` +
    `<label>Balance<input aria-label="Opening balance" inputmode="decimal" value="${esc(draft.balance)}" onchange="caSetDraft('balance',this.value)"></label>` +
    `<label>As of<input aria-label="Balance date" type="date" value="${esc(draft.as_of)}" onchange="caSetDraft('as_of',this.value)"></label>${imports.length ? pick : ""}</div>` +
    `<button class="btn" type="button" onclick="caAdd()">Add account</button>`;
}

export function renderCashAccounts() {
  if (caData === null) setTimeout(caLoad, 0);
  return `<div id="caRoot">${caHtml(caData)}</div>`;
}

function caPaint() {
  const root = document.getElementById("caRoot");
  if (root) root.innerHTML = caHtml(caData);
}

export async function caLoad() {
  try { caData = await api("/api/cash-accounts"); } catch (e) { caData = { accounts: [], import_accounts: [] }; caMessage = { text: e.message, error: true }; }
  caPaint();
}

export function caSetDraft(key, value) { caDraft = { ...caDraft, [key]: value }; }

export async function caAdd() {
  try {
    await api("/api/cash-accounts", { method: "POST", body: JSON.stringify(caDraft) });
    caMessage = { text: `Added ${caDraft.name.trim()}.`, error: false };
    caDraft = { name: "", balance: "", as_of: "", import_account_key: "" };
  } catch (e) { caMessage = { text: e.message, error: true }; }
  await caLoad();
}

export async function caDelete(account) {
  if (!(await confirmDestructive("Its balance is removed from the plan.", { title: `Delete ${accountDisplayLabel(account)}?`, action: "Delete account" }))) return;
  try {
    await api("/api/cash-accounts/delete", { method: "POST", body: JSON.stringify({ account }) });
    caMessage = { text: `Deleted ${accountDisplayLabel(account)}.`, error: false };
  } catch (e) { caMessage = { text: e.message, error: true }; }
  await caLoad();
}

Object.assign(window, { renderCashAccounts, caHtml, caLoad, caSetDraft, caAdd, caDelete });
