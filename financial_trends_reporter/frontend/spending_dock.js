// Spending breakdown panels (docked along the bottom, off the card). Hovering a row LABEL shows that row's
// categories in the left panel; hovering a category there shows its merchants in the right panel. A click
// (or Enter/Space on the focused label) pins a panel so hovering elsewhere no longer replaces it; Escape,
// the Close button or a click outside the chart and panels closes everything. Ticks and bars open nothing.
import { escSvg, detailPopupHtml, categoryListHtml } from "./charts.js";

// A click on Pin/Unpin re-renders its panel, which detaches the clicked button before this document-level
// handler runs; a detached target is not "outside" (closest() on it no longer reaches #spendDock).
export function isOutsideClick(target) {
  if (!target || target.isConnected === false) return false;
  return !(target.closest && target.closest("#chartCategories, #spendDock"));
}

export function initSpendingDock({ doc, win, getModel }) {
  const popup = doc.getElementById("detailPopup");
  const popup2 = doc.getElementById("detailPopup2");
  const dock = doc.getElementById("spendDock");
  const catBox = doc.getElementById("chartCategories");
  let popRow = null, popCat = -1, rowPinned = false, catPinned = false;
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
  function showRow(idx) {
    const row = modelRow(idx);
    if (!row) return;
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
    popCat = idx;
    popup2.innerHTML = dockBar(catPinned, cat.name) + detailPopupHtml(`${cat.name} - merchants`, cat.merchants);
    popup2.scrollTop = 0;
    popup.querySelectorAll(".pop-cat").forEach(el => el.classList.toggle("pinned", catPinned && Number(el.dataset.cat) === idx));
  }
  function hideAll() {
    dock.classList.remove("open");
    popup.innerHTML = ""; popup2.innerHTML = "";
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
  dock.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("button[data-dock]");
    if (!btn) return;
    const what = btn.dataset.dock;
    if (what === "close") { hideAll(); return; }
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
  return { hideAll };
}
