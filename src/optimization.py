from __future__ import annotations
import sys as _sys


# ===== BEGIN allocation_optimizer.py =====

"""
allocation_optimizer.py — Mean-variance optimizer with risk tolerance,
human capital, glide path, and non-liquid asset integration.

Computes optimal portfolio allocation targets from the household's actual
situation instead of static defaults.

Created as part of the generic calculator transformation (v3.3).
"""

import numpy as np
from collections import OrderedDict
from pathlib import Path
try:
    from . import allocation_policy as _ap
except ImportError:  # pragma: no cover - allows direct script-style imports
    import allocation_policy as _ap

# ─────────────────────────────────────────────────────────────────────────────
# ASSET CLASS ASSUMPTIONS
# Shipped defaults are long-term capital-market-style planning assumptions.
# They are not live forecasts. Version 7.5.2 can select 1/3/5/10/20/25/30-year
# horizon presets, advanced correlation overrides, or expert CSV uploads.
# User-adjustable via client_data.csv or guided UI
# ─────────────────────────────────────────────────────────────────────────────

ASSET_CLASSES = OrderedDict([
    ('US Large Cap',     {'ret': 0.100, 'vol': 0.150, 'label': 'US Large Cap Equity', 'stock_corr': 1.00, 'education': 'Core broad U.S. large-cap stock-index exposure.'}),
    ('US Mid Cap',       {'ret': 0.105, 'vol': 0.180, 'label': 'US Mid Cap Equity', 'stock_corr': 0.94, 'education': 'U.S. mid-cap equity exposure between large- and small-cap risk/return.'}),
    ('US Small Cap',     {'ret': 0.115, 'vol': 0.220, 'label': 'US Small Cap Equity', 'stock_corr': 0.88, 'education': 'Higher expected-return U.S. small-company exposure; usually higher volatility.'}),
    ('International',    {'ret': 0.080, 'vol': 0.170, 'label': 'International Developed', 'stock_corr': 0.82, 'education': 'Developed non-U.S. equity diversification.'}),
    ('Emerging Markets', {'ret': 0.090, 'vol': 0.220, 'label': 'Emerging Markets', 'stock_corr': 0.72, 'education': 'Higher-growth non-U.S. equity exposure with higher political/currency risk.'}),
    ('Commodities',      {'ret': 0.050, 'vol': 0.180, 'label': 'Broad Commodities', 'stock_corr': 0.15, 'education': 'Broad energy, metals, and agriculture basket; can help inflation shocks.'}),
    ('Bonds',            {'ret': 0.040, 'vol': 0.050, 'label': 'Investment Grade Bonds', 'stock_corr': -0.20, 'education': 'Core duration and credit exposure for ballast and income.'}),
    ('Short-Term Bonds', {'ret': 0.035, 'vol': 0.030, 'label': 'Short-Term Bonds', 'stock_corr': 0.05, 'education': 'Low-duration bond reserve; lower rate sensitivity than broad bonds.'}),
    ('TIPS',             {'ret': 0.040, 'vol': 0.050, 'label': 'Treasury Inflation-Protected Securities', 'stock_corr': 0.10, 'education': 'Inflation-linked U.S. Treasury bonds; helps hedge real spending risk.'}),
    ('Municipal Bonds',  {'ret': 0.035, 'vol': 0.045, 'label': 'Municipal Bonds', 'stock_corr': -0.10, 'education': 'Tax-exempt municipal bond sleeve; after-tax benefit depends on tax bracket and state.'}),
    ('Managed Futures',  {'ret': 0.060, 'vol': 0.100, 'label': 'Managed Futures / Trend Following', 'stock_corr': -0.05, 'education': 'Systematic long/short futures trend following; often diversifies equity bear markets.'}),
    ('Private Credit',   {'ret': 0.070, 'vol': 0.080, 'label': 'Private Credit / Loan-Like Income', 'stock_corr': 0.45, 'education': 'Credit income sleeve with illiquidity and credit-cycle risk; cap conservatively.'}),
    ('REITs',            {'ret': 0.080, 'vol': 0.190, 'label': 'Real Estate (REITs)', 'stock_corr': 0.65, 'education': 'Liquid real estate securities; equity-like drawdowns with income/inflation sensitivity.'}),
    ('Cash',             {'ret': 0.020, 'vol': 0.010, 'label': 'Cash / Money Market', 'stock_corr': -0.05, 'education': 'Liquidity reserve and spending buffer.'}),
])

# Correlation matrix (symmetric, indexed by asset class name)
# Source: 30-year rolling correlations from Vanguard/Morningstar
_CORR = {
    ('US Large Cap', 'US Mid Cap'): 0.94,
    ('US Large Cap', 'US Small Cap'): 0.88,
    ('US Large Cap', 'International'): 0.82,
    ('US Large Cap', 'Emerging Markets'): 0.72,
    ('US Large Cap', 'Commodities'): 0.15,
    ('US Large Cap', 'Bonds'): -0.20,
    ('US Large Cap', 'Short-Term Bonds'): 0.05,
    ('US Large Cap', 'TIPS'): 0.10,
    ('US Large Cap', 'Municipal Bonds'): -0.10,
    ('US Large Cap', 'Managed Futures'): -0.05,
    ('US Large Cap', 'Private Credit'): 0.45,
    ('US Large Cap', 'REITs'): 0.65,
    ('US Large Cap', 'Cash'): -0.05,
    ('US Mid Cap', 'US Small Cap'): 0.92,
    ('US Mid Cap', 'International'): 0.78,
    ('US Mid Cap', 'Emerging Markets'): 0.70,
    ('US Mid Cap', 'Commodities'): 0.18,
    ('US Mid Cap', 'Bonds'): -0.17,
    ('US Mid Cap', 'Short-Term Bonds'): 0.05,
    ('US Mid Cap', 'TIPS'): 0.09,
    ('US Mid Cap', 'Municipal Bonds'): -0.08,
    ('US Mid Cap', 'Managed Futures'): -0.05,
    ('US Mid Cap', 'Private Credit'): 0.48,
    ('US Mid Cap', 'REITs'): 0.68,
    ('US Mid Cap', 'Cash'): -0.05,
    ('US Small Cap', 'International'): 0.75,
    ('US Small Cap', 'Emerging Markets'): 0.70,
    ('US Small Cap', 'Commodities'): 0.20,
    ('US Small Cap', 'Bonds'): -0.15,
    ('US Small Cap', 'Short-Term Bonds'): 0.05,
    ('US Small Cap', 'TIPS'): 0.08,
    ('US Small Cap', 'Municipal Bonds'): -0.07,
    ('US Small Cap', 'Managed Futures'): -0.05,
    ('US Small Cap', 'Private Credit'): 0.50,
    ('US Small Cap', 'REITs'): 0.70,
    ('US Small Cap', 'Cash'): -0.05,
    ('International', 'Emerging Markets'): 0.85,
    ('International', 'Commodities'): 0.25,
    ('International', 'Bonds'): -0.10,
    ('International', 'Short-Term Bonds'): 0.02,
    ('International', 'TIPS'): 0.08,
    ('International', 'Municipal Bonds'): -0.05,
    ('International', 'Managed Futures'): -0.05,
    ('International', 'Private Credit'): 0.40,
    ('International', 'REITs'): 0.55,
    ('International', 'Cash'): -0.03,
    ('Emerging Markets', 'Commodities'): 0.35,
    ('Emerging Markets', 'Bonds'): -0.05,
    ('Emerging Markets', 'Short-Term Bonds'): 0.05,
    ('Emerging Markets', 'TIPS'): 0.10,
    ('Emerging Markets', 'Municipal Bonds'): -0.02,
    ('Emerging Markets', 'Managed Futures'): -0.05,
    ('Emerging Markets', 'Private Credit'): 0.50,
    ('Emerging Markets', 'REITs'): 0.50,
    ('Emerging Markets', 'Cash'): -0.02,
    ('Commodities', 'Bonds'): -0.10,
    ('Commodities', 'Short-Term Bonds'): 0.00,
    ('Commodities', 'TIPS'): 0.20,
    ('Commodities', 'Municipal Bonds'): -0.05,
    ('Commodities', 'Managed Futures'): 0.15,
    ('Commodities', 'Private Credit'): 0.20,
    ('Commodities', 'REITs'): 0.25,
    ('Commodities', 'Cash'): 0.00,
    ('Bonds', 'Short-Term Bonds'): 0.75,
    ('Bonds', 'TIPS'): 0.55,
    ('Bonds', 'Municipal Bonds'): 0.70,
    ('Bonds', 'Managed Futures'): 0.00,
    ('Bonds', 'Private Credit'): 0.35,
    ('Bonds', 'REITs'): 0.20,
    ('Bonds', 'Cash'): 0.50,
    ('Short-Term Bonds', 'TIPS'): 0.35,
    ('Short-Term Bonds', 'Municipal Bonds'): 0.55,
    ('Short-Term Bonds', 'Managed Futures'): 0.00,
    ('Short-Term Bonds', 'Private Credit'): 0.20,
    ('Short-Term Bonds', 'REITs'): 0.10,
    ('Short-Term Bonds', 'Cash'): 0.30,
    ('TIPS', 'Municipal Bonds'): 0.40,
    ('TIPS', 'Managed Futures'): 0.00,
    ('TIPS', 'Private Credit'): 0.25,
    ('TIPS', 'REITs'): 0.25,
    ('TIPS', 'Cash'): 0.10,
    ('Municipal Bonds', 'Managed Futures'): 0.00,
    ('Municipal Bonds', 'Private Credit'): 0.30,
    ('Municipal Bonds', 'REITs'): 0.15,
    ('Municipal Bonds', 'Cash'): 0.35,
    ('Managed Futures', 'Private Credit'): 0.00,
    ('Managed Futures', 'REITs'): 0.00,
    ('Managed Futures', 'Cash'): 0.00,
    ('Private Credit', 'REITs'): 0.35,
    ('Private Credit', 'Cash'): 0.05,
    ('REITs', 'Cash'): 0.05,
}


# Preserve pristine defaults so each build can reset before applying a selected
# horizon/preset/custom file. ASSET_CLASSES and _CORR remain the runtime values
# used by the optimizer and workbook notes.
_BASE_ASSET_CLASSES = OrderedDict((k, dict(v)) for k, v in ASSET_CLASSES.items())
_BASE_CORR = dict(_CORR)
SUPPORTED_CAPITAL_MARKET_HORIZONS = (1, 3, 5, 10, 20, 25, 30)
CAPITAL_MARKET_PRESETS = ("CONSERVATIVE", "BASELINE", "AGGRESSIVE")
CORRELATION_PRESETS = ("LOW", "MODERATE", "HIGH", "STRESS")


def _parse_number(value, default=None):
    """Parse numbers and percentages from CSV/client_data strings."""
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        is_pct = text.endswith('%')
        text = text.replace('%', '').replace(',', '').strip()
        out = float(text)
        if is_pct:
            out /= 100.0
        return out
    except Exception:
        return default


def _normalize_horizon(value):
    h = int(round(_parse_number(value, 30) or 30))
    return min(SUPPORTED_CAPITAL_MARKET_HORIZONS, key=lambda x: abs(x - h))


def _preset_adjustment(preset):
    preset = str(preset or 'BASELINE').upper().strip()
    if preset == 'CONSERVATIVE':
        return -0.010, 1.08
    if preset == 'AGGRESSIVE':
        return 0.010, 0.96
    return 0.0, 1.0


def _horizon_adjustment(asset_class, horizon):
    """Deterministic horizon adjustment for shipped presets.

    These are not market forecasts. They are intentionally transparent planning
    curves: short horizons are treated as less reliable and more volatile; long
    horizons converge toward the shipped long-term baseline.
    """
    # Lower equity/alternatives returns slightly at short horizons because
    # sequence risk dominates planning over one to five years. Cash/short bonds
    # are adjusted much less.
    ret_factor = {
        1: 0.70, 3: 0.78, 5: 0.86, 10: 0.94, 20: 0.98, 25: 0.99, 30: 1.00
    }.get(horizon, 1.00)
    vol_factor = {
        1: 1.22, 3: 1.16, 5: 1.10, 10: 1.04, 20: 0.98, 25: 0.96, 30: 1.00
    }.get(horizon, 1.00)
    low_duration = {'Cash', 'Short-Term Bonds'}
    core_bonds = {'Bonds', 'TIPS'}
    if asset_class in low_duration:
        ret_factor = {1: 1.00, 3: 1.00, 5: 1.00, 10: 0.98, 20: 0.98, 25: 0.98, 30: 0.98}.get(horizon, ret_factor)
        vol_factor = {1: 1.02, 3: 1.02, 5: 1.00, 10: 1.00, 20: 0.98, 25: 0.98, 30: 1.00}.get(horizon, vol_factor)
    elif asset_class in core_bonds:
        ret_factor = {1: 0.95, 3: 0.98, 5: 1.00, 10: 1.00, 20: 0.98, 25: 0.98, 30: 0.98}.get(horizon, ret_factor)
        vol_factor = {1: 1.08, 3: 1.05, 5: 1.02, 10: 1.00, 20: 0.98, 25: 0.98, 30: 1.00}.get(horizon, vol_factor)
    return ret_factor, vol_factor


def _generated_assumption(asset_class, horizon, preset):
    base = _BASE_ASSET_CLASSES[asset_class]
    ret_factor, vol_factor = _horizon_adjustment(asset_class, horizon)
    ret_adj, vol_adj = _preset_adjustment(preset)
    # Keep a small floor/ceiling so the generated preset remains plausible for
    # planning and does not produce pathological optimizer inputs.
    ret = max(-0.02, min(0.18, base['ret'] * ret_factor + ret_adj))
    vol = max(0.005, min(0.40, base['vol'] * vol_factor * vol_adj))
    out = dict(base)
    out['ret'] = ret
    out['vol'] = vol
    out['assumption_source'] = f'generated_{horizon}yr_{str(preset or "BASELINE").upper()}'
    out['assumption_horizon_years'] = horizon
    return out


def reset_capital_market_assumptions():
    """Reset runtime optimizer assumptions to shipped defaults."""
    ASSET_CLASSES.clear()
    for k, v in _BASE_ASSET_CLASSES.items():
        ASSET_CLASSES[k] = dict(v)
    _CORR.clear()
    _CORR.update(_BASE_CORR)


def _resolve_project_path(path_value):
    p = Path(str(path_value or '').strip())
    if not str(p):
        return None
    if p.is_absolute():
        return p
    # optimization.py is in src/, so project root is one directory up.
    root = Path(__file__).resolve().parent.parent
    candidates = [root / p, root / "reference_data" / p.name]
    try:
        from .workspace_context import active_workspace_id, candidate_input_files, first_existing
        found = first_existing(candidate_input_files(p.name, active_workspace_id(), root))
        if found:
            return found
    except Exception:
        pass
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return root / p


def _load_capital_market_assumption_rows(path_value, horizon, preset):
    """Load expert custom return/volatility rows.

    Expected columns: horizon_years,preset,asset_class,expected_return,volatility,
    stock_index_correlation,notes. Rows without matching horizon/preset are
    ignored unless those columns are blank.
    """
    p = _resolve_project_path(path_value)
    if not p or not p.exists():
        return {}
    out = {}
    import csv
    with p.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            cls = _ap.canonical_asset_class((row.get('asset_class') or row.get('class') or '').strip())
            if cls not in _BASE_ASSET_CLASSES:
                continue
            row_h = row.get('horizon_years') or row.get('horizon') or ''
            row_p = (row.get('preset') or row.get('scenario') or '').strip().upper()
            if row_h and _normalize_horizon(row_h) != horizon:
                continue
            if row_p and row_p != str(preset or 'BASELINE').upper():
                continue
            ret = _parse_number(row.get('expected_return') or row.get('return'), None)
            vol = _parse_number(row.get('volatility') or row.get('vol'), None)
            stock_corr = _parse_number(row.get('stock_index_correlation') or row.get('stock_corr'), None)
            out.setdefault(cls, {})
            if ret is not None:
                out[cls]['ret'] = ret
            if vol is not None:
                out[cls]['vol'] = vol
            if stock_corr is not None:
                out[cls]['stock_corr'] = stock_corr
            out[cls]['assumption_source'] = f'custom_file:{p.name}'
            out[cls]['assumption_horizon_years'] = horizon
    return out


def _apply_correlation_preset(preset):
    preset = str(preset or 'MODERATE').upper().strip()
    if preset not in CORRELATION_PRESETS:
        preset = 'MODERATE'
    if preset == 'MODERATE':
        return
    for pair, corr in list(_CORR.items()):
        a, b = pair
        # Preserve diagonal indirectly. Correlation values are off-diagonal only.
        if preset == 'LOW':
            new = corr * 0.85
        elif preset == 'HIGH':
            new = corr + 0.10 if corr >= 0 else corr * 0.70
        else:  # STRESS
            # In stress markets, risky assets often become more correlated and
            # diversifiers may help less. Keep managed futures diversifying.
            if 'Managed Futures' in pair:
                new = min(0.25, corr + 0.10)
            elif corr >= 0:
                new = corr + 0.20
            else:
                new = 0.05
        _CORR[pair] = max(-0.95, min(0.95, new))


def _load_correlation_file(path_value, horizon, preset):
    """Load pairwise correlations from CSV.

    Expected columns: horizon_years,preset,asset_class_a,asset_class_b,correlation.
    Blank horizon/preset rows apply to all selected horizons/presets.
    """
    p = _resolve_project_path(path_value)
    if not p or not p.exists():
        return {}
    import csv
    out = {}
    with p.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            a = _ap.canonical_asset_class((row.get('asset_class_a') or row.get('asset_a') or row.get('a') or '').strip())
            b = _ap.canonical_asset_class((row.get('asset_class_b') or row.get('asset_b') or row.get('b') or '').strip())
            if a not in _BASE_ASSET_CLASSES or b not in _BASE_ASSET_CLASSES or a == b:
                continue
            row_h = row.get('horizon_years') or row.get('horizon') or ''
            row_p = (row.get('preset') or row.get('scenario') or '').strip().upper()
            if row_h and _normalize_horizon(row_h) != horizon:
                continue
            if row_p and row_p != str(preset or 'BASELINE').upper():
                continue
            corr = _parse_number(row.get('correlation'), None)
            if corr is not None:
                out[(a, b)] = max(-0.95, min(0.95, corr))
    return out


def apply_capital_market_config(c):
    """Apply Version 7.5.2 capital-market assumption configuration.

    Order of precedence:
      1. shipped defaults reset
      2. selected horizon/preset generated assumptions
      3. optional expert capital_market_assumptions.csv
      4. per-asset overrides from client_data.csv/UI
      5. correlation preset
      6. optional expert asset_correlations.csv
      7. advanced pairwise correlation rows from client_data.csv/UI
    """
    reset_capital_market_assumptions()
    cfg = c.get('capital_market_config', {}) or {}
    mode = str(cfg.get('assumption_mode') or 'PRESET').upper().strip()
    horizon = _normalize_horizon(cfg.get('horizon_years', 30))
    preset = str(cfg.get('preset') or 'BASELINE').upper().strip()
    if preset not in CAPITAL_MARKET_PRESETS:
        preset = 'BASELINE'

    # Shipped reference-data CSV is authoritative for normal operation.  The
    # hardcoded table above is now only a last-resort fallback for damaged or
    # missing reference data.
    shipped = _load_capital_market_assumption_rows(
        'reference_data/capital_market_assumptions.csv',
        horizon,
        preset,
    )
    if shipped:
        for cls, vals in shipped.items():
            ASSET_CLASSES[cls].update(vals)
    else:
        # Fallback: generated horizon/preset assumptions for every asset class.
        for cls in list(ASSET_CLASSES.keys()):
            ASSET_CLASSES[cls].update(_generated_assumption(cls, horizon, preset))

    if mode == 'CUSTOM_FILE' or bool(cfg.get('use_custom_capital_market_file')):
        custom = _load_capital_market_assumption_rows(
            cfg.get('custom_capital_market_file') or 'capital_market_assumptions.csv',
            horizon,
            preset,
        )
        for cls, vals in custom.items():
            ASSET_CLASSES[cls].update(vals)

    # Correlation preset/file/advanced rows.
    corr_mode = str(cfg.get('correlation_assumption_mode') or 'PRESET').upper().strip()
    corr_preset = str(cfg.get('correlation_preset') or 'MODERATE').upper().strip()
    _apply_correlation_preset(corr_preset)

    if corr_mode == 'CUSTOM_FILE' or bool(cfg.get('use_custom_correlations_file')):
        _CORR.update(_load_correlation_file(
            cfg.get('custom_correlations_file') or 'asset_correlations.csv',
            horizon,
            preset,
        ))
    if corr_mode in {'ADVANCED', 'CUSTOM_FILE'}:
        for pair, corr in (c.get('asset_correlation_overrides') or {}).items():
            if isinstance(pair, str) and '|' in pair:
                a, b = [_ap.canonical_asset_class(x.strip()) for x in pair.split('|', 1)]
                if a in ASSET_CLASSES and b in ASSET_CLASSES and a != b:
                    val = _parse_number(corr, None)
                    if val is not None:
                        _CORR[(a, b)] = max(-0.95, min(0.95, val))
            elif isinstance(pair, tuple) and len(pair) == 2:
                a, b = [_ap.canonical_asset_class(x) for x in pair]
                if a in ASSET_CLASSES and b in ASSET_CLASSES and a != b:
                    val = _parse_number(corr, None)
                    if val is not None:
                        _CORR[(a, b)] = max(-0.95, min(0.95, val))

    return {
        'assumption_mode': mode,
        'horizon_years': horizon,
        'preset': preset,
        'correlation_assumption_mode': corr_mode,
        'correlation_preset': corr_preset,
        'custom_capital_market_file': cfg.get('custom_capital_market_file') or '',
        'shipped_reference_data_loaded': bool(shipped),
        'custom_correlations_file': cfg.get('custom_correlations_file') or '',
    }


def get_correlation(a, b):
    """Get correlation between two asset classes."""
    if a == b:
        return 1.0
    return _CORR.get((a, b), _CORR.get((b, a), 0.0))


def build_covariance_matrix(classes):
    """Build covariance matrix using the shared vectorized fast core."""
    try:
        from .vectorized_fast_core import covariance_matrix
    except Exception:  # pragma: no cover
        from src.vectorized_fast_core import covariance_matrix
    return covariance_matrix(classes, ASSET_CLASSES, _CORR)


# ─────────────────────────────────────────────────────────────────────────────
# RISK TOLERANCE
# ─────────────────────────────────────────────────────────────────────────────

def auto_risk_score(age, withdrawal_rate, funded_ratio):
    """Auto-derive risk tolerance (1-10) from age, withdrawal rate, and funded ratio.

    Args:
        age: current age of primary member
        withdrawal_rate: annual spending / liquid portfolio (0.04 = 4%)
        funded_ratio: PV of guaranteed income / PV of spending needs (0-1+)

    Returns:
        float 1.0-10.0
    """
    # Base: younger = more aggressive
    base = max(1, min(10, 10 - (age - 25) / 7))

    # Adjust for withdrawal rate: high rate → more conservative
    if withdrawal_rate > 0.05:
        base -= 1.5
    elif withdrawal_rate > 0.04:
        base -= 0.5
    elif withdrawal_rate < 0.02:
        base += 1.0

    # Adjust for funded ratio: high guaranteed income → more aggressive
    if funded_ratio > 0.8:
        base += 1.5
    elif funded_ratio > 0.5:
        base += 0.5
    elif funded_ratio < 0.2:
        base -= 0.5

    return max(1.0, min(10.0, base))


def risk_to_equity_pct(risk_score):
    """Map risk score (1-10) to target equity percentage.

    1 = 20% equity (very conservative)
    5 = 60% equity (moderate)
    10 = 95% equity (very aggressive)
    """
    return min(0.95, max(0.20, 0.20 + (risk_score - 1) * 0.0833))


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN CAPITAL
# ─────────────────────────────────────────────────────────────────────────────

def compute_human_capital(salary, years_to_retirement, stability_factor=0.8, discount_rate=0.03):
    """PV of remaining earned income — acts like a bond in the total portfolio.

    Args:
        salary: current annual earned income
        years_to_retirement: years until retirement
        stability_factor: 0.8 for stable W-2, 0.5 for variable/self-employed
        discount_rate: real discount rate
    """
    if salary <= 0 or years_to_retirement <= 0:
        return 0.0
    pv = sum(salary * stability_factor / (1 + discount_rate)**t
             for t in range(1, int(years_to_retirement) + 1))
    return pv


# ─────────────────────────────────────────────────────────────────────────────
# GLIDE PATH
# ─────────────────────────────────────────────────────────────────────────────

def apply_glide_path(equity_pct, years_to_retirement, mode='target_date'):
    """Adjust equity percentage based on glide path.

    Args:
        equity_pct: base target equity % (from risk tolerance)
        years_to_retirement: can be negative (already retired)
        mode: 'target_date' or 'static'

    Returns:
        adjusted equity percentage
    """
    if mode == 'static':
        return equity_pct

    # Target-date style: reduce equity by ~1.5% per year past age 50
    # Pre-retirement: full equity allocation
    # Post-retirement: reduce by 1.5% per year retired
    if years_to_retirement > 10:
        return equity_pct  # far from retirement — stay aggressive
    elif years_to_retirement > 0:
        # Approaching retirement — begin de-risking
        return equity_pct - (10 - years_to_retirement) * 0.015
    else:
        # In retirement — continue de-risking
        years_retired = abs(years_to_retirement)
        return max(0.30, equity_pct - 0.015 * (10 + years_retired))




# ─────────────────────────────────────────────────────────────────────────────
# ALLOCATION POLICY / NON-LIQUID COVERAGE
# ─────────────────────────────────────────────────────────────────────────────

def allocation_class_enabled(c, class_name):
    """Return whether an asset class may appear in recommended targets.

    Existing holdings are still shown even when a class is disabled; the flag
    only controls target/recommendation generation.
    """
    enabled = c.get('asset_class_enabled') or {}
    return bool(enabled.get(class_name, True))


def allocation_selection_action(c, class_name):
    actions = c.get('asset_class_selection_action') or {}
    action = actions.get(class_name)
    if action is None:
        return getattr(_ap, 'SELECTION_INCLUDE', 'include') if allocation_class_enabled(c, class_name) else getattr(_ap, 'SELECTION_EXCLUDE', 'exclude')
    return _ap.normalize_selection_action(action)

def _apply_alternate_first_targets(c, targets):
    """Move target weight to the selected alternate class when requested.

    The UI wording is intentionally user-facing: "consider alternate first" and
    "alternate asset class to count toward this class."  In the target engine we
    implement that by crediting the class target to its selected alternate before
    normalizing the final liquid target.  The original class is still visible in
    holdings/drift, but new recommendation weight is directed to the alternate.
    """
    if not targets:
        return {}, {}
    out = dict(targets)
    actions = c.get('asset_class_selection_action') or {}
    alternates = c.get('asset_class_alternate_first') or {}
    applied = {}
    for cls, raw_action in actions.items():
        action = _ap.normalize_selection_action(raw_action)
        if action != getattr(_ap, 'SELECTION_ALTERNATE_FIRST', 'consider_alternate_first'):
            continue
        alt = _ap.canonical_asset_class(alternates.get(cls, ''))
        if not alt or alt == cls or alt not in ASSET_CLASSES:
            continue
        amt = float(out.get(cls, 0.0) or 0.0)
        if amt <= 0:
            continue
        out[cls] = 0.0
        out[alt] = float(out.get(alt, 0.0) or 0.0) + amt
        applied[cls] = alt
    total = sum(float(v or 0.0) for v in out.values())
    if total > 0:
        out = {k: max(0.0, float(v or 0.0)) / total for k, v in out.items() if max(0.0, float(v or 0.0)) > 1e-10}
    else:
        out = {}
    return out, applied


def _alternate_existing_source_for_class(c, class_name):
    """Return an existing-asset source mapped to a class via consider-alternate-first.

    Asset-class alternates (for example redirecting Bonds to TIPS) are handled by
    _apply_alternate_first_targets. This helper is only for non-liquid or
    existing-plan assets such as Home Equity, Social Security, pensions,
    annuities, and notes receivable.
    """
    cls = _ap.canonical_asset_class(class_name)
    action = allocation_selection_action(c, cls)
    if action != getattr(_ap, 'SELECTION_ALTERNATE_FIRST', 'consider_alternate_first'):
        return ''
    alternates = c.get('asset_class_alternate_first') or {}
    alt = _ap.canonical_asset_class(alternates.get(cls, ''))
    if not alt:
        return ''
    if alt in ASSET_CLASSES:
        return ''
    return _ap.normalize_existing_asset_source(alt)


def _coverage_value_for_existing_source(source, coverage):
    src = _ap.normalize_existing_asset_source(source)
    if src == 'Home Equity':
        return float(coverage.get('home_equity_reit_coverage_value', 0.0) or 0.0)
    if src == 'Social Security':
        return float(coverage.get('ss_pv', 0.0) or 0.0)
    if src == 'Pension':
        return float(coverage.get('pension_pv', 0.0) or 0.0)
    if src == 'Annuities':
        return float(coverage.get('annuity_pv', 0.0) or 0.0)
    if src == 'Note Receivable':
        return float(coverage.get('note_pv', 0.0) or 0.0)
    if src == 'Guaranteed income + note receivable':
        return float(coverage.get('fixed_income_coverage_pv', 0.0) or 0.0)
    if 'home equity' in src.lower():
        return float(coverage.get('home_equity_reit_coverage_value', 0.0) or 0.0)
    if any(token in src.lower() for token in ('social security', 'pension', 'annuit', 'note', 'guaranteed income')):
        return float(coverage.get('fixed_income_coverage_pv', 0.0) or 0.0)
    return 0.0


def _coverage_source_label(coverage, sleeve):
    """Human-readable source label for aggregate sleeve coverage."""
    if sleeve == 'fixed_income':
        sources = coverage.get('fixed_income_included_sources') or []
        return ', '.join(sources) if sources else 'Guaranteed income + note receivable'
    if sleeve == 'real_estate':
        return 'Home Equity'
    return 'Existing asset coverage'


def _sleeve_fully_covered_classes(c, base_targets, coverage, total_portfolio):
    """Classes whose whole sleeve is satisfied by non-liquid coverage.

    Coverage is evaluated at two levels: users can map a single class to an
    alternate existing source, and policy can also allow an aggregate sleeve to
    be satisfied by an existing asset pool.  When the aggregate fixed-income
    or real-estate sleeve is fully covered, every positive target inside that
    sleeve is treated as covered and removed from the liquid 100% target.
    """
    out = {}
    total_portfolio = float(total_portfolio or 0.0)
    if total_portfolio <= 0 or not base_targets:
        return out
    tolerance = max(1.0, total_portfolio * 0.0005)

    fi_classes = [cls for cls in getattr(_ap, 'FIXED_INCOME_CLASSES', set()) if cls in ASSET_CLASSES]
    fi_target_pct = sum(max(0.0, float(base_targets.get(cls, 0.0) or 0.0)) for cls in fi_classes)
    fi_target_value = fi_target_pct * total_portfolio
    fi_coverage_value = max(0.0, float(coverage.get('fixed_income_coverage_pv', 0.0) or 0.0))
    if fi_target_value > 0 and fi_coverage_value + tolerance >= fi_target_value:
        source = _coverage_source_label(coverage, 'fixed_income')
        for cls in fi_classes:
            original_target_pct = max(0.0, float(base_targets.get(cls, 0.0) or 0.0))
            if original_target_pct <= 1e-12:
                continue
            if allocation_selection_action(c, cls) == getattr(_ap, 'SELECTION_EXCLUDE', 'exclude'):
                continue
            class_target_value = original_target_pct * total_portfolio
            out[cls] = {
                'source': source,
                'original_target_pct': original_target_pct,
                'target_value': class_target_value,
                'covered_value': min(fi_coverage_value, class_target_value),
                'remaining_liquid_pct_before_normalization': 0.0,
                'fully_covered': True,
                'coverage_scope': 'fixed_income_sleeve',
            }

    re_classes = [cls for cls in getattr(_ap, 'REAL_ESTATE_CLASSES', set()) if cls in ASSET_CLASSES]
    re_target_pct = sum(max(0.0, float(base_targets.get(cls, 0.0) or 0.0)) for cls in re_classes)
    re_target_value = re_target_pct * total_portfolio
    re_coverage_value = max(0.0, float(coverage.get('home_equity_reit_coverage_value', 0.0) or 0.0))
    if re_target_value > 0 and re_coverage_value + tolerance >= re_target_value:
        source = _coverage_source_label(coverage, 'real_estate')
        for cls in re_classes:
            original_target_pct = max(0.0, float(base_targets.get(cls, 0.0) or 0.0))
            if original_target_pct <= 1e-12:
                continue
            if allocation_selection_action(c, cls) == getattr(_ap, 'SELECTION_EXCLUDE', 'exclude'):
                continue
            class_target_value = original_target_pct * total_portfolio
            out[cls] = {
                'source': source,
                'original_target_pct': original_target_pct,
                'target_value': class_target_value,
                'covered_value': min(re_coverage_value, class_target_value),
                'remaining_liquid_pct_before_normalization': 0.0,
                'fully_covered': True,
                'coverage_scope': 'real_estate_sleeve',
            }
    return out


def _adjust_liquid_targets_for_existing_coverage(c, targets, coverage, liquid_nw, total_portfolio):
    """Remove/subtract classes satisfied by existing non-liquid coverage.

    The UI lets a class be marked "consider alternate first" and mapped to an
    existing plan asset/source. For recommendations, that class's original target
    is still important context, but any target already satisfied by the mapped
    source should not consume the 100% liquid target completeness. The residual
    target is spread across the remaining included, uncovered classes.
    """
    if not targets:
        return {}, {}
    base = {k: max(0.0, float(v or 0.0)) for k, v in targets.items() if k in ASSET_CLASSES}
    original_total = sum(base.values()) or 1.0
    base = {k: v / original_total for k, v in base.items() if v > 1e-12}
    total_portfolio = float(total_portfolio or 0.0)
    liquid_nw = float(liquid_nw or 0.0)
    adjusted = dict(base)
    coverage_adjustments = {}
    if total_portfolio <= 0 or liquid_nw <= 0:
        return adjusted, coverage_adjustments

    # First apply aggregate sleeve coverage.  This is what keeps Short-Term
    # Bonds, TIPS, and Municipal Bonds out of the liquid recommendation when
    # the fixed-income sleeve is already covered by guaranteed income / notes,
    # even if the individual sub-sleeve was not separately mapped.
    sleeve_covered = _sleeve_fully_covered_classes(c, base, coverage, total_portfolio)
    for cls, info in sleeve_covered.items():
        adjusted[cls] = 0.0
        coverage_adjustments[cls] = dict(info)

    for cls in list(base.keys()):
        if coverage_adjustments.get(cls, {}).get('fully_covered'):
            continue
        source = _alternate_existing_source_for_class(c, cls)
        if not source:
            continue
        coverage_value = max(0.0, _coverage_value_for_existing_source(source, coverage))
        if coverage_value <= 0:
            continue
        original_target_pct = base.get(cls, 0.0)
        target_value = original_target_pct * total_portfolio
        covered_value = min(coverage_value, target_value)
        remaining_value = max(0.0, target_value - covered_value)
        remaining_liquid_pct = remaining_value / liquid_nw if liquid_nw > 0 else 0.0
        fully_covered = remaining_value <= max(1.0, total_portfolio * 0.0005)
        adjusted[cls] = remaining_liquid_pct
        coverage_adjustments[cls] = {
            'source': source,
            'original_target_pct': original_target_pct,
            'target_value': target_value,
            'covered_value': covered_value,
            'remaining_liquid_pct_before_normalization': remaining_liquid_pct,
            'fully_covered': fully_covered,
            'coverage_scope': 'asset_class_mapping',
        }
    total = sum(max(0.0, float(v or 0.0)) for v in adjusted.values())
    if total > 0:
        adjusted = {k: max(0.0, float(v or 0.0)) / total for k, v in adjusted.items() if max(0.0, float(v or 0.0)) > 1e-10}
    else:
        adjusted = {}
    for cls, info in coverage_adjustments.items():
        info['liquid_target_pct'] = adjusted.get(cls, 0.0)
    return adjusted, coverage_adjustments


def _covered_existing_asset_classes(c, coverage, targets=None, total_portfolio=None):
    """Classes fully covered by existing assets or aggregate sleeve coverage."""
    out = set()
    targets = targets or {}
    total_portfolio = float(total_portfolio or 0.0)
    normalized_targets = {}
    if targets:
        canonical = {}
        for k, v in targets.items():
            cls = _ap.canonical_asset_class(k)
            if cls in ASSET_CLASSES:
                try:
                    canonical[cls] = canonical.get(cls, 0.0) + max(0.0, float(v or 0.0))
                except Exception:
                    pass
        _sum = sum(canonical.values())
        if _sum > 0:
            normalized_targets = {k: v / _sum for k, v in canonical.items()}
    if normalized_targets and total_portfolio > 0:
        out.update(_sleeve_fully_covered_classes(c, normalized_targets, coverage, total_portfolio).keys())
    for cls in ASSET_CLASSES:
        source = _alternate_existing_source_for_class(c, cls)
        if not source:
            continue
        coverage_value = _coverage_value_for_existing_source(source, coverage)
        if coverage_value <= 0:
            continue
        target_pct = float(normalized_targets.get(cls, 0.0) if normalized_targets else targets.get(cls, 0.0) or 0.0)
        if target_pct > 0 and total_portfolio > 0:
            if coverage_value + max(1.0, total_portfolio * 0.0005) >= target_pct * total_portfolio:
                out.add(cls)
        else:
            # If no explicit target is known yet, the source exists and is mapped,
            # so keep the class out of the optimizer candidate set. This prevents
            # a covered sleeve such as REITs/Home Equity from receiving a new
            # liquid recommendation before coverage is applied.
            out.add(cls)
    return out

def _coverage_policy(c):
    policy = c.get('allocation_coverage') or {}
    return {
        'social_security_satisfies_fixed_income_target': bool(policy.get('social_security_satisfies_fixed_income_target', True)),
        'pension_satisfies_fixed_income_target': bool(policy.get('pension_satisfies_fixed_income_target', True)),
        'annuities_satisfy_fixed_income_target': bool(policy.get('annuities_satisfy_fixed_income_target', True)),
        'note_receivable_satisfies_fixed_income_target': bool(policy.get('note_receivable_satisfies_fixed_income_target', True)),
        'include_home_equity_in_allocation_view': bool(policy.get('include_home_equity_in_allocation_view', True)),
        'home_equity_satisfies_reit_target': bool(policy.get('home_equity_satisfies_reit_target', True)),
        'liquid_reit_target_pct_when_home_not_counted': float(policy.get('liquid_reit_target_pct_when_home_not_counted', 0.05) or 0.05),
    }


def compute_allocation_coverage(c, now_yr=None):
    """Compute non-liquid/guaranteed assets used by allocation targets.

    These values are policy-controlled. They answer: which non-liquid assets are
    allowed to satisfy target allocation sleeves before recommending liquid ETFs?
    """
    import datetime
    if now_yr is None:
        now_yr = datetime.date.today().year
    policy = _coverage_policy(c)
    plan_years = max(0, int(c.get('plan_end', now_yr + 30) - now_yr))
    discount = float(c.get('ret', 0.07) or 0.07)
    annuity_factor = sum(1/(1+discount)**t for t in range(1, plan_years+1)) if plan_years > 0 else 0.0

    ss_annual = (float(c.get('h_ss_pia', 0) or 0) + float(c.get('w_ss_pia', 0) or 0)) * 12
    pension_annual = float(c.get('wife_pension', {}).get('init_pmt', 0) or 0) * 12
    annuity_annual = 0.0
    for key in ['wife_single', 'wife_joint', 'h_single', 'h_joint']:
        st = c.get(key, {}) or {}
        if float(st.get('init_pmt', 0) or 0) > 0:
            annuity_annual += float(st.get('init_pmt', 0) or 0) * 12

    ss_pv = ss_annual * annuity_factor
    pension_pv = pension_annual * annuity_factor
    annuity_pv = annuity_annual * annuity_factor
    note_pv = float(c.get('note_face', 0) or 0)

    fixed_income_coverage_pv = 0.0
    included_sources = []
    excluded_sources = []
    for key, label, value in [
        ('social_security_satisfies_fixed_income_target', 'Social Security', ss_pv),
        ('pension_satisfies_fixed_income_target', 'Pension', pension_pv),
        ('annuities_satisfy_fixed_income_target', 'Annuities', annuity_pv),
        ('note_receivable_satisfies_fixed_income_target', 'Note Receivable', note_pv),
    ]:
        if policy[key]:
            fixed_income_coverage_pv += value
            if value > 0:
                included_sources.append(label)
        elif value > 0:
            excluded_sources.append(label)

    gross_home_equity = max(0.0, float(c.get('home_val', 0) or 0) - float(c.get('mortgage_bal', 0) or 0))
    home_equity_allocation_value = gross_home_equity if policy['include_home_equity_in_allocation_view'] else 0.0
    home_equity_reit_coverage_value = home_equity_allocation_value if policy['home_equity_satisfies_reit_target'] else 0.0

    return {
        'policy': policy,
        'annuity_factor': annuity_factor,
        'ss_pv': ss_pv,
        'pension_pv': pension_pv,
        'annuity_pv': annuity_pv,
        'note_pv': note_pv,
        'all_guaranteed_income_pv': ss_pv + pension_pv + annuity_pv,
        'fixed_income_coverage_pv': fixed_income_coverage_pv,
        'fixed_income_included_sources': included_sources,
        'fixed_income_excluded_sources': excluded_sources,
        'gross_home_equity': gross_home_equity,
        'home_equity_allocation_value': home_equity_allocation_value,
        'home_equity_reit_coverage_value': home_equity_reit_coverage_value,
        'home_equity_excluded': gross_home_equity > 0 and not policy['include_home_equity_in_allocation_view'],
        'home_equity_counts_toward_reit': bool(home_equity_reit_coverage_value > 0),
    }


def _normalized_split(classes, base_weights):
    selected = {k: v for k, v in base_weights.items() if k in classes and v > 0}
    total = sum(selected.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in selected.items()}

# ─────────────────────────────────────────────────────────────────────────────
# MEAN-VARIANCE OPTIMIZER
# ─────────────────────────────────────────────────────────────────────────────

def optimize_equity_sleeve(equity_budget, available_classes, inflation_sensitive_pct=0.0,
                           concentration=None, class_constraints=None):
    """Solve a constrained mean-variance/CVaR-aware equity-sleeve allocation.

    This is the production optimizer. It uses scipy's SLSQP optimizer when
    available and falls back to deterministic equal weighting only if scipy is
    unavailable. Constraints: fully invested, no shorting, class max weights,
    inflation/commodity floor, and concentration penalties.
    """
    if not available_classes:
        return {}
    classes = [c for c in available_classes if c in ASSET_CLASSES]
    n = len(classes)
    if n == 0:
        return {}
    if n == 1:
        return {classes[0]: 1.0}

    mu = np.array([ASSET_CLASSES[c]['ret'] for c in classes], dtype=float)
    cov = build_covariance_matrix(classes) + np.eye(n) * 1e-6
    concentration = concentration or {}
    class_constraints = class_constraints or {}
    class_caps = {
        'US Large Cap': 0.65,
        'US Mid Cap': 0.35,
        'US Small Cap': 0.35,
        'International': 0.45,
        'Emerging Markets': 0.20,
        'Commodities': 0.12,
        'Managed Futures': 0.12,
        'Private Credit': 0.10,
        'REITs': 0.15,
    }
    max_weight = np.array([class_caps.get(c, 0.45) for c in classes], dtype=float)
    min_weight = np.zeros(n)
    for i, c_name in enumerate(classes):
        cons = class_constraints.get(c_name, {}) if isinstance(class_constraints, dict) else {}
        user_min = cons.get('min_target', -1)
        user_max = cons.get('max_target', -1)
        try:
            user_min = float(user_min)
        except Exception:
            user_min = -1
        try:
            user_max = float(user_max)
        except Exception:
            user_max = -1
        if user_min >= 0:
            min_weight[i] = min(0.95, max(0.0, user_min))
        if user_max >= 0:
            max_weight[i] = min(1.0, max(0.0, user_max))
        if max_weight[i] < min_weight[i]:
            max_weight[i] = min_weight[i]
    if min_weight.sum() >= 0.999:
        # Keep the optimizer feasible even if the user enters aggressive floors.
        # The diagnostic/report still shows the configured values; this just
        # prevents SLSQP infeasibility from breaking the build.
        min_weight = min_weight / min_weight.sum() * 0.999
    if max_weight.sum() < 1.0:
        # If user caps are too tight, proportionally relax them so a 100% sleeve
        # can still be constructed.
        max_weight = max_weight / max_weight.sum()
    for i, c_name in enumerate(classes):
        if c_name == 'Commodities':
            min_weight[i] = min(0.10, max(0.0, inflation_sensitive_pct * 0.08))
        elif c_name == 'Managed Futures' and inflation_sensitive_pct > 0.20:
            min_weight[i] = 0.02

    risk_aversion = 3.0
    downside_penalty = 1.2

    def objective(w):
        port_ret = float(w @ mu)
        port_var = float(w @ cov @ w)
        # Normal-approximate CVaR proxy: mean minus 2.06 sigma at 95%.
        downside = max(0.0, 0.0 - (port_ret - 2.06 * (port_var ** 0.5)))
        conc_penalty = sum((max(0.0, concentration.get(classes[i], 0.0) - 0.10) * w[i]) ** 2 for i in range(n))
        return -(port_ret) + risk_aversion * port_var + downside_penalty * downside + 2.0 * conc_penalty

    bounds = [(float(min_weight[i]), float(max_weight[i])) for i in range(n)]
    constraints = [{'type': 'eq', 'fun': lambda w: float(np.sum(w) - 1.0)}]
    # Make an initial point that satisfies lower/upper bounds where possible.
    remaining = max(0.0, 1.0 - float(min_weight.sum()))
    x0 = min_weight + remaining / n
    x0 = np.minimum(x0, max_weight)
    if x0.sum() <= 0:
        x0 = np.ones(n) / n
    else:
        x0 = x0 / x0.sum()

    try:
        from scipy.optimize import minimize
        res = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints,
                       options={'maxiter': 500, 'ftol': 1e-10})
        if not res.success:
            raise RuntimeError(res.message)
        weights = np.maximum(np.array(res.x, dtype=float), 0.0)
    except Exception:
        weights = x0

    total = weights.sum()
    if total <= 0:
        weights = np.ones(n) / n
    else:
        weights = weights / total
    return {classes[i]: float(weights[i]) for i in range(n)}


def compute_optimal_allocation(c, force_mode=None):
    """Compute target allocation using either user targets or optimizer recommendation.

    force_mode may be "user_target" or "optimizer_recommendation" and is used by
    reports/UI to show both recommendations side by side without changing the
    selected plan mode.

    Compute target allocation with user-controlled class inclusion and non-liquid coverage.

    Asset classes can be disabled via:
        Asset Class Optimizer Controls,<class>,selection_action,exclude

    Non-liquid coverage can be controlled via Model Constants / Allocation rows,
    for example whether home equity satisfies REIT exposure or annuities satisfy
    fixed-income exposure.
    """
    import datetime
    now_yr = datetime.date.today().year

    capital_market_diagnostics = apply_capital_market_config(c)

    for cls_name, overrides in c.get('asset_class_overrides', {}).items():
        if cls_name in ASSET_CLASSES:
            base = _BASE_ASSET_CLASSES.get(cls_name, {})
            # The packaged client_data.csv includes default return/volatility
            # values for readability. Treat values equal to the shipped 30-year
            # baseline as documentation defaults, not forced overrides, so the
            # selected horizon/preset can take effect. If the user changes a
            # value away from the baseline, that explicit override wins.
            ret_val = overrides.get('ret', -1)
            vol_val = overrides.get('vol', -1)
            if ret_val is not None and ret_val >= 0 and abs(ret_val - base.get('ret', ret_val)) > 1e-9:
                ASSET_CLASSES[cls_name]['ret'] = ret_val
                ASSET_CLASSES[cls_name]['assumption_source'] = 'client_data_override'
            if vol_val is not None and vol_val >= 0 and abs(vol_val - base.get('vol', vol_val)) > 1e-9:
                ASSET_CLASSES[cls_name]['vol'] = vol_val
                ASSET_CLASSES[cls_name]['assumption_source'] = 'client_data_override'

    age = now_yr - c.get('h_dob_yr', 1970)
    spend = c.get('spend_base', 80000)
    liquid_nw = sum(c.get('balances', {}).values())
    withdrawal_rate = spend / liquid_nw if liquid_nw > 0 else 0.05

    coverage = compute_allocation_coverage(c, now_yr)
    annuity_factor = coverage['annuity_factor']
    spending_pv = spend * annuity_factor
    funded_ratio = coverage['all_guaranteed_income_pv'] / spending_pv if spending_pv > 0 else 0
    fixed_income_coverage_pv = coverage['fixed_income_coverage_pv']
    total_portfolio_for_coverage = liquid_nw + fixed_income_coverage_pv + coverage.get('home_equity_allocation_value', 0.0)

    risk_score = c.get('risk_tolerance', 0)
    if risk_score <= 0:
        risk_score = auto_risk_score(age, withdrawal_rate, funded_ratio)
    risk_score = max(1, min(10, risk_score))

    years_to_ret = c.get('h_ret_yr', now_yr + 10) - now_yr
    salary = c.get('earned', 0)
    stability = c.get('human_capital_stability', 0.8)
    human_capital = compute_human_capital(salary, max(0, years_to_ret), stability)

    base_equity_pct = risk_to_equity_pct(risk_score)
    total_wealth = liquid_nw + fixed_income_coverage_pv + human_capital + coverage['home_equity_allocation_value']
    bond_like_pct = (fixed_income_coverage_pv + human_capital) / total_wealth if total_wealth > 0 else 0
    equity_boost = min(0.10, bond_like_pct * 0.15)

    glide_mode = c.get('glide_path', 'target_date')
    equity_pct = apply_glide_path(base_equity_pct + equity_boost, years_to_ret, glide_mode)
    equity_pct = max(0.20, min(0.95, equity_pct))

    concentration = {}
    employer_stock_pct = c.get('concentration_employer_stock', 0)
    real_estate_pct = c.get('concentration_real_estate', 0)
    business_pct = c.get('concentration_business', 0)
    if employer_stock_pct > 0:
        concentration['US Large Cap'] = employer_stock_pct
    if real_estate_pct > 0:
        concentration['REITs'] = real_estate_pct
    if business_pct > 0:
        concentration['US Small Cap'] = business_pct

    selected_mode = _ap.normalize_allocation_mode(force_mode or c.get('allocation_selection_mode', 'user_target'))

    # Optional optimizer override.  In optimizer mode, users may enter a full
    # 100% optimizer override allocation in asset_class_optimizer_controls.csv.
    # Leaving the override rows blank preserves the computed optimizer result.
    raw_optimizer_override = dict(c.get('allocation_optimizer_override_pct') or {})
    for _cls, _action in (c.get('asset_class_selection_action') or {}).items():
        if _ap.normalize_selection_action(_action) == getattr(_ap, 'SELECTION_EXCLUDE', 'exclude'):
            raw_optimizer_override[_ap.canonical_asset_class(_cls)] = 0.0
    optimizer_override_sum = _ap.target_total(raw_optimizer_override) if raw_optimizer_override else 0.0
    if selected_mode == _ap.ALLOCATION_MODE_OPTIMIZER and optimizer_override_sum > 0:
        canonical_override = {}
        for _k, _v in raw_optimizer_override.items():
            _cls = _ap.canonical_asset_class(_k)
            if _cls in ASSET_CLASSES:
                try:
                    _val = float(_v or 0.0)
                except Exception:
                    _val = 0.0
                canonical_override[_cls] = max(0.0, _val)
        _sum = sum(canonical_override.values())
        if _sum > 0:
            explicit_targets = {cls: canonical_override.get(cls, 0.0) / _sum for cls in ASSET_CLASSES}
        else:
            explicit_targets = {}
        explicit_targets, alternate_map = _apply_alternate_first_targets(c, explicit_targets)
        original_explicit_targets = dict(explicit_targets)
        # Existing-asset coverage must affect the active liquid recommendation,
        # not just the side-by-side report view.  If guaranteed income / note
        # receivable PV fully covers the fixed-income sleeve, all fixed-income
        # sub-sleeves are removed before liquid targets are normalized so the
        # workbook does not recommend unnecessary bond purchases.
        explicit_targets, coverage_adjustments = _adjust_liquid_targets_for_existing_coverage(
            c, explicit_targets, coverage, liquid_nw, total_portfolio_for_coverage
        )
        total_targets = dict(original_explicit_targets)
        total_targets['Bonds/Fixed Income'] = sum(original_explicit_targets.get(cls, 0.0) for cls in _ap.FIXED_INCOME_CLASSES)
        total_targets['REITs/Real Estate'] = sum(original_explicit_targets.get(cls, 0.0) for cls in _ap.REAL_ESTATE_CLASSES)
        disabled_classes = [cls for cls in ASSET_CLASSES if not allocation_class_enabled(c, cls)]
        equity_pct = sum(explicit_targets.get(cls, 0.0) for cls in _ap.GROWTH_CLASSES)
        return {
            'total_targets': total_targets,
            'liquid_targets': dict(explicit_targets),
            'equity_pct': equity_pct,
            'risk_score': risk_score,
            'human_capital': human_capital,
            'bond_pv': fixed_income_coverage_pv,
            'funded_ratio': funded_ratio,
            'home_equity': coverage['home_equity_allocation_value'],
            'allocation_coverage': coverage,
            'disabled_asset_classes': disabled_classes,
            'diagnostics': {
                'age': age,
                'withdrawal_rate': withdrawal_rate,
                'base_equity_pct': base_equity_pct,
                'equity_boost_from_bonds': equity_boost,
                'glide_path_mode': glide_mode,
                'years_to_retirement': years_to_ret,
                'inflation_sensitive_pct': c.get('inflation_sensitive_spending_pct', 0),
                'concentration': concentration,
                'stability_factor': stability,
                'fixed_income_coverage_sources': coverage['fixed_income_included_sources'],
                'fixed_income_excluded_sources': coverage['fixed_income_excluded_sources'],
                'home_equity_counts_toward_reit': coverage['home_equity_counts_toward_reit'],
                'disabled_asset_classes': disabled_classes,
                'alternate_first_map': alternate_map,
                'coverage_adjustments': coverage_adjustments,
                'asset_class_selection_action': c.get('asset_class_selection_action', {}),
                'asset_class_constraints': c.get('asset_class_overrides', {}),
                'capital_market_assumptions': capital_market_diagnostics,
                'allocation_policy_mode': 'optimizer_override_pct',
                'allocation_selection_mode': selected_mode,
                'allocation_selection_label': _ap.allocation_mode_label(selected_mode),
                'optimizer_override_sum': optimizer_override_sum,
                'optimizer_override_normalized': abs(optimizer_override_sum - 1.0) > 0.0001,
                'optimizer_recommendation_comment': getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', ''),
            },
        }

    # Simple/default target mix mode.  The user-facing allocation policy is one
    # target percentage per asset class, unless the UI toggle selects the
    # household-specific optimizer recommendation.  The optimizer branch below
    # remains visible as a recommendation and can be selected directly.
    raw_targets = dict(c.get('allocation_target_pct') or {})
    # Excluded classes remain visible in the UI but do not receive target weight.
    # Include and Consider alternate first rows keep their target percentage.
    for _cls, _action in (c.get('asset_class_selection_action') or {}).items():
        if _ap.normalize_selection_action(_action) == getattr(_ap, 'SELECTION_EXCLUDE', 'exclude'):
            raw_targets[_ap.canonical_asset_class(_cls)] = 0.0
    raw_target_sum = _ap.target_total(raw_targets)
    if selected_mode != _ap.ALLOCATION_MODE_OPTIMIZER and raw_targets and raw_target_sum > 0:
        explicit_targets = _ap.normalize_targets(raw_targets)
        explicit_targets, alternate_map = _apply_alternate_first_targets(c, explicit_targets)
        original_explicit_targets = dict(explicit_targets)
        # Existing-asset coverage must affect the active liquid recommendation,
        # not just the side-by-side report view.  If guaranteed income / note
        # receivable PV fully covers the fixed-income sleeve, all fixed-income
        # sub-sleeves are removed before liquid targets are normalized so the
        # workbook does not recommend unnecessary bond purchases.
        explicit_targets, coverage_adjustments = _adjust_liquid_targets_for_existing_coverage(
            c, explicit_targets, coverage, liquid_nw, total_portfolio_for_coverage
        )
        total_targets = dict(original_explicit_targets)
        total_targets['Bonds/Fixed Income'] = sum(original_explicit_targets.get(cls, 0.0) for cls in _ap.FIXED_INCOME_CLASSES)
        total_targets['REITs/Real Estate'] = sum(original_explicit_targets.get(cls, 0.0) for cls in _ap.REAL_ESTATE_CLASSES)
        disabled_classes = [cls for cls in ASSET_CLASSES if not allocation_class_enabled(c, cls)]
        equity_pct = sum(explicit_targets.get(cls, 0.0) for cls in _ap.GROWTH_CLASSES)
        optimizer_peer = None
        if force_mode is None:
            try:
                optimizer_peer = compute_optimal_allocation(c, force_mode=_ap.ALLOCATION_MODE_OPTIMIZER)
            except Exception as _ex:
                optimizer_peer = {'error': str(_ex)}
        return {
            'total_targets': total_targets,
            'liquid_targets': dict(explicit_targets),
            'equity_pct': equity_pct,
            'risk_score': risk_score,
            'human_capital': human_capital,
            'bond_pv': fixed_income_coverage_pv,
            'funded_ratio': funded_ratio,
            'home_equity': coverage['home_equity_allocation_value'],
            'allocation_coverage': coverage,
            'disabled_asset_classes': disabled_classes,
            'diagnostics': {
                'age': age,
                'withdrawal_rate': withdrawal_rate,
                'base_equity_pct': base_equity_pct,
                'equity_boost_from_bonds': equity_boost,
                'glide_path_mode': glide_mode,
                'years_to_retirement': years_to_ret,
                'inflation_sensitive_pct': c.get('inflation_sensitive_spending_pct', 0),
                'concentration': concentration,
                'stability_factor': stability,
                'fixed_income_coverage_sources': coverage['fixed_income_included_sources'],
                'fixed_income_excluded_sources': coverage['fixed_income_excluded_sources'],
                'home_equity_counts_toward_reit': coverage['home_equity_counts_toward_reit'],
                'disabled_asset_classes': disabled_classes,
                'alternate_first_map': alternate_map,
                'coverage_adjustments': coverage_adjustments,
                'asset_class_selection_action': c.get('asset_class_selection_action', {}),
                'asset_class_constraints': c.get('asset_class_overrides', {}),
                'capital_market_assumptions': capital_market_diagnostics,
                'allocation_policy_mode': 'user_target_pct',
                'allocation_selection_mode': selected_mode,
                'allocation_selection_label': _ap.allocation_mode_label(selected_mode),
                'allocation_target_sum': raw_target_sum,
                'allocation_target_normalized': abs(raw_target_sum - 1.0) > 0.0001,
                'optimizer_recommendation': optimizer_peer,
                'optimizer_recommendation_comment': getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', ''),
            },
        }

    inflation_pct = c.get('inflation_sensitive_spending_pct', 0)
    candidate_growth_classes = [
        'US Large Cap', 'US Mid Cap', 'US Small Cap', 'International', 'Emerging Markets',
        'Commodities', 'Managed Futures', 'Private Credit', 'REITs'
    ]
    _covered_candidate_classes = _covered_existing_asset_classes(
        c, coverage, c.get('allocation_target_pct') or {}, total_portfolio_for_coverage
    )
    equity_classes = [
        cls for cls in candidate_growth_classes
        if allocation_class_enabled(c, cls) and cls not in _covered_candidate_classes
    ]
    if not equity_classes:
        equity_classes = ['US Large Cap']

    equity_weights = optimize_equity_sleeve(
        equity_pct * liquid_nw,
        equity_classes,
        inflation_pct,
        concentration,
        c.get('asset_class_overrides', {})
    )

    home_equity_for_allocation = coverage['home_equity_allocation_value']
    home_equity_for_reit = coverage['home_equity_reit_coverage_value']
    total_portfolio = liquid_nw + fixed_income_coverage_pv + home_equity_for_allocation
    cash_pct = c.get('cash_target_pct', 0.05) if allocation_class_enabled(c, 'Cash') else 0.0

    if home_equity_for_reit > 0:
        re_pct = min(0.10, home_equity_for_reit / total_portfolio if total_portfolio > 0 else 0.05)
    elif allocation_class_enabled(c, 'REITs'):
        re_pct = max(0.0, min(0.25, coverage['policy'].get('liquid_reit_target_pct_when_home_not_counted', 0.05)))
    else:
        re_pct = 0.0

    fi_pct = max(0.0, 1.0 - equity_pct - cash_pct - re_pct)

    total_targets = {}
    for cls, wt in equity_weights.items():
        total_targets[cls] = equity_pct * wt

    total_targets['Bonds/Fixed Income'] = fi_pct
    fi_base_split = {'Bonds': 0.45, 'Short-Term Bonds': 0.20, 'TIPS': 0.20, 'Municipal Bonds': 0.15}
    fi_split = _normalized_split(
        [cls for cls in fi_base_split if allocation_class_enabled(c, cls)],
        fi_base_split
    )
    for _fi_cls, _fi_wt in fi_split.items():
        total_targets[_fi_cls] = fi_pct * _fi_wt

    if re_pct > 0:
        total_targets['REITs/Real Estate'] = re_pct
        if allocation_class_enabled(c, 'REITs'):
            total_targets['REITs'] = re_pct
    if cash_pct > 0:
        total_targets['Cash'] = cash_pct

    _tt_sum = sum(total_targets.values())
    if _tt_sum > 0:
        total_targets = {k: v / _tt_sum for k, v in total_targets.items()}
    _class_only_targets = {k: v for k, v in total_targets.items() if k in ASSET_CLASSES}
    _class_only_targets, _total_alt_map = _apply_alternate_first_targets(c, _class_only_targets)
    for _cls in ASSET_CLASSES:
        if _cls in total_targets:
            total_targets[_cls] = _class_only_targets.get(_cls, 0.0)

    fi_target_amt = total_targets.get('Bonds/Fixed Income', 0.0) * total_portfolio
    re_target_amt = total_targets.get('REITs/Real Estate', 0.0) * total_portfolio
    fi_remaining = max(0, fi_target_amt - fixed_income_coverage_pv) / liquid_nw if liquid_nw > 0 else 0
    re_remaining = max(0, re_target_amt - home_equity_for_reit) / liquid_nw if liquid_nw > 0 else 0

    liquid_targets = {}
    denom = equity_pct + fi_remaining + re_remaining + cash_pct
    if denom <= 0:
        denom = 1.0
    for cls, wt in equity_weights.items():
        liquid_targets[cls] = wt * equity_pct / denom if equity_pct > 0 else 0

    if fi_remaining > 0.0001 and fi_split:
        for _fi_cls, _fi_wt in fi_split.items():
            liquid_targets[_fi_cls] = fi_remaining * _fi_wt / denom
    if re_remaining > 0.0001 and allocation_class_enabled(c, 'REITs'):
        liquid_targets['REITs'] = re_remaining / denom
    if cash_pct > 0:
        liquid_targets['Cash'] = cash_pct / denom

    lt_sum = sum(liquid_targets.values())
    if lt_sum > 0:
        liquid_targets = {k: v/lt_sum for k, v in liquid_targets.items()}
    liquid_targets, alternate_map = _apply_alternate_first_targets(c, liquid_targets)
    liquid_targets, coverage_adjustments = _adjust_liquid_targets_for_existing_coverage(
        c, liquid_targets, coverage, liquid_nw, total_portfolio_for_coverage
    )
    _covered_total_classes = _covered_existing_asset_classes(
        c, coverage, total_targets, total_portfolio_for_coverage
    )

    disabled_classes = [cls for cls in ASSET_CLASSES if not allocation_class_enabled(c, cls)]

    return {
        'total_targets': total_targets,
        'liquid_targets': liquid_targets,
        'equity_pct': equity_pct,
        'risk_score': risk_score,
        'human_capital': human_capital,
        'bond_pv': fixed_income_coverage_pv,
        'funded_ratio': funded_ratio,
        'home_equity': home_equity_for_allocation,
        'allocation_coverage': coverage,
        'disabled_asset_classes': disabled_classes,
        'diagnostics': {
            'age': age,
            'withdrawal_rate': withdrawal_rate,
            'base_equity_pct': base_equity_pct,
            'equity_boost_from_bonds': equity_boost,
            'glide_path_mode': glide_mode,
            'years_to_retirement': years_to_ret,
            'inflation_sensitive_pct': inflation_pct,
            'concentration': concentration,
            'stability_factor': stability,
            'fixed_income_coverage_sources': coverage['fixed_income_included_sources'],
            'fixed_income_excluded_sources': coverage['fixed_income_excluded_sources'],
            'home_equity_counts_toward_reit': coverage['home_equity_counts_toward_reit'],
            'disabled_asset_classes': disabled_classes,
            'alternate_first_map': alternate_map,
            'coverage_adjustments': coverage_adjustments,
            'covered_existing_asset_classes': sorted(_covered_total_classes),
            'asset_class_selection_action': c.get('asset_class_selection_action', {}),
            'asset_class_constraints': c.get('asset_class_overrides', {}),
            'capital_market_assumptions': capital_market_diagnostics,
            'allocation_policy_mode': 'optimizer_recommendation',
            'allocation_selection_mode': selected_mode,
            'allocation_selection_label': _ap.allocation_mode_label(selected_mode),
            'optimizer_recommendation_comment': getattr(_ap, 'OPTIMIZER_RECOMMENDATION_COMMENT', ''),
        },
    }



# ─────────────────────────────────────────────────────────────────────────────
# SHARPE RATIO / RISK-FREE RATE
# ─────────────────────────────────────────────────────────────────────────────

def risk_free_rate(c):
    """Resolve the risk-free rate assumption used for Sharpe-ratio calculations.

    Precedence:
      1. capital_market_config['risk_free_rate'] if present and a valid
         non-negative number (lets an expert/advanced user override it).
      2. The Cash asset class expected return in ASSET_CLASSES (~0.020),
         which already reflects the selected horizon/preset assumptions.
      3. A hardcoded 0.02 fallback if Cash is somehow missing.
    """
    cfg = c.get('capital_market_config', {}) or {}
    raw_rf = cfg.get('risk_free_rate', None)
    if raw_rf is not None:
        try:
            rf = float(raw_rf)
            if rf >= 0:
                return rf
        except (TypeError, ValueError):
            pass
    cash = ASSET_CLASSES.get('Cash', {})
    try:
        return float(cash.get('ret', 0.020))
    except (TypeError, ValueError):
        return 0.020


def sharpe_ratio(expected_return, volatility, rf):
    """Return the Sharpe ratio (expected_return - rf) / volatility.

    Guards against non-positive volatility (undefined/degenerate Sharpe) by
    returning 0.0 instead of raising or producing inf/NaN.
    """
    try:
        vol = float(volatility)
    except (TypeError, ValueError):
        return 0.0
    if vol <= 0:
        return 0.0
    try:
        return float((float(expected_return) - float(rf)) / vol)
    except (TypeError, ValueError):
        return 0.0


def allocation_portfolio_stats(c, force_mode=None):
    """Return allocation-implied planning statistics for a user/optimizer mode.

    The main cash-flow projection has a configured portfolio return.  Scenario
    analysis uses this helper when the user wants to compare "change to user
    allocation" versus "change to optimizer allocation": the scenario keeps the
    full household plan constant, switches the allocation mode, and substitutes
    the selected allocation's weighted expected return and covariance-based
    volatility.  This keeps the base plan stable while making allocation
    scenarios produce real terminal-net-worth differences.
    """
    selected = compute_optimal_allocation(c, force_mode=force_mode)
    targets = selected.get('liquid_targets') or {}
    classes = [cls for cls, wt in targets.items() if cls in ASSET_CLASSES and float(wt or 0) > 0]
    rf = risk_free_rate(c)
    if not classes:
        _fallback_ret = float(c.get('ret', 0.0) or 0.0)
        _fallback_vol = float(c.get('mc_sigma', 0.0) or 0.0)
        return {
            'mode': _ap.normalize_allocation_mode(force_mode or c.get('allocation_selection_mode', 'user_target')),
            'label': _ap.allocation_mode_label(force_mode or c.get('allocation_selection_mode', 'user_target')),
            'targets': {},
            'expected_return': _fallback_ret,
            'volatility': _fallback_vol,
            'geometric_return': _fallback_ret,
            'sharpe': sharpe_ratio(_fallback_ret, _fallback_vol, rf),
            'diagnostics': selected.get('diagnostics', {}),
        }
    weights = np.array([float(targets.get(cls, 0.0) or 0.0) for cls in classes], dtype=float)
    total = float(weights.sum())
    if total <= 0:
        weights = np.ones(len(classes), dtype=float) / len(classes)
    else:
        weights = weights / total
    mu = np.array([float(ASSET_CLASSES[cls].get('ret', 0.0) or 0.0) for cls in classes], dtype=float)
    exp_ret = float(np.dot(weights, mu))
    cov = build_covariance_matrix(classes)
    variance = max(0.0, float(weights.T @ cov @ weights))
    vol = float(np.sqrt(variance))
    geo = float(exp_ret - 0.5 * variance)
    return {
        'mode': _ap.normalize_allocation_mode(force_mode or c.get('allocation_selection_mode', 'user_target')),
        'label': _ap.allocation_mode_label(force_mode or c.get('allocation_selection_mode', 'user_target')),
        'targets': {cls: float(weights[i]) for i, cls in enumerate(classes)},
        'expected_return': exp_ret,
        'volatility': vol,
        'geometric_return': geo,
        'sharpe': sharpe_ratio(exp_ret, vol, rf),
        'diagnostics': selected.get('diagnostics', {}),
    }


# ─────────────────────────────────────────────────────────────────────────────
# EFFICIENT FRONTIER
# ─────────────────────────────────────────────────────────────────────────────

def _min_variance_portfolio(cov, n, bounds):
    """Solve the long-only global-minimum-variance portfolio via SLSQP.

    Falls back to equal weighting if scipy is unavailable or the solve fails.
    Used only as the starting ("left") anchor point of the efficient frontier.
    """
    x0 = np.ones(n) / n
    try:
        from scipy.optimize import minimize
    except Exception:
        return x0

    def variance(w):
        return float(w @ cov @ w)

    constraints = [{'type': 'eq', 'fun': lambda w: float(np.sum(w) - 1.0)}]
    try:
        res = minimize(variance, x0, method='SLSQP', bounds=bounds, constraints=constraints,
                       options={'maxiter': 500, 'ftol': 1e-12})
        if res.success:
            w = np.maximum(np.array(res.x, dtype=float), 0.0)
            total = w.sum()
            if total > 0:
                return w / total
    except Exception:
        pass
    return x0


def efficient_frontier(c, n_points=20, force_mode=None):
    """Trace the long-only mean-variance efficient frontier for this household.

    Reuses the same eligible/enabled asset-class set that the recommended
    allocation resolves to (compute_optimal_allocation's liquid_targets, the
    same classes allocation_portfolio_stats uses) and the same expected-return
    assumptions used elsewhere (ASSET_CLASSES[...]['ret']).

    Each point minimizes portfolio variance for a target expected return,
    subject to sum(weights) == 1 and weights >= 0 (long-only), solved with
    scipy SLSQP in the same style as optimize_equity_sleeve. Target returns
    are swept from the global-minimum-variance portfolio's return up to the
    highest single-asset expected return, which is the "efficient" (dominant)
    branch of the classic Markowitz parabola: volatility and return are both
    non-decreasing along it.

    Returns a list of dicts sorted by ascending volatility:
        {'target_return', 'volatility', 'return', 'sharpe', 'weights': {cls: wt}}

    Degenerate cases (fewer than 2 eligible classes, or scipy failures) fall
    back gracefully rather than raising.
    """
    apply_capital_market_config(c)
    try:
        selected = compute_optimal_allocation(c, force_mode=force_mode)
        targets = selected.get('liquid_targets') or {}
    except Exception:
        targets = {}
    classes = [cls for cls, wt in targets.items() if cls in ASSET_CLASSES and float(wt or 0) > 0]
    if len(classes) < 2:
        # Fall back to all enabled asset classes if the recommended solution
        # collapsed to a single class (e.g. all liquid assets swept to cash).
        classes = [cls for cls in ASSET_CLASSES if allocation_class_enabled(c, cls)]
    if len(classes) < 2:
        classes = list(ASSET_CLASSES.keys())

    n = len(classes)
    rf = risk_free_rate(c)
    if n == 0:
        return []

    mu = np.array([float(ASSET_CLASSES[cls].get('ret', 0.0) or 0.0) for cls in classes], dtype=float)

    if n == 1:
        vol = float(ASSET_CLASSES[classes[0]].get('vol', 0.0) or 0.0)
        ret = float(mu[0])
        return [{
            'target_return': ret,
            'volatility': vol,
            'return': ret,
            'sharpe': sharpe_ratio(ret, vol, rf),
            'weights': {classes[0]: 1.0},
        }]

    try:
        cov = build_covariance_matrix(classes) + np.eye(n) * 1e-6
    except Exception:
        return []

    bounds = [(0.0, 1.0) for _ in range(n)]
    points = []

    try:
        from scipy.optimize import minimize

        w_min = _min_variance_portfolio(cov, n, bounds)
        r0 = float(w_min @ mu)
        ret_hi = float(np.max(mu))

        n_points = max(2, int(n_points))
        if ret_hi <= r0 + 1e-12:
            targets_grid = [r0]
        else:
            targets_grid = list(np.linspace(r0, ret_hi, n_points))

        def variance(w):
            return float(w @ cov @ w)

        x0 = w_min.copy()
        for target in targets_grid:
            constraints = [
                {'type': 'eq', 'fun': lambda w: float(np.sum(w) - 1.0)},
                {'type': 'eq', 'fun': lambda w, t=target: float(w @ mu - t)},
            ]
            try:
                res = minimize(variance, x0, method='SLSQP', bounds=bounds, constraints=constraints,
                               options={'maxiter': 500, 'ftol': 1e-12})
            except Exception:
                continue
            if not res.success:
                continue
            w = np.maximum(np.array(res.x, dtype=float), 0.0)
            total = w.sum()
            if total <= 0:
                continue
            w = w / total
            port_ret = float(w @ mu)
            port_var = max(0.0, float(w @ cov @ w))
            vol = float(np.sqrt(port_var))
            points.append({
                'target_return': float(target),
                'volatility': vol,
                'return': port_ret,
                'sharpe': sharpe_ratio(port_ret, vol, rf),
                'weights': {classes[i]: float(w[i]) for i in range(n)},
            })
            x0 = w  # warm-start the next solve from the previous solution
    except Exception:
        points = []

    if not points:
        # Full fallback: surface at least the min-variance corner portfolio so
        # callers still get a usable (if degenerate) frontier instead of an
        # empty list or a raised exception.
        try:
            w_min = _min_variance_portfolio(cov, n, bounds)
            port_ret = float(w_min @ mu)
            vol = float(np.sqrt(max(0.0, float(w_min @ cov @ w_min))))
            points = [{
                'target_return': port_ret,
                'volatility': vol,
                'return': port_ret,
                'sharpe': sharpe_ratio(port_ret, vol, rf),
                'weights': {classes[i]: float(w_min[i]) for i in range(n)},
            }]
        except Exception:
            return []

    points.sort(key=lambda p: (p['volatility'], p['return']))
    return points


# ===== END allocation_optimizer.py =====
