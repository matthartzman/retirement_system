// Spending breakdown panels (docked along the bottom, off the card). Hovering a row LABEL shows that row's
// categories in the left panel; hovering a category there shows its merchants in the right panel. A click
// (or Enter/Space on the focused label) pins a panel so hovering elsewhere no longer replaces it; Escape,
// the Close button or a click outside the chart and panels closes everything. Ticks and bars open nothing.
// Hovering a merchant in the right panel loads its transactions into a third panel after a short delay.
import { escSvg, detailPopupHtml, categoryListHtml, transactionsUrl, transactionsPanelHtml, latestOnly } from "./charts.js";

export const HOVER_DELAY_MS = 200;

// A click on Pin/Unpin re-renders its panel, which detaches the clicked button before this document-level
// handler runs; a detached target is not "outside" (closest() on it no longer reaches #spendDock).
export function isOutsideClick(target) {
  if (!target || target.isConnected === false) return false;
  return !(target.closest && target.closest("#chartCategories, #spendDock"));
}

export function initSpendingDock({ doc, win, getModel, getRange }) {
  const popup = doc.getElementById("detailPopup");
  const popup2 = doc.getElementById("detailPopup2");
  const popup3 = doc.getElementById("detailPopup3");
  const dock = doc.getElementById("spendDock");
  const catBox = doc.getElementById("chartCategories");
  let popRow = null, popCat = -1, rowPinned = false, catPinned = false;
  // Third level: the merchant shown (or pending), its pin, a per-(range,line) cache and a latest-wins guard.
  let merchantPinned = false, txn = null, hoverTimer = null;
  const txnCache = new Map(), txnSeq = latestOnly();
  function rowIndexForLabel(target) {
    const label = target.closest && target.closest(".row-label");
    const g = label && label.closest("[data-row]");
    return g ? Number(g.dataset.row) : -1;
  }
  function modelRow(idx) {
    const model = getModel();
    if (!model || idx < 0) return null;
    return idx === 0 ? model.totalDetail : model.rows[idx - 1] || null;
  }
  function dockBar(pinned, what) {
    return `<div class="dock-bar"><span class="grow">${pinned ? "Pinned" : "Preview"} - ${escSvg(what)}</span>` +
      `<button type="button" data-dock="${pinned ? "unpin" : "pin"}">${pinned ? "Unpin" : "Pin"}</button>` +
      `<button type="button" data-dock="close" aria-label="Close breakdown">Close</button></div>`;
  }
  function markSelected(idx) {
    catBox.querySelectorAll(".bar-row.sel").forEach(g => g.classList.remove("sel"));
    const g = idx >= 0 && catBox.querySelector(`[data-row="${idx}"]`);
    if (g) g.classList.add("sel");
  }
  function cancelHover() {
    if (hoverTimer != null) { win.clearTimeout(hoverTimer); hoverTimer = null; }
  }
  // Empties the transactions panel and drops any request still in flight.
  function clearTxns() {
    cancelHover(); txnSeq.start();
    txn = null; merchantPinned = false;
    popup3.innerHTML = "";
  }
  function drawTxns(body) {
    popup3.innerHTML = dockBar(merchantPinned, txn.merchant) + body;
    popup3.scrollTop = 0;
  }
  function renderTxns() {
    const cached = txnCache.get(txn.url);
    drawTxns(cached ? transactionsPanelHtml(`${txn.merchant} - transactions`, cached) : '<div class="empty">Loading…</div>');
  }
  function loadMerchant(idx) {
    const cat = popRow && popRow.categories && popRow.categories[popCat];
    const m = cat && cat.merchants[idx];
    if (!m || !getRange) return;
    const url = transactionsUrl(getRange(), { type: popRow.name, group: cat.group, category: cat.name, merchant: m[0] });
    txn = { merchant: m[0], url, idx };
    const id = txnSeq.start();
    renderTxns();
    if (txnCache.has(url)) return;
    win.fetch(url).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }).then(data => {
      txnCache.set(url, data);
      if (txnSeq.isCurrent(id) && txn && txn.url === url) renderTxns();
    }).catch(() => {
      if (txnSeq.isCurrent(id) && txn && txn.url === url) drawTxns('<div class="empty">Couldn\'t load transactions.</div>');
    });
  }
  function merchantIndex(target) {
    const rowEl = target.closest && target.closest("[data-merchant]");
    return rowEl ? Number(rowEl.dataset.merchant) : -1;
  }
  function showRow(idx) {
    const row = modelRow(idx);
    if (!row) return;
    clearTxns();
    popRow = row; popCat = -1; catPinned = false;
    popup2.innerHTML = "";
    popup.innerHTML = dockBar(rowPinned, row.detailTitle) + (row.categories ? categoryListHtml(row.detailTitle, row.categories)
                                                                           : detailPopupHtml(row.detailTitle, row.detail));
    popup.scrollTop = 0;
    markSelected(idx);
    dock.classList.add("open");
  }
  function showMerchants(idx) {
    const cat = popRow && popRow.categories && popRow.categories[idx];
    if (!cat) return;
    if (idx !== popCat) clearTxns();
    popCat = idx;
    popup2.innerHTML = dockBar(catPinned, cat.name) + detailPopupHtml(`${cat.name} - merchants`, cat.merchants, undefined, { indexAttr: "merchant" });
    popup2.scrollTop = 0;
    popup.querySelectorAll(".pop-cat").forEach(el => el.classList.toggle("pinned", catPinned && Number(el.dataset.cat) === idx));
  }
  function hideAll() {
    dock.classList.remove("open");
    popup.innerHTML = ""; popup2.innerHTML = ""; clearTxns();
    popRow = null; popCat = -1; rowPinned = false; catPinned = false;
    markSelected(-1);
  }
  catBox.addEventListener("mouseover", (e) => {
    if (rowPinned) return;
    const idx = rowIndexForLabel(e.target);
    if (idx >= 0 && modelRow(idx) !== popRow) showRow(idx);
  });
  function pinRow(e) {
    const idx = rowIndexForLabel(e.target);
    if (idx < 0) return false;
    rowPinned = true; showRow(idx);
    return true;
  }
  catBox.addEventListener("click", pinRow);
  catBox.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && pinRow(e)) e.preventDefault();
  });
  popup.addEventListener("mouseover", (e) => {
    const rowEl = e.target.closest && e.target.closest("[data-cat]");
    if (!rowEl || !popRow || !popRow.categories || catPinned) return;
    const idx = Number(rowEl.dataset.cat);
    if (idx !== popCat) showMerchants(idx);
  });
  popup.addEventListener("click", (e) => {
    const rowEl = e.target.closest && e.target.closest("[data-cat]");
    if (!rowEl || !popRow || !popRow.categories) return;
    catPinned = true; showMerchants(Number(rowEl.dataset.cat));
  });
  popup2.addEventListener("mouseover", (e) => {
    const idx = merchantIndex(e.target);
    if (idx < 0 || merchantPinned || (txn && txn.idx === idx)) return;
    cancelHover();
    hoverTimer = win.setTimeout(() => { hoverTimer = null; loadMerchant(idx); }, HOVER_DELAY_MS);
  });
  popup2.addEventListener("mouseout", (e) => {
    // Leaving the row (not just moving between its children) cancels a pending request.
    const rowEl = e.target.closest && e.target.closest("[data-merchant]");
    if (rowEl && !(e.relatedTarget && rowEl.contains && rowEl.contains(e.relatedTarget))) cancelHover();
  });
  function pinMerchant(e) {
    const idx = merchantIndex(e.target);
    if (idx < 0) return false;
    cancelHover(); merchantPinned = true; loadMerchant(idx);
    return true;
  }
  popup2.addEventListener("click", pinMerchant);
  popup2.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && pinMerchant(e)) e.preventDefault();
  });
  dock.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button[data-dock]");
    if (!btn) return;
    const what = btn.dataset.dock;
    if (what === "close") { hideAll(); return; }
    if (popup3.contains(btn)) { if (txn) { merchantPinned = what === "pin"; renderTxns(); } return; }
    if (popup2.contains(btn)) { catPinned = what === "pin"; showMerchants(popCat); return; }
    rowPinned = what === "pin";
    showRow(getModel() ? [getModel().totalDetail, ...getModel().rows].indexOf(popRow) : -1);
  });
  doc.addEventListener("keydown", (e) => { if (e.key === "Escape") hideAll(); });
  doc.addEventListener("click", (e) => {
    if (!dock.classList.contains("open")) return;
    if (!isOutsideClick(e.target)) return;
    hideAll();
  });
  // The date range changed (or the data reloaded): cached transactions are for another window.
  function onRangeChange() { txnCache.clear(); clearTxns(); }
  return { hideAll, onRangeChange };
}
