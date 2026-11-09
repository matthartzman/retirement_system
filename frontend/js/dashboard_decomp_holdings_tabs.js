// Investment Holdings tab host: Positions (the grouped lot table), Activity (the transaction log) and Import (broker files).
// The tab is remembered and deep-linkable: #holdings/activity?account=..&symbol=..&type=..&source=backfill&year=..&back=sales
const HS_KEY = "holdings.tab.v1";
const HS_FILTERS = ["account", "symbol", "type", "source", "year", "back"];
export const HOLDINGS_TABS = [["positions", "Positions"], ["activity", "Activity"], ["import", "Import"]];
const hsTabOk = (t) => HOLDINGS_TABS.some((x) => x[0] === t);
let hsState = { tab: "positions", filters: {} };

// null unless the hash is ours; an unknown tab falls back to Positions.
export function hsParseHash(hash) {
  const m = /^#holdings(?:\/([^?]*))?(?:\?(.*))?$/.exec(String(hash || ""));
  if (!m) return null;
  const p = new URLSearchParams(m[2] || "");
  const out = { tab: hsTabOk(m[1]) ? m[1] : "positions" };
  for (const k of HS_FILTERS) out[k] = p.get(k) || "";
  return out;
}
export function hsActivityLink(f = {}) {
  const q = HS_FILTERS.filter((k) => f[k]).map((k) => `${k}=${encodeURIComponent(f[k])}`).join("&");
  return `#holdings/activity${q ? "?" + q : ""}`;
}
// A deep link wins; otherwise the remembered tab (storage may be off).
export function hsInitial(hash, storage = globalThis.localStorage) {
  const d = hsParseHash(hash);
  if (d) { const { tab, ...filters } = d; return { tab, filters }; }
  try { const t = JSON.parse(storage.getItem(HS_KEY)); if (hsTabOk(t)) return { tab: t, filters: {} }; } catch (e) { /* off or corrupt: Positions */ }
  return { tab: "positions", filters: {} };
}
export const hsBackHtml = (f) => (f && f.back === "sales" ? `<p class="hs-back"><a href="#sales_ledger?tab=fix" onclick="hsBack();return false">← Back to Sales Ledger</a></p>` : "");
export const hsTabBarHtml = (active) => `<div class="workspace-tabs hs-tabbar" role="tablist" aria-label="Investment holdings sections">` +
  HOLDINGS_TABS.map(([id, label]) => `<button type="button" role="tab" id="hs-t-${id}" class="workspace-tab${id === active ? " active" : ""}" aria-selected="${id === active}" onclick="hsSetTab('${id}')">${label}</button>`).join("") + `</div>`;

export function hsSetTab(id) {
  if (!hsTabOk(id)) return;
  hsState = { tab: id, filters: id === hsState.tab ? hsState.filters : {} };
  try { globalThis.localStorage.setItem(HS_KEY, JSON.stringify(id)); } catch (e) { /* convenience only */ }
  if (typeof renderMain === "function") renderMain();
}
export function hsBack() { if (typeof setStep === "function") setStep("sales_ledger"); }

// The page body: tab bar, then only the active tab (the others load when first opened).
export function renderHoldingsTabs(positionsFn) {
  const body = hsState.tab === "activity" ? window.renderTransactionLog()
    : hsState.tab === "import" ? window.renderBrokerImport() : positionsFn();
  return `${hsTabBarHtml(hsState.tab)}${hsState.tab === "positions" ? "" : hsBackHtml(hsState.filters)}<div role="tabpanel" id="hs-p-${hsState.tab}">${body}</div>`;
}

// Follow #holdings/... links (from the ledger, the chooser, Activity rows) and restore one after a reload.
export function hsGoHash() {
  const loc = typeof location !== "undefined" ? location : null;
  const d = loc && hsParseHash(loc.hash);
  if (!d) return;
  const { tab, ...filters } = d;
  hsState = { tab, filters };
  if (window.tlApplyFilters && tab === "activity") window.tlApplyFilters(filters);
  if (window.activeStep !== "holdings" && typeof setStep === "function") setStep("holdings"); else if (typeof renderMain === "function") renderMain();
}
hsState = hsInitial(typeof location !== "undefined" ? location.hash : "");
if (typeof window !== "undefined" && window.addEventListener) {
  window.addEventListener("hashchange", hsGoHash);
  window.addEventListener("load", () => setTimeout(hsGoHash, 400));
}

Object.assign(window, { HOLDINGS_TABS, hsParseHash, hsActivityLink, hsInitial, hsBackHtml, hsTabBarHtml, hsSetTab, hsBack, renderHoldingsTabs, hsGoHash });
