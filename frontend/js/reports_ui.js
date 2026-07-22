/* reports_ui.js: feature-owned report explorer rendering helpers.
   Phase 3 extraction: detailed results sheet/table/chart renderers moved from dashboard.js. */
(function () {
  "use strict";

  // ---- Escape utilities ----
  // esc/escJs live in dashboard_shared_helpers.js (A13), loaded first; this
  // module's bare esc(...) calls resolve to that global.
  function escCtx(ctx, v) {
    return ctx && ctx.esc ? ctx.esc(v) : esc(v);
  }
  function norm(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_");
  }
  function call(fn) {
    try {
      return typeof fn === "function" ? fn() : undefined;
    } catch (_e) {
      return undefined;
    }
  }

  // ---- Workbook sheet classification helpers ----
  function resultDisplayName(name) {
    return (
      String(name || "")
        .replace(/^\s*\d+[A-Za-z]?\.\s*/, "")
        .trim() || String(name || "Results")
    );
  }
  function workbookTabPrefix(name) {
    var m = String(name || "").match(/^(\d+[A-Za-z]?)[\.\s]/);
    return m
      ? m[1]
      : String(name || "").match(/^(\d+[A-Za-z]?)$/)
        ? String(name || "")
        : null;
  }
  function isWorkbookSectionDivider(name) {
    return (
      /^\d+[\.\s]/.test(String(name || "")) &&
      !/^\d+[A-Za-z][\.\s]/.test(String(name || ""))
    );
  }
  function isWorkbookContentSheet(name) {
    return workbookTabPrefix(name) !== null && !isWorkbookSectionDivider(name);
  }
  function workbookSheetSectionInt(name) {
    var m = String(name || "").match(/^(\d+)/);
    return m ? m[1] : null;
  }
  function isExcelTabSheet(s) {
    return (
      s.source === "excel_parser_fallback" ||
      /^\d+[A-Za-z]/.test(String(s.name || ""))
    );
  }

  // ---- Detail cell helpers ----
  function workbookCellSearchText(row) {
    return (row?.cells || [])
      .map((c) => String(c.display ?? c.value ?? ""))
      .join(" ")
      .toLowerCase();
  }
  function detailSectionMatches(section, q) {
    if (!q) return true;
    const title = String(section?.title || "").toLowerCase();
    if (title.includes(q)) return true;
    return (section?.rows || []).some((r) =>
      workbookCellSearchText(r).includes(q),
    );
  }
  function filteredDetailRows(section, q) {
    const rows = section?.rows || [];
    if (!q) return rows;
    return rows.filter(
      (r) =>
        workbookCellSearchText(r).includes(q) ||
        String(section?.title || "")
          .toLowerCase()
          .includes(q),
    );
  }
  function detailFallbackHeader(i, maxCells) {
    const base = [
      "Description",
      "Value",
      "Detail",
      "Scenario",
      "Year",
      "Amount",
      "Result",
      "Notes",
    ];
    return base[i] || `Detail ${i + 1}`;
  }
  const DETAIL_MONEY_TERMS = [
    "amount",
    "balance",
    "value",
    "price",
    "basis",
    "sale",
    "gross",
    "income",
    "spending",
    "expense",
    "cost",
    "payment",
    "mortgage",
    "tax",
    "taxes",
    "premium",
    "benefit",
    "withdrawal",
    "contribution",
    "distribution",
    "cash",
    "net worth",
    "nw",
    "ending nw",
    "terminal nw",
    "delta vs base",
    "principal",
    "interest",
    "dividend",
    "gain",
    "capital gain",
    "ltcg",
    "salary",
    "rent",
    "reserve",
    "proceeds",
    "equity",
  ];
  const DETAIL_PERCENT_TERMS = [
    "percent",
    "percentage",
    "pct",
    "rate",
    "return",
    "yield",
    "growth",
    "inflation",
    "cola",
    "success probability",
    "probability",
    "volatility",
    "allocation",
  ];
  function detailNumericValue(cell) {
    if (cell && typeof cell.value === "number" && Number.isFinite(cell.value))
      return cell.value;
    const raw = String(cell?.value ?? cell?.display ?? "").trim();
    if (!raw || /[a-zA-Z]/.test(raw.replace(/[KMB%$]/g, ""))) return null;
    const neg = /^\(.*\)$/.test(raw) || /^\s*-/.test(raw);
    let mult = 1;
    let cleaned = raw.replace(/[$,%()\s]/g, "");
    if (/[kK]$/.test(cleaned)) {
      mult = 1000;
      cleaned = cleaned.slice(0, -1);
    } else if (/[mM]$/.test(cleaned)) {
      mult = 1000000;
      cleaned = cleaned.slice(0, -1);
    } else if (/[bB]$/.test(cleaned)) {
      mult = 1000000000;
      cleaned = cleaned.slice(0, -1);
    }
    cleaned = cleaned.replace(/,/g, "");
    const n = Number(cleaned);
    if (!Number.isFinite(n)) return null;
    return (neg ? -Math.abs(n) : n) * mult;
  }
  function detailText(cell) {
    return String(cell?.display ?? cell?.value ?? "").trim();
  }
  function detailRowText(row) {
    return (row?.cells || []).map(detailText).filter(Boolean).join(" ");
  }
  function detailIsYearLike(n, context) {
    return (
      Number.isInteger(n) &&
      n >= 1900 &&
      n <= 2200 &&
      (/(^|[^a-z])year([^a-z]|$)/.test(context) || Math.abs(n) < 2300)
    );
  }
  function detailIsAgeContext(context) {
    return (
      /(^|[^a-z])age([^a-z]|$)/.test(context) ||
      /(^|\s)[hw]\s*age($|\s)/.test(context)
    );
  }
  function detailCurrencyK(n) {
    if (!Number.isFinite(n)) return "";
    const neg = n < 0;
    const abs = Math.abs(n);
    if (Math.round(abs / 1000) === 0)
      return (neg ? "-" : "") + "$" + Math.round(abs);
    const k = Math.round(abs / 1000);
    return (
      (neg ? "-" : "") +
      "$" +
      k.toLocaleString(undefined, { maximumFractionDigits: 0 }) +
      "K"
    );
  }
  function detailPercentDisplay(n) {
    if (!Number.isFinite(n)) return "";
    const pct = Math.abs(n) <= 1 ? n * 100 : n;
    return (
      pct.toLocaleString(undefined, {
        maximumFractionDigits: 0,
        minimumFractionDigits: 0,
      }) + "%"
    );
  }
  function detailIntegerDisplay(n) {
    if (!Number.isFinite(n)) return "";
    return String(Math.round(n));
  }
  function detailNumberDisplay(n) {
    if (!Number.isFinite(n)) return "";
    const decimals = Math.abs(n) < 100 && Math.abs(n % 1) > 0 ? 2 : 0;
    return n.toLocaleString(undefined, {
      maximumFractionDigits: decimals,
      minimumFractionDigits: 0,
    });
  }
  function detailRowHasMostlyBlankLeadingCells(cells) {
    return cells.length && cells.slice(0, 2).every((c) => !detailText(c));
  }
  function detailCellIsYearText(text) {
    const n = Number(String(text || "").replace(/\.0$/, ""));
    return Number.isInteger(n) && n >= 1900 && n <= 2200;
  }
  function detailHeaderScore(row, next) {
    const cells = row?.cells || [];
    const nonblank = cells.map(detailText).filter(Boolean);
    if (nonblank.length < 2) return -1;
    const textCount = nonblank.filter((x) => /[A-Za-z]/.test(x)).length;
    const yearCount = nonblank.filter(detailCellIsYearText).length;
    const nextNonblank = (next?.cells || [])
      .map(detailText)
      .filter(Boolean).length;
    let score =
      nonblank.length +
      (nextNonblank >= 2 ? 4 : 0) +
      (textCount ? 3 : 0) +
      (yearCount >= 2 ? 5 : 0);
    if (nonblank.length === 1) score -= 8;
    if (detailRowHasMostlyBlankLeadingCells(cells) && textCount <= 1)
      score -= 2;
    return score;
  }
  function detailHeaderRowIndex(section, rows) {
    if (!rows.length) return -1;
    let best = -1,
      bestScore = -1;
    const limit = Math.min(rows.length, 18);
    for (let i = 0; i < limit; i++) {
      const score = detailHeaderScore(rows[i], rows[i + 1]);
      if (score > bestScore) {
        bestScore = score;
        best = i;
      }
    }
    return bestScore >= 7 ? best : -1;
  }
  function detailIdentifierRowIndex(rows, headerIdx) {
    if (headerIdx <= 0) return -1;
    for (let i = headerIdx - 1; i >= 0; i--) {
      const cells = rows[i]?.cells || [];
      const vals = cells.map(detailText);
      const nonblank = vals.filter(Boolean);
      if (!nonblank.length) continue;
      const text = nonblank.join(" ").toLowerCase();
      if (
        text.includes("identifier") ||
        nonblank.length >= 2 ||
        cells.length > 3
      )
        return i;
      if (nonblank.length === 1 && i === 0 && headerIdx === 1) return i;
    }
    return -1;
  }
  function detailCellContext(section, row, cellIndex, headers) {
    const parts = [
      detailText(headers[cellIndex] || {}),
      detailText((row?.cells || [])[0] || {}),
      detailText((row?.cells || [])[1] || {}),
    ];
    return norm(parts.join(" "));
  }
  function detailTermInContext(context, term) {
    const t = norm(term);
    return new RegExp(
      "(^|[^a-z0-9])" +
        t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") +
        "([^a-z0-9]|$)",
    ).test(context);
  }
  function detailCellKind(section, row, cellIndex, headers) {
    const c = (row?.cells || [])[cellIndex] || {};
    const kind = String(c.kind || "").toLowerCase();
    const n = detailNumericValue(c);
    const context = detailCellContext(section, row, cellIndex, headers);
    if (n !== null && detailIsYearLike(n, context)) return "year";
    if (n !== null && detailIsAgeContext(context)) return "integer";
    if (["percent", "date", "text", "boolean"].includes(kind)) return kind;
    if (kind === "currency" && n !== null) return "currency";
    if (n === null) return "text";
    if (DETAIL_PERCENT_TERMS.some((term) => detailTermInContext(context, term)))
      return "percent";
    if (DETAIL_MONEY_TERMS.some((term) => detailTermInContext(context, term)))
      return "currency";
    return "number";
  }
  function detailCellDisplay(section, row, cellIndex, headers) {
    const c = (row?.cells || [])[cellIndex] || {};
    const raw = detailText(c);
    const n = detailNumericValue(c);
    if (n === null) return raw;
    const kind = detailCellKind(section, row, cellIndex, headers);
    if (kind === "currency") return detailCurrencyK(n);
    if (kind === "percent") return detailPercentDisplay(n);
    if (kind === "year" || kind === "integer") return detailIntegerDisplay(n);
    return detailNumberDisplay(n);
  }
  function detailColumnGroupKey(section, groupIndex) {
    return `${String(section?.title || "section")
      .replace(/[^a-z0-9]+/gi, "_")
      .slice(0, 42)}_${Number(section?.start_row || 0)}_${groupIndex}`;
  }
  function detailMeaningfulLabel(label) {
    const text = String(label || "").trim();
    return (
      !!text &&
      !/^measure\s*\d+$/i.test(text) &&
      !/^detail\s*\d+$/i.test(text) &&
      !/^column\s*\d+$/i.test(text)
    );
  }
  function detailLabelForColumn(section, rows, headers, i) {
    const header = detailText(headers[i] || {});
    if (detailMeaningfulLabel(header)) return header;
    for (const row of rows.slice(0, 18)) {
      const text = detailText((row.cells || [])[i] || {});
      if (detailMeaningfulLabel(text) && !_looksLikeDataValueForLabel(text))
        return text;
    }
    return detailFallbackHeader(i, 0);
  }
  function _looksLikeDataValueForLabel(text) {
    const t = String(text || "").trim();
    if (!t) return true;
    if (detailCellIsYearText(t)) return false;
    if (/^[$(\-\d,.%KMB\s]+$/i.test(t)) return true;
    return false;
  }
  function detailCleanSectionTitle(title) {
    return String(title || "")
      .replace(/^\s*\d+[A-Za-z]?\.\s*/, "")
      .replace(/\s+section\s+\d+\s*·\s*rows\s*\d+\s*[–-]\s*\d+\s*$/i, "")
      .trim();
  }
  function detailGroupLabel(section, labels, cols) {
    const visible = cols
      .map((i) => String(labels[i] || "").trim())
      .filter(detailMeaningfulLabel);
    const years = visible.filter(detailCellIsYearText);
    if (years.length >= Math.max(2, visible.length - 1)) {
      const first = years[0],
        last = years[years.length - 1];
      return first === last ? `Year ${first}` : `Years ${first}–${last}`;
    }
    if (visible.length) {
      const first = visible[0],
        last = visible[visible.length - 1];
      return first === last ? first : `${first} – ${last}`;
    }
    const sectionTitle = detailCleanSectionTitle(section?.title) || "Details";
    return `${sectionTitle} details ${cols[0] + 1}–${cols[cols.length - 1] + 1}`;
  }
  function detailColumnGroups(section, labels, pinned) {
    const detail = [];
    labels.forEach((_, i) => {
      if (!pinned.has(i)) detail.push(i);
    });
    const yearCount = detail.filter((i) =>
      detailCellIsYearText(String(labels[i] || "")),
    ).length;
    const gSize = yearCount >= Math.max(3, detail.length * 0.5) ? 10 : 6;
    const groups = [];
    for (let i = 0; i < detail.length; i += gSize) {
      const cols = detail.slice(i, i + gSize);
      groups.push({
        index: groups.length,
        cols,
        label: detailGroupLabel(section, labels, cols),
      });
    }
    return groups;
  }
  function detailSuperHeaderCells(rows, identifierIdx, cols) {
    if (identifierIdx < 0) return [];
    const idCells = rows[identifierIdx]?.cells || [];
    let current = "";
    const labels = cols.map((i) => {
      const text = detailText(idCells[i] || {});
      if (text) current = text;
      return current;
    });
    const out = [];
    labels.forEach((label, idx) => {
      const clean = detailMeaningfulLabel(label) ? label : "";
      if (!out.length || out[out.length - 1].label !== clean) {
        out.push({ label: clean, span: 1 });
      } else {
        out[out.length - 1].span++;
      }
    });
    return out;
  }
  function renderDetailTableForCols(
    rows,
    cols,
    labels,
    headers,
    identifierIdx,
    headerIdx,
    section,
  ) {
    const superCells = detailSuperHeaderCells(rows, identifierIdx, cols);
    let html = `<div class="detail-table-wrap"><table class="detail-result-table ${superCells.length ? "has-super-head" : ""}"><thead>`;
    if (superCells.length) {
      html +=
        '<tr class="detail-super-head">' +
        superCells
          .map((g) => `<th colspan="${g.span}">${esc(g.label)}</th>`)
          .join("") +
        "</tr>";
    }
    html += `<tr class="detail-label-head">${cols.map((i) => `<th>${esc(labels[i])}</th>`).join("")}</tr></thead><tbody>`;
    rows.forEach((r, ri) => {
      if (ri === headerIdx || ri === identifierIdx) return;
      html += "<tr>";
      cols.forEach((i) => {
        const kind = detailCellKind(section, r, i, headers);
        const val = detailCellDisplay(section, r, i, headers);
        html += `<td class="detail-cell-${esc(kind)}${kind === "currency" && detailNumericValue((r.cells || [])[i]) < 0 ? " negative-money" : ""}" title="${esc(String((r.cells || [])[i]?.value ?? ""))}">${esc(val)}</td>`;
      });
      html += "</tr>";
    });
    html += "</tbody></table></div>";
    return html;
  }

  // ---- Column group state (kept for backward compatibility; new render uses DOM toggling) ----
  function detailVisibleColumns(ctx, section, labels, q) {
    const maxCells = labels.length;
    const pinned = new Set();
    labels.forEach((label, i) => {
      const low = norm(label);
      if (
        i < 2 ||
        i === maxCells - 1 ||
        low.includes("total") ||
        low.includes("sum") ||
        low.includes("σ") ||
        low.includes("net worth")
      )
        pinned.add(i);
    });
    if (maxCells <= 8 || q) {
      return {
        cols: Array.from({ length: maxCells }, (_, i) => i),
        groups: [],
        pinned,
      };
    }
    const groups = detailColumnGroups(section, labels, pinned);
    const visible = new Set([...pinned]);
    groups.forEach((g) => {
      g.cols.forEach((c) => visible.add(c));
    });
    return { cols: Array.from(visible).sort((a, b) => a - b), groups, pinned };
  }
  // Find the summary column index for a group (the Σ/Total column that stays visible when collapsed)
  function _groupSummaryIdx(cols, labels) {
    // Prefer last col in group labeled with Σ/Total/Sum/NW
    const rev = [...cols].reverse();
    const found = rev.find((i) => {
      const low = norm(labels[i] || "");
      return (
        low.includes("σ") ||
        low.includes("total") ||
        low.includes("sum") ||
        low.includes("net_worth")
      );
    });
    return found !== undefined ? found : cols[cols.length - 1];
  }
  function renderDetailedResultTable(ctx, section, q) {
    const rows = filteredDetailRows(section, q);
    if (!rows.length)
      return '<div class="section-note">No rows match the current search.</div>';
    const maxCells = Math.max(1, ...rows.map((r) => (r.cells || []).length));
    const headerIdx = q ? -1 : detailHeaderRowIndex(section, rows);
    const headers = headerIdx >= 0 ? rows[headerIdx].cells || [] : [];
    const labels = Array.from({ length: maxCells }, (_, i) =>
      detailLabelForColumn(section, rows, headers, i),
    );
    const identifierIdx = q ? -1 : detailIdentifierRowIndex(rows, headerIdx);
    // Small table or active search: flat render
    if (maxCells <= 8 || q)
      return renderDetailTableForCols(
        rows,
        Array.from({ length: maxCells }, (_, i) => i),
        labels,
        headers,
        identifierIdx,
        headerIdx,
        section,
      );

    // Use semantic column_groups when provided by the results model
    const semanticGroups =
      section &&
      Array.isArray(section.column_groups) &&
      section.column_groups.length >= 2
        ? section.column_groups
        : null;
    if (semanticGroups) {
      // First group = always-pinned identifiers; remaining groups are collapsible
      const pinnedGroupEnd = Math.min(semanticGroups[0].end, maxCells - 1);
      const pinnedArr = Array.from({ length: pinnedGroupEnd + 1 }, (_, i) => i);
      const collapsible = semanticGroups
        .slice(1)
        .map((g, gi) => {
          const cols = [];
          for (let i = g.start; i <= Math.min(g.end, maxCells - 1); i++)
            cols.push(i);
          const sumIdx = _groupSummaryIdx(cols, labels);
          return { index: gi, label: g.label, cols, sumIdx };
        })
        .filter((g) => g.cols.length);
      if (!collapsible.length)
        return renderDetailTableForCols(
          rows,
          Array.from({ length: maxCells }, (_, i) => i),
          labels,
          headers,
          identifierIdx,
          headerIdx,
          section,
        );
      const nGroups = collapsible.length;
      let html = `<div class="detail-single-table-wrap"><div class="detail-col-group-bar"><div class="detail-col-group-label"><b>Show / hide columns</b><span class="detail-col-group-status">${nGroups} group${nGroups !== 1 ? "s" : ""} · all collapsed</span></div><div class="detail-col-group-bar-btns"><button class="btn" type="button" onclick="expandAllDetailGroups(this)">Expand all</button><button class="btn" type="button" onclick="collapseAllDetailGroups(this)">Collapse all</button></div></div>`;
      html += `<div class="detail-table-wrap"><table class="detail-result-table has-col-groups"><thead>`;
      // Row 1: group headers — spacer for pinned + 2 cols per collapsible group (summary + detail)
      html += '<tr class="detail-col-group-header-row">';
      if (pinnedArr.length)
        html += `<th class="detail-col-group-spacer" colspan="${pinnedArr.length}"></th>`;
      collapsible.forEach((g, gi) => {
        // Each group occupies: 1 always-visible summary col + (cols.length-1) hidden detail cols
        const totalColspan = g.cols.length;
        html += `<th class="detail-col-group-th collapsed" data-group="${gi}" data-group-label="${esc(g.label)}" colspan="${totalColspan}" onclick="toggleDetailColGroup(this)"><span class="col-group-toggle-label">▶ ${esc(g.label)}</span></th>`;
      });
      html += "</tr>";
      // Row 2: column labels
      html += '<tr class="detail-label-head">';
      pinnedArr.forEach((i) => (html += `<th>${esc(labels[i])}</th>`));
      collapsible.forEach((g, gi) => {
        g.cols.forEach((i) => {
          const isSummary = i === g.sumIdx;
          // Summary col: always visible; detail cols: hidden when collapsed
          html += `<th${isSummary ? ` class="cg-summary"` : ` class="cg-hidden" data-col-group="${gi}"`}>${esc(labels[i])}</th>`;
        });
      });
      html += "</tr></thead><tbody>";
      rows.forEach((r, ri) => {
        if (ri === headerIdx || ri === identifierIdx) return;
        html += "<tr>";
        pinnedArr.forEach((i) => {
          const kind = detailCellKind(section, r, i, headers);
          const val = detailCellDisplay(section, r, i, headers);
          const neg =
            kind === "currency" && detailNumericValue((r.cells || [])[i]) < 0;
          html += `<td class="detail-cell-${esc(kind)}${neg ? " negative-money" : ""}" title="${esc(String((r.cells || [])[i]?.value ?? ""))}">${esc(val)}</td>`;
        });
        collapsible.forEach((g, gi) => {
          g.cols.forEach((i) => {
            const kind = detailCellKind(section, r, i, headers);
            const val = detailCellDisplay(section, r, i, headers);
            const neg =
              kind === "currency" && detailNumericValue((r.cells || [])[i]) < 0;
            const isSummary = i === g.sumIdx;
            html += `<td class="${isSummary ? "cg-summary" : "cg-hidden detail-cell-" + esc(kind) + (neg ? " negative-money" : "")}${isSummary ? " detail-cell-" + esc(kind) + (neg ? " negative-money" : "") : ""}"${isSummary ? "" : ` data-col-group="${gi}"`} title="${esc(String((r.cells || [])[i]?.value ?? ""))}">${esc(val)}</td>`;
          });
        });
        html += "</tr>";
      });
      html += "</tbody></table></div></div>";
      return html;
    }

    // Fallback: auto-generated groups for sheets without semantic column_groups
    const pinned = new Set();
    labels.forEach((label, i) => {
      const low = norm(label);
      if (
        i < 2 ||
        i === maxCells - 1 ||
        low.includes("total") ||
        low.includes("sum") ||
        low.includes("σ") ||
        low.includes("net worth")
      )
        pinned.add(i);
    });
    const groups = detailColumnGroups(section, labels, pinned);
    if (!groups.length)
      return renderDetailTableForCols(
        rows,
        Array.from({ length: maxCells }, (_, i) => i),
        labels,
        headers,
        identifierIdx,
        headerIdx,
        section,
      );
    const pinnedArr = [...pinned].sort((a, b) => a - b);
    const nPinned = pinnedArr.length;
    const nGroups = groups.length;
    let html = `<div class="detail-single-table-wrap"><div class="detail-col-group-bar"><div class="detail-col-group-label"><b>Show / hide columns</b><span class="detail-col-group-status">${nGroups} group${nGroups !== 1 ? "s" : ""} · all collapsed</span></div><div class="detail-col-group-bar-btns"><button class="btn" type="button" onclick="expandAllDetailGroups(this)">Expand all</button><button class="btn" type="button" onclick="collapseAllDetailGroups(this)">Collapse all</button></div></div>`;
    html += `<div class="detail-table-wrap"><table class="detail-result-table has-col-groups"><thead>`;
    html += '<tr class="detail-col-group-header-row">';
    if (nPinned)
      html += `<th class="detail-col-group-spacer" colspan="${nPinned}"></th>`;
    groups.forEach((g, gi) => {
      const sumIdx = _groupSummaryIdx(g.cols, labels);
      const detailCount = g.cols.length - 1;
      html += `<th class="detail-col-group-th collapsed" data-group="${gi}" data-group-label="${esc(g.label)}" colspan="${g.cols.length}" onclick="toggleDetailColGroup(this)"><span class="col-group-toggle-label">▶ ${esc(g.label)}</span><small>${detailCount} col${detailCount !== 1 ? "s" : ""} + summary</small></th>`;
    });
    html += "</tr>";
    html += '<tr class="detail-label-head">';
    pinnedArr.forEach((i) => (html += `<th>${esc(labels[i])}</th>`));
    groups.forEach((g, gi) => {
      const sumIdx = _groupSummaryIdx(g.cols, labels);
      g.cols.forEach((i) => {
        const isSummary = i === sumIdx;
        html += `<th${isSummary ? ` class="cg-summary"` : ` class="cg-hidden" data-col-group="${gi}"`}>${esc(labels[i])}</th>`;
      });
    });
    html += "</tr></thead><tbody>";
    rows.forEach((r, ri) => {
      if (ri === headerIdx || ri === identifierIdx) return;
      html += "<tr>";
      pinnedArr.forEach((i) => {
        const kind = detailCellKind(section, r, i, headers);
        const val = detailCellDisplay(section, r, i, headers);
        const neg =
          kind === "currency" && detailNumericValue((r.cells || [])[i]) < 0;
        html += `<td class="detail-cell-${esc(kind)}${neg ? " negative-money" : ""}" title="${esc(String((r.cells || [])[i]?.value ?? ""))}">${esc(val)}</td>`;
      });
      groups.forEach((g, gi) => {
        const sumIdx = _groupSummaryIdx(g.cols, labels);
        g.cols.forEach((i) => {
          const kind = detailCellKind(section, r, i, headers);
          const val = detailCellDisplay(section, r, i, headers);
          const neg =
            kind === "currency" && detailNumericValue((r.cells || [])[i]) < 0;
          const isSummary = i === sumIdx;
          html += `<td class="${isSummary ? "cg-summary" : "cg-hidden detail-cell-" + esc(kind) + (neg ? " negative-money" : "")}${isSummary ? " detail-cell-" + esc(kind) + (neg ? " negative-money" : "") : ""}"${isSummary ? "" : ` data-col-group="${gi}"`} title="${esc(String((r.cells || [])[i]?.value ?? ""))}">${esc(val)}</td>`;
        });
      });
      html += "</tr>";
    });
    html += "</tbody></table></div></div>";
    return html;
  }

  // ---- Chart renderers ----
  function niceTickRange(max, count) {
    count = count || 5;
    if (!max || max <= 0) return Array.from({ length: count }, (_, i) => i);
    var rawStep = max / (count - 1);
    var mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    var nice = [1, 2, 5];
    var step = nice.reduce(function (best, m) {
      var s = m * mag;
      return Math.abs(s - rawStep) < Math.abs(best - rawStep) ? s : best;
    }, nice[0] * mag);
    return Array.from({ length: count }, function (_, i) {
      return step * i;
    });
  }
  function detailInferYLabel(max) {
    if (max <= 1.5) return "Rate (%)";
    if (max <= 150 && Number.isInteger(Math.round(max))) return "Count";
    return "Amount ($K)";
  }
  function detailChartColor(i) {
    return [
      "#000000",
      "#E69F00",
      "#56B4E9",
      "#009E73",
      "#F0E442",
      "#0072B2",
      "#D55E00",
      "#CC79A7",
    ][i % 8];
  }
  function detailChartValues(chart) {
    return (chart?.series || []).flatMap((s) =>
      (s.values || []).map(Number).filter(Number.isFinite),
    );
  }
  function detailChartMaxStack(chart) {
    const xs = chart?.x || [];
    let max = 0;
    xs.forEach((_, i) => {
      let total = 0;
      (chart.series || []).forEach((s) => {
        total += Math.max(0, Number((s.values || [])[i]) || 0);
      });
      max = Math.max(max, total);
    });
    return max || 1;
  }
  function renderDetailStackedBarChart(chart) {
    var xs = chart.x || [],
      series = chart.series || [],
      max = detailChartMaxStack(chart);
    var w = 960,
      h = 340,
      plotX = 80,
      plotY = 28,
      plotW = 820,
      plotH = 230,
      step = xs.length ? plotW / xs.length : plotW,
      barW = Math.max(2, Math.min(14, step * 0.62));
    var niceVals = niceTickRange(max);
    var ticks = niceVals.map(function (v) {
      return v / max;
    });
    var yLabel = chart.y_label || detailInferYLabel(max);
    var svg =
      '<svg viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="' +
      esc(chart.title || "Chart") +
      '">';
    ticks.forEach(function (t, i) {
      var y = plotY + plotH - t * plotH;
      var rawVal = niceVals[i];
      var label =
        max <= 1.5
          ? (rawVal * 100).toFixed(0) + "%"
          : max <= 150
            ? String(Math.round(rawVal))
            : detailCurrencyK(rawVal);
      svg +=
        '<line x1="' +
        plotX +
        '" y1="' +
        y.toFixed(1) +
        '" x2="' +
        (plotX + plotW) +
        '" y2="' +
        y.toFixed(1) +
        '" stroke="#e8e2d5" stroke-width="1"/>';
      svg +=
        '<text x="' +
        (plotX - 6) +
        '" y="' +
        (y + 4).toFixed(1) +
        '" text-anchor="end" class="detail-chart-tick">' +
        esc(label) +
        "</text>";
    });
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      (plotY + plotH) +
      '" x2="' +
      (plotX + plotW) +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      plotY +
      '" x2="' +
      plotX +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<text x="14" y="' +
      (plotY + plotH / 2) +
      '" text-anchor="middle" class="detail-chart-tick" transform="rotate(-90 14 ' +
      (plotY + plotH / 2) +
      ')">' +
      esc(yLabel) +
      "</text>";
    svg +=
      '<text x="' +
      (plotX + plotW / 2) +
      '" y="' +
      (h - 4) +
      '" text-anchor="middle" class="detail-chart-tick">Year</text>';
    xs.forEach(function (x, i) {
      var y = plotY + plotH;
      series.forEach(function (s, si) {
        var val = Math.max(0, Number((s.values || [])[i]) || 0);
        var rh = (val / max) * plotH;
        if (rh > 0.5) {
          svg +=
            '<rect x="' +
            (plotX + i * step + (step - barW) / 2).toFixed(1) +
            '" y="' +
            (y - rh).toFixed(1) +
            '" width="' +
            barW.toFixed(1) +
            '" height="' +
            rh.toFixed(1) +
            '" fill="' +
            detailChartColor(si) +
            '"><title>' +
            esc(s.label) +
            " " +
            esc(x) +
            ": " +
            esc(detailCurrencyK(val)) +
            "</title></rect>";
        }
        y -= rh;
      });
      if (i % Math.max(1, Math.ceil(xs.length / 8)) === 0)
        svg +=
          '<text x="' +
          (plotX + i * step + step / 2).toFixed(1) +
          '" y="' +
          (plotY + plotH + 16) +
          '" text-anchor="middle" class="detail-chart-tick">' +
          esc(String(x)) +
          "</text>";
    });
    svg += "</svg>";
    return svg + renderDetailChartLegend(series);
  }
  function renderDetailLineChart(chart) {
    var xs = chart.x || [],
      series = chart.series || [],
      vals = detailChartValues(chart);
    var max = Math.max.apply(null, vals.concat([1])),
      min = Math.min.apply(null, vals.concat([0]));
    var range = max - min || 1,
      w = 960,
      h = 340,
      plotX = 80,
      plotY = 28,
      plotW = 820,
      plotH = 230;
    var niceVals = niceTickRange(max);
    var ticks = niceVals.map(function (v) {
      return v / max;
    });
    var yLabel = chart.y_label || detailInferYLabel(max);
    var svg =
      '<svg viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="' +
      esc(chart.title || "Chart") +
      '">';
    ticks.forEach(function (t, i) {
      var val = min + t * range;
      var y = plotY + plotH - t * plotH;
      var rawVal = niceVals[i];
      var label =
        max <= 1.5
          ? (rawVal * 100).toFixed(0) + "%"
          : max <= 150
            ? String(Math.round(rawVal))
            : detailCurrencyK(rawVal);
      svg +=
        '<line x1="' +
        plotX +
        '" y1="' +
        y.toFixed(1) +
        '" x2="' +
        (plotX + plotW) +
        '" y2="' +
        y.toFixed(1) +
        '" stroke="#e8e2d5" stroke-width="1"/>';
      svg +=
        '<text x="' +
        (plotX - 6) +
        '" y="' +
        (y + 4).toFixed(1) +
        '" text-anchor="end" class="detail-chart-tick">' +
        esc(label) +
        "</text>";
    });
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      (plotY + plotH) +
      '" x2="' +
      (plotX + plotW) +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      plotY +
      '" x2="' +
      plotX +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<text x="14" y="' +
      (plotY + plotH / 2) +
      '" text-anchor="middle" class="detail-chart-tick" transform="rotate(-90 14 ' +
      (plotY + plotH / 2) +
      ')">' +
      esc(yLabel) +
      "</text>";
    svg +=
      '<text x="' +
      (plotX + plotW / 2) +
      '" y="' +
      (h - 4) +
      '" text-anchor="middle" class="detail-chart-tick">Year</text>';
    series.forEach(function (s, si) {
      var pts = (s.values || [])
        .map(function (v, i) {
          var x = plotX + (xs.length <= 1 ? 0 : (i / (xs.length - 1)) * plotW);
          var y = plotY + plotH - (((Number(v) || 0) - min) / range) * plotH;
          return (
            x.toFixed(1) +
            "," +
            Math.max(plotY, Math.min(plotY + plotH, y)).toFixed(1)
          );
        })
        .join(" ");
      svg +=
        '<polyline points="' +
        pts +
        '" fill="none" stroke="' +
        detailChartColor(si) +
        '" stroke-width="2.5"><title>' +
        esc(s.label) +
        "</title></polyline>";
    });
    xs.forEach(function (x, i) {
      if (i % Math.max(1, Math.ceil(xs.length / 8)) === 0)
        svg +=
          '<text x="' +
          (
            plotX + (xs.length <= 1 ? 0 : (i / (xs.length - 1)) * plotW)
          ).toFixed(1) +
          '" y="' +
          (plotY + plotH + 16) +
          '" text-anchor="middle" class="detail-chart-tick">' +
          esc(String(x)) +
          "</text>";
    });
    svg += "</svg>";
    return svg + renderDetailChartLegend(series);
  }
  function renderDetailScatterChart(chart) {
    var series = chart.series || [];
    var allPts = series.flatMap(function (s) {
      return s.points || [];
    });
    var xs = allPts.map(function (p) {
      return Number(p.x) || 0;
    });
    var ys = allPts.map(function (p) {
      return Number(p.y) || 0;
    });
    var xMax = Math.max.apply(null, xs.concat([0])) * 1.1 || 1;
    var xMin = Math.min.apply(null, xs.concat([0]));
    var yMax = Math.max.apply(null, ys.concat([0])) * 1.1 || 1;
    var yMin = Math.min.apply(null, ys.concat([0]));
    var xRange = xMax - xMin || 1;
    var yRange = yMax - yMin || 1;
    var w = 960,
      h = 340,
      plotX = 80,
      plotY = 28,
      plotW = 820,
      plotH = 230;
    var isPct = chart.unit === "percent" || yMax <= 1.5;
    function fmtAxisVal(v) {
      return isPct ? (v * 100).toFixed(1) + "%" : detailCurrencyK(v);
    }
    function toPx(pt) {
      return {
        x: plotX + ((Number(pt.x) - xMin) / xRange) * plotW,
        y: plotY + plotH - ((Number(pt.y) - yMin) / yRange) * plotH,
      };
    }
    var svg =
      '<svg viewBox="0 0 ' +
      w +
      " " +
      h +
      '" role="img" aria-label="' +
      esc(chart.title || "Chart") +
      '">';
    var yTicks = niceTickRange(yMax - yMin, 5).map(function (v) {
      return v + yMin;
    });
    yTicks.forEach(function (v) {
      var y = plotY + plotH - ((v - yMin) / yRange) * plotH;
      svg +=
        '<line x1="' +
        plotX +
        '" y1="' +
        y.toFixed(1) +
        '" x2="' +
        (plotX + plotW) +
        '" y2="' +
        y.toFixed(1) +
        '" stroke="#e8e2d5" stroke-width="1"/>';
      svg +=
        '<text x="' +
        (plotX - 6) +
        '" y="' +
        (y + 4).toFixed(1) +
        '" text-anchor="end" class="detail-chart-tick">' +
        esc(fmtAxisVal(v)) +
        "</text>";
    });
    var xTicks = niceTickRange(xMax - xMin, 5).map(function (v) {
      return v + xMin;
    });
    xTicks.forEach(function (v) {
      var x = plotX + ((v - xMin) / xRange) * plotW;
      svg +=
        '<text x="' +
        x.toFixed(1) +
        '" y="' +
        (plotY + plotH + 16) +
        '" text-anchor="middle" class="detail-chart-tick">' +
        esc(fmtAxisVal(v)) +
        "</text>";
    });
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      (plotY + plotH) +
      '" x2="' +
      (plotX + plotW) +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<line x1="' +
      plotX +
      '" y1="' +
      plotY +
      '" x2="' +
      plotX +
      '" y2="' +
      (plotY + plotH) +
      '" class="detail-axis"/>';
    svg +=
      '<text x="14" y="' +
      (plotY + plotH / 2) +
      '" text-anchor="middle" class="detail-chart-tick" transform="rotate(-90 14 ' +
      (plotY + plotH / 2) +
      ')">' +
      esc(chart.y_label || "") +
      "</text>";
    svg +=
      '<text x="' +
      (plotX + plotW / 2) +
      '" y="' +
      (h - 4) +
      '" text-anchor="middle" class="detail-chart-tick">' +
      esc(chart.x_label || "") +
      "</text>";
    series.forEach(function (s, si) {
      var pts = (s.points || []).map(toPx);
      var color = detailChartColor(si);
      if (s.style === "line") {
        var polyPts = pts
          .map(function (p) {
            return p.x.toFixed(1) + "," + p.y.toFixed(1);
          })
          .join(" ");
        svg +=
          '<polyline points="' +
          polyPts +
          '" fill="none" stroke="' +
          color +
          '" stroke-width="2"/>';
        pts.forEach(function (p) {
          svg +=
            '<circle cx="' +
            p.x.toFixed(1) +
            '" cy="' +
            p.y.toFixed(1) +
            '" r="3" fill="' +
            color +
            '"/>';
        });
      } else {
        pts.forEach(function (p) {
          svg +=
            '<circle cx="' +
            p.x.toFixed(1) +
            '" cy="' +
            p.y.toFixed(1) +
            '" r="7" fill="' +
            color +
            '" stroke="#fff" stroke-width="1.5"><title>' +
            esc(s.label) +
            "</title></circle>";
        });
      }
    });
    svg += "</svg>";
    return svg + renderDetailChartLegend(series);
  }
  function detailPiePath(cx, cy, r, start, end) {
    const sx = cx + r * Math.cos(start),
      sy = cy + r * Math.sin(start),
      ex = cx + r * Math.cos(end),
      ey = cy + r * Math.sin(end),
      large = end - start > Math.PI ? 1 : 0;
    return `M ${cx} ${cy} L ${sx} ${sy} A ${r} ${r} 0 ${large} 1 ${ex} ${ey} Z`;
  }
  function renderDetailPieChart(chart) {
    const slices = (chart.slices || []).filter((s) => Number(s.value) > 0);
    const total = slices.reduce((n, s) => n + Number(s.value || 0), 0) || 1;
    let angle = -Math.PI / 2;
    let svg =
      '<svg viewBox="0 0 300 300" role="img" aria-label="' +
      esc(chart.title || "Chart") +
      '" style="width:100%;max-width:260px;flex-shrink:0">';
    slices.forEach((s, i) => {
      const span = (Number(s.value || 0) / total) * Math.PI * 2;
      svg += `<path d="${detailPiePath(150, 150, 105, angle, angle + span)}" fill="${detailChartColor(i)}"><title>${esc(s.label)}: ${esc(detailCurrencyK(Number(s.value || 0)))} (${Math.round((Number(s.value || 0) / total) * 100)}%)</title></path>`;
      angle += span;
    });
    svg += "</svg>";
    const legendItems = slices
      .map(
        (s, i) =>
          `<div style="display:flex;align-items:center;gap:6px;font-size:12px;line-height:1.4"><i style="display:inline-block;width:12px;height:12px;min-width:12px;border-radius:2px;background:${detailChartColor(i)}"></i><span>${esc(s.label)} · ${Math.round((Number(s.value || 0) / total) * 100)}%</span></div>`,
      )
      .join("");
    return `<div style="display:flex;flex-direction:column;align-items:center;gap:12px">${svg}<div style="display:flex;flex-direction:column;gap:5px;align-self:stretch">${legendItems}</div></div>`;
  }
  function renderDetailChartLegend(series) {
    const items = (series || []).slice(0, 12);
    return `<div class="detail-chart-legend">${items.map((s, i) => `<span><i style="background:${detailChartColor(i)}"></i>${esc(s.label || "Series")}</span>`).join("")}${(series || []).length > items.length ? `<span>+${(series || []).length - items.length} more</span>` : ""}</div>`;
  }
  function renderDetailChartCard(ctx, chart) {
    var body = "";
    var KNOWN_TYPES = ["pie", "line", "bar", "stacked_bar", "stacked-bar", "scatter"];
    try {
      if (chart.type === "pie") body = renderDetailPieChart(chart);
      else if (chart.type === "line") body = renderDetailLineChart(chart);
      else if (chart.type === "scatter") body = renderDetailScatterChart(chart);
      else if (
        chart.type === "bar" ||
        chart.type === "stacked_bar" ||
        chart.type === "stacked-bar"
      )
        body = renderDetailStackedBarChart(chart);
      else if (!chart.type || KNOWN_TYPES.indexOf(chart.type) < 0)
        body =
          '<div class="chart-type-note">Chart type not yet supported: ' +
          esc(chart.type || "unknown") +
          "</div>";
      else body = renderDetailStackedBarChart(chart);
    } catch (e) {
      body =
        '<div class="section-note">This chart could not be rendered in the UI. Use Download Workbook to view the Excel chart.</div>';
    }
    var cacheId =
      ctx && ctx.cacheChart
        ? ctx.cacheChart(body, chart.title || "Chart")
        : "nocache";
    return (
      '<section class="detail-chart-card chart-expandable" onclick="openCachedChart(\'' +
      cacheId +
      '\')" title="Click to expand">' +
      '<div class="chart-expand-hint">&#x2922; Expand</div>' +
      "<h4>" +
      esc(chart.title || "Chart") +
      "</h4>" +
      body +
      "</section>"
    );
  }
  function renderChartDashboardSheet(ctx, sheet) {
    const charts = [...(sheet.charts || [])].sort((a, b) => {
      const aEx = /executive\s*summary/i.test(a.title || "");
      const bEx = /executive\s*summary/i.test(b.title || "");
      if (aEx && !bEx) return -1;
      if (!aEx && bEx) return 1;
      return 0;
    });
    let html = `<div class="detail-sheet-title"><h3>${esc(resultDisplayName(sheet.name))}</h3><span>${Number(charts.length)} charts</span></div>`;
    html += `<div class="section-note detail-preview-note">${esc(sheet.chart_note || "Chart-only dashboard. Source ranges are hidden and not displayed in the explorer.")}</div>`;
    if (!charts.length) {
      html += `<div class="missing-list"><h3>No chart data available</h3><p>Use Download Workbook to view the embedded Excel chart dashboard.</p></div>`;
      return html;
    }
    html += `<div class="detail-chart-grid">${charts.map((c) => renderDetailChartCard(ctx, c)).join("")}</div>`;
    return html;
  }

  // ---- Nav rendering ----
  function setDetailedResultsNavOpen(ctx, open) {
    call(() => ctx.setDetailedResultsNavOpenValue(!!open));
    try {
      if (window.localStorage)
        window.localStorage.setItem(
          "retirementDetailedResultsNavOpen",
          open ? "1" : "0",
        );
    } catch (_e) {}
  }
  function renderDetailedResultsNav(ctx) {
    ctx = ctx || {};
    const navOpen =
      !!call(ctx.getDetailedResultsNavOpen) ||
      call(ctx.getActiveStep) === "detailed_results";
    let html = `<details class="detailed-results-nav" ${navOpen ? "open" : ""} ontoggle="setDetailedResultsNavOpen(this.open)"><summary>Retirement Plan Workbook</summary><div class="detailed-results-nav-body">`;
    const activeCls =
      call(ctx.getActiveStep) === "detailed_results" ? "active" : "";
    html += `<button class="stepbtn ${activeCls}" type="button" data-step-id="detailed_results"><span class="num">↳</span><span><span class="step-title">Retirement Plan Workbook</span><div class="step-desc">Every workbook result sheet — charts and tables.</div></span></button>`;
    const data = call(ctx.getDetailedResultsData);
    if (data && data.success && Array.isArray(data.sheets)) {
      const allSheets = data.sheets;
      const groups = [];
      const groupMap = {};
      allSheets.forEach(function (sh) {
        if (!isWorkbookSectionDivider(sh.name)) return;
        const snum = workbookSheetSectionInt(sh.name);
        if (!snum || groupMap[snum]) return;
        const g = { label: sh.name, snum: snum, sheets: [] };
        groups.push(g);
        groupMap[snum] = g;
      });
      allSheets.forEach(function (sh) {
        if (
          !isWorkbookContentSheet(sh.name) &&
          !isWorkbookSectionDivider(sh.name)
        )
          return;
        const snum = workbookSheetSectionInt(sh.name);
        if (!snum) return;
        if (!groupMap[snum]) {
          const g = { label: "Section " + snum, snum: snum, sheets: [] };
          groups.push(g);
          groupMap[snum] = g;
        }
        groupMap[snum].sheets.push(sh);
      });
      groups.sort(function (a, b) {
        return Number(a.snum) - Number(b.snum);
      });
      groups.forEach(function (group) {
        const catOpen =
          navOpen &&
          (call(ctx.getActiveStep) === "detailed_results" ||
            group.sheets.some(function (sh) {
              return sh.name === call(ctx.getActiveDetailedSheet);
            }));
        html += `<details class="detail-nav-category" ${catOpen ? "open" : ""}><summary>${escCtx(ctx, group.label)}</summary><div class="detail-nav-sheets">`;
        group.sheets.forEach(function (sheet) {
          const cls =
            sheet.name === call(ctx.getActiveDetailedSheet) ? "active" : "";
          html += `<button class="detail-sheet-btn ${cls}" type="button" data-detail-sheet="${escCtx(ctx, sheet.name)}"><span>${escCtx(ctx, sheet.name)}</span><small>${sheet.kind === "chart_dashboard" ? `${Number(sheet.chart_count || sheet.section_count || 0)} charts` : `${Number(sheet.section_count || 0)} sections · ${Number(sheet.row_count || 0)} rows`}</small></button>`;
        });
        html += "</div></details>";
      });
    } else if (call(ctx.getDetailedResultsError)) {
      html += `<div class="detail-nav-note error">${escCtx(ctx, call(ctx.getDetailedResultsError))}</div>`;
    } else {
      html +=
        '<div class="detail-nav-note">Build outputs, then open this section to browse detailed results.</div>';
    }
    html += "</div></details>";
    return html;
  }
  function detailedProgressHtml(ctx, compact) {
    return call(() => ctx.detailedProgressHtml(!!compact)) || "";
  }
  function renderDetailedResults(ctx) {
    ctx = ctx || {};
    const hasData = !!call(ctx.getDetailedResultsData);
    const isLoading = !!call(ctx.getDetailedResultsLoading);
    const hasError = !!call(ctx.getDetailedResultsError);
    if (!hasData && !isLoading && !hasError) {
      // Kick off the async load, and show loading state immediately so there is no
      // "Build outputs first" flash while the setTimeout macro-task is pending.
      setTimeout(() => call(() => ctx.loadDetailedResults(false)), 0);
      return `<div class="holdings detailed-results"><div class="detail-loading-card"><h3>Loading results index</h3><p class="small">Opening the generated results and loading navigation first. Selected result pages load separately so large workbooks do not freeze the explorer.</p><div class="table-actions"><button class="btn" type="button" onclick="loadDetailedResults(true)" disabled>Refresh results</button></div></div></div>`;
    }
    if (isLoading) {
      return `<div class="holdings detailed-results"><div class="detail-loading-card"><h3>Loading results index</h3><p class="small">Opening the generated results and loading navigation first. Selected result pages load separately so large workbooks do not freeze the explorer.</p>${detailedProgressHtml(ctx, false)}<div class="table-actions"><button class="btn" type="button" onclick="loadDetailedResults(true)" disabled>Refresh results</button></div></div></div>`;
    }
    const detailedResultsError = call(ctx.getDetailedResultsError) || "";
    const detailedResultsData = call(ctx.getDetailedResultsData);
    if (detailedResultsError && !detailedResultsData) {
      return `<div class="holdings detailed-results"><div class="missing-list"><h3>Results unavailable</h3><p>${escCtx(ctx, detailedResultsError)}</p><p class="small">The explorer now times out instead of staying on a frozen loading message. Rebuild outputs if the file is missing or corrupt, then refresh this screen.</p></div><div class="table-actions"><button class="btn good" type="button" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button><button class="btn" type="button" onclick="loadDetailedResults(true)">Refresh results</button></div></div>`;
    }
    const data = detailedResultsData || {};
    if (!data.success) {
      return `<div class="holdings detailed-results"><div class="missing-list"><h3>Results unavailable</h3><p>${escCtx(ctx, data.error || detailedResultsError || "Build outputs first. Another browser refresh is not enough if no workbook exists yet.")}</p></div><div class="table-actions"><button class="btn good" type="button" data-requires-app="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button><button class="btn" type="button" onclick="loadDetailedResults(true)">Refresh results</button></div></div>`;
    }
    call(ctx.chooseDefaultDetailedSheet);
    const activeSheet = call(ctx.getActiveDetailedSheet);
    const sheet =
      call(() => ctx.detailedSheetByName(activeSheet)) ||
      (data.sheets || [])[0];
    const q = String(call(ctx.getDetailResultsSearchText) || "")
      .trim()
      .toLowerCase();
    let html = `<div class="holdings detailed-results"><div class="detail-results-head"><div><h3 class="group-title">Retirement Plan Workbook</h3><p class="small">${Number(data.sheet_count || 0)} result sheets from <b>${escCtx(ctx, data.workbook || "retirement_plan.xlsx")}</b>. Charts rendered natively; tables enhanced for the UI.</p></div><div class="table-actions"><button class="btn" type="button" onclick="loadDetailedResults(true)">Refresh results</button><button class="btn" data-requires-app="1" data-download="1" onclick="downloadWithBuild('/api/xlsx','Workbook')">Download Workbook</button></div></div>`;
    html += `<div class="detail-results-toolbar"><label><b>Search this result sheet</b><input class="search" value="${escCtx(ctx, call(ctx.getDetailResultsSearchText) || "")}" placeholder="Filter rows within the selected result page..." oninput="detailResultsSearchText=this.value;renderMain()"></label><label><b>Sheet</b><select onchange="setDetailedResultSheet(this.value)">${(
      data.sheets || []
    )
      .filter((s) => isExcelTabSheet(s))
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")))
      .map(
        (s) =>
          `<option value="${escCtx(ctx, s.name)}" ${sheet && s.name === sheet.name ? "selected" : ""}>${escCtx(ctx, s.name)}</option>`,
      )
      .join("")}</select></label><button class="btn" type="button" onclick="expandAllDetailColumnsOnPage()">Expand all columns</button></div>`;
    if (!sheet) {
      html += `<div class="section-note">No workbook sheets were found.</div></div>`;
      return html;
    }
    if (sheet.kind === "chart_dashboard" && Array.isArray(sheet.charts)) {
      html += renderChartDashboardSheet(ctx, sheet);
      html += "</div>";
      return html;
    }
    if (!Array.isArray(sheet.sections)) {
      if (
        !call(ctx.getDetailedResultSheetLoading) &&
        !call(ctx.getDetailedResultSheetError)
      )
        setTimeout(
          () => call(() => ctx.loadDetailedResultSheet(sheet.name, false)),
          0,
        );
      html += `<div class="detail-sheet-title"><h3>${escCtx(ctx, call(() => resultDisplayName(sheet.name)) || sheet.name)}</h3><span>${sheet.kind === "chart_dashboard" ? "chart-only · loads on demand" : `${Number(sheet.row_count || 0)} rows · loads on demand`}</span></div>`;
      if (call(ctx.getDetailedResultSheetError)) {
        html += `<div class="missing-list"><h3>Selected sheet unavailable</h3><p>${escCtx(ctx, call(ctx.getDetailedResultSheetError))}</p></div><div class="table-actions"><button class="btn" type="button" onclick="loadDetailedResultSheet(activeDetailedSheet,true)">Retry selected sheet</button><button class="btn" type="button" onclick="loadDetailedResults(true)">Refresh results</button></div></div>`;
        return html;
      }
      html += `<div class="detail-loading-card"><h3>Loading selected sheet</h3><p class="small">Loading the selected result page for <b>${escCtx(ctx, call(() => resultDisplayName(sheet.name)) || sheet.name)}</b>. Other result pages load only when selected.</p>${detailedProgressHtml(ctx, false)}</div></div>`;
      return html;
    }
    html += `<div class="detail-sheet-title"><h3>${escCtx(ctx, call(() => resultDisplayName(sheet.name)) || sheet.name)}</h3><span>${Number(sheet.row_count || 0)} rows · ${Number((sheet.sections || []).length)} sections · ${Number(sheet.column_count || 0)} columns</span></div>`;
    if (sheet.preview_note)
      html += `<div class="section-note detail-preview-note">${escCtx(ctx, sheet.preview_note)}${sheet.truncated ? " Showing a bounded preview so this sheet returns quickly." : ""}</div>`;
    const sections = (sheet.sections || []).filter((sec) =>
      detailSectionMatches(sec, q),
    );
    if (!sections.length)
      html += `<div class="section-note">No rows in this sheet match the current search.</div>`;
    sections.forEach(function (sec, i) {
      const rows = filteredDetailRows(sec, q);
      const sectionTitle =
        detailCleanSectionTitle(sec.title) ||
        resultDisplayName(sheet.name) ||
        "Details";
      const isOpen = q || i === 0 || sections.length === 1;
      html += `<details class="detailed-result-section" ${isOpen ? "open" : ""}><summary><span>${escCtx(ctx, sectionTitle)}</span><small>${Number(rows.length)} rows</small></summary>${renderDetailedResultTable(ctx, sec, q)}</details>`;
    });
    html += "</div>";
    return html;
  }
  window.RetirementReportsUI = {
    setDetailedResultsNavOpen,
    renderDetailedResultsNav,
    renderDetailedResults,
    // Exported for dashboard.js callers (chooseDefaultDetailedSheet uses isExcelTabSheet)
    isExcelTabSheet,
    resultDisplayName,
    // Exported for test coverage verification
    DETAIL_MONEY_TERMS,
    detailCurrencyK,
    detailHeaderRowIndex,
    detailLabelForColumn,
    detailGroupLabel,
    detailIdentifierRowIndex,
  };
})();
