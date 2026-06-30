from __future__ import annotations
import sys as _sys


# ===== BEGIN tax_data.py =====

"""
tax_data.py — Externalized tax reference tables, state tax library,
annuity calibration defaults, and provenance registry.

All tax-year-specific constants are tagged with the year they apply and
their authoritative source. The engine reads .value; the Methodology sheet
reads all three fields (value, tax_year, source).

Created as part of Section 9 generalization (v3.1).
"""

import os
import csv
import datetime

# ─────────────────────────────────────────────────────────────────────────────
# FILING STATUSES
# ─────────────────────────────────────────────────────────────────────────────

TAX_REFERENCE_YEAR = int(os.environ.get('TAX_REFERENCE_YEAR') or os.environ.get('RETIREMENT_TAX_YEAR') or datetime.date.today().year)
# Embedded statutory tables are intentionally tagged with their own vintages;
# do not inflate all tables from the current calendar year by accident.
FEDERAL_BRACKETS_VALUE_YEAR = int(os.environ.get('FEDERAL_BRACKETS_VALUE_YEAR') or 2025)
STANDARD_DEDUCTION_VALUE_YEAR = int(os.environ.get('STANDARD_DEDUCTION_VALUE_YEAR') or 2025)
IRMAA_TIERS_VALUE_YEAR = int(os.environ.get('IRMAA_TIERS_VALUE_YEAR') or 2025)
LTCG_BRACKETS_VALUE_YEAR = int(os.environ.get('LTCG_BRACKETS_VALUE_YEAR') or 2025)
SS_WAGE_BASE_VALUE_YEAR = int(os.environ.get('SS_WAGE_BASE_VALUE_YEAR') or 2025)
SALT_REVERSION_YEAR = TAX_REFERENCE_YEAR + 4

FILING_STATUSES = ['MFJ', 'Single', 'HOH', 'MFS']

# ─────────────────────────────────────────────────────────────────────────────
# DATED FEDERAL TAX-LAW DATASET
# ─────────────────────────────────────────────────────────────────────────────


def _load_federal_tax_law_tables(reference_year=None):
    """Load all federal tax-law tables from reference_data/tax_law_v10.json.

    There are intentionally no embedded federal bracket, deduction, NIIT, LTCG,
    IRMAA, SALT, or Social Security wage-base tables in this module.  The local
    dated dataset is the sole source of statutory federal values; CSV remains a
    migration/import adapter below.
    """
    try:
        try:
            from .tax_law import load_tax_law_dataset
        except Exception:
            from src.tax_law import load_tax_law_dataset
        ds = load_tax_law_dataset()
        year = int(reference_year or TAX_REFERENCE_YEAR)
        engine = ds.as_engine_tables(year)
        provenance = {}
        for item in ds.values:
            if item.effective_year <= year and (item.expires_year is None or year <= item.expires_year):
                provenance[f'{item.name}_{item.filing_status.lower()}'] = {
                    'tax_year': item.effective_year,
                    'source': item.source,
                }
        provenance['_ordinary_bracket_effective_year'] = {
            'tax_year': max((b.effective_year for b in ds.brackets if b.bracket_type == 'ordinary'), default=year),
            'source': ds.generated_from,
        }
        return engine, provenance, ds.generated_from
    except Exception as exc:
        raise RuntimeError(f'Federal tax-law dataset could not be loaded: {exc}') from exc


_FEDERAL_ENGINE_TABLES, _FEDERAL_DATASET_PROVENANCE, _FEDERAL_DATASET_SOURCE = _load_federal_tax_law_tables(TAX_REFERENCE_YEAR)
FEDERAL_BRACKETS_BASE_YEAR = dict(_FEDERAL_ENGINE_TABLES.get('ordinary_brackets') or {})
FEDERAL_BRACKETS_VALUE_YEAR = int(_FEDERAL_DATASET_PROVENANCE.get('_ordinary_bracket_effective_year', {}).get('tax_year', TAX_REFERENCE_YEAR))
STANDARD_DEDUCTION_BASE_YEAR = dict(_FEDERAL_ENGINE_TABLES.get('standard_deduction') or {})
STANDARD_DEDUCTION_VALUE_YEAR = max((meta['tax_year'] for key, meta in _FEDERAL_DATASET_PROVENANCE.items() if key.startswith('standard_deduction_')), default=TAX_REFERENCE_YEAR)
STANDARD_DEDUCTION_OVER65_BASE_YEAR = dict(_FEDERAL_ENGINE_TABLES.get('standard_deduction_over65') or {})
NIIT_THRESHOLD = dict(_FEDERAL_ENGINE_TABLES.get('niit_threshold') or {})
IRMAA_TIERS_BASE_YEAR = {k: list(v) for k, v in (_FEDERAL_ENGINE_TABLES.get('irmaa_tiers') or {}).items()}
IRMAA_TIERS_VALUE_YEAR = max((meta['tax_year'] for key, meta in _FEDERAL_DATASET_PROVENANCE.items() if key.startswith('irmaa_tier')), default=TAX_REFERENCE_YEAR)
LTCG_BRACKETS_BASE_YEAR = dict(_FEDERAL_ENGINE_TABLES.get('ltcg_brackets') or {})
LTCG_BRACKETS_VALUE_YEAR = max((meta['tax_year'] for key, meta in _FEDERAL_DATASET_PROVENANCE.items() if key.startswith('ltcg_')), default=TAX_REFERENCE_YEAR)
SS_WAGE_BASE_VALUE_YEAR = TAX_REFERENCE_YEAR
SALT_REVERSION_YEAR = TAX_REFERENCE_YEAR + 4

TAX_YEAR_PROVENANCE = {
    'federal_brackets': {'tax_year': FEDERAL_BRACKETS_VALUE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'standard_deduction': {'tax_year': STANDARD_DEDUCTION_VALUE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'standard_deduction_over65': {'tax_year': STANDARD_DEDUCTION_VALUE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'niit_threshold': {'tax_year': TAX_REFERENCE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'irmaa_tiers': {'tax_year': IRMAA_TIERS_VALUE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'ltcg_brackets': {'tax_year': LTCG_BRACKETS_VALUE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'salt_schedule': {'tax_year': TAX_REFERENCE_YEAR, 'source': _FEDERAL_DATASET_SOURCE},
    'ss_wage_base': {'tax_year': max((meta['tax_year'] for key, meta in _FEDERAL_DATASET_PROVENANCE.items() if key.startswith('ss_wage_base')), default=TAX_REFERENCE_YEAR), 'source': _FEDERAL_DATASET_SOURCE},
}


def tax_table_currency_warnings(reference_year=None, max_lag_years=1):
    """Return warnings when the dated tax-law dataset is stale."""
    ref = int(reference_year or TAX_REFERENCE_YEAR)
    warnings = []
    for key, meta in TAX_YEAR_PROVENANCE.items():
        try:
            yr = int(meta.get('tax_year'))
        except Exception:
            continue
        if abs(ref - yr) > int(max_lag_years):
            warnings.append(f'{key} table vintage {yr} differs from reference year {ref}')
    return warnings


# ─────────────────────────────────────────────────────────────────────────────
# STATE TAX LIBRARY (defaults — overridden by state_tax.csv if present)
# ─────────────────────────────────────────────────────────────────────────────

STATE_TAX_DEFAULTS = {
    'Illinois':       {'rate': 0.0495, 'type': 'flat', 'exempt_retirement': True,
                       'exempt_ss': True, 'prop_rate': 0.0217, 'sales_rate': 0.0875,
                       'estate': True, 'estate_exempt': 4_000_000,
                       'retirement_exempt_over_65': 0,
                       'source': 'IL 35 ILCS 5/203'},
    'Indiana':       {'rate': 0.0305, 'type': 'flat', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0087, 'sales_rate': 0.0700,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'IN Department of Revenue flat individual income tax; verify current local/county rates separately'},
    'Florida':        {'rate': 0.0,    'type': 'none', 'exempt_retirement': True,
                       'exempt_ss': True, 'prop_rate': 0.0083, 'sales_rate': 0.0707,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'FL Constitution Art. VII §5'},
    'Texas':          {'rate': 0.0,    'type': 'none', 'exempt_retirement': True,
                       'exempt_ss': True, 'prop_rate': 0.0180, 'sales_rate': 0.0820,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'TX Constitution Art. VIII'},
    'Tennessee':      {'rate': 0.0,    'type': 'none', 'exempt_retirement': True,
                       'exempt_ss': True, 'prop_rate': 0.0071, 'sales_rate': 0.0955,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'TN Code §67-2-104 (Hall Tax repealed 2021)'},
    'North Carolina': {'rate': 0.045,  'type': 'flat', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0085, 'sales_rate': 0.0700,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'NC GS §105-153.7'},
    'Arizona':        {'rate': 0.025,  'type': 'flat', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0063, 'sales_rate': 0.0840,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'ARS §43-1011 (flat rate eff. 2023)'},
    'Colorado':       {'rate': 0.044,  'type': 'flat', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0055, 'sales_rate': 0.0770,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 24_000,
                       'source': 'CRS §39-22-104; §39-22-104(4)(f)'},
    'Nevada':         {'rate': 0.0,    'type': 'none', 'exempt_retirement': True,
                       'exempt_ss': True, 'prop_rate': 0.0055, 'sales_rate': 0.0823,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'NV Constitution Art. 10 §1'},
    'California':     {'rate': 0.093,  'type': 'graduated', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0073, 'sales_rate': 0.0875,
                       'estate': False, 'estate_exempt': 0,
                       'retirement_exempt_over_65': 0,
                       'source': 'CA Rev. & Tax Code §17041'},
    'New York':       {'rate': 0.0685, 'type': 'graduated', 'exempt_retirement': False,
                       'exempt_ss': True, 'prop_rate': 0.0168, 'sales_rate': 0.0800,
                       'estate': True, 'estate_exempt': 6_940_000,
                       'retirement_exempt_over_65': 20_000,
                       'source': 'NY Tax Law §601; §612(c)(3-a)'},
}


def _parse_bool(s):
    """Parse a boolean-ish string."""
    if isinstance(s, bool):
        return s
    return str(s).strip().upper() in ('TRUE', 'YES', '1', 'T')


def _parse_float(s, default=0.0):
    """Parse a numeric string, stripping $, %, commas."""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace('$', '').replace(',', '')
    if s.endswith('%'):
        try:
            return float(s[:-1]) / 100.0
        except ValueError:
            return default
    try:
        return float(s)
    except ValueError:
        return default


def load_state_tax(search_dirs=None):
    """Load state tax rules. Overlays state_tax.csv onto STATE_TAX_DEFAULTS.
    
    CSV columns: state,rate,type,exempt_retirement,exempt_ss,prop_rate,
                 sales_rate,estate,estate_exempt,retirement_exempt_over_65,source
    
    Returns: dict {state_name: {rule_dict}}
    """
    rules = {k: dict(v) for k, v in STATE_TAX_DEFAULTS.items()}  # deep copy defaults
    
    if search_dirs is None:
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_dirs = [_project_root, os.getcwd(), '/mnt/user-data/outputs']
    
    csv_path = None
    for d in search_dirs:
        p = os.path.join(d, 'reference_data/state_tax.csv')
        if os.path.exists(p):
            csv_path = p
            break
    
    if csv_path:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                state = (row.get('state', '') or '').strip()
                if not state or state.startswith('#'):
                    continue
                rules[state] = {
                    'rate':                     _parse_float(row.get('rate', '0')),
                    'type':                     (row.get('type', 'flat') or 'flat').strip(),
                    'exempt_retirement':         _parse_bool(row.get('exempt_retirement', 'FALSE')),
                    'exempt_ss':                 _parse_bool(row.get('exempt_ss', 'TRUE')),
                    'prop_rate':                 _parse_float(row.get('prop_rate', '0')),
                    'sales_rate':                _parse_float(row.get('sales_rate', '0')),
                    'estate':                    _parse_bool(row.get('estate', 'FALSE')),
                    'estate_exempt':             _parse_float(row.get('estate_exempt', '0')),
                    'retirement_exempt_over_65': _parse_float(row.get('retirement_exempt_over_65', '0')),
                    'source':                    (row.get('source', '') or '').strip(),
                }
    
    return rules


def load_tax_constants(search_dirs=None):
    """Load tax constant overrides from tax_constants.csv.
    
    CSV columns: key, tax_year, value, source
    Returns: dict {key: {'value': float, 'tax_year': int, 'source': str}}
    
    Supported keys (overlaid onto module-level defaults):
        std_ded_mfj, std_ded_single, std_ded_hoh, std_ded_mfs,
        over65_add_mfj, over65_add_single, over65_add_hoh, over65_add_mfs,
        niit_threshold_mfj, niit_threshold_single, niit_threshold_hoh, niit_threshold_mfs,
        ss_wage_base
    """
    registry = {}

    # v10 primary path: tax-law values are loaded from the dated local dataset.
    # tax_constants.csv remains a compatibility/import adapter below.
    try:
        try:
            from .tax_law import load_tax_law_dataset
        except Exception:
            from src.tax_law import load_tax_law_dataset
        ds = load_tax_law_dataset()
        engine = ds.as_engine_tables(TAX_REFERENCE_YEAR)
        for filing, val in engine.get('standard_deduction', {}).items():
            if filing in STANDARD_DEDUCTION_BASE_YEAR:
                STANDARD_DEDUCTION_BASE_YEAR[filing] = val
        for filing, val in engine.get('standard_deduction_over65', {}).items():
            if filing in STANDARD_DEDUCTION_OVER65_BASE_YEAR:
                STANDARD_DEDUCTION_OVER65_BASE_YEAR[filing] = val
        for filing, val in engine.get('niit_threshold', {}).items():
            if filing in NIIT_THRESHOLD:
                NIIT_THRESHOLD[filing] = val
        for filing, table in engine.get('ordinary_brackets', {}).items():
            FEDERAL_BRACKETS_BASE_YEAR[filing] = table
        for filing, table in engine.get('ltcg_brackets', {}).items():
            LTCG_BRACKETS_BASE_YEAR[filing] = table
        for filing, table in engine.get('irmaa_tiers', {}).items():
            IRMAA_TIERS_BASE_YEAR[filing] = list(table)
        for item in ds.values:
            key = f"{item.name}_{item.filing_status.lower()}"
            registry[key] = {'value': item.value, 'tax_year': item.effective_year, 'source': item.source}
        registry['_v10_tax_law_dataset'] = {'value': len(ds.values), 'tax_year': max(v.effective_year for v in ds.values), 'source': ds.generated_from}
        return registry
    except Exception:
        pass

    if search_dirs is None:
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_dirs = [_project_root, os.getcwd(), '/mnt/user-data/outputs']
    
    csv_path = None
    for d in search_dirs:
        p = os.path.join(d, 'reference_data/tax_constants.csv')
        if os.path.exists(p):
            csv_path = p
            break
    
    if csv_path:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get('key', '') or '').strip()
                if not key or key.startswith('#'):
                    continue
                registry[key] = {
                    'value':    _parse_float(row.get('value', '0')),
                    'tax_year': int(_parse_float(row.get('tax_year', str(TAX_REFERENCE_YEAR)))),
                    'source':   (row.get('source', '') or '').strip(),
                }
    
    # Apply overrides to module-level defaults
    for filing in FILING_STATUSES:
        fk = filing.lower()
        sd_key = f'std_ded_{fk}'
        if sd_key in registry:
            STANDARD_DEDUCTION_BASE_YEAR[filing] = registry[sd_key]['value']
        o65_key = f'over65_add_{fk}'
        if o65_key in registry:
            STANDARD_DEDUCTION_OVER65_BASE_YEAR[filing] = registry[o65_key]['value']
        niit_key = f'niit_threshold_{fk}'
        if niit_key in registry:
            NIIT_THRESHOLD[filing] = registry[niit_key]['value']
    
    return registry


# ─────────────────────────────────────────────────────────────────────────────
# ANNUITY CALIBRATION DEFAULTS
# Expose the purchase-rate-by-age curve and reserve-decay constants so any
# carrier's product can be matched by editing values rather than code.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_ANNUITY_CALIB = {
    # Purchase rate curve: piecewise linear segments [(age_start, base_rate, slope_per_year)]
    # annuity_purchase_rate(age) = base + slope * (age - age_start) within each segment
    'purchase_rate_segments': [
        {'age_start':  0, 'age_end': 68, 'base_rate': 0.050, 'slope': 0.000},
        {'age_start': 68, 'age_end': 75, 'base_rate': 0.050, 'slope': 0.002},
        {'age_start': 75, 'age_end': 85, 'base_rate': 0.064, 'slope': 0.005},
        {'age_start': 85, 'age_end': 95, 'base_rate': 0.114, 'slope': 0.007},
        {'age_start': 95, 'age_end': 999,'base_rate': 0.184, 'slope': 0.015},
    ],
    # Reserve decay model constants
    'reserve_decay_rate':        0.975,   # annual decay factor (years 0-6)
    'reserve_decay_period':      6,       # years of initial decay
    'mortality_credit_boost':    1.29,    # multiplier at mortality credit onset
    'post_credit_decay_rate':    0.96,    # annual decay after mortality credit (years 7-22)
    'post_credit_decay_period': 16,       # years of post-credit decay (6+16=22)
    'late_life_growth_rate':     1.07,    # annual growth factor after year 22 (longevity credits)
}


def annuity_purchase_rate_from_calib(age, calib=None):
    """Compute purchase rate from calibration segments.
    Falls back to DEFAULT_ANNUITY_CALIB if calib is None."""
    if calib is None:
        calib = DEFAULT_ANNUITY_CALIB
    segments = calib.get('purchase_rate_segments', DEFAULT_ANNUITY_CALIB['purchase_rate_segments'])
    for seg in segments:
        if age < seg['age_end']:
            return seg['base_rate'] + seg['slope'] * max(0, age - seg['age_start'])
    # Past all segments — use last segment's formula
    last = segments[-1]
    return last['base_rate'] + last['slope'] * (age - last['age_start'])


def annuity_reserve_from_calib(reserve_start, yr_offset, calib=None):
    """Compute actuarial reserve using calibration constants.
    Falls back to DEFAULT_ANNUITY_CALIB if calib is None."""
    if calib is None:
        calib = DEFAULT_ANNUITY_CALIB
    
    decay_rate    = calib.get('reserve_decay_rate', 0.975)
    decay_period  = calib.get('reserve_decay_period', 6)
    mc_boost      = calib.get('mortality_credit_boost', 1.29)
    post_decay    = calib.get('post_credit_decay_rate', 0.96)
    post_period   = calib.get('post_credit_decay_period', 16)
    late_growth   = calib.get('late_life_growth_rate', 1.07)
    
    if yr_offset <= decay_period:
        return reserve_start * (decay_rate ** yr_offset)
    r_dp = reserve_start * (decay_rate ** decay_period)
    transition = decay_period + post_period
    if yr_offset <= transition:
        return r_dp * mc_boost * (post_decay ** (yr_offset - decay_period))
    r_tr = r_dp * mc_boost * (post_decay ** post_period)
    return r_tr * (late_growth ** (yr_offset - transition))


# ─────────────────────────────────────────────────────────────────────────────
# ROTH CONVERSION POLICIES
# ─────────────────────────────────────────────────────────────────────────────

ROTH_POLICIES = ['optimize_terminal_tax', 'optimize', 'balanced_optimize', 'terminal_tax_optimize', 'fill_to_bracket', 'fill_to_irmaa', 'fixed_dollar', 'none']

# ─────────────────────────────────────────────────────────────────────────────
# CASCADE ACCOUNTS (discretionary, gap-driven)
# Constraint: 'Trust' must precede 'Roth' (LTCG tax on trust draws is
# funded by Roth; reversing this produces incorrect tax results).
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_CASCADE_ORDER = ['IRA', 'Trust', 'Roth', 'Home']
VALID_CASCADE_ACCOUNTS = {'IRA', 'Trust', 'Roth', 'Home'}

def validate_cascade_order(order):
    """Validate a cascade order list. Returns (cleaned_list, warnings).
    Enforces: Trust before Roth (LTCG coupling)."""
    warnings = []
    cleaned = []
    for item in order:
        item = item.strip()
        if item in VALID_CASCADE_ACCOUNTS:
            if item not in cleaned:
                cleaned.append(item)
        else:
            warnings.append(f'Unknown cascade account "{item}" — ignored')
    
    # Ensure all required accounts are present (append missing at end)
    for acct in DEFAULT_CASCADE_ORDER:
        if acct not in cleaned:
            cleaned.append(acct)
            warnings.append(f'Added missing cascade account "{acct}" at end')
    
    # Enforce Trust before Roth
    ti = cleaned.index('Trust')
    ri = cleaned.index('Roth')
    if ti > ri:
        cleaned.remove('Trust')
        cleaned.insert(ri, 'Trust')
        warnings.append('Moved Trust before Roth (LTCG tax coupling requires this order)')
    
    return cleaned, warnings

# ===== END tax_data.py =====
