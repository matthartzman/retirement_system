/**
 * Unit tests for admin_ui.mjs pure functions.
 *
 * Phase B Batch 4: Infrastructure/Admin tests conversion
 * Converts source-text matching assertions to behavior-based testing.
 *
 * Run with: npm test
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import {
  rowCell,
  isHeader,
  isComment,
  isSetting,
  cleanComment,
  titleCaseLabel,
  rowsToCsv,
  parseCsv,
  choicesFor,
  choiceDisplay,
  adminDependencyRank,
  filteredSettingRows,
  adminNorm,
  summarizeRows,
  tableColumnNote,
} from '../../frontend/js/modules/admin_ui.mjs';

describe('rowCell', () => {
  test('extracts cell value from row array', () => {
    const row = ['Section', 'Subsection', 'label', 'value', 'units'];
    assert.equal(rowCell(row, 0), 'Section');
    assert.equal(rowCell(row, 2), 'label');
    assert.equal(rowCell(row, 4), 'units');
  });

  test('returns empty string for missing index', () => {
    const row = ['Section', 'Subsection'];
    assert.equal(rowCell(row, 5), '');
  });

  test('returns empty string for null or undefined row', () => {
    assert.equal(rowCell(null, 0), '');
    assert.equal(rowCell(undefined, 0), '');
  });

  test('converts number to string', () => {
    const row = ['Section', 100, 'label'];
    assert.equal(rowCell(row, 1), '100');
  });
});

describe('isHeader', () => {
  test('identifies valid CSV header row', () => {
    const header = ['section', 'subsection', 'label', 'value'];
    assert.equal(isHeader(header), true);
  });

  test('handles case-insensitive matching', () => {
    const header = ['SECTION', 'SUBSECTION', 'label', 'value'];
    assert.equal(isHeader(header), true);
  });

  test('rejects rows with wrong column names', () => {
    const notHeader = ['Section', 'Subset', 'label', 'value'];
    assert.equal(isHeader(notHeader), false);
  });

  test('rejects short rows', () => {
    const short = ['section'];
    assert.equal(isHeader(short), false);
  });
});

describe('isComment', () => {
  test('identifies comment rows starting with #', () => {
    const comment = ['# This is a comment', 'value2'];
    assert.equal(isComment(comment), true);
  });

  test('handles leading whitespace - is trimmed so # is at start', () => {
    const comment = ['  # Comment', 'value2'];
    assert.equal(isComment(comment), true); // trim removes leading spaces, then # is at start
  });

  test('rejects non-comment rows', () => {
    const normal = ['Section', 'Subsection'];
    assert.equal(isComment(normal), false);
  });

  test('handles empty or null rows', () => {
    assert.equal(isComment([]), false);
    assert.equal(isComment(null), false);
  });
});

describe('isSetting', () => {
  test('identifies valid setting rows', () => {
    const setting = ['System', 'Pricing', 'pricing_mode', 'CACHE', '%', 'note'];
    assert.equal(isSetting(setting), true);
  });

  test('rejects header rows', () => {
    const header = ['section', 'subsection', 'label', 'value'];
    assert.equal(isSetting(header), false);
  });

  test('rejects comment rows', () => {
    const comment = ['# comment', 'value2'];
    assert.equal(isSetting(comment), false);
  });

  test('rejects rows with fewer than 4 columns', () => {
    const short = ['System', 'Pricing', 'pricing_mode'];
    assert.equal(isSetting(short), false);
  });

  test('rejects empty first column (after trim)', () => {
    const empty = ['  ', 'Pricing', 'pricing_mode', 'value'];
    assert.ok(!isSetting(empty)); // falsy when first column is empty after trim
  });
});

describe('cleanComment', () => {
  test('removes leading # and dashes', () => {
    assert.equal(cleanComment('# --- comment ---'), 'comment');
    assert.equal(cleanComment('# comment'), 'comment');
  });

  test('removes trailing dashes', () => {
    assert.equal(cleanComment('# comment ---'), 'comment');
  });

  test('preserves leading whitespace in input (not trimmed by function)', () => {
    assert.equal(cleanComment('  # comment  '), '# comment');
  });

  test('handles null or empty input', () => {
    assert.equal(cleanComment(null), '');
    assert.equal(cleanComment(undefined), '');
    assert.equal(cleanComment(''), '');
  });

  test('preserves text without comment markers', () => {
    assert.equal(cleanComment('plain text'), 'plain text');
  });
});

describe('titleCaseLabel', () => {
  test('converts snake_case to Title Case', () => {
    assert.equal(titleCaseLabel('pricing_mode'), 'Pricing Mode');
    assert.equal(titleCaseLabel('max_build_seconds'), 'Max Build Seconds');
  });

  test('replaces acronyms in title case', () => {
    assert.equal(titleCaseLabel('csv_file'), 'CSV File');
    assert.equal(titleCaseLabel('api_key'), 'API Key');
    assert.equal(titleCaseLabel('ira_balance'), 'IRA Balance');
  });

  test('uses hardcoded label map for known keys', () => {
    assert.equal(
      titleCaseLabel('annual_premium_base_year'),
      'Pre-65 Healthcare Premium (annual per person)'
    );
    assert.equal(titleCaseLabel('mc_engine_mode'), 'Monte Carlo Engine');
  });

  test('special replacements for W2 and K1', () => {
    assert.equal(titleCaseLabel('w2_income'), 'W-2 Income');
    assert.equal(titleCaseLabel('k1_loss'), 'K-1 Loss');
  });

  test('handles null or empty input', () => {
    assert.equal(titleCaseLabel(null), '');
    assert.equal(titleCaseLabel(undefined), '');
    assert.equal(titleCaseLabel(''), '');
  });
});

describe('rowsToCsv', () => {
  test('converts array of rows to CSV string', () => {
    const rows = [
      ['Section', 'Subsection', 'Label', 'Value'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
    ];
    const csv = rowsToCsv(rows);
    assert.ok(csv.includes('Section,Subsection,Label,Value'));
    assert.ok(csv.includes('System,Pricing,pricing_mode,CACHE'));
  });

  test('quotes values containing commas', () => {
    const rows = [['Name', 'Description'], ['Test', 'Value, with comma']];
    const csv = rowsToCsv(rows);
    assert.ok(csv.includes('"Value, with comma"'));
  });

  test('escapes quotes by doubling them', () => {
    const rows = [['Name', 'Value'], ['Test', 'Value "quoted"']];
    const csv = rowsToCsv(rows);
    assert.ok(csv.includes('"Value ""quoted"""'));
  });

  test('quotes values containing newlines', () => {
    const rows = [['Name'], ['Multi\nline']];
    const csv = rowsToCsv(rows);
    assert.ok(csv.includes('"Multi\nline"'));
  });

  test('ends with newline', () => {
    const rows = [['A', 'B']];
    const csv = rowsToCsv(rows);
    assert.ok(csv.endsWith('\n'));
  });

  test('handles empty rows', () => {
    const csv = rowsToCsv([]);
    assert.equal(csv, '\n');
  });
});

describe('parseCsv', () => {
  test('parses simple CSV text', () => {
    const csv = 'Section,Subsection,Label\nSystem,Pricing,pricing_mode';
    const rows = parseCsv(csv);
    assert.deepEqual(rows[0], ['Section', 'Subsection', 'Label']);
    assert.deepEqual(rows[1], ['System', 'Pricing', 'pricing_mode']);
  });

  test('handles quoted values with commas', () => {
    const csv = 'Name,Description\nTest,"Value, with comma"';
    const rows = parseCsv(csv);
    assert.equal(rows[1][1], 'Value, with comma');
  });

  test('handles escaped quotes', () => {
    const csv = 'Name,Value\nTest,"Quote: ""exact"""';
    const rows = parseCsv(csv);
    assert.equal(rows[1][1], 'Quote: "exact"');
  });

  test('handles multiline quoted values', () => {
    const csv = 'Name,Description\nTest,"Line 1\nLine 2"';
    const rows = parseCsv(csv);
    assert.equal(rows[1][1], 'Line 1\nLine 2');
  });

  test('handles carriage returns', () => {
    const csv = 'A,B\r\nC,D';
    const rows = parseCsv(csv);
    assert.equal(rows.length, 2);
  });

  test('handles empty input', () => {
    const rows = parseCsv('');
    assert.equal(rows.length, 0);
  });

  test('round-trip CSV parsing and generation', () => {
    const original = [
      ['Section', 'Subsection'],
      ['System', 'Pricing'],
      ['Test', 'Value, with comma'],
    ];
    const csv = rowsToCsv(original);
    const parsed = parseCsv(csv);
    assert.deepEqual(parsed, original);
  });
});

describe('choicesFor', () => {
  test('returns fixed choices for known settings', () => {
    const pricingRow = ['Market Pricing', '', 'pricing_mode', 'CACHE', '', ''];
    const choices = choicesFor(pricingRow);
    assert.deepEqual(choices, ['CACHE', 'LIVE', 'OFFLINE']);
  });

  test('returns roth_target_bracket_rate options', () => {
    const row = ['Roth', '', 'roth_target_bracket_rate', '24%', '', ''];
    const choices = choicesFor(row);
    assert.ok(choices.includes('24.00%'));
    assert.ok(choices.includes('37.00%'));
  });

  test('returns TRUE/FALSE for boolean units', () => {
    const boolRow = ['System', '', 'enabled', 'TRUE', 'yes/no', ''];
    const choices = choicesFor(boolRow);
    assert.deepEqual(choices, ['TRUE', 'FALSE']);
  });

  test('splits pipe-separated units', () => {
    const pipeRow = ['System', '', 'mode', 'A', 'A | B | C', ''];
    const choices = choicesFor(pipeRow);
    assert.deepEqual(choices, ['A', 'B', 'C']);
  });

  test('returns null when no choices available', () => {
    const freeRow = ['System', '', 'custom_key', 'value', 'text', ''];
    const choices = choicesFor(freeRow);
    assert.equal(choices, null);
  });

  test('handles schema type choices', () => {
    const schemaRow = ['schema', '', 'type', 'text', '', ''];
    const choices = choicesFor(schemaRow);
    assert.ok(choices.includes('text'));
    assert.ok(choices.includes('choice'));
    assert.ok(choices.includes('currency'));
  });
});

describe('choiceDisplay', () => {
  test('formats mc_engine_mode display text', () => {
    assert.equal(
      choiceDisplay('mc_engine_mode', 'advanced_exact_scalar'),
      'Advanced Exact Scalar (slower, advisor-ready)'
    );
    assert.equal(
      choiceDisplay('mc_engine_mode', 'quick_vectorized'),
      'Quick Vectorized (faster, approximate)'
    );
  });

  test('formats roth_irmaa_target_tier display', () => {
    assert.ok(
      choiceDisplay('roth_irmaa_target_tier', 'TIER_1').includes('$212,000')
    );
    assert.ok(
      choiceDisplay('roth_irmaa_target_tier', 'TIER_5').includes('$750,000')
    );
  });

  test('formats roth_target_bracket_rate', () => {
    assert.equal(choiceDisplay('roth_target_bracket_rate', '24.00%'), '24% bracket');
  });

  test('replaces underscores with spaces for other labels', () => {
    assert.equal(choiceDisplay('some_label', 'some_value'), 'some value');
  });

  test('returns value unchanged if no special formatting', () => {
    assert.equal(choiceDisplay('unknown', 'PLAIN'), 'PLAIN');
  });
});

describe('adminDependencyRank', () => {
  test('ranks settings in fixed list highest (00)', () => {
    assert.equal(adminDependencyRank('enabled'), '00');
    assert.equal(adminDependencyRank('mc_engine_mode'), '00');
    assert.equal(adminDependencyRank('roth_conversion_policy'), '00');
  });

  test('ranks settings ending with _mode or containing policy (01)', () => {
    assert.equal(adminDependencyRank('pricing_mode'), '01');
    assert.equal(adminDependencyRank('asset_location_strategy'), '01');
  });

  test('ranks target/bracket/tier settings (02)', () => {
    assert.equal(adminDependencyRank('roth_target_bracket_rate'), '02');
    assert.equal(adminDependencyRank('irmaa_guardrail'), '02');
  });

  test('ranks amount/rate settings (03)', () => {
    assert.equal(adminDependencyRank('headroom_usage'), '03');
    assert.equal(adminDependencyRank('tax_rate_pct'), '03');
  });

  test('ranks date/year settings (04)', () => {
    assert.equal(adminDependencyRank('start_year'), '04');
    assert.equal(adminDependencyRank('tax_year'), '04');
  });

  test('ranks unknown settings (50)', () => {
    assert.equal(adminDependencyRank('unknown_key'), '50');
    assert.equal(adminDependencyRank('custom_value'), '50');
  });

  test('handles null input', () => {
    assert.equal(adminDependencyRank(null), '50');
    assert.equal(adminDependencyRank(''), '50');
  });
});

describe('filteredSettingRows', () => {
  test('returns all setting rows without filters', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
      ['System', 'Pricing', 'pricing_timeout', '30'],
    ];
    const result = filteredSettingRows(rows, {});
    assert.equal(result.length, 2);
  });

  test('filters by section', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
      ['Build', 'Timeout', 'max_build_seconds', '900'],
    ];
    const result = filteredSettingRows(rows, { filterSections: ['System'] });
    assert.equal(result.length, 1);
    assert.equal(result[0].r[2], 'pricing_mode');
  });

  test('filters by key', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
      ['System', 'Pricing', 'pricing_timeout', '30'],
    ];
    const result = filteredSettingRows(rows, {
      filterKeys: ['pricing_mode'],
    });
    assert.equal(result.length, 1);
  });

  test('returns row indices', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
    ];
    const result = filteredSettingRows(rows, {});
    assert.equal(result[0].i, 1);
  });

  test('excludes header and comment rows', () => {
    const rows = [
      ['section', 'subsection'],
      ['# comment'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
    ];
    const result = filteredSettingRows(rows, {});
    assert.equal(result.length, 1);
  });
});

describe('adminNorm', () => {
  test('converts to lowercase snake_case', () => {
    assert.equal(adminNorm('PricingMode'), 'pricingmode');
    assert.equal(adminNorm('Pricing Mode'), 'pricing_mode');
  });

  test('replaces non-alphanumeric with underscores', () => {
    assert.equal(adminNorm('pricing-mode'), 'pricing_mode');
    assert.equal(adminNorm('pricing.mode'), 'pricing_mode');
  });

  test('collapses multiple separators', () => {
    assert.equal(adminNorm('pricing---mode'), 'pricing_mode');
  });

  test('handles null or empty', () => {
    assert.equal(adminNorm(null), '');
    assert.equal(adminNorm(''), '');
  });
});

describe('summarizeRows', () => {
  test('counts sections and settings', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'CACHE'],
      ['System', 'Build', 'max_build_seconds', '900'],
      ['Roth', 'Strategy', 'roth_objective_mode', 'BALANCED'],
    ];
    const summary = summarizeRows(rows);
    assert.equal(summary.sections, 2);
    assert.equal(summary.settings, 3);
  });

  test('extracts pricing_mode value', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Pricing', 'pricing_mode', 'LIVE'],
    ];
    const summary = summarizeRows(rows);
    assert.equal(summary.pricing_mode, 'LIVE');
  });

  test('extracts trade_optimizer_mode value', () => {
    const rows = [
      ['section', 'subsection'],
      ['System', 'Rebalancing', 'trade_optimizer_mode', 'GLOBAL_TAX_AWARE'],
    ];
    const summary = summarizeRows(rows);
    assert.equal(summary.trade_optimizer, 'GLOBAL_TAX_AWARE');
  });

  test('uses n/a when values not found', () => {
    const rows = [
      ['section', 'subsection'],
      ['Custom', 'Setting', 'custom_key', 'value'],
    ];
    const summary = summarizeRows(rows);
    assert.equal(summary.pricing_mode, 'n/a');
    assert.equal(summary.trade_optimizer, 'n/a');
  });

  test('handles empty rows', () => {
    const summary = summarizeRows([]);
    assert.equal(summary.sections, 0);
    assert.equal(summary.settings, 0);
  });
});

describe('tableColumnNote', () => {
  test('returns standard column notes', () => {
    assert.equal(tableColumnNote('generic', 'section'), 'Grouping section. Keeps related inputs together.');
    assert.equal(tableColumnNote('generic', 'label'), 'Setting key used by the model.');
  });

  test('returns default note for unknown columns', () => {
    const note = tableColumnNote('generic', 'unknown_col');
    assert.ok(note.includes('Editable field'));
  });

  test('handles null profile by falling through to standard column check', () => {
    const note = tableColumnNote(null, 'section');
    assert.equal(note, 'Grouping section. Keeps related inputs together.');
  });

  test('handles null column', () => {
    const note = tableColumnNote('generic', null);
    assert.ok(note.includes('Editable field'));
  });
});
