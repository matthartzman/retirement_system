/**
 * Admin UI Helper Functions
 *
 * Pure functions for admin settings management, CSV parsing, and UI rendering.
 * Extracted from admin.js for testability and reusability.
 */

/**
 * Extract cell value from CSV row
 * @param {array} row - CSV row array
 * @param {number} i - Column index
 * @returns {string} Cell value as string, empty string if missing
 */
export function rowCell(row, i) {
  return String((row || [])[i] ?? '');
}

/**
 * Check if row is CSV header row
 * @param {array} row - CSV row array
 * @returns {boolean} True if row matches header format
 */
export function isHeader(row) {
  return (
    rowCell(row, 0).trim().toLowerCase() === 'section' &&
    rowCell(row, 1).trim().toLowerCase() === 'subsection'
  );
}

/**
 * Check if row is comment row
 * @param {array} row - CSV row array
 * @returns {boolean} True if row starts with #
 */
export function isComment(row) {
  return rowCell(row, 0).trim().startsWith('#');
}

/**
 * Check if row is valid setting row
 * @param {array} row - CSV row array
 * @returns {boolean} True if row is a setting (not header or comment, has at least 4 columns)
 */
export function isSetting(row) {
  return (
    rowCell(row, 0).trim() &&
    !isHeader(row) &&
    !isComment(row) &&
    row.length >= 4
  );
}

/**
 * Clean comment text by removing comment markers
 * @param {string} s - Comment text
 * @returns {string} Cleaned comment
 */
export function cleanComment(s) {
  return String(s || '')
    .replace(/^#\s*-*/, '')
    .replace(/-*\s*$/, '')
    .trim();
}

/**
 * Convert string to title case with acronym substitution
 * @param {string} s - Input string (typically snake_case)
 * @returns {string} Title-cased string with acronyms
 */
export function titleCaseLabel(s) {
  const key = String(s || '').trim();
  const labelMap = {
    annual_premium_base_year:
      'Pre-65 Healthcare Premium (annual per person)',
    part_b_base_premium_monthly: 'Monthly Medicare Part B (prior to IRMAA)',
    part_d_base_premium_monthly: 'Monthly Medicare Part D (prior to IRMAA)',
    annual_oop_estimate_today: 'Annual Household Medical OOP Cap',
    mc_engine_mode: 'Monte Carlo Engine',
    monthly_at_claim_age_today_dollars: 'Monthly at Claim Age',
    monthly_pia_at_fra_today_dollars: 'Monthly at FRA',
    roth_target_bracket_rate: 'Roth Tax-Bracket Ceiling',
    roth_irmaa_target_tier: 'Medicare IRMAA Tier Ceiling',
    irmaa_guardrail_mode: 'IRMAA Guardrail Behavior',
    roth_irmaa_headroom_usage_pct: 'IRMAA Headroom Used',
    irmaa_annual_inflator: 'IRMAA Threshold Inflation',
  };

  if (labelMap[key]) return labelMap[key];

  let out = String(s || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const acronyms = {
    js: 'JS',
    ltcg: 'LTCG',
    stcg: 'STCG',
    etf: 'ETF',
    etfs: 'ETFs',
    pdia: 'PDIA',
    niit: 'NIIT',
    ira: 'IRA',
    iras: 'IRAs',
    rmd: 'RMD',
    rmds: 'RMDs',
    qcd: 'QCD',
    hsa: 'HSA',
    hsas: 'HSAs',
    cma: 'CMA',
    cmas: 'CMAs',
    csv: 'CSV',
    ui: 'UI',
    api: 'API',
    url: 'URL',
    https: 'HTTPS',
    http: 'HTTP',
    dns: 'DNS',
    pdf: 'PDF',
    xlsx: 'XLSX',
    qc: 'QC',
    tips: 'TIPS',
    reit: 'REIT',
    reits: 'REITs',
    sep: 'SEP',
    llc: 'LLC',
    irs: 'IRS',
    agi: 'AGI',
    magi: 'MAGI',
    pia: 'PIA',
    fra: 'FRA',
  };

  return out
    .replace(/\b[A-Za-z0-9]+\b/g, (w) => acronyms[w.toLowerCase()] || w)
    .replace(/\bW2\b/g, 'W-2')
    .replace(/\bK1\b/g, 'K-1');
}

/**
 * Convert CSV rows array to CSV string format
 * @param {array} rows - Array of row arrays
 * @returns {string} CSV formatted text
 */
export function rowsToCsv(rows) {
  return (
    rows
      .map((r) =>
        r
          .map((v) => {
            v = String(v ?? '');
            return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
          })
          .join(',')
      )
      .join('\n') + '\n'
  );
}

/**
 * Parse CSV text into rows array
 * @param {string} text - CSV formatted text
 * @returns {array} Array of row arrays
 */
export function parseCsv(text) {
  const rows = [];
  let row = [],
    val = '',
    inQ = false;

  for (let i = 0; i < String(text).length; i++) {
    const ch = text[i],
      nx = text[i + 1];

    if (inQ) {
      if (ch === '"' && nx === '"') {
        val += '"';
        i++;
      } else if (ch === '"') {
        inQ = false;
      } else {
        val += ch;
      }
    } else {
      if (ch === '"') {
        inQ = true;
      } else if (ch === ',') {
        row.push(val);
        val = '';
      } else if (ch === '\n') {
        row.push(val);
        rows.push(row);
        row = [];
        val = '';
      } else if (ch === '\r') {
        // skip carriage return
      } else {
        val += ch;
      }
    }
  }

  if (val || row.length) {
    row.push(val);
    rows.push(row);
  }

  return rows;
}

/**
 * Get valid choices for a setting row
 * @param {array} row - Setting row
 * @returns {array|null} Array of valid choices, or null if no fixed choices
 */
export function choicesFor(row) {
  const units = rowCell(row, 4).trim();
  const label = rowCell(row, 2).trim();
  const section = rowCell(row, 0).trim();

  const fixed = {
    pricing_mode: ['CACHE', 'LIVE', 'OFFLINE'],
    trade_optimizer_mode: ['GLOBAL_TAX_AWARE', 'HEURISTIC'],
    allow_taxable_gain_sales: [
      'NEVER',
      'DRIFT_THRESHOLD',
      'WITHIN_BUDGET',
      'ALWAYS',
    ],
    wash_sale_policy: ['FLAG_ONLY', 'AVOID_SAME_SYMBOL', 'STRICT_AVOID'],
    asset_location_strength: ['LIGHT', 'BALANCED', 'STRONG'],
    solver_fallback_policy: ['HEURISTIC', 'NONE'],
    app_mode: ['LOCAL'],
    config_backend: ['SQLITE', 'CSV', 'YAML', 'JSON'],
    filing_status: ['MFJ', 'Single', 'HOH', 'MFS'],
    survivor_filing_status: ['Single', 'HOH', 'MFS'],
    roth_conversion_policy: [
      'optimize_terminal_tax',
      'fill_to_bracket',
      'fill_to_irmaa',
      'fixed_dollar',
      'none',
    ],
    mc_engine_mode: ['advanced_exact_scalar', 'quick_vectorized'],
  };

  if (section === 'schema' && label === 'type') {
    return [
      'text',
      'choice',
      'boolean',
      'date',
      'percent',
      'integer',
      'year',
      'number',
      'currency',
      'dollars',
      'path',
      'secret',
    ];
  }

  if (label === 'roth_target_bracket_rate') {
    return ['10.00%', '12.00%', '22.00%', '24.00%', '32.00%', '35.00%', '37.00%'];
  }

  if (fixed[label]) return fixed[label];

  if (['yes/no', 'boolean', 'true/false'].includes(units.toLowerCase())) {
    return ['TRUE', 'FALSE'];
  }

  if (/^.+\|.+$/.test(units)) {
    return units.split('|').map((x) => x.trim()).filter(Boolean);
  }

  return null;
}

/**
 * Format choice value for display
 * @param {string} label - Setting label
 * @param {string} value - Choice value
 * @returns {string} Formatted display text
 */
export function choiceDisplay(label, value) {
  const v = String(value);

  if (label === 'mc_engine_mode') {
    const m = {
      advanced_exact_scalar: 'Advanced Exact Scalar (slower, advisor-ready)',
      quick_vectorized: 'Quick Vectorized (faster, approximate)',
      exact_scalar: 'Advanced Exact Scalar (slower, advisor-ready)',
      vectorized: 'Quick Vectorized (faster, approximate)',
    };
    return m[v] || v;
  }

  if (label === 'roth_irmaa_target_tier') {
    const m = {
      TIER_1: 'Tier 1 — MFJ $212,000 / Single $106,000',
      TIER_2: 'Tier 2 — MFJ $268,000 / Single $133,000',
      TIER_3: 'Tier 3 — MFJ $335,000 / Single $167,000',
      TIER_4: 'Tier 4 — MFJ $402,000 / Single $200,000',
      TIER_5: 'Tier 5 — MFJ $750,000 / Single $500,000',
    };
    return m[v] || v;
  }

  if (label === 'roth_target_bracket_rate') {
    return v.replace('.00%', '%') + ' bracket';
  }

  return v.replace(/_/g, ' ');
}

/**
 * Get dependency rank for sorting (00 = highest priority)
 * @param {string} key - Setting key
 * @returns {string} Rank string for sorting
 */
export function adminDependencyRank(key) {
  const l = String(key || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_');

  if (
    [
      'enabled',
      'active',
      'use',
      'mode',
      'policy',
      'policy_type',
      'type',
      'mc_engine_mode',
      'roth_conversion_policy',
      'allocation_selection_mode',
    ].includes(l)
  ) {
    return '00';
  }

  if (
    l.includes('policy') ||
    l.includes('strategy') ||
    l.endsWith('_mode') ||
    l.includes('method')
  ) {
    return '01';
  }

  if (
    l.includes('target') ||
    l.includes('bracket') ||
    l.includes('tier') ||
    l.includes('guardrail')
  ) {
    return '02';
  }

  if (
    l.includes('amount') ||
    l.includes('pct') ||
    l.includes('percent') ||
    l.includes('rate') ||
    l.includes('headroom')
  ) {
    return '03';
  }

  if (
    l.includes('start') ||
    l.includes('end') ||
    l.includes('year') ||
    l.includes('date') ||
    l.includes('window')
  ) {
    return '04';
  }

  return '50';
}

/**
 * Filter setting rows by criteria
 * @param {array} rows - CSV rows
 * @param {object} opts - Filter options (filterKeys, filterSections, filterSubsections)
 * @returns {array} Filtered rows with indices
 */
export function filteredSettingRows(rows, opts = {}) {
  return rows
    .map((r, i) => ({ r, i }))
    .filter((x) => {
      if (!isSetting(x.r)) return false;

      const sec = rowCell(x.r, 0),
        sub = rowCell(x.r, 1),
        key = rowCell(x.r, 2);

      if (
        opts.filterKeys &&
        opts.filterKeys.length &&
        !opts.filterKeys.includes(key)
      ) {
        return false;
      }

      if (
        opts.filterSections &&
        opts.filterSections.length &&
        !opts.filterSections.includes(sec)
      ) {
        return false;
      }

      if (
        opts.filterSubsections &&
        opts.filterSubsections.length &&
        !opts.filterSubsections.includes(sub)
      ) {
        return false;
      }

      return true;
    });
}

/**
 * Normalize string to snake_case
 * @param {string} s - Input string
 * @returns {string} Normalized string
 */
export function adminNorm(s) {
  return String(s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_');
}

/**
 * Summarize row counts and key settings
 * @param {array} rows - CSV rows
 * @returns {object} Summary with counts and key values
 */
export function summarizeRows(rows) {
  const settings = rows.filter(isSetting);
  const sections = new Set(settings.map((r) => rowCell(r, 0)));
  const pricing = settings.find((r) => rowCell(r, 2) === 'pricing_mode');
  const opt = settings.find((r) => rowCell(r, 2) === 'trade_optimizer_mode');

  return {
    sections: sections.size,
    settings: settings.length,
    pricing_mode: pricing ? rowCell(pricing, 3) : 'n/a',
    trade_optimizer: opt ? rowCell(opt, 3) : 'n/a',
  };
}

/**
 * Get column helper note
 * @param {string} profile - CSV profile type
 * @param {string} col - Column name
 * @returns {string} Helper note for column
 */
export function tableColumnNote(profile, col) {
  const p = {
    section: 'Grouping section. Keeps related inputs together.',
    subsection: 'Subgroup within the section.',
    label: 'Setting key used by the model.',
    value: 'Editable value used by workbook/projection logic.',
    units: 'Expected type or units.',
    notes: 'Helper note explaining the setting impact.',
  }[col];

  if (p) return p;

  return 'Editable field. Review downstream workbook impact before saving.';
}
